#!/usr/bin/env python3
"""
Content Preview - renders extracted JSON sections as human-readable Streamlit UI.
Lets users verify the extraction captured headings, links, tables, etc. correctly.
Supports optional section selection: pass selection_key to enable per-section checkboxes.
"""

import json
import streamlit as st
from typing import Optional

from ui.content_selection import build_chunk_labels


def render_content_preview(content_json: str, selection_key: Optional[str] = None):
    """Parse sections JSON and render each section's markdown content in a scrollable container.

    Args:
        content_json: Extracted content as JSON string with {"sections": [...]} format.
        selection_key: If provided, renders a checkbox per section so users can
                       exclude sections from LLM analysis. State stored in
                       st.session_state[selection_key] as list of selected section names.
                       If None, renders read-only (post-analysis mode).
    """
    try:
        data = json.loads(content_json)
    except Exception:
        st.warning("Could not parse extracted content for preview.")
        return

    sections = data.get('sections', [])
    if not sections:
        st.info("No content extracted.")
        return

    section_labels = build_chunk_labels(sections)

    # --- Selection state ---
    selected_set: set = set()
    if selection_key is not None:
        cb_prefix = f"{selection_key}__cb__"
        # On fresh extraction (selection_key was popped), clear stale checkbox keys
        if selection_key not in st.session_state:
            for k in [k for k in st.session_state if k.startswith(cb_prefix)]:
                del st.session_state[k]

    # --- Scrollable preview container ---
    c = st.container(height=500)

    for section in sections:
        idx = section.get('index')
        label = section_labels.get(idx, f"Section {idx}")
        content = section.get('content', '')

        c.markdown("---")
        if selection_key is not None:
            cb_key = f"{cb_prefix}{label}"
            with c:
                col_toggle, col_label = st.columns([1, 12])
                is_selected = col_toggle.checkbox(
                    "Include",
                    value=st.session_state.get(cb_key, True),
                    key=cb_key,
                    label_visibility="collapsed",
                )
                col_label.markdown(
                    f"<span style='color:#888;font-size:0.78em;font-weight:600;"
                    f"letter-spacing:0.05em;text-transform:uppercase'>{label}</span>",
                    unsafe_allow_html=True,
                )
            if is_selected:
                selected_set.add(label)
        else:
            is_selected = True
            c.markdown(
                f"<span style='color:#888;font-size:0.78em;font-weight:600;"
                f"letter-spacing:0.05em;text-transform:uppercase'>{label}</span>",
                unsafe_allow_html=True
            )

        if not is_selected:
            c.markdown(
                "<span style='color:#bbb;font-size:0.78em;font-style:italic'>"
                "Section excluded from analysis</span>",
                unsafe_allow_html=True
            )
            continue

        if content:
            c.markdown(content)

    if selection_key is not None:
        st.session_state[selection_key] = list(selected_set)
