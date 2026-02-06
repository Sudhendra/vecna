from vecna.tools.types import ToolCall, ToolSpec


def test_tool_spec_defaults():
    spec = ToolSpec(name="python_exec", description="Run python", input_schema={"code": "string"})
    assert spec.name == "python_exec"
    assert spec.output_schema is None
    assert spec.tags == []


def test_tool_call_round_trip():
    call = ToolCall(tool_name="python_exec", arguments={"code": "print(1)"}, raw_text="x")
    assert call.tool_name == "python_exec"
    assert call.arguments["code"] == "print(1)"
