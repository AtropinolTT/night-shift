"""FusionDispatch — experimental multi-model fusion for Bifrost.

Sends a prompt to 2-3 models in parallel, collects responses,
and uses a synthesis model to merge them into a single answer.

EXPERIMENTAL — Model Fusion (v1-alpha).  User-invoked only via /fusion.
"""

from __future__ import annotations

import time
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Any

from companion.config import DEFAULTS, load_config

# ── constants ──────────────────────────────────────────────────────────────

EXPERIMENTAL_LABEL = "EXPERIMENTAL — Model Fusion (v1-alpha)"

DEFAULT_MODELS: list[str] = ["deepseek-v4-pro", "deepseek-v4-flash"]

MAX_MODELS: int = 3

DEFAULT_COST_CEILING: float = 0.50
DEFAULT_TIMEOUT_PER_MODEL: int = 60

# Estimated USD per token (input, output) — coarse estimates for cost tracking.
# In production these should come from live pricing APIs.
MODEL_RATES: dict[str, tuple[float, float]] = {
    "deepseek-v4-pro":   (0.002 / 1_000_000, 0.008 / 1_000_000),
    "deepseek-v4-flash": (0.0002 / 1_000_000, 0.0008 / 1_000_000),
    "deepseek-v3":       (0.001 / 1_000_000, 0.004 / 1_000_000),
    "gpt-4o":           (0.005 / 1_000_000, 0.015 / 1_000_000),
    "claude-sonnet-4":  (0.003 / 1_000_000, 0.015 / 1_000_000),
}

SYNTHESIS_PROMPT_TEMPLATE = (
    "You are a synthesis engine. Given these {n} responses to the original prompt, "
    "produce the best combined answer. Consider different perspectives, "
    "resolve contradictions, and merge complementary insights into a single "
    "coherent response.\n\n"
    "--- ORIGINAL PROMPT ---\n{prompt}\n--- END ORIGINAL PROMPT ---\n\n"
    "{responses}\n\n"
    "--- SYNTHESIS INSTRUCTIONS ---\n"
    "1. Identify the strongest claims and evidence from each response.\n"
    "2. Note any disagreements and explain which position has better support.\n"
    "3. If one response is noticeably weaker, give it less weight.\n"
    "4. Produce one unified answer — do NOT present a list of competing answers.\n"
    "5. Start your response with: {label}\n"
)


# ── data structures ────────────────────────────────────────────────────────


@dataclass
class ModelResponse:
    """A single model's response to the fusion prompt."""

    model: str
    response: str
    cost: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
    wall_time_ms: int = 0
    timed_out: bool = False
    error: str | None = None


@dataclass
class FusionResult:
    """Result of a fusion_dispatch call."""

    prompt: str
    model_responses: list[dict[str, Any]] = field(default_factory=list)
    fused_answer: str = ""
    cost: float = 0.0
    wall_time_ms: int = 0
    timed_out_models: list[str] = field(default_factory=list)
    label: str = EXPERIMENTAL_LABEL


# ── cost helpers ───────────────────────────────────────────────────────────


def _estimate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    """Estimate USD cost from token counts using hard-coded rates."""
    in_rate, out_rate = MODEL_RATES.get(model, (0.0, 0.0))
    return input_tokens * in_rate + output_tokens * out_rate


def _approx_tokens(text: str) -> int:
    """Rough token count — ~4 chars per token for English text."""
    return max(1, len(text) // 4)


# ── model caller (mock — swap for real APIs in production) ────────────────


def _call_model(
    model: str,
    prompt: str,
    timeout_s: int = DEFAULT_TIMEOUT_PER_MODEL,
) -> ModelResponse:
    """Call a single model and return its response.

    Currently uses a mock implementation.  Replace the body of this
    function with real HTTP API calls for production use.

    Parameters
    ----------
    model : str
        Model identifier (e.g. "deepseek-v4-pro").
    prompt : str
        The prompt text to send.
    timeout_s : int
        Maximum wait time in seconds.

    Returns
    -------
    ModelResponse
    """
    t0 = time.monotonic()
    input_tokens = _approx_tokens(prompt)

    # ── mock implementation ─────────────────────────────────────────────
    # Simulate network latency (0.2–1.5 s)
    import random

    latency = random.uniform(0.2, 1.5)
    remaining = timeout_s - latency
    if remaining <= 0:
        elapsed_ms = int(timeout_s * 1000)
        return ModelResponse(
            model=model,
            response="",
            cost=0.0,
            input_tokens=input_tokens,
            output_tokens=0,
            wall_time_ms=elapsed_ms,
            timed_out=True,
        )

    time.sleep(latency)

    output_tokens = random.randint(60, 350)
    elapsed_ms = int((time.monotonic() - t0) * 1000)

    response_text = (
        f"[{model}] {EXPERIMENTAL_LABEL}\n\n"
        f"(mock response — {output_tokens} token output)\n"
        f"This is a placeholder response from {model}. "
        f"In production, this contains the model's actual output "
        f"generated from the prompt.\n"
        f"Prompt excerpt: \"{prompt[:120]}{'...' if len(prompt) > 120 else ''}\""
    )

    cost = _estimate_cost(model, input_tokens, output_tokens)

    return ModelResponse(
        model=model,
        response=response_text,
        cost=cost,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        wall_time_ms=elapsed_ms,
    )
    # ── end mock ────────────────────────────────────────────────────────


# ── synthesis ──────────────────────────────────────────────────────────────


def _build_synthesis_prompt(prompt: str, responses: list[ModelResponse]) -> str:
    """Build the synthesis prompt from individual model responses."""
    blocks: list[str] = []
    for i, r in enumerate(responses, 1):
        blocks.append(
            f"=== RESPONSE {i} (from {r.model}) ===\n{r.response}\n"
        )
    return SYNTHESIS_PROMPT_TEMPLATE.format(
        n=len(responses),
        prompt=prompt,
        responses="\n".join(blocks),
        label=EXPERIMENTAL_LABEL,
    )


def _synthesize(
    prompt: str,
    responses: list[ModelResponse],
    synthesis_model: str,
    timeout_s: int,
) -> tuple[str, float]:
    """Run the synthesis step — send merged responses to the synthesis model."""
    synthesis_prompt = _build_synthesis_prompt(prompt, responses)
    result = _call_model(synthesis_model, synthesis_prompt, timeout_s)
    return result.response, result.cost


# ── public API ─────────────────────────────────────────────────────────────


def fusion_dispatch(
    prompt: str,
    models: list[str] | None = None,
    synthesis_model: str | None = None,
    cost_ceiling: float = DEFAULT_COST_CEILING,
    timeout_per_model: int = DEFAULT_TIMEOUT_PER_MODEL,
) -> dict[str, Any]:
    """Dispatch a prompt to multiple models in parallel and synthesize a fused answer.

    EXPERIMENTAL — Model Fusion (v1-alpha).  User-invoked only via /fusion.

    Parameters
    ----------
    prompt : str
        Prompt text sent to every model.
    models : list[str] | None
        Model IDs to query (max 3).  Default: ``["deepseek-v4-pro", "deepseek-v4-flash"]``.
    synthesis_model : str | None
        Model used for synthesis.  Default: config ``model_for_fusion_synthesis``.
    cost_ceiling : float
        Maximum total USD cost.  Default $0.50.
    timeout_per_model : int
        Seconds to wait per model before skipping it.  Default 60.

    Returns
    -------
    dict
        Keys: ``prompt``, ``model_responses``, ``fused_answer``, ``cost``,
        ``wall_time_ms``, ``timed_out_models``, ``label``.

    Raises
    ------
    ValueError
        If ``models`` exceeds :data:`MAX_MODELS` (3), or if *prompt* is empty.
    """
    if not prompt or not prompt.strip():
        raise ValueError("fusion_dispatch requires a non-empty prompt")

    resolved_models = list(models) if models else list(DEFAULT_MODELS)
    if len(resolved_models) > MAX_MODELS:
        raise ValueError(
            f"fusion_dispatch supports at most {MAX_MODELS} models, "
            f"got {len(resolved_models)}"
        )
    if len(resolved_models) < 2:
        raise ValueError(
            "fusion_dispatch requires at least 2 models, "
            f"got {len(resolved_models)}"
        )

    cfg = load_config()
    resolved_synthesis: str = (
        synthesis_model
        or getattr(cfg, "model_for_fusion_synthesis", DEFAULTS["model_for_fusion_synthesis"])
    )

    wall_start = time.monotonic()

    # ── Phase 1: parallel dispatch ─────────────────────────────────────
    model_responses: list[ModelResponse] = []
    timed_out: list[str] = []
    cumulative_cost: float = 0.0

    with ThreadPoolExecutor(max_workers=min(len(resolved_models), MAX_MODELS)) as executor:
        future_map: dict[Future[ModelResponse], str] = {}
        for model in resolved_models:
            fut = executor.submit(_call_model, model, prompt, timeout_per_model)
            future_map[fut] = model

        for fut in as_completed(future_map):
            model = future_map[fut]
            try:
                result = fut.result(timeout=timeout_per_model + 5)
                if result.timed_out:
                    timed_out.append(model)
                    model_responses.append(result)
                else:
                    cumulative_cost += result.cost
                    if cumulative_cost > cost_ceiling:
                        result.error = (
                            f"Cost ceiling ${cost_ceiling:.2f} exceeded "
                            f"(cumulative ${cumulative_cost:.4f}). "
                            f"Response included but further models may be skipped."
                        )
                    model_responses.append(result)
            except Exception as exc:
                timed_out.append(model)
                model_responses.append(
                    ModelResponse(
                        model=model,
                        response="",
                        wall_time_ms=int((time.monotonic() - wall_start) * 1000),
                        timed_out=True,
                        error=str(exc),
                    )
                )

    successful = [r for r in model_responses if not r.timed_out and r.response]

    if not successful:
        wall_ms = int((time.monotonic() - wall_start) * 1000)
        return {
            "prompt": prompt,
            "model_responses": [
                {
                    "model": r.model,
                    "response": r.response or "",
                    "cost": r.cost,
                    "input_tokens": r.input_tokens,
                    "output_tokens": r.output_tokens,
                    "wall_time_ms": r.wall_time_ms,
                    "timed_out": r.timed_out,
                    "error": r.error,
                }
                for r in model_responses
            ],
            "fused_answer": (
                f"{EXPERIMENTAL_LABEL}\n\n"
                "Fusion failed: all models timed out or returned empty responses."
            ),
            "cost": cumulative_cost,
            "wall_time_ms": wall_ms,
            "timed_out_models": timed_out,
            "label": EXPERIMENTAL_LABEL,
        }

    # ── Phase 2: synthesis ─────────────────────────────────────────────
    synth_answer, synth_cost = _synthesize(
        prompt, successful, resolved_synthesis, timeout_per_model * 2
    )
    cumulative_cost += synth_cost

    wall_ms = int((time.monotonic() - wall_start) * 1000)

    # Prepend label if the synthesis model didn't include it
    if EXPERIMENTAL_LABEL not in synth_answer:
        synth_answer = f"{EXPERIMENTAL_LABEL}\n\n{synth_answer}"

    return {
        "prompt": prompt,
        "model_responses": [
            {
                "model": r.model,
                "response": r.response or "",
                "cost": r.cost,
                "input_tokens": r.input_tokens,
                "output_tokens": r.output_tokens,
                "wall_time_ms": r.wall_time_ms,
                "timed_out": r.timed_out,
                "error": r.error,
            }
            for r in model_responses
        ],
        "fused_answer": synth_answer,
        "cost": round(cumulative_cost, 6),
        "wall_time_ms": wall_ms,
        "timed_out_models": timed_out,
        "label": EXPERIMENTAL_LABEL,
    }


# ── top-level alias for MCP registration ───────────────────────────────────

# fusion_dispatch is registered as an MCP tool in companion/server.py.
# Kept as a plain function (no async, no state) so it can be called both
# via MCP and directly from test code.
