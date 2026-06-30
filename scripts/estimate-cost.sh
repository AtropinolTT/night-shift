#!/usr/bin/env bash
# estimate-cost.sh — Estimate DeepSeek V4 API cost for a job
# Reads pricing from ~/.claude/night-shift/pricing.json
#
# Usage: estimate-cost.sh --tokens <N> --model <pro|flash> --window <peak|off-peak> [--json]
#   --tokens N             Estimated total tokens
#   --model pro|flash      DeepSeek V4 model variant
#   --window peak|off-peak Current pricing window
#   --input-ratio 0.5      Fraction of tokens that are input (default 0.5)
#   --json                 Output as JSON

set -euo pipefail

TOKENS=""
MODEL=""
WINDOW=""
INPUT_RATIO=0.5
OUTPUT_JSON=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    --tokens) TOKENS="$2"; shift 2 ;;
    --model) MODEL="$2"; shift 2 ;;
    --window) WINDOW="$2"; shift 2 ;;
    --input-ratio) INPUT_RATIO="$2"; shift 2 ;;
    --json) OUTPUT_JSON=true; shift ;;
    *) echo "Unknown option: $1" >&2; exit 1 ;;
  esac
done

if [[ -z "$TOKENS" || -z "$MODEL" || -z "$WINDOW" ]]; then
  echo "Usage: estimate-cost.sh --tokens <N> --model <pro|flash> --window <peak|off-peak> [--json]" >&2
  exit 1
fi

export NS_TOKENS="$TOKENS"
export NS_MODEL="$MODEL"
export NS_WINDOW="$WINDOW"
export NS_INPUT_RATIO="$INPUT_RATIO"
export NS_OUTPUT_JSON="$OUTPUT_JSON"
export NS_PRICING_FILE="$HOME/.claude/night-shift/pricing.json"

python3 - "$NS_PRICING_FILE" << 'PYEOF'
import json, os, sys

pricing_file = sys.argv[1]
if not os.path.exists(pricing_file):
    print(f"Error: pricing.json not found at {pricing_file}", file=sys.stderr)
    sys.exit(1)

with open(pricing_file) as f:
    pricing = json.load(f)

model_key = os.environ["NS_MODEL"]
window_raw = os.environ["NS_WINDOW"]
# Normalize off-peak → off_peak for JSON key lookup
window_key = window_raw.replace("-", "_")
tokens = int(os.environ["NS_TOKENS"])
input_ratio = float(os.environ["NS_INPUT_RATIO"])
output_json = os.environ["NS_OUTPUT_JSON"] == "true"

model = pricing["models"][model_key]
rates = model[window_key]
name = model["name"]

try:
    tokens_m = tokens / 1_000_000
    input_tokens_m = tokens_m * input_ratio
    output_tokens_m = tokens_m * (1 - input_ratio)
except OverflowError:
    # Extreme token count — cost is effectively infinite
    result = {
        "model": model_key,
        "model_name": name,
        "window": window_raw,
        "tokens": tokens,
        "error": "token count too large for estimation",
        "total_cost_cny": float('inf'),
    }
    print(json.dumps(result, ensure_ascii=False))
    sys.exit(0)

# Cache miss (worst case) for input
input_rate = rates["input_cache_miss"]
output_rate = rates["output"]

input_cost = input_tokens_m * input_rate
output_cost = output_tokens_m * output_rate
total_cost = input_cost + output_cost

result = {
    "model": model_key,
    "model_name": name,
    "window": window_raw,
    "tokens": tokens,
    "tokens_millions": round(tokens_m, 2),
    "input_tokens_m": round(input_tokens_m, 6),
    "output_tokens_m": round(output_tokens_m, 6),
    "input_rate_cny_per_m": input_rate,
    "output_rate_cny_per_m": output_rate,
    "input_cost_cny": round(input_cost, 4),
    "output_cost_cny": round(output_cost, 4),
    "total_cost_cny": round(total_cost, 4),
}

# Off-peak comparison when in peak window
if window_key == "peak":
    off_rates = model["off_peak"]
    off_input = input_tokens_m * off_rates["input_cache_miss"]
    off_output = output_tokens_m * off_rates["output"]
    off_total = off_input + off_output
    premium = total_cost - off_total
    result["offpeak_cost_cny"] = round(off_total, 4)
    result["premium_cny"] = round(premium, 4)

if output_json:
    print(json.dumps(result, ensure_ascii=False))
else:
    print(f"Model:  {name}")
    print(f"Window: {window_raw}")
    print(f"Tokens: {tokens:,} (~{tokens_m:.2f}M)")
    print(f"Input cost:   {input_cost:.4f} CNY ({input_tokens_m:.6f}M × {input_rate} CNY/M)")
    print(f"Output cost:  {output_cost:.4f} CNY ({output_tokens_m:.6f}M × {output_rate} CNY/M)")
    print(f"Total:        {total_cost:.4f} CNY")
    if window_key == "peak":
        print(f"Off-peak:     {off_total:.4f} CNY (save {premium:.4f} CNY — 2× premium)")
PYEOF
