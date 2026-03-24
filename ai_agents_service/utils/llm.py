"""
LLM provider factory.

Supported providers (set LLM_PROVIDER in .env):
  - ollama_local  — Ollama running on your machine
  - ollama_cloud  — Ollama Cloud (api.ollama.com) with an API key
  - openai        — OpenAI or any OpenAI-compatible API (Groq, Together, etc.)
"""

import os
import logging
from dotenv import load_dotenv

load_dotenv()

log = logging.getLogger(__name__)

LLM_PROVIDER = os.getenv("LLM_PROVIDER", "ollama_local").lower()
LLM_MODEL = os.getenv("LLM_MODEL", "llama3.1:8b")


def _make_ollama_local(model: str, temperature: float):
    """Local Ollama — no authentication needed."""
    from langchain_ollama import OllamaLLM

    return OllamaLLM(
        model=model,
        base_url=os.getenv("OLLAMA_HOST", "http://localhost:11434"),
        temperature=temperature,
        num_ctx=int(os.getenv("LLM_CTX", "16384")),
    )


def _make_ollama_cloud(model: str, temperature: float):
    """
    Ollama Cloud via langchain-ollama.

    The ollama Python package constructs an httpx.Client with the Authorization
    header at import time and encodes it as ASCII — crashing on non-ASCII keys.
    Workaround: set OLLAMA_HOST before the import so the internal client
    initialises with the correct URL, then pass the key via `headers` which
    langchain-ollama forwards directly to requests (bypassing the buggy path).
    """
    api_key = os.getenv("OLLAMA_API_KEY", "")
    base_url = os.getenv("OLLAMA_BASE_URL", "https://api.ollama.com")
    if not api_key:
        raise ValueError("OLLAMA_API_KEY is required for ollama_cloud provider")

    os.environ["OLLAMA_HOST"] = base_url

    from langchain_ollama import OllamaLLM

    return OllamaLLM(
        model=model,
        base_url=base_url,
        headers={"Authorization": f"Bearer {api_key}"},
        temperature=temperature,
        num_ctx=int(os.getenv("LLM_CTX", "32768")),
    )


def _make_openai(model: str, temperature: float):
    """OpenAI or any OpenAI-compatible API (Groq, Together, Anthropic proxy, etc.)."""
    api_key = os.getenv("OPENAI_API_KEY", "")
    if not api_key:
        raise ValueError("OPENAI_API_KEY is required for openai provider")

    from langchain_openai import ChatOpenAI

    kwargs = dict(model=model, api_key=api_key, temperature=temperature)
    base_url = os.getenv("OPENAI_BASE_URL", "")
    if base_url:
        kwargs["base_url"] = base_url
    return ChatOpenAI(**kwargs)


def _make(temperature: float):
    if LLM_PROVIDER == "ollama_local":
        return _make_ollama_local(LLM_MODEL, temperature)
    if LLM_PROVIDER == "ollama_cloud":
        return _make_ollama_cloud(LLM_MODEL, temperature)
    if LLM_PROVIDER == "openai":
        return _make_openai(LLM_MODEL, temperature)
    raise ValueError(
        f"Unknown LLM_PROVIDER='{LLM_PROVIDER}'. "
        "Valid values: ollama_local, ollama_cloud, openai"
    )


try:
    llm = _make(0.20)
    llm_supervisor = _make(0.40)
    llm_search_agent = _make(0.20)
    llm_code_agent = _make(0.05)
    llm_analysis_agent = _make(0.55)
    llm_skeptic_agent = _make(0.75)
    log.info("LLMs loaded — provider=%s model=%s", LLM_PROVIDER, LLM_MODEL)
except Exception as exc:
    log.error("Failed to load LLM (provider=%s model=%s): %s", LLM_PROVIDER, LLM_MODEL, exc)
    raise
