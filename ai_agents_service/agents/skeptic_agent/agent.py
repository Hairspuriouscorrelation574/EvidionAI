from typing import Dict, Any
import logging
from datetime import datetime
from utils.schema import AgentState
from .prompt import SKEPTIC_AGENT_PROMPTS

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class SkepticAgent:
    """Agent providing critical counter-analysis"""
    
    def __init__(self, llm: Any):
        self.llm = llm

    def _build_analysis_context(self, state: AgentState) -> str:
        """Build detailed context for critical analysis"""
        context = []

        context.append(f"ORIGINAL QUERY: {state['user_input']}")

        search_results = state.get("search_results", [])
        if search_results:
            context.append(f"\nSEARCH RESULTS ({len(search_results)} total):")
            for i, result in enumerate(search_results, 1):
                source = result.get("source", "unknown")
                analysis = result.get("analysis", "")
                quality = result.get("quality", {}).get("score", "N/A")
                context.append(f"{i}. {source} (Quality: {quality}/10)")
                context.append(f"   Analysis: {analysis}")

        code_solutions = state.get("code_solutions", [])
        if code_solutions:
            context.append(f"\nCODE SOLUTIONS ({len(code_solutions)} total):")
            for solution in code_solutions:
                req = solution.get("requirements", {})
                langs = req.get("languages", ["python"])
                context.append(f"- Languages: {', '.join(langs)}")
                context.append(f"  Analysis: {solution.get('analysis', '')}")

        analyses = state.get("analyses", [])
        if analyses:
            context.append(f"\nPREVIOUS ANALYSES ({len(analyses)} total):")
            for analysis in analyses:
                a_type = analysis.get("type", "unknown")
                content = analysis.get("content", "")
                context.append(f"[{a_type}]: {content}")
        
        return "\n".join(context)
    
    def _generate_critique(self, query: str, instructions: str, context: str) -> Dict[str, Any]:
        """Generate structured critique"""
        prompt = SKEPTIC_AGENT_PROMPTS["detailed_critique"].format(
            query=query,
            instructions=instructions,
            context=context
        )
        
        response = self.llm.invoke(prompt)

        return {
            "timestamp": datetime.now().isoformat(),
            "agent": "skeptic",
            "prompt": prompt,
            "content": response
        }
    
    def run(self, state: AgentState) -> Dict[str, Any]:
        """Execute detailed critical analysis"""
        logger.info("🔍 Skeptic Agent: Critical evaluation")
        
        context = self._build_analysis_context(state)
        
        instructions = state["supervisor_instructions"][-1]

        critique = self._generate_critique(state["user_input"], instructions, context)

        history = [{"role": "Supervisor to Skeptic Agent", "content": critique["prompt"]},
                   {"role": "Skeptic Agent", "content": critique["content"]}]
        
        critique.pop("prompt")

        return {
            "current_agent": "supervisor",
            "critiques": state.get("critiques", []) + [critique],
            "messages": state["messages"] + [
                {"role": "assistant (skeptic agent)", "content": f"Skeptic: Critical analysis completed. Critical analysis is available in the section Critiques."}
            ],
            "history": state["history"] + history,
            "last_update": datetime.now().isoformat()
        }
