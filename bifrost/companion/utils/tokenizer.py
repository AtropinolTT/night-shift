"""Token counting for Bifrost via tiktoken.

Provides accurate token counts (replacing the coarse ``len(text) // 4``
heuristic used elsewhere) when tiktoken is available.
"""

from __future__ import annotations

from typing import Optional

_ENCODING: Optional[object] = None
_ENCODING_NAME: str = "cl100k_base"


def _get_encoding() -> Optional[object]:
    global _ENCODING
    if _ENCODING is not None:
        return _ENCODING
    try:
        import tiktoken
        _ENCODING = tiktoken.get_encoding(_ENCODING_NAME)
    except Exception:
        _ENCODING = False  # type: ignore[assignment]
    return _ENCODING if _ENCODING is not False else None


def count_tokens(text: str) -> int:
    """Return the number of tokens in *text*.

    Uses tiktoken's ``cl100k_base`` encoding when available;
    falls back to a character-count heuristic (``len(text) // 4``).
    """
    if not text:
        return 0
    enc = _get_encoding()
    if enc is not None:
        return len(enc.encode(text))
    return max(1, len(text) // 4)


def count_tokens_messages(messages: list[dict[str, str]]) -> int:
    """Return the token count for a list of chat messages.

    Each message is a dict with ``role`` and ``content`` keys.
    Falls back to summing character-count heuristics.
    """
    total = 0
    enc = _get_encoding()
    for msg in messages:
        content = msg.get("content", "")
        if enc is not None:
            total += len(enc.encode(content))
            total += 4  # per-message overhead estimate
        else:
            total += max(1, len(content) // 4) + 4
    return total
