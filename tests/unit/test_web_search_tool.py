"""Unit tests for web search tool."""

import asyncio
from typing import Any, Dict, Optional, Union

import aiohttp
import pytest

from vecna.tools.types import ToolExecutionContext


class _FakeResponse:
    def __init__(self, body: str, status: int = 200):
        self._body = body
        self.status = status

    async def text(self, errors: str = "ignore") -> str:
        return self._body

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _ExplodingResponse(_FakeResponse):
    async def text(self, errors: str = "ignore") -> str:
        raise RuntimeError("parser exploded")


class _FakeSession:
    def __init__(
        self,
        response: Union[_FakeResponse, Exception],
        recorder: Optional[Dict[str, Any]] = None,
    ):
        self._response = response
        self._recorder = recorder if recorder is not None else {}

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    def get(self, url: str, **kwargs):
        self._recorder["url"] = url
        self._recorder["kwargs"] = kwargs
        if isinstance(self._response, Exception):
            raise self._response
        return self._response


async def test_empty_query_returns_failure():
    from vecna.tools.web_search_tool import web_search_executor

    result = await web_search_executor({"query": "   "}, ToolExecutionContext())

    assert result.success is False
    assert result.error is not None
    assert "query" in result.error.lower()


async def test_no_results_returns_success_message(monkeypatch):
    pytest.importorskip("bs4")

    from vecna.tools.web_search_tool import web_search_executor

    monkeypatch.setattr(
        "aiohttp.ClientSession",
        lambda *args, **kwargs: _FakeSession(_FakeResponse("<html><body></body></html>")),
    )

    result = await web_search_executor({"query": "gibberish"}, ToolExecutionContext())

    assert result.success is True
    assert "no results" in result.output.lower()


async def test_parses_ddg_html_results(monkeypatch):
    pytest.importorskip("bs4")

    from vecna.tools.web_search_tool import web_search_executor

    recorder = {}
    html = """
    <html>
      <body>
        <div class="result">
          <a class="result__a" href="https://example.com/page">Example Title</a>
          <a class="result__snippet">Useful summary text.</a>
        </div>
      </body>
    </html>
    """

    monkeypatch.setattr(
        "aiohttp.ClientSession",
        lambda *args, **kwargs: _FakeSession(_FakeResponse(html), recorder=recorder),
    )

    result = await web_search_executor({"query": "example"}, ToolExecutionContext())

    assert result.success is True
    assert "Example Title" in result.output
    assert "https://example.com/page" in result.output
    assert "Useful summary text." in result.output
    assert "duckduckgo.com/html/" in recorder["url"]
    assert recorder["kwargs"]["params"]["q"] == "example"


async def test_network_errors_return_failure(monkeypatch):
    from vecna.tools.web_search_tool import web_search_executor

    for exc in [asyncio.TimeoutError(), aiohttp.ClientError("boom")]:
        monkeypatch.setattr(
            "aiohttp.ClientSession",
            lambda *args, **kwargs: _FakeSession(exc),
        )
        result = await web_search_executor({"query": "example"}, ToolExecutionContext())
        assert result.success is False
        assert result.error is not None
        assert "failed" in result.error.lower() or "timed out" in result.error.lower()


async def test_http_error_status_returns_failure(monkeypatch):
    from vecna.tools.web_search_tool import web_search_executor

    monkeypatch.setattr(
        "aiohttp.ClientSession",
        lambda *args, **kwargs: _FakeSession(_FakeResponse("<html></html>", status=503)),
    )

    result = await web_search_executor({"query": "example"}, ToolExecutionContext())

    assert result.success is False
    assert result.error == "search request failed with HTTP status 503"


async def test_unexpected_exception_returns_failure(monkeypatch):
    from vecna.tools.web_search_tool import web_search_executor

    monkeypatch.setattr(
        "aiohttp.ClientSession",
        lambda *args, **kwargs: _FakeSession(_ExplodingResponse("<html></html>")),
    )

    result = await web_search_executor({"query": "example"}, ToolExecutionContext())

    assert result.success is False
    assert result.error is not None
    assert "unexpected search error" in result.error
    assert "parser exploded" in result.error


async def test_missing_bs4_dependency_returns_failure(monkeypatch):
    import vecna.tools.web_search_tool as web_search_tool

    monkeypatch.setattr(web_search_tool, "BeautifulSoup", None)
    monkeypatch.setattr(
        "aiohttp.ClientSession",
        lambda *args, **kwargs: _FakeSession(_FakeResponse("<html><body></body></html>")),
    )

    result = await web_search_tool.web_search_executor({"query": "example"}, ToolExecutionContext())

    assert result.success is False
    assert result.error is not None
    assert "beautifulsoup4" in result.error.lower()


async def test_max_results_limits_result_count(monkeypatch):
    import vecna.tools.web_search_tool as web_search_tool

    html = """
    <html>
      <body>
        <div class="result">
          <a class="result__a" href="https://example.com/1">First</a>
          <a class="result__snippet">One</a>
        </div>
        <div class="result">
          <a class="result__a" href="https://example.com/2">Second</a>
          <a class="result__snippet">Two</a>
        </div>
      </body>
    </html>
    """

    def _fake_extract_results(raw_html, max_results=5):
        assert raw_html == html
        return [
            {"title": "First", "url": "https://example.com/1", "snippet": "One"},
            {"title": "Second", "url": "https://example.com/2", "snippet": "Two"},
        ][:max_results]

    monkeypatch.setattr(web_search_tool, "BeautifulSoup", object())
    monkeypatch.setattr(web_search_tool, "_extract_results", _fake_extract_results)
    monkeypatch.setattr(
        "aiohttp.ClientSession",
        lambda *args, **kwargs: _FakeSession(_FakeResponse(html)),
    )

    result = await web_search_tool.web_search_executor(
        {"query": "example", "max_results": 1},
        ToolExecutionContext(),
    )

    assert result.success is True
    assert "First" in result.output
    assert "Second" not in result.output
    assert result.metadata["result_count"] == 1
    assert result.metadata["max_results"] == 1


async def test_max_results_rejects_invalid_value(monkeypatch):
    import vecna.tools.web_search_tool as web_search_tool

    monkeypatch.setattr(
        "aiohttp.ClientSession",
        lambda *args, **kwargs: _FakeSession(_FakeResponse("<html><body></body></html>")),
    )

    result = await web_search_tool.web_search_executor(
        {"query": "example", "max_results": 0},
        ToolExecutionContext(),
    )

    assert result.success is False
    assert result.error == "max_results must be between 1 and 10"


async def test_max_results_applies_upper_bound_cap(monkeypatch):
    import vecna.tools.web_search_tool as web_search_tool

    observed = {"max_results": None}

    def _fake_extract_results(raw_html, max_results=5):
        observed["max_results"] = max_results
        return [{"title": "First", "url": "https://example.com/1", "snippet": "One"}]

    monkeypatch.setattr(web_search_tool, "BeautifulSoup", object())
    monkeypatch.setattr(web_search_tool, "_extract_results", _fake_extract_results)
    monkeypatch.setattr(
        "aiohttp.ClientSession",
        lambda *args, **kwargs: _FakeSession(_FakeResponse("<html><body></body></html>")),
    )

    result = await web_search_tool.web_search_executor(
        {"query": "example", "max_results": 999},
        ToolExecutionContext(),
    )

    assert result.success is True
    assert observed["max_results"] == 10
    assert result.metadata["max_results"] == 10
