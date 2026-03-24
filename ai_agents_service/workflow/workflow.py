import logging
from typing import Any, Dict, Optional

from langgraph.graph import StateGraph

from agents.analysis_agent.agent import AnalysisAgent
from agents.code_agent.agent import CodeAgent
from agents.search_agent.agent import SearchAgent
from agents.skeptic_agent.agent import SkepticAgent
from agents.supervisor.agent import Supervisor
from utils.llm import (
    llm as default_llm,
    llm_analysis_agent,
    llm_code_agent,
    llm_search_agent,
    llm_skeptic_agent,
    llm_supervisor,
)
from utils.schema import AgentState

logger = logging.getLogger(__name__)


def create_workflow(llm_override=None):
    """Build and compile the multi-agent LangGraph workflow.

    Args:
        llm_override: When provided, every agent uses this LLM instance
            (typically a CancellableLLM wrapper).  When None, each agent
            uses its own temperature-tuned LLM.

    Returns:
        A compiled LangGraph graph ready to call ``.invoke()``.
    """
    if llm_override is not None:
        supervisor = Supervisor(llm=llm_override)
        search_agent = SearchAgent(llm=llm_override)
        code_agent = CodeAgent(llm=llm_override)
        analysis_agent = AnalysisAgent(llm=llm_override)
        skeptic_agent = SkepticAgent(llm=llm_override)
    else:
        supervisor = Supervisor(llm=llm_supervisor)
        search_agent = SearchAgent(llm=llm_search_agent)
        code_agent = CodeAgent(llm=llm_code_agent)
        analysis_agent = AnalysisAgent(llm=llm_analysis_agent)
        skeptic_agent = SkepticAgent(llm=llm_skeptic_agent)

    def supervisor_node(state: AgentState) -> Dict[str, Any]:
        return supervisor.run(state)

    def search_node(state: AgentState) -> Dict[str, Any]:
        return search_agent.run(state)

    def code_node(state: AgentState) -> Dict[str, Any]:
        return code_agent.run(state)

    def analysis_node(state: AgentState) -> Dict[str, Any]:
        return analysis_agent.run(state)

    def skeptic_node(state: AgentState) -> Dict[str, Any]:
        return skeptic_agent.run(state)

    def done_node(state: AgentState) -> Dict[str, Any]:
        return state

    def route_next(state: AgentState) -> str:
        next_agent = state.get("current_agent", "supervisor")
        logger.info("Routing to: %s", next_agent)
        return next_agent

    workflow = StateGraph(AgentState)
    workflow.add_node("supervisor", supervisor_node)
    workflow.add_node("search", search_node)
    workflow.add_node("code", code_node)
    workflow.add_node("analyze", analysis_node)
    workflow.add_node("skeptic", skeptic_node)
    workflow.add_node("done", done_node)

    workflow.set_entry_point("supervisor")
    workflow.add_conditional_edges(
        "supervisor",
        route_next,
        {
            "search": "search",
            "code": "code",
            "analyze": "analyze",
            "skeptic": "skeptic",
            "done": "done",
            "supervisor": "supervisor",
        },
    )
    workflow.add_edge("search", "supervisor")
    workflow.add_edge("code", "supervisor")
    workflow.add_edge("analyze", "supervisor")
    workflow.add_edge("skeptic", "supervisor")

    graph = workflow.compile()
    logger.info("Workflow graph compiled successfully")
    return graph
