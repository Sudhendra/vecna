"""Tests for the content summarize tool via steipete summarize CLI."""

import json
from unittest.mock import AsyncMock, patch

from vecna.tools.summarize_tool import (
    SummarizeTool,
    SummarizeConfig,
    SummarizeResult,
    SUMMARIZE_TOOL_SPEC,
    summarize_executor,
)
from vecna.tools.types import ToolExecutionContext


class TestSummarizeToolSpec:
    def test_tool_spec_name(self):
        assert SUMMARIZE_TOOL_SPEC.name == "content_summarize"

    def test_tool_spec_has_description(self):
        assert "summarize" in SUMMARIZE_TOOL_SPEC.description.lower()

    def test_tool_spec_input_schema(self):
        schema = SUMMARIZE_TOOL_SPEC.input_schema
        assert "url" in schema
        assert "format" in schema

    def test_tool_spec_tags(self):
        assert "summarize" in SUMMARIZE_TOOL_SPEC.tags
        assert "content" in SUMMARIZE_TOOL_SPEC.tags


class TestSummarizeConfig:
    def test_default_config(self):
        config = SummarizeConfig()
        assert config.binary_path == "summarize"
        assert config.timeout == 60.0
        assert config.max_output_length == 50000

    def test_custom_config(self):
        config = SummarizeConfig(timeout=120.0)
        assert config.timeout == 120.0
        # Other defaults unchanged
        assert config.binary_path == "summarize"
        assert config.max_output_length == 50000


class TestSummarizeResult:
    def test_success_result(self):
        result = SummarizeResult(
            success=True,
            url="https://example.com/article",
            summary="This is a summary of the article.",
            content_type="article",
        )
        assert result.success is True
        assert result.url == "https://example.com/article"
        assert "summary" in result.summary.lower()
        assert result.content_type == "article"

    def test_error_result(self):
        result = SummarizeResult(
            success=False,
            url="https://example.com/broken",
            error="404 Not Found",
        )
        assert result.success is False
        assert result.error == "404 Not Found"
        assert result.summary == ""

    def test_to_dict_contains_all_fields(self):
        result = SummarizeResult(
            success=True,
            url="https://example.com",
            summary="Summary text",
            content_type="article",
            word_count=150,
        )
        d = result.to_dict()
        assert d["success"] is True
        assert d["url"] == "https://example.com"
        assert d["summary"] == "Summary text"
        assert d["content_type"] == "article"
        assert d["word_count"] == 150

    def test_to_dict_error_result(self):
        result = SummarizeResult(
            success=False,
            url="https://example.com/broken",
            error="Connection timeout",
        )
        d = result.to_dict()
        assert d["success"] is False
        assert d["error"] == "Connection timeout"


class TestSummarizeTool:
    def test_tool_creation_default_config(self):
        tool = SummarizeTool()
        assert tool.config.binary_path == "summarize"
        assert tool.config.timeout == 60.0

    def test_tool_creation_custom_config(self):
        config = SummarizeConfig(binary_path="/usr/local/bin/summarize", timeout=90.0)
        tool = SummarizeTool(config=config)
        assert tool.config.binary_path == "/usr/local/bin/summarize"
        assert tool.config.timeout == 90.0

    async def test_summarize_url_success(self):
        tool = SummarizeTool()
        mock_output = json.dumps(
            {
                "title": "Test Article",
                "summary": "This is a great article about testing.",
                "content_type": "article",
                "word_count": 500,
                "url": "https://example.com/article",
            }
        )

        with patch(
            "vecna.tools.summarize_tool.SummarizeTool._exec_summarize",
            new_callable=AsyncMock,
            return_value=(0, mock_output, ""),
        ):
            result = await tool.summarize("https://example.com/article")
            assert result.success is True
            assert result.summary == "This is a great article about testing."
            assert result.content_type == "article"
            assert result.title == "Test Article"
            assert result.word_count == 500

    async def test_summarize_url_failure(self):
        tool = SummarizeTool()

        with patch(
            "vecna.tools.summarize_tool.SummarizeTool._exec_summarize",
            new_callable=AsyncMock,
            return_value=(1, "", "Failed to fetch URL"),
        ):
            result = await tool.summarize("https://example.com/broken")
            assert result.success is False
            assert "fetch" in result.error.lower()

    async def test_summarize_youtube_url(self):
        tool = SummarizeTool()
        mock_output = json.dumps(
            {
                "title": "Great Video",
                "summary": "A video about AI.",
                "content_type": "youtube",
                "duration": "10:30",
                "url": "https://youtube.com/watch?v=abc123",
            }
        )

        with patch(
            "vecna.tools.summarize_tool.SummarizeTool._exec_summarize",
            new_callable=AsyncMock,
            return_value=(0, mock_output, ""),
        ):
            result = await tool.summarize("https://youtube.com/watch?v=abc123")
            assert result.success is True
            assert result.content_type == "youtube"
            assert result.title == "Great Video"
            assert result.metadata.get("duration") == "10:30"

    async def test_summarize_invalid_json_output(self):
        """Error path: CLI returns non-JSON output."""
        tool = SummarizeTool()

        with patch(
            "vecna.tools.summarize_tool.SummarizeTool._exec_summarize",
            new_callable=AsyncMock,
            return_value=(0, "not json {{", ""),
        ):
            result = await tool.summarize("https://example.com")
            assert result.success is False
            assert "json" in result.error.lower() or "parse" in result.error.lower()

    async def test_summarize_nonzero_exit_no_stderr(self):
        """Error path: CLI exits nonzero with no stderr message."""
        tool = SummarizeTool()

        with patch(
            "vecna.tools.summarize_tool.SummarizeTool._exec_summarize",
            new_callable=AsyncMock,
            return_value=(2, "", ""),
        ):
            result = await tool.summarize("https://example.com")
            assert result.success is False
            assert "exit" in result.error.lower() or "code" in result.error.lower()

    async def test_summarize_timeout(self):
        """Error path: subprocess times out."""
        tool = SummarizeTool()

        with patch(
            "vecna.tools.summarize_tool.SummarizeTool._exec_summarize",
            new_callable=AsyncMock,
            return_value=(1, "", "Summarize timed out after 60.0s"),
        ):
            result = await tool.summarize("https://slow-site.com")
            assert result.success is False
            assert "timed out" in result.error.lower()

    async def test_summarize_binary_not_found(self):
        """Error path: summarize binary is not installed."""
        tool = SummarizeTool()

        with patch(
            "vecna.tools.summarize_tool.SummarizeTool._exec_summarize",
            new_callable=AsyncMock,
            return_value=(1, "", "summarize binary not found"),
        ):
            result = await tool.summarize("https://example.com")
            assert result.success is False
            assert "not found" in result.error.lower()

    async def test_summarize_output_truncation(self):
        """Edge case: CLI output exceeds max_output_length."""
        config = SummarizeConfig(max_output_length=100)
        tool = SummarizeTool(config=config)

        # Build valid JSON that is very long
        long_summary = "x" * 200
        mock_output = json.dumps(
            {
                "title": "Long Article",
                "summary": long_summary,
                "content_type": "article",
                "word_count": 10000,
                "url": "https://example.com/long",
            }
        )

        with patch(
            "vecna.tools.summarize_tool.SummarizeTool._exec_summarize",
            new_callable=AsyncMock,
            return_value=(0, mock_output, ""),
        ):
            result = await tool.summarize("https://example.com/long")
            # Truncated JSON can't be parsed — should fail gracefully
            assert result.success is False
            assert "json" in result.error.lower() or "parse" in result.error.lower()

    async def test_summarize_with_format_parameter(self):
        """Passes format argument to the CLI."""
        tool = SummarizeTool()
        mock_output = json.dumps(
            {
                "title": "Test",
                "summary": "Bullet point summary.",
                "content_type": "article",
                "word_count": 100,
                "url": "https://example.com",
            }
        )

        with patch(
            "vecna.tools.summarize_tool.SummarizeTool._exec_summarize",
            new_callable=AsyncMock,
            return_value=(0, mock_output, ""),
        ) as mock_exec:
            result = await tool.summarize("https://example.com", output_format="bullet_points")
            assert result.success is True
            # Verify --format was passed in the args list
            # patch replaces method at class level; first positional arg is self
            positional_args = mock_exec.call_args[0]
            # Find the list argument (args to subprocess)
            args_list = [a for a in positional_args if isinstance(a, list)][0]
            assert "--format" in args_list
            assert "bullet_points" in args_list

    async def test_summarize_metadata_captures_extra_fields(self):
        """Extra JSON fields from CLI are captured in metadata."""
        tool = SummarizeTool()
        mock_output = json.dumps(
            {
                "title": "Video",
                "summary": "A video.",
                "content_type": "youtube",
                "word_count": 300,
                "url": "https://youtube.com/watch?v=test",
                "duration": "15:00",
                "channel": "TestChannel",
            }
        )

        with patch(
            "vecna.tools.summarize_tool.SummarizeTool._exec_summarize",
            new_callable=AsyncMock,
            return_value=(0, mock_output, ""),
        ):
            result = await tool.summarize("https://youtube.com/watch?v=test")
            assert result.success is True
            assert result.metadata["duration"] == "15:00"
            assert result.metadata["channel"] == "TestChannel"


class TestSummarizeExecutor:
    async def test_executor_returns_tool_result(self):
        ctx = ToolExecutionContext(session_id="test-session")
        mock_output = json.dumps(
            {
                "title": "Test",
                "summary": "Summary here",
                "content_type": "article",
                "word_count": 100,
                "url": "https://example.com",
            }
        )

        with patch(
            "vecna.tools.summarize_tool.SummarizeTool._exec_summarize",
            new_callable=AsyncMock,
            return_value=(0, mock_output, ""),
        ):
            result = await summarize_executor(
                {"url": "https://example.com"},
                ctx,
            )
            assert result.tool_name == "content_summarize"
            assert result.success is True
            assert "Summary here" in result.output

    async def test_executor_missing_url(self):
        ctx = ToolExecutionContext()
        result = await summarize_executor({}, ctx)
        assert result.tool_name == "content_summarize"
        assert result.success is False
        assert "url" in result.error.lower()

    async def test_executor_error_propagates(self):
        ctx = ToolExecutionContext(session_id="test-session")

        with patch(
            "vecna.tools.summarize_tool.SummarizeTool._exec_summarize",
            new_callable=AsyncMock,
            return_value=(1, "", "Connection refused"),
        ):
            result = await summarize_executor(
                {"url": "https://example.com/down"},
                ctx,
            )
            assert result.success is False
            assert "Connection refused" in result.error

    async def test_executor_includes_title_in_output(self):
        ctx = ToolExecutionContext(session_id="test-session")
        mock_output = json.dumps(
            {
                "title": "Important Article",
                "summary": "Key findings of the study.",
                "content_type": "article",
                "word_count": 2000,
                "url": "https://example.com/article",
            }
        )

        with patch(
            "vecna.tools.summarize_tool.SummarizeTool._exec_summarize",
            new_callable=AsyncMock,
            return_value=(0, mock_output, ""),
        ):
            result = await summarize_executor(
                {"url": "https://example.com/article"},
                ctx,
            )
            assert "Important Article" in result.output
            assert "Key findings" in result.output
            assert "article" in result.output
            assert "2000" in result.output

    async def test_executor_passes_format_parameter(self):
        ctx = ToolExecutionContext()
        mock_output = json.dumps(
            {
                "title": "Test",
                "summary": "Detailed summary.",
                "content_type": "article",
                "word_count": 500,
                "url": "https://example.com",
            }
        )

        with patch(
            "vecna.tools.summarize_tool.SummarizeTool._exec_summarize",
            new_callable=AsyncMock,
            return_value=(0, mock_output, ""),
        ):
            result = await summarize_executor(
                {"url": "https://example.com", "format": "detailed"},
                ctx,
            )
            assert result.success is True
            assert "Detailed summary" in result.output
