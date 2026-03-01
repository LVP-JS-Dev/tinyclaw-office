#!/usr/bin/env python3
"""Integration wrapper for claw-compactor memory compression.

This module provides a high-level Python API for memory compression operations,
wrapping the underlying mem_compress.py script and library functions.

Typical usage:
    from skills.claw_compactor.integration import ClawCompactor

    compactor = ClawCompactor(workspace="/path/to/workspace")
    result = compactor.benchmark()
    print(f"Token savings: {result['total_saved']}")
"""

import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


class ClawCompactor:
    """High-level API wrapper for claw-compactor memory compression.

    This class provides methods to execute compression operations on a workspace
    containing memory files. It supports workspace validation, benchmarking,
    observation extraction, tiered summarization, and full compression pipeline.

    Attributes:
        workspace: Path to the workspace directory containing memory files
        verbose: Enable verbose output for debugging
    """

    def __init__(self, workspace: str, verbose: bool = False):
        """Initialize the ClawCompactor with a workspace path.

        Args:
            workspace: Path to workspace directory (should contain memory/ or MEMORY.md)
            verbose: Enable verbose output for debugging

        Raises:
            ValueError: If workspace path doesn't exist or is invalid
            TypeError: If workspace is not a valid directory
        """
        self.workspace = self._validate_workspace(workspace)
        self.verbose = verbose

        # Add scripts/ to path for imports
        script_dir = Path(__file__).parent / "scripts"
        lib_dir = Path(__file__).parent / "lib"
        sys.path.insert(0, str(script_dir))
        sys.path.insert(0, str(lib_dir))

    def _validate_workspace(self, workspace: str) -> Path:
        """Validate and return workspace Path.

        Args:
            workspace: Path string to validate

        Returns:
            Resolved Path object for the workspace

        Raises:
            ValueError: If workspace doesn't exist or isn't a directory
        """
        path = Path(workspace).resolve()
        if not path.exists():
            raise ValueError(f"Workspace not found: {workspace}")
        if not path.is_dir():
            raise ValueError(f"Workspace is not a directory: {workspace}")
        return path

    def _collect_md_files(self) -> List[Path]:
        """Collect all .md files in workspace (root + memory/).

        Returns:
            List of Path objects for markdown files
        """
        files: List[Path] = []

        # Root level markdown files
        for f in sorted(self.workspace.glob("*.md")):
            files.append(f)

        # Memory directory markdown files
        mem_dir = self.workspace / "memory"
        if mem_dir.is_dir():
            for f in sorted(mem_dir.glob("*.md")):
                if not f.name.startswith('.'):
                    files.append(f)

        return files

    def benchmark(self, json_output: bool = True) -> Dict[str, Any]:
        """Run non-destructive performance benchmark.

        Estimates potential token savings from applying compression techniques
        without modifying any files.

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
        """
        result = self._run_command("benchmark", json_output=json_output)
        if json_output and isinstance(result, dict):
            return result
        return {}

    def observe(self, json_output: bool = True, since: Optional[str] = None) -> Dict[str, Any]:
        """Scan session transcripts and generate observations.

        Compresses session transcripts by extracting factual observations,
        decisions, and action items. Achieves ~97% size reduction.

        Args:
            json_output: If True, return parsed dict; if False, print raw output
            since: Optional date string to filter sessions (YYYY-MM-DD format)

        Returns:
            Dictionary with:
                - processed: Number of new sessions processed
                - total_tracked: Total number of tracked sessions

        Raises:
            RuntimeError: If observe command fails
        """
        args = {} if since is None else {"since": since}
        result = self._run_command("observe", json_output=json_output, **args)
        if json_output and isinstance(result, dict):
            return result
        return {}

    def tiers(self, json_output: bool = True) -> Dict[str, Any]:
        """Generate tiered summaries (L0, L1, L2).

        Creates multiple levels of summarization with increasing compression.
        Saves tiered memory files to memory/MEMORY-{L0,L1,L2}.md

        Args:
            json_output: If True, return parsed dict; if False, print raw output

        Returns:
            Dictionary with:
                - levels: List of tier levels generated
                - total_sections: Number of input sections processed

        Raises:
            RuntimeError: If tiers command fails
        """
        result = self._run_command("tiers", json_output=json_output)
        if json_output and isinstance(result, dict):
            return result
        return {}

    def dict_compress(self, json_output: bool = True) -> Dict[str, Any]:
        """Run dictionary-based compression (CCP).

        Builds a codebook of frequent phrases and replaces them with $XX codes.
        Saves codebook to memory/.codebook.json for decompression.

        Args:
            json_output: If True, return parsed dict; if False, print raw output

        Returns:
            Dictionary with:
                - codebook_entries: Number of entries in codebook
                - files_scanned: Number of files scanned
                - codebook_path: Path to saved codebook

        Raises:
            RuntimeError: If dict command fails
        """
        result = self._run_command("dict", json_output=json_output)
        if json_output and isinstance(result, dict):
            return result
        return {}

    def full(self, json_output: bool = True, since: Optional[str] = None) -> Dict[str, Any]:
        """Run complete compression pipeline.

        Executes the full compression workflow:
        1. Count initial tokens
        2. Observe (scan session transcripts)
        3. Tiers (generate tiered summaries)
        4. Dict (dictionary compression)
        5. Report final token counts

        Args:
            json_output: If True, return parsed dict; if False, print raw output
            since: Optional date string to filter sessions (YYYY-MM-DD format)

        Returns:
            Dictionary with compression statistics (printed output parsed)

        Raises:
            RuntimeError: If full command fails
        """
        args = {} if since is None else {"since": since}
        # Note: full command prints output rather than returning JSON
        result = self._run_command("full", json_output=json_output, **args)
        return result

    def estimate(self, json_output: bool = True) -> Dict[str, Any]:
        """Estimate token counts for workspace files.

        Args:
            json_output: If True, return parsed dict; if False, print raw output

        Returns:
            Dictionary with:
                - files: List of file token counts
                - total_tokens: Sum of all file token counts

        Raises:
            RuntimeError: If estimate command fails
        """
        result = self._run_command("estimate", json_output=json_output)
        if json_output and isinstance(result, dict):
            return result
        return {}

    def _run_command(self, command: str, json_output: bool = True, **kwargs) -> Any:
        """Run a compression command via subprocess.

        Args:
            command: Command name (benchmark, observe, tiers, full, etc.)
            json_output: If True, parse and return JSON output
            **kwargs: Additional command arguments

        Returns:
            Parsed JSON dict if json_output=True, else None

        Raises:
            RuntimeError: If command execution fails
        """
        script_path = Path(__file__).parent / "scripts" / "mem_compress.py"

        if not script_path.exists():
            raise RuntimeError(f"Script not found: {script_path}")

        cmd = [sys.executable, str(script_path), str(self.workspace), command]

        # Add optional arguments
        if json_output:
            cmd.append("--json")

        for key, value in kwargs.items():
            cmd.extend([f"--{key}", str(value)])

        if self.verbose:
            print(f"Running: {' '.join(cmd)}", file=sys.stderr)

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=False,
                cwd=str(self.workspace)
            )

            if result.returncode != 0:
                error_msg = result.stderr.strip() or result.stdout.strip()
                raise RuntimeError(
                    f"Command '{command}' failed with exit code {result.returncode}: {error_msg}"
                )

            if json_output and result.stdout.strip():
                try:
                    return json.loads(result.stdout.strip())
                except json.JSONDecodeError as e:
                    # Some commands (like 'full') don't output valid JSON
                    if self.verbose:
                        print(f"Warning: Could not parse JSON output: {e}", file=sys.stderr)
                    return result.stdout.strip()

            return result.stdout.strip()

        except FileNotFoundError as e:
            raise RuntimeError(f"Failed to execute command: {e}")
        except Exception as e:
            raise RuntimeError(f"Unexpected error running command '{command}': {e}")

    def get_memory_dir(self) -> Path:
        """Get or create the memory directory for artifacts.

        Returns:
            Path to the memory directory
        """
        mem_dir = self.workspace / "memory"
        mem_dir.mkdir(exist_ok=True)
        return mem_dir

    def get_artifacts(self) -> Dict[str, Any]:
        """Get information about compression artifacts.

        Returns:
            Dictionary with:
                - codebook: Path to codebook if exists
                - observations_dir: Path to observations directory
                - observation_files: List of observation file paths
        """
        mem_dir = self.get_memory_dir()

        artifacts = {
            "codebook": None,
            "observations_dir": mem_dir / "observations",
            "observation_files": []
        }

        codebook_path = mem_dir / ".codebook.json"
        if codebook_path.exists():
            artifacts["codebook"] = codebook_path

        obs_dir = mem_dir / "observations"
        if obs_dir.is_dir():
            artifacts["observation_files"] = sorted(obs_dir.glob("*.md"))

        return artifacts


def main():
    """CLI entry point for integration module.

    Allows running compression operations via:
        python -m skills.claw_compactor.integration --workspace <path> --command <cmd>
    """
    import argparse

    parser = argparse.ArgumentParser(
        description="Claw-compactor integration wrapper for memory compression"
    )
    parser.add_argument(
        "--workspace",
        required=True,
        help="Workspace directory path"
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
        compactor = ClawCompactor(args.workspace, verbose=args.verbose)

        command_map = {
            "benchmark": lambda: compactor.benchmark(json_output=args.json),
            "observe": lambda: compactor.observe(json_output=args.json, since=args.since),
            "tiers": lambda: compactor.tiers(json_output=args.json),
            "full": lambda: compactor.full(json_output=args.json, since=args.since),
            "dict": lambda: compactor.dict_compress(json_output=args.json),
            "estimate": lambda: compactor.estimate(json_output=args.json),
        }

        result = command_map[args.command]()

        if args.json and isinstance(result, dict):
            print(json.dumps(result, indent=2))
        elif result:
            print(result)

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
