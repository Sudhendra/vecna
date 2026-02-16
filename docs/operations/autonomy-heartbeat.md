# Autonomy Heartbeat Operations

The heartbeat runner provides a bounded, cron-friendly autonomy tick.

## Command Usage

Use `vecna heartbeat tick` to execute at most N queued goals in one run.

```bash
# Default: up to 3 goals, queue at ~/.vecna/autonomy_queue.jsonl
vecna heartbeat tick

# Override per-run limits
vecna heartbeat tick --max-goals 5
vecna heartbeat tick --queue-path ~/.vecna/autonomy_queue.jsonl
```

Command output is a single summary line:

```text
status=<ok|idle|partial|error> popped=<n> executed=<n> completed=<n> failed=<n> skipped=<n>
```

## Scheduling (Cron)

Run heartbeat as a one-shot command on an external scheduler:

```cron
# Every 15 minutes
*/15 * * * * /usr/bin/env vecna heartbeat tick --max-goals 3
```

## Config Keys

Heartbeat-related config keys in `~/.vecna/config.json`:

- `enable_autonomy_heartbeat`
- `heartbeat_interval_seconds`
- `heartbeat_jitter_seconds`

Queue throughput for each invocation is controlled by the CLI flag `--max-goals`.

Note: these config keys are schema-level controls and reserved for higher-level automation wiring.
The current `vecna heartbeat tick` command is a one-shot runner; cadence is driven by your external
scheduler (for example cron/systemd), not by an internal background timer.
