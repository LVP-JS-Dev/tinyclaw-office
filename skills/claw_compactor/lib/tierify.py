#!/usr/bin/env python3
"""Generate tiered summaries (L0/L1/L2) for progressive context loading.

L0: ~200 tokens - Key facts and decisions
L1: ~500 tokens - Important details and context
L2: ~1000 tokens - Full summary
"""

import re
from typing import Dict, List


def generate_tiers(text: str) -> Dict[str, str]:
    """Generate tiered summaries from text.

    Args:
        text: Source text

    Returns:
        Dictionary with L0, L1, L2 summaries
    """
    sections = parse_sections(text)

    # L0: Key facts only (headings and first sentences)
    l0_lines = []
    for section in sections[:5]:  # Top 5 sections
        heading = section.get('heading', '')
        content = section.get('content', '')
        first_sentence = content.split('.')[0] if content else ''
        l0_lines.append(f"## {heading}\n{first_sentence}.")

    # L1: Important details
    l1_lines = []
    for section in sections[:10]:
        heading = section.get('heading', '')
        content = section.get('content', '')
        # Take first 3 sentences
        sentences = content.split('.')[:3]
        l1_lines.append(f"## {heading}\n{'.'.join(sentences)}.")

    # L2: Full summary (all sections)
    l2_lines = []
    for section in sections:
        heading = section.get('heading', '')
        content = section.get('content', '')
        l2_lines.append(f"## {heading}\n{content}")

    return {
        'L0': '\n\n'.join(l0_lines) if l0_lines else '# Summary\n\nNo content.',
        'L1': '\n\n'.join(l1_lines) if l1_lines else '# Summary\n\nNo content.',
        'L2': '\n\n'.join(l2_lines) if l2_lines else text,
    }


def parse_sections(text: str) -> List[Dict[str, str]]:
    """Parse markdown sections from text.

    Args:
        text: Markdown text

    Returns:
        List of section dictionaries with 'heading' and 'content'
    """
    sections = []
    lines = text.split('\n')

    current_heading = 'Introduction'
    current_content = []

    for line in lines:
        heading_match = re.match(r'^#+\s+(.+)$', line)

        if heading_match:
            # Save previous section
            if current_content:
                sections.append({
                    'heading': current_heading,
                    'content': '\n'.join(current_content).strip()
                })

            # Start new section
            current_heading = heading_match.group(1)
            current_content = []
        else:
            current_content.append(line)

    # Don't forget the last section
    if current_content:
        sections.append({
            'heading': current_heading,
            'content': '\n'.join(current_content).strip()
        })

    return sections
