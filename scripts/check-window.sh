#!/usr/bin/env bash
# check-window.sh — Returns current Beijing time pricing window for DeepSeek V4
# Reads peak hour definitions from ~/.claude/night-shift/pricing.json
#
# Output: window=peak|off-peak minutes_remaining=<int> next_transition=HH:MM next_window=peak|off-peak
# Options:
#   --simulate peak|off-peak  Pretend a specific window
#   --json                    Output as JSON

set -euo pipefail

PRICING_FILE="$HOME/.claude/night-shift/pricing.json"
SIMULATE=""
OUTPUT_JSON=false

for arg in "$@"; do
  case "$arg" in
    --simulate)
      SIMULATE="${2:-}"; shift 2 2>/dev/null || shift ;;
    --json)
      OUTPUT_JSON=true; shift ;;
  esac
done

export SIMULATE="$SIMULATE"
export OUTPUT_JSON="$OUTPUT_JSON"
export PRICING_FILE="$PRICING_FILE"

python3 - "$PRICING_FILE" << 'PYEOF'
import json, os, sys
from datetime import datetime, timedelta
import subprocess

pricing_file = sys.argv[1]
simulate = os.environ.get("SIMULATE", "")
output_json = os.environ.get("OUTPUT_JSON", "false") == "true"

if not os.path.exists(pricing_file):
    # Fallback: use hardcoded defaults
    timezone = "Asia/Shanghai"
    peak_windows = [
        {"start": "09:00", "end": "12:00"},
        {"start": "14:00", "end": "18:00"},
    ]
else:
    with open(pricing_file) as f:
        pricing = json.load(f)
    timezone = pricing.get("timezone", "Asia/Shanghai")
    peak_windows = pricing.get("peak_windows", [
        {"start": "09:00", "end": "12:00"},
        {"start": "14:00", "end": "18:00"},
    ])

# Determine current time
if simulate == "peak":
    hour, minute = 10, 0
elif simulate == "off-peak":
    hour, minute = 22, 0
else:
    # Use system date command with TZ for accurate Beijing time
    try:
        tz = timezone.replace("Asia/Shanghai", "Asia/Shanghai")  # normalize
        result = subprocess.run(
            ["date", "+%H %M"],
            env={**os.environ, "TZ": timezone},
            capture_output=True, text=True
        )
        hour_str, minute_str = result.stdout.strip().split()
        hour = int(hour_str)
        minute = int(minute_str)
    except Exception:
        # Fallback: use Python's time (may not match system TZ setting)
        now = datetime.now()
        # Assume UTC+8 if we can't use system TZ
        hour = (now.hour + 8) % 24
        minute = now.minute

total_minutes = hour * 60 + minute

# Parse peak windows
def parse_time(s):
    """Parse HH:MM to minutes since midnight"""
    h, m = s.split(":")
    return int(h) * 60 + int(m)

peak_ranges = []
for pw in peak_windows:
    start = parse_time(pw["start"])
    end = parse_time(pw["end"])
    peak_ranges.append((start, end))

# Check if currently peak
is_peak = False
for start, end in peak_ranges:
    if start <= total_minutes < end:
        is_peak = True
        break

window = "peak" if is_peak else "off-peak"
next_window = "off-peak" if is_peak else "peak"

# Find next transition
transitions = []
for start, end in peak_ranges:
    transitions.append(start)  # off→peak
    transitions.append(end)    # peak→off

next_min = 9999
for t in transitions:
    if t > total_minutes and t < next_min:
        next_min = t

# Wrap around: next is first transition tomorrow + 24h
if next_min == 9999:
    next_min = transitions[0] + 1440  # add 24h in minutes

minutes_remaining = next_min - total_minutes
next_total = total_minutes + minutes_remaining
next_hour = (next_total // 60) % 24
next_minute = next_total % 60
next_transition = f"{next_hour:02d}:{next_minute:02d} CST"

if output_json:
    result = {
        "window": window,
        "minutes_remaining": minutes_remaining,
        "next_transition": next_transition,
        "next_window": next_window,
        "current_time": f"{hour:02d}:{minute:02d} CST",
        "timezone": timezone,
    }
    print(json.dumps(result, ensure_ascii=False))
else:
    print(f"window={window} minutes_remaining={minutes_remaining} next_transition={next_transition} next_window={next_window}")
PYEOF
