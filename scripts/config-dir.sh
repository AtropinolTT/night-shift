#!/bin/bash
# Resolve night-shift config directory across agentic tools.
# Priority: QODER_NS_CONFIG_DIR > .qoder > .claude > .codex > .opencode > .config
set -euo pipefail

CONFIG_DIR="${QODER_NS_CONFIG_DIR:-}"
if [[ -z "$CONFIG_DIR" ]]; then
  for dir in "$HOME/.qoder/night-shift" "$HOME/.claude/night-shift" \
             "$HOME/.codex/night-shift" "$HOME/.opencode/night-shift" \
             "$HOME/.config/night-shift"; do
    if [[ -d "$dir" ]]; then
      CONFIG_DIR="$dir"
      break
    fi
  done
fi
echo "${CONFIG_DIR:-$HOME/.qoder/night-shift}"
