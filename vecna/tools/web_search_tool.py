"""DuckDuckGo HTML web search tool executor."""

import asyncio
from typing import Any, Dict, List

import aiohttp

try:
    from bs4 import BeautifulSoup
except ImportError:  # pragma: no cover - dependency may be optional in minimal installs
    BeautifulSoup = None

from vecna.tools.types import ToolExecutionContext, ToolResult

DUCKDUCKGO_HTML_URL = "https://html.duckduckgo.com/html/"
DEFAULT_TIMEOUT_SECONDS = 10
MAX_RESULTS = 5
MAX_RESULTS_CAP = 10
PARSER_DEPENDENCY_ERROR = (
    "web_search parser dependency missing: install beautifulsoup4 (bs4) to parse search results"
)


def _extract_results(html: str, max_results: int = MAX_RESULTS) -> List[Dict[str, str]]:
    soup = BeautifulSoup(html, "html.parser")
    parsed_results = []

    for node in soup.select("div.result"):
        title_node = node.select_one("a.result__a")
        if title_node is None:
            continue

        title = title_node.get_text(strip=True)
        url = title_node.get("href", "").strip()

        snippet_node = node.select_one(".result__snippet")
        snippet = snippet_node.get_text(strip=True) if snippet_node is not None else ""

        if not title and not url and not snippet:
            continue

        parsed_results.append({"title": title, "url": url, "snippet": snippet})
        if len(parsed_results) >= max_results:
            break

    return parsed_results


def _format_results(results: List[Dict[str, str]]) -> str:
    lines = []
    for idx, item in enumerate(results, start=1):
        lines.append(f"{idx}. {item['title']}")
        lines.append(f"URL: {item['url']}")
        if item["snippet"]:
            lines.append(f"Snippet: {item['snippet']}")
        lines.append("")
    return "\n".join(lines).strip()


async def web_search_executor(args: Dict[str, Any], context: ToolExecutionContext) -> ToolResult:
    del context

    query = str(args.get("query", "")).strip()
    if not query:
        return ToolResult(
            tool_name="web_search",
            success=False,
            output="",
            error="query is required",
        )

    raw_max_results = args.get("max_results", MAX_RESULTS)
    if isinstance(raw_max_results, bool):
        return ToolResult(
            tool_name="web_search",
            success=False,
            output="",
            error=f"max_results must be between 1 and {MAX_RESULTS_CAP}",
        )
    try:
        max_results = int(raw_max_results)
    except (TypeError, ValueError):
        return ToolResult(
            tool_name="web_search",
            success=False,
            output="",
            error=f"max_results must be between 1 and {MAX_RESULTS_CAP}",
        )

    if max_results < 1:
        return ToolResult(
            tool_name="web_search",
            success=False,
            output="",
            error=f"max_results must be between 1 and {MAX_RESULTS_CAP}",
        )
    max_results = min(max_results, MAX_RESULTS_CAP)

    timeout = aiohttp.ClientTimeout(total=DEFAULT_TIMEOUT_SECONDS)
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(
                DUCKDUCKGO_HTML_URL,
                params={"q": query},
                headers={"User-Agent": "vecna-web-search/1.0"},
            ) as response:
                if response.status >= 400:
                    return ToolResult(
                        tool_name="web_search",
                        success=False,
                        output="",
                        error=f"search request failed with HTTP status {response.status}",
                    )
                html = await response.text(errors="ignore")
    except asyncio.TimeoutError:
        return ToolResult(
            tool_name="web_search",
            success=False,
            output="",
            error="search request timed out",
        )
    except aiohttp.ClientError as exc:
        return ToolResult(
            tool_name="web_search",
            success=False,
            output="",
            error=f"search request failed: {exc}",
        )
    except (OSError, RuntimeError, ValueError) as exc:
        return ToolResult(
            tool_name="web_search",
            success=False,
            output="",
            error=f"unexpected search error: {exc}",
        )

    if BeautifulSoup is None:
        return ToolResult(
            tool_name="web_search",
            success=False,
            output="",
            error=PARSER_DEPENDENCY_ERROR,
        )

    results = _extract_results(html, max_results=max_results)
    if not results:
        return ToolResult(
            tool_name="web_search",
            success=True,
            output=f"No results found for query: {query}",
            metadata={"query": query, "result_count": 0, "max_results": max_results},
        )

    return ToolResult(
        tool_name="web_search",
        success=True,
        output=_format_results(results),
        metadata={"query": query, "result_count": len(results), "max_results": max_results},
    )
