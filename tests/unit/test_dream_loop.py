from vecna.memory import dream_loop


def test_run_scheduled_dream_loop_forwards_dry_run(monkeypatch):
    sentinel = object()
    received = {}

    def fake_run_dream_loop(*, dry_run):
        received["dry_run"] = dry_run
        return sentinel

    monkeypatch.setattr(dream_loop, "run_dream_loop", fake_run_dream_loop)

    result = dream_loop.run_scheduled_dream_loop(dry_run=True)

    assert received["dry_run"] is True
    assert result is sentinel
