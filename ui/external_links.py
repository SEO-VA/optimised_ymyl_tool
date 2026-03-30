#!/usr/bin/env python3
"""
Helpers for rendering external links with explicit browser-tab behavior.
"""

import html

import streamlit as st


def _build_same_tab_link_html(label: str, url: str, primary: bool = True) -> str:
    safe_label = html.escape(label)
    safe_url = html.escape(url, quote=True)

    if primary:
        style = (
            "display:flex;align-items:center;justify-content:center;width:100%;"
            "padding:0.55rem 0.75rem;border-radius:0.5rem;box-sizing:border-box;"
            "background:#ff4b4b;color:#ffffff;text-decoration:none;font-weight:600;"
            "border:1px solid #ff4b4b;"
        )
    else:
        style = (
            "display:flex;align-items:center;justify-content:center;width:100%;"
            "padding:0.55rem 0.75rem;border-radius:0.5rem;box-sizing:border-box;"
            "background:transparent;color:inherit;text-decoration:none;font-weight:600;"
            "border:1px solid rgba(49, 51, 63, 0.2);"
        )

    return (
        f'<a href="{safe_url}" target="_self" rel="self" style="{style}">'
        f"{safe_label}"
        "</a>"
    )


def render_same_tab_auth_link(label: str, url: str, primary: bool = True) -> None:
    """Render an external auth link that navigates in the current tab."""
    st.markdown(_build_same_tab_link_html(label, url, primary=primary), unsafe_allow_html=True)
