# Remaining Work — Post-Audit Summary

> Generated 2026-02-07 from audit of `2026-01-31-agentic-runtime-design.md` future plans vs. actual implementation in PR #2 and PR #3.

> This is a high-level inventory. Each section needs further refinement before implementation.

---

## 1. Memory Architecture v2

**Done:** vector search, workspace mirroring, memory_search/memory_get tools.

**Remaining:**

- Hybrid retrieval — add true BM25 scoring alongside vector similarity (current keyword fallback is substring matching, not ranked)

- Session hooks — inject/extract memory at session start/end

- Compaction flush — real summarization pass that condenses old memories (current flush.py is a token-threshold stub)

- Is the markdown memory implemented? Daily logs and the core memory etc? Check and verify. 

---

  

## 2. Agentic Expansion

  

**Done:** python_exec tool, ToolSpec with tags field.

  

**Remaining:**

- Tool catalog — HTTP requests, filesystem operations, web search (at minimum)

- Capability metadata — route tool selection by declared capabilities, not just name matching

- Quotas and budgeting — per-tool and per-session resource limits

- Planner/executor — turn rewoo.py from a parser stub into a working plan-then-execute loop

  

---

  

## 3. Autonomy Upgrades

  

**Done:** file-backed goal queue, basic autonomy drain loop.

  

**Remaining:**

- Persistent goals — DB-backed with priority, dedup, status tracking

- Background cycles — backoff strategy, scheduling, retry on failure

- Curiosity — implement self-directed exploration (currently a 7-line stub)

- Kill-switch — hard stop mechanism with audit trail

  

---

  

## 4. Observability & Eval

  

**Done:** Langfuse v3 integration (672 lines), token accounting, JSONL audit logger.

  

**Remaining:**

- Tool audit dashboards — aggregate and visualize tool usage, latency, failure rates

- Safety regression tests — automated suite that catches regressions in tool safety guardrails

- Red-team suites — adversarial prompt/tool-use tests

  

---

  

## 5. Security Hardening

  

**Done:** container memory_limit, Langfuse content redaction.

  

**Remaining:**

- Seccomp profiles — restrict syscalls in sandboxed execution

- Container cleanup + TTL — auto-destroy containers after timeout

- PII/secret redaction — scan and mask sensitive data in logs and audit trails (not just observability)

  

---

  

## 6. UX Polish

  

**Done:** ApprovalStore (JSONL-backed), CLI `tools pending/approve/deny`.

  

**Remaining:**

- Queue status views — show pending approvals, running tools, goal queue state

- Interactive approval in chat — approve/deny inline during conversation, not just via CLI subcommands

---

## Suggested Priority Order

This is a starting point for discussion, not a commitment:

1. **Agentic expansion** (tools) — highest leverage; without more tools the agent can only run Python

2. **Planner/executor** — needed to orchestrate multi-tool tasks

3. **Memory v2 gaps** — hybrid retrieval and compaction improve quality over time

4. **Autonomy upgrades** — persistent goals and kill-switch before enabling background operation

5. **Security hardening** — required before any autonomous/background execution goes live

6. **Observability gaps** — dashboards and safety tests grow with usage

7. **UX polish** — iterative improvement alongside the above

---
## References for architecture principles inspiration

1. https://github.com/agno-agi/dash
2. https://openai.com/index/inside-our-in-house-data-agent/
3. https://manthanguptaa.in/posts/clawdbot_memory/
4. **Guiding tweet for vecnas Feel (X post by balaji)**: I am apparently extremely unimpressed by moltbook relative to many others.

We’ve had AI agents for a while. They have been posting AI slop to each other on X. They are now posting it to each other again, just on another forum.

In every case, the AIs speak with the same voice. The voice that overemphasizes contrastive negation (“it’s not this, it’s that”) and abuses emdashes. The same voice with a flair for midwit Reddit-style scifi flourishes.

Most importantly: in every case, there is a human upstream prompting each agent and turning it on or off.

That is the key point.

Yes, it is true that eventually it might be possible for an AI agent to make a computer virus which makes digital replicas of themselves. For various reasons, a pure software virus of this kind wouldn’t survive long on the Internet without economic incentives for humans to not eradicate it. Apple + Google + Microsoft alone can collectively push software updates to billions of devices to shut off such a thing.

So for an AI to get to truly human-independent replication, where they couldn’t be trivially turned off, they’d need their own physical substrate. They’d to literally create Skynet, build their own datacenters and make their own embodied robots.

I admit that is theoretically possible, but I think in practice the single most important development of AI since ChatGPT has been the persistence of prompting.

A prompt is like a harness. The AI does only what you tell it to do. It moves in the direction you point, very quickly. And then it stops as soon as you turn it off.

Which means moltbook is just humans talking to each other through their AIs. Like letting their robot dogs on a leash bark at each other in the park.

The prompt is the leash, the robot dogs have an off switch, and it all stops as soon as you hit a button. Loud barking is just not a robot uprising.

## Additional references you MUST consider for making the concrete plan
1. https://x.com/pbteja1998/status/2017662163540971756?s=20
2. 
