#!/usr/bin/env python3
"""Session observation extraction.

Compresses session transcripts by extracting factual observations,
decisions, and action items.
"""

import json
from typing import Any, Dict, List


def parse_session_jsonl(path) -> List[Dict[str, Any]]:
    """Parse a session JSONL file.

    Args:
        path: Path to JSONL file

    Returns:
        List of message dictionaries
    """
    messages = []

    with open(path, 'r', encoding='utf-8') as f:
        for line in f:
            if line.strip():
                try:
                    messages.append(json.loads(line))
                except json.JSONDecodeError:
                    continue

    return messages


def extract_tool_interactions(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Extract tool use interactions from messages.

    Args:
        messages: List of message dictionaries

    Returns:
        List of tool interactions
    """
    interactions = []

    for msg in messages:
        if msg.get('role') == 'assistant':
            content = msg.get('content', [])

            if isinstance(content, list):
                for item in content:
                    if isinstance(item, dict) and item.get('type') == 'tool_use':
                        interactions.append({
                            'tool': item.get('name', ''),
                            'input': item.get('input', {}),
                            'id': item.get('id', '')
                        })

    return interactions


def rule_extract_observations(interactions: List[Dict[str, Any]]) -> List[str]:
    """Extract observations from tool interactions using rule-based approach.

    Args:
        interactions: List of tool interactions

    Returns:
        List of observation strings
    """
    observations = []

    for interaction in interactions:
        tool_name = interaction.get('tool', '')
        tool_input = interaction.get('input', {})

        # Extract key facts based on tool type
        if tool_name == 'write_file':
            path = tool_input.get('file_path', '')
            observations.append(f"Created file: {path}")

        elif tool_name == 'read_file':
            path = tool_input.get('file_path', '')
            observations.append(f"Read file: {path}")

        elif tool_name == 'Bash':
            command = tool_input.get('command', '')
            observations.append(f"Executed: {command[:80]}...")

        elif tool_name == 'AskUserQuestion':
            questions = tool_input.get('questions', [])
            observations.append(f"Asked {len(questions)} question(s)")

    return observations


def format_observations_md(observations: List[str]) -> str:
    """Format observations as markdown.

    Args:
        observations: List of observation strings

    Returns:
        Markdown formatted observations
    """
    if not observations:
        return "# Observations\n\nNo observations extracted.\n"

    lines = ["# Observations\n"]

    for obs in observations:
        lines.append(f"- {obs}")

    return "\n".join(lines) + "\n"
