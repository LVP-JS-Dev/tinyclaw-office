#!/usr/bin/env python3
"""High-level API for memory compression operations.

This module provides a user-friendly interface for memory compression,
wrapping the underlying claw-compactor integration. It is designed to be
the primary entry point for applications using memory compression.

Typical usage:
    from lib.memory_compressor import MemoryCompressor

    compressor = MemoryCompressor(workspace="/path/to/workspace")
    result = compressor.benchmark()
    print(f"Token savings: {result['total_saved']}")
"""

import sys
from pathlib import Path
from typing import Any, Dict, Optional


class MemoryCompressor:
    """High-level API for memory compression operations.

    This class provides a clean interface for compressing AI agent session
    transcripts and memory files. It supports workspace validation, benchmarking,
    observation extraction, tiered summarization, and full compression pipeline.

    The class is designed to be imported and used directly in application code:

        compressor = MemoryCompressor(workspace=".")
        benchmark_result = compressor.benchmark()
        compressor.observe(since="2025-01-01")

    Attributes:
        workspace: Path to the workspace directory containing memory files
        verbose: Enable verbose output for debugging
    """

    def __init__(self, workspace: str, verbose: bool = False):
        """Initialize the MemoryCompressor with a workspace path.

        Args:
            workspace: Path to workspace directory (should contain memory/ or MEMORY.md)
            verbose: Enable verbose output for debugging

        Raises:
            ValueError: If workspace path doesn't exist or is invalid
            TypeError: If workspace is not a valid directory

        Example:
            >>> compressor = MemoryCompressor("/path/to/workspace")
            >>> print(compressor.workspace)
            /path/to/workspace
        """
        # Import here to avoid circular dependencies
        try:
            from skills.claw_compactor.integration import ClawCompactor
        except ImportError as e:
            raise ImportError(
                "Failed to import ClawCompactor. Ensure the skills.claw_compactor "
                f"module is available: {e}"
            )

        self._compactor = ClawCompactor(workspace=workspace, verbose=verbose)
        self.workspace = self._compactor.workspace
        self.verbose = verbose

    def benchmark(self, json_output: bool = True) -> Dict[str, Any]:
        """Run non-destructive performance benchmark.

        Estimates potential token savings from applying compression techniques
        without modifying any files. This is useful for assessing whether
        compression is worthwhile for a given workspace.

        Args:
            json_output: If True, return parsed dict; if False, print raw output

        Returns:
            Dictionary containing benchmark results:
                - steps: List of compression steps with before/after token counts
                - total_before: Starting token count
                - total_after: Final token count after all optimizations
                - total_saved: Number of tokens saved
                - total_pct: Percentage of tokens saved

        Raises:
            RuntimeError: If benchmark command fails

        Example:
            >>> compressor = MemoryCompressor(".")
            >>> result = compressor.benchmark()
            >>> print(f"Savings: {result['total_pct']}%")
        """
        return self._compactor.benchmark(json_output=json_output)

    def observe(self, json_output: bool = True, since: Optional[str] = None) -> Dict[str, Any]:
        """Scan session transcripts and generate observations.

        Compresses session transcripts by extracting factual observations,
        decisions, and action items. Achieves ~97% size reduction while
        preserving semantic meaning.

        Args:
            json_output: If True, return parsed dict; if False, print raw output
            since: Optional date string to filter sessions (YYYY-MM-DD format)

        Returns:
            Dictionary with:
                - processed: Number of new sessions processed
                - total_tracked: Total number of tracked sessions

        Raises:
            RuntimeError: If observe command fails

        Example:
            >>> compressor = MemoryCompressor(".")
            >>> result = compressor.observe(since="2025-01-01")
            >>> print(f"Processed {result['processed']} sessions")
        """
        return self._compactor.observe(json_output=json_output, since=since)

    def tiers(self, json_output: bool = True) -> Dict[str, Any]:
        """Generate tiered summaries (L0, L1, L2).

        Creates multiple levels of summarization with increasing compression.
        Saves tiered memory files to memory/MEMORY-{L0,L1,L2}.md.

        The levels are:
            - L0: Light compression (key points, ~70% reduction)
            - L1: Medium compression (summaries, ~85% reduction)
            - L2: Heavy compression (essential facts only, ~95% reduction)

        Args:
            json_output: If True, return parsed dict; if False, print raw output

        Returns:
            Dictionary with:
                - levels: List of tier levels generated
                - total_sections: Number of input sections processed

        Raises:
            RuntimeError: If tiers command fails

        Example:
            >>> compressor = MemoryCompressor(".")
            >>> result = compressor.tiers()
            >>> print(f"Generated {len(result['levels'])} tiers")
        """
        return self._compactor.tiers(json_output=json_output)

    def dict_compress(self, json_output: bool = True) -> Dict[str, Any]:
        """Run dictionary-based compression (CCP).

        Builds a codebook of frequent phrases and replaces them with $XX codes.
        Saves codebook to memory/.codebook.json for decompression.

        The codebook maps frequently occurring phrases to short codes,
        achieving additional compression on top of observation/tier methods.

        Args:
            json_output: If True, return parsed dict; if False, print raw output

        Returns:
            Dictionary with:
                - codebook_entries: Number of entries in codebook
                - files_scanned: Number of files scanned
                - codebook_path: Path to saved codebook

        Raises:
            RuntimeError: If dict command fails

        Example:
            >>> compressor = MemoryCompressor(".")
            >>> result = compressor.dict_compress()
            >>> print(f"Codebook has {result['codebook_entries']} entries")
        """
        return self._compactor.dict_compress(json_output=json_output)

    def full(self, json_output: bool = True, since: Optional[str] = None) -> Dict[str, Any]:
        """Run complete compression pipeline.

        Executes the full compression workflow:
        1. Count initial tokens
        2. Observe (scan session transcripts)
        3. Tiers (generate tiered summaries)
        4. Dict (dictionary compression)
        5. Report final token counts

        This is the recommended method for complete workspace compression.

        Args:
            json_output: If True, return parsed dict; if False, print raw output
            since: Optional date string to filter sessions (YYYY-MM-DD format)

        Returns:
            Dictionary with compression statistics (printed output parsed)

        Raises:
            RuntimeError: If full command fails

        Example:
            >>> compressor = MemoryCompressor(".")
            >>> result = compressor.full()
            >>> # Full compression complete
        """
        return self._compactor.full(json_output=json_output, since=since)

    def estimate(self, json_output: bool = True) -> Dict[str, Any]:
        """Estimate token counts for workspace files.

        Provides a breakdown of token usage across all memory files
        in the workspace.

        Args:
            json_output: If True, return parsed dict; if False, print raw output

        Returns:
            Dictionary with:
                - files: List of file token counts
                - total_tokens: Sum of all file token counts

        Raises:
            RuntimeError: If estimate command fails

        Example:
            >>> compressor = MemoryCompressor(".")
            >>> result = compressor.estimate()
            >>> print(f"Total tokens: {result['total_tokens']}")
        """
        return self._compactor.estimate(json_output=json_output)

    def get_memory_dir(self) -> Path:
        """Get or create the memory directory for artifacts.

        Ensures the memory directory exists and returns its path.
        All compression artifacts (codebooks, observations, etc.) are
        stored in this directory.

        Returns:
            Path to the memory directory

        Example:
            >>> compressor = MemoryCompressor(".")
            >>> mem_dir = compressor.get_memory_dir()
            >>> print(mem_dir)
            /path/to/workspace/memory
        """
        return self._compactor.get_memory_dir()

    def get_artifacts(self) -> Dict[str, Any]:
        """Get information about compression artifacts.

        Returns paths and status information for all compression artifacts
        in the workspace, including codebooks and observation files.

        Returns:
            Dictionary with:
                - codebook: Path to codebook if exists, else None
                - observations_dir: Path to observations directory
                - observation_files: List of observation file paths

        Example:
            >>> compressor = MemoryCompressor(".")
            >>> artifacts = compressor.get_artifacts()
            >>> if artifacts['codebook']:
            ...     print(f"Codebook: {artifacts['codebook']}")
        """
        return self._compactor.get_artifacts()


# Convenience function for quick operations
def compress_workspace(workspace: str, operation: str = "benchmark", **kwargs) -> Any:
    """Convenience function for one-shot compression operations.

    This function provides a quick way to run compression operations without
    explicitly creating a MemoryCompressor instance.

    Args:
        workspace: Path to workspace directory
        operation: Operation to run (benchmark, observe, tiers, full, dict, estimate)
        **kwargs: Additional arguments passed to the operation

    Returns:
        Result of the operation (typically a dict)

    Raises:
        ValueError: If operation is not recognized
        RuntimeError: If the operation fails

    Example:
        >>> result = compress_workspace(".", "benchmark")
        >>> print(f"Savings: {result['total_saved']} tokens")
    """
    compressor = MemoryCompressor(workspace)

    operations = {
        "benchmark": lambda: compressor.benchmark(**kwargs),
        "observe": lambda: compressor.observe(**kwargs),
        "tiers": lambda: compressor.tiers(**kwargs),
        "full": lambda: compressor.full(**kwargs),
        "dict": lambda: compressor.dict_compress(**kwargs),
        "estimate": lambda: compressor.estimate(**kwargs),
    }

    if operation not in operations:
        raise ValueError(
            f"Unknown operation: {operation}. "
            f"Valid operations: {', '.join(operations.keys())}"
        )

    return operations[operation]()


def main():
    """CLI entry point for memory_compressor module.

    Allows running compression operations via:
        python -m lib.memory_compressor --workspace <path> --command <cmd>
    """
    import argparse
    import json

    parser = argparse.ArgumentParser(
        description="Memory compression API for AI agent workflows"
    )
    parser.add_argument(
        "--workspace",
        default=".",
        help="Workspace directory path (default: current directory)"
    )
    parser.add_argument(
        "--command",
        required=True,
        choices=["benchmark", "observe", "tiers", "full", "dict", "estimate"],
        help="Compression command to run"
    )
    parser.add_argument(
        "--json",
        action="store_true",
        default=True,
        help="Output results as JSON (default: True)"
    )
    parser.add_argument(
        "--since",
        type=str,
        default=None,
        help="Filter sessions since date (YYYY-MM-DD)"
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable verbose output"
    )

    args = parser.parse_args()

    try:
        result = compress_workspace(
            args.workspace,
            args.command,
            json_output=args.json,
            since=args.since
        )

        if args.json and isinstance(result, dict):
            print(json.dumps(result, indent=2))
        elif result:
            print(result)

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
