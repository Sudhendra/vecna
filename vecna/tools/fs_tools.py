"""Read-only filesystem tools bounded by context sandbox roots."""

from pathlib import Path
from typing import Any, Dict, List

from vecna.tools.path_policy import is_allowed
from vecna.tools.types import ToolExecutionContext, ToolResult

MAX_READ_CHARS = 10000
MAX_LIST_ENTRIES = 200
READ_TRUNCATION_MARKER = "\n...[truncated]"


def _get_allowed_roots(context: ToolExecutionContext) -> List[str]:
    return context.allowed_fs_roots


def _blocked_result(tool_name: str) -> ToolResult:
    return ToolResult(tool_name=tool_name, success=False, output="", error="path not allowed")


async def fs_read_executor(args: Dict[str, Any], context: ToolExecutionContext) -> ToolResult:
    path = str(args.get("path", "")).strip()
    if not path:
        return ToolResult(tool_name="fs_read", success=False, output="", error="missing path")

    allowed_roots = _get_allowed_roots(context)
    if not is_allowed(path, allowed_roots):
        return _blocked_result("fs_read")

    try:
        target = Path(path).expanduser().resolve()
        if not target.exists():
            return ToolResult(tool_name="fs_read", success=False, output="", error="path not found")
        if not target.is_file():
            return ToolResult(
                tool_name="fs_read", success=False, output="", error="path is not a file"
            )

        with target.open("r", encoding="utf-8", errors="replace") as handle:
            content = handle.read(MAX_READ_CHARS + 1)

        if len(content) > MAX_READ_CHARS:
            content = f"{content[:MAX_READ_CHARS]}{READ_TRUNCATION_MARKER}"

        return ToolResult(tool_name="fs_read", success=True, output=content)
    except PermissionError:
        return ToolResult(tool_name="fs_read", success=False, output="", error="permission denied")
    except OSError as exc:
        return ToolResult(
            tool_name="fs_read", success=False, output="", error=f"read failed: {exc}"
        )


async def fs_list_executor(args: Dict[str, Any], context: ToolExecutionContext) -> ToolResult:
    path = str(args.get("path", "")).strip()
    if not path:
        return ToolResult(tool_name="fs_list", success=False, output="", error="missing path")

    allowed_roots = _get_allowed_roots(context)
    if not is_allowed(path, allowed_roots):
        return _blocked_result("fs_list")

    try:
        target = Path(path).expanduser().resolve()
        if not target.exists():
            return ToolResult(tool_name="fs_list", success=False, output="", error="path not found")
        if not target.is_dir():
            return ToolResult(
                tool_name="fs_list",
                success=False,
                output="",
                error="path is not a directory",
            )

        entries: List[str] = []
        for entry in target.iterdir():
            suffix = "/" if entry.is_dir() else ""
            entries.append(f"{entry.name}{suffix}")
            if len(entries) >= MAX_LIST_ENTRIES:
                break

        return ToolResult(tool_name="fs_list", success=True, output="\n".join(entries))
    except PermissionError:
        return ToolResult(tool_name="fs_list", success=False, output="", error="permission denied")
    except OSError as exc:
        return ToolResult(
            tool_name="fs_list", success=False, output="", error=f"list failed: {exc}"
        )
