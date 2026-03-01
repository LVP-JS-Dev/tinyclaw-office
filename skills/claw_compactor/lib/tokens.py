#!/usr/bin/env python3
"""Token counting utilities for claw-compactor.

Supports both tiktoken (exact) and heuristic (CJK-aware) token counting.
"""

import re
from typing import Optional

# Try to import tiktoken, fall back to heuristic
_TIKTOKEN_AVAILABLE = False
try:
    import tiktoken
    _TIKTOKEN_AVAILABLE = True
    _ENCODING = tiktoken.get_encoding("cl100k_base")
except ImportError:
    _ENCODING = None


def using_tiktoken() -> bool:
    """Check if tiktoken is available."""
    return _TIKTOKEN_AVAILABLE


def estimate_tokens(text: str) -> int:
    """Estimate token count for text.

    Uses tiktoken if available, otherwise falls back to CJK-aware heuristic.
    """
    if not text:
        return 0

    if _TIKTOKEN_AVAILABLE:
        try:
            return len(_ENCODING.encode(text))
        except Exception:
            pass  # Fall back to heuristic

    # Heuristic: CJK-aware character count
    # CJK characters typically use ~2-3 tokens, ASCII uses ~4 chars per token
    cjk_pattern = re.compile(r'[\u4e00-\u9fff\u3400-\u4dbf\u3040-\u309f\u30a0-\u30ff\uac00-\ud7af]')
    cjk_chars = len(cjk_pattern.findall(text))
    non_cjk_chars = len(text) - cjk_chars

    # CJK: ~1.5 chars per token, ASCII: ~4 chars per token
    cjk_tokens = cjk_chars / 1.5
    ascii_tokens = non_cjk_chars / 4

    return int(cjk_tokens + ascii_tokens)


def count_tokens(text: str, model: str = "gpt-4") -> int:
    """Count tokens exactly using tiktoken if available.

    Args:
        text: Text to count tokens for
        model: Model name for encoding (default: gpt-4)

    Returns:
        Token count (estimate if tiktoken unavailable)
    """
    return estimate_tokens(text)
