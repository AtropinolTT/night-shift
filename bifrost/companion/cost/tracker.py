"""Session-level cost tracking for Bifrost.

Tracks token usage and estimated cost per session, exposed as an MCP tool
so the plugin can query accumulated costs during long-running sessions.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class CostEntry:
    tool_name: str
    input_tokens: int
    output_tokens: int
    cost: float
    wall_time_ms: int
    timestamp: float = field(default_factory=time.monotonic)


class SessionCostTracker:
    """Accumulates per-call costs and exposes a session total."""

    def __init__(self) -> None:
        self._entries: list[CostEntry] = []
        self._total_cost: float = 0.0
        self._total_tokens: int = 0
        self._call_count: int = 0

    def record(
        self,
        tool_name: str,
        input_tokens: int,
        output_tokens: int,
        cost: float,
        wall_time_ms: int,
    ) -> None:
        entry = CostEntry(
            tool_name=tool_name,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost=cost,
            wall_time_ms=wall_time_ms,
        )
        self._entries.append(entry)
        self._total_cost += cost
        self._total_tokens += input_tokens + output_tokens
        self._call_count += 1

    def summary(self) -> dict[str, Any]:
        return {
            "call_count": self._call_count,
            "total_tokens": self._total_tokens,
            "total_cost": round(self._total_cost, 6),
            "entries": [
                {
                    "tool_name": e.tool_name,
                    "input_tokens": e.input_tokens,
                    "output_tokens": e.output_tokens,
                    "cost": round(e.cost, 6),
                    "wall_time_ms": e.wall_time_ms,
                }
                for e in self._entries[-20:]  # last 20 for summary
            ],
        }

    def reset(self) -> None:
        self._entries.clear()
        self._total_cost = 0.0
        self._total_tokens = 0
        self._call_count = 0
