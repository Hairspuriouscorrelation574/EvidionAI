import concurrent.futures
import threading
from typing import Any


class CancelledByUser(Exception):
    """Raised when the user cancels an in-flight LLM call."""


_llm_pool = concurrent.futures.ThreadPoolExecutor(
    max_workers=16,
    thread_name_prefix="llm_worker",
)


class CancellableLLM:
    """
    Thin wrapper around any LangChain LLM that polls a threading.Event
    and raises CancelledByUser if the event is set before or during the call.
    """

    POLL_INTERVAL = 0.5  # seconds between cancel checks

    def __init__(self, llm: Any, cancel_event: threading.Event):
        object.__setattr__(self, "_llm", llm)
        object.__setattr__(self, "_cancel_event", cancel_event)

    def __getattr__(self, name: str) -> Any:
        return getattr(object.__getattribute__(self, "_llm"), name)

    def invoke(self, prompt: Any, **kwargs) -> Any:
        llm = object.__getattribute__(self, "_llm")
        cancel_event = object.__getattribute__(self, "_cancel_event")

        if cancel_event and cancel_event.is_set():
            raise CancelledByUser("Cancelled before LLM call started")

        future = _llm_pool.submit(llm.invoke, prompt, **kwargs)

        while True:
            try:
                return future.result(timeout=self.POLL_INTERVAL)
            except concurrent.futures.TimeoutError:
                if cancel_event and cancel_event.is_set():
                    future.cancel()
                    raise CancelledByUser("LLM call interrupted by user cancel")
            except concurrent.futures.CancelledError:
                raise CancelledByUser("LLM future was cancelled")
