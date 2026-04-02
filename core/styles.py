"""
core/styles.py
==============
Shared Streamlit CSS injected on every page via apply_styles().

Fixes included
--------------
- Page title / subtitle never truncate — they wrap naturally
- Section titles, result boxes, status messages consistent across pages
- Removes Streamlit default top-padding that wastes header space
"""

import streamlit as st


def apply_styles():
    """Inject shared CSS into the current Streamlit page."""
    st.markdown(_CSS, unsafe_allow_html=True)


_CSS = """
<style>

/* ── Remove excessive top padding Streamlit adds ────────────────────── */
.block-container {
    padding-top: 1.2rem !important;
    padding-bottom: 2rem !important;
    max-width: 1100px;
}

/* ── Stop Streamlit wrapper divs from clipping content ──────────────── */
[data-testid="stMarkdownContainer"],
[data-testid="stMarkdownContainer"] > div,
.stMarkdown,
.element-container,
.row-widget {
    overflow: visible !important;
    min-width: 0;
    white-space: normal !important;
}

/* ── Page title ──────────────────────────────────────────────────────── */
.page-title {
    font-size: clamp(1.4rem, 3.5vw, 2.1rem);
    font-weight: 700;
    color: #1A2F6B;
    line-height: 1.25;
    margin: 0 0 0.25rem 0;
    white-space: normal !important;
    overflow: visible !important;
    text-overflow: unset !important;
    display: block;
    width: 100%;
}

/* ── Page subtitle ───────────────────────────────────────────────────── */
.page-subtitle {
    font-size: clamp(0.85rem, 2vw, 1rem);
    color: #555;
    font-style: italic;
    margin: 0 0 1rem 0;
    white-space: normal !important;
    overflow: visible !important;
    text-overflow: unset !important;
    display: block;
    width: 100%;
}

/* ── Section headings inside containers ─────────────────────────────── */
.section-title {
    font-size: 1rem;
    font-weight: 600;
    color: #1A5276;
    margin-bottom: 0.4rem;
}

/* ── Result box ──────────────────────────────────────────────────────── */
.result-box {
    background: #F0F4FA;
    border: 1px solid #C5D5E8;
    border-radius: 10px;
    padding: 1.1rem 1.4rem;
    margin-bottom: 1rem;
}

.result-title {
    font-size: 1rem;
    color: #1a2332;
    margin-bottom: 0.4rem;
}

.date-loc { font-weight: 600; }
.loc      { font-weight: 700; color: #1A2F6B; }

.fallow-label {
    font-size: 0.9rem;
    color: #555;
    margin-bottom: 0.5rem;
}

.paw-big {
    font-size: 3rem;
    font-weight: 800;
    color: #1A3A6B;
    line-height: 1;
}

.paw-unit {
    font-size: 1.4rem;
    color: #1A3A6B;
    margin-left: 4px;
}

.pawc-pct {
    font-size: 1.1rem;
    color: #555;
    margin-left: 12px;
}

/* ── Status / spinner messages ───────────────────────────────────────── */
.status-msg {
    font-size: 0.9rem;
    color: #1A5276;
    font-style: italic;
}

/* ── Tighten Streamlit radio / selectbox labels ──────────────────────── */
div[data-testid="stRadio"] label,
div[data-testid="stSelectbox"] label {
    font-size: 0.9rem;
}

/* ── Container borders slightly softer ───────────────────────────────── */
div[data-testid="stVerticalBlockBorderWrapper"] {
    border-radius: 10px !important;
    border-color: #D0DCF0 !important;
}

/* ── Divider thinner ────────────────────────────────────────────────── */
hr {
    margin: 0.6rem 0 !important;
    border-color: #E8EDF5 !important;
}

</style>
"""
