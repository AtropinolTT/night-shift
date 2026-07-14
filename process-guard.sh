#!/bin/bash
# ============================================================
# Claude Code Process Guard — Interactive Launcher
#
# Usage:
#   ./process-guard.sh                        # CPU partition (default1)
#   ./process-guard.sh -p gpu1 --gres gpu:1   # GPU partition
#
# What it does:
#   1. Submits a Slurm job with the guard script
#   2. Waits for the job to start running
#   3. Auto-SSHes to the compute node and attaches to tmux
#   4. When you detach (Ctrl+b d), gives you a menu
# ============================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
GUARD_SCRIPT="$SCRIPT_DIR/process-guard.slurm"

# ---- Parse extra sbatch flags ----
SBATCH_FLAGS=("$@")

# ---- Submit ----
echo "=== Submitting process guard ==="
echo "Partition: ${SBATCH_FLAGS[*]:-default1 (default)}"

JOB_OUTPUT=$(sbatch "${SBATCH_FLAGS[@]}" "$GUARD_SCRIPT" 2>&1)
echo "$JOB_OUTPUT"

# Extract job ID (accepts both "Submitted batch job N" and raw N)
JOB_ID=$(echo "$JOB_OUTPUT" | grep -oP 'Submitted batch job \K\d+')
if [ -z "$JOB_ID" ]; then
    echo "ERROR: Failed to submit job."
    exit 1
fi

echo "Job ID: $JOB_ID"
echo ""

# ---- Wait for job to start running ----
echo "=== Waiting for job $JOB_ID to start... ==="
while :; do
    STATE=$(sacct -j "$JOB_ID" --format=State --noheader -X 2>/dev/null | head -1 | tr -d ' ')
    [ -z "$STATE" ] && STATE="PENDING"

    NODE=$(squeue -j "$JOB_ID" -o '%N' --noheader 2>/dev/null | head -1 | tr -d ' ')
    [ -z "$NODE" ] && NODE="?"

    printf "\r  State: %-10s  Node: %-10s" "$STATE" "$NODE"

    if [[ "$STATE" == "RUNNING" && -n "$NODE" && "$NODE" != "?" ]]; then
        echo ""
        echo ""
        echo "=== Job running on $NODE ==="
        break
    fi

    # Handle finished jobs
    if [[ "$STATE" =~ ^(COMPLETED|FAILED|CANCELLED|TIMEOUT)$ ]]; then
        echo ""
        echo "Job already finished (state=$STATE)."
        exit 1
    fi

    sleep 3
done

# ---- Cleanup handler: kill the job on exit ----
cleanup() {
    echo ""
    echo "=== Cleaning up ==="
    scancel "$JOB_ID" 2>/dev/null || true
}
trap cleanup EXIT

# ---- SSH into node and attach to tmux ----
echo "=== Connecting to claude session on $NODE ==="
echo "  (use Ctrl+b d to detach — claude keeps running)"
echo ""

# Use the custom SSH port if specified in the cluster config
# Adjust the SSH command to match your cluster
SSH_CMD="ssh -p gpu1 $NODE"

# Loop: keep the user in the driver's seat
ATTEMPT=1
while :; do
    echo "--- Connection attempt $ATTEMPT ---"

    # SSH and attach to tmux
    $SSH_CMD -t "tmux attach -t claude-$JOB_ID 2>/dev/null; echo '--- Session ended ---'"

    # After detach/exit, check if claude is still running
    SESSION_ALIVE=$($SSH_CMD "tmux has-session -t claude-$JOB_ID 2>/dev/null && echo yes || echo no" 2>/dev/null)

    echo ""
    if [ "$SESSION_ALIVE" = "yes" ]; then
        echo "  [d] Detach — keep running"
        echo "  [r] Re-attach to claude"
        echo "  [k] Kill the whole job"
        echo "  [s] Stop guard (stop restarts, keep current claude)"
        echo "  [q] Quit (disconnect, keep running)"
        echo ""
        printf "Action (d/r/k/s/q): "
        read -r action
        case "$action" in
            r) ATTEMPT=$((ATTEMPT + 1)); continue ;;
            k) echo "Killing job $JOB_ID..."; scancel "$JOB_ID" 2>/dev/null; exit 0 ;;
            s) echo "Stopping guard..."; $SSH_CMD "touch /tmp/pg-exit-$JOB_ID" 2>/dev/null
               echo "Sent stop signal. Waiting for guard to exit..."; sleep 3; exit 0 ;;
            q) echo "Disconnecting. Job $JOB_ID still running on $NODE."
               trap - EXIT
               echo "To reconnect later:"; echo "  ssh -p gpu1 $NODE"
               echo "  tmux attach -t claude-$JOB_ID"
               exit 0 ;;
            *) echo "Staying detached."; exit 0 ;;
        esac
    else
        echo "Claude session ended. Job $JOB_ID finished."
        exit 0
    fi
done
