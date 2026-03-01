#!/usr/bin/env python3
"""Dictionary-based compression (CCP - Claw Compactor Protocol).

Builds a codebook of frequent phrases and replaces them with $XX codes.
"""

import json
import re
from pathlib import Path
from typing import Dict, List, Tuple


def build_codebook(texts: List[str], min_freq: int = 2) -> Dict[str, str]:
    """Build a codebook from frequent phrases in texts.

    Args:
        texts: List of text samples
        min_freq: Minimum frequency for a phrase to be included

    Returns:
        Dictionary mapping codes to phrases
    """
    from collections import Counter

    # Simple word frequency counting
    word_counter = Counter()

    for text in texts:
        words = re.findall(r'\b\w+\b', text.lower())
        word_counter.update(words)

    # Filter by frequency and create codebook
    codebook = {}
    code_idx = 0

    for word, freq in word_counter.most_common():
        if freq >= min_freq and len(word) > 3:  # Only meaningful words
            code = f"${code_idx:02d}"
            codebook[code] = word
            code_idx += 1
            if code_idx >= 99:  # Limit to 99 codes
                break

    return codebook


def compress_text(text: str, codebook: Dict[str, str]) -> str:
    """Compress text using dictionary codebook.

    Args:
        text: Text to compress
        codebook: Dictionary mapping codes to phrases

    Returns:
        Compressed text with phrases replaced by codes
    """
    compressed = text

    # Sort codes by length (longest first) to avoid partial replacements
    sorted_codes = sorted(codebook.items(), key=lambda x: len(x[1]), reverse=True)

    for code, phrase in sorted_codes:
        # Case-insensitive replacement
        pattern = re.compile(re.escape(phrase), re.IGNORECASE)
        compressed = pattern.sub(code, compressed)

    return compressed


def decompress_text(text: str, codebook: Dict[str, str]) -> str:
    """Decompress text by expanding codes back to phrases.

    Args:
        text: Compressed text
        codebook: Dictionary mapping codes to phrases

    Returns:
        Decompressed text
    """
    decompressed = text

    # Sort codes by length (shortest first) to avoid overlaps
    for code in sorted(codebook.keys(), key=len, reverse=True):
        phrase = codebook[code]
        decompressed = decompressed.replace(code, phrase)

    return decompressed


def save_codebook(codebook: Dict[str, str], path: Path) -> None:
    """Save codebook to JSON file.

    Args:
        codebook: Dictionary mapping codes to phrases
        path: Path to save codebook
    """
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(codebook, f, indent=2, ensure_ascii=False)


def load_codebook(path: Path) -> Dict[str, str]:
    """Load codebook from JSON file.

    Args:
        path: Path to codebook file

    Returns:
        Dictionary mapping codes to phrases
    """
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)
