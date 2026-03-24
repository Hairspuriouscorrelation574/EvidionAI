import asyncio
import concurrent.futures
import json
import logging
import os
import threading
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from memory.memory_manager import MemoryManager
from pipeline import MultiAgentChat
from utils.cancellable_llm import CancelledByUser
from utils.llm import llm as base_llm

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
)
log = logging.getLogger("ai_agents_service")

HEARTBEAT_INTERVAL = 15  # seconds between SSE keepalive pings
POLL_SLICE = 0.25  # seconds between future.done() checks

_registry: Dict[str, Dict] = {}
_lock = threading.Lock()
_pool = concurrent.futures.ThreadPoolExecutor(
    max_workers=int(os.getenv("WORKER_THREADS", "4")),
    thread_name_prefix="evidion_worker",
)

app = FastAPI(
    title="EvidionAI — Agents Service",
    description="Internal SSE service that runs the multi-agent research workflow.",
    version="1.0.0",
)


class QueryRequest(BaseModel):
    query: str = Field(..., alias="query")
    chat_context: List[Dict[str, Any]] = Field(default_factory=list)
    request_id: Optional[str] = None
    session_id: Optional[str] = None
    memory_id: Optional[str] = None


class CancelRequest(BaseModel):
    request_id: str


def _run_query(
    request_id: str,
    user_input: str,
    chat_context: list,
    cancel_event: threading.Event,
    memory_id: Optional[str] = None,
):
    """Run the agent workflow in a thread-pool worker.

    Returns:
        Tuple of (final_answer, full_history).
    """
    with _lock:
        if request_id in _registry:
            _registry[request_id]["thread_id"] = threading.current_thread().ident

    memory_manager = None
    if memory_id:
        try:
            memory_manager = MemoryManager(memory_id=memory_id)
        except Exception as exc:
            log.warning("[%s] Memory init failed (non-critical): %s", request_id, exc)

    try:
        return MultiAgentChat(memory_manager=memory_manager).process_query(
            user_input, chat_context, cancel_event=cancel_event
        )
    except CancelledByUser:
        log.info("[%s] Cancelled by user", request_id)
        return ("[Research was cancelled by the user.]", [])
    except Exception as exc:
        log.error("[%s] Worker error: %s", request_id, exc, exc_info=True)
        return (f"System error: {exc}", [])
    finally:
        with _lock:
            _registry.pop(request_id, None)


@app.post("/process", summary="Run AI agent workflow (SSE stream)")
async def process(request: QueryRequest):
    request_id = request.request_id or "default"
    cancel_event = threading.Event()

    with _lock:
        _registry[request_id] = {"thread_id": None, "event": cancel_event}

    memory_id = request.memory_id or request.session_id
    future = _pool.submit(
        _run_query,
        request_id,
        request.query,
        request.chat_context,
        cancel_event,
        memory_id,
    )

    with _lock:
        if request_id in _registry:
            _registry[request_id]["future"] = future

    async def event_stream():
        elapsed = 0.0
        try:
            while True:
                await asyncio.sleep(POLL_SLICE)
                elapsed += POLL_SLICE

                if future.done():
                    try:
                        final_answer, full_history = future.result()
                    except CancelledByUser:
                        final_answer, full_history = "[Research was cancelled by the user.]", []
                    except Exception as exc:
                        log.error("[%s] future.result() error: %s", request_id, exc, exc_info=True)
                        final_answer, full_history = f"System error: {exc}", []

                    log.info("[%s] Finished — %d chars", request_id, len(final_answer))
                    payload = json.dumps(
                        {"final_answer": final_answer, "full_history": full_history or []},
                        ensure_ascii=False,
                    )
                    yield f"event: result\ndata: {payload}\n\n"
                    return

                if elapsed >= HEARTBEAT_INTERVAL:
                    elapsed = 0.0
                    yield "event: ping\ndata: {}\n\n"

        except GeneratorExit:
            log.info("[%s] SSE client disconnected", request_id)
        except Exception as exc:
            log.error("[%s] event_stream error: %s", request_id, exc, exc_info=True)
            payload = json.dumps({"final_answer": f"Stream error: {exc}", "full_history": []})
            yield f"event: error\ndata: {payload}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@app.post("/cancel", status_code=status.HTTP_200_OK, summary="Cancel a running workflow")
async def cancel(req: CancelRequest):
    with _lock:
        entry = _registry.get(req.request_id)
    if not entry:
        return {"cancelled": False, "detail": "No active request with that id"}
    entry["event"].set()
    log.info("Cancel event set for request_id=%s", req.request_id)
    return {"cancelled": True}


@app.get("/memory/stats", summary="Memory statistics for a namespace")
async def memory_stats(memory_id: str):
    mem = MemoryManager(memory_id=memory_id)
    return mem.get_stats()


@app.get("/memory/recall", summary="Query long-term memory")
async def memory_recall(memory_id: str, q: str, k: int = 5):
    mem = MemoryManager(memory_id=memory_id)
    return {"query": q, "results": mem.recall(q, k=k)}


@app.get("/health", summary="Health check")
async def health():
    return {"status": "ok"}
