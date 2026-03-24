import json
import logging
import os

import httpx
from fastapi import APIRouter, HTTPException, status
from fastapi.responses import StreamingResponse

from .config import base_url, port
from .models import QueryRequest

log = logging.getLogger("api_gateway.ai")
router = APIRouter()

_MAX_QUERY_LEN = int(os.getenv("AI_QUERY_MAX_LENGTH", "5000"))
_TIMEOUT = float(os.getenv("AI_REQUEST_TIMEOUT", "14400"))  # 4 hours


@router.post(
    "/process",
    summary="Run a research workflow",
    description=(
        "Submit a research query. Returns a **Server-Sent Events** stream.\n\n"
        "Event types:\n"
        "- `ping` — keepalive heartbeat (~15 s interval)\n"
        "- `result` — final answer + full agent trace (JSON)\n"
        "- `error` — fatal error (JSON)\n\n"
        "The stream closes after `result` or `error`."
    ),
)
async def process(req: QueryRequest):
    query = req.query.strip()
    if not query:
        raise HTTPException(400, "Query cannot be empty")
    if len(query) > _MAX_QUERY_LEN:
        raise HTTPException(400, f"Query too long (max {_MAX_QUERY_LEN} chars)")

    log.info("AI request: %d chars, id=%s", len(query), req.request_id)

    async def _stream():
        timeout = httpx.Timeout(connect=30, read=_TIMEOUT, write=60, pool=_TIMEOUT)
        async with httpx.AsyncClient(timeout=timeout) as client:
            try:
                async with client.stream(
                    "POST",
                    f"http://{base_url}:{port}/process",
                    json={
                        "query": query,
                        "chat_context": req.chat_context,
                        "request_id": req.request_id,
                        "session_id": req.session_id,
                        "memory_id": req.memory_id,
                    },
                ) as resp:
                    if resp.status_code != 200:
                        body = await resp.aread()
                        log.error("Agents service %d: %s", resp.status_code, body[:200])
                        payload = json.dumps({
                            "final_answer": f"[ERROR] Agents service returned {resp.status_code}",
                            "full_history": [],
                        })
                        yield f"event: error\ndata: {payload}\n\n"
                        return
                    async for chunk in resp.aiter_text():
                        if chunk:
                            yield chunk

            except httpx.TimeoutException:
                log.warning("[%s] Gateway read timeout — agent still running", req.request_id)

            except httpx.RequestError as exc:
                log.error("Agents service unreachable: %s", exc)
                payload = json.dumps({"final_answer": "[ERROR] AI service unavailable.", "full_history": []})
                yield f"event: error\ndata: {payload}\n\n"

            except Exception as exc:
                log.error("Stream error: %s", exc, exc_info=True)
                payload = json.dumps({"final_answer": f"[ERROR] {exc}", "full_history": []})
                yield f"event: error\ndata: {payload}\n\n"

    return StreamingResponse(
        _stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@router.post("/cancel", summary="Cancel a running workflow", status_code=status.HTTP_200_OK)
async def cancel(body: dict):
    request_id = body.get("request_id", "default")
    async with httpx.AsyncClient(timeout=10) as client:
        try:
            resp = await client.post(
                f"http://{base_url}:{port}/cancel",
                json={"request_id": request_id},
            )
            return resp.json()
        except Exception as exc:
            log.warning("Cancel failed: %s", exc)
            return {"cancelled": False}
