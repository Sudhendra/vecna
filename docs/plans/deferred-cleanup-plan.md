# VECNA Deferred Cleanup — Technical Plan

> **Branch:** `vecna/deferred-cleanup`
> **Source:** Verification audit findings from `docs/third-verification-report-2026-02-19.md`
> **Context:** These items were deferred from the 29-task master implementation PR because
> they are pre-existing code quality debt, intentional design decisions, or low-risk cosmetic
> issues — not functional regressions. All tests pass (1431 pass, 1 skip) on main.

**Recommendation:** This is a single opencode session, not a task-card split. There are
8 items but they're all grep-and-fix refactors, not new feature work. Estimated time:
45-60 minutes in one session. No new files created, no architectural changes.

## Execution Log (2026-02-19, stopped mid-run)

### Completed

- **Item 4** (`SerializableMixin` / HumanModel): completed in `vecna/core/human_model.py`.
  - `HumanModel` now inherits `SerializableMixin`.
  - `to_dict()` overrides were updated to use `super().to_dict()` where custom behavior remains.
  - Verification run: `pytest tests/unit/test_human_model.py -v --tb=short` (37 passed), file-level `ruff check` and format check passed.

- **Item 1** (replace non-entrypoint `except Exception`): completed.
  - Non-entrypoint `except Exception` removed across touched modules.
  - Repo grep now shows `except Exception` only in `vecna/cli/main.py`.
  - Verification run: targeted `ruff check` across modified groups and global grep recheck.

### In Progress / Partial

- **Item 2** (trivial test assertions): partially completed.
  - Updated files:
    - `tests/e2e/test_full_stack.py`
    - `tests/integration/test_pg_memory_store.py`
    - `tests/integration/test_pg_state_manager.py`
    - `tests/integration/test_redis_hot_cache.py`
    - `tests/unit/test_adapters.py`
    - `tests/unit/test_human_model_integration.py`
    - `tests/unit/test_memory_tools.py`
    - `tests/unit/test_temporal_facts.py`
  - Full Item 2 grep cleanup + full test validation are still pending.

### Remaining

- **Item 3:** private attribute access cleanup in tests.
- **Item 5:** remove/constrain `_infer_provider()` heuristics in `vecna/adapters/base.py`.
- **Item 6:** YAML `<HIVE_UPDATE>` deprecation warning/config/prompt updates.
- **Item 7:** Jaccard fallback documentation updates.
- **Item 8:** still intentionally skipped per recommendation.

### Pending Full Verification

- `ruff check .`
- `ruff format --check .`
- `pytest tests/ -v --tb=short`
- Final run of `docs/plans/tasks/full-verification-prompt.md`

---

## Item 1: Amendment 8 — Replace bare `except Exception` (149 occurrences)

**What:** Internal/library code uses `except Exception` instead of specific exception types.
Only top-level entry points (CLI main, HTTP handlers) are allowed to use `except Exception`.

**Scope:**
```bash
grep -rn "except Exception" vecna/ --include="*.py" | grep -v __pycache__ | grep -v test_
```
Last audit found 149 non-entrypoint occurrences.

**Fix rules (from Amendment 8 in `docs/plans/tasks/00-amendments.md`):**

| Module | Replace `except Exception` with |
|---|---|
| `vecna/adapters/*.py` | `openai.APIError`, `anthropic.APIError`, `json.JSONDecodeError`, `asyncio.TimeoutError` |
| `vecna/memory/pg_store.py` | `sqlalchemy.exc.SQLAlchemyError`, `asyncio.TimeoutError` |
| `vecna/core/state_store.py` | `json.JSONDecodeError`, `IOError`, `OSError` |
| `vecna/core/hive_state.py` | `KeyError`, `ValueError`, `json.JSONDecodeError` |
| `vecna/orchestrator/*.py` | `asyncio.TimeoutError`, `ValueError`, `KeyError` |
| `vecna/tools/*.py` | `subprocess.SubprocessError`, `asyncio.TimeoutError`, `OSError` |
| `vecna/channels/*.py` | `asyncio.TimeoutError`, `OSError`, `ValueError` |
| `vecna/integrations/*.py` | `subprocess.SubprocessError`, `asyncio.TimeoutError`, `json.JSONDecodeError` |
| `vecna/security/*.py` | `cryptography.fernet.InvalidToken`, `json.JSONDecodeError`, `ValueError` |
| `vecna/server/*.py` (non-handler) | `json.JSONDecodeError`, `KeyError`, `ValueError` |
| Redis-related code | `redis.RedisError` |

**Approach:**
- For each `except Exception`, read the `try` block to determine what can actually fail.
- Replace with the most specific exception type(s) that cover the actual failure modes.
- If multiple exception types are needed: `except (TypeError, ValueError, KeyError) as e:`
- Keep `except Exception` ONLY in: `vecna/cli/main.py` top-level, HTTP route handlers in `vecna/server/routes.py`, and WebSocket handler.
- After each file, run `ruff check <file>` to ensure no import issues.

**Verification:**
```bash
# Should return ONLY entrypoint files (cli/main.py, server/routes.py)
grep -rn "except Exception" vecna/ --include="*.py" | grep -v __pycache__ | grep -v test_
pytest tests/ -v --tb=short
```

---

## Item 2: Amendment 9 — Fix trivial test assertions (22 occurrences)

**What:** Tests use `isinstance()`, `is not None`, or `len() > 0` as their primary assertion
instead of asserting specific values.

**Scope:**
```bash
grep -rn "assert isinstance\|assert .* is not None\|assert len(.*).*> 0" tests/ --include="*.py" | grep -v __pycache__
```
Last audit found 22 single-trivial-assertion tests.

**Fix rules (from Amendment 9):**
- `assert isinstance(fact, Fact)` → `assert fact.content == "expected_content"`
- `assert result is not None` → `assert result.field == expected_value`
- `assert len(items) > 0` → `assert len(items) == 3` (or whatever the expected count is)

**Approach:**
- For each match, check if it's the PRIMARY assertion of the test or a precondition.
- Precondition checks (e.g. `assert config is not None` before testing config.field) are fine to keep.
- Primary assertions must be replaced with specific value checks.
- Read the test to understand what it's actually testing, then assert the specific expected outcome.

**Verification:**
```bash
# Review remaining matches — should only be precondition checks
grep -rn "assert isinstance\|assert .* is not None\|assert len(.*).*> 0" tests/ --include="*.py" | grep -v __pycache__
pytest tests/ -v --tb=short
```

---

## Item 3: Amendment 11 — Fix private attribute access in tests

**What:** Tests access private attributes (`_channels`, `_sessions`, etc.) directly instead
of using public accessor methods.

**Scope:**
```bash
grep -rn "\._[a-z]" tests/ --include="*.py" | grep -v __pycache__ | grep -v __init__ | grep -v "_mock\|_patch\|_fake\|_stub\|_test\|_create\|_make\|_build\|_get\|_set"
```
Flagged files from audit:
- `tests/unit/test_rewoo_integration.py:183`
- `tests/unit/test_hybrid_search.py:101`
- `tests/integration/test_pg_state_manager.py:540` (and several more lines)

**Fix approach:**
For each private attribute access, choose one of:
1. **Add a public accessor** to the class if one doesn't exist:
   - `obj._channels` → add `obj.list_channels()` method, use that in test
   - `obj._sessions` → add `obj.get_session_count()` method
   - `obj._pending` → add `obj.pending_count` property
2. **Pass via constructor** if the test is setting a private attribute after construction:
   - `obj._store = mock_store` → `obj = MyClass(store=mock_store)`
3. **Use existing public API** if one already exists but the test bypasses it.

**Do NOT:**
- Add public accessors that expose internal mutable state directly (return copies or counts).
- Change the class's actual internal implementation, only add thin accessor methods.

**Verification:**
```bash
grep -rn "\._[a-z]" tests/unit/test_rewoo_integration.py tests/unit/test_hybrid_search.py tests/integration/test_pg_state_manager.py | grep -v __pycache__ | grep -v __init__
pytest tests/ -v --tb=short
```

---

## Item 4: Amendment 7 — HumanModel SerializableMixin inheritance

**What:** `HumanModel` in `vecna/core/human_model.py` does not inherit from `SerializableMixin`,
and several dataclasses retain custom `to_dict()` overrides that duplicate the mixin's logic.

**Scope:**
```bash
# HumanModel not inheriting
grep -n "class HumanModel" vecna/core/human_model.py

# Custom to_dict() that could use the mixin
grep -rn "def to_dict" vecna/ --include="*.py" | grep -v __pycache__ | grep -v test_
```

**Fix approach:**
1. Make `HumanModel` inherit from `SerializableMixin`:
   ```python
   from vecna.core.types import SerializableMixin

   @dataclass
   class HumanModel(SerializableMixin):
   ```
2. For each custom `to_dict()` override, check if the mixin's generic implementation handles it.
   - If yes: delete the custom `to_dict()`, rely on mixin.
   - If no (custom logic like nested serialization): keep the override but have it call `super().to_dict()` and modify the result.
3. Same for `Preference`, `CommunicationStyle`, `InteractionPattern`, `EmotionalContext`.

**Verification:**
```bash
# Confirm inheritance
grep -A2 "class HumanModel\|class Preference\|class CommunicationStyle\|class InteractionPattern\|class EmotionalContext" vecna/core/human_model.py

# Test round-trip serialization still works
pytest tests/unit/test_human_model.py -v --tb=short
pytest tests/ -v --tb=short
```

---

## Item 5: Amendment 4 — Remove _infer_provider() heuristics

**What:** `vecna/adapters/base.py` has `_infer_provider()` that uses substring heuristics
alongside the proper `Provider` enum match routing. The heuristics should be removed so
the enum is the single source of truth.

**Scope:**
```bash
grep -n "_infer_provider\|provider ==" vecna/adapters/base.py
```

**Fix approach:**
- Delete or gut `_infer_provider()` — it should not be needed if config always specifies a `Provider` enum value.
- If backward compatibility is needed for configs that don't specify a provider, convert `_infer_provider()` to map known model name patterns to `Provider` enum values explicitly (not substring matching), and log a deprecation warning.
- The `create_adapter()` function should use ONLY `match config.provider` on the enum.

**Verification:**
```bash
grep -n "provider ==" vecna/adapters/base.py  # Should be zero or only in enum match
pytest tests/unit/test_native_adapters.py tests/unit/test_adapters.py -v --tb=short
pytest tests/ -v --tb=short
```

---

## Item 6: Kill Signal 3 — Remove legacy YAML HIVE_UPDATE parser

**What:** `vecna/adapters/base.py` still contains the `<HIVE_UPDATE>` YAML parsing path
and the prompt instructs models to return YAML blocks. This was the #3 kill signal.

**Context:** This was intentionally deferred because it serves as a fallback for models
that don't support native tool/function calling. However, now that Task 7 (tool calling)
and Task 21 (native adapters) are complete, the fallback should be deprecated.

**Scope:**
```bash
grep -rn "HIVE_UPDATE\|yaml.safe_load\|hive_update.*yaml" vecna/adapters/ --include="*.py" | grep -v __pycache__ | grep -v test_
```

**Fix approach:**
- **Do NOT delete yet** — add a deprecation warning when the YAML path is hit:
  ```python
  import warnings
  warnings.warn(
      "YAML HIVE_UPDATE parsing is deprecated. Configure native tool calling for this adapter.",
      DeprecationWarning,
      stacklevel=2,
  )
  ```
- Update the adapter prompt template to prefer tool calling and only mention YAML as last resort.
- Add a config flag `allow_yaml_fallback: bool = True` so it can be disabled per adapter.
- Log when YAML fallback is used so it's visible in observability.

**Verification:**
```bash
pytest tests/unit/test_tool_calling_adapter.py tests/unit/test_adapters.py -v --tb=short
pytest tests/ -v --tb=short
```

---

## Item 7: Kill Signal 5 — Document Jaccard fallback as intentional

**What:** Jaccard word overlap remains in `ConsensusEngine._is_similar()` and
`HiveState.add_fact()` as a fallback when embeddings are unavailable. The audit flagged
this as "NOT FIXED" but it's actually correct behavior.

**Fix:** Add docstring clarification, not code changes:
- In `ConsensusEngine._is_similar()`: document that Jaccard is the fallback when embeddings are not available.
- In `HiveState.add_fact()`: document that cosine similarity is primary (Amendment 14), Jaccard is fallback-only.
- Add a brief note in `docs/architecture.md` under the consensus section explaining the similarity hierarchy: pgvector cosine (database) → in-memory cosine (when embeddings present) → Jaccard (text-only fallback).

**Verification:**
```bash
# Just confirm docs build and tests pass
pytest tests/ -v --tb=short
```

---

## Item 8: File inventory count mismatch in master plan

**What:** Master plan "New Files (26)" header says 26 but the list contains 28 entries.
Extra files created beyond the list: `vecna/core/encrypted_state_store.py`,
`vecna/observability/dashboard.py`, `vecna/tui/__init__.py`.

**Fix:** This is a documentation-only fix:
- Update the master plan's "New Files" count to match actual list.
- Or simply leave it — the plan is a historical document and the code is the source of truth.

**Recommendation:** Skip this. Not worth touching the master plan post-merge.

---

## Execution Order

Items 1-6 have actual code changes. Items 7-8 are docs-only or skip.

Run in this order to minimize test breakage between steps:
1. **Item 4** (SerializableMixin) — changes class signatures, could affect serialization tests
2. **Item 1** (except Exception) — largest change, highest risk of typos
3. **Item 2** (trivial assertions) — test-only changes
4. **Item 3** (private attributes) — test + minor class changes
5. **Item 5** (Provider heuristics) — adapter routing change
6. **Item 6** (YAML deprecation) — adapter change
7. **Item 7** (Jaccard docs) — docs only
8. **Item 8** (skip)

After each item: `pytest tests/ -v --tb=short && ruff check . && ruff format --check .`

Final commit: `git add -A && git commit -m "fix: resolve deferred code quality items — amendments 4,7,8,9,11 + YAML deprecation"`

Or commit per-item if you prefer granular history.

---

## Post-Cleanup Verification

After all items are done, run the full verification prompt from `docs/plans/tasks/full-verification-prompt.md`
one final time. Expected result:
- All 16 amendments PASS (no more PARTIAL or FAIL)
- All kill signals FIXED or DEFERRED-WITH-DEPRECATION
- Test count >= 1431 (may increase from new error tests in Item 2)
- 0 failures, 0 errors
- VERDICT: READY TO MERGE
