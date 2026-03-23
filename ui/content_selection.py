#!/usr/bin/env python3

import json
from typing import Iterable, Optional


def build_chunk_labels(big_chunks: list[dict]) -> dict[int, str]:
    """Build stable, human-readable labels for each big chunk."""
    name_counts: dict[str, int] = {}
    labels: dict[int, str] = {}

    for position, chunk in enumerate(big_chunks, start=1):
        idx = chunk.get('big_chunk_index', position)
        name = chunk.get('content_name') or f"Section {idx}"
        name_counts[name] = name_counts.get(name, 0) + 1

    for position, chunk in enumerate(big_chunks, start=1):
        idx = chunk.get('big_chunk_index', position)
        name = chunk.get('content_name') or f"Section {idx}"
        labels[idx] = f"{name} ({idx})" if name_counts[name] > 1 else name

    return labels


def filter_content_json(content_json: str, selected_labels: Optional[Iterable[str]]) -> Optional[str]:
    """Return a JSON string containing only the selected big chunks."""
    try:
        data = json.loads(content_json)
    except Exception:
        return content_json

    if selected_labels is None:
        return content_json

    selected_set = set(selected_labels)
    big_chunks = data.get('big_chunks', [])
    chunk_labels = build_chunk_labels(big_chunks)
    filtered_chunks = []

    for position, chunk in enumerate(big_chunks, start=1):
        idx = chunk.get('big_chunk_index', position)
        if chunk_labels.get(idx, f"Section {idx}") in selected_set:
            filtered_chunks.append(chunk)

    if not filtered_chunks:
        return None

    data['big_chunks'] = filtered_chunks
    return json.dumps(data)
