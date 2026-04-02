"""
core/styles.py — Shared CSS for all pages
==========================================
Single source of truth for the visual style of the Risk Status app.
Based on the How's the season? page as the design template.

Usage in any page:
    from core.styles import apply_styles
    apply_styles()
"""

import streamlit as st


# ── Colour palette ────────────────────────────────────────────────────────────
BLUE_DARK   = "#1a4a6e"   # headings, primary actions
BLUE_MID    = "#2a7ab8"   # section titles, links
BLUE_LIGHT  = "#e8f4fd"   # info backgrounds
GREEN_DARK  = "#1a6a1a"   # above average
GREEN_BG    = "#eaf5ea"   # above average background
ORANGE_DARK = "#8a3a00"   # below average
ORANGE_BG   = "#fdf0e8"   # below average background
TEXT_DARK   = "#1a1a1a"   # body text
TEXT_MID    = "#555"      # secondary text
CHIP_BG     = "#f0f5fb"   # stat chips background
CHIP_BORDER = "#c0d4e8"   # stat chips border
CHIP_TEXT   = "#2a4a6a"   # stat chips text


def apply_styles():
    """Inject the shared CSS into the current Streamlit page."""
    st.markdown("""
<style>
/* ── Fonts ── */
@import url('https://fonts.googleapis.com/css2?family=Merriweather:ital,wght@0,400;0,700;1,400&family=Source+Sans+3:wght@300;400;600;700&display=swap');

html, body, [class*="css"] {
    font-family: 'Source Sans 3', sans-serif;
}

/* ── Page layout ── */
.block-container {
    padding-top: 1.5rem !important;
    padding-bottom: 2rem !important;
    max-width: 1100px !important;
}

/* ── Page title and subtitle ── */
.page-title {
    font-family: 'Merriweather', serif;
    font-size: 2.2rem; font-weight: 700;
    color: #1a4a6e; line-height: 1.15; margin-bottom: 4px;
}
.page-subtitle {
    font-family: 'Merriweather', serif; font-style: italic;
    font-size: 1.0rem; color: #555; margin-bottom: 16px;
}

/* ── Section headings inside containers ── */
.section-title {
    font-family: 'Merriweather', serif;
    font-size: 1.1rem; font-weight: 700;
    color: #2a7ab8; margin-bottom: 12px;
}

/* ── Containers ── */
div[data-testid="stVerticalBlockBorderWrapper"] {
    background: #fff !important;
    border: 1.5px solid #d0dcea !important;
    border-radius: 8px !important;
    padding: 1rem 1.4rem 1.1rem !important;
    margin-bottom: 0.8rem !important;
    box-shadow: 0 1px 4px rgba(26,74,110,0.06) !important;
}

/* ── Stat chips ── */
.chip-row { display: flex; gap: 8px; flex-wrap: wrap; margin: 8px 0 16px 0; }
.chip {
    background: #f0f5fb; border: 1px solid #c0d4e8;
    border-radius: 4px; padding: 3px 10px;
    font-size: 0.82rem; color: #2a4a6a;
}
.chip b { color: #1a1a1a; }

/* ── Result headline (Season) ── */
.result-headline {
    font-family: 'Merriweather', serif; font-size: 1.05rem;
    color: #1a1a1a; line-height: 1.8;
    border: 2px solid #ccc; border-radius: 6px;
    padding: 16px 22px; background: #fff; margin-bottom: 16px;
}
.rank {
    font-size: 1.9rem; font-weight: 700;
    color: #1a4a6e; vertical-align: baseline;
}
.diff-above {
    font-size: 0.88rem; font-weight: 600; border-radius: 3px;
    padding: 2px 8px; background: #eaf5ea; color: #1a6a1a;
}
.diff-below {
    font-size: 0.88rem; font-weight: 600; border-radius: 3px;
    padding: 2px 8px; background: #fdf0e8; color: #8a3a00;
}
.r-site { font-size: 0.88rem; color: #555; letter-spacing: 0.03em; }

/* ── Result banner (Odds) ── */
.result-banner {
    background: #eef5ff; border: 1.5px solid #b8d4f0;
    border-radius: 6px; padding: 1rem 1.4rem;
    margin: 0.8rem 0; display: flex;
    align-items: center; gap: 1rem; flex-wrap: wrap;
}
.rb-label {
    font-size: 0.72rem; color: #4a7aaa;
    letter-spacing: 0.08em; text-transform: uppercase;
    font-weight: 600;
}
.rb-value {
    font-family: 'Merriweather', serif;
    font-size: 1.2rem; font-weight: 700;
    color: #1a1a1a; line-height: 1.3;
}
.rb-pct {
    font-family: 'Merriweather', serif;
    font-size: 2.2rem; font-weight: 700;
    color: #1a4a6e; margin-left: auto;
}

/* ── Result box (Howwet) ── */
.result-box {
    background: #fff; border: 2px solid #2a7ab8;
    border-radius: 6px; padding: 20px 28px; margin-bottom: 16px;
}
.result-title { font-size: 1.05rem; color: #1a2332; margin-bottom: 8px; line-height: 1.6; }
.result-title .date-loc { color: #c17f24; font-weight: 700; }
.result-title .loc      { color: #1a6a1a; font-weight: 700; }
.fallow-label { font-size: 0.92rem; color: #555; margin-bottom: 14px; }
.paw-big  { font-family: 'Merriweather', serif; font-size: 2.4rem; font-weight: 700; color: #1a6a1a; }
.paw-unit { font-size: 1.0rem; color: #666; margin-left: 6px; }
.pawc-pct { font-family: 'Merriweather', serif; font-size: 1.4rem; font-weight: 700; color: #1a4a6e; margin-left: 20px; }

/* ── Status message ── */
.status-msg { font-size: 0.88rem; color: #666; font-style: italic; padding: 4px 0; }

/* ── Primary button ── */
.stButton > button[kind="primary"] {
    background: #1a4a6e !important; color: #fff !important;
    border: none !important; border-radius: 6px !important;
    padding: 12px 40px !important; font-size: 1.0rem !important;
    font-weight: 600 !important; font-family: 'Source Sans 3', sans-serif !important;
    width: 100% !important;
}
.stButton > button[kind="primary"]:hover { background: #0f3050 !important; }

/* ── Secondary button (Change) ── */
.stButton > button {
    border-radius: 6px !important;
    font-family: 'Source Sans 3', sans-serif !important;
    font-weight: 600 !important;
}

/* ── Inputs ── */
div[data-testid="stTextInput"] input,
div[data-testid="stNumberInput"] input {
    border: 1.5px solid #c0d4e8 !important;
    border-radius: 6px !important;
    font-family: 'Source Sans 3', sans-serif !important;
    font-size: 0.95rem !important;
    min-height: 42px !important;
}
div[data-testid="stTextInput"] input:focus,
div[data-testid="stNumberInput"] input:focus {
    border-color: #2a7ab8 !important;
    box-shadow: 0 0 0 2px rgba(42,122,184,0.15) !important;
}
div[data-testid="stSelectbox"] div[data-baseweb="select"] > div:first-child {
    border: 1.5px solid #c0d4e8 !important;
    border-radius: 6px !important;
    min-height: 42px !important;
}

/* ── Radio list (station picker) ── */
div[data-testid="stRadio"] > div { flex-direction: column !important; gap: 4px !important; }
div[data-testid="stRadio"] label {
    display: flex !important; align-items: center !important;
    padding: 8px 12px !important; border-radius: 6px !important;
    border: 1px solid #d0dcea !important; background: #f8fafd !important;
    font-size: 0.88rem !important; color: #1a2332 !important;
    cursor: pointer !important;
}
div[data-testid="stRadio"] label:hover {
    background: #e8f0fb !important; border-color: #2a7ab8 !important;
}

/* ── Tablet optimisation (≤900px) ── */
@media (max-width: 900px) {
    .page-title { font-size: 1.7rem !important; }
    .page-subtitle { font-size: 0.92rem !important; }
    .block-container { padding: 1rem 0.8rem 2rem !important; }
    .result-headline { font-size: 0.95rem; padding: 12px 16px; }
    .rank { font-size: 1.5rem; }
    .rb-pct { font-size: 1.7rem; }
    .paw-big { font-size: 1.9rem; }
    .pawc-pct { font-size: 1.1rem; }
    .chip { font-size: 0.75rem; padding: 2px 8px; }
    div[data-testid="stRadio"] label { padding: 10px 12px !important; font-size: 0.85rem !important; }
    div[data-testid="stTextInput"] input,
    div[data-testid="stNumberInput"] input { min-height: 46px !important; font-size: 1rem !important; }
}

/* ── Phone (≤600px) ── */
@media (max-width: 600px) {
    .page-title { font-size: 1.4rem !important; }
    .result-headline { font-size: 0.88rem; padding: 10px 12px; }
    .rank { font-size: 1.3rem; }
    .diff-above, .diff-below { display: block; margin-top: 4px; }
    .rb-pct { font-size: 1.5rem; margin-left: 0; width: 100%; }
    .paw-big { font-size: 1.6rem; }
    .result-box { padding: 14px 16px; }
}
</style>
""", unsafe_allow_html=True)
