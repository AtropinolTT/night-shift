"""Fusion quality baseline test (T9.3).

Runs 20 diverse prompts through ``fusion_dispatch`` with mocked models
to establish a v1-alpha quality baseline.  No real API calls — all model
responses are controlled to produce different perspectives per model,
allowing the synthesis step to be tested deterministically.

Test categories: trivia (5), reasoning (5), coding (5),
                summarization (3), translation (2) — total 20.

Metrics recorded per prompt:
- best_single_score (0-5 heuristic)
- fusion_score (0-5 heuristic)
- delta (fusion - best_single)
- cost, wall_time_ms
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from companion.fusion.dispatch import ModelResponse, fusion_dispatch

# ═══════════════════════════════════════════════════════════════════════════
#  Mock _call_model — zero real API calls
# ═══════════════════════════════════════════════════════════════════════════

_CALL_LOG: list[dict[str, Any]] = []


def _detect_synthesis_prompt(prompt: str) -> str | None:
    """Return the original prompt if this is a synthesis call, else None."""
    if "You are a synthesis engine" not in prompt:
        return None
    for entry in PROMPT_REGISTRY:
        if entry["prompt"] in prompt:
            return entry["prompt"]
    return None


def _mock_call_model(model: str, prompt: str, timeout_s: int = 60) -> ModelResponse:
    """Mock returning controlled, different responses per model.

    For regular dispatch: looks up the prompt in PROMPT_REGISTRY and
    returns the pre-defined response for *model*.

    For synthesis: detects the "synthesis engine" marker, extracts the
    original prompt, and returns the pre-defined synthesis answer.
    """
    _CALL_LOG.append({"model": model, "prompt_len": len(prompt)})

    input_tokens = max(1, len(prompt) // 4)

    # ── synthesis path ──────────────────────────────────────────────────
    original = _detect_synthesis_prompt(prompt)
    if original is not None:
        for entry in PROMPT_REGISTRY:
            if entry["prompt"] == original:
                synth = entry["synthesis"]
                return ModelResponse(
                    model=model,
                    response=synth,
                    cost=0.000_002,
                    input_tokens=input_tokens,
                    output_tokens=max(1, len(synth) // 4),
                    wall_time_ms=1,
                )
        return ModelResponse(
            model=model,
            response="SYNTHESIS: no matching prompt found.",
            cost=0.000_001,
            input_tokens=input_tokens,
            output_tokens=10,
            wall_time_ms=1,
        )

    # ── regular dispatch path ───────────────────────────────────────────
    for entry in PROMPT_REGISTRY:
        if prompt == entry["prompt"]:
            resp = entry["responses"].get(model, f"[{model}] No response configured.")
            return ModelResponse(
                model=model,
                response=resp,
                cost=0.000_001,
                input_tokens=input_tokens,
                output_tokens=max(1, len(resp) // 4),
                wall_time_ms=1,
            )

    # ── fallback ────────────────────────────────────────────────────────
    return ModelResponse(
        model=model,
        response=f"[{model}] Generic fallback for: {prompt[:100]}",
        cost=0.000_001,
        input_tokens=input_tokens,
        output_tokens=15,
        wall_time_ms=1,
    )


# ═══════════════════════════════════════════════════════════════════════════
#  Heuristic scoring (0-5) — proxy for answer quality
# ═══════════════════════════════════════════════════════════════════════════


def _score_answer(answer: str, expected_keywords: list[str]) -> int:
    """Score an answer 0-5 based on keyword coverage and substance.

    - 1 point per expected keyword found (max 3)
    - 1 point if answer > 20 chars (non-trivial)
    - 1 point if answer > 80 chars (substantive)
    """
    score = 0
    for kw in expected_keywords[:3]:
        if kw.casefold() in answer.casefold():
            score += 1
    if len(answer) > 20:
        score += 1
    if len(answer) > 80:
        score += 1
    return score


# ═══════════════════════════════════════════════════════════════════════════
#  Prompt registry — 20 prompts × 2 model responses × 1 synthesis
# ═══════════════════════════════════════════════════════════════════════════

PROMPT_REGISTRY: list[dict[str, Any]] = [
    # ────────────────── TRIVIA (1-5) ────────────────────────────────────
    {
        "id": 1,
        "category": "trivia",
        "prompt": "What is the capital of France?",
        "keywords": ["paris", "france", "capital"],
        "responses": {
            "deepseek-v4-pro": (
                "The capital of France is Paris. Paris has been the capital since "
                "the 10th century and is one of the most populous cities in Europe, "
                "with approximately 2.1 million residents within its city limits "
                "and over 12 million in the metropolitan area."
            ),
            "deepseek-v4-flash": "Paris.",
        },
        "synthesis": (
            "EXPERIMENTAL — Model Fusion (v1-alpha)\n\n"
            "The capital of France is Paris — a city that has served as the "
            "nation's capital since the 10th century. It is one of Europe's "
            "most populous cities, with over 2 million residents in the city "
            "proper and more than 12 million in the greater metropolitan area."
        ),
    },
    {
        "id": 2,
        "category": "trivia",
        "prompt": "Who painted the Mona Lisa?",
        "keywords": ["leonardo", "vinci", "lisa"],
        "responses": {
            "deepseek-v4-pro": (
                "The Mona Lisa was painted by Leonardo da Vinci, the Italian "
                "Renaissance polymath, between approximately 1503 and 1519. "
                "It is an oil painting on a poplar wood panel and is housed "
                "in the Louvre Museum in Paris."
            ),
            "deepseek-v4-flash": (
                "Leonardo da Vinci painted the Mona Lisa."
            ),
        },
        "synthesis": (
            "EXPERIMENTAL — Model Fusion (v1-alpha)\n\n"
            "The Mona Lisa was painted by the Italian Renaissance master "
            "Leonardo da Vinci between approximately 1503 and 1519. This iconic "
            "oil-on-poplar portrait is displayed at the Louvre Museum in Paris "
            "and is widely considered one of the most famous paintings in the world."
        ),
    },
    {
        "id": 3,
        "category": "trivia",
        "prompt": "What is the chemical symbol for gold?",
        "keywords": ["au", "aurum", "gold"],
        "responses": {
            "deepseek-v4-pro": (
                "The chemical symbol for gold is Au, derived from the Latin "
                "word 'aurum' meaning 'shining dawn' or 'glow of sunrise'. "
                "Gold's atomic number is 79 and it is a transition metal in "
                "group 11 of the periodic table."
            ),
            "deepseek-v4-flash": "Au.",
        },
        "synthesis": (
            "EXPERIMENTAL — Model Fusion (v1-alpha)\n\n"
            "The chemical symbol for gold is Au, from the Latin 'aurum'. "
            "Gold has atomic number 79 and belongs to group 11 of the "
            "periodic table as a transition metal."
        ),
    },
    {
        "id": 4,
        "category": "trivia",
        "prompt": "In which year did World War II end?",
        "keywords": ["1945", "world", "war"],
        "responses": {
            "deepseek-v4-pro": (
                "World War II ended in 1945. Germany surrendered on May 8, 1945 "
                "(V-E Day), and Japan surrendered on September 2, 1945 (V-J Day) "
                "following the atomic bombings of Hiroshima and Nagasaki."
            ),
            "deepseek-v4-flash": "1945.",
        },
        "synthesis": (
            "EXPERIMENTAL — Model Fusion (v1-alpha)\n\n"
            "World War II ended in 1945, with Germany's surrender on May 8 "
            "(Victory in Europe Day) and Japan's formal surrender on "
            "September 2 (Victory over Japan Day)."
        ),
    },
    {
        "id": 5,
        "category": "trivia",
        "prompt": "What is the speed of light in a vacuum?",
        "keywords": ["299", "meter", "second"],
        "responses": {
            "deepseek-v4-pro": (
                "The speed of light in a vacuum is approximately 299,792,458 "
                "meters per second (exactly 299,792,458 m/s by definition since 1983). "
                "In more familiar units, this is about 186,282 miles per second. "
                "This constant, denoted c, is fundamental to physics."
            ),
            "deepseek-v4-flash": "299,792,458 meters per second.",
        },
        "synthesis": (
            "EXPERIMENTAL — Model Fusion (v1-alpha)\n\n"
            "The speed of light in a vacuum is exactly 299,792,458 meters per second "
            "(approximately 186,282 miles per second). This constant, denoted as c, "
            "has been defined as an exact value since 1983 and is fundamental to "
            "modern physics."
        ),
    },
    # ────────────────── REASONING (6-10) ────────────────────────────────
    {
        "id": 6,
        "category": "reasoning",
        "prompt": (
            "If all dogs are mammals and all mammals are animals, "
            "are all dogs animals? Explain."
        ),
        "keywords": ["dogs", "animals", "transitive"],
        "responses": {
            "deepseek-v4-pro": (
                "Yes, all dogs are animals. This follows from the transitive property "
                "of categorical syllogisms: if A ⊆ B (dogs are a subset of mammals) "
                "and B ⊆ C (mammals are a subset of animals), then A ⊆ C (dogs are "
                "a subset of animals). More formally, for any x: dog(x) → mammal(x) "
                "and mammal(x) → animal(x), therefore dog(x) → animal(x)."
            ),
            "deepseek-v4-flash": (
                "Yes. All dogs are animals because they are mammals, and "
                "mammals are animals."
            ),
        },
        "synthesis": (
            "EXPERIMENTAL — Model Fusion (v1-alpha)\n\n"
            "Yes, all dogs are animals. This conclusion follows from the transitive "
            "property of categorical logic: dogs are a subset of mammals, mammals "
            "are a subset of animals, therefore dogs are a subset of animals. "
            "Formally: dog(x) → mammal(x) → animal(x), so dog(x) → animal(x)."
        ),
    },
    {
        "id": 7,
        "category": "reasoning",
        "prompt": (
            "A bat and a ball cost $1.10 in total. The bat costs "
            "$1.00 more than the ball. How much does the ball cost?"
        ),
        "keywords": ["0.05", "5 cents", "ball"],
        "responses": {
            "deepseek-v4-pro": (
                "The ball costs $0.05. Here's the reasoning:\n"
                "Let b = cost of ball, t = cost of bat.\n"
                "We know: t + b = 1.10 and t = b + 1.00\n"
                "Substituting: (b + 1.00) + b = 1.10\n"
                "2b + 1.00 = 1.10 → 2b = 0.10 → b = 0.05\n"
                "So the ball costs 5 cents. The common intuitive mistake is to "
                "say $0.10, but that would make the bat $1.10 for a total of $1.20."
            ),
            "deepseek-v4-flash": "5 cents.",
        },
        "synthesis": (
            "EXPERIMENTAL — Model Fusion (v1-alpha)\n\n"
            "The ball costs $0.05 (5 cents). Solving the system of equations:\n"
            "bat + ball = 1.10 and bat = ball + 1.00\n"
            "Substituting gives 2*ball + 1.00 = 1.10, so ball = 0.05.\n"
            "The intuitive but incorrect answer of 10 cents would make the total $1.20."
        ),
    },
    {
        "id": 8,
        "category": "reasoning",
        "prompt": (
            "If it takes 5 machines 5 minutes to make 5 widgets, "
            "how long would it take 100 machines to make 100 widgets?"
        ),
        "keywords": ["5 minutes", "rate", "machine"],
        "responses": {
            "deepseek-v4-pro": (
                "It would take 5 minutes. Here's why:\n"
                "5 machines make 5 widgets in 5 minutes, so the production rate "
                "is 1 widget per machine per 5 minutes (or 0.2 widgets per machine "
                "per minute).\n"
                "With 100 machines, the rate is 100 × 0.2 = 20 widgets per minute. "
                "To make 100 widgets: 100 ÷ 20 = 5 minutes.\n"
                "Alternatively: each machine still takes 5 minutes per widget, "
                "and with 100 machines running in parallel, 100 widgets are "
                "completed simultaneously in those same 5 minutes."
            ),
            "deepseek-v4-flash": "5 minutes.",
        },
        "synthesis": (
            "EXPERIMENTAL — Model Fusion (v1-alpha)\n\n"
            "It would take 5 minutes. Since 5 machines produce 5 widgets in "
            "5 minutes, each machine produces 1 widget in 5 minutes. With 100 "
            "machines working in parallel, 100 widgets are produced in the same "
            "5 minutes. The key insight is that adding more machines increases "
            "production rate proportionally, not the time per widget."
        ),
    },
    {
        "id": 9,
        "category": "reasoning",
        "prompt": (
            "You have a 3-gallon jug and a 5-gallon jug. "
            "How do you measure exactly 4 gallons of water?"
        ),
        "keywords": ["fill", "jug", "gallon"],
        "responses": {
            "deepseek-v4-pro": (
                "Step-by-step solution:\n"
                "1. Fill the 5-gallon jug completely.\n"
                "2. Pour from the 5-gallon jug into the 3-gallon jug until the "
                "3-gallon jug is full. This leaves 2 gallons in the 5-gallon jug.\n"
                "3. Empty the 3-gallon jug.\n"
                "4. Pour the remaining 2 gallons from the 5-gallon jug into the "
                "3-gallon jug (the 3-gallon jug now has 2 gallons, with 1 gallon "
                "of space remaining).\n"
                "5. Fill the 5-gallon jug again.\n"
                "6. Pour from the 5-gallon jug into the 3-gallon jug until the "
                "3-gallon jug is full. Since it only has room for 1 more gallon, "
                "you pour exactly 1 gallon, leaving exactly 4 gallons in the "
                "5-gallon jug."
            ),
            "deepseek-v4-flash": (
                "Fill the 5-gallon jug, pour into the 3-gallon jug, leaving 2 "
                "gallons. Empty the 3-gallon jug, transfer the 2 gallons, refill "
                "the 5, and top off the 3 — leaving 4 gallons."
            ),
        },
        "synthesis": (
            "EXPERIMENTAL — Model Fusion (v1-alpha)\n\n"
            "To measure exactly 4 gallons:\n"
            "1. Fill the 5-gallon jug.\n"
            "2. Pour from the 5 into the 3 until the 3 is full → 2 gallons remain in the 5.\n"
            "3. Empty the 3-gallon jug.\n"
            "4. Pour the 2 gallons from the 5 into the 3.\n"
            "5. Refill the 5-gallon jug.\n"
            "6. Top off the 3-gallon jug from the 5 (it takes 1 more gallon) → 4 gallons remain in the 5."
        ),
    },
    {
        "id": 10,
        "category": "reasoning",
        "prompt": (
            "If you flip a fair coin 3 times, what is the probability "
            "of getting at least 2 heads?"
        ),
        "keywords": ["0.5", "50%", "heads"],
        "responses": {
            "deepseek-v4-pro": (
                "The probability is 0.5 (50%).\n"
                "All 8 equally likely outcomes: HHH, HHT, HTH, THH, HTT, THT, TTH, TTT.\n"
                "Favorable outcomes (≥2 heads): HHH, HHT, HTH, THH — that's 4 out of 8.\n"
                "Therefore, P(at least 2 heads) = 4/8 = 1/2 = 0.5.\n"
                "Using the binomial distribution confirms: P(X≥2) = P(2)+P(3) "
                "= C(3,2)(0.5)^3 + C(3,3)(0.5)^3 = 3/8 + 1/8 = 4/8 = 0.5."
            ),
            "deepseek-v4-flash": "50% or 4/8.",
        },
        "synthesis": (
            "EXPERIMENTAL — Model Fusion (v1-alpha)\n\n"
            "The probability is 0.5 (50%). Out of 8 equally likely outcomes when "
            "flipping a fair coin 3 times, exactly 4 have at least 2 heads: "
            "HHH, HHT, HTH, THH. Binomial calculation confirms: "
            "P(X≥2) = C(3,2)(0.5)³ + C(3,3)(0.5)³ = 3/8 + 1/8 = 4/8 = 0.5."
        ),
    },
    # ────────────────── CODING (11-15) ──────────────────────────────────
    {
        "id": 11,
        "category": "coding",
        "prompt": "Write a Python function to check if a string is a palindrome.",
        "keywords": ["def", "return", "palindrome"],
        "responses": {
            "deepseek-v4-pro": (
                "Here is a clean Python function to check if a string is a palindrome:\n\n"
                "```python\n"
                "def is_palindrome(s: str) -> bool:\n"
                "    \"\"\"Return True if s is a palindrome, ignoring case and non-alphanumeric chars.\"\"\"\n"
                "    cleaned = ''.join(c.lower() for c in s if c.isalnum())\n"
                "    return cleaned == cleaned[::-1]\n"
                "```\n\n"
                "This handles mixed case, spaces, and punctuation. "
                "For example, 'A man, a plan, a canal: Panama' returns True."
            ),
            "deepseek-v4-flash": (
                "def is_palindrome(s):\n"
                "    return s == s[::-1]"
            ),
        },
        "synthesis": (
            "EXPERIMENTAL — Model Fusion (v1-alpha)\n\n"
            "```python\n"
            "def is_palindrome(s: str) -> bool:\n"
            "    \"\"\"Return True if s is a palindrome, case-insensitive, ignoring punctuation.\"\"\"\n"
            "    cleaned = ''.join(c.lower() for c in s if c.isalnum())\n"
            "    return cleaned == cleaned[::-1]\n"
            "```\n"
            "The function normalizes input by lowercasing and stripping non-alphanumeric "
            "characters, then compares the string to its reverse."
        ),
    },
    {
        "id": 12,
        "category": "coding",
        "prompt": "Write a SQL query to find the second highest salary from an employees table.",
        "keywords": ["select", "salary", "max"],
        "responses": {
            "deepseek-v4-pro": (
                "Several approaches, ordered by clarity:\n\n"
                "```sql\n"
                "-- Approach 1: subquery with MAX\n"
                "SELECT MAX(salary) AS second_highest_salary\n"
                "FROM employees\n"
                "WHERE salary < (SELECT MAX(salary) FROM employees);\n"
                "```\n\n"
                "```sql\n"
                "-- Approach 2: OFFSET (if duplicates should be distinct)\n"
                "SELECT DISTINCT salary FROM employees\n"
                "ORDER BY salary DESC LIMIT 1 OFFSET 1;\n"
                "```\n\n"
                "Approach 1 returns NULL if fewer than 2 distinct salaries exist. "
                "Approach 2 returns empty set in that case."
            ),
            "deepseek-v4-flash": (
                "SELECT MAX(salary) FROM employees WHERE salary < (SELECT MAX(salary) FROM employees);"
            ),
        },
        "synthesis": (
            "EXPERIMENTAL — Model Fusion (v1-alpha)\n\n"
            "```sql\n"
            "SELECT MAX(salary) AS second_highest_salary\n"
            "FROM employees\n"
            "WHERE salary < (SELECT MAX(salary) FROM employees);\n"
            "```\n"
            "This uses a subquery to find the maximum salary, then finds the "
            "maximum of all salaries below that. Returns NULL if fewer than "
            "2 distinct salaries exist, which is typically the desired behavior."
        ),
    },
    {
        "id": 13,
        "category": "coding",
        "prompt": "Write a Python function to merge two sorted lists into one sorted list.",
        "keywords": ["merge", "append", "while"],
        "responses": {
            "deepseek-v4-pro": (
                "```python\n"
                "from typing import TypeVar\n\n"
                "T = TypeVar('T')\n\n"
                "def merge_sorted(a: list[T], b: list[T]) -> list[T]:\n"
                "    \"\"\"Merge two sorted lists into one sorted list. O(n+m) time, O(n+m) space.\"\"\"\n"
                "    result: list[T] = []\n"
                "    i = j = 0\n"
                "    while i < len(a) and j < len(b):\n"
                "        if a[i] <= b[j]:\n"
                "            result.append(a[i])\n"
                "            i += 1\n"
                "        else:\n"
                "            result.append(b[j])\n"
                "            j += 1\n"
                "    result.extend(a[i:])\n"
                "    result.extend(b[j:])\n"
                "    return result\n"
                "```"
            ),
            "deepseek-v4-flash": (
                "def merge(a, b):\n"
                "    return sorted(a + b)"
            ),
        },
        "synthesis": (
            "EXPERIMENTAL — Model Fusion (v1-alpha)\n\n"
            "```python\n"
            "def merge_sorted(a: list[int], b: list[int]) -> list[int]:\n"
            "    \"\"\"Merge two sorted lists using two-pointer technique. O(n+m) time.\"\"\"\n"
            "    result = []\n"
            "    i = j = 0\n"
            "    while i < len(a) and j < len(b):\n"
            "        if a[i] <= b[j]:\n"
            "            result.append(a[i]); i += 1\n"
            "        else:\n"
            "            result.append(b[j]); j += 1\n"
            "    result.extend(a[i:])\n"
            "    result.extend(b[j:])\n"
            "    return result\n"
            "```\n"
            "This two-pointer approach runs in O(n+m) time, taking advantage "
            "of the input lists already being sorted."
        ),
    },
    {
        "id": 14,
        "category": "coding",
        "prompt": "Write a JavaScript function to debounce a function call.",
        "keywords": ["debounce", "clearTimeout", "setTimeout"],
        "responses": {
            "deepseek-v4-pro": (
                "```javascript\n"
                "/**\n"
                " * Creates a debounced version of a function that delays invocation\n"
                " * until after `delay` milliseconds have elapsed since the last call.\n"
                " * @param {Function} fn - The function to debounce.\n"
                " * @param {number} delay - Delay in milliseconds.\n"
                " * @returns {Function} Debounced function with a `.cancel()` method.\n"
                " */\n"
                "function debounce(fn, delay) {\n"
                "  let timerId = null;\n"
                "  function debounced(...args) {\n"
                "    clearTimeout(timerId);\n"
                "    timerId = setTimeout(() => {\n"
                "      fn.apply(this, args);\n"
                "    }, delay);\n"
                "  }\n"
                "  debounced.cancel = () => {\n"
                "    clearTimeout(timerId);\n"
                "    timerId = null;\n"
                "  };\n"
                "  return debounced;\n"
                "}\n"
                "```"
            ),
            "deepseek-v4-flash": (
                "function debounce(fn, delay) {\n"
                "  let timer;\n"
                "  return (...args) => {\n"
                "    clearTimeout(timer);\n"
                "    timer = setTimeout(() => fn(...args), delay);\n"
                "  };\n"
                "}"
            ),
        },
        "synthesis": (
            "EXPERIMENTAL — Model Fusion (v1-alpha)\n\n"
            "```javascript\n"
            "function debounce(fn, delay) {\n"
            "  let timerId = null;\n"
            "  function debounced(...args) {\n"
            "    clearTimeout(timerId);\n"
            "    timerId = setTimeout(() => fn.apply(this, args), delay);\n"
            "  }\n"
            "  debounced.cancel = () => { clearTimeout(timerId); timerId = null; };\n"
            "  return debounced;\n"
            "}\n"
            "```\n"
            "This returns a function that delays invoking `fn` until `delay` ms "
            "after the last call. A `.cancel()` method is included for cleanup."
        ),
    },
    {
        "id": 15,
        "category": "coding",
        "prompt": (
            "Write a Python function to find all prime numbers up to N "
            "using the Sieve of Eratosthenes."
        ),
        "keywords": ["sieve", "prime", "eratosthenes"],
        "responses": {
            "deepseek-v4-pro": (
                "```python\n"
                "def sieve_of_eratosthenes(n: int) -> list[int]:\n"
                "    \"\"\"Return all primes <= n using the Sieve of Eratosthenes.\"\"\"\n"
                "    if n < 2:\n"
                "        return []\n"
                "    is_prime = [True] * (n + 1)\n"
                "    is_prime[0] = is_prime[1] = False\n"
                "    for i in range(2, int(n**0.5) + 1):\n"
                "        if is_prime[i]:\n"
                "            for j in range(i * i, n + 1, i):\n"
                "                is_prime[j] = False\n"
                "    return [i for i, prime in enumerate(is_prime) if prime]\n"
                "```"
            ),
            "deepseek-v4-flash": (
                "def primes(n):\n"
                "    sieve = [True] * (n+1)\n"
                "    for p in range(2, int(n**0.5)+1):\n"
                "        if sieve[p]:\n"
                "            for i in range(p*p, n+1, p):\n"
                "                sieve[i] = False\n"
                "    return [p for p in range(2, n+1) if sieve[p]]"
            ),
        },
        "synthesis": (
            "EXPERIMENTAL — Model Fusion (v1-alpha)\n\n"
            "```python\n"
            "def sieve_of_eratosthenes(n: int) -> list[int]:\n"
            "    \"\"\"Return all prime numbers <= n.\"\"\"\n"
            "    if n < 2:\n"
            "        return []\n"
            "    is_prime = [True] * (n + 1)\n"
            "    is_prime[0] = is_prime[1] = False\n"
            "    for i in range(2, int(n ** 0.5) + 1):\n"
            "        if is_prime[i]:\n"
            "            for j in range(i * i, n + 1, i):\n"
            "                is_prime[j] = False\n"
            "    return [i for i, prime in enumerate(is_prime) if prime]\n"
            "```"
        ),
    },
    # ────────────────── SUMMARIZATION (16-18) ───────────────────────────
    {
        "id": 16,
        "category": "summarization",
        "prompt": "Summarize the key features of Python 3.12.",
        "keywords": ["f-string", "error", "performance"],
        "responses": {
            "deepseek-v4-pro": (
                "Python 3.12 introduced several notable features:\n"
                "1. F-string improvements — supports arbitrary expressions inside "
                "f-strings with nested quotes and multi-line expressions.\n"
                "2. More informative error messages — better tracebacks with "
                "location hints and suggestions for common mistakes.\n"
                "3. Performance boost — up to 5% faster overall due to various "
                "interpreter optimizations including the new type-parameter syntax.\n"
                "4. New `type` statement — `type X = int | str` for type aliases.\n"
                "5. Override decorator: `@override` from typing module.\n"
                "6. Improved compatibility with the import system and subinterpreters."
            ),
            "deepseek-v4-flash": (
                "Python 3.12: better f-strings, improved error messages, "
                "~5% faster, new type syntax."
            ),
        },
        "synthesis": (
            "EXPERIMENTAL — Model Fusion (v1-alpha)\n\n"
            "Key features of Python 3.12:\n"
            "1. **Enhanced f-strings**: support for arbitrary expressions, nested "
            "quotes, and multi-line f-string expressions.\n"
            "2. **Better error messages**: more precise tracebacks with suggestions "
            "for common mistakes.\n"
            "3. **Performance**: approximately 5% faster overall through interpreter "
            "optimizations.\n"
            "4. **Type-parameter syntax**: `type X = int | str` for cleaner type aliases.\n"
            "5. **@override decorator** and improved subinterpreter support."
        ),
    },
    {
        "id": 17,
        "category": "summarization",
        "prompt": "Summarize the plot of the novel '1984' by George Orwell.",
        "keywords": ["winston", "big brother", "ocean"],
        "responses": {
            "deepseek-v4-pro": (
                "George Orwell's '1984' is a dystopian novel set in a totalitarian "
                "superstate called Oceania, ruled by the Party and its omnipresent "
                "leader, Big Brother. The protagonist, Winston Smith, works at the "
                "Ministry of Truth where he rewrites historical records to align "
                "with Party doctrine. Dissatisfied with the oppressive regime, "
                "Winston begins a forbidden love affair with Julia and secretly "
                "rebels by keeping a diary and seeking out the underground "
                "Brotherhood. Eventually, Winston and Julia are captured by the "
                "Thought Police. Winston is tortured and brainwashed by O'Brien "
                "in the Ministry of Love until he genuinely comes to love Big Brother, "
                "his spirit completely broken."
            ),
            "deepseek-v4-flash": (
                "In a totalitarian future, Winston Smith rebels against the Party "
                "by falling in love and seeking truth. He is captured, tortured, "
                "and ultimately brainwashed into loving Big Brother."
            ),
        },
        "synthesis": (
            "EXPERIMENTAL — Model Fusion (v1-alpha)\n\n"
            "Set in the totalitarian superstate of Oceania, George Orwell's '1984' "
            "follows Winston Smith, a Ministry of Truth worker who secretly rebels "
            "against the Party by keeping a diary and beginning a forbidden affair "
            "with Julia. After being captured by the Thought Police, Winston is "
            "systematically tortured by O'Brien in the Ministry of Love until his "
            "resistance is shattered and he genuinely loves Big Brother — the regime's "
            "ultimate victory over individual will."
        ),
    },
    {
        "id": 18,
        "category": "summarization",
        "prompt": "Summarize the water cycle in 3 sentences.",
        "keywords": ["evaporat", "condens", "precipi"],
        "responses": {
            "deepseek-v4-pro": (
                "The water cycle describes the continuous movement of water on, "
                "above, and below the Earth's surface. Solar energy causes water "
                "to evaporate from oceans, lakes, and soil, rising as water vapor "
                "into the atmosphere where it condenses into clouds. The water "
                "returns to the surface as precipitation (rain, snow, sleet) and "
                "eventually flows back to oceans via runoff and groundwater, "
                "completing the cycle."
            ),
            "deepseek-v4-flash": (
                "Water evaporates from oceans, forms clouds, and falls as rain. "
                "It flows through rivers back to the ocean. This cycle repeats continuously."
            ),
        },
        "synthesis": (
            "EXPERIMENTAL — Model Fusion (v1-alpha)\n\n"
            "The water cycle is the continuous movement of water driven by solar energy: "
            "water evaporates from oceans, lakes, and soil, rising as vapor into the "
            "atmosphere. The vapor condenses into clouds and returns to the surface as "
            "precipitation (rain, snow, or sleet). This water flows through rivers and "
            "groundwater back to the oceans, completing the cycle and sustaining life on Earth."
        ),
    },
    # ────────────────── TRANSLATION (19-20) ─────────────────────────────
    {
        "id": 19,
        "category": "translation",
        "prompt": "Translate 'Hello, how are you?' to French.",
        "keywords": ["bonjour", "comment", "vous"],
        "responses": {
            "deepseek-v4-pro": (
                "The French translation is: \"Bonjour, comment allez-vous ?\"\n\n"
                "Notes:\n"
                "- \"Bonjour\" means \"hello\" (formal/general greeting).\n"
                "- \"Comment allez-vous ?\" is the formal/polite form of \"how are you?\".\n"
                "- Informal alternative: \"Salut, ça va ?\" (for friends/casual settings)."
            ),
            "deepseek-v4-flash": "Bonjour, comment allez-vous ?",
        },
        "synthesis": (
            "EXPERIMENTAL — Model Fusion (v1-alpha)\n\n"
            "French: **Bonjour, comment allez-vous ?**\n"
            "- \"Bonjour\" = hello (formal greeting)\n"
            "- \"Comment allez-vous ?\" = how are you? (formal/polite)\n"
            "- Casual alternative: \"Salut, ça va ?\""
        ),
    },
    {
        "id": 20,
        "category": "translation",
        "prompt": "Translate 'The quick brown fox jumps over the lazy dog' to Spanish.",
        "keywords": ["zorro", "perro", "rápido"],
        "responses": {
            "deepseek-v4-pro": (
                "The Spanish translation is: \"El rápido zorro marrón salta "
                "sobre el perro perezoso.\"\n\n"
                "Word-by-word breakdown:\n"
                "- The quick = El rápido\n"
                "- brown fox = zorro marrón\n"
                "- jumps over = salta sobre\n"
                "- the lazy dog = el perro perezoso\n\n"
                "This is a pangram (contains every letter). In Spanish, it uses "
                "every letter of the Spanish alphabet including ñ."
            ),
            "deepseek-v4-flash": (
                "El rápido zorro marrón salta sobre el perro perezoso."
            ),
        },
        "synthesis": (
            "EXPERIMENTAL — Model Fusion (v1-alpha)\n\n"
            "Spanish: **El rápido zorro marrón salta sobre el perro perezoso.**\n"
            "This pangram contains every letter of the Spanish alphabet and "
            "is the standard Spanish equivalent of the English typing exercise."
        ),
    },
]

# ═══════════════════════════════════════════════════════════════════════════
#  Test results collector (module-scoped)
# ═══════════════════════════════════════════════════════════════════════════


class _BaselineReport:
    """Collect per-prompt fusion quality metrics."""

    def __init__(self) -> None:
        self.entries: list[dict[str, Any]] = []

    def record(
        self,
        prompt_id: int,
        category: str,
        prompt: str,
        best_single_score: int,
        fusion_score: int,
        delta: int,
        cost: float,
        wall_time_ms: int,
        fused_answer: str,
        model_responses: list[dict[str, Any]],
    ) -> None:
        self.entries.append(
            {
                "id": prompt_id,
                "category": category,
                "prompt": prompt[:80],
                "best_single_score": best_single_score,
                "fusion_score": fusion_score,
                "delta": delta,
                "cost": cost,
                "wall_time_ms": wall_time_ms,
                "fused_truncated": fused_answer[:120],
                "model_responses_truncated": [
                    {"model": r["model"], "response": r["response"][:60]}
                    for r in model_responses
                ],
            }
        )

    @property
    def fusion_wins(self) -> int:
        return sum(1 for e in self.entries if e["delta"] > 0)

    @property
    def fusion_ties(self) -> int:
        return sum(1 for e in self.entries if e["delta"] == 0)

    @property
    def fusion_losses(self) -> int:
        return sum(1 for e in self.entries if e["delta"] < 0)

    @property
    def avg_delta(self) -> float:
        if not self.entries:
            return 0.0
        return sum(e["delta"] for e in self.entries) / len(self.entries)

    def summary(self) -> str:
        lines = [
            "",
            "╔══════════════════════════════════════════════════════════════╗",
            "║     FUSION QUALITY BASELINE — T9.3 REPORT (v1-alpha)        ║",
            "╠══════════════════════════════════════════════════════════════╣",
            "║  NOTE: v1-alpha quality baseline — not guaranteed.          ║",
            "║  This is a test of the fusion mechanism, not model quality. ║",
            "╠══════════════════════════════════════════════════════════════╣",
            f"║  Total prompts:            {len(self.entries):>5d}                             ║",
            f"║  Fusion wins (delta>0):    {self.fusion_wins:>5d}                             ║",
            f"║  Fusion ties  (delta=0):   {self.fusion_ties:>5d}                             ║",
            f"║  Fusion losses (delta<0):  {self.fusion_losses:>5d}                             ║",
            f"║  Avg delta:                {self.avg_delta:>+6.2f}                             ║",
            "╚══════════════════════════════════════════════════════════════╝",
            "",
        ]
        return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════════════
#  Fixtures
# ═══════════════════════════════════════════════════════════════════════════


@pytest.fixture(scope="module")
def report() -> _BaselineReport:
    return _BaselineReport()


@pytest.fixture(scope="module", autouse=True)
def _patch_fusion_dispatch() -> None:
    """Replace _call_model with mock for the entire module.  Zero real API calls."""
    import companion.fusion.dispatch as mod

    original = mod._call_model
    mod._call_model = _mock_call_model
    yield
    mod._call_model = original


@pytest.fixture(autouse=True)
def _reset_call_log() -> None:
    _CALL_LOG.clear()


# ═══════════════════════════════════════════════════════════════════════════
#  Helper — run fusion and score
# ═══════════════════════════════════════════════════════════════════════════


def _run_and_score(
    entry: dict[str, Any], report: _BaselineReport
) -> dict[str, Any]:
    """Run fusion_dispatch on one prompt and record quality metrics."""
    prompt: str = entry["prompt"]
    keywords: list[str] = entry["keywords"]
    pid: int = entry["id"]
    category: str = entry["category"]

    result = fusion_dispatch(prompt)

    # Score individual model responses
    individual_scores: list[int] = []
    for mr in result["model_responses"]:
        s = _score_answer(mr["response"], keywords)
        individual_scores.append(s)

    best_single = max(individual_scores) if individual_scores else 0
    fusion_score = _score_answer(result["fused_answer"], keywords)
    delta = fusion_score - best_single

    report.record(
        prompt_id=pid,
        category=category,
        prompt=prompt,
        best_single_score=best_single,
        fusion_score=fusion_score,
        delta=delta,
        cost=result["cost"],
        wall_time_ms=result["wall_time_ms"],
        fused_answer=result["fused_answer"],
        model_responses=result["model_responses"],
    )

    return result


# ═══════════════════════════════════════════════════════════════════════════
#  Parametrized test — one per prompt
# ═══════════════════════════════════════════════════════════════════════════


class TestFusionBaseline:
    """Run fusion_dispatch on all 20 prompts and record per-prompt metrics."""

    @pytest.mark.parametrize("entry", PROMPT_REGISTRY, ids=lambda e: f"P{e['id']}-{e['category']}")
    def test_fusion_prompt(self, entry: dict[str, Any], report: _BaselineReport) -> None:
        """Run one prompt through fusion, verify structural correctness."""
        result = _run_and_score(entry, report)

        # Structural assertions
        assert result["fused_answer"], "fused_answer must be non-empty"
        assert isinstance(result["fused_answer"], str)
        assert len(result["model_responses"]) >= 2, (
            f"Expected >=2 model responses, got {len(result['model_responses'])}"
        )
        assert result["cost"] >= 0, "cost must be non-negative"
        assert result["wall_time_ms"] >= 0, "wall_time_ms must be non-negative"
        assert "v1-alpha" in result["label"], "must carry v1-alpha label"

        # Fused answer must differ from individual model responses
        # (it includes the label prefix and merged content)
        model_texts = {mr["response"].strip() for mr in result["model_responses"] if mr["response"]}
        fused = result["fused_answer"].strip()
        assert fused not in model_texts, (
            "fused_answer must differ from any single model response"
        )


class TestFusionEdgeCases:
    """Edge cases for the fusion dispatch mechanism."""

    def test_empty_prompt_raises(self) -> None:
        with pytest.raises(ValueError, match="non-empty prompt"):
            fusion_dispatch("")

    def test_whitespace_prompt_raises(self) -> None:
        with pytest.raises(ValueError, match="non-empty prompt"):
            fusion_dispatch("   ")

    def test_single_model_raises(self) -> None:
        with pytest.raises(ValueError, match="at least 2 models"):
            fusion_dispatch("hello", models=["deepseek-v4-pro"])

    def test_too_many_models_raises(self) -> None:
        with pytest.raises(ValueError, match="at most 3 models"):
            fusion_dispatch("hello", models=["a", "b", "c", "d"])

    def test_return_dict_keys(self) -> None:
        result = fusion_dispatch("What is 2+2?")
        expected_keys = {
            "prompt", "model_responses", "fused_answer",
            "cost", "wall_time_ms", "timed_out_models", "label",
        }
        assert expected_keys <= set(result.keys()), (
            f"Missing keys: {expected_keys - set(result.keys())}"
        )

    def test_model_responses_have_required_fields(self) -> None:
        result = fusion_dispatch("What is 2+2?")
        for mr in result["model_responses"]:
            for key in ("model", "response", "cost", "wall_time_ms", "timed_out"):
                assert key in mr, f"model_response missing key: {key}"


# ═══════════════════════════════════════════════════════════════════════════
#  Final report — printed after all tests run
# ═══════════════════════════════════════════════════════════════════════════


class TestFusionReport:
    """Print and record the consolidated baseline report."""

    def test_final_report(
        self, report: _BaselineReport, capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Print the baseline report and enforce minimum coverage."""
        summary = report.summary()
        print(summary)

        # Minimum coverage: all 20 prompts must have been tested
        assert len(report.entries) == 20, (
            f"Expected 20 prompts tested, got {len(report.entries)}"
        )

        # Verify category distribution
        categories: dict[str, int] = {}
        for e in report.entries:
            cat = e["category"]
            categories[cat] = categories.get(cat, 0) + 1

        assert categories.get("trivia", 0) == 5, f"trivia: {categories.get('trivia', 0)}"
        assert categories.get("reasoning", 0) == 5, f"reasoning: {categories.get('reasoning', 0)}"
        assert categories.get("coding", 0) == 5, f"coding: {categories.get('coding', 0)}"
        assert categories.get("summarization", 0) == 3, f"summarization: {categories.get('summarization', 0)}"
        assert categories.get("translation", 0) == 2, f"translation: {categories.get('translation', 0)}"

        # All prompts must have valid scores
        for e in report.entries:
            assert 0 <= e["best_single_score"] <= 5, (
                f"P{e['id']}: invalid best_single_score {e['best_single_score']}"
            )
            assert 0 <= e["fusion_score"] <= 5, (
                f"P{e['id']}: invalid fusion_score {e['fusion_score']}"
            )
            assert -5 <= e["delta"] <= 5, (
                f"P{e['id']}: invalid delta {e['delta']}"
            )

        # ── append to learnings.md ───────────────────────────────────────
        learnings_path = (
            Path(__file__).parent.parent.parent
            / ".omo" / "notepads" / "bifrost" / "learnings.md"
        )
        learnings_path.parent.mkdir(parents=True, exist_ok=True)

        from datetime import datetime

        with open(learnings_path, "a") as f:
            f.write("\n---\n")
            f.write(f"## T9.3 — Fusion Quality Baseline (v1-alpha) — {datetime.now().isoformat()}\n\n")
            f.write("**Label**: v1-alpha quality baseline — not guaranteed.\n")
            f.write("**Method**: 20 prompts × 2 mock models × 1 synthesis pass. All mocked.\n\n")
            f.write(f"**Overall**: {len(report.entries)} prompts | "
                    f"Wins: {report.fusion_wins} | Ties: {report.fusion_ties} | "
                    f"Losses: {report.fusion_losses} | "
                    f"Avg Delta: {report.avg_delta:+.2f}\n\n")

            f.write("| # | Category | Prompt | Best Single | Fusion | Delta |\n")
            f.write("|---|----------|--------|-------------|--------|-------|\n")
            for e in report.entries:
                delta_str = f"+{e['delta']}" if e["delta"] > 0 else str(e["delta"])
                f.write(
                    f"| {e['id']:>2} | {e['category']:<13} | {e['prompt'][:50]} | "
                    f"{e['best_single_score']} | {e['fusion_score']} | {delta_str} |\n"
                )
            f.write("\n")
