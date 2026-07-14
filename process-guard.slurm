#!/bin/bash
#SBATCH --job-name=pg-%j
#SBATCH --output=/dev/null
#SBATCH --error=/dev/null
#SBATCH --time=3-00:00:00
#SBATCH --cpus-per-task=4
#SBATCH --mem=16G
#SBATCH --ntasks=1
#SBATCH --partition=default1
#SBATCH --wait-all-nodes=1

# ============================================================
# Claude Code Process Guard — runs on the compute node
# ============================================================

WORK_DIR="${SLURM_SUBMIT_DIR:-$PWD}"
TMUX_SESSION="claude-${SLURM_JOB_ID}"
MAX_RESTARTS=10
RESTART_DELAY=5

cd "$WORK_DIR" || exit 1

restart_count=0
while [ $restart_count -lt $MAX_RESTARTS ]; do
    # Clean slate
    tmux kill-session -t "$TMUX_SESSION" 2>/dev/null

    # Create a tmux session with a status bar showing job info
    tmux new-session -d -s "$TMUX_SESSION" -c "$WORK_DIR"

    # Set status bar: jobid | host | cwd | attempt
    tmux set-option -t "$TMUX_SESSION" status-left "#[fg=green]PG ${SLURM_JOB_ID}@${SLURMD_NODENAME:-$(hostname)} #[default]"
    tmux set-option -t "$TMUX_SESSION" status-right "#[fg=yellow]attempt $((restart_count + 1))/$MAX_RESTARTS#[default]"
    tmux set-option -t "$TMUX_SESSION" status-interval 1
    tmux set-option -t "$TMUX_SESSION" status on

    # Launch claude in the tmux window
    tmux send-keys -t "$TMUX_SESSION" "cd '$WORK_DIR'; claude" Enter

    # Signal the outer script that tmux is ready
    echo "READY $SLURM_JOB_ID $SLURMD_NODENAME $(hostname)"

    # Wait for claude to finish
    while tmux has-session -t "$TMUX_SESSION" 2>/dev/null; do
        sleep 2
    done

    # Check if guard should stop — write exit code to a temp file
    EXIT_FILE="/tmp/pg-exit-${SLURM_JOB_ID}"
    if [ -f "$EXIT_FILE" ]; then
        rm -f "$EXIT_FILE"
        exit 0
    fi

    restart_count=$((restart_count + 1))
    [ $restart_count -lt $MAX_RESTARTS ] && sleep "$RESTART_DELAY"
done

exit 1