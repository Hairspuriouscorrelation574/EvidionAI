from typing import Dict, Tuple, List, Any
import json
import logging
from datetime import datetime
from utils.schema import AgentState
from .prompt import SUPERVISOR_PROMPTS

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class Supervisor:
    """Main supervisor agent that coordinates all other agents"""
    
    def __init__(self, llm: Any):
        self.llm = llm
        self.max_iterations = 50
        self.quality_threshold = 8
    
    def decide_next_action(self, state: AgentState) -> Tuple[Dict[str, Any], str]:
        """Make intelligent decision about next step"""
        logger.info(f"🎯 Supervisor making decision (Iteration {state['iteration']})...")
        
        recent_history = state.get("messages", [])
        history_text = "\n".join([f"{msg.get('role', 'unknown')}: {msg.get('content', '')}" 
                                 for msg in recent_history])
        
        agent_history = state.get("agent_history", [])
        recent_agents = agent_history
        
        prompt = SUPERVISOR_PROMPTS["decision_making"].format(
            iteration=state["iteration"],
            user_input=state["user_input"],
            search=state.get("search_results", []),
            code=state.get("code_solutions", []),
            analysis=state.get("analyses", []),
            skeptic=state.get("critiques", []),
            agent_history=", ".join([a.get("agent", "unknown") for a in recent_agents]),
            recent_history=history_text
        )
        
        response = self.llm.invoke(prompt)

        logger.info(f"Decision response: {response}")
        
        try:
            if "{" in response and "}" in response:
                json_start = response.find("{")
                json_end = response.rfind("}") + 1
                json_str = response[json_start:json_end]
                decision = json.loads(json_str)
                
                if decision.get("next_agent") not in ["search", "code", "analyze", "skeptic", "done"]:
                    decision["next_agent"] = "done"
                
                return [decision, prompt, response]
        except:
            logger.info(f"Error in parsing supervisor agent JSON on decision: {response}")
            return [{}, response]
    
    def create_final_report(self, state: AgentState, instructions: str) -> List[str]:
        """Create comprehensive final report"""
        logger.info("📝 Supervisor creating final report...")
        
        search_summary = "\n".join([
            f"- {r.get('source', 'unknown')}: {r.get('analysis', '')}..."
            for r in state.get("search_results", [])
        ]) if state.get("search_results") else "No search results"
        
        code_summary = "\n".join([
            f"- Solution {i+1}: {s.get('requirements', {}).get('languages', ['python'])[0]} - Complexity: {s.get('requirements', {}).get('complexity', 'unknown')}"
            for i, s in enumerate(state.get("code_solutions", []))
        ]) if state.get("code_solutions") else "No code solutions"
        
        analysis_summary = "\n".join([
            f"- Analysis {i+1}: {a.get('type', 'unknown')}"
            for i, a in enumerate(state.get("analyses", []))
        ]) if state.get("analyses") else "No analyses"
        
        skeptic_summary = "\n".join([
            f"- Skeptic {i+1}: {a.get('type', 'unknown')}"
            for i, a in enumerate(state.get("critiques", []))
        ]) if state.get("critiques") else "No critiques"

        recent_history = state.get("messages", [])
        history_text = "\n".join([f"{msg.get('role', 'unknown')}: {msg.get('content', '')}" 
                                 for msg in recent_history])

        prompt = SUPERVISOR_PROMPTS["final_synthesis"].format(
            user_input=state["user_input"],
            instructions=instructions,
            iteration=state["iteration"],
            search_count=len(state.get("search_results", [])),
            code_count=len(state.get("code_solutions", [])),
            analysis_count=len(state.get("analyses", [])),
            skeptic_count=len(state.get("critiques", [])),
            search_summary=search_summary,
            code_summary=code_summary,
            analysis_summary=analysis_summary,
            skeptic_summary=skeptic_summary,
            recent_history=history_text
        )
        
        return [self.llm.invoke(prompt), prompt]
    
    def run(self, state: AgentState) -> Dict[str, Any]:
        """Execute supervisor coordination"""
        if state["iteration"] >= self.max_iterations:
            logger.warning(f"⚠️ Maximum iterations reached ({self.max_iterations})")
            final_report, prompt = self.create_final_report(state)

            history = [{"role": "Supervisor to Supervisor", "content": prompt},
                       {"role": "Supervisor", "content": final_report}]
            
            logger.info(f"Final report:\n {final_report}")

            return {
                "current_agent": "done",
                "final_answer": final_report,
                "history": state["history"] + history,
                "status": "complete",
                "last_update": datetime.now().isoformat()
            }

        if state.get("_cancel_event") and state["_cancel_event"].is_set():
            logger.info("🛑 Cancel event detected — stopping workflow")
            return {
                "current_agent": "done",
                "final_answer": "[Research was cancelled by the user.]",
                "history": state.get("history", []),
                "status": "cancelled",
                "last_update": datetime.now().isoformat()
            }

        decision, prompt, response = self.decide_next_action(state)
        next_agent = decision.get("next_agent", "done")

        history = [{"role": "Supervisor to Supervisor", "content": prompt},
                   {"role": "Supervisor", "content": response}]
        
        logger.info(f"Supervisor decision: {next_agent} (Quality: {decision.get('quality_score', 'N/A')})")
        
        if next_agent == "done":
            instructions = decision.get("instructions", "No instructions provided")
            final_report, prompt = self.create_final_report(state, instructions)

            history = [{"role": "Supervisor to Supervisor", "content": prompt},
                       {"role": "Supervisor", "content": final_report}]

            logger.info(f"Final report:\n {final_report}")
            
            return {
                "current_agent": "done",
                "final_answer": final_report,
                "history": state["history"] + history,
                "status": "complete",
                "last_update": datetime.now().isoformat()
            }
        else:
            return {
                "current_agent": next_agent,
                "messages": state["messages"] + [{
                    "role": "assistant (supervisor agent)", 
                    "content": f"Supervisor → {next_agent.upper()}: {decision.get('reasoning', 'No reasoning provided')}..."
                }],
                "history": state["history"] + history,
                "agent_history": state.get("agent_history", []) + [{
                    "agent": next_agent,
                    "iteration": state["iteration"],
                    "reasoning": decision.get("reasoning", ""),
                    "timestamp": datetime.now().isoformat()
                }],
                "supervisor_instructions": state["supervisor_instructions"] + [decision.get("instructions", "No instructions provided")],
                "iteration": state["iteration"] + 1,
                "last_update": datetime.now().isoformat()
            }
