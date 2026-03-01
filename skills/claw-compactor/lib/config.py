#!/usr/bin/env python3
"""Configuration management for claw-compactor."""

import json
from pathlib import Path
from typing import Any, Dict


DEFAULT_CONFIG = {
    'chars_per_token': 4,
    'level0_max_tokens': 200,
    'level1_max_tokens': 500,
    'dedup_similarity_threshold': 0.6,
    'dedup_shingle_size': 3,
}


def load_config(workspace: Path) -> Dict[str, Any]:
    """Load configuration from workspace.

    Args:
        workspace: Path to workspace directory

    Returns:
        Configuration dictionary
    """
    config_path = workspace / 'claw-compactor-config.json'

    if not config_path.exists():
        return DEFAULT_CONFIG.copy()

    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            user_config = json.load(f)

        # Merge with defaults
        config = DEFAULT_CONFIG.copy()
        config.update(user_config)

        return config

    except (json.JSONDecodeError, OSError):
        return DEFAULT_CONFIG.copy()


def save_config(workspace: Path, config: Dict[str, Any]) -> None:
    """Save configuration to workspace.

    Args:
        workspace: Path to workspace directory
        config: Configuration dictionary
    """
    config_path = workspace / 'claw-compactor-config.json'

    with open(config_path, 'w', encoding='utf-8') as f:
        json.dump(config, f, indent=2)
