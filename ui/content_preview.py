#!/usr/bin/env python3
"""
Content Preview - renders extracted JSON chunks as human-readable Streamlit UI.
Lets users verify the extraction captured headings, links, tables, etc. correctly.
Supports optional section selection: pass selection_key to enable per-section checkboxes.
"""

import json
import re
import streamlit as st
from typing import Optional

from ui.content_selection import build_chunk_labels


def render_content_preview(content_json: str, selection_key: Optional[str] = None):
    """Parse big_chunks JSON and render each small_chunk visually in a scrollable container.

    Args:
        content_json: Extracted content as JSON string.
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

    big_chunks = data.get('big_chunks', [])
    if not big_chunks:
        st.info("No content extracted.")
        return

    chunk_labels = build_chunk_labels(big_chunks)

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

    _table_buf: list[str] = []
    _table_header: Optional[str] = None

    def flush_table():
        nonlocal _table_buf, _table_header
        if _table_header is not None:
            _render_markdown_table(_table_header, _table_buf, c)
        _table_header = None
        _table_buf = []

    for chunk in big_chunks:
        idx = chunk.get('big_chunk_index')
        label = chunk_labels.get(idx, f"Section {idx}")
        items = chunk.get('small_chunks', [])

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
            _table_header = None
            _table_buf = []
            continue

        _table_header = None
        _table_buf = []

        for item in items:
            if not item:
                continue

            if item.startswith("TABLE_HEADER:"):
                flush_table()
                _table_header = item[len("TABLE_HEADER:"):].strip()
                continue
            elif item.startswith("TABLE_ROW:"):
                _table_buf.append(item[len("TABLE_ROW:"):].strip())
                continue
            else:
                flush_table()

            if item.startswith("FAQ_Q:"):
                c.markdown(f"**Q: {item[len('FAQ_Q:'):].strip()}**")
                continue
            if item.startswith("FAQ_A:"):
                c.markdown(f"> {item[len('FAQ_A:'):].strip()}")
                continue

            if item.startswith("H1:"):
                c.markdown(f"# {item[3:].strip()}")
            elif item.startswith("H2:") or item.startswith("HEADER:"):
                text = re.sub(r'^H2:|^HEADER:', '', item).strip()
                c.markdown(f"## {text}")
            elif item.startswith("H3:"):
                c.markdown(f"### {item[3:].strip()}")
            elif item.startswith("H4:"):
                c.markdown(f"#### {item[3:].strip()}")
            elif item.startswith(("META_DESC:", "PUBLISHED:", "UPDATED:", "AUTHOR:", "SCHEMA_RATING:")):
                c.caption(item)
            elif item.startswith("SUBTITLE:"):
                c.markdown(f"*{item[9:].strip()}*")
            elif item.startswith("LEAD:"):
                c.markdown(item[5:].strip())
            elif item.startswith("SUMMARY:"):
                c.info(item[8:].strip())
            elif item.startswith("CONTENT:"):
                c.markdown(item[8:].strip())
            elif item.startswith("UL:") or item.startswith("OL:"):
                prefix = "UL:" if item.startswith("UL:") else "OL:"
                _render_list(item[len(prefix):].strip(), ordered=item.startswith("OL:"), target=c)
            elif item.startswith("LIST:"):
                _render_list(item[5:].strip().replace(' // ', ' | '), ordered=False, target=c)
            elif item.startswith("DEF_LIST:"):
                entries = [e.strip() for e in item[9:].strip().split(' | ')]
                md_lines = []
                for entry in entries:
                    if ':' in entry:
                        term, _, defn = entry.partition(':')
                        md_lines.append(f"**{term.strip()}**: {defn.strip()}")
                    else:
                        md_lines.append(entry)
                c.markdown('\n\n'.join(md_lines))
            elif item.startswith("BLOCKQUOTE:"):
                c.markdown(f"> {item[11:].strip()}")
            elif item.startswith("WARNING:"):
                c.warning(item[8:].strip())
            elif item.startswith("NOTICE:"):
                c.info(item[7:].strip())
            else:
                c.markdown(item)

        flush_table()

    if selection_key is not None:
        st.session_state[selection_key] = list(selected_set)


def _render_list(raw: str, ordered: bool, target=st):
    items = [i.strip() for i in raw.split(' | ') if i.strip()]
    lines = []
    for i, item in enumerate(items):
        if item.startswith('> '):
            lines.append(f"  - {item[2:]}")
        elif ordered:
            text = re.sub(r'^\d+\.\s*', '', item)
            lines.append(f"{i+1}. {text}")
        else:
            lines.append(f"- {item}")
    if lines:
        target.markdown('\n'.join(lines))


def _render_markdown_table(header_row: str, data_rows: list, target=st):
    cols = [c.strip() for c in header_row.split(' | ')]
    separator = ' | '.join(['---'] * len(cols))
    lines = [
        '| ' + ' | '.join(cols) + ' |',
        '| ' + separator + ' |',
    ]
    for row in data_rows:
        cells = [c.strip() for c in row.split(' | ')]
        while len(cells) < len(cols):
            cells.append('')
        cells = cells[:len(cols)]
        lines.append('| ' + ' | '.join(cells) + ' |')
    target.markdown('\n'.join(lines))
