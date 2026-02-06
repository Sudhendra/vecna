import json
import re
from typing import List

from vecna.tools.code_executor import detect_code_blocks
from vecna.tools.types import ToolCall


_TOOL_CALL_RE = re.compile(r"<TOOL_CALL>(.*?)</TOOL_CALL>", re.DOTALL | re.IGNORECASE)


def parse_tool_calls(text: str) -> List[ToolCall]:
    calls: List[ToolCall] = []
    occupied_ranges: List[tuple[int, int]] = []

    for match in _TOOL_CALL_RE.finditer(text):
        raw = match.group(1).strip()
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            continue

        tool_name = payload.get("name")
        args = payload.get("args", {})
        if not tool_name:
            continue

        calls.append(
            ToolCall(
                tool_name=tool_name,
                arguments=args,
                raw_text=match.group(0),
                start_pos=match.start(),
                end_pos=match.end(),
            )
        )
        occupied_ranges.append((match.start(), match.end()))

    for block in detect_code_blocks(text):
        if _overlaps_ranges(block.start_pos, block.end_pos, occupied_ranges):
            continue

        calls.append(
            ToolCall(
                tool_name="python_exec",
                arguments={"code": block.code},
                raw_text=block.original_text,
                start_pos=block.start_pos,
                end_pos=block.end_pos,
            )
        )

    calls.sort(key=lambda call: call.start_pos)
    return calls


def _overlaps_ranges(start: int, end: int, ranges: List[tuple[int, int]]) -> bool:
    for range_start, range_end in ranges:
        if start < range_end and end > range_start:
            return True
    return False
