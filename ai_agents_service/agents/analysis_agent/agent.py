from typing import Dict, Any
import json
import logging
from datetime import datetime
from utils.schema import AgentState
from .prompt import ANALYSIS_AGENT_PROMPTS

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class AnalysisAgent:
    """Agent for deep analysis and synthesis of information"""
    
    def __init__(self, llm: Any):
        self.llm = llm
    
    def run(self, state: AgentState) -> Dict[str, Any]:
        """Perform comprehensive analysis"""
        logger.info("🧠 Analysis Agent activated...")
        
        query = state["user_input"]
        search_data = state.get("search_results", [])
        code_data = state.get("code_solutions", [])

        analysis_context = {
            "query": query,
            "search_sources": search_data,
            "code_solutions": code_data,
            "total_iterations": state["iteration"],
            "status": state.get("status", "processing")
        }
        
        prompt = ANALYSIS_AGENT_PROMPTS["comprehensive_analysis"].format(
            query=query,
            instructions = state["supervisor_instructions"][-1],
            analysis_context=json.dumps(analysis_context, indent=2),
            search_count=len(search_data),
            code_count=len(code_data),
        )

        analysis = self.llm.invoke(prompt)
        
        return {
            "analyses": state.get("analyses", []) + [{
                "type": "comprehensive_analysis",
                "content": analysis,
                "timestamp": datetime.now().isoformat()
            }],
            "current_agent": "supervisor",
            "messages": state["messages"] + [
                {"role": "assistant (analysis agent)", "content": f"Analysis Agent completed: Generated comprehensive analysis."}
            ],
            "history": state["history"] + [
                {"role": "Supervisor to Analysis Agent", "content": prompt},
                {"role": "Analysis Agent", "content": analysis}
            ],
            "last_update": datetime.now().isoformat()
        }
