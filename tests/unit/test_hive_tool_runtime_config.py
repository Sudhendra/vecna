"""Tests for HiveLoop tool runtime configuration wiring."""

from vecna.orchestrator.loop import HiveConfig, HiveLoop


def test_hive_loop_registry_respects_web_and_fs_feature_flags():
    disabled_loop = HiveLoop(
        config=HiveConfig(
            use_pg_memory=False,
            use_semantic_memory=False,
            enable_web_tools=False,
            enable_fs_tools=False,
        )
    )
    disabled_names = {spec.name for spec in disabled_loop.tool_registry.list_tools()}

    assert "python_exec" in disabled_names
    assert "memory_search" in disabled_names
    assert "memory_get" in disabled_names
    assert "http_request" not in disabled_names
    assert "web_search" not in disabled_names
    assert "fs_read" not in disabled_names
    assert "fs_list" not in disabled_names

    enabled_loop = HiveLoop(
        config=HiveConfig(
            use_pg_memory=False,
            use_semantic_memory=False,
            enable_web_tools=True,
            enable_fs_tools=True,
        )
    )
    enabled_names = {spec.name for spec in enabled_loop.tool_registry.list_tools()}

    assert "http_request" in enabled_names
    assert "web_search" in enabled_names
    assert "fs_read" in enabled_names
    assert "fs_list" in enabled_names


def test_hive_loop_runtime_wires_quota_manager_from_config():
    loop = HiveLoop(
        config=HiveConfig(
            use_pg_memory=False,
            use_semantic_memory=False,
            tool_quota_per_session=5,
            tool_quota_per_tool=2,
        )
    )

    assert loop.tool_runtime.quota_manager is not None
    assert loop.tool_runtime.quota_manager.config.per_session == 5
    assert loop.tool_runtime.quota_manager.config.per_tool == 2


def test_hive_loop_builds_tool_context_with_allowed_fs_roots_and_session_id():
    loop = HiveLoop(
        config=HiveConfig(
            use_pg_memory=False,
            use_semantic_memory=False,
            tool_allowed_fs_roots=["~/sandbox", "/tmp/work"],
        )
    )

    context = loop._build_tool_execution_context(session_id="session-1")

    assert context.session_id == "session-1"
    assert context.allowed_fs_roots == ["~/sandbox", "/tmp/work"]
