from vecna.config.schema import AgentMode
from vecna.orchestrator.autonomy import AutonomyLoop
from vecna.orchestrator.loop import HiveLoop


def resolve_loop(mode: AgentMode) -> HiveLoop:
    if mode == AgentMode.explorer:
        return AutonomyLoop(name="explorer")
    return HiveLoop(name="assistant")
