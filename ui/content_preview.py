#!/usr/bin/env python3
"""
Content Preview - renders extracted JSON chunks as human-readable Streamlit UI.
Lets users verify the extraction captured headings, links, tables, etc. correctly.
"""

import json
import re
import streamlit as st
from typing import Optional


def render_content_preview(content_json: str):
    """Parse big_chunks JSON and render each small_chunk visually."""
    try:
        data = json.loads(content_json)
    except Exception:
        st.warning("Could not parse extracted content for preview.")
        return

    big_chunks = data.get('big_chunks', [])
    if not big_chunks:
        st.info("No content extracted.")
        return

    # Accumulate table rows between TABLE_HEADER and the next non-TABLE_ROW chunk
    _table_buf: list[str] = []
    _table_header: Optional[str] = None

    def flush_table():
        nonlocal _table_buf, _table_header
        if _table_header is not None:
            _render_markdown_table(_table_header, _table_buf)
        _table_header = None
        _table_buf = []

    for chunk in big_chunks:
        name = chunk.get('content_name', '')
        items = chunk.get('small_chunks', [])

        # Section divider with name
        st.markdown(f"---")
        st.markdown(f"<span style='color:#888;font-size:0.78em;font-weight:600;letter-spacing:0.05em;text-transform:uppercase'>{name}</span>", unsafe_allow_html=True)

        _table_header = None
        _table_buf = []

        for item in items:
            if not item:
                continue

            # Table rows — buffer them
            if item.startswith("TABLE_HEADER:"):
                flush_table()
                _table_header = item[len("TABLE_HEADER:"):].strip()
                continue
            elif item.startswith("TABLE_ROW:"):
                _table_buf.append(item[len("TABLE_ROW:"):].strip())
                continue
            else:
                flush_table()

            # FAQ pair
            if item.startswith("FAQ_Q:"):
                q = item[len("FAQ_Q:"):].strip()
                st.markdown(f"**Q: {q}**")
                continue
            if item.startswith("FAQ_A:"):
                a = item[len("FAQ_A:"):].strip()
                st.markdown(f"> {a}")
                continue

            # Headings
            if item.startswith("H1:"):
                st.markdown(f"# {item[3:].strip()}")
            elif item.startswith("H2:") or item.startswith("HEADER:"):
                text = re.sub(r'^H2:|^HEADER:', '', item).strip()
                st.markdown(f"## {text}")
            elif item.startswith("H3:"):
                st.markdown(f"### {item[3:].strip()}")
            elif item.startswith("H4:"):
                st.markdown(f"#### {item[3:].strip()}")

            # Metadata fields
            elif item.startswith(("META_DESC:", "PUBLISHED:", "UPDATED:", "AUTHOR:", "SCHEMA_RATING:")):
                st.caption(item)

            # Lead / Subtitle / Summary
            elif item.startswith("SUBTITLE:"):
                st.markdown(f"*{item[9:].strip()}*")
            elif item.startswith("LEAD:"):
                st.markdown(item[5:].strip())
            elif item.startswith("SUMMARY:"):
                st.info(item[8:].strip())

            # Content
            elif item.startswith("CONTENT:"):
                st.markdown(item[8:].strip())

            # Lists
            elif item.startswith("UL:") or item.startswith("OL:"):
                prefix = "UL:" if item.startswith("UL:") else "OL:"
                raw = item[len(prefix):].strip()
                _render_list(raw, ordered=item.startswith("OL:"))

            # Legacy LIST: format (fallback)
            elif item.startswith("LIST:"):
                raw = item[5:].strip()
                _render_list(raw.replace(' // ', ' | '), ordered=False)

            # Definition list
            elif item.startswith("DEF_LIST:"):
                raw = item[9:].strip()
                entries = [e.strip() for e in raw.split(' | ')]
                md_lines = []
                for entry in entries:
                    if ':' in entry:
                        term, _, defn = entry.partition(':')
                        md_lines.append(f"**{term.strip()}**: {defn.strip()}")
                    else:
                        md_lines.append(entry)
                st.markdown('\n\n'.join(md_lines))

            # Blockquote
            elif item.startswith("BLOCKQUOTE:"):
                st.markdown(f"> {item[11:].strip()}")

            # Warnings / notices
            elif item.startswith("WARNING:"):
                st.warning(item[8:].strip())
            elif item.startswith("NOTICE:"):
                st.info(item[7:].strip())

            # Fallback — plain text
            else:
                st.markdown(item)

        flush_table()


def _render_list(raw: str, ordered: bool):
    """Render pipe-separated list items as markdown bullets/numbers."""
    items = [i.strip() for i in raw.split(' | ') if i.strip()]
    lines = []
    for i, item in enumerate(items):
        if item.startswith('> '):
            # Nested item
            lines.append(f"  - {item[2:]}")
        elif ordered:
            # Strip existing number prefix if present (e.g. "1. text")
            text = re.sub(r'^\d+\.\s*', '', item)
            lines.append(f"{i+1}. {text}")
        else:
            lines.append(f"- {item}")
    if lines:
        st.markdown('\n'.join(lines))


def _render_markdown_table(header_row: str, data_rows: list):
    """Render a pipe-separated header + rows as a Markdown table."""
    cols = [c.strip() for c in header_row.split(' | ')]
    separator = ' | '.join(['---'] * len(cols))
    lines = [
        '| ' + ' | '.join(cols) + ' |',
        '| ' + separator + ' |',
    ]
    for row in data_rows:
        cells = [c.strip() for c in row.split(' | ')]
        # Pad or trim to match header column count
        while len(cells) < len(cols):
            cells.append('')
        cells = cells[:len(cols)]
        lines.append('| ' + ' | '.join(cells) + ' |')
    st.markdown('\n'.join(lines))
