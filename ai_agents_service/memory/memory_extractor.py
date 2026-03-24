import logging
import json
from typing import Any, List, Dict
from datetime import datetime

logger = logging.getLogger(__name__)


EXTRACTION_PROMPT = """You are a memory extraction system of an autonomous AI research system. Analyze the following conversation and extract:

1. USER FACTS: Any persistent facts about the user (preferences, name, job, goals, tech stack, language, etc.)
2. KEY INSIGHTS: The most important conclusions, discoveries, or answers from this session that would be useful to remember for future sessions.

Conversation:
---
USER QUERY: {user_input}

FINAL ANSWER: {final_answer}

AGENT HISTORY (brief): {agent_summary}
---

Respond ONLY with a JSON object, no markdown, no preamble:
{{
  "user_facts": ["fact1", "fact2"],
  "insights": [
    {{"content": "...", "topic": "..."}},
    ...
  ]
}}

Extract only what is clearly stated. If nothing notable, return empty arrays."""


class MemoryExtractor:
    def __init__(self, llm: Any, memory_manager: Any):
        self.llm = llm
        self.mem = memory_manager

    def extract_and_save(
        self,
        session_id: str,
        user_input: str,
        final_answer: str,
        agent_history: List[Dict],
        analyses: List[Dict] = None,
        search_results: List[Dict] = None,
        iterations: int = 0,
    ) -> Dict[str, int]:
        counts = {"session": 0, "user_facts": 0, "insights": 0}

        self.mem.save_session(
            session_id=session_id,
            user_input=user_input,
            final_answer=final_answer,
            analyses=analyses,
            search_results=search_results,
            iterations=iterations,
        )
        counts["session"] = 1

        agent_summary = self._summarize_agent_history(agent_history)

        prompt = EXTRACTION_PROMPT.format(
            user_input=user_input,
            final_answer=final_answer,
            agent_summary=agent_summary,
        )

        try:
            response = self.llm.invoke(prompt)
            clean = response.strip().lstrip("```json").lstrip("```").rstrip("```").strip()
            data = json.loads(clean)

            for fact in data.get("user_facts", []):
                if fact and len(fact) > 3:
                    self.mem.save_user_fact(fact, source_session=session_id)
                    counts["user_facts"] += 1

            for ins in data.get("insights", []):
                content = ins.get("content", "")
                topic = ins.get("topic", "general")
                if content and len(content) > 3:
                    self.mem.save_insight(content, topic=topic, source=session_id)
                    counts["insights"] += 1

        except Exception as e:
            logger.warning(f"Memory extraction LLM error: {e}")

        logger.info(f"Memory extraction done: {counts}")
        return counts

    def _summarize_agent_history(self, agent_history: List[Dict]) -> str:
        if not agent_history:
            return "No agent history"
        agents_used = list(set(a.get("agent", "?") for a in agent_history))
        return f"Agents used: {', '.join(agents_used)} ({len(agent_history)} steps)"
