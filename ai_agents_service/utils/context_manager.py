import logging
import os

log = logging.getLogger(__name__)

MAX_MESSAGES = int(os.getenv("CONTEXT_MAX_MESSAGES", "30"))
COMPRESS_THRESHOLD = int(os.getenv("CONTEXT_COMPRESS_THRESHOLD", "35"))


class ContextManager:
    """Rolling window with LLM summarisation for long conversations."""

    def __init__(self, llm=None):
        self.llm = llm
        self.running_summary = ""
        self._compressions = 0

    def maybe_compress(self, messages: list, task: str = "") -> tuple:
        """
        Compress old messages into a running summary when the history grows
        beyond COMPRESS_THRESHOLD.  Returns (messages, was_compressed).
        """
        if len(messages) <= COMPRESS_THRESHOLD:
            return messages, False

        n_to_compress = len(messages) - MAX_MESSAGES
        old_msgs = messages[:n_to_compress]
        fresh_msgs = messages[n_to_compress:]

        if not self.llm or not old_msgs:
            return messages, False

        try:
            history_text = "\n".join(
                f"{m.get('role', 'unknown')}: {m.get('content', '')}"
                for m in old_msgs
            )
            prompt = (
                f"Summarize the following conversation history concisely, "
                f"preserving all key facts, decisions, URLs, code, findings, and failures. "
                f"Current task context: {task}\n\n"
                f"History to summarize:\n{history_text}\n\n"
                f"Produce a dense summary (max 600 words):"
            )
            new_summary = self.llm.invoke(prompt)
            self.running_summary = (
                f"{self.running_summary}\n\n---\n\n{new_summary}"
                if self.running_summary
                else new_summary
            )
            self._compressions += 1
            log.info(
                "Compressed %d messages → summary #%d", n_to_compress, self._compressions
            )
            return fresh_msgs, True
        except Exception as exc:
            log.warning("Compression failed: %s", exc)
            return messages, False

    def get_summary_message(self) -> dict | None:
        if not self.running_summary:
            return None
        return {
            "role": "system",
            "content": f"[Conversation history summary]\n{self.running_summary}",
        }

    def reset(self):
        self.running_summary = ""
        self._compressions = 0

    def get_stats(self) -> dict:
        return {
            "compressions": self._compressions,
            "summary_len": len(self.running_summary),
        }
