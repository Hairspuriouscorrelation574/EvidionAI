from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional


class QueryRequest(BaseModel):
    """Payload for starting a new research workflow."""
    query: str = Field(..., description="Research question or task")
    chat_context: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Previous messages for context (role/content pairs)",
    )
    request_id: Optional[str] = Field(None, description="Client-supplied idempotency key")
    session_id: Optional[str] = Field(None, description="Session to append results to")
    memory_id: Optional[str] = Field(None, description="Memory namespace for long-term recall")


class QueryResponse(BaseModel):
    final_answer: str
    full_history: List[Dict[str, Any]]
