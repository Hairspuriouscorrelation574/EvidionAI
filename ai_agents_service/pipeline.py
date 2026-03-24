import logging
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from utils.cancellable_llm import CancellableLLM, CancelledByUser
from utils.context_manager import ContextManager
from utils.llm import llm as base_llm
from utils.schema import AgentState
from workflow.workflow import create_workflow

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger(__name__)


class MultiAgentChat:
    """Entry point for the multi-agent research workflow."""

    def __init__(self, memory_manager=None):
        self.conversation_history = []
        self.session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.mem = memory_manager
        self.ctx = ContextManager(llm=base_llm)

    def _build_memory_context(self, user_input: str) -> str:
        if not self.mem:
            return ""
        try:
            return self.mem.recall_context_for_query(user_input, k=5)
        except Exception as exc:
            logger.warning("Memory recall failed: %s", exc)
            return ""

    def process_query(
        self,
        user_input: str,
        chat_context: Optional[List[Dict]] = None,
        cancel_event=None,
    ) -> Tuple[str, List]:
        """Run a query through the multi-agent workflow.

        Returns:
            Tuple of (final_answer, conversation_history).
        """
        cancellable = CancellableLLM(base_llm, cancel_event) if cancel_event is not None else None
        workflow = create_workflow(llm_override=cancellable)

        memory_context = self._build_memory_context(user_input)
        context_messages = list(chat_context or [])

        if memory_context:
            context_messages = [{"role": "system", "content": memory_context}] + context_messages
            logger.info("Memory context injected (%d chars)", len(memory_context))

        if len(context_messages) > 10:
            context_messages, compressed = self.ctx.maybe_compress(
                context_messages, task=user_input
            )
            if compressed:
                summary_msg = self.ctx.get_summary_message()
                if summary_msg:
                    context_messages = [summary_msg] + context_messages

        user_message = {"role": "user", "content": user_input}
        initial_state: AgentState = {
            "user_input": user_input,
            "messages": context_messages + [user_message],
            "history": context_messages + [user_message],
            "current_agent": "supervisor",
            "agent_history": [],
            "supervisor_instructions": [],
            "search_results": [],
            "code_solutions": [],
            "analyses": [],
            "critiques": [],
            "iteration": 0,
            "final_answer": "",
            "status": "processing",
            "start_time": datetime.now().isoformat(),
            "last_update": datetime.now().isoformat(),
            "_cancel_event": cancel_event,
        }

        try:
            result = workflow.invoke(initial_state, config={"recursion_limit": 50})
            final_answer = result.get("final_answer") or "Task completed but no final answer generated."

            self.conversation_history.append({
                "query": user_input,
                "messages": result.get("messages", []),
                "history": result.get("history", []),
                "response": final_answer,
                "search_results": result.get("search_results", []),
                "code_solutions": result.get("code_solutions", []),
                "analyses": result.get("analyses", []),
                "critiques": result.get("critiques", []),
                "iterations": result.get("iteration", 0),
                "start_time": result.get("start_time", ""),
                "end_time": datetime.now().isoformat(),
            })

            if self.mem:
                try:
                    self.mem.save_session(
                        session_id=self.session_id,
                        user_input=user_input,
                        final_answer=final_answer,
                        analyses=result.get("analyses", []),
                        search_results=result.get("search_results", []),
                        iterations=result.get("iteration", 0),
                    )
                except Exception as exc:
                    logger.warning("Memory save failed (non-critical): %s", exc)

            return final_answer, self.conversation_history

        except CancelledByUser:
            logger.info("Workflow cancelled by user")
            return "[Research was cancelled by the user.]", []
        except Exception as exc:
            logger.error("Workflow execution error: %s", exc, exc_info=True)
            return f"System error: {exc}", []
