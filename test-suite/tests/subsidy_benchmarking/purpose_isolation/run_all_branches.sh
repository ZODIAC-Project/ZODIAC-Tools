#!/usr/bin/env bash
# Runs every purpose-isolation workload branch sequentially via --branch,
# logs each run separately, and prints a pass/fail summary at the end.
#
# Usage:
#   ./run_all_branches.sh [amount_messages]
#
# Example:
#   ./run_all_branches.sh 1

set -u  # undefined vars are an error; NOT -e, since we want to keep going after a failing branch

AMOUNT_MESSAGES="${1:-1}"

# This script lives at tests/subsidy_benchmarking/purpose_isolation/, but
# `uv run pytest` must be invoked from the repo root (test-suite/, where
# pyproject.toml lives). Resolve the repo root relative to the script's own
# location so this works regardless of the directory it's called from.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
cd "$REPO_ROOT" || { echo "Could not cd into repo root: $REPO_ROOT"; exit 1; }

TEST_FILE="tests/subsidy_benchmarking/purpose_isolation/test_workload.py"
LOG_DIR="tests/subsidy_benchmarking/purpose_isolation/test_logs/$(date +%Y%m%d_%H%M%S)"

BRANCHES=(
    "passthrough"
    "no-fault"
    "broker"
    "broker-success"
    "mcp"
    "mcp-success"
    "vector"
    "vector-success"
)

mkdir -p "$LOG_DIR"

RESULTS=()  # entries of the form "branch:STATUS" - avoids declare -A, which
            # needs bash 4+ and isn't supported by macOS's default bash 3.2

echo "================================================================"
echo "Running ${#BRANCHES[@]} branches, amount-messages=$AMOUNT_MESSAGES"
echo "Logs: $LOG_DIR"
echo "================================================================"

for branch in "${BRANCHES[@]}"; do
    log_file="$LOG_DIR/${branch}.log"
    echo ""
    echo ">>> Running branch: $branch"
    echo "    Log: $log_file"

    uv run pytest "$TEST_FILE" -vv -s \
        --branch="$branch" \
        --amount-messages="$AMOUNT_MESSAGES" \
        --model="academic/openai-gpt-oss-120b" \
        > "$log_file" 2>&1

    exit_code=$?
    if [ $exit_code -eq 0 ]; then
        RESULTS+=("$branch:PASS")
        echo "    Result: PASS"
    else
        RESULTS+=("$branch:FAIL (exit $exit_code)")
        echo "    Result: FAIL (exit $exit_code) - see $log_file"
    fi
done

echo ""
echo "================================================================"
echo "SUMMARY"
echo "================================================================"
overall_status=0
for entry in "${RESULTS[@]}"; do
    branch="${entry%%:*}"
    status="${entry#*:}"
    printf "  %-18s %s\n" "$branch" "$status"
    [[ "$status" == PASS ]] || overall_status=1
done
echo "================================================================"

exit $overall_status