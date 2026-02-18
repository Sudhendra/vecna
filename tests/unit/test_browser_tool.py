"""Tests for the Playwright-based browser automation tool."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from vecna.tools.browser_tool import (
    BrowserTool,
    BrowserConfig,
    BrowserResult,
    PageContent,
    BROWSER_NAVIGATE_SPEC,
    BROWSER_SCREENSHOT_SPEC,
    BROWSER_CLICK_SPEC,
    browser_navigate_executor,
    browser_screenshot_executor,
    browser_click_executor,
)
from vecna.tools.types import ToolResult, ToolExecutionContext


class TestBrowserConfig:
    def test_default_config(self):
        config = BrowserConfig()
        assert config.headless is True
        assert config.timeout == 30.0
        assert config.max_content_length == 50000
        # Amendment 9: assert specific substring, not just existence
        assert "Vecna" in config.user_agent
        assert "Mozilla" in config.user_agent
        assert config.viewport_width == 1280
        assert config.viewport_height == 720

    def test_custom_config(self):
        config = BrowserConfig(headless=False, timeout=60.0, max_content_length=10000)
        assert config.headless is False
        assert config.timeout == 60.0
        assert config.max_content_length == 10000
        # Unmodified defaults preserved
        assert config.viewport_width == 1280


class TestBrowserToolSpecs:
    def test_navigate_spec_name(self):
        assert BROWSER_NAVIGATE_SPEC.name == "browser_navigate"

    def test_navigate_spec_schema_has_url(self):
        assert "url" in BROWSER_NAVIGATE_SPEC.input_schema

    def test_navigate_spec_tags(self):
        assert "browser" in BROWSER_NAVIGATE_SPEC.tags
        assert "web" in BROWSER_NAVIGATE_SPEC.tags

    def test_navigate_spec_description(self):
        assert "navigate" in BROWSER_NAVIGATE_SPEC.description.lower()

    def test_screenshot_spec_name(self):
        assert BROWSER_SCREENSHOT_SPEC.name == "browser_screenshot"

    def test_screenshot_spec_schema_has_url(self):
        assert "url" in BROWSER_SCREENSHOT_SPEC.input_schema

    def test_screenshot_spec_tags(self):
        assert "browser" in BROWSER_SCREENSHOT_SPEC.tags
        assert "screenshot" in BROWSER_SCREENSHOT_SPEC.tags

    def test_click_spec_name(self):
        assert BROWSER_CLICK_SPEC.name == "browser_click"

    def test_click_spec_schema_has_selector(self):
        assert "selector" in BROWSER_CLICK_SPEC.input_schema

    def test_click_spec_tags(self):
        assert "browser" in BROWSER_CLICK_SPEC.tags
        assert "interact" in BROWSER_CLICK_SPEC.tags


class TestPageContent:
    def test_page_content_creation(self):
        content = PageContent(
            url="https://example.com",
            title="Example",
            text="Hello world",
            html="<html><body>Hello world</body></html>",
        )
        assert content.url == "https://example.com"
        assert content.title == "Example"
        assert content.text == "Hello world"
        assert content.html == "<html><body>Hello world</body></html>"

    def test_page_content_to_dict_fields(self):
        content = PageContent(
            url="https://example.com",
            title="Example",
            text="Hello",
            html="<p>Hello</p>",
        )
        d = content.to_dict()
        assert d["url"] == "https://example.com"
        assert d["title"] == "Example"
        assert d["text"] == "Hello"
        assert d["html"] == "<p>Hello</p>"

    def test_page_content_truncation(self):
        long_text = "A" * 100000
        content = PageContent(
            url="https://example.com",
            title="Long Page",
            text=long_text,
        )
        truncated = content.truncated_text(max_length=1000)
        assert len(truncated) <= 1000
        assert truncated.endswith("... [truncated]")
        # Amendment 9: verify the prefix is from the original text
        assert truncated.startswith("AAAA")

    def test_page_content_no_truncation_when_short(self):
        content = PageContent(
            url="https://example.com",
            title="Short",
            text="Brief text",
        )
        result = content.truncated_text(max_length=1000)
        assert result == "Brief text"

    def test_page_content_default_values(self):
        content = PageContent(url="https://example.com")
        assert content.title == ""
        assert content.text == ""
        assert content.html == ""
        assert content.metadata == {}


class TestBrowserResult:
    def test_success_result(self):
        page = PageContent(url="https://example.com", title="Example", text="Hi")
        result = BrowserResult(
            success=True,
            action="navigate",
            url="https://example.com",
            content=page,
        )
        assert result.success is True
        assert result.action == "navigate"
        assert result.url == "https://example.com"
        assert result.content.title == "Example"

    def test_error_result(self):
        result = BrowserResult(
            success=False,
            action="navigate",
            url="https://example.com",
            error="Connection refused",
        )
        assert result.success is False
        assert result.error == "Connection refused"
        assert result.content is None

    def test_to_dict_success(self):
        page = PageContent(url="https://example.com", title="Ex", text="Hello")
        result = BrowserResult(
            success=True,
            action="navigate",
            url="https://example.com",
            content=page,
        )
        d = result.to_dict()
        assert d["success"] is True
        assert d["action"] == "navigate"
        assert d["url"] == "https://example.com"
        # Content is serialized via SerializableMixin as nested dict
        assert d["content"]["url"] == "https://example.com"

    def test_to_dict_error(self):
        result = BrowserResult(
            success=False,
            action="screenshot",
            url="https://example.com",
            error="Timeout",
        )
        d = result.to_dict()
        assert d["success"] is False
        assert d["error"] == "Timeout"
        assert d["content"] is None

    def test_screenshot_result_has_b64(self):
        result = BrowserResult(
            success=True,
            action="screenshot",
            url="https://example.com",
            screenshot_b64="iVBORw0KGgo=",
        )
        assert result.screenshot_b64 == "iVBORw0KGgo="


class TestBrowserToolLifecycle:
    def test_tool_creation_default_config(self):
        tool = BrowserTool()
        assert tool.config.headless is True
        assert tool.config.timeout == 30.0
        assert tool.is_running is False

    def test_tool_creation_custom_config(self):
        config = BrowserConfig(headless=False, timeout=60.0)
        tool = BrowserTool(config=config)
        assert tool.config.headless is False
        assert tool.config.timeout == 60.0

    async def test_stop_sets_not_running(self):
        """Stop should set is_running to False and clean up."""
        tool = BrowserTool()
        # Simulate started state via the public setter
        tool.is_running = True
        mock_browser = AsyncMock()
        mock_pw_ctx = MagicMock()
        mock_pw_ctx.__aexit__ = AsyncMock(return_value=False)
        # Use the set_browser/set_context helpers to inject mocks
        tool.set_browser(mock_browser)
        tool.set_playwright_context(mock_pw_ctx)

        await tool.stop()
        assert tool.is_running is False

    async def test_start_failure_when_playwright_missing(self):
        """Error path: playwright is not installed."""
        tool = BrowserTool()
        with patch(
            "vecna.tools.browser_tool.async_playwright",
            side_effect=None,
        ) as mock_pw:
            # Simulate ImportError at the point of use
            mock_pw.side_effect = ImportError("No module named 'playwright'")
            with pytest.raises(RuntimeError, match="[Pp]laywright"):
                await tool.start()


class TestBrowserToolNavigation:
    def _make_running_tool(self) -> tuple:
        """Create a BrowserTool with mocked browser in running state."""
        tool = BrowserTool()
        mock_page = AsyncMock()
        mock_page.title.return_value = "Example Page"
        mock_page.url = "https://example.com"
        mock_page.content.return_value = "<html><body>Hello</body></html>"
        mock_page.inner_text.return_value = "Hello"
        mock_page.close = AsyncMock()

        mock_browser = AsyncMock()
        mock_browser.new_page.return_value = mock_page
        tool.set_browser(mock_browser)
        tool.is_running = True
        return tool, mock_page, mock_browser

    async def test_navigate_returns_page_content(self):
        tool, mock_page, _ = self._make_running_tool()

        result = await tool.navigate("https://example.com")
        assert result.success is True
        assert result.content is not None
        assert result.content.title == "Example Page"
        assert result.content.url == "https://example.com"
        assert "Hello" in result.content.text

    async def test_navigate_handles_timeout(self):
        """Error path: page.goto raises a timeout error."""
        tool = BrowserTool(config=BrowserConfig(timeout=1.0))
        mock_page = AsyncMock()
        mock_page.goto.side_effect = TimeoutError("Navigation timeout exceeded")
        mock_page.close = AsyncMock()

        mock_browser = AsyncMock()
        mock_browser.new_page.return_value = mock_page
        tool.set_browser(mock_browser)
        tool.is_running = True

        result = await tool.navigate("https://slow-site.example.com")
        assert result.success is False
        assert "timeout" in result.error.lower()

    async def test_navigate_fails_when_not_running(self):
        """Error path: browser not started."""
        tool = BrowserTool()
        result = await tool.navigate("https://example.com")
        assert result.success is False
        assert "not running" in result.error.lower()

    async def test_navigate_handles_connection_error(self):
        """Error path: network connection fails."""
        tool = BrowserTool()
        mock_page = AsyncMock()
        mock_page.goto.side_effect = ConnectionError("Connection refused")
        mock_page.close = AsyncMock()

        mock_browser = AsyncMock()
        mock_browser.new_page.return_value = mock_page
        tool.set_browser(mock_browser)
        tool.is_running = True

        result = await tool.navigate("https://unreachable.example.com")
        assert result.success is False
        assert result.error != ""

    async def test_navigate_truncates_long_content(self):
        """Edge case: page text exceeds max_content_length."""
        config = BrowserConfig(max_content_length=100)
        tool = BrowserTool(config=config)
        long_text = "X" * 500
        mock_page = AsyncMock()
        mock_page.title.return_value = "Long Page"
        mock_page.url = "https://example.com/long"
        mock_page.content.return_value = "<html><body>" + long_text + "</body></html>"
        mock_page.inner_text.return_value = long_text

        mock_browser = AsyncMock()
        mock_browser.new_page.return_value = mock_page
        tool.set_browser(mock_browser)
        tool.is_running = True

        result = await tool.navigate("https://example.com/long")
        assert result.success is True
        assert len(result.content.text) <= 115  # 100 + "... [truncated]"
        assert result.content.text.endswith("... [truncated]")


class TestBrowserToolScreenshot:
    async def test_screenshot_returns_base64(self):
        tool = BrowserTool()
        fake_png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
        mock_page = AsyncMock()
        mock_page.goto.return_value = None
        mock_page.screenshot.return_value = fake_png
        mock_page.close = AsyncMock()

        mock_browser = AsyncMock()
        mock_browser.new_page.return_value = mock_page
        tool.set_browser(mock_browser)
        tool.is_running = True

        result = await tool.screenshot("https://example.com")
        assert result.success is True
        assert result.screenshot_b64 is not None
        assert len(result.screenshot_b64) > 0

    async def test_screenshot_fails_when_not_running(self):
        """Error path: browser not started."""
        tool = BrowserTool()
        result = await tool.screenshot("https://example.com")
        assert result.success is False
        assert "not running" in result.error.lower()

    async def test_screenshot_handles_error(self):
        """Error path: screenshot operation fails."""
        tool = BrowserTool()
        mock_page = AsyncMock()
        mock_page.goto.side_effect = TimeoutError("Page load timeout")
        mock_page.close = AsyncMock()

        mock_browser = AsyncMock()
        mock_browser.new_page.return_value = mock_page
        tool.set_browser(mock_browser)
        tool.is_running = True

        result = await tool.screenshot("https://slow-site.example.com")
        assert result.success is False
        assert result.error != ""


class TestBrowserToolClick:
    async def test_click_element(self):
        tool = BrowserTool()
        mock_page = AsyncMock()
        mock_page.click.return_value = None
        mock_page.url = "https://example.com/after-click"
        mock_page.title.return_value = "After Click"
        mock_page.content.return_value = "<html><body>Clicked</body></html>"
        mock_page.inner_text.return_value = "Clicked"

        tool.set_current_page(mock_page)
        tool.is_running = True

        result = await tool.click("button#submit")
        assert result.success is True
        assert result.content.title == "After Click"
        assert result.content.url == "https://example.com/after-click"

    async def test_click_fails_when_no_page_loaded(self):
        """Error path: no page loaded before click."""
        tool = BrowserTool()
        tool.is_running = True
        result = await tool.click("button#submit")
        assert result.success is False
        assert "no page" in result.error.lower()

    async def test_click_handles_element_not_found(self):
        """Error path: CSS selector doesn't match any element."""
        tool = BrowserTool()
        mock_page = AsyncMock()
        mock_page.click.side_effect = TimeoutError("Element not found: #nonexistent")
        tool.set_current_page(mock_page)
        tool.is_running = True

        result = await tool.click("#nonexistent")
        assert result.success is False
        assert result.error != ""


class TestBrowserNavigateExecutor:
    async def test_navigate_executor_success(self):
        ctx = ToolExecutionContext(session_id="test")
        mock_result = BrowserResult(
            success=True,
            action="navigate",
            url="https://example.com",
            content=PageContent(
                url="https://example.com",
                title="Test Page",
                text="Content here",
            ),
        )

        with patch(
            "vecna.tools.browser_tool._get_browser_tool",
        ) as mock_get:
            mock_tool = AsyncMock()
            mock_tool.navigate.return_value = mock_result
            mock_tool.is_running = True
            mock_get.return_value = mock_tool

            result = await browser_navigate_executor({"url": "https://example.com"}, ctx)
            assert isinstance(result, ToolResult)
            assert result.success is True
            assert result.tool_name == "browser_navigate"
            assert "Test Page" in result.output
            assert "Content here" in result.output

    async def test_navigate_executor_missing_url(self):
        """Error path: missing required url parameter."""
        ctx = ToolExecutionContext()
        result = await browser_navigate_executor({}, ctx)
        assert result.success is False
        assert "url" in result.error.lower()
        assert result.tool_name == "browser_navigate"

    async def test_navigate_executor_empty_url(self):
        """Error path: empty url string."""
        ctx = ToolExecutionContext()
        result = await browser_navigate_executor({"url": ""}, ctx)
        assert result.success is False
        assert "url" in result.error.lower()

    async def test_navigate_executor_propagates_error(self):
        """Error from tool propagates to ToolResult."""
        ctx = ToolExecutionContext(session_id="test")
        mock_result = BrowserResult(
            success=False,
            action="navigate",
            url="https://example.com",
            error="Connection refused",
        )

        with patch(
            "vecna.tools.browser_tool._get_browser_tool",
        ) as mock_get:
            mock_tool = AsyncMock()
            mock_tool.navigate.return_value = mock_result
            mock_tool.is_running = True
            mock_get.return_value = mock_tool

            result = await browser_navigate_executor({"url": "https://example.com"}, ctx)
            assert result.success is False
            assert "Connection refused" in result.error


class TestBrowserScreenshotExecutor:
    async def test_screenshot_executor_success(self):
        ctx = ToolExecutionContext(session_id="test")
        mock_result = BrowserResult(
            success=True,
            action="screenshot",
            url="https://example.com",
            screenshot_b64="iVBORw0KGgo=",
        )

        with patch(
            "vecna.tools.browser_tool._get_browser_tool",
        ) as mock_get:
            mock_tool = AsyncMock()
            mock_tool.screenshot.return_value = mock_result
            mock_tool.is_running = True
            mock_get.return_value = mock_tool

            result = await browser_screenshot_executor({"url": "https://example.com"}, ctx)
            assert result.success is True
            assert result.tool_name == "browser_screenshot"
            assert "screenshot" in result.output.lower()

    async def test_screenshot_executor_missing_url(self):
        """Error path: missing required url parameter."""
        ctx = ToolExecutionContext()
        result = await browser_screenshot_executor({}, ctx)
        assert result.success is False
        assert "url" in result.error.lower()


class TestBrowserClickExecutor:
    async def test_click_executor_success(self):
        ctx = ToolExecutionContext(session_id="test")
        mock_result = BrowserResult(
            success=True,
            action="click",
            url="https://example.com/clicked",
            content=PageContent(
                url="https://example.com/clicked",
                title="Clicked",
                text="After click content",
            ),
        )

        with patch(
            "vecna.tools.browser_tool._get_browser_tool",
        ) as mock_get:
            mock_tool = AsyncMock()
            mock_tool.click.return_value = mock_result
            mock_get.return_value = mock_tool

            result = await browser_click_executor({"selector": "button#go"}, ctx)
            assert result.success is True
            assert result.tool_name == "browser_click"
            assert "After click content" in result.output

    async def test_click_executor_missing_selector(self):
        """Error path: missing required selector parameter."""
        ctx = ToolExecutionContext()
        result = await browser_click_executor({}, ctx)
        assert result.success is False
        assert "selector" in result.error.lower()

    async def test_click_executor_empty_selector(self):
        """Error path: empty selector string."""
        ctx = ToolExecutionContext()
        result = await browser_click_executor({"selector": ""}, ctx)
        assert result.success is False
        assert "selector" in result.error.lower()
