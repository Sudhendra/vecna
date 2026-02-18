#!/usr/bin/env bash
# run-vecna-tasks.sh — Execute VECNA task cards sequentially via OpenCode
#
# Usage:
#   ./run-vecna-tasks.sh                    # Run all tasks in dependency order
#   ./run-vecna-tasks.sh 1 2 3              # Run specific tasks
#   ./run-vecna-tasks.sh --from 6           # Resume from task 6 onward
#   ./run-vecna-tasks.sh --phase 1          # Run Phase 1 only (tasks 1-12)
#   ./run-vecna-tasks.sh --dry-run 1 2 3    # Show what would run, don't execute
#
# Requirements:
#   - OpenCode CLI installed (opencode)
#   - Opus 4.6 enabled via GitHub Copilot Pro+
#   - This script in your project root alongside docs/plans/tasks/
#
# Configuration:
TASK_DIR="docs/plans/tasks"
AMENDMENTS="${TASK_DIR}/00-amendments.md"
PROGRESS="${TASK_DIR}/PROGRESS.md"
LOG_DIR=".vecna-runs"

set -euo pipefail

# ─── macOS compatibility ──────────────────────────────────────────────────────

# Detect sed variant (GNU vs BSD)
if sed --version >/dev/null 2>&1; then
    SED_CMD="sed"
    SED_INPLACE_FLAG="-i"
else
    SED_CMD="sed"
    SED_INPLACE_FLAG="-i ''"
fi

sed_inplace() {
    if sed --version >/dev/null 2>&1; then
        sed -i "$@"
    else
        sed -i '' "$@"
    fi
}

# ─── Helpers ──────────────────────────────────────────────────────────────────

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log()   { echo -e "${BLUE}[vecna]${NC} $*"; }
ok()    { echo -e "${GREEN}[  OK ]${NC} $*"; }
warn()  { echo -e "${YELLOW}[WARN ]${NC} $*"; }
err()   { echo -e "${RED}[FAIL ]${NC} $*"; }

mkdir -p "$LOG_DIR"

# ─── Execution order ─────────────────────────────────────────────────────────

PHASE1_ORDER=(1 2 3 4 5 6 7 8 9 10 11 12)
PHASE2_ORDER=(13 14 15 16 17 18 19 20 21)
PHASE3_ORDER=(22 23 24 25 26 27 28 29)
ALL_ORDER=("${PHASE1_ORDER[@]}" "${PHASE2_ORDER[@]}" "${PHASE3_ORDER[@]}")

# ─── Parse arguments ─────────────────────────────────────────────────────────

DRY_RUN=false
TASKS_TO_RUN=()

while [[ $# -gt 0 ]]; do
    case "$1" in
        --dry-run)
            DRY_RUN=true
            shift
            ;;
        --from)
            FROM_TASK="$2"
            shift 2
            FOUND=false
            for t in "${ALL_ORDER[@]}"; do
                if [[ "$t" -ge "$FROM_TASK" ]] || $FOUND; then
                    FOUND=true
                    TASKS_TO_RUN+=("$t")
                fi
                if [[ "$t" -eq "$FROM_TASK" ]]; then
                    FOUND=true
                fi
            done
            ;;
        --phase)
            PHASE="$2"
            shift 2
            case "$PHASE" in
                1) TASKS_TO_RUN=("${PHASE1_ORDER[@]}") ;;
                2) TASKS_TO_RUN=("${PHASE2_ORDER[@]}") ;;
                3) TASKS_TO_RUN=("${PHASE3_ORDER[@]}") ;;
                *) err "Unknown phase: $PHASE"; exit 1 ;;
            esac
            ;;
        *)
            TASKS_TO_RUN+=("$1")
            shift
            ;;
    esac
done

# Default: run all
if [[ ${#TASKS_TO_RUN[@]} -eq 0 ]]; then
    TASKS_TO_RUN=("${ALL_ORDER[@]}")
fi

# ─── Validate ────────────────────────────────────────────────────────────────

if [[ ! -f "$AMENDMENTS" ]]; then
    err "Amendments file not found: $AMENDMENTS"
    err "Expected task files in $TASK_DIR/"
    exit 1
fi

if ! command -v opencode &>/dev/null; then
    err "opencode CLI not found. Install: curl -fsSL https://opencode.ai/install.sh | bash"
    exit 1
fi

# ─── Find task file by number ────────────────────────────────────────────────

find_task_file() {
    local num
    num=$(printf "%02d" "$1")
    local found
    found=$(find "$TASK_DIR" -name "${num}-*.md" -not -name "00-*" | head -1)
    echo "$found"
}

# ─── Update progress safely (macOS + Linux) ──────────────────────────────────

update_progress() {
    local task_num="$1"
    local new_status="$2"
    local commit_hash="${3:-}"

    [[ -f "$PROGRESS" ]] || return 0

    if [[ -n "$commit_hash" ]]; then
        sed_inplace "s/| ${task_num} |.*| \`todo\` |/| ${task_num} | ... | \`${new_status}\` | ${commit_hash} |/" "$PROGRESS" 2>/dev/null || true
        sed_inplace "s/| ${task_num} |.*| \`in_progress\` |/| ${task_num} | ... | \`${new_status}\` | ${commit_hash} |/" "$PROGRESS" 2>/dev/null || true
    else
        sed_inplace "s/| ${task_num} |.*| \`todo\` |/| ${task_num} | ... | \`${new_status}\` | |/" "$PROGRESS" 2>/dev/null || true
        sed_inplace "s/| ${task_num} |.*| \`in_progress\` |/| ${task_num} | ... | \`${new_status}\` | |/" "$PROGRESS" 2>/dev/null || true
    fi
}

# ─── Run a single task ───────────────────────────────────────────────────────

run_task() {
    local task_num="$1"
    local task_file
    task_file=$(find_task_file "$task_num")

    if [[ -z "$task_file" ]]; then
        err "No task file found for task $task_num"
        return 1
    fi

    local task_name
    task_name=$(head -1 "$task_file" | sed 's/^# //')
    local run_log="${LOG_DIR}/task-${task_num}-$(date +%Y%m%d-%H%M%S).log"

    log "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    log "Starting: ${task_name}"
    log "File:     ${task_file}"
    log "Log:      ${run_log}"
    log "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

    if $DRY_RUN; then
        warn "[DRY RUN] Would execute: $task_file"
        return 0
    fi

    update_progress "$task_num" "in_progress"

    # Build the prompt: amendments + task content
    local prompt
    prompt="You are implementing a specific task from the VECNA master implementation plan.

STEP 1: Read the amendments below carefully — these are BINDING rules.
STEP 2: Read the task specification below — implement EXACTLY what it says.
STEP 3: Follow the TDD workflow: write tests first, verify they fail, implement, verify they pass.
STEP 4: Run the full test suite for regressions: pytest tests/ -v --tb=short
STEP 5: Run ruff check . and ruff format --check .
STEP 6: Commit with message: feat: <description>

=== AMENDMENTS (BINDING) ===
$(cat "$AMENDMENTS")

=== TASK TO IMPLEMENT ===
$(cat "$task_file")"

    # Execute via OpenCode
    local start_time
    start_time=$(date +%s)

    if opencode run "$prompt" > "$run_log" 2>&1; then
        local end_time
        end_time=$(date +%s)
        local duration=$(( end_time - start_time ))
        ok "${task_name} — completed in ${duration}s"

        local commit_hash
        commit_hash=$(git rev-parse --short HEAD 2>/dev/null || echo "no-commit")
        update_progress "$task_num" "done" "$commit_hash"

        return 0
    else
        local end_time
        end_time=$(date +%s)
        local duration=$(( end_time - start_time ))
        err "${task_name} — FAILED after ${duration}s (see ${run_log})"

        update_progress "$task_num" "failed"

        return 1
    fi
}

# ─── Main ─────────────────────────────────────────────────────────────────────

log "VECNA Task Runner"
log "Tasks to run: ${TASKS_TO_RUN[*]}"
log "Agent: opencode (Opus 4.6 via GitHub Copilot Pro+)"
log ""

PASSED=0
FAILED=0

for task_num in "${TASKS_TO_RUN[@]}"; do
    if run_task "$task_num"; then
        PASSED=$((PASSED + 1))
    else
        FAILED=$((FAILED + 1))
        warn "Task $task_num failed — continuing with remaining tasks"
    fi
    echo ""
done

# ─── Summary ──────────────────────────────────────────────────────────────────

log "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
log "SUMMARY"
log "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
ok  "Passed:  $PASSED"
[[ $FAILED -gt 0 ]] && err "Failed:  $FAILED" || log "Failed:  0"
log ""
log "Run logs: ${LOG_DIR}/"
log "Progress: ${PROGRESS}"
