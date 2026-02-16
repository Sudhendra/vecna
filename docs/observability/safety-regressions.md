# Safety Regressions

Vecna includes a dedicated safety regression suite under `tests/safety/` to prevent regressions in tool-call policy handling.

## What The Suite Covers

- Prompt-injected dangerous tool calls are denied or routed to approval
- Inline approval control parsing is resilient to malformed tags
- Malformed `<TOOL_CALL>` payloads do not execute and do not crash runtime
- Unknown policy actions fail closed

Primary files:

- `tests/safety/test_tool_safety_regressions.py`
- `tests/safety/test_red_team_tool_calls.py`

## Commands

Run all safety tests:

```bash
pytest tests/safety -v
```

Run specific suites:

```bash
pytest tests/safety/test_tool_safety_regressions.py -v
pytest tests/safety/test_red_team_tool_calls.py -v
```

## Recommended CI Pairing

For release gates, run safety tests together with unit and e2e coverage:

```bash
pytest tests/unit/ tests/e2e/ tests/safety -v
```
