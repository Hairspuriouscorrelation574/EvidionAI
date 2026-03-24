from typing import Any, Dict, List, Literal, Optional, TypedDict


class AgentState(TypedDict):
    """Shared state passed between agents in the research workflow."""

    # Input
    user_input: str
    messages: List[Dict[str, str]]
    history: List[Dict[str, str]]

    # Agent routing
    current_agent: Literal["supervisor", "search", "code", "done", "analyze", "skeptic"]
    agent_history: List[Dict[str, Any]]
    supervisor_instructions: List[str]

    # Collected data
    search_results: List[Dict[str, Any]]
    code_solutions: List[Dict[str, Any]]
    analyses: List[Dict[str, Any]]
    critiques: List[str]

    # Runtime — not persisted to DB
    _cancel_event: Optional[Any]

    # Execution control
    iteration: int

    # Output
    final_answer: str
    status: Literal["processing", "success", "failed", "need_clarification", "complete"]

    # Metadata
    start_time: str
    last_update: str
