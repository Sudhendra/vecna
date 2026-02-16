from vecna.tools.parser import parse_tool_calls


def test_parse_tool_call_block():
    text = 'hello <TOOL_CALL>{"name":"python_exec","args":{"code":"print(1)"}}</TOOL_CALL>'
    calls = parse_tool_calls(text)
    assert len(calls) == 1
    assert calls[0].tool_name == "python_exec"


def test_parse_python_code_block_as_tool_call():
    text = "```python\nprint(1)\n```"
    calls = parse_tool_calls(text)
    assert len(calls) == 1
    assert calls[0].tool_name == "python_exec"
    assert "print(1)" in calls[0].arguments["code"]


def test_explicit_tool_call_overlaps_implicit_block():
    text = (
        '<TOOL_CALL>{"name":"python_exec","args":{"code":"```python\\nprint(1)\\n```"}}</TOOL_CALL>'
    )
    calls = parse_tool_calls(text)
    assert len(calls) == 1
    assert calls[0].tool_name == "python_exec"


def test_parse_tool_calls_preserves_explicit_implicit_order():
    text = (
        "before ```python\nprint(1)\n``` middle "
        '<TOOL_CALL>{"name":"python_exec","args":{"code":"print(2)"}}</TOOL_CALL>'
        " after ```python\nprint(3)\n```"
    )
    calls = parse_tool_calls(text)
    assert [call.arguments["code"].strip() for call in calls] == [
        "print(1)",
        "print(2)",
        "print(3)",
    ]


def test_parse_ignores_xml_style_tool_call_payload():
    text = "<TOOL_CALL><name>python_exec</name><args><code>print(1)</code></args></TOOL_CALL>"
    calls = parse_tool_calls(text)
    assert calls == []
