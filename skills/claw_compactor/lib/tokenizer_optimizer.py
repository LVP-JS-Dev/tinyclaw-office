#!/usr/bin/env python3
"""Tokenizer-level format optimization.

Optimizes text formatting to reduce token count while preserving meaning.
"""

import re


def optimize_tokens(text: str, aggressive: bool = False) -> str:
    """Optimize text for token efficiency.

    Args:
        text: Text to optimize
        aggressive: Apply more aggressive optimizations

    Returns:
        Optimized text
    """
    optimized = text

    # Remove excessive whitespace
    optimized = re.sub(r'\n{3,}', '\n\n', optimized)
    optimized = re.sub(r' +', ' ', optimized)

    # Simplify common markdown patterns
    optimized = re.sub(r'#{4,}\s', '#### ', optimized)  # Limit heading depth

    # Remove redundant formatting
    optimized = re.sub(r'\*\*\*\*([^*]+)\*\*\*\*', r'**\1**', optimized)  # **** -> **

    if aggressive:
        # More aggressive optimizations
        # Remove bullet points if they're just visual clutter
        optimized = re.sub(r'^[\s]*[-*+]\s+', '', optimized, flags=re.MULTILINE)

        # Compress numbered lists
        optimized = re.sub(r'^\s*\d+\.\s+', '', optimized, flags=re.MULTILINE)

        # Remove empty markdown sections
        optimized = re.sub(r'^#+\s+\n', '', optimized, flags=re.MULTILINE)

    return optimized


def estimate_savings(text: str) -> int:
    """Estimate potential token savings from optimization.

    Args:
        text: Text to analyze

    Returns:
        Estimated tokens saved
    """
    from .tokens import estimate_tokens

    original = estimate_tokens(text)
    optimized = estimate_tokens(optimize_tokens(text, aggressive=True))

    return original - optimized
