"""
Long-term semantic memory backed by ChromaDB.

Memory is namespaced by a single ``memory_id`` string — typically the
project slug or session id.  Passing the same id across sessions lets the
system accumulate knowledge; different ids keep namespaces isolated.
"""

import logging
import os
import uuid
from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

log = logging.getLogger(__name__)

MemoryType = Literal["session_summary", "user_fact", "agent_insight"]

MEMORY_DIR = os.getenv("MEMORY_DIR", "./data/memory")

_chroma_client = None
_embedding_fn = None


def _get_chroma():
    global _chroma_client, _embedding_fn
    if _chroma_client is not None:
        return _chroma_client, _embedding_fn

    import chromadb

    os.makedirs(MEMORY_DIR, exist_ok=True)
    _chroma_client = chromadb.PersistentClient(path=MEMORY_DIR)

    try:
        from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction

        _embedding_fn = SentenceTransformerEmbeddingFunction(model_name="all-MiniLM-L6-v2")
        log.info("ChromaDB initialised with SentenceTransformer at %s", MEMORY_DIR)
    except Exception as exc:
        log.warning("SentenceTransformer unavailable (%s), using ChromaDB default embeddings", exc)
        _embedding_fn = None

    return _chroma_client, _embedding_fn


def _sanitize(memory_id: str) -> str:
    """Return a ChromaDB-safe collection name derived from memory_id."""
    safe = "".join(c if c.isalnum() or c == "_" else "_" for c in memory_id)
    return f"mem_{safe}"[:63]


class MemoryManager:
    """Vector-backed long-term memory for an agent session."""

    def __init__(self, memory_id: str):
        if not memory_id:
            raise ValueError("memory_id is required")
        self.memory_id = str(memory_id)
        client, emb_fn = _get_chroma()
        self._col = client.get_or_create_collection(
            name=_sanitize(self.memory_id),
            embedding_function=emb_fn,
            metadata={"hnsw:space": "cosine"},
        )
        log.debug("MemoryManager ready: memory_id=%s", self.memory_id)

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def save(
        self,
        content: str,
        memory_type: MemoryType,
        metadata: Optional[Dict[str, Any]] = None,
        memory_id_key: Optional[str] = None,
    ) -> str:
        mid = memory_id_key or str(uuid.uuid4())
        meta = {
            "memory_type": memory_type,
            "memory_id": self.memory_id,
            "created_at": datetime.utcnow().isoformat(),
            **(metadata or {}),
        }
        self._col.upsert(ids=[mid], documents=[content], metadatas=[meta])
        return mid

    def save_session(
        self,
        session_id: str,
        user_input: str,
        final_answer: str,
        analyses: Optional[List[Dict]] = None,
        search_results: Optional[List[Dict]] = None,
        iterations: int = 0,
    ) -> str:
        analyses_text = ""
        if analyses:
            analyses_text = " | ".join(
                f"{a.get('type', 'analysis')}: {a.get('content', '')}"
                for a in analyses[:3]
            )
        content = "\n".join([
            f"SESSION: {session_id}",
            f"USER QUERY: {user_input}",
            f"FINAL ANSWER SUMMARY: {final_answer[:500]}",
            f"ANALYSES: {analyses_text or 'none'}",
            f"ITERATIONS: {iterations}",
        ])
        return self.save(
            content,
            "session_summary",
            {"session_id": session_id, "iterations": iterations},
        )

    def save_insight(self, insight: str, topic: str, source: str = "agent") -> str:
        return self.save(insight, "agent_insight", {"topic": topic, "source": source})

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def recall(
        self,
        query: str,
        k: int = 5,
        memory_type: Optional[MemoryType] = None,
    ) -> List[Dict[str, Any]]:
        total = self._col.count()
        if total == 0:
            return []

        where: Dict[str, Any] = {"memory_id": self.memory_id}
        if memory_type:
            where = {"$and": [{"memory_id": self.memory_id}, {"memory_type": memory_type}]}

        try:
            result = self._col.query(
                query_texts=[query],
                n_results=min(k, total),
                where=where,
            )
        except Exception as exc:
            log.warning("ChromaDB query error: %s", exc)
            return []

        return [
            {
                "id": result["ids"][0][i],
                "content": doc,
                "metadata": result["metadatas"][0][i],
                "score": 1.0 - result["distances"][0][i],
            }
            for i, doc in enumerate(result["documents"][0])
        ]

    def recall_context_for_query(self, user_input: str, k: int = 5) -> str:
        memories = self.recall(user_input, k=k)
        if not memories:
            return ""
        lines = ["=== RELEVANT MEMORIES ==="]
        for m in memories:
            mtype = m["metadata"].get("memory_type", "unknown")
            created = m["metadata"].get("created_at", "")[:10]
            score = m.get("score", 0.0)
            lines.append(f"[{mtype} | {created} | relevance={score:.2f}]")
            lines.append(m["content"][:1000])
            lines.append("---")
        return "\n".join(lines)

    def get_stats(self) -> Dict[str, Any]:
        return {
            "backend": "chromadb",
            "memory_id": self.memory_id,
            "total": self._col.count(),
        }
