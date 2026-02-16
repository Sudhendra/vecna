"""Unit tests for HTTP request tool."""

import asyncio

import aiohttp

from vecna.tools.types import ToolExecutionContext


class _FakeResponse:
    def __init__(
        self,
        body: str,
        content_type: str = "text/plain",
        status: int = 200,
        headers: dict[str, str] | None = None,
    ):
        self._body = body
        self.status = status
        merged_headers = {"Content-Type": content_type}
        if headers:
            merged_headers.update(headers)
        self.headers = merged_headers

    async def text(self, errors: str = "ignore") -> str:
        return self._body

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _FakeSession:
    def __init__(self, response: _FakeResponse | Exception):
        self._response = response

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    def get(self, url: str, **kwargs):
        del kwargs
        if isinstance(self._response, Exception):
            raise self._response
        return self._response


async def test_blocks_private_network_targets(monkeypatch):
    from vecna.tools.http_tool import http_request_executor

    def fake_getaddrinfo(*args, **kwargs):
        return [(2, 1, 6, "", ("127.0.0.1", 80))]

    monkeypatch.setattr("socket.getaddrinfo", fake_getaddrinfo)

    result = await http_request_executor(
        {"url": "http://localhost:8080/test"},
        ToolExecutionContext(),
    )

    assert result.success is False
    assert result.error is not None
    assert "private" in result.error.lower() or "blocked" in result.error.lower()


async def test_invalid_scheme_rejected():
    from vecna.tools.http_tool import http_request_executor

    result = await http_request_executor(
        {"url": "file:///etc/passwd"},
        ToolExecutionContext(),
    )

    assert result.success is False
    assert result.error is not None
    assert "scheme" in result.error.lower()


async def test_extracts_visible_text_from_html(monkeypatch):
    from vecna.tools.http_tool import http_request_executor

    html = (
        "<html><head><style>.x{display:none}</style><script>alert('x')</script></head>"
        "<body><h1>Hello</h1><p>World</p></body></html>"
    )

    def fake_getaddrinfo(*args, **kwargs):
        return [(2, 1, 6, "", ("93.184.216.34", 80))]

    monkeypatch.setattr("socket.getaddrinfo", fake_getaddrinfo)
    monkeypatch.setattr(
        "aiohttp.ClientSession",
        lambda *args, **kwargs: _FakeSession(_FakeResponse(html, content_type="text/html")),
    )

    result = await http_request_executor(
        {"url": "https://example.com"},
        ToolExecutionContext(),
    )

    assert result.success is True
    assert "Hello" in result.output
    assert "World" in result.output
    assert "alert" not in result.output
    assert "display:none" not in result.output


async def test_non_html_returns_text_body(monkeypatch):
    from vecna.tools.http_tool import http_request_executor

    def fake_getaddrinfo(*args, **kwargs):
        return [(2, 1, 6, "", ("93.184.216.34", 80))]

    monkeypatch.setattr("socket.getaddrinfo", fake_getaddrinfo)
    monkeypatch.setattr(
        "aiohttp.ClientSession",
        lambda *args, **kwargs: _FakeSession(
            _FakeResponse("plain text body", content_type="text/plain")
        ),
    )

    result = await http_request_executor(
        {"url": "https://example.com/plain"},
        ToolExecutionContext(),
    )

    assert result.success is True
    assert result.output == "plain text body"


async def test_timeout_and_http_errors_handled_as_failure(monkeypatch):
    from vecna.tools.http_tool import http_request_executor

    def fake_getaddrinfo(*args, **kwargs):
        return [(2, 1, 6, "", ("93.184.216.34", 80))]

    monkeypatch.setattr("socket.getaddrinfo", fake_getaddrinfo)

    for exc in [asyncio.TimeoutError(), aiohttp.ClientError("boom")]:
        monkeypatch.setattr(
            "aiohttp.ClientSession",
            lambda *args, **kwargs: _FakeSession(exc),
        )
        result = await http_request_executor(
            {"url": "https://example.com"},
            ToolExecutionContext(),
        )
        assert result.success is False
        assert result.error is not None


async def test_redirect_responses_are_blocked(monkeypatch):
    from vecna.tools.http_tool import http_request_executor

    def fake_getaddrinfo(*args, **kwargs):
        return [(2, 1, 6, "", ("93.184.216.34", 80))]

    monkeypatch.setattr("socket.getaddrinfo", fake_getaddrinfo)
    monkeypatch.setattr(
        "aiohttp.ClientSession",
        lambda *args, **kwargs: _FakeSession(
            _FakeResponse(
                "",
                status=302,
                headers={"Location": "http://example.org/next"},
            )
        ),
    )

    result = await http_request_executor(
        {"url": "https://example.com/redirect"},
        ToolExecutionContext(),
    )

    assert result.success is False
    assert result.error is not None
    assert "redirect" in result.error.lower()


async def test_invalid_timeout_returns_failure(monkeypatch):
    from vecna.tools.http_tool import http_request_executor

    dns_called = False

    def fake_getaddrinfo(*args, **kwargs):
        nonlocal dns_called
        dns_called = True
        return [(2, 1, 6, "", ("93.184.216.34", 80))]

    monkeypatch.setattr("socket.getaddrinfo", fake_getaddrinfo)

    result = await http_request_executor(
        {"url": "https://example.com", "timeout": "abc"},
        ToolExecutionContext(),
    )

    assert result.success is False
    assert result.error is not None
    assert "timeout" in result.error.lower()
    assert dns_called is False
