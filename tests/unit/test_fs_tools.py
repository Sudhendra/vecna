"""Unit tests for filesystem tools with sandboxed roots."""

from vecna.tools.types import ToolExecutionContext


async def test_fs_read_success_inside_root(tmp_path):
    from vecna.tools.fs_tools import fs_read_executor

    allowed_root = tmp_path / "allowed"
    allowed_root.mkdir()
    target = allowed_root / "note.txt"
    target.write_text("inside root", encoding="utf-8")

    result = await fs_read_executor(
        {"path": str(target)},
        ToolExecutionContext(allowed_fs_roots=[str(allowed_root)]),
    )

    assert result.success is True
    assert result.output == "inside root"


async def test_fs_read_blocked_outside_root(tmp_path):
    from vecna.tools.fs_tools import fs_read_executor

    allowed_root = tmp_path / "allowed"
    allowed_root.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("outside root", encoding="utf-8")

    result = await fs_read_executor(
        {"path": str(outside)},
        ToolExecutionContext(allowed_fs_roots=[str(allowed_root)]),
    )

    assert result.success is False
    assert result.error == "path not allowed"


async def test_fs_read_ignores_args_allowlist_widening_attempt(tmp_path):
    from vecna.tools.fs_tools import fs_read_executor

    allowed_root = tmp_path / "allowed"
    allowed_root.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("outside root", encoding="utf-8")

    result = await fs_read_executor(
        {
            "path": str(outside),
            "allowed_fs_roots": [str(tmp_path)],
        },
        ToolExecutionContext(allowed_fs_roots=[str(allowed_root)]),
    )

    assert result.success is False
    assert result.error == "path not allowed"


async def test_fs_list_success_inside_root(tmp_path):
    from vecna.tools.fs_tools import fs_list_executor

    allowed_root = tmp_path / "allowed"
    allowed_root.mkdir()
    (allowed_root / "a.txt").write_text("A", encoding="utf-8")
    (allowed_root / "subdir").mkdir()

    result = await fs_list_executor(
        {"path": str(allowed_root)},
        ToolExecutionContext(allowed_fs_roots=[str(allowed_root)]),
    )

    assert result.success is True
    assert "a.txt" in result.output
    assert "subdir" in result.output


async def test_fs_list_blocked_outside_root(tmp_path):
    from vecna.tools.fs_tools import fs_list_executor

    allowed_root = tmp_path / "allowed"
    allowed_root.mkdir()
    outside_dir = tmp_path / "outside"
    outside_dir.mkdir()

    result = await fs_list_executor(
        {"path": str(outside_dir)},
        ToolExecutionContext(allowed_fs_roots=[str(allowed_root)]),
    )

    assert result.success is False
    assert result.error == "path not allowed"


async def test_fs_read_missing_path_argument(tmp_path):
    from vecna.tools.fs_tools import fs_read_executor

    allowed_root = tmp_path / "allowed"
    allowed_root.mkdir()

    result = await fs_read_executor({}, ToolExecutionContext(allowed_fs_roots=[str(allowed_root)]))

    assert result.success is False
    assert result.error == "missing path"


async def test_fs_list_missing_path_argument(tmp_path):
    from vecna.tools.fs_tools import fs_list_executor

    allowed_root = tmp_path / "allowed"
    allowed_root.mkdir()

    result = await fs_list_executor({}, ToolExecutionContext(allowed_fs_roots=[str(allowed_root)]))

    assert result.success is False
    assert result.error == "missing path"


async def test_fs_read_rejects_directory_target(tmp_path):
    from vecna.tools.fs_tools import fs_read_executor

    allowed_root = tmp_path / "allowed"
    allowed_root.mkdir()

    result = await fs_read_executor(
        {"path": str(allowed_root)},
        ToolExecutionContext(allowed_fs_roots=[str(allowed_root)]),
    )

    assert result.success is False
    assert result.error == "path is not a file"


async def test_fs_list_rejects_file_target(tmp_path):
    from vecna.tools.fs_tools import fs_list_executor

    allowed_root = tmp_path / "allowed"
    allowed_root.mkdir()
    target = allowed_root / "note.txt"
    target.write_text("inside root", encoding="utf-8")

    result = await fs_list_executor(
        {"path": str(target)},
        ToolExecutionContext(allowed_fs_roots=[str(allowed_root)]),
    )

    assert result.success is False
    assert result.error == "path is not a directory"


async def test_fs_read_permission_denied(monkeypatch, tmp_path):
    from vecna.tools.fs_tools import fs_read_executor

    allowed_root = tmp_path / "allowed"
    allowed_root.mkdir()
    target = allowed_root / "note.txt"
    target.write_text("inside root", encoding="utf-8")

    def _raise_permission_error(*args, **kwargs):
        raise PermissionError("denied")

    monkeypatch.setattr("pathlib.Path.open", _raise_permission_error)

    result = await fs_read_executor(
        {"path": str(target)},
        ToolExecutionContext(allowed_fs_roots=[str(allowed_root)]),
    )

    assert result.success is False
    assert result.error == "permission denied"


async def test_fs_list_permission_denied(monkeypatch, tmp_path):
    from vecna.tools.fs_tools import fs_list_executor

    allowed_root = tmp_path / "allowed"
    allowed_root.mkdir()
    (allowed_root / "a.txt").write_text("A", encoding="utf-8")

    def _raise_permission_error(*args, **kwargs):
        raise PermissionError("denied")

    monkeypatch.setattr("pathlib.Path.iterdir", _raise_permission_error)

    result = await fs_list_executor(
        {"path": str(allowed_root)},
        ToolExecutionContext(allowed_fs_roots=[str(allowed_root)]),
    )

    assert result.success is False
    assert result.error == "permission denied"


async def test_fs_read_handles_none_allowed_roots(tmp_path):
    from vecna.tools.fs_tools import fs_read_executor

    allowed_root = tmp_path / "allowed"
    allowed_root.mkdir()
    target = allowed_root / "note.txt"
    target.write_text("inside root", encoding="utf-8")

    result = await fs_read_executor(
        {"path": str(target)}, ToolExecutionContext(allowed_fs_roots=None)
    )

    assert result.success is False
    assert result.error == "path not allowed"


async def test_fs_list_handles_none_allowed_roots(tmp_path):
    from vecna.tools.fs_tools import fs_list_executor

    allowed_root = tmp_path / "allowed"
    allowed_root.mkdir()

    result = await fs_list_executor(
        {"path": str(allowed_root)},
        ToolExecutionContext(allowed_fs_roots=None),
    )

    assert result.success is False
    assert result.error == "path not allowed"


async def test_fs_read_truncates_without_using_read_text(monkeypatch, tmp_path):
    from vecna.tools.fs_tools import MAX_READ_CHARS, fs_read_executor

    allowed_root = tmp_path / "allowed"
    allowed_root.mkdir()
    target = allowed_root / "big.txt"
    target.write_text("x" * (MAX_READ_CHARS + 500), encoding="utf-8")

    def _read_text_should_not_be_called(*args, **kwargs):
        raise AssertionError("read_text should not be used for truncated reads")

    monkeypatch.setattr("pathlib.Path.read_text", _read_text_should_not_be_called)

    result = await fs_read_executor(
        {"path": str(target)},
        ToolExecutionContext(allowed_fs_roots=[str(allowed_root)]),
    )

    assert result.success is True
    assert len(result.output) <= MAX_READ_CHARS + len("\n...[truncated]")
    assert result.output.endswith("\n...[truncated]")


async def test_fs_list_caps_entries_without_sorting(tmp_path, monkeypatch):
    from vecna.tools.fs_tools import MAX_LIST_ENTRIES, fs_list_executor

    allowed_root = tmp_path / "allowed"
    allowed_root.mkdir()

    for index in range(MAX_LIST_ENTRIES + 25):
        (allowed_root / f"entry_{index:04}.txt").write_text("x", encoding="utf-8")

    def _sorted_should_not_be_called(*args, **kwargs):
        raise AssertionError("sorted should not be used for fs_list")

    monkeypatch.setattr("builtins.sorted", _sorted_should_not_be_called)

    result = await fs_list_executor(
        {"path": str(allowed_root)},
        ToolExecutionContext(allowed_fs_roots=[str(allowed_root)]),
    )

    assert result.success is True
    listed = [line for line in result.output.splitlines() if line]
    assert len(listed) == MAX_LIST_ENTRIES
