"""
Playwright-based browser automation tool.

Provides browser navigation, screenshots, and element interaction
as registered Vecna tools. Runs headless by default.

Tool risk tier: HIGH — requires approval in autonomous mode.
"""

import base64
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from vecna.core.types import SerializableMixin
from vecna.tools.types import ToolExecutionContext, ToolResult, ToolSpec

logger = logging.getLogger("vecna.tools.browser_tool")

# Lazy import for playwright — it's an optional dependency.
# We defer the import to runtime so the module can be loaded
# even when playwright is not installed.
try:
    from playwright.async_api import Error as PlaywrightError
    from playwright.async_api import TimeoutError as PlaywrightTimeoutError
    from playwright.async_api import async_playwright
except ImportError:
    async_playwright = None  # type: ignore[assignment, misc]
    PlaywrightError = RuntimeError  # type: ignore[assignment]
    PlaywrightTimeoutError = TimeoutError  # type: ignore[assignment]


# -- Tool Specifications --

BROWSER_NAVIGATE_SPEC = ToolSpec(
    name="browser_navigate",
    description=(
        "Navigate to a URL and return the page content as text. "
        "Use for reading web pages, documentation, or any URL content."
    ),
    input_schema={
        "url": "string",
    },
    tags=["browser", "web", "navigate"],
)

BROWSER_SCREENSHOT_SPEC = ToolSpec(
    name="browser_screenshot",
    description=(
        "Take a screenshot of a URL and return as base64-encoded PNG. "
        "Use for visual inspection of web pages."
    ),
    input_schema={
        "url": "string",
    },
    tags=["browser", "web", "screenshot"],
)

BROWSER_CLICK_SPEC = ToolSpec(
    name="browser_click",
    description=(
        "Click an element on the current page by CSS selector. "
        "Must call browser_navigate first to load a page."
    ),
    input_schema={
        "selector": "string",
    },
    tags=["browser", "web", "interact"],
)


@dataclass
class BrowserConfig:
    """Configuration for the browser tool."""

    headless: bool = True
    timeout: float = 30.0
    max_content_length: int = 50000
    user_agent: str = (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36 Vecna/1.0"
    )
    viewport_width: int = 1280
    viewport_height: int = 720


@dataclass
class PageContent(SerializableMixin):
    """Extracted content from a web page."""

    url: str = ""
    title: str = ""
    text: str = ""
    html: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def truncated_text(self, max_length: int = 50000) -> str:
        """Return text truncated to max_length."""
        if len(self.text) <= max_length:
            return self.text
        return self.text[: max_length - 15] + "... [truncated]"


@dataclass
class BrowserResult(SerializableMixin):
    """Result of a browser action."""

    success: bool = False
    action: str = ""
    url: str = ""
    content: Optional[PageContent] = None
    screenshot_b64: Optional[str] = None
    error: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Override to serialize nested PageContent via its own to_dict()."""
        d = super().to_dict()
        if self.content is not None:
            d["content"] = self.content.to_dict()
        return d


class BrowserTool:
    """
    Playwright-based browser automation.

    Manages a browser instance lifecycle (start/stop) and provides
    navigation, screenshots, and element interaction.
    """

    def __init__(self, config: Optional[BrowserConfig] = None) -> None:
        self.config = config or BrowserConfig()
        self.is_running: bool = False
        self._browser: Optional[Any] = None
        self._playwright_ctx: Optional[Any] = None
        self._current_page: Optional[Any] = None

    # -- Public setters for dependency injection (Amendment 11) --

    def set_browser(self, browser: Any) -> None:
        """Inject a browser instance (for testing)."""
        self._browser = browser

    def set_playwright_context(self, ctx: Any) -> None:
        """Inject a playwright context manager (for testing)."""
        self._playwright_ctx = ctx

    def set_current_page(self, page: Any) -> None:
        """Inject a current page (for testing)."""
        self._current_page = page

    # -- Lifecycle --

    async def start(self) -> None:
        """Start the browser instance."""
        if async_playwright is None:
            raise RuntimeError(
                "Playwright is not installed. Install with: "
                "pip install playwright && playwright install chromium"
            )

        try:
            self._playwright_ctx = async_playwright()
            playwright = await self._playwright_ctx.__aenter__()
            self._browser = await playwright.chromium.launch(
                headless=self.config.headless,
            )
            self.is_running = True
            logger.info("Browser started (headless=%s)", self.config.headless)
        except (
            PlaywrightError,
            PlaywrightTimeoutError,
            OSError,
            RuntimeError,
            ValueError,
            ImportError,
        ) as e:
            # Clean up on failure
            if self._playwright_ctx:
                try:
                    await self._playwright_ctx.__aexit__(None, None, None)
                except (PlaywrightError, OSError, RuntimeError):
                    pass  # Cleanup: swallow during error recovery
                self._playwright_ctx = None
            logger.error("Failed to start browser: %s", e)
            raise RuntimeError(f"Failed to start browser: {e}") from e

    async def stop(self) -> None:
        """Stop the browser instance and clean up resources."""
        if self._current_page:
            try:
                await self._current_page.close()
            except (PlaywrightError, OSError, RuntimeError):
                pass  # Cleanup: tolerate errors during shutdown
            self._current_page = None

        if self._browser:
            try:
                await self._browser.close()
            except (PlaywrightError, OSError, RuntimeError):
                pass  # Cleanup: tolerate errors during shutdown
            self._browser = None

        if self._playwright_ctx:
            try:
                await self._playwright_ctx.__aexit__(None, None, None)
            except (PlaywrightError, OSError, RuntimeError):
                pass  # Cleanup: tolerate errors during shutdown
            self._playwright_ctx = None

        self.is_running = False
        logger.info("Browser stopped")

    # -- Actions --

    async def navigate(self, url: str) -> BrowserResult:
        """Navigate to a URL and return the page content."""
        if not self.is_running or not self._browser:
            return BrowserResult(
                success=False,
                action="navigate",
                url=url,
                error="Browser is not running. Call start() first.",
            )

        page = None
        try:
            page = await self._browser.new_page(
                user_agent=self.config.user_agent,
                viewport={
                    "width": self.config.viewport_width,
                    "height": self.config.viewport_height,
                },
            )

            await page.goto(
                url,
                timeout=int(self.config.timeout * 1000),
                wait_until="domcontentloaded",
            )

            title = await page.title()
            text = await page.inner_text("body")
            html = await page.content()

            # Sanitize and truncate
            text = text.strip()
            if len(text) > self.config.max_content_length:
                text = text[: self.config.max_content_length - 15] + "... [truncated]"

            self._current_page = page

            content = PageContent(
                url=page.url,
                title=title,
                text=text,
                html=html if len(html) < self.config.max_content_length else "",
            )

            return BrowserResult(
                success=True,
                action="navigate",
                url=page.url,
                content=content,
            )

        except (TimeoutError, PlaywrightTimeoutError, OSError, ConnectionError) as e:
            logger.error("Navigation error for %s: %s", url, e)
            if page:
                try:
                    await page.close()
                except (PlaywrightError, OSError, RuntimeError):
                    pass  # Cleanup during error handling
            return BrowserResult(
                success=False,
                action="navigate",
                url=url,
                error=f"Navigation timeout or error: {e}",
            )
        except (PlaywrightError, RuntimeError, ValueError) as e:
            logger.error("Navigation error for %s: %s", url, e)
            if page:
                try:
                    await page.close()
                except (PlaywrightError, OSError, RuntimeError):
                    pass  # Cleanup during error handling
            return BrowserResult(
                success=False,
                action="navigate",
                url=url,
                error=str(e),
            )

    async def screenshot(self, url: str) -> BrowserResult:
        """Take a screenshot of a URL."""
        if not self.is_running or not self._browser:
            return BrowserResult(
                success=False,
                action="screenshot",
                url=url,
                error="Browser is not running. Call start() first.",
            )

        page = None
        try:
            page = await self._browser.new_page(
                viewport={
                    "width": self.config.viewport_width,
                    "height": self.config.viewport_height,
                },
            )
            await page.goto(
                url,
                timeout=int(self.config.timeout * 1000),
                wait_until="domcontentloaded",
            )

            screenshot_bytes = await page.screenshot(type="png", full_page=False)
            screenshot_b64 = base64.b64encode(screenshot_bytes).decode("utf-8")

            await page.close()

            return BrowserResult(
                success=True,
                action="screenshot",
                url=url,
                screenshot_b64=screenshot_b64,
            )

        except (TimeoutError, PlaywrightTimeoutError, OSError, ConnectionError) as e:
            logger.error("Screenshot error for %s: %s", url, e)
            if page:
                try:
                    await page.close()
                except (PlaywrightError, OSError, RuntimeError):
                    pass  # Cleanup during error handling
            return BrowserResult(
                success=False,
                action="screenshot",
                url=url,
                error=f"Screenshot timeout or error: {e}",
            )
        except (PlaywrightError, RuntimeError, ValueError) as e:
            logger.error("Screenshot error for %s: %s", url, e)
            if page:
                try:
                    await page.close()
                except (PlaywrightError, OSError, RuntimeError):
                    pass  # Cleanup during error handling
            return BrowserResult(
                success=False,
                action="screenshot",
                url=url,
                error=str(e),
            )

    async def click(self, selector: str) -> BrowserResult:
        """Click an element on the current page."""
        if not self._current_page:
            return BrowserResult(
                success=False,
                action="click",
                error="No page loaded. Call navigate() first.",
            )

        try:
            await self._current_page.click(selector, timeout=int(self.config.timeout * 1000))

            # Return updated page state
            title = await self._current_page.title()
            text = await self._current_page.inner_text("body")
            html = await self._current_page.content()

            if len(text) > self.config.max_content_length:
                text = text[: self.config.max_content_length - 15] + "... [truncated]"

            content = PageContent(
                url=self._current_page.url,
                title=title,
                text=text,
                html=html if len(html) < self.config.max_content_length else "",
            )

            return BrowserResult(
                success=True,
                action="click",
                url=self._current_page.url,
                content=content,
            )

        except (TimeoutError, PlaywrightTimeoutError, OSError) as e:
            logger.error("Click error for selector '%s': %s", selector, e)
            return BrowserResult(
                success=False,
                action="click",
                error=f"Click error: {e}",
            )
        except (PlaywrightError, RuntimeError, ValueError) as e:
            logger.error("Click error for selector '%s': %s", selector, e)
            return BrowserResult(
                success=False,
                action="click",
                error=str(e),
            )


# -- Singleton browser tool instance --
_browser_tool: Optional[BrowserTool] = None


def _get_browser_tool() -> BrowserTool:
    """Get or create the global browser tool instance."""
    global _browser_tool
    if _browser_tool is None:
        _browser_tool = BrowserTool()
    return _browser_tool


async def browser_navigate_executor(args: Dict[str, Any], ctx: ToolExecutionContext) -> ToolResult:
    """ToolRegistry-compatible executor for browser navigation."""
    url = args.get("url", "")
    if not url:
        return ToolResult(
            tool_name="browser_navigate",
            success=False,
            output="",
            error="Missing required parameter: url",
        )

    tool = _get_browser_tool()
    if not tool.is_running:
        try:
            await tool.start()
        except RuntimeError as e:
            return ToolResult(
                tool_name="browser_navigate",
                success=False,
                output="",
                error=f"Failed to start browser: {e}",
            )

    result = await tool.navigate(url)

    if result.success and result.content:
        output = f"**{result.content.title}**\n\n"
        output += result.content.truncated_text(max_length=40000)
        return ToolResult(
            tool_name="browser_navigate",
            success=True,
            output=output,
            metadata=result.to_dict(),
        )
    else:
        return ToolResult(
            tool_name="browser_navigate",
            success=False,
            output="",
            error=result.error,
        )


async def browser_screenshot_executor(
    args: Dict[str, Any], ctx: ToolExecutionContext
) -> ToolResult:
    """ToolRegistry-compatible executor for browser screenshots."""
    url = args.get("url", "")
    if not url:
        return ToolResult(
            tool_name="browser_screenshot",
            success=False,
            output="",
            error="Missing required parameter: url",
        )

    tool = _get_browser_tool()
    if not tool.is_running:
        try:
            await tool.start()
        except RuntimeError as e:
            return ToolResult(
                tool_name="browser_screenshot",
                success=False,
                output="",
                error=f"Failed to start browser: {e}",
            )

    result = await tool.screenshot(url)

    if result.success and result.screenshot_b64:
        return ToolResult(
            tool_name="browser_screenshot",
            success=True,
            output=f"Screenshot captured ({len(result.screenshot_b64)} bytes b64)",
            metadata={"screenshot_b64": result.screenshot_b64, **result.to_dict()},
        )
    else:
        return ToolResult(
            tool_name="browser_screenshot",
            success=False,
            output="",
            error=result.error,
        )


async def browser_click_executor(args: Dict[str, Any], ctx: ToolExecutionContext) -> ToolResult:
    """ToolRegistry-compatible executor for browser click."""
    selector = args.get("selector", "")
    if not selector:
        return ToolResult(
            tool_name="browser_click",
            success=False,
            output="",
            error="Missing required parameter: selector",
        )

    tool = _get_browser_tool()
    result = await tool.click(selector)

    if result.success and result.content:
        output = f"Clicked '{selector}'. Page now shows:\n\n"
        output += f"**{result.content.title}**\n"
        output += result.content.truncated_text(max_length=20000)
        return ToolResult(
            tool_name="browser_click",
            success=True,
            output=output,
            metadata=result.to_dict(),
        )
    else:
        return ToolResult(
            tool_name="browser_click",
            success=False,
            output="",
            error=result.error,
        )
