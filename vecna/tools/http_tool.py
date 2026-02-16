"""HTTP request tool with SSRF guardrails and safe output handling."""

import asyncio
from html.parser import HTMLParser
import ipaddress
import math
import socket
from typing import Any, Dict, List
from urllib.parse import urlparse

import aiohttp
from aiohttp.abc import AbstractResolver

from vecna.tools.types import ToolExecutionContext, ToolResult

ALLOWED_SCHEMES = {"http", "https"}
MAX_OUTPUT_CHARS = 8000
DEFAULT_TIMEOUT_SECONDS = 10
MIN_TIMEOUT_SECONDS = 1
MAX_TIMEOUT_SECONDS = 120


def _is_disallowed_ip(ip_text: str) -> bool:
    ip = ipaddress.ip_address(ip_text)
    return any(
        [
            ip.is_private,
            ip.is_loopback,
            ip.is_link_local,
            ip.is_reserved,
            ip.is_multicast,
            ip.is_unspecified,
        ]
    )


def _resolve_host_ips(hostname: str, port: int) -> List[str]:
    resolved = socket.getaddrinfo(hostname, port, type=socket.SOCK_STREAM)
    ips = []
    for entry in resolved:
        sockaddr = entry[4]
        if not sockaddr:
            continue
        ips.append(sockaddr[0])
    return ips


class _PinnedResolver(AbstractResolver):
    def __init__(self, hostname: str, records: List[tuple[Any, ...]]) -> None:
        self._hostname = hostname
        self._resolved = []
        for family, _, proto, _, sockaddr in records:
            if not sockaddr:
                continue
            self._resolved.append(
                {
                    "hostname": hostname,
                    "host": sockaddr[0],
                    "port": sockaddr[1],
                    "family": family,
                    "proto": proto,
                    "flags": 0,
                }
            )

    async def resolve(self, host: str, port: int = 0, family: int = socket.AF_INET):
        del port, family
        if host != self._hostname:
            raise OSError("resolved host mismatch")
        return list(self._resolved)

    async def close(self) -> None:
        return None


def _parse_timeout_seconds(raw_timeout: Any) -> float:
    if raw_timeout is None:
        return float(DEFAULT_TIMEOUT_SECONDS)
    if isinstance(raw_timeout, bool):
        raise ValueError("timeout must be numeric")
    try:
        timeout = float(raw_timeout)
    except (TypeError, ValueError) as exc:
        raise ValueError("timeout must be numeric") from exc
    if not math.isfinite(timeout):
        raise ValueError("timeout must be finite")
    if timeout < MIN_TIMEOUT_SECONDS or timeout > MAX_TIMEOUT_SECONDS:
        raise ValueError(
            f"timeout must be between {MIN_TIMEOUT_SECONDS} and {MAX_TIMEOUT_SECONDS} seconds"
        )
    return timeout


def _extract_visible_text(body: str, content_type: str) -> str:
    if "html" not in content_type.lower():
        return body

    try:
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(body, "html.parser")
        for tag in soup(["script", "style"]):
            tag.decompose()
        return soup.get_text(separator=" ", strip=True)
    except ImportError:
        parser = _VisibleHTMLTextParser()
        parser.feed(body)
        parser.close()
        return " ".join(text for text in parser.text_chunks if text).strip()


class _VisibleHTMLTextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._drop_depth = 0
        self.text_chunks: List[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:  # type: ignore[override]
        del attrs
        if tag in {"script", "style"}:
            self._drop_depth += 1

    def handle_endtag(self, tag: str) -> None:  # type: ignore[override]
        if tag in {"script", "style"} and self._drop_depth > 0:
            self._drop_depth -= 1

    def handle_data(self, data: str) -> None:
        if self._drop_depth == 0:
            cleaned = data.strip()
            if cleaned:
                self.text_chunks.append(cleaned)


def _truncate(text: str, limit: int = MAX_OUTPUT_CHARS) -> str:
    if len(text) <= limit:
        return text
    return text[:limit]


async def http_request_executor(args: Dict[str, Any], context: ToolExecutionContext) -> ToolResult:
    del context

    url = str(args.get("url", "")).strip()
    try:
        timeout_seconds = _parse_timeout_seconds(args.get("timeout", DEFAULT_TIMEOUT_SECONDS))
    except ValueError as exc:
        return ToolResult(
            tool_name="http_request",
            success=False,
            output="",
            error=f"invalid timeout: {exc}",
        )

    parsed = urlparse(url)
    if parsed.scheme.lower() not in ALLOWED_SCHEMES:
        return ToolResult(
            tool_name="http_request",
            success=False,
            output="",
            error="invalid URL scheme; only http and https are allowed",
        )

    if not parsed.hostname:
        return ToolResult(
            tool_name="http_request",
            success=False,
            output="",
            error="invalid URL: missing host",
        )

    port = parsed.port or (443 if parsed.scheme.lower() == "https" else 80)
    try:
        resolved = socket.getaddrinfo(parsed.hostname, port, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        return ToolResult(
            tool_name="http_request",
            success=False,
            output="",
            error=f"DNS resolution failed: {exc}",
        )

    ips = []
    for entry in resolved:
        sockaddr = entry[4]
        if not sockaddr:
            continue
        ips.append(sockaddr[0])

    if not ips:
        return ToolResult(
            tool_name="http_request",
            success=False,
            output="",
            error="DNS resolution returned no addresses",
        )

    for ip in ips:
        if _is_disallowed_ip(ip):
            return ToolResult(
                tool_name="http_request",
                success=False,
                output="",
                error="request blocked: target resolves to private/reserved address",
            )

    timeout = aiohttp.ClientTimeout(total=timeout_seconds)
    resolver = _PinnedResolver(parsed.hostname, resolved)
    connector = aiohttp.TCPConnector(resolver=resolver)
    try:
        async with aiohttp.ClientSession(timeout=timeout, connector=connector) as session:
            async with session.get(url, allow_redirects=False) as response:
                if 300 <= response.status < 400:
                    location = response.headers.get("Location", "")
                    location_suffix = f" to {location}" if location else ""
                    return ToolResult(
                        tool_name="http_request",
                        success=False,
                        output="",
                        error=(
                            f"request blocked: redirect responses are not allowed{location_suffix}"
                        ),
                        metadata={"status": response.status},
                    )
                if response.status >= 400:
                    return ToolResult(
                        tool_name="http_request",
                        success=False,
                        output="",
                        error=f"HTTP error: status {response.status}",
                        metadata={"status": response.status},
                    )
                body = await response.text(errors="ignore")
                content_type = response.headers.get("Content-Type", "")
    except asyncio.TimeoutError:
        return ToolResult(
            tool_name="http_request",
            success=False,
            output="",
            error="request timed out",
        )
    except aiohttp.ClientError as exc:
        return ToolResult(
            tool_name="http_request",
            success=False,
            output="",
            error=f"HTTP request failed: {exc}",
        )

    text = _extract_visible_text(body, content_type)
    return ToolResult(
        tool_name="http_request",
        success=True,
        output=_truncate(text),
        metadata={"url": url, "content_type": content_type},
    )
