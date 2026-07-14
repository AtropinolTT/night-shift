#!/bin/bash
# DCG hook wrapper for QoderCLI
# Bridges DCG robot-mode exit codes (1=deny) -> QoderCLI exit codes (2=block)

input=$(cat)
command=$(echo "$input" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    ti = data.get('tool_input', {})
    cmd = ti.get('command', '')
    print(cmd)
except Exception:
    print('')
")

# Skip non-commands
if [ -z "$command" ]; then
  exit 0
fi

# Run DCG in robot mode (JSON stdout, silent stderr)
result=$(echo "$input" | dcg hook --robot 2>/dev/null)
exit_code=$?

case $exit_code in
  0)
    exit 0
    ;;
  1)
    >&2 echo "DCG blocked: $command"
    exit 2
    ;;
  *)
    >&2 echo "DCG hook error (exit=$exit_code), allowing: $command"
    exit 0
    ;;
esac
