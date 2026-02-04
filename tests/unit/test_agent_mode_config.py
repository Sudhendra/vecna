from vecna.config.schema import AgentMode, VecnaConfig


def test_default_agent_mode():
    cfg = VecnaConfig()
    assert cfg.agent_mode == AgentMode.assistant


def test_agent_mode_parsing():
    cfg = VecnaConfig(agent_mode=AgentMode.explorer)
    assert cfg.agent_mode == AgentMode.explorer
