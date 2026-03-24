import re
import logging
from typing import List, Dict, Optional

import requests
from bs4 import BeautifulSoup
from langchain_community.tools import ArxivQueryRun
from langchain_community.utilities import ArxivAPIWrapper
from langchain_core.tools import Tool

logger = logging.getLogger(__name__)

arxiv_api = ArxivAPIWrapper(top_k_results=5, doc_content_chars_max=10000, load_max_docs=3)
arxiv = ArxivQueryRun(api_wrapper=arxiv_api)

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

_STRIP_TAGS = [
    "script", "style", "nav", "footer", "header",
    "aside", "form", "iframe", "button", "input", "noscript",
]
_CONTENT_TAGS = ["p", "h1", "h2", "h3", "h4", "h5", "h6", "li", "article", "section"]


def read_webpage(url: str, max_chars: int = 10000) -> str:
    """Fetch a URL and return its plain-text content."""
    try:
        resp = requests.get(url, headers=_HEADERS, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.content, "html.parser")
        for tag in soup(_STRIP_TAGS):
            tag.decompose()
        parts = [
            t.get_text(separator=" ", strip=True)
            for t in soup.find_all(_CONTENT_TAGS)
            if t.get_text(strip=True)
        ]
        text = " ".join(parts) if parts else soup.get_text(separator=" ", strip=True)
        return re.sub(r"\s+", " ", text)[:max_chars]
    except Exception as exc:
        return f"[Error reading {url}: {exc}]"


def ddg_search(query: str, max_results: int = 8) -> List[Dict]:
    """Search DuckDuckGo and return a list of {title, url, snippet} dicts."""
    try:
        from duckduckgo_search import DDGS

        with DDGS() as ddgs:
            return [
                {
                    "title": r.get("title", ""),
                    "url": r.get("href", ""),
                    "snippet": r.get("body", ""),
                }
                for r in ddgs.text(query, max_results=max_results)
            ]
    except Exception as exc:
        logger.warning("DDGS search failed: %s", exc)
        return []


def wikipedia_search(query: str, sentences: int = 10) -> Dict:
    """Search Wikipedia and return {title, url, summary}."""
    try:
        base = "https://en.wikipedia.org/w/api.php"
        search_resp = requests.get(
            base,
            params={"action": "query", "list": "search", "srsearch": query,
                    "format": "json", "srlimit": 1},
            timeout=10,
        )
        search_resp.raise_for_status()
        hits = search_resp.json().get("query", {}).get("search", [])
        if not hits:
            return {}

        title = hits[0]["title"]
        page_resp = requests.get(
            base,
            params={"action": "query", "prop": "extracts|info", "exsentences": sentences,
                    "explaintext": True, "inprop": "url", "titles": title,
                    "format": "json", "redirects": 1},
            timeout=10,
        )
        page_resp.raise_for_status()
        page = next(iter(page_resp.json().get("query", {}).get("pages", {}).values()))
        return {
            "title": page.get("title", title),
            "url": page.get("fullurl", f"https://en.wikipedia.org/wiki/{title.replace(' ', '_')}"),
            "summary": page.get("extract", "")[:5000],
        }
    except Exception as exc:
        logger.warning("Wikipedia search failed: %s", exc)
        return {}


def extract_urls_from_ddg(results: List[Dict]) -> List[str]:
    """Extract URLs from ddg_search() results."""
    return [r["url"] for r in results if r.get("url")]


def extract_urls_from_text(text: str, max_urls: int = 5) -> List[str]:
    """Extract URLs from raw text via regex."""
    pattern = r"https?://(?:[-\w.]|(?:%[\da-fA-F]{2}))+[/\w.\-?=&%+#]*"
    return list(dict.fromkeys(re.findall(pattern, text)))[:max_urls]


def _ddg_tool_func(query: str) -> str:
    results = ddg_search(query, max_results=8)
    if not results:
        return "No results found."
    lines = [
        f"[{i + 1}] {r['title']}\n    URL: {r['url']}\n    {r['snippet']}"
        for i, r in enumerate(results)
    ]
    return "\n\n".join(lines)


def _wikipedia_tool_func(query: str) -> str:
    res = wikipedia_search(query)
    if not res:
        return "No Wikipedia article found."
    return f"Title: {res['title']}\nURL: {res['url']}\n\n{res['summary']}"


search_tool = Tool(
    name="web_search",
    func=_ddg_tool_func,
    description="Search the web with DuckDuckGo. Returns title, URL and snippet for each result.",
)

arxiv_tool = Tool(
    name="arxiv_search",
    func=lambda q: arxiv.run(q),
    description="Search academic papers on ArXiv.",
)

wikipedia_tool = Tool(
    name="wikipedia_search",
    func=_wikipedia_tool_func,
    description="Search Wikipedia for background knowledge. Returns article summary and URL.",
)

read_webpage_tool = Tool(
    name="read_webpage",
    func=read_webpage,
    description="Fetch and read the full text content of a URL.",
)
