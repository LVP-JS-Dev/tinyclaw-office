#!/usr/bin/env python3
"""Run-Length Encoding (RLE) for common patterns.

Compresses repeated patterns like file paths, IPs, and enums.
"""

import re
from typing import List


# Common patterns to compress
_PATTERNS = [
    # Workspace paths
    (r'/Users/[^/]+/([^/]+/)', '$WS/\\1/'),
    (r'/home/[^/]+/([^/]+/)', '$WH/\\1/'),
    # IP addresses
    (r'(\d+\.\d+\.\d+)\.\d+', '$IP\\1'),
    # Enum-like patterns
    (r'("status":\s*)"(active|pending|completed)"', '\\1"$ST_\\2"'),
]


def compress(text: str, workspace_paths: List[str] = None) -> str:
    """Compress text using RLE patterns.

    Args:
        text: Text to compress
        workspace_paths: List of workspace paths to create shorthands for

    Returns:
        Compressed text
    """
    compressed = text

    # Add workspace-specific patterns
    if workspace_paths:
        for ws_path in workspace_paths:
            # Create a shorthand for the workspace path
            pattern = re.compile(re.escape(ws_path))
            compressed = pattern.sub('$WS', compressed)

    # Apply standard patterns
    for pattern, replacement in _PATTERNS:
        compressed = re.sub(pattern, replacement, compressed)

    return compressed


def decompress(text: str, workspace_path: str = None) -> str:
    """Decompress text by expanding RLE patterns.

    Note: Full decompression requires the original workspace path.
    Some patterns (like IPs) are lossy.

    Args:
        text: Compressed text
        workspace_path: Original workspace path to expand $WS

    Returns:
        Partially decompressed text
    """
    decompressed = text

    # Expand workspace path if provided
    if workspace_path:
        decompressed = decompressed.replace('$WS', workspace_path)

    # Note: IP shorthand is lossy and can't be fully decompressed
    # Status enums would need reverse mapping

    return decompressed
