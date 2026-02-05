import pytest

from vecna.tools.code_executor import execute_code_tool
from vecna.tools.types import ToolExecutionContext


@pytest.mark.asyncio
async def test_execute_code_tool_wraps_executor(monkeypatch):
    class Dummy:
        success = True
        stdout = "ok"
        stderr = ""
        return_code = 0
        execution_time_ms = 1.0
        packages_installed = []

    async def fake_execute(code):
        return Dummy()

    monkeypatch.setattr("vecna.tools.code_executor.execute_code_block", fake_execute)
    result = await execute_code_tool({"code": "print(1)"}, ToolExecutionContext())
    assert result.success is True
    assert result.output == "ok"
