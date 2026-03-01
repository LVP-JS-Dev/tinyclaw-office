#!/usr/bin/env python3
"""Unified entry point for claw-compactor skill.

Usage:
    python3 mem_compress.py <workspace> [options]

Commands:
    compress  - Rule-based compression of memory files
    estimate  - Token count estimation
    dedup     - Cross-file duplicate detection
    tiers     - Generate tiered summaries
    audit     - Workspace memory health check
    observe   - Compress session transcripts into observations
    dict      - Dictionary-based compression
    optimize  - Tokenizer-level format optimization
    full      - Run complete pipeline (all steps in order)
    benchmark - Performance report with before/after stats
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime, date
from pathlib import Path
from typing import Dict, Any, List, Optional

# Ensure scripts/ is on path for lib imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.tokens import estimate_tokens, using_tiktoken
from lib.exceptions import FileNotFoundError_, MemCompressError


def _workspace_path(workspace: str) -> Path:
    """Validate and return workspace Path. Exits on error."""
    p = Path(workspace)
    if not p.exists():
        print(f"Error: workspace not found: {workspace}", file=sys.stderr)
        sys.exit(1)
    if not p.is_dir():
        print(f"Error: workspace is not a directory: {workspace}", file=sys.stderr)
        sys.exit(1)
    return p


def _count_tokens_in_workspace(workspace: Path) -> int:
    """Count total tokens in all .md files in workspace."""
    total = 0
    for f in sorted(workspace.glob("*.md")):
        total += estimate_tokens(f.read_text(encoding="utf-8", errors="replace"))

    mem_dir = workspace / "memory"
    if mem_dir.is_dir():
        for f in sorted(mem_dir.glob("*.md")):
            total += estimate_tokens(f.read_text(encoding="utf-8", errors="replace"))

    return total


def _collect_md_files(workspace: Path) -> List[Path]:
    """Collect all .md files in workspace (root + memory/)."""
    files: List[Path] = []
    for f in sorted(workspace.glob("*.md")):
        files.append(f)

    mem_dir = workspace / "memory"
    if mem_dir.is_dir():
        for f in sorted(mem_dir.glob("*.md")):
            if not f.name.startswith('.'):
                files.append(f)

    return files


# ── Command handlers ─────────────────────────────────────────────


def cmd_estimate(workspace: Path, args) -> int:
    """Estimate token counts for workspace files."""
    files = _collect_md_files(workspace)
    if not files:
        print("No markdown files found.", file=sys.stderr)
        return 1

    results = []
    for f in files:
        text = f.read_text(encoding="utf-8", errors="replace")
        tokens = estimate_tokens(text)
        results.append({
            "file": str(f.relative_to(workspace)),
            "tokens": tokens
        })

    if args.json:
        print(json.dumps({"files": results, "total_tokens": sum(r["tokens"] for r in results)}, indent=2))
    else:
        for r in results:
            print(f"{r['file']}: {r['tokens']:,} tokens")
        print(f"\nTotal: {sum(r['tokens'] for r in results):,} tokens")

    return 0


def cmd_observe(workspace: Path, args) -> int:
    """Scan session transcripts and generate observations."""
    from lib.observer import parse_session_jsonl, extract_tool_interactions, rule_extract_observations, format_observations_md

    # OpenClaw stores transcripts per-agent at ~/.openclaw/agents/<agent_id>/sessions/
    sessions_base = os.path.expanduser("~/.openclaw/agents")
    sessions_dirs = []

    if os.path.isdir(sessions_base):
        for agent_id in os.listdir(sessions_base):
            agent_sessions = os.path.join(sessions_base, agent_id, "sessions")
            if os.path.isdir(agent_sessions):
                sessions_dirs.append(agent_sessions)

    if not sessions_dirs:
        print(f"No session directories found under {sessions_base}/*/sessions/", file=sys.stderr)
        return 1

    sessions_dir = sessions_dirs[0]  # primary agent

    # Load tracker
    mem_dir = workspace / "memory"
    mem_dir.mkdir(exist_ok=True)
    tracker_path = mem_dir / ".observed-sessions.json"
    tracker: Dict[str, str] = {}

    if tracker_path.exists():
        try:
            tracker = json.loads(tracker_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            tracker = {}

    # Find session files
    session_files = sorted(Path(sessions_dir).glob("*.jsonl"))
    since = getattr(args, 'since', None)
    new_count = 0

    obs_dir = mem_dir / "observations"
    obs_dir.mkdir(exist_ok=True)

    for sf in session_files:
        if sf.name in tracker:
            continue

        # Apply --since filter
        if since:
            try:
                # Try to extract date from filename
                fname = sf.stem
                if fname < since:
                    continue
            except Exception:
                pass

        try:
            messages = parse_session_jsonl(sf)
            interactions = extract_tool_interactions(messages)

            if not interactions:
                tracker[sf.name] = datetime.now().isoformat()
                continue

            observations = rule_extract_observations(interactions)

            if observations:
                md = format_observations_md(observations)
                obs_file = obs_dir / f"{sf.stem}.md"
                obs_file.write_text(md, encoding="utf-8")
                new_count += 1
                tracker[sf.name] = datetime.now().isoformat()

        except Exception as e:
            print(f"Warning: failed to process {sf.name}: {e}", file=sys.stderr)

    # Save tracker
    tracker_path.write_text(json.dumps(tracker, indent=2), encoding="utf-8")

    if args.json:
        print(json.dumps({"processed": new_count, "total_tracked": len(tracker)}))
    else:
        print(f"Processed {new_count} new session(s), {len(tracker)} total tracked.")

    return 0


def cmd_tiers(workspace: Path, args) -> int:
    """Generate tiered summaries."""
    from lib.tierify import generate_tiers, parse_sections

    files = _collect_md_files(workspace)
    if not files:
        print("No memory files found.", file=sys.stderr)
        return 1

    all_sections = []
    for f in files:
        text = f.read_text(encoding="utf-8", errors="replace")
        sections = parse_sections(text)
        all_sections.extend(sections)

    # Combine all content and generate tiers
    combined_text = '\n\n'.join([
        f"## {s['heading']}\n{s['content']}"
        for s in all_sections
    ])

    tiers = generate_tiers(combined_text)

    # Save tiers to memory directory
    mem_dir = workspace / "memory"
    mem_dir.mkdir(exist_ok=True)

    for level, content in tiers.items():
        (mem_dir / f"MEMORY-{level}.md").write_text(content, encoding="utf-8")

    if args.json:
        print(json.dumps({
            "levels": list(tiers.keys()),
            "total_sections": len(all_sections)
        }))
    else:
        print(f"Generated {len(tiers)} tier summaries:")
        for level in tiers:
            tokens = estimate_tokens(tiers[level])
            print(f"  {level}: {tokens:,} tokens")

    return 0


def cmd_dict(workspace: Path, args) -> int:
    """Dictionary-based compression."""
    from lib.dictionary import build_codebook, save_codebook

    files = _collect_md_files(workspace)
    texts = [f.read_text(encoding="utf-8", errors="replace") for f in files]

    mem_dir = workspace / "memory"
    mem_dir.mkdir(exist_ok=True)
    cb_path = mem_dir / ".codebook.json"

    codebook = build_codebook(texts, min_freq=2)
    save_codebook(codebook, cb_path)

    if args.json:
        print(json.dumps({
            "codebook_entries": len(codebook),
            "files_scanned": len(files),
            "codebook_path": str(cb_path)
        }))
    else:
        print(f"Codebook: {len(codebook)} entries from {len(files)} files")
        print(f"Saved to: {cb_path}")

    return 0


def cmd_benchmark(workspace: Path, args) -> int:
    """Non-destructive performance benchmark."""
    from lib.dictionary import build_codebook, compress_text
    from lib.rle import compress as rle_compress
    from lib.tokenizer_optimizer import optimize_tokens

    files = _collect_md_files(workspace)
    if not files:
        if not args.json:
            print("No files found.", file=sys.stderr)
        return 1

    # Read all files
    texts = {}
    for f in files:
        texts[str(f)] = f.read_text(encoding="utf-8", errors="replace")

    combined = '\n'.join(texts.values())

    # Baseline
    baseline_tokens = estimate_tokens(combined)

    # Step 1: Rule engine (simple whitespace optimization)
    rule_compressed = re.sub(r'\n{3,}', '\n\n', combined)
    rule_tokens = estimate_tokens(rule_compressed)

    # Step 2: Dictionary compress
    cb = build_codebook(list(texts.values()), min_freq=2)
    dict_compressed = compress_text(rule_compressed, cb)
    dict_tokens = estimate_tokens(dict_compressed)

    # Step 3: RLE
    ws_paths = [str(workspace)]
    rle_compressed = rle_compress(dict_compressed, ws_paths)
    rle_tokens = estimate_tokens(rle_compressed)

    # Step 4: Tokenizer optimize
    tok_optimized = optimize_tokens(rle_compressed, aggressive=True)
    tok_tokens = estimate_tokens(tok_optimized)

    steps = [
        {"name": "Rule Engine", "before": baseline_tokens, "after": rule_tokens},
        {"name": "Dictionary Compress", "before": rule_tokens, "after": dict_tokens},
        {"name": "RLE Patterns", "before": dict_tokens, "after": rle_tokens},
        {"name": "Tokenizer Optimize", "before": rle_tokens, "after": tok_tokens},
    ]

    for s in steps:
        s["saved"] = s["before"] - s["after"]
        s["pct"] = round((s["saved"] / s["before"] * 100), 1) if s["before"] > 0 else 0.0

    total_saved = baseline_tokens - tok_tokens
    total_pct = round((total_saved / baseline_tokens * 100), 1) if baseline_tokens > 0 else 0.0

    if args.json:
        print(json.dumps({
            "steps": steps,
            "total_before": baseline_tokens,
            "total_after": tok_tokens,
            "total_saved": total_saved,
            "total_pct": total_pct,
        }))
        return 0

    # Human report
    today = date.today().isoformat()
    print(f"=== claw-compactor Performance Report ===")
    print(f"Date: {today}")
    print(f"Engine: {'tiktoken' if using_tiktoken() else 'heuristic'}")
    print(f"Files: {len(files)}")
    print()
    print(f"{'Step':<22} | {'Before':>8} | {'After':>8} | {'Saved':>6} | {'%':>6}")
    print("-" * 58)

    for s in steps:
        print(f"{s['name']:<22} | {s['before']:>8,} | {s['after']:>8,} | {s['saved']:>6,} | {s['pct']:>5.1f}%")

    print("-" * 58)
    print(f"{'TOTAL (memory)':<22} | {baseline_tokens:>8,} | {tok_tokens:>8,} | {total_saved:>6,} | {total_pct:>5.1f}%")
    print()
    print(f"💰 Total savings: {total_saved:,} tokens ({total_pct:.1f}%)")
    print()

    return 0


def cmd_full(workspace: Path, args) -> int:
    """Run complete compression pipeline."""
    # 1. Count initial tokens
    before_tokens = _count_tokens_in_workspace(workspace)
    print(f"Before: {before_tokens:,} tokens")

    # 2. Observe (scan session transcripts)
    try:
        observe_args = argparse.Namespace(json=False, since=getattr(args, 'since', None))
        cmd_observe(workspace, observe_args)
    except Exception as e:
        print(f" observe: skipped ({e})")

    # 3. Tiers
    try:
        tier_args = argparse.Namespace(json=False)
        cmd_tiers(workspace, tier_args)
    except Exception as e:
        print(f" tiers: skipped ({e})")

    # 4. Dict (dictionary compression)
    try:
        dict_args = argparse.Namespace(json=False)
        cmd_dict(workspace, dict_args)
    except Exception as e:
        print(f" dict: skipped ({e})")

    # 5. Final count
    after_tokens = _count_tokens_in_workspace(workspace)
    saved = before_tokens - after_tokens
    pct = (saved / before_tokens * 100) if before_tokens > 0 else 0

    print(f"After: {after_tokens:,} tokens")
    print(f"Tokens saved: {saved:,} ({pct:.0f}%)")

    return 0


# ── Command map & parser ─────────────────────────────────────────


COMMAND_MAP = {
    "compress": lambda w, a: print("Not implemented"),
    "estimate": cmd_estimate,
    "dedup": lambda w, a: print("Not implemented"),
    "tiers": cmd_tiers,
    "audit": lambda w, a: print("Not implemented"),
    "observe": cmd_observe,
    "dict": cmd_dict,
    "optimize": lambda w, a: print("Not implemented"),
    "full": cmd_full,
    "benchmark": cmd_benchmark,
}


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser."""
    parser = argparse.ArgumentParser(
        description="claw-compactor: workspace memory compression toolkit"
    )
    parser.add_argument("workspace", help="Workspace directory path")
    sub = parser.add_subparsers(dest="command")
    sub.required = True

    # Add -v to all subparsers via parent
    _common = argparse.ArgumentParser(add_help=False)
    _common.add_argument("-v", "--verbose", action="store_true", help="Verbose output")

    # estimate
    p = sub.add_parser("estimate", help="Token estimation", parents=[_common])
    p.add_argument("--json", action="store_true")

    # observe
    p = sub.add_parser("observe", help="Compress session transcripts", parents=[_common])
    p.add_argument("--json", action="store_true")
    p.add_argument("--since", type=str, default=None)

    # tiers
    p = sub.add_parser("tiers", help="Generate tiered summaries", parents=[_common])
    p.add_argument("--json", action="store_true")

    # dict
    p = sub.add_parser("dict", help="Dictionary compression", parents=[_common])
    p.add_argument("--json", action="store_true")

    # full
    p = sub.add_parser("full", help="Run complete pipeline", parents=[_common])
    p.add_argument("--json", action="store_true")
    p.add_argument("--since", type=str, default=None)

    # benchmark
    p = sub.add_parser("benchmark", help="Performance benchmark", parents=[_common])
    p.add_argument("--json", action="store_true")

    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()

    if args.verbose:
        import logging
        logging.basicConfig(level=logging.DEBUG)

    workspace = _workspace_path(args.workspace)
    handler = COMMAND_MAP[args.command]
    sys.exit(handler(workspace, args))


if __name__ == "__main__":
    main()
