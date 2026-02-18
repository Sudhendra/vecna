"""
Content summarization tool via the steipete summarize CLI.

Provides URL/YouTube/podcast summarization as a registered Vecna tool.
Uses ``summarize <url> --json`` for structured output.

Registered as ``content_summarize`` in the ToolRegistry.
"""

import asyncio
import json
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from vecna.core.types import SerializableMixin
from vecna.tools.types import ToolExecutionContext, ToolResult, ToolSpec

logger = logging.getLogger("vecna.tools.summarize_tool")


SUMMARIZE_TOOL_SPEC = ToolSpec(
    name="content_summarize",
    description=(
        "Summarize content from a URL (articles, YouTube videos, podcasts). "
        "Returns a structured summary with title, content type, and word count."
    ),
    input_schema={
        "url": "string",
        "format": "string",  # optional: "brief", "detailed", "bullet_points"
    },
    tags=["summarize", "content", "web", "research"],
)


@dataclass
class SummarizeConfig:
    """Configuration for the summarize tool."""

    binary_path: str = "summarize"
    timeout: float = 60.0
    max_output_length: int = 50000


@dataclass
class SummarizeResult(SerializableMixin):
    """Result of a content summarization."""

    success: bool = False
    url: str = ""
    summary: str = ""
    title: str = ""
    content_type: str = ""  # article, youtube, podcast, pdf
    word_count: int = 0
    error: str = ""
    raw_output: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)


class SummarizeTool:
    """
    Content summarization via the steipete summarize CLI.

    Wraps ``summarize <url> --json`` for structured output parsing.
    Supports articles, YouTube videos, podcasts, and PDFs.
    """

    def __init__(self, config: Optional[SummarizeConfig] = None) -> None:
        self.config = config or SummarizeConfig()

    async def _exec_summarize(
        self, args: List[str], timeout: Optional[float] = None
    ) -> Tuple[int, str, str]:
        """Execute the summarize subprocess."""
        effective_timeout = timeout or self.config.timeout
        try:
            proc = await asyncio.create_subprocess_exec(
                self.config.binary_path,
                *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=effective_timeout)
            return (
                proc.returncode or 0,
                stdout.decode("utf-8", errors="replace"),
                stderr.decode("utf-8", errors="replace"),
            )
        except asyncio.TimeoutError:
            logger.warning("Summarize timed out after %ss", effective_timeout)
            return (1, "", f"Summarize timed out after {effective_timeout}s")
        except FileNotFoundError:
            logger.error("summarize binary not found at %s", self.config.binary_path)
            return (1, "", "summarize binary not found")
        except OSError as e:
            logger.error("OS error running summarize: %s", e)
            return (1, "", str(e))

    async def summarize(self, url: str, output_format: str = "brief") -> SummarizeResult:
        """Summarize content from a URL."""
        args = [url, "--json"]
        if output_format and output_format != "brief":
            args.extend(["--format", output_format])

        returncode, stdout, stderr = await self._exec_summarize(args)

        if returncode != 0:
            logger.warning("summarize exited with code %d for %s: %s", returncode, url, stderr)
            return SummarizeResult(
                success=False,
                url=url,
                error=stderr or f"summarize exited with code {returncode}",
                raw_output=stdout,
            )

        # Truncate excessively long output
        if len(stdout) > self.config.max_output_length:
            stdout = stdout[: self.config.max_output_length]

        try:
            parsed = json.loads(stdout)
        except json.JSONDecodeError as e:
            logger.error("Failed to parse summarize JSON output: %s", e)
            return SummarizeResult(
                success=False,
                url=url,
                error=f"Failed to parse JSON output: {e}",
                raw_output=stdout,
            )

        return SummarizeResult(
            success=True,
            url=url,
            summary=parsed.get("summary", ""),
            title=parsed.get("title", ""),
            content_type=parsed.get("content_type", "unknown"),
            word_count=parsed.get("word_count", 0),
            raw_output=stdout,
            metadata={
                k: v
                for k, v in parsed.items()
                if k not in ("summary", "title", "content_type", "word_count", "url")
            },
        )


# -- Global tool instance for the executor --
_default_tool = SummarizeTool()


async def summarize_executor(args: Dict[str, Any], ctx: ToolExecutionContext) -> ToolResult:
    """ToolRegistry-compatible executor for the summarize tool."""
    url = args.get("url", "")
    if not url:
        return ToolResult(
            tool_name="content_summarize",
            success=False,
            output="",
            error="Missing required parameter: url",
        )

    output_format = args.get("format", "brief")
    result = await _default_tool.summarize(url, output_format=output_format)

    if result.success:
        output_parts: List[str] = []
        if result.title:
            output_parts.append(f"**{result.title}**")
        output_parts.append(result.summary)
        if result.word_count:
            output_parts.append(f"\n[{result.content_type}, {result.word_count} words]")

        return ToolResult(
            tool_name="content_summarize",
            success=True,
            output="\n".join(output_parts),
            metadata=result.to_dict(),
        )
    else:
        return ToolResult(
            tool_name="content_summarize",
            success=False,
            output="",
            error=result.error,
        )
