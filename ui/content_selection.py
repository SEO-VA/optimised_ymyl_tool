#!/usr/bin/env python3

import json
from typing import Iterable, Optional


def build_chunk_labels(sections: list[dict]) -> dict[int, str]:
    """Build stable, human-readable labels for each section."""
    name_counts: dict[str, int] = {}
    labels: dict[int, str] = {}

    for position, section in enumerate(sections, start=1):
        idx = section.get('index', position)
        name = section.get('name') or f"Section {idx}"
        name_counts[name] = name_counts.get(name, 0) + 1

    for position, section in enumerate(sections, start=1):
        idx = section.get('index', position)
        name = section.get('name') or f"Section {idx}"
        labels[idx] = f"{name} ({idx})" if name_counts[name] > 1 else name

    return labels


def filter_content_json(content_json: str, selected_labels: Optional[Iterable[str]]) -> Optional[str]:
    """Return a JSON string containing only the selected sections."""
    try:
        data = json.loads(content_json)
    except Exception:
        return content_json

    if selected_labels is None:
        return content_json

    selected_set = set(selected_labels)
    sections = data.get('sections', [])
    section_labels = build_chunk_labels(sections)
    filtered = []

    for position, section in enumerate(sections, start=1):
        idx = section.get('index', position)
        if section_labels.get(idx, f"Section {idx}") in selected_set:
            filtered.append(section)

    if not filtered:
        return None

    data['sections'] = filtered
    return json.dumps(data)
