# Tooling Hardening

This guide covers the runtime hardening knobs added for tool execution and sandboxed code paths.

## Seccomp Profile (RLM Docker Sandbox)

`RLMConfig` supports seccomp-based syscall filtering:

- `enable_seccomp`: enable Docker seccomp enforcement
- `seccomp_profile_path`: optional custom profile path

If `seccomp_profile_path` is not set, Vecna uses the bundled profile at:

- `vecna/security/seccomp/default-profile.json`

Python example:

```python
from vecna.memory.rlm_bridge import RLMBridge, RLMConfig

bridge = RLMBridge(
    RLMConfig(
        enable_seccomp=True,
        seccomp_profile_path="/absolute/path/to/seccomp.json",
    )
)
```

## Container Idle TTL

`RLMConfig.container_ttl_seconds` enforces automatic recycle of idle prewarmed containers.

- `None` or `<= 0`: TTL disabled
- `> 0`: container is shut down and re-prewarmed after idle expiry

Example:

```python
RLMConfig(container_ttl_seconds=900)
```

## Redaction Controls

### Tool audit logs

`ToolAuditLogger` supports payload and text redaction via `redact=True`:

```python
from vecna.tools.audit import ToolAuditLogger

audit_logger = ToolAuditLogger(redact=True)
```

Redaction uses `vecna.tools.redaction.redact_all` to mask common secret and PII patterns.

### Langfuse tracing payloads

Set `VECNA_LANGFUSE_LOG_PROMPTS=false` to store redacted metadata (length/hash) instead of raw prompts and outputs.
