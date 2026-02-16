from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    input_schema: Dict[str, Any]
    output_schema: Optional[Dict[str, Any]] = None
    tags: List[str] = field(default_factory=list)


@dataclass
class ToolCall:
    tool_name: str
    arguments: Dict[str, Any]
    raw_text: str
    start_pos: int = 0
    end_pos: int = 0


@dataclass
class ToolResult:
    tool_name: str
    success: bool
    output: str
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ToolExecutionContext:
    session_id: Optional[str] = None
    user_id: Optional[str] = None
    request_id: Optional[str] = None
    domain: Optional[str] = None
    allowed_fs_roots: List[str] = field(default_factory=list)
