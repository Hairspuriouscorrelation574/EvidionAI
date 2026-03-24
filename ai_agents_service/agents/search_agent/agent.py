from typing import Dict, Tuple, List, Any
import json
import logging
from datetime import datetime
from utils.schema import AgentState
from .prompt import SEARCH_AGENT_PROMPTS
from utils.llm_utils import (
    search_tool, arxiv_tool, read_webpage_tool,
    ddg_search, wikipedia_search, extract_urls_from_ddg, extract_urls_from_text
)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class SearchAgent:
    """
    Production search agent.

    Sources (all free, no API keys):
      1. DuckDuckGo structured (explicit URLs + snippets)
      2. Full page reads of top DDG results
      3. Wikipedia REST API (background / concepts)
      4. ArXiv (academic papers)

    Strategy is decided by LLM (search_decision prompt), with keyword fallback.
    Every URL tracked explicitly → supervisor gets numbered citation list.
    Full history (prompt + response per LLM call) preserved for frontend trace.
    """

    MAX_PAGES = 5

    def __init__(self, llm: Any):
        self.llm = llm
        self.tools = {
            "web":   search_tool,
            "arxiv": arxiv_tool,
            "read":  read_webpage_tool,
        }
        self.search_depth = self.MAX_PAGES

    def decide_search_strategy(self, query: str, instructions: str) -> List:
        """
        LLM decides which sources to use and what queries to run.
        Returns [strategy_dict, prompt, response] — same contract as original.
        """
        prompt = SEARCH_AGENT_PROMPTS["search_decision"].format(
            query=query, instructions=instructions)

        response = ""
        try:
            response = self.llm.invoke(prompt)
            if "{" in response and "}" in response:
                j = response[response.find("{"):response.rfind("}") + 1]
                strategy = json.loads(j)
                strategy.setdefault("use_web_search", True)
                strategy.setdefault("use_arxiv", False)
                strategy.setdefault("use_wikipedia", False)
                strategy.setdefault("web_query", query)
                strategy.setdefault("arxiv_query", query)
                strategy.setdefault("wiki_query", query)
                return [strategy, prompt, response]
        except Exception as e:
            logger.warning(f"Strategy parse failed: {e}")

        q = query.lower()
        strategy = {
            "use_web_search": True,
            "use_arxiv": any(t in q for t in ["paper","research","study","scientific","arxiv",
                                              "algorithm","neural","model","theorem"]),
            "use_wikipedia": any(t in q for t in ["what is","who is","history of","definition",
                                                  "explain","concept","overview","biography"]),
            "web_query": query,
            "arxiv_query": query,
            "wiki_query": query,
            "reasoning": "Fallback (keyword detection)",
        }
        return [strategy, prompt, response]

    def analyze_content(self, content: str, source_type: str,
                        query: str, instructions: str) -> List[str]:
        """Returns [analysis_text, prompt] — same contract as original."""
        prompt = SEARCH_AGENT_PROMPTS["analysis"].format(
            query=query,
            instructions=instructions,
            source_type=source_type,
            content_length=len(content),
            content=content[:30000]
        )
        try:
            return [self.llm.invoke(prompt), prompt]
        except Exception as e:
            return [f"Analysis error: {e}", prompt]

    def run(self, state: AgentState) -> Dict[str, Any]:
        logger.info(f"🔍 Search Agent: {state['user_input'][:60]}…")

        query = state["user_input"]
        instructions = state["supervisor_instructions"][-1]

        strategy, strategy_prompt, strategy_response = self.decide_search_strategy(query, instructions)

        all_results: List[Dict] = []
        urls_used: List[str] = []

        history = [
            {"role": "Supervisor to Search Agent", "content": strategy_prompt},
            {"role": "Search Agent", "content": strategy_response},
        ]

        logger.info(f"web={strategy['use_web_search']} wiki={strategy.get('use_wikipedia')} "
                    f"arxiv={strategy.get('use_arxiv')}")

        if strategy.get("use_web_search", True):
            web_query = strategy.get("web_query", query)
            logger.info(f"🌐 Performing web search...")
            try:
                ddg_results = ddg_search(web_query, max_results=8)

                if ddg_results:
                    snippets_text = "\n\n".join(
                        f"[{i+1}] {r['title']}\nURL: {r['url']}\n{r['snippet']}"
                        for i, r in enumerate(ddg_results)
                    )
                    web_analysis, prompt = self.analyze_content(
                        snippets_text, "Web Search Results (DuckDuckGo)", query, instructions)

                    history.append({"role": "Search Agent to Search Agent", "content": prompt})
                    history.append({"role": "Search Agent", "content": web_analysis})

                    ddg_urls = [r["url"] for r in ddg_results if r.get("url")]
                    all_results.append({
                        "source": "web_search",
                        "url": None,
                        "urls": ddg_urls,
                        "content": snippets_text[:1000],
                        "analysis": web_analysis,
                        "timestamp": datetime.now().isoformat(),
                    })
                    urls_used += ddg_urls

                    for url in extract_urls_from_ddg(ddg_results)[:self.MAX_PAGES]:
                        try:
                            logger.info(f"📄 {url[:100]}")
                            page_content = self.tools["read"].run(url)
                            if not page_content or page_content.startswith("[Error"):
                                continue
                            page_analysis, prompt = self.analyze_content(
                                page_content, f"Webpage: {url}", query, instructions)

                            history.append({"role": "Search Agent to Search Agent", "content": prompt})
                            history.append({"role": "Search Agent", "content": page_analysis})

                            all_results.append({
                                "source": f"webpage: {url}",
                                "url": url,
                                "urls": [url],
                                "content": page_content[:10000],
                                "analysis": page_analysis,
                                "timestamp": datetime.now().isoformat(),
                            })
                        except Exception as e:
                            logger.warning(f"page read failed {url[:100]}: {e}")

                else:
                    logger.info("DDG empty, raw fallback")
                    raw = self.tools["web"].run(web_query)
                    fallback_analysis, prompt = self.analyze_content(
                        raw, "Web Search (text fallback)", query, instructions
                        )

                    history.append({"role": "Search Agent to Search Agent", "content": prompt})
                    history.append({"role": "Search Agent", "content": fallback_analysis})

                    raw_urls = extract_urls_from_text(raw)
                    all_results.append({
                        "source": "web_search",
                        "url": None,
                        "urls": raw_urls,
                        "content": raw[:1000],
                        "analysis": fallback_analysis,
                        "timestamp": datetime.now().isoformat(),
                    })
                    urls_used += raw_urls

            except Exception as e:
                logger.error(f"Web search error: {e}")

        if strategy.get("use_wikipedia", False):
            wiki_query = strategy.get("wiki_query", query)
            logger.info(f"📖 Wikipedia: {wiki_query[:100]}")
            try:
                wiki = wikipedia_search(wiki_query)
                if wiki and wiki.get("summary"):
                    wiki_analysis, prompt = self.analyze_content(
                        wiki["summary"], f"Wikipedia: {wiki['title']}", query, instructions)

                    history.append({"role": "Search Agent to Search Agent", "content": prompt})
                    history.append({"role": "Search Agent", "content": wiki_analysis})

                    all_results.append({
                        "source": f"wikipedia: {wiki['title']}",
                        "url": wiki["url"],
                        "urls": [wiki["url"]],
                        "content": wiki["summary"],
                        "analysis": wiki_analysis,
                        "timestamp": datetime.now().isoformat(),
                    })
                    urls_used.append(wiki["url"])
            except Exception as e:
                logger.error(f"Wikipedia error: {e}")

        if strategy.get("use_arxiv", False):
            arxiv_query = strategy.get("arxiv_query", query)
            logger.info(f"📚 ArXiv: {arxiv_query[:100]}")
            try:
                arxiv_results = self.tools["arxiv"].run(arxiv_query)
                arxiv_urls = extract_urls_from_text(arxiv_results, max_urls=10)
                arxiv_analysis, prompt = self.analyze_content(
                    arxiv_results, "ArXiv Papers", query, instructions
                    )

                history.append({"role": "Search Agent to Search Agent", "content": prompt})
                history.append({"role": "Search Agent", "content": arxiv_analysis})

                all_results.append({
                    "source": "arxiv",
                    "url": "https://arxiv.org",
                    "urls": arxiv_urls,
                    "content": arxiv_results[:1000],
                    "analysis": arxiv_analysis,
                    "timestamp": datetime.now().isoformat(),
                })
                urls_used += arxiv_urls
            except Exception as e:
                logger.error(f"ArXiv error: {e}")

        seen = set()
        unique_urls = [u for u in urls_used if u and not (u in seen or seen.add(u))]

        sources_summary = "\n".join(
            f"- {r['source']}: {r['analysis'][:10000]}..."
            for r in all_results
        )
        citation_block = "\n".join(
            f"[{i+1}] {url}" for i, url in enumerate(unique_urls)
        )

        summary_prompt = SEARCH_AGENT_PROMPTS["summarize_search"].format(
            count=len(all_results),
            query=query,
            instructions=instructions,
            sources_summary=sources_summary
        )
        search_summary = self.llm.invoke(summary_prompt)

        history.append({"role": "Search Agent to Search Agent", "content": summary_prompt})
        history.append({"role": "Search Agent", "content": search_summary})

        if unique_urls:
            search_summary_with_citations = (
                search_summary
                + f"\n\n**Sources used ({len(unique_urls)}):**\n{citation_block}"
            )
        else:
            search_summary_with_citations = search_summary

        logger.info(f"✅ Search done: {len(all_results)} sources, {len(unique_urls)} URLs")

        return {
            "search_results": state.get("search_results", []) + all_results,
            "current_agent": "supervisor",
            "messages": state["messages"] + [{
                "role": "assistant (search agent)",
                "content": f"Search Agent completed: Found {len(all_results)} sources. Analysis and references are provided in the analysis",
            }],
            "analyses": state.get("analyses", []) + [{
                "type": "search_summary",
                "content": search_summary_with_citations,
                "urls_used": unique_urls,
                "timestamp": datetime.now().isoformat(),
            }],
            "history": state["history"] + history,
            "last_update": datetime.now().isoformat(),
        }
