from vecna.orchestrator.curiosity import CuriosityEngine


def test_curiosity_creates_goal():
    engine = CuriosityEngine()
    goals = engine.from_contradictions([{"content": "X vs Y", "confidence": 0.4}])
    assert goals and "explore" in goals[0]["goal"]
