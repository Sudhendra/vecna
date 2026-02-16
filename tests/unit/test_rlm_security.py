from datetime import datetime, timedelta
import asyncio
import json

from vecna.memory.rlm_bridge import RLMBridge, RLMConfig


class _FakeProcess:
    def __init__(self, stdout: bytes = b"", stderr: bytes = b"", returncode: int = 0):
        self._stdout = stdout
        self._stderr = stderr
        self.returncode = returncode

    async def communicate(self):
        return self._stdout, self._stderr


async def test_rlm_bridge_includes_seccomp_profile_when_enabled(monkeypatch):
    captured_cmd = []

    def _fake_run(*args, **kwargs):
        class _Result:
            returncode = 0

        return _Result()

    async def _fake_create_subprocess_exec(*cmd, **kwargs):
        captured_cmd.extend(cmd)
        return _FakeProcess(stdout=b"container123", stderr=b"", returncode=0)

    config = RLMConfig(enable_seccomp=True, seccomp_profile_path="/tmp/seccomp.json")
    bridge = RLMBridge(config=config)

    monkeypatch.setattr("vecna.memory.rlm_bridge.subprocess.run", _fake_run)
    monkeypatch.setattr(
        "vecna.memory.rlm_bridge.asyncio.create_subprocess_exec", _fake_create_subprocess_exec
    )

    async def _fake_install_packages(packages):
        return True, ""

    monkeypatch.setattr(bridge, "install_packages", _fake_install_packages)

    await bridge.prewarm()

    cmd_text = " ".join(captured_cmd)
    assert "--security-opt" in captured_cmd
    assert "seccomp=/tmp/seccomp.json" in cmd_text


async def test_rlm_container_ttl_forces_shutdown_after_idle_period(monkeypatch):
    shutdown_calls = []
    prewarm_calls = []

    async def _fake_shutdown():
        shutdown_calls.append(True)

    async def _fake_prewarm():
        prewarm_calls.append(True)
        bridge._container_id = "new-container"
        return True

    async def _fake_create_subprocess_exec(*cmd, **kwargs):
        return _FakeProcess(stdout=b"ok", stderr=b"", returncode=0)

    config = RLMConfig(container_ttl_seconds=1)
    bridge = RLMBridge(config=config)
    bridge._container_id = "old-container"
    bridge._prewarmed = True
    bridge._last_activity = datetime.now() - timedelta(seconds=5)

    monkeypatch.setattr(bridge, "shutdown", _fake_shutdown)
    monkeypatch.setattr(bridge, "prewarm", _fake_prewarm)
    monkeypatch.setattr(
        "vecna.memory.rlm_bridge.asyncio.create_subprocess_exec", _fake_create_subprocess_exec
    )

    await bridge.execute_code("print('hello')")

    assert len(shutdown_calls) == 1
    assert len(prewarm_calls) == 1


async def test_recursive_query_embeds_query_safely(monkeypatch):
    bridge = RLMBridge(config=RLMConfig(pg_url="postgresql://example"))
    query = 'What about """ and __import__("os")?'
    captured_code = {"value": ""}

    async def _fake_execute_code(code):
        captured_code["value"] = code
        return json.dumps({"query": query, "results": [], "success": True}), "", 0

    monkeypatch.setattr(bridge, "execute_code", _fake_execute_code)

    result = await bridge.recursive_query(query)

    assert result.success is True
    assert 'query = """' not in captured_code["value"]
    assert f"query = {json.dumps(query)}" in captured_code["value"]


class _SlowProcess:
    def __init__(self):
        self.returncode = 0
        self.terminated = False
        self.killed = False

    async def communicate(self):
        await asyncio.sleep(0.05)
        return b"", b""

    def terminate(self):
        self.terminated = True

    def kill(self):
        self.killed = True

    async def wait(self):
        self.returncode = -9
        return self.returncode


async def test_execute_code_times_out_during_communicate(monkeypatch):
    bridge = RLMBridge(config=RLMConfig(timeout=0.01))
    bridge._container_id = "container-1"

    process = _SlowProcess()

    async def _fake_create_subprocess_exec(*cmd, **kwargs):
        return process

    monkeypatch.setattr(
        "vecna.memory.rlm_bridge.asyncio.create_subprocess_exec", _fake_create_subprocess_exec
    )

    stdout, stderr, code = await bridge.execute_code("print('hello')")

    assert stdout == ""
    assert code == -1
    assert "timed out" in stderr.lower()
    assert process.terminated is True or process.killed is True
