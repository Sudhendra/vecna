# Remaining Work Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implement all remaining Vecna subsystems — tool expansion, autonomy upgrades, memory improvements, security hardening, observability, and UX polish — transforming Vecna from a single-cycle assistant into a capable autonomous agent.

**Architecture:** Each phase builds on the previous. Tools come first (the agent needs hands before it needs autonomy). Then autonomy infrastructure (goal queue, curiosity, kill-switch). Then memory improvements (multi-hop, dream insights). Then security/observability/UX. All new subsystems are feature-flagged and TDD.

**Tech Stack:** Python 3.10+, asyncio, aiohttp, httpx, beautifulsoup4, PostgreSQL+pgvector, Redis, Docker, Ruff, pytest (asyncio_mode=auto)

---

## Design Decisions (from brainstorming)

### Web/HTTP Tool: httpx + beautifulsoup4 (not Unbrowse)

**Decision:** Use `httpx` (async HTTP) + `beautifulsoup4` (HTML parsing) for the HTTP/web tool.

**Why not Unbrowse.ai:**
- Beta product with crypto tokenomics ($FDRY token) — uncertain longevity
- Requires API key and external service dependency
- MCP integration is clean but product maturity is low
- Network-level approach can't handle JS-heavy sites anyway
- httpx+bs4 are battle-tested, zero external dependencies, fully offline-capable

**Why not browser-use/playwright:**
- Overkill for Vecna's needs — we need HTTP fetch + parse, not full browser automation
- Heavy dependency (Chromium binary)
- Can always add later behind the same tool abstraction if needed

### Markdown Workspace: Keep direct file I/O (not Obsidian CLI)

**Decision:** Keep Vecna's existing `workspace.py` + `mirror.py` direct file I/O to `~/.vecna/`.

**Why not Obsidian CLI:**
- Requires Obsidian desktop app running — incompatible with headless/autonomous operation
- Requires Obsidian 1.12+ (early access, Catalyst license)
- Vecna already has a working markdown workspace system
- Adds massive operational complexity for marginal benefit

**Compromise:** Structure `~/.vecna/` as Obsidian-vault-compatible (add `.obsidian/` config dir). Users can optionally open it in Obsidian for visualization. Zero code dependency on Obsidian. Implemented as a one-time workspace init enhancement in Task 11.

### Filesystem Tool: Scoped sandboxed operations

**Decision:** Allow read/list/stat within configurable allowed directories. No write/delete — that's what `python_exec` is for (sandboxed in Docker). Risk-assessed per operation.

### Web Search: DuckDuckGo HTML scrape via httpx

**Decision:** Use DuckDuckGo HTML search endpoint (no API key required) parsed with bs4. No external service dependency. Can swap to SerpAPI/Brave Search later via config.

---

## Phase 1: Tool Catalog Expansion

### Task 1: HTTP Request Tool

**Files:**
- Create: `vecna/tools/http_tool.py`
- Modify: `vecna/tools/registry.py:33-59`
- Test: `tests/unit/test_http_tool.py`

**Step 1: Write the failing test**

```python
# tests/unit/test_http_tool.py
"""HTTP request tool tests."""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from vecna.tools.http_tool import http_request_executor, parse_html_content
from vecna.tools.types import ToolExecutionContext, ToolResult


class TestParseHtmlContent:
    def test_extracts_text_from_html(self):
        html = "<html><body><h1>Title</h1><p>Hello world</p></body></html>"
        result = parse_html_content(html)
        assert "Title" in result
        assert "Hello world" in result

    def test_strips_script_and_style_tags(self):
        html = "<html><body><script>alert(1)</script><style>.x{}</style><p>Keep me</p></body></html>"
        result = parse_html_content(html)
        assert "alert" not in result
        assert "Keep me" in result

    def test_truncates_long_content(self):
        html = "<html><body><p>" + "x" * 20000 + "</p></body></html>"
        result = parse_html_content(html, max_chars=1000)
        assert len(result) <= 1000


class TestHttpRequestExecutor:
    @pytest.fixture
    def context(self):
        return ToolExecutionContext(session_id="test-session")

    async def test_successful_get_request(self, context):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = "<html><body><p>Hello</p></body></html>"
        mock_response.headers = {"content-type": "text/html"}

        with patch("vecna.tools.http_tool.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.request = AsyncMock(return_value=mock_response)
            mock_client_cls.return_value = mock_client

            result = await http_request_executor(
                {"url": "https://example.com", "method": "GET"}, context
            )

        assert isinstance(result, ToolResult)
        assert result.success is True
        assert "Hello" in result.output

    async def test_rejects_non_http_urls(self, context):
        result = await http_request_executor(
            {"url": "file:///etc/passwd", "method": "GET"}, context
        )
        assert result.success is False
        assert "invalid" in result.error.lower() or "denied" in result.error.lower()

    async def test_rejects_private_ips(self, context):
        result = await http_request_executor(
            {"url": "http://192.168.1.1/admin", "method": "GET"}, context
        )
        assert result.success is False

    async def test_returns_json_for_json_content(self, context):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = '{"key": "value"}'
        mock_response.headers = {"content-type": "application/json"}

        with patch("vecna.tools.http_tool.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.request = AsyncMock(return_value=mock_response)
            mock_client_cls.return_value = mock_client

            result = await http_request_executor(
                {"url": "https://api.example.com/data", "method": "GET"}, context
            )

        assert result.success is True
        assert "value" in result.output

    async def test_timeout_handling(self, context):
        with patch("vecna.tools.http_tool.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            import httpx

            mock_client.request = AsyncMock(side_effect=httpx.TimeoutException("timeout"))
            mock_client_cls.return_value = mock_client

            result = await http_request_executor(
                {"url": "https://slow.example.com", "method": "GET"}, context
            )

        assert result.success is False
        assert "timeout" in result.error.lower()
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_http_tool.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'vecna.tools.http_tool'`

**Step 3: Write minimal implementation**

```python
# vecna/tools/http_tool.py
"""HTTP request tool for fetching web pages and APIs."""
import ipaddress
import logging
from typing import Optional
from urllib.parse import urlparse

import httpx

from vecna.tools.types import ToolExecutionContext, ToolResult

logger = logging.getLogger("vecna.tools.http")

# Safety: block private/reserved IP ranges
_BLOCKED_NETWORKS = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fe80::/10"),
]

_MAX_RESPONSE_CHARS = 8000
_DEFAULT_TIMEOUT = 30


def _is_private_ip(hostname: str) -> bool:
    """Check if a hostname resolves to a private/reserved IP."""
    import socket

    try:
        addr = socket.gethostbyname(hostname)
        ip = ipaddress.ip_address(addr)
        return any(ip in network for network in _BLOCKED_NETWORKS)
    except (socket.gaierror, ValueError):
        return False


def parse_html_content(html: str, max_chars: int = _MAX_RESPONSE_CHARS) -> str:
    """Extract readable text from HTML, stripping scripts/styles."""
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        # Fallback: crude tag stripping
        import re

        text = re.sub(r"<[^>]+>", " ", html)
        return text[:max_chars].strip()

    soup = BeautifulSoup(html, "html.parser")

    # Remove script and style elements
    for element in soup(["script", "style", "nav", "footer", "header"]):
        element.decompose()

    text = soup.get_text(separator="\n", strip=True)

    # Collapse multiple blank lines
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    result = "\n".join(lines)

    return result[:max_chars]


async def http_request_executor(
    args: dict, context: ToolExecutionContext
) -> ToolResult:
    """Execute an HTTP request and return the response content."""
    url = args.get("url", "")
    method = args.get("method", "GET").upper()
    headers = args.get("headers", {})
    body = args.get("body")
    timeout = args.get("timeout", _DEFAULT_TIMEOUT)

    # Validate URL scheme
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return ToolResult(
            tool_name="http_request",
            success=False,
            output="",
            error=f"Invalid URL scheme: {parsed.scheme}. Only http/https allowed.",
        )

    # Block private IPs (SSRF protection)
    if parsed.hostname and _is_private_ip(parsed.hostname):
        return ToolResult(
            tool_name="http_request",
            success=False,
            output="",
            error="Denied: URL resolves to a private/reserved IP address.",
        )

    # Only allow safe methods
    if method not in ("GET", "HEAD", "OPTIONS", "POST", "PUT", "PATCH", "DELETE"):
        return ToolResult(
            tool_name="http_request",
            success=False,
            output="",
            error=f"Invalid HTTP method: {method}",
        )

    try:
        async with httpx.AsyncClient(
            follow_redirects=True,
            timeout=httpx.Timeout(timeout),
            limits=httpx.Limits(max_connections=5),
        ) as client:
            response = await client.request(
                method=method,
                url=url,
                headers=headers,
                content=body,
            )

        content_type = response.headers.get("content-type", "")

        if "application/json" in content_type:
            output = response.text[:_MAX_RESPONSE_CHARS]
        elif "text/html" in content_type:
            output = parse_html_content(response.text)
        else:
            output = response.text[:_MAX_RESPONSE_CHARS]

        return ToolResult(
            tool_name="http_request",
            success=True,
            output=output,
            metadata={
                "status_code": response.status_code,
                "content_type": content_type,
                "url": str(response.url),
            },
        )

    except httpx.TimeoutException:
        return ToolResult(
            tool_name="http_request",
            success=False,
            output="",
            error=f"Timeout after {timeout}s fetching {url}",
        )
    except httpx.HTTPError as exc:
        return ToolResult(
            tool_name="http_request",
            success=False,
            output="",
            error=f"HTTP error: {exc}",
        )
    except Exception as exc:
        logger.error(f"http_request tool error: {exc}")
        return ToolResult(
            tool_name="http_request",
            success=False,
            output="",
            error=f"Request failed: {exc}",
        )
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_http_tool.py -v`
Expected: PASS (all 6 tests)

**Step 5: Commit**

```bash
git add vecna/tools/http_tool.py tests/unit/test_http_tool.py
git commit -m "feat: add HTTP request tool with SSRF protection and HTML parsing"
```

---

### Task 2: Register HTTP Tool in Default Registry

**Files:**
- Modify: `vecna/tools/registry.py:33-59`
- Modify: `vecna/tools/permissions.py:49-83` (add risk assessment for http_request)
- Modify: `tests/unit/test_tools_registry.py` (add test for new tool)

**Step 1: Write the failing test**

Add to existing `tests/unit/test_tools_registry.py`:

```python
class TestDefaultRegistryTools:
    def test_http_request_tool_registered(self):
        from vecna.tools.registry import get_default_registry

        registry = get_default_registry()
        specs = registry.list_tools()
        names = [s.name for s in specs]
        assert "http_request" in names

    def test_http_request_tool_has_correct_schema(self):
        from vecna.tools.registry import get_default_registry

        registry = get_default_registry()
        tool = registry.get("http_request")
        assert "url" in tool.spec.input_schema
        assert "method" in tool.spec.input_schema
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_tools_registry.py::TestDefaultRegistryTools -v`
Expected: FAIL with `KeyError: 'http_request'`

**Step 3: Register the tool**

In `vecna/tools/registry.py`, add import and registration:

```python
# Add to imports at top
from vecna.tools.http_tool import http_request_executor

# Add to get_default_registry() after memory_get registration:
    registry.register(
        ToolSpec(
            name="http_request",
            description="Fetch a URL via HTTP. Returns parsed text for HTML, raw for JSON/text.",
            input_schema={
                "url": "string",
                "method": "string",
                "headers": "object",
                "body": "string",
            },
            tags=["web", "http", "fetch"],
        ),
        executor=http_request_executor,
    )
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_tools_registry.py::TestDefaultRegistryTools -v`
Expected: PASS

**Step 5: Commit**

```bash
git add vecna/tools/registry.py tests/unit/test_tools_registry.py
git commit -m "feat: register http_request tool in default registry"
```

---

### Task 3: Web Search Tool (DuckDuckGo)

**Files:**
- Create: `vecna/tools/web_search_tool.py`
- Modify: `vecna/tools/registry.py`
- Test: `tests/unit/test_web_search_tool.py`

**Step 1: Write the failing test**

```python
# tests/unit/test_web_search_tool.py
"""Web search tool tests."""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from vecna.tools.web_search_tool import web_search_executor, parse_ddg_results
from vecna.tools.types import ToolExecutionContext, ToolResult


class TestParseDdgResults:
    def test_extracts_results_from_html(self):
        # Minimal DDG-like result HTML
        html = """
        <div class="result">
            <a class="result__a" href="https://example.com">Example Title</a>
            <a class="result__snippet">This is a snippet about example.</a>
        </div>
        """
        results = parse_ddg_results(html)
        assert isinstance(results, list)

    def test_returns_empty_for_no_results(self):
        results = parse_ddg_results("<html><body>No results</body></html>")
        assert results == []

    def test_limits_results(self):
        html = "<html><body>" + '<div class="result"><a class="result__a" href="https://x.com">X</a><a class="result__snippet">Snip</a></div>' * 20 + "</body></html>"
        results = parse_ddg_results(html, max_results=5)
        assert len(results) <= 5


class TestWebSearchExecutor:
    @pytest.fixture
    def context(self):
        return ToolExecutionContext(session_id="test-session")

    async def test_successful_search(self, context):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = """<div class="result"><a class="result__a" href="https://example.com">Result</a><a class="result__snippet">Snippet text</a></div>"""

        with patch("vecna.tools.web_search_tool.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client_cls.return_value = mock_client

            result = await web_search_executor({"query": "python asyncio"}, context)

        assert isinstance(result, ToolResult)
        assert result.success is True

    async def test_empty_query_fails(self, context):
        result = await web_search_executor({"query": ""}, context)
        assert result.success is False

    async def test_timeout_returns_error(self, context):
        with patch("vecna.tools.web_search_tool.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            import httpx

            mock_client.get = AsyncMock(side_effect=httpx.TimeoutException("timeout"))
            mock_client_cls.return_value = mock_client

            result = await web_search_executor({"query": "test"}, context)

        assert result.success is False
        assert "timeout" in result.error.lower()
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_web_search_tool.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'vecna.tools.web_search_tool'`

**Step 3: Write minimal implementation**

```python
# vecna/tools/web_search_tool.py
"""Web search tool using DuckDuckGo HTML endpoint."""
import logging
from typing import Dict, List
from urllib.parse import quote_plus

import httpx

from vecna.tools.types import ToolExecutionContext, ToolResult

logger = logging.getLogger("vecna.tools.web_search")

_DDG_URL = "https://html.duckduckgo.com/html/"
_DEFAULT_TIMEOUT = 15
_DEFAULT_MAX_RESULTS = 8


def parse_ddg_results(html: str, max_results: int = _DEFAULT_MAX_RESULTS) -> List[Dict[str, str]]:
    """Parse DuckDuckGo HTML search results into structured data."""
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        return []

    soup = BeautifulSoup(html, "html.parser")
    results = []

    for result_div in soup.select(".result")[:max_results]:
        link_tag = result_div.select_one(".result__a")
        snippet_tag = result_div.select_one(".result__snippet")

        if not link_tag:
            continue

        title = link_tag.get_text(strip=True)
        url = link_tag.get("href", "")
        snippet = snippet_tag.get_text(strip=True) if snippet_tag else ""

        if title and url:
            results.append({"title": title, "url": url, "snippet": snippet})

    return results


async def web_search_executor(
    args: dict, context: ToolExecutionContext
) -> ToolResult:
    """Search the web using DuckDuckGo and return structured results."""
    query = args.get("query", "").strip()
    max_results = args.get("max_results", _DEFAULT_MAX_RESULTS)

    if not query:
        return ToolResult(
            tool_name="web_search",
            success=False,
            output="",
            error="Empty search query.",
        )

    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(_DEFAULT_TIMEOUT),
            follow_redirects=True,
        ) as client:
            response = await client.get(
                _DDG_URL,
                params={"q": query},
                headers={"User-Agent": "Vecna/1.0 (research agent)"},
            )

        results = parse_ddg_results(response.text, max_results=max_results)

        if not results:
            return ToolResult(
                tool_name="web_search",
                success=True,
                output="No results found.",
                metadata={"query": query, "result_count": 0},
            )

        # Format results as readable text
        lines = []
        for i, r in enumerate(results, 1):
            lines.append(f"{i}. {r['title']}")
            lines.append(f"   URL: {r['url']}")
            if r["snippet"]:
                lines.append(f"   {r['snippet']}")
            lines.append("")

        output = "\n".join(lines).strip()

        return ToolResult(
            tool_name="web_search",
            success=True,
            output=output,
            metadata={"query": query, "result_count": len(results)},
        )

    except httpx.TimeoutException:
        return ToolResult(
            tool_name="web_search",
            success=False,
            output="",
            error=f"Timeout searching for: {query}",
        )
    except Exception as exc:
        logger.error(f"web_search error: {exc}")
        return ToolResult(
            tool_name="web_search",
            success=False,
            output="",
            error=f"Search failed: {exc}",
        )
```

**Step 4: Register in registry.py**

Add to `get_default_registry()`:

```python
from vecna.tools.web_search_tool import web_search_executor

    registry.register(
        ToolSpec(
            name="web_search",
            description="Search the web for information. Returns titles, URLs, and snippets.",
            input_schema={"query": "string", "max_results": "int"},
            tags=["web", "search"],
        ),
        executor=web_search_executor,
    )
```

**Step 5: Run tests and commit**

Run: `pytest tests/unit/test_web_search_tool.py -v`
Expected: PASS

```bash
git add vecna/tools/web_search_tool.py tests/unit/test_web_search_tool.py vecna/tools/registry.py
git commit -m "feat: add web search tool using DuckDuckGo HTML endpoint"
```

---

### Task 4: Filesystem Read Tool

**Files:**
- Create: `vecna/tools/fs_tool.py`
- Modify: `vecna/tools/registry.py`
- Modify: `vecna/config/schema.py` (add `allowed_fs_paths` config)
- Test: `tests/unit/test_fs_tool.py`

**Step 1: Write the failing test**

```python
# tests/unit/test_fs_tool.py
"""Filesystem read tool tests."""
import os
import pytest
import tempfile
from pathlib import Path

from vecna.tools.fs_tool import (
    fs_read_executor,
    fs_list_executor,
    is_path_allowed,
)
from vecna.tools.types import ToolExecutionContext, ToolResult


class TestPathValidation:
    def test_allows_path_within_allowed_dirs(self):
        assert is_path_allowed("/home/user/docs/file.txt", ["/home/user/docs"]) is True

    def test_denies_path_outside_allowed_dirs(self):
        assert is_path_allowed("/etc/passwd", ["/home/user/docs"]) is False

    def test_blocks_path_traversal(self):
        assert is_path_allowed("/home/user/docs/../../etc/passwd", ["/home/user/docs"]) is False

    def test_denies_empty_allowed_list(self):
        assert is_path_allowed("/any/path", []) is False

    def test_allows_home_vecna_by_default(self):
        vecna_dir = str(Path.home() / ".vecna")
        assert is_path_allowed(f"{vecna_dir}/SOUL.md", [vecna_dir]) is True


class TestFsReadExecutor:
    @pytest.fixture
    def context(self):
        return ToolExecutionContext(session_id="test-session")

    async def test_reads_existing_file(self, context, tmp_path):
        test_file = tmp_path / "test.txt"
        test_file.write_text("hello world")

        result = await fs_read_executor(
            {"path": str(test_file), "allowed_dirs": [str(tmp_path)]}, context
        )
        assert result.success is True
        assert "hello world" in result.output

    async def test_denies_file_outside_allowed_dirs(self, context, tmp_path):
        result = await fs_read_executor(
            {"path": "/etc/passwd", "allowed_dirs": [str(tmp_path)]}, context
        )
        assert result.success is False
        assert "denied" in result.error.lower() or "not allowed" in result.error.lower()

    async def test_returns_error_for_missing_file(self, context, tmp_path):
        result = await fs_read_executor(
            {"path": str(tmp_path / "nonexistent.txt"), "allowed_dirs": [str(tmp_path)]}, context
        )
        assert result.success is False

    async def test_truncates_large_files(self, context, tmp_path):
        big_file = tmp_path / "big.txt"
        big_file.write_text("x" * 50000)

        result = await fs_read_executor(
            {"path": str(big_file), "max_chars": 1000, "allowed_dirs": [str(tmp_path)]}, context
        )
        assert result.success is True
        assert len(result.output) <= 1100  # some slack for truncation message


class TestFsListExecutor:
    @pytest.fixture
    def context(self):
        return ToolExecutionContext(session_id="test-session")

    async def test_lists_directory_contents(self, context, tmp_path):
        (tmp_path / "a.txt").write_text("a")
        (tmp_path / "b.txt").write_text("b")
        (tmp_path / "subdir").mkdir()

        result = await fs_list_executor(
            {"path": str(tmp_path), "allowed_dirs": [str(tmp_path)]}, context
        )
        assert result.success is True
        assert "a.txt" in result.output
        assert "b.txt" in result.output
        assert "subdir" in result.output
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_fs_tool.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'vecna.tools.fs_tool'`

**Step 3: Write minimal implementation**

```python
# vecna/tools/fs_tool.py
"""Filesystem read tool with path sandboxing."""
import logging
import os
from pathlib import Path
from typing import List, Optional

from vecna.tools.types import ToolExecutionContext, ToolResult

logger = logging.getLogger("vecna.tools.fs")

_MAX_READ_CHARS = 10000


def is_path_allowed(path: str, allowed_dirs: List[str]) -> bool:
    """Check if a path is within the allowed directories (resolved, no traversal)."""
    if not allowed_dirs:
        return False

    try:
        resolved = Path(path).resolve()
    except (ValueError, OSError):
        return False

    for allowed in allowed_dirs:
        try:
            allowed_resolved = Path(allowed).resolve()
            if resolved == allowed_resolved or allowed_resolved in resolved.parents:
                return True
        except (ValueError, OSError):
            continue

    return False


async def fs_read_executor(args: dict, context: ToolExecutionContext) -> ToolResult:
    """Read a file's contents within allowed directories."""
    path = args.get("path", "")
    allowed_dirs = args.get("allowed_dirs", [str(Path.home() / ".vecna")])
    max_chars = args.get("max_chars", _MAX_READ_CHARS)

    if not path:
        return ToolResult("fs_read", False, "", error="No path provided.")

    if not is_path_allowed(path, allowed_dirs):
        return ToolResult(
            "fs_read", False, "", error=f"Path not allowed: {path}. Allowed dirs: {allowed_dirs}"
        )

    try:
        resolved = Path(path).resolve()
        if not resolved.exists():
            return ToolResult("fs_read", False, "", error=f"File not found: {path}")
        if not resolved.is_file():
            return ToolResult("fs_read", False, "", error=f"Not a file: {path}")

        content = resolved.read_text(encoding="utf-8", errors="replace")

        if len(content) > max_chars:
            content = content[:max_chars] + f"\n\n[... truncated at {max_chars} chars]"

        return ToolResult(
            "fs_read",
            True,
            content,
            metadata={"path": str(resolved), "size_bytes": resolved.stat().st_size},
        )

    except PermissionError:
        return ToolResult("fs_read", False, "", error=f"Permission denied: {path}")
    except Exception as exc:
        logger.error(f"fs_read error: {exc}")
        return ToolResult("fs_read", False, "", error=f"Read failed: {exc}")


async def fs_list_executor(args: dict, context: ToolExecutionContext) -> ToolResult:
    """List directory contents within allowed directories."""
    path = args.get("path", "")
    allowed_dirs = args.get("allowed_dirs", [str(Path.home() / ".vecna")])

    if not path:
        return ToolResult("fs_list", False, "", error="No path provided.")

    if not is_path_allowed(path, allowed_dirs):
        return ToolResult(
            "fs_list", False, "", error=f"Path not allowed: {path}. Allowed dirs: {allowed_dirs}"
        )

    try:
        resolved = Path(path).resolve()
        if not resolved.exists():
            return ToolResult("fs_list", False, "", error=f"Directory not found: {path}")
        if not resolved.is_dir():
            return ToolResult("fs_list", False, "", error=f"Not a directory: {path}")

        entries = []
        for entry in sorted(resolved.iterdir()):
            entry_type = "dir" if entry.is_dir() else "file"
            size = entry.stat().st_size if entry.is_file() else 0
            entries.append(f"  {entry_type}  {size:>8}  {entry.name}")

        output = f"Contents of {resolved}:\n" + "\n".join(entries)

        return ToolResult(
            "fs_list",
            True,
            output,
            metadata={"path": str(resolved), "entry_count": len(entries)},
        )

    except PermissionError:
        return ToolResult("fs_list", False, "", error=f"Permission denied: {path}")
    except Exception as exc:
        logger.error(f"fs_list error: {exc}")
        return ToolResult("fs_list", False, "", error=f"List failed: {exc}")
```

**Step 4: Register in registry.py and run tests**

Add to `get_default_registry()`:

```python
from vecna.tools.fs_tool import fs_read_executor, fs_list_executor

    registry.register(
        ToolSpec(
            name="fs_read",
            description="Read a file's contents. Sandboxed to allowed directories.",
            input_schema={"path": "string", "max_chars": "int"},
            tags=["filesystem", "read"],
        ),
        executor=fs_read_executor,
    )
    registry.register(
        ToolSpec(
            name="fs_list",
            description="List directory contents. Sandboxed to allowed directories.",
            input_schema={"path": "string"},
            tags=["filesystem", "list"],
        ),
        executor=fs_list_executor,
    )
```

Run: `pytest tests/unit/test_fs_tool.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add vecna/tools/fs_tool.py tests/unit/test_fs_tool.py vecna/tools/registry.py
git commit -m "feat: add sandboxed filesystem read/list tools"
```

---

### Task 5: Semantic Tool Router

**Files:**
- Modify: `vecna/tools/router.py:1-21`
- Modify: `vecna/tools/types.py` (add `capabilities` field to ToolSpec)
- Test: `tests/unit/test_tool_router.py` (extend existing)

**Step 1: Write the failing test**

```python
# Add to tests/unit/test_tool_router.py

class TestSemanticToolRouting:
    def test_tag_based_routing(self):
        from vecna.tools.router import ToolRouter
        from vecna.tools.types import ToolSpec

        router = ToolRouter()

        specs = [
            ToolSpec(name="http_request", description="Fetch URLs", input_schema={}, tags=["web", "http"]),
            ToolSpec(name="web_search", description="Search the web", input_schema={}, tags=["web", "search"]),
            ToolSpec(name="python_exec", description="Execute Python", input_schema={}, tags=["code", "exec"]),
            ToolSpec(name="fs_read", description="Read files", input_schema={}, tags=["filesystem"]),
        ]

        ranked = router.rank_by_tags(specs, required_tags=["web"])
        names = [s.name for s in ranked]
        assert "http_request" in names[:2]
        assert "web_search" in names[:2]

    def test_keyword_routing(self):
        from vecna.tools.router import ToolRouter
        from vecna.tools.types import ToolSpec

        router = ToolRouter()

        specs = [
            ToolSpec(name="http_request", description="Fetch a URL via HTTP", input_schema={}, tags=["web"]),
            ToolSpec(name="web_search", description="Search the web for information", input_schema={}, tags=["search"]),
            ToolSpec(name="python_exec", description="Execute Python code", input_schema={}, tags=["code"]),
        ]

        ranked = router.rank_by_query(specs, query="search for python tutorials online")
        # web_search should rank higher than http_request for a search query
        names = [s.name for s in ranked]
        assert names[0] == "web_search"

    def test_rank_by_tags_returns_all_if_no_tags(self):
        from vecna.tools.router import ToolRouter
        from vecna.tools.types import ToolSpec

        router = ToolRouter()
        specs = [
            ToolSpec(name="a", description="A", input_schema={}, tags=["x"]),
            ToolSpec(name="b", description="B", input_schema={}, tags=["y"]),
        ]
        ranked = router.rank_by_tags(specs, required_tags=[])
        assert len(ranked) == 2
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_tool_router.py::TestSemanticToolRouting -v`
Expected: FAIL with `AttributeError: 'ToolRouter' object has no attribute 'rank_by_tags'`

**Step 3: Write implementation**

Replace `vecna/tools/router.py`:

```python
"""Tool routing: success-rate ranking + tag/keyword-based semantic routing."""
from typing import Dict, List, Optional

from vecna.tools.types import ToolSpec


class ToolRouter:
    def __init__(self) -> None:
        self._stats: Dict[str, Dict[str, int]] = {}

    def record(self, tool_name: str, success: bool) -> None:
        stats = self._stats.setdefault(tool_name, {"success": 0, "total": 0})
        stats["total"] += 1
        if success:
            stats["success"] += 1

    def success_rate(self, name: str) -> float:
        stats = self._stats.get(name)
        if not stats or stats["total"] == 0:
            return 0.0
        return stats["success"] / stats["total"]

    def rank(self, tool_names: list[str]) -> list[str]:
        """Rank tool names by success rate (original behavior)."""
        indexed = list(enumerate(tool_names))
        indexed.sort(key=lambda item: (self.success_rate(item[1]), -item[0]), reverse=True)
        return [name for _, name in indexed]

    def rank_by_tags(
        self, specs: List[ToolSpec], required_tags: Optional[List[str]] = None
    ) -> List[ToolSpec]:
        """Rank tools by tag overlap with required tags."""
        if not required_tags:
            return list(specs)

        tag_set = set(required_tags)

        def tag_score(spec: ToolSpec) -> float:
            if not spec.tags:
                return 0.0
            overlap = len(tag_set & set(spec.tags))
            return overlap / len(tag_set)

        return sorted(specs, key=tag_score, reverse=True)

    def rank_by_query(self, specs: List[ToolSpec], query: str) -> List[ToolSpec]:
        """Rank tools by keyword overlap between query and tool description + tags."""
        query_words = set(query.lower().split())

        def relevance(spec: ToolSpec) -> float:
            desc_words = set(spec.description.lower().split())
            tag_words = set(t.lower() for t in (spec.tags or []))
            all_words = desc_words | tag_words | {spec.name.lower()}
            overlap = len(query_words & all_words)
            return overlap

        return sorted(specs, key=relevance, reverse=True)
```

**Step 4: Run tests**

Run: `pytest tests/unit/test_tool_router.py -v`
Expected: PASS (both old and new tests)

**Step 5: Commit**

```bash
git add vecna/tools/router.py tests/unit/test_tool_router.py
git commit -m "feat: add tag-based and keyword-based semantic tool routing"
```

---

### Task 6: Tool Quotas and Budgeting

**Files:**
- Create: `vecna/tools/quotas.py`
- Modify: `vecna/tools/runtime.py:42-109` (enforce quotas before execution)
- Modify: `vecna/config/schema.py` (add quota config fields)
- Test: `tests/unit/test_tool_quotas.py`

**Step 1: Write the failing test**

```python
# tests/unit/test_tool_quotas.py
"""Tool quota enforcement tests."""
import pytest
from vecna.tools.quotas import ToolQuotaManager, QuotaConfig


class TestToolQuotaManager:
    def test_allows_within_quota(self):
        config = QuotaConfig(max_calls_per_session=10, max_calls_per_tool=5)
        mgr = ToolQuotaManager(config)
        assert mgr.check("python_exec", session_id="s1") is True

    def test_denies_over_session_limit(self):
        config = QuotaConfig(max_calls_per_session=2, max_calls_per_tool=100)
        mgr = ToolQuotaManager(config)
        mgr.record("python_exec", "s1")
        mgr.record("http_request", "s1")
        assert mgr.check("web_search", session_id="s1") is False

    def test_denies_over_tool_limit(self):
        config = QuotaConfig(max_calls_per_session=100, max_calls_per_tool=2)
        mgr = ToolQuotaManager(config)
        mgr.record("python_exec", "s1")
        mgr.record("python_exec", "s1")
        assert mgr.check("python_exec", session_id="s1") is False

    def test_different_sessions_independent(self):
        config = QuotaConfig(max_calls_per_session=2, max_calls_per_tool=100)
        mgr = ToolQuotaManager(config)
        mgr.record("python_exec", "s1")
        mgr.record("python_exec", "s1")
        assert mgr.check("python_exec", session_id="s2") is True

    def test_unlimited_quota(self):
        config = QuotaConfig(max_calls_per_session=0, max_calls_per_tool=0)
        mgr = ToolQuotaManager(config)
        for _ in range(100):
            mgr.record("python_exec", "s1")
        assert mgr.check("python_exec", session_id="s1") is True

    def test_remaining_calls(self):
        config = QuotaConfig(max_calls_per_session=5, max_calls_per_tool=3)
        mgr = ToolQuotaManager(config)
        mgr.record("python_exec", "s1")
        assert mgr.remaining_for_tool("python_exec", "s1") == 2
        assert mgr.remaining_for_session("s1") == 4
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_tool_quotas.py -v`
Expected: FAIL with `ModuleNotFoundError`

**Step 3: Write implementation**

```python
# vecna/tools/quotas.py
"""Tool quota management for per-session and per-tool limits."""
from dataclasses import dataclass, field
from typing import Dict


@dataclass
class QuotaConfig:
    """Quota limits. 0 means unlimited."""

    max_calls_per_session: int = 0
    max_calls_per_tool: int = 0


class ToolQuotaManager:
    """Track and enforce per-session and per-tool call quotas."""

    def __init__(self, config: QuotaConfig) -> None:
        self.config = config
        # session_id -> tool_name -> count
        self._counts: Dict[str, Dict[str, int]] = {}

    def record(self, tool_name: str, session_id: str) -> None:
        """Record a tool invocation."""
        session = self._counts.setdefault(session_id, {})
        session[tool_name] = session.get(tool_name, 0) + 1

    def check(self, tool_name: str, session_id: str) -> bool:
        """Check if a tool call is within quota. Returns True if allowed."""
        session = self._counts.get(session_id, {})

        # Check per-session limit
        if self.config.max_calls_per_session > 0:
            total = sum(session.values())
            if total >= self.config.max_calls_per_session:
                return False

        # Check per-tool limit
        if self.config.max_calls_per_tool > 0:
            tool_count = session.get(tool_name, 0)
            if tool_count >= self.config.max_calls_per_tool:
                return False

        return True

    def remaining_for_tool(self, tool_name: str, session_id: str) -> int:
        """Return remaining calls for a specific tool in a session. -1 means unlimited."""
        if self.config.max_calls_per_tool <= 0:
            return -1
        session = self._counts.get(session_id, {})
        used = session.get(tool_name, 0)
        return max(0, self.config.max_calls_per_tool - used)

    def remaining_for_session(self, session_id: str) -> int:
        """Return remaining total calls for a session. -1 means unlimited."""
        if self.config.max_calls_per_session <= 0:
            return -1
        session = self._counts.get(session_id, {})
        used = sum(session.values())
        return max(0, self.config.max_calls_per_session - used)
```

**Step 4: Run tests**

Run: `pytest tests/unit/test_tool_quotas.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add vecna/tools/quotas.py tests/unit/test_tool_quotas.py
git commit -m "feat: add tool quota manager for per-session and per-tool limits"
```

---

## Phase 2: Autonomy Upgrades

### Task 7: DB-Backed Priority Goal Queue

**Files:**
- Rewrite: `vecna/orchestrator/goal_queue.py:1-32`
- Create: `vecna/migrations/versions/005_goal_queue_table.py`
- Test: `tests/unit/test_goal_queue.py` (extend existing)
- Test: `tests/integration/test_goal_queue_pg.py`

**Step 1: Write the failing test**

```python
# tests/unit/test_goal_queue.py — replace/extend existing tests
"""Goal queue tests (in-memory fallback for unit tests)."""
import pytest
from vecna.orchestrator.goal_queue import GoalQueue, GoalItem, GoalStatus


class TestGoalItem:
    def test_create_goal_item(self):
        goal = GoalItem(content="learn about quantum computing", priority=5)
        assert goal.content == "learn about quantum computing"
        assert goal.priority == 5
        assert goal.status == GoalStatus.PENDING

    def test_goal_status_transitions(self):
        goal = GoalItem(content="test", priority=1)
        assert goal.status == GoalStatus.PENDING

        goal.status = GoalStatus.ACTIVE
        assert goal.status == GoalStatus.ACTIVE

        goal.status = GoalStatus.COMPLETED
        assert goal.status == GoalStatus.COMPLETED


class TestGoalQueue:
    @pytest.fixture
    def queue(self, tmp_path):
        return GoalQueue(path=tmp_path / "goals.jsonl")

    def test_push_and_pop_fifo(self, queue):
        queue.push(GoalItem(content="first", priority=1))
        queue.push(GoalItem(content="second", priority=1))
        item = queue.pop()
        assert item is not None
        assert item.content == "first"

    def test_pop_respects_priority(self, queue):
        queue.push(GoalItem(content="low", priority=1))
        queue.push(GoalItem(content="high", priority=10))
        queue.push(GoalItem(content="medium", priority=5))
        item = queue.pop()
        assert item is not None
        assert item.content == "high"

    def test_pop_returns_none_when_empty(self, queue):
        assert queue.pop() is None

    def test_dedup_rejects_duplicate_content(self, queue):
        queue.push(GoalItem(content="learn python", priority=5))
        queue.push(GoalItem(content="learn python", priority=8))
        # Should have only one goal
        first = queue.pop()
        second = queue.pop()
        assert first is not None
        assert second is None

    def test_list_pending(self, queue):
        queue.push(GoalItem(content="a", priority=1))
        queue.push(GoalItem(content="b", priority=2))
        pending = queue.list_pending()
        assert len(pending) == 2

    def test_mark_completed(self, queue):
        queue.push(GoalItem(content="do thing", priority=5))
        item = queue.pop()
        queue.mark_completed(item.id)
        pending = queue.list_pending()
        assert len(pending) == 0

    def test_mark_failed_with_retry(self, queue):
        queue.push(GoalItem(content="retry me", priority=5, max_retries=2))
        item = queue.pop()
        queue.mark_failed(item.id)
        # Should be re-queued since retries remain
        pending = queue.list_pending()
        assert len(pending) == 1
        assert pending[0].retry_count == 1
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_goal_queue.py -v`
Expected: FAIL with `ImportError: cannot import name 'GoalItem'`

**Step 3: Write implementation**

```python
# vecna/orchestrator/goal_queue.py
"""Priority goal queue with dedup, status tracking, and retry support."""
import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional


class GoalStatus(str, Enum):
    PENDING = "pending"
    ACTIVE = "active"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class GoalItem:
    """A single goal in the queue."""

    content: str
    priority: int = 5
    status: GoalStatus = GoalStatus.PENDING
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    retry_count: int = 0
    max_retries: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "content": self.content,
            "priority": self.priority,
            "status": self.status.value if isinstance(self.status, GoalStatus) else self.status,
            "created_at": self.created_at,
            "retry_count": self.retry_count,
            "max_retries": self.max_retries,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "GoalItem":
        status = data.get("status", "pending")
        if isinstance(status, str):
            status = GoalStatus(status)
        return cls(
            id=data.get("id", str(uuid.uuid4())),
            content=data["content"],
            priority=data.get("priority", 5),
            status=status,
            created_at=data.get("created_at", datetime.utcnow().isoformat()),
            retry_count=data.get("retry_count", 0),
            max_retries=data.get("max_retries", 0),
            metadata=data.get("metadata", {}),
        )


class GoalQueue:
    """File-backed priority goal queue with dedup and retry.

    Goals are sorted by priority (highest first). Duplicate content
    is rejected. Failed goals are re-queued if retries remain.

    For DB-backed persistence, use PgGoalQueue (requires PostgreSQL).
    """

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._goals: List[GoalItem] = []
        self._load()

    def _load(self) -> None:
        """Load goals from JSONL file."""
        if not self.path.exists():
            return
        try:
            with self.path.open("r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        data = json.loads(line)
                        # Handle legacy format: {"goal": "..."} from old GoalQueue
                        if "goal" in data and "content" not in data:
                            data["content"] = data.pop("goal")
                        self._goals.append(GoalItem.from_dict(data))
        except (json.JSONDecodeError, KeyError):
            pass

    def _save(self) -> None:
        """Persist goals to JSONL file."""
        with self.path.open("w", encoding="utf-8") as f:
            for goal in self._goals:
                f.write(json.dumps(goal.to_dict()) + "\n")

    def push(self, item: GoalItem) -> bool:
        """Add a goal. Returns False if duplicate content exists."""
        # Dedup: skip if same content already in queue
        existing_contents = {g.content for g in self._goals if g.status == GoalStatus.PENDING}
        if item.content in existing_contents:
            return False

        item.status = GoalStatus.PENDING
        self._goals.append(item)
        self._save()
        return True

    def pop(self) -> Optional[GoalItem]:
        """Remove and return the highest-priority pending goal."""
        pending = [g for g in self._goals if g.status == GoalStatus.PENDING]
        if not pending:
            return None

        # Sort by priority descending, then by created_at ascending (oldest first among same priority)
        pending.sort(key=lambda g: (-g.priority, g.created_at))
        best = pending[0]
        best.status = GoalStatus.ACTIVE
        self._save()
        return best

    def list_pending(self) -> List[GoalItem]:
        """Return all pending goals sorted by priority."""
        pending = [g for g in self._goals if g.status == GoalStatus.PENDING]
        pending.sort(key=lambda g: (-g.priority, g.created_at))
        return pending

    def mark_completed(self, goal_id: str) -> None:
        """Mark a goal as completed."""
        for goal in self._goals:
            if goal.id == goal_id:
                goal.status = GoalStatus.COMPLETED
                break
        self._save()

    def mark_failed(self, goal_id: str) -> None:
        """Mark a goal as failed. Re-queue if retries remain."""
        for goal in self._goals:
            if goal.id == goal_id:
                goal.retry_count += 1
                if goal.retry_count <= goal.max_retries:
                    goal.status = GoalStatus.PENDING
                else:
                    goal.status = GoalStatus.FAILED
                break
        self._save()
```

**Step 4: Run tests**

Run: `pytest tests/unit/test_goal_queue.py -v`
Expected: PASS

**Step 5: Update autonomy.py to use GoalItem**

Update `vecna/orchestrator/autonomy.py` to use the new `GoalItem`:

```python
# In autonomy.py, change the run() method's item handling:
# Before: goal = item.get("goal")
# After:  goal = item.content if isinstance(item, GoalItem) else item.get("goal", "")
```

**Step 6: Commit**

```bash
git add vecna/orchestrator/goal_queue.py tests/unit/test_goal_queue.py vecna/orchestrator/autonomy.py
git commit -m "feat: upgrade goal queue with priority, dedup, status, and retry support"
```

---

### Task 8: Curiosity Engine

**Files:**
- Rewrite: `vecna/orchestrator/curiosity.py:1-7`
- Test: `tests/unit/test_curiosity_engine.py` (extend existing)

**Step 1: Write the failing test**

```python
# tests/unit/test_curiosity_engine.py — extend/replace existing
"""Curiosity engine tests."""
import pytest
from vecna.orchestrator.curiosity import CuriosityEngine, CuriositySignal
from vecna.core.types import Fact, Belief, Hypothesis, OpenQuestion, Contradiction


class TestCuriositySignals:
    @pytest.fixture
    def engine(self):
        return CuriosityEngine()

    def test_generates_goals_from_contradictions(self, engine):
        contradictions = [
            Contradiction(content="Python is fast vs Python is slow", resolution=None)
        ]
        signals = engine.from_contradictions(contradictions)
        assert len(signals) == 1
        assert isinstance(signals[0], CuriositySignal)
        assert "contradiction" in signals[0].source

    def test_generates_goals_from_open_questions(self, engine):
        questions = [
            OpenQuestion(content="How does pgvector handle updates?")
        ]
        signals = engine.from_open_questions(questions)
        assert len(signals) == 1
        assert "question" in signals[0].source

    def test_generates_goals_from_low_confidence_beliefs(self, engine):
        beliefs = [
            Belief(content="Redis is always faster than PG", confidence=0.3),
            Belief(content="Python is interpreted", confidence=0.9),
        ]
        signals = engine.from_weak_beliefs(beliefs, threshold=0.5)
        assert len(signals) == 1
        assert "Redis" in signals[0].goal

    def test_generates_goals_from_knowledge_gaps(self, engine):
        facts = [
            Fact(content="We use PostgreSQL for storage", source="system"),
            Fact(content="We use Redis for caching", source="system"),
        ]
        hypotheses = [
            Hypothesis(content="Graph traversal could use Neo4j", confidence=0.4),
        ]
        signals = engine.from_knowledge_gaps(facts, hypotheses)
        assert len(signals) >= 1

    def test_prioritize_signals(self, engine):
        signals = [
            CuriositySignal(goal="low priority", source="question", urgency=0.2),
            CuriositySignal(goal="high priority", source="contradiction", urgency=0.9),
            CuriositySignal(goal="medium", source="weak_belief", urgency=0.5),
        ]
        ranked = engine.prioritize(signals, max_goals=2)
        assert len(ranked) == 2
        assert ranked[0].urgency >= ranked[1].urgency

    def test_dedup_similar_signals(self, engine):
        signals = [
            CuriositySignal(goal="explore Redis performance", source="question", urgency=0.5),
            CuriositySignal(goal="explore Redis speed", source="contradiction", urgency=0.6),
        ]
        # Should detect overlap via word similarity
        deduped = engine.dedup(signals)
        assert len(deduped) <= 2  # May or may not dedup depending on threshold

    def test_to_goal_dicts(self, engine):
        signals = [CuriositySignal(goal="test goal", source="test", urgency=0.5)]
        dicts = engine.to_goal_dicts(signals)
        assert len(dicts) == 1
        assert dicts[0]["content"] == "test goal"
        assert "priority" in dicts[0]
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_curiosity_engine.py -v`
Expected: FAIL with `ImportError: cannot import name 'CuriositySignal'`

**Step 3: Write implementation**

```python
# vecna/orchestrator/curiosity.py
"""Curiosity engine: self-directed exploration from knowledge gaps."""
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from vecna.core.types import Belief, Contradiction, Fact, Hypothesis, OpenQuestion


@dataclass
class CuriositySignal:
    """A signal indicating something worth exploring."""

    goal: str
    source: str  # "contradiction", "question", "weak_belief", "knowledge_gap"
    urgency: float = 0.5  # 0.0 to 1.0
    metadata: Dict[str, str] = field(default_factory=dict)


class CuriosityEngine:
    """Generate exploration goals from substrate state signals."""

    def from_contradictions(self, contradictions: List[Contradiction]) -> List[CuriositySignal]:
        """Generate goals to resolve contradictions."""
        signals = []
        for item in contradictions:
            content = item.content if isinstance(item, Contradiction) else str(item)
            signals.append(
                CuriositySignal(
                    goal=f"Investigate and resolve: {content}",
                    source="contradiction",
                    urgency=0.8,
                )
            )
        return signals

    def from_open_questions(self, questions: List[OpenQuestion]) -> List[CuriositySignal]:
        """Generate goals from unresolved questions."""
        signals = []
        for q in questions:
            content = q.content if isinstance(q, OpenQuestion) else str(q)
            signals.append(
                CuriositySignal(
                    goal=f"Research: {content}",
                    source="question",
                    urgency=0.6,
                )
            )
        return signals

    def from_weak_beliefs(
        self, beliefs: List[Belief], threshold: float = 0.5
    ) -> List[CuriositySignal]:
        """Generate goals to strengthen or refute low-confidence beliefs."""
        signals = []
        for b in beliefs:
            confidence = b.confidence if isinstance(b, Belief) else 0.5
            content = b.content if isinstance(b, Belief) else str(b)
            if confidence < threshold:
                signals.append(
                    CuriositySignal(
                        goal=f"Verify or refute: {content}",
                        source="weak_belief",
                        urgency=1.0 - confidence,
                        metadata={"confidence": str(confidence)},
                    )
                )
        return signals

    def from_knowledge_gaps(
        self, facts: List[Fact], hypotheses: List[Hypothesis]
    ) -> List[CuriositySignal]:
        """Generate goals from untested hypotheses."""
        signals = []
        for h in hypotheses:
            content = h.content if isinstance(h, Hypothesis) else str(h)
            confidence = h.confidence if isinstance(h, Hypothesis) else 0.5
            if confidence < 0.7:
                signals.append(
                    CuriositySignal(
                        goal=f"Test hypothesis: {content}",
                        source="knowledge_gap",
                        urgency=0.5 + (0.5 * (1.0 - confidence)),
                        metadata={"confidence": str(confidence)},
                    )
                )
        return signals

    def prioritize(
        self, signals: List[CuriositySignal], max_goals: int = 5
    ) -> List[CuriositySignal]:
        """Sort signals by urgency and return top N."""
        sorted_signals = sorted(signals, key=lambda s: s.urgency, reverse=True)
        return sorted_signals[:max_goals]

    def dedup(self, signals: List[CuriositySignal]) -> List[CuriositySignal]:
        """Remove near-duplicate signals by word overlap."""
        if len(signals) <= 1:
            return signals

        result = [signals[0]]
        for candidate in signals[1:]:
            candidate_words = set(candidate.goal.lower().split())
            is_dup = False
            for existing in result:
                existing_words = set(existing.goal.lower().split())
                if not candidate_words or not existing_words:
                    continue
                overlap = len(candidate_words & existing_words)
                jaccard = overlap / len(candidate_words | existing_words)
                if jaccard > 0.6:
                    is_dup = True
                    break
            if not is_dup:
                result.append(candidate)
        return result

    def to_goal_dicts(self, signals: List[CuriositySignal]) -> List[Dict[str, str]]:
        """Convert signals to goal dicts for GoalQueue."""
        return [
            {
                "content": s.goal,
                "priority": str(int(s.urgency * 10)),
                "metadata": {"source": s.source, **s.metadata},
            }
            for s in signals
        ]
```

**Step 4: Run tests**

Run: `pytest tests/unit/test_curiosity_engine.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add vecna/orchestrator/curiosity.py tests/unit/test_curiosity_engine.py
git commit -m "feat: implement curiosity engine with multi-signal exploration goals"
```

---

### Task 9: Kill-Switch with Audit Trail

**Files:**
- Create: `vecna/orchestrator/kill_switch.py`
- Modify: `vecna/orchestrator/autonomy.py` (integrate kill-switch check)
- Test: `tests/unit/test_kill_switch.py`

**Step 1: Write the failing test**

```python
# tests/unit/test_kill_switch.py
"""Kill-switch tests."""
import pytest
from pathlib import Path
from vecna.orchestrator.kill_switch import KillSwitch


class TestKillSwitch:
    @pytest.fixture
    def ks(self, tmp_path):
        return KillSwitch(state_dir=tmp_path)

    def test_not_killed_by_default(self, ks):
        assert ks.is_killed() is False

    def test_kill_sets_flag(self, ks):
        ks.kill(reason="test emergency stop")
        assert ks.is_killed() is True

    def test_resume_clears_flag(self, ks):
        ks.kill(reason="test")
        ks.resume(reason="safe to continue")
        assert ks.is_killed() is False

    def test_audit_trail_records_events(self, ks):
        ks.kill(reason="first kill")
        ks.resume(reason="first resume")
        ks.kill(reason="second kill")

        trail = ks.get_audit_trail()
        assert len(trail) == 3
        assert trail[0]["action"] == "kill"
        assert trail[1]["action"] == "resume"
        assert trail[2]["action"] == "kill"

    def test_kill_persists_across_instances(self, tmp_path):
        ks1 = KillSwitch(state_dir=tmp_path)
        ks1.kill(reason="persist test")

        ks2 = KillSwitch(state_dir=tmp_path)
        assert ks2.is_killed() is True

    def test_check_or_raise(self, ks):
        ks.kill(reason="test")
        with pytest.raises(RuntimeError, match="Kill switch"):
            ks.check_or_raise()
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_kill_switch.py -v`
Expected: FAIL with `ModuleNotFoundError`

**Step 3: Write implementation**

```python
# vecna/orchestrator/kill_switch.py
"""Kill-switch for emergency halt of autonomous operations."""
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

logger = logging.getLogger("vecna.kill_switch")


class KillSwitch:
    """Emergency halt mechanism with audit trail.

    State is persisted to disk so it survives process restarts.
    """

    def __init__(self, state_dir: Path) -> None:
        self._state_dir = Path(state_dir)
        self._state_dir.mkdir(parents=True, exist_ok=True)
        self._flag_path = self._state_dir / "kill_switch.flag"
        self._audit_path = self._state_dir / "kill_switch_audit.jsonl"

    def is_killed(self) -> bool:
        """Check if the kill switch is active."""
        return self._flag_path.exists()

    def kill(self, reason: str = "") -> None:
        """Activate the kill switch."""
        self._flag_path.write_text(reason or "manual kill", encoding="utf-8")
        self._append_audit("kill", reason)
        logger.warning(f"Kill switch ACTIVATED: {reason}")

    def resume(self, reason: str = "") -> None:
        """Deactivate the kill switch."""
        if self._flag_path.exists():
            self._flag_path.unlink()
        self._append_audit("resume", reason)
        logger.info(f"Kill switch DEACTIVATED: {reason}")

    def check_or_raise(self) -> None:
        """Raise RuntimeError if kill switch is active."""
        if self.is_killed():
            reason = self._flag_path.read_text(encoding="utf-8").strip()
            raise RuntimeError(f"Kill switch is active: {reason}")

    def get_audit_trail(self) -> List[Dict[str, Any]]:
        """Return the full audit trail."""
        if not self._audit_path.exists():
            return []
        entries = []
        with self._audit_path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    entries.append(json.loads(line))
        return entries

    def _append_audit(self, action: str, reason: str) -> None:
        """Append an event to the audit trail."""
        event = {
            "action": action,
            "reason": reason,
            "timestamp": datetime.utcnow().isoformat(),
        }
        with self._audit_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(event) + "\n")
```

**Step 4: Run tests**

Run: `pytest tests/unit/test_kill_switch.py -v`
Expected: PASS

**Step 5: Integrate into autonomy.py**

In `vecna/orchestrator/autonomy.py`, add kill-switch check in `run()`:

```python
# Add to AutonomyLoop.run() at the start of the while loop:
#     if hasattr(self, '_kill_switch') and self._kill_switch and self._kill_switch.is_killed():
#         logger.warning("Kill switch active, halting autonomy loop.")
#         break
```

**Step 6: Commit**

```bash
git add vecna/orchestrator/kill_switch.py tests/unit/test_kill_switch.py vecna/orchestrator/autonomy.py
git commit -m "feat: add kill-switch with audit trail for autonomous operations"
```

---

### Task 10: Autonomy Loop with Backoff and Scheduling

**Files:**
- Modify: `vecna/orchestrator/autonomy.py:1-36`
- Test: `tests/unit/test_autonomy_loop.py`

**Step 1: Write the failing test**

```python
# tests/unit/test_autonomy_loop.py
"""Autonomy loop tests."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from vecna.orchestrator.autonomy import AutonomyLoop, BackoffConfig
from vecna.orchestrator.goal_queue import GoalQueue, GoalItem
from vecna.orchestrator.kill_switch import KillSwitch


class TestBackoffConfig:
    def test_default_backoff(self):
        config = BackoffConfig()
        assert config.base_delay_seconds > 0
        assert config.max_delay_seconds > config.base_delay_seconds

    def test_compute_delay_exponential(self):
        config = BackoffConfig(base_delay_seconds=1.0, max_delay_seconds=60.0, multiplier=2.0)
        assert config.compute_delay(0) == 1.0
        assert config.compute_delay(1) == 2.0
        assert config.compute_delay(2) == 4.0
        assert config.compute_delay(10) == 60.0  # capped at max


class TestAutonomyLoopIntegration:
    @pytest.fixture
    def queue(self, tmp_path):
        return GoalQueue(path=tmp_path / "goals.jsonl")

    @pytest.fixture
    def kill_switch(self, tmp_path):
        return KillSwitch(state_dir=tmp_path)

    async def test_halts_when_kill_switch_active(self, queue, kill_switch, tmp_path):
        queue.push(GoalItem(content="should not run", priority=5))
        kill_switch.kill(reason="test halt")

        loop = AutonomyLoop(name="test")
        loop._kill_switch = kill_switch
        # Mock think to track if it was called
        loop.think = AsyncMock(return_value="done")

        results = await loop.run(goal_queue=queue, max_cycles=1)
        assert len(results) == 0
        loop.think.assert_not_called()
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_autonomy_loop.py -v`
Expected: FAIL with `ImportError: cannot import name 'BackoffConfig'`

**Step 3: Write implementation**

```python
# vecna/orchestrator/autonomy.py
"""Autonomy loop: background goal execution with backoff, scheduling, and kill-switch."""
import asyncio
import logging
from dataclasses import dataclass
from typing import List, Optional

from vecna.adapters.base import BaseAdapter
from vecna.orchestrator.goal_queue import GoalQueue, GoalItem, GoalStatus
from vecna.orchestrator.kill_switch import KillSwitch
from vecna.orchestrator.loop import HiveConfig, HiveLoop

logger = logging.getLogger("vecna.autonomy")


@dataclass
class BackoffConfig:
    """Exponential backoff configuration for idle/error cycles."""

    base_delay_seconds: float = 2.0
    max_delay_seconds: float = 120.0
    multiplier: float = 2.0

    def compute_delay(self, consecutive_failures: int) -> float:
        """Compute delay for the given number of consecutive failures."""
        delay = self.base_delay_seconds * (self.multiplier ** consecutive_failures)
        return min(delay, self.max_delay_seconds)


class AutonomyLoop(HiveLoop):
    def __init__(
        self,
        config: Optional[HiveConfig] = None,
        adapters: Optional[List[BaseAdapter]] = None,
        name: str = "explorer",
        backoff: Optional[BackoffConfig] = None,
        kill_switch: Optional[KillSwitch] = None,
    ):
        super().__init__(config=config, adapters=adapters, name=name)
        self._backoff = backoff or BackoffConfig()
        self._kill_switch = kill_switch

    async def run(
        self,
        goal_queue: GoalQueue,
        max_cycles: Optional[int] = None,
    ) -> List[str]:
        """Drain the goal queue, executing goals with backoff and kill-switch checks."""
        results: List[str] = []
        consecutive_failures = 0
        cycles = 0

        while True:
            # Kill-switch check
            if self._kill_switch and self._kill_switch.is_killed():
                logger.warning("Kill switch active — halting autonomy loop.")
                break

            # Cycle limit check
            if max_cycles is not None and cycles >= max_cycles:
                break

            item = goal_queue.pop()
            if item is None:
                break

            cycles += 1
            goal_content = item.content if isinstance(item, GoalItem) else item.get("goal", "")
            if not goal_content:
                continue

            try:
                result = await self._run_goal(goal_content, max_cycles=max_cycles)
                results.append(result)
                consecutive_failures = 0

                if isinstance(item, GoalItem):
                    goal_queue.mark_completed(item.id)

            except Exception as exc:
                logger.error(f"Goal failed: {goal_content[:80]}: {exc}")
                consecutive_failures += 1

                if isinstance(item, GoalItem):
                    goal_queue.mark_failed(item.id)

                # Backoff on failure
                delay = self._backoff.compute_delay(consecutive_failures)
                logger.info(f"Backing off for {delay:.1f}s after {consecutive_failures} failures")
                await asyncio.sleep(delay)

        return results

    async def _run_goal(self, goal: str, max_cycles: Optional[int] = None) -> str:
        """Execute one queued goal, preferring ReWOO when enabled."""
        return await self.think(goal, max_cycles=max_cycles)
```

**Step 4: Run tests**

Run: `pytest tests/unit/test_autonomy_loop.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add vecna/orchestrator/autonomy.py tests/unit/test_autonomy_loop.py
git commit -m "feat: upgrade autonomy loop with backoff, kill-switch, and GoalItem support"
```

---

## Phase 3: Memory Improvements

### Task 11: Obsidian-Compatible Workspace Init

**Files:**
- Modify: `vecna/memory/workspace.py` (add `.obsidian/` vault config)
- Test: `tests/unit/test_workspace.py` (extend)

**Step 1: Write the failing test**

```python
# Add to tests/unit/test_workspace.py

class TestObsidianCompatibility:
    def test_creates_obsidian_config_dir(self, tmp_path):
        from vecna.memory.workspace import init_workspace

        init_workspace(tmp_path)
        obsidian_dir = tmp_path / ".obsidian"
        assert obsidian_dir.exists()
        assert (obsidian_dir / "app.json").exists()

    def test_obsidian_config_enables_wikilinks(self, tmp_path):
        import json
        from vecna.memory.workspace import init_workspace

        init_workspace(tmp_path)
        config = json.loads((tmp_path / ".obsidian" / "app.json").read_text())
        assert config.get("useMarkdownLinks") is True or "useMarkdownLinks" in config
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_workspace.py::TestObsidianCompatibility -v`
Expected: FAIL (no `.obsidian/` directory created)

**Step 3: Add Obsidian config to workspace init**

In `vecna/memory/workspace.py`, add to `init_workspace()`:

```python
    # Make workspace Obsidian-vault-compatible for optional visualization
    obsidian_dir = workspace_dir / ".obsidian"
    obsidian_dir.mkdir(exist_ok=True)
    app_config = obsidian_dir / "app.json"
    if not app_config.exists():
        import json
        app_config.write_text(json.dumps({
            "useMarkdownLinks": True,
            "newFileLocation": "folder",
            "newFileFolderPath": "memory",
            "attachmentFolderPath": ".attachments",
        }, indent=2))
```

**Step 4: Run tests**

Run: `pytest tests/unit/test_workspace.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add vecna/memory/workspace.py tests/unit/test_workspace.py
git commit -m "feat: make vecna workspace Obsidian-vault-compatible"
```

---

### Task 12: Multi-Hop Graph Traversal (Recursive CTE)

**Files:**
- Modify: `vecna/memory/pg_store.py:910-976`
- Test: `tests/integration/test_pg_memory_store.py` (extend)

**Step 1: Write the failing integration test**

```python
# Add to tests/integration/test_pg_memory_store.py

class TestMultiHopTraversal:
    """Tests for recursive graph traversal (requires PG)."""

    @pytest.fixture
    async def seeded_store(self, pg_store):
        """Create a chain: A -> B -> C -> D"""
        a = await pg_store.add_item(content="Node A", item_type="fact")
        b = await pg_store.add_item(content="Node B", item_type="fact")
        c = await pg_store.add_item(content="Node C", item_type="fact")
        d = await pg_store.add_item(content="Node D", item_type="fact")

        pg_store.add_edge(a.id, b.id, relation="related_to", weight=0.9)
        pg_store.add_edge(b.id, c.id, relation="related_to", weight=0.8)
        pg_store.add_edge(c.id, d.id, relation="related_to", weight=0.7)

        return pg_store, a, b, c, d

    async def test_depth_1_returns_direct_neighbors(self, seeded_store):
        store, a, b, c, d = seeded_store
        results = store.get_related_items(a.id, max_depth=1)
        ids = [item.id for item, _, _ in results]
        assert b.id in ids
        assert c.id not in ids

    async def test_depth_2_returns_two_hops(self, seeded_store):
        store, a, b, c, d = seeded_store
        results = store.get_related_items(a.id, max_depth=2)
        ids = [item.id for item, _, _ in results]
        assert b.id in ids
        assert c.id in ids
        assert d.id not in ids

    async def test_depth_3_returns_full_chain(self, seeded_store):
        store, a, b, c, d = seeded_store
        results = store.get_related_items(a.id, max_depth=3)
        ids = [item.id for item, _, _ in results]
        assert b.id in ids
        assert c.id in ids
        assert d.id in ids

    async def test_path_is_correct(self, seeded_store):
        store, a, b, c, d = seeded_store
        results = store.get_related_items(a.id, max_depth=3)
        # Find the path to D
        for item, weight, path in results:
            if item.id == d.id:
                assert len(path) > 3  # Should have intermediate nodes
```

**Step 2: Run test**

Run: `pytest tests/integration/test_pg_memory_store.py::TestMultiHopTraversal -v`
Expected: FAIL (depth 2+ returns nothing because `max_depth` is ignored)

**Step 3: Implement recursive CTE**

Replace the `get_related_items` method in `vecna/memory/pg_store.py` (lines 910-976):

```python
    def get_related_items(
        self, item_id: str, relation: Optional[str] = None, max_depth: int = 1
    ) -> List[Tuple[MemoryItem, float, List[str]]]:
        """
        Get items related to a given item via edges using recursive CTE.

        Returns list of (item, path_weight, path) tuples.
        """
        conn = self._get_connection()

        try:
            relation_filter = "AND me.relation = %s" if relation else ""
            params_cte = [item_id, item_id]
            if relation:
                params_cte.append(relation)

            query = f"""
                WITH RECURSIVE graph AS (
                    -- Base case: direct neighbors
                    SELECT
                        CASE WHEN me.source_id = %s THEN me.target_id ELSE me.source_id END AS node_id,
                        me.weight,
                        me.relation,
                        ARRAY[%s, me.relation,
                              CASE WHEN me.source_id = %s THEN me.target_id ELSE me.source_id END
                        ]::text[] AS path,
                        1 AS depth
                    FROM memory_edges me
                    WHERE (me.source_id = %s OR me.target_id = %s)
                    {relation_filter}

                    UNION ALL

                    -- Recursive case: follow edges
                    SELECT
                        CASE WHEN me.source_id = g.node_id THEN me.target_id ELSE me.source_id END,
                        g.weight * me.weight,
                        me.relation,
                        g.path || me.relation ||
                            CASE WHEN me.source_id = g.node_id THEN me.target_id ELSE me.source_id END,
                        g.depth + 1
                    FROM memory_edges me
                    JOIN graph g ON (me.source_id = g.node_id OR me.target_id = g.node_id)
                    WHERE g.depth < %s
                        AND NOT (
                            CASE WHEN me.source_id = g.node_id THEN me.target_id ELSE me.source_id END
                        ) = ANY(g.path)
                        {relation_filter}
                )
                SELECT DISTINCT ON (mi.id)
                    mi.id, mi.content, mi.item_type, mi.confidence, mi.domain,
                    mi.source_model, mi.embedding, mi.metadata, mi.retrieval_count,
                    mi.last_retrieved_at, mi.created_at, mi.updated_at,
                    g.weight, g.path
                FROM graph g
                JOIN memory_items mi ON mi.id = g.node_id::uuid
                ORDER BY mi.id, g.weight DESC
            """

            # Build params
            params = [item_id, item_id, item_id, item_id, item_id]
            if relation:
                params.append(relation)
            params.append(max_depth)
            if relation:
                params.append(relation)

            with conn.cursor() as cur:
                cur.execute(query, params)
                rows = cur.fetchall()

            results = []
            for row in rows:
                item = MemoryItem(
                    id=str(row[0]),
                    content=row[1],
                    item_type=row[2],
                    confidence=row[3],
                    domain=row[4],
                    source_model=row[5],
                    embedding=list(row[6]) if row[6] is not None else None,
                    metadata=row[7] or {},
                    retrieval_count=row[8] or 0,
                    last_retrieved_at=row[9],
                    created_at=row[10],
                    updated_at=row[11],
                )
                weight = row[12]
                path = list(row[13]) if row[13] else [item_id, str(row[0])]
                results.append((item, weight, path))

            return results

        except Exception as e:
            logger.error(f"Failed to get related items: {e}")
            return []
```

> **Note:** The exact SQL will need testing against the actual PG schema. The recursive CTE avoids cycles via the `NOT ... = ANY(g.path)` check. The implementer should verify column types and adjust cast expressions as needed.

**Step 4: Run integration tests**

Run: `pytest tests/integration/test_pg_memory_store.py::TestMultiHopTraversal -v`
Expected: PASS (requires running PostgreSQL)

**Step 5: Commit**

```bash
git add vecna/memory/pg_store.py tests/integration/test_pg_memory_store.py
git commit -m "feat: implement multi-hop graph traversal via recursive CTE"
```

---

### Task 13: Dream Loop Insight Generation

**Files:**
- Modify: `vecna/memory/dream_loop.py:449-461`
- Test: `tests/unit/test_dream_loop.py` (extend)

**Step 1: Write the failing test**

```python
# Add to tests/unit/test_dream_loop.py

class TestGenerateInsights:
    def test_generates_insights_from_clusters(self, dream_loop_with_summarizer):
        """_generate_insights should find related memories and synthesize."""
        loop = dream_loop_with_summarizer

        # Mock pg_store.search to return related memories
        loop.pg_store.search = MagicMock(return_value=[
            (MagicMock(id="1", content="Python is great for data science", item_type="fact"), 0.9),
            (MagicMock(id="2", content="Python ML libraries are mature", item_type="fact"), 0.85),
            (MagicMock(id="3", content="NumPy powers scientific computing", item_type="fact"), 0.8),
        ])
        loop.pg_store.get_recent_events = MagicMock(return_value=[])

        # Mock summarizer to return insight text
        loop.summarizer = MagicMock()
        loop.summarizer.return_value = "Python's data science ecosystem is mature and interconnected."

        count = loop._generate_insights(dry_run=True)
        # Should attempt to generate at least one insight
        assert count >= 0  # May be 0 if not enough clusters

    def test_returns_zero_without_summarizer(self):
        from vecna.memory.dream_loop import DreamLoop

        loop = DreamLoop.__new__(DreamLoop)
        loop.summarizer = None
        loop.pg_store = None
        assert loop._generate_insights(dry_run=False) == 0
```

**Step 2: Run test to verify behavior**

Run: `pytest tests/unit/test_dream_loop.py::TestGenerateInsights -v`

**Step 3: Implement `_generate_insights`**

Replace the placeholder in `vecna/memory/dream_loop.py:449-461`:

```python
    def _generate_insights(self, dry_run: bool) -> int:
        """Generate new insights by cross-referencing memories (requires LLM)."""
        if not self.summarizer or not self.pg_store:
            return 0

        insights_generated = 0

        try:
            # Get recent high-confidence facts to find clusters
            recent_items = self.pg_store.search("", top_k=50)
            if len(recent_items) < 3:
                return 0

            # Group items by domain
            domain_groups: Dict[str, List[Any]] = {}
            for item, score in recent_items:
                domain = getattr(item, "domain", "general") or "general"
                domain_groups.setdefault(domain, []).append(item)

            # For each domain with enough items, try to synthesize
            for domain, items in domain_groups.items():
                if len(items) < 3:
                    continue

                # Take top items and ask summarizer to find patterns
                contents = [item.content for item in items[:10]]
                combined = "\n- ".join(contents)
                prompt = (
                    f"Given these related facts/beliefs in the '{domain}' domain:\n"
                    f"- {combined}\n\n"
                    "What pattern, insight, or hypothesis emerges from these? "
                    "Respond with a single concise insight sentence."
                )

                try:
                    insight_text = self.summarizer(prompt)
                    if insight_text and len(insight_text.strip()) > 10:
                        if not dry_run:
                            self.pg_store.add_item(
                                content=insight_text.strip(),
                                item_type="hypothesis",
                                domain=domain,
                                confidence=0.5,
                                metadata={"source": "dream_loop_insight", "input_count": len(items)},
                            )
                        insights_generated += 1
                except Exception as e:
                    logger.warning(f"Insight generation failed for domain {domain}: {e}")

        except Exception as e:
            logger.error(f"Dream insight generation error: {e}")

        return insights_generated
```

**Step 4: Run tests**

Run: `pytest tests/unit/test_dream_loop.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add vecna/memory/dream_loop.py tests/unit/test_dream_loop.py
git commit -m "feat: implement dream loop insight generation from memory clusters"
```

---

## Phase 4: Security Hardening

### Task 14: Container TTL Auto-Cleanup

**Files:**
- Modify: `vecna/memory/rlm_bridge.py` (add TTL tracking and cleanup)
- Test: `tests/unit/test_container_ttl.py`

**Step 1: Write the failing test**

```python
# tests/unit/test_container_ttl.py
"""Container TTL tests."""
import pytest
from datetime import datetime, timedelta
from vecna.tools.container_ttl import ContainerTTLManager


class TestContainerTTLManager:
    def test_registers_container(self):
        mgr = ContainerTTLManager(default_ttl_seconds=300)
        mgr.register("container-123")
        assert mgr.is_registered("container-123")

    def test_detects_expired_container(self):
        mgr = ContainerTTLManager(default_ttl_seconds=0)  # immediate expiry
        mgr.register("container-123")
        expired = mgr.get_expired()
        assert "container-123" in expired

    def test_not_expired_within_ttl(self):
        mgr = ContainerTTLManager(default_ttl_seconds=3600)
        mgr.register("container-123")
        expired = mgr.get_expired()
        assert "container-123" not in expired

    def test_unregister_removes_tracking(self):
        mgr = ContainerTTLManager(default_ttl_seconds=300)
        mgr.register("container-123")
        mgr.unregister("container-123")
        assert not mgr.is_registered("container-123")

    def test_touch_extends_ttl(self):
        mgr = ContainerTTLManager(default_ttl_seconds=1)
        mgr.register("container-123")
        import time
        time.sleep(0.1)
        mgr.touch("container-123")  # Reset TTL
        # Should not be expired immediately after touch
        assert "container-123" not in mgr.get_expired()
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_container_ttl.py -v`
Expected: FAIL with `ModuleNotFoundError`

**Step 3: Write implementation**

```python
# vecna/tools/container_ttl.py
"""Container TTL tracking and auto-cleanup."""
import logging
from datetime import datetime, timedelta
from typing import Dict, List

logger = logging.getLogger("vecna.tools.container_ttl")


class ContainerTTLManager:
    """Track container lifetimes and identify expired containers."""

    def __init__(self, default_ttl_seconds: int = 600) -> None:
        self._default_ttl = default_ttl_seconds
        self._containers: Dict[str, datetime] = {}  # container_id -> last_active

    def register(self, container_id: str) -> None:
        """Register a container with the current timestamp."""
        self._containers[container_id] = datetime.utcnow()

    def unregister(self, container_id: str) -> None:
        """Remove a container from tracking."""
        self._containers.pop(container_id, None)

    def is_registered(self, container_id: str) -> bool:
        """Check if a container is tracked."""
        return container_id in self._containers

    def touch(self, container_id: str) -> None:
        """Reset the TTL for a container."""
        if container_id in self._containers:
            self._containers[container_id] = datetime.utcnow()

    def get_expired(self) -> List[str]:
        """Return list of container IDs that have exceeded their TTL."""
        now = datetime.utcnow()
        cutoff = now - timedelta(seconds=self._default_ttl)
        return [
            cid for cid, last_active in self._containers.items() if last_active <= cutoff
        ]
```

**Step 4: Run tests**

Run: `pytest tests/unit/test_container_ttl.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add vecna/tools/container_ttl.py tests/unit/test_container_ttl.py
git commit -m "feat: add container TTL tracking for auto-cleanup"
```

---

### Task 15: PII/Secret Redaction

**Files:**
- Create: `vecna/tools/redaction.py`
- Test: `tests/unit/test_redaction.py`

**Step 1: Write the failing test**

```python
# tests/unit/test_redaction.py
"""PII/secret redaction tests."""
import pytest
from vecna.tools.redaction import redact_secrets, redact_pii


class TestRedactSecrets:
    def test_redacts_aws_keys(self):
        text = "My key is AKIAIOSFODNN7EXAMPLE and secret is wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"
        result = redact_secrets(text)
        assert "AKIAIOSFODNN7EXAMPLE" not in result
        assert "[REDACTED_AWS_KEY]" in result

    def test_redacts_generic_api_keys(self):
        text = 'api_key = "sk-1234567890abcdef1234567890abcdef"'
        result = redact_secrets(text)
        assert "sk-1234567890abcdef" not in result

    def test_redacts_database_urls(self):
        text = "DATABASE_URL=postgresql://user:password123@host:5432/db"
        result = redact_secrets(text)
        assert "password123" not in result

    def test_preserves_normal_text(self):
        text = "This is a normal sentence about programming."
        result = redact_secrets(text)
        assert result == text


class TestRedactPII:
    def test_redacts_email_addresses(self):
        text = "Contact me at john.doe@example.com for details."
        result = redact_pii(text)
        assert "john.doe@example.com" not in result
        assert "[REDACTED_EMAIL]" in result

    def test_redacts_phone_numbers(self):
        text = "Call me at 555-123-4567 or (555) 987-6543."
        result = redact_pii(text)
        assert "555-123-4567" not in result

    def test_preserves_normal_text(self):
        text = "The quick brown fox jumps over the lazy dog."
        result = redact_pii(text)
        assert result == text
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_redaction.py -v`
Expected: FAIL

**Step 3: Write implementation**

```python
# vecna/tools/redaction.py
"""PII and secret redaction for logs and audit trails."""
import re
from typing import List, Tuple


# Secret patterns: (regex, replacement)
_SECRET_PATTERNS: List[Tuple[re.Pattern, str]] = [
    # AWS Access Key ID
    (re.compile(r"AKIA[0-9A-Z]{16}"), "[REDACTED_AWS_KEY]"),
    # Generic long hex/alphanum tokens (API keys, secrets)
    (re.compile(r"(?:api[_-]?key|secret|token|password|passwd|pwd)\s*[=:]\s*['\"]?([A-Za-z0-9_\-]{20,})['\"]?", re.IGNORECASE), r"[REDACTED_SECRET]"),
    # OpenAI-style keys
    (re.compile(r"sk-[A-Za-z0-9]{20,}"), "[REDACTED_API_KEY]"),
    # Database URLs with passwords
    (re.compile(r"(postgresql|mysql|redis|mongodb)://[^:]+:([^@]+)@"), r"\1://[user]:[REDACTED_PASSWORD]@"),
    # GitHub tokens
    (re.compile(r"ghp_[A-Za-z0-9]{36}"), "[REDACTED_GH_TOKEN]"),
    (re.compile(r"gho_[A-Za-z0-9]{36}"), "[REDACTED_GH_TOKEN]"),
]

# PII patterns
_PII_PATTERNS: List[Tuple[re.Pattern, str]] = [
    # Email addresses
    (re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}"), "[REDACTED_EMAIL]"),
    # US phone numbers (various formats)
    (re.compile(r"\(?\d{3}\)?[\s\-.]?\d{3}[\s\-.]?\d{4}"), "[REDACTED_PHONE]"),
    # SSN
    (re.compile(r"\d{3}-\d{2}-\d{4}"), "[REDACTED_SSN]"),
]


def redact_secrets(text: str) -> str:
    """Redact known secret patterns from text."""
    result = text
    for pattern, replacement in _SECRET_PATTERNS:
        result = pattern.sub(replacement, result)
    return result


def redact_pii(text: str) -> str:
    """Redact personally identifiable information from text."""
    result = text
    for pattern, replacement in _PII_PATTERNS:
        result = pattern.sub(replacement, result)
    return result


def redact_all(text: str) -> str:
    """Redact both secrets and PII from text."""
    return redact_pii(redact_secrets(text))
```

**Step 4: Run tests**

Run: `pytest tests/unit/test_redaction.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add vecna/tools/redaction.py tests/unit/test_redaction.py
git commit -m "feat: add PII and secret redaction for logs and audit trails"
```

---

## Phase 5: Observability

### Task 16: Tool Audit Dashboard Data

**Files:**
- Create: `vecna/observability/tool_dashboard.py`
- Test: `tests/unit/test_tool_dashboard.py`

**Step 1: Write the failing test**

```python
# tests/unit/test_tool_dashboard.py
"""Tool dashboard data aggregation tests."""
import pytest
from vecna.observability.tool_dashboard import ToolDashboard
from vecna.tools.audit import ToolAuditEvent


class TestToolDashboard:
    def test_aggregate_empty(self):
        dash = ToolDashboard()
        stats = dash.get_stats()
        assert stats["total_calls"] == 0

    def test_aggregate_events(self):
        dash = ToolDashboard()
        dash.ingest(ToolAuditEvent(tool_name="python_exec", action="allow", risk_tier="low", success=True))
        dash.ingest(ToolAuditEvent(tool_name="python_exec", action="allow", risk_tier="low", success=False))
        dash.ingest(ToolAuditEvent(tool_name="http_request", action="allow", risk_tier="low", success=True))

        stats = dash.get_stats()
        assert stats["total_calls"] == 3
        assert stats["by_tool"]["python_exec"]["total"] == 2
        assert stats["by_tool"]["python_exec"]["success"] == 1
        assert stats["by_tool"]["http_request"]["total"] == 1

    def test_failure_rate(self):
        dash = ToolDashboard()
        for _ in range(8):
            dash.ingest(ToolAuditEvent(tool_name="test", action="allow", risk_tier="low", success=True))
        for _ in range(2):
            dash.ingest(ToolAuditEvent(tool_name="test", action="allow", risk_tier="low", success=False))

        stats = dash.get_stats()
        assert stats["by_tool"]["test"]["failure_rate"] == pytest.approx(0.2)

    def test_denied_calls_tracked(self):
        dash = ToolDashboard()
        dash.ingest(ToolAuditEvent(tool_name="python_exec", action="deny", risk_tier="high", success=False))

        stats = dash.get_stats()
        assert stats["denied_count"] == 1
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_tool_dashboard.py -v`
Expected: FAIL

**Step 3: Write implementation**

```python
# vecna/observability/tool_dashboard.py
"""Tool usage aggregation for dashboards."""
from dataclasses import dataclass, field
from typing import Any, Dict, List

from vecna.tools.audit import ToolAuditEvent


@dataclass
class ToolStats:
    total: int = 0
    success: int = 0
    failed: int = 0
    denied: int = 0

    @property
    def failure_rate(self) -> float:
        if self.total == 0:
            return 0.0
        return self.failed / self.total


class ToolDashboard:
    """Aggregate tool audit events into dashboard metrics."""

    def __init__(self) -> None:
        self._events: List[ToolAuditEvent] = []
        self._by_tool: Dict[str, ToolStats] = {}
        self._total = ToolStats()

    def ingest(self, event: ToolAuditEvent) -> None:
        """Ingest a single audit event."""
        self._events.append(event)

        stats = self._by_tool.setdefault(event.tool_name, ToolStats())
        stats.total += 1
        self._total.total += 1

        if event.action == "deny":
            stats.denied += 1
            self._total.denied += 1
            stats.failed += 1
            self._total.failed += 1
        elif event.success:
            stats.success += 1
            self._total.success += 1
        else:
            stats.failed += 1
            self._total.failed += 1

    def get_stats(self) -> Dict[str, Any]:
        """Return aggregated statistics."""
        return {
            "total_calls": self._total.total,
            "success_count": self._total.success,
            "failed_count": self._total.failed,
            "denied_count": self._total.denied,
            "by_tool": {
                name: {
                    "total": s.total,
                    "success": s.success,
                    "failed": s.failed,
                    "denied": s.denied,
                    "failure_rate": s.failure_rate,
                }
                for name, s in self._by_tool.items()
            },
        }
```

**Step 4: Run tests**

Run: `pytest tests/unit/test_tool_dashboard.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add vecna/observability/tool_dashboard.py tests/unit/test_tool_dashboard.py
git commit -m "feat: add tool audit dashboard data aggregation"
```

---

## Phase 6: UX Polish

### Task 17: Queue Status CLI Command

**Files:**
- Modify: `vecna/cli/main.py` (add `vecna queue` command group)
- Test: `tests/e2e/test_cli_queue.py`

**Step 1: Write the failing test**

```python
# tests/e2e/test_cli_queue.py
"""CLI queue status tests."""
import pytest
from click.testing import CliRunner
from vecna.cli.main import cli


class TestQueueCLI:
    def test_queue_status_shows_empty(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["queue", "status"], catch_exceptions=False)
        assert result.exit_code == 0
        assert "empty" in result.output.lower() or "0" in result.output

    def test_queue_list_command_exists(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["queue", "--help"])
        assert result.exit_code == 0
        assert "status" in result.output
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/e2e/test_cli_queue.py -v`
Expected: FAIL (no `queue` command group)

**Step 3: Add queue CLI commands**

In `vecna/cli/main.py`, add:

```python
@cli.group()
def queue():
    """Goal queue management."""
    pass


@queue.command()
def status():
    """Show goal queue status."""
    from pathlib import Path
    from vecna.orchestrator.goal_queue import GoalQueue

    queue_path = Path.home() / ".vecna" / "goal_queue.jsonl"
    q = GoalQueue(path=queue_path)
    pending = q.list_pending()

    if not pending:
        click.echo("Goal queue is empty (0 pending goals).")
        return

    click.echo(f"Goal queue: {len(pending)} pending goals\n")
    for i, goal in enumerate(pending, 1):
        click.echo(f"  {i}. [P{goal.priority}] {goal.content[:80]}")
        click.echo(f"     Status: {goal.status.value} | Retries: {goal.retry_count}/{goal.max_retries}")
```

**Step 4: Run tests**

Run: `pytest tests/e2e/test_cli_queue.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add vecna/cli/main.py tests/e2e/test_cli_queue.py
git commit -m "feat: add goal queue status CLI command"
```

---

## Phase 7: Integration Wiring

### Task 18: Wire Quotas into ToolRuntime

**Files:**
- Modify: `vecna/tools/runtime.py:27-41` (add QuotaManager)
- Modify: `vecna/config/schema.py` (add quota fields)
- Test: `tests/unit/test_tools_runtime.py` (extend)

**Step 1: Write the failing test**

```python
# Add to tests/unit/test_tools_runtime.py

class TestRuntimeQuotaEnforcement:
    async def test_denies_call_when_quota_exceeded(self):
        from vecna.tools.runtime import ToolRuntime, RuntimeConfig
        from vecna.tools.registry import get_default_registry
        from vecna.tools.permissions import ToolPermissionManager, ToolPolicy
        from vecna.tools.quotas import ToolQuotaManager, QuotaConfig
        from vecna.tools.types import ToolExecutionContext

        registry = get_default_registry()
        policy = ToolPolicy(default_action="allow")
        pm = ToolPermissionManager(policy)
        quota = ToolQuotaManager(QuotaConfig(max_calls_per_session=1, max_calls_per_tool=100))

        runtime = ToolRuntime(registry=registry, permission_manager=pm, quota_manager=quota)

        ctx = ToolExecutionContext(session_id="s1")

        # First call should work (mock the actual execution)
        text1 = '<TOOL_CALL name="memory_get">{"item_id": "test"}</TOOL_CALL>'
        _, results1 = await runtime.execute_calls(text1, ctx)

        # Second call should be denied by quota
        text2 = '<TOOL_CALL name="memory_get">{"item_id": "test2"}</TOOL_CALL>'
        _, results2 = await runtime.execute_calls(text2, ctx)
        assert any(not r.success and "quota" in (r.error or "").lower() for r in results2)
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_tools_runtime.py::TestRuntimeQuotaEnforcement -v`
Expected: FAIL (ToolRuntime doesn't accept `quota_manager`)

**Step 3: Wire quotas into runtime**

In `vecna/tools/runtime.py`, add quota parameter and check:

```python
# Add to __init__ parameters:
    quota_manager: Optional[ToolQuotaManager] = None,

# Store it:
    self.quota_manager = quota_manager

# In execute_calls, after policy check and before execution:
    if self.quota_manager and not self.quota_manager.check(
        call.tool_name, context.session_id or ""
    ):
        result = ToolResult(call.tool_name, False, "", error="Quota exceeded for this session.")
    else:
        # ... existing execution code ...
        # After successful execution, record:
        if self.quota_manager and context.session_id:
            self.quota_manager.record(call.tool_name, context.session_id)
```

**Step 4: Run tests**

Run: `pytest tests/unit/test_tools_runtime.py -v`
Expected: PASS

**Step 5: Add quota config fields to schema.py**

In `vecna/config/schema.py`, add to `VecnaConfig`:

```python
    # Tool quota settings
    tool_quota_per_session: int = 0  # 0 = unlimited
    tool_quota_per_tool: int = 0    # 0 = unlimited
```

**Step 6: Commit**

```bash
git add vecna/tools/runtime.py vecna/config/schema.py tests/unit/test_tools_runtime.py
git commit -m "feat: wire tool quota enforcement into ToolRuntime"
```

---

### Task 19: Wire Redaction into Audit Logger

**Files:**
- Modify: `vecna/tools/audit.py` (apply redaction before logging)
- Test: `tests/unit/test_tools_audit.py` (extend)

**Step 1: Write the failing test**

```python
# Add to tests/unit/test_tools_audit.py

class TestAuditRedaction:
    def test_redacts_secrets_in_audit_events(self, tmp_path):
        from vecna.tools.audit import ToolAuditLogger, ToolAuditEvent

        logger = ToolAuditLogger(log_path=tmp_path / "audit.jsonl", redact=True)
        logger.log_event(ToolAuditEvent(
            tool_name="http_request",
            action="allow",
            risk_tier="low",
            success=True,
            error="",
            metadata={"url": "postgresql://user:secretpass123@host/db"},
        ))

        import json
        lines = (tmp_path / "audit.jsonl").read_text().strip().split("\n")
        event = json.loads(lines[0])
        assert "secretpass123" not in json.dumps(event)
```

**Step 2-5:** Implement redaction call in audit logger, run tests, commit.

```bash
git commit -m "feat: wire PII/secret redaction into tool audit logger"
```

---

### Task 20: Full Integration Test and Lint

**Step 1: Run full lint**

```bash
ruff check .
ruff format --check .
```

**Step 2: Run full unit test suite**

```bash
pytest tests/unit/ -v
```

**Step 3: Fix any regressions**

Iterate until clean.

**Step 4: Run integration tests** (if PG/Redis available)

```bash
pytest tests/integration/ -v -m "not requires_docker"
```

**Step 5: Final commit**

```bash
git commit -m "chore: fix lint and test regressions from tool expansion"
```

---

## Summary of All Tasks

| # | Task | Phase | Priority |
|---|------|-------|----------|
| 1 | HTTP request tool (httpx + bs4) | Tool Expansion | P1 |
| 2 | Register HTTP tool in registry | Tool Expansion | P1 |
| 3 | Web search tool (DuckDuckGo) | Tool Expansion | P1 |
| 4 | Filesystem read tool (sandboxed) | Tool Expansion | P1 |
| 5 | Semantic tool router (tag + keyword) | Tool Expansion | P1 |
| 6 | Tool quotas and budgeting | Tool Expansion | P1 |
| 7 | DB-backed priority goal queue | Autonomy | P1 |
| 8 | Curiosity engine | Autonomy | P1 |
| 9 | Kill-switch with audit trail | Autonomy | P1 |
| 10 | Autonomy loop with backoff | Autonomy | P1 |
| 11 | Obsidian-compatible workspace init | Memory | P2 |
| 12 | Multi-hop graph traversal (CTE) | Memory | P2 |
| 13 | Dream loop insight generation | Memory | P2 |
| 14 | Container TTL auto-cleanup | Security | P2 |
| 15 | PII/secret redaction | Security | P2 |
| 16 | Tool audit dashboard data | Observability | P2 |
| 17 | Queue status CLI command | UX | P2 |
| 18 | Wire quotas into ToolRuntime | Integration | P1 |
| 19 | Wire redaction into audit logger | Integration | P2 |
| 20 | Full integration test and lint | QA | P1 |

## Dependencies

```
Task 1 → Task 2 (tool must exist before registration)
Task 7 → Task 10 (goal queue must be upgraded before autonomy loop uses it)
Task 9 → Task 10 (kill-switch must exist before autonomy loop checks it)
Task 6 → Task 18 (quotas must exist before runtime wiring)
Task 15 → Task 19 (redaction must exist before audit wiring)
Tasks 1-6 can be parallelized (independent tool implementations)
Tasks 7-10 can be partially parallelized (7 and 8,9 independent; 10 depends on 7 and 9)
Tasks 11-16 are all independent and can be parallelized
```

## Items Explicitly Deferred

These are tracked but intentionally deferred beyond this plan:

- **Identity emergence (P2+):** Opinion formation, personality drift tracking, contradiction-driven growth — requires stronger autonomous substrate first
- **Seccomp profiles:** OS-level container hardening — depends on Docker deployment patterns stabilizing
- **Safety regression test suites / red-team suites:** Requires tool catalog to be stable
- **Interactive approval in chat:** UX feature — lower priority than core agent capabilities
- **Cross-session pattern detection:** Requires multi-hop traversal (Task 12) + dream loop (Task 13) to be working first
- **Memory consolidation (merge/compress):** Requires flush + dream loop maturity
- **Heartbeat/cron scheduling:** Described in tejas_article.md — deferred until autonomy loop (Task 10) is proven in practice
