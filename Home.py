"""
Home.py — Landing page for the rainfall-tools suite
"""

import streamlit as st

st.set_page_config(
    page_title="Risk Status",
    page_icon="🌧️",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Source+Sans+3:wght@300;400;600;700&display=swap');
html, body, [class*="css"] { font-family: 'Source Sans 3', sans-serif; }

/* Rename sidebar nav items via CSS */
[data-testid="stSidebarNav"] a[href*="1_Season"] span { visibility: hidden; }
[data-testid="stSidebarNav"] a[href*="1_Season"]::before { content: "Season?"; visibility: visible; }
[data-testid="stSidebarNav"] a[href*="2_Odds"] span { visibility: hidden; }
[data-testid="stSidebarNav"] a[href*="2_Odds"]::before { content: "Odds?"; visibility: visible; }
[data-testid="stSidebarNav"] a[href*="3_Howwet"] span { visibility: hidden; }
[data-testid="stSidebarNav"] a[href*="3_Howwet"]::before { content: "Water stored?"; visibility: visible; }

.tool-card {
    border: 1.5px solid #d0dcea;
    border-radius: 10px;
    padding: 1.4rem 1.6rem;
    background: #fff;
    margin-bottom: 0.5rem;
    box-shadow: 0 1px 4px rgba(11,31,58,0.05);
    cursor: pointer;
    transition: border-color 0.15s, box-shadow 0.15s;
}
.tool-card:hover {
    border-color: #2979c4;
    box-shadow: 0 2px 10px rgba(41,121,196,0.15);
}
.tool-title { font-size: 1.3rem; font-weight: 700; color: #1a4a6e; margin-bottom: 0.3rem; }
.tool-desc  { font-size: 1rem; color: #444; line-height: 1.6; }

/* Hide the page_link button text — card itself is the clickable area */
.tool-link { margin-top: 0 !important; }
.tool-link a {
    display: block !important;
    position: absolute !important;
    inset: 0 !important;
    opacity: 0 !important;
}
.card-wrap {
    position: relative;
}
</style>
""", unsafe_allow_html=True)

st.markdown("# 🌧️ Risk Status")
st.markdown(
    "*A suite of Australian rainfall and soil water analysis tools "
    "powered by [SILO](https://www.longpaddock.qld.gov.au/silo/) climate data.*"
)
st.divider()

col1, col2, col3 = st.columns(3)

with col1:
    with st.container():
        st.markdown("""
        <div class="tool-card">
            <div class="tool-title">📈 How's the season?</div>
            <div class="tool-desc">
                Compare this season's cumulative rainfall against all years on record.
                See where you sit as a percentile and how far above or below the median you are.
            </div>
        </div>
        """, unsafe_allow_html=True)
        st.page_link("pages/1_Season.py", label="Open", icon="📈")

with col2:
    with st.container():
        st.markdown("""
        <div class="tool-card">
            <div class="tool-title">🎲 What are the odds?</div>
            <div class="tool-desc">
                How often has a rainfall threshold been exceeded within a given
                number of days, during a chosen season?
                Year-by-year frequency analysis with downloadable results.
            </div>
        </div>
        """, unsafe_allow_html=True)
        st.page_link("pages/2_Odds.py", label="Open", icon="🎲")

with col3:
    with st.container():
        st.markdown("""
        <div class="tool-card">
            <div class="tool-title">💧 How much rain stored?</div>
            <div class="tool-desc">
                Run the PERFECT/HowLeaky water balance model for any location in Australia.
                Track plant available soil water over a fallow period against historical years.
            </div>
        </div>
        """, unsafe_allow_html=True)
        st.page_link("pages/3_Howwet.py", label="Open", icon="💧")

st.divider()
st.caption(
    "Data: Queensland Government SILO climate database  ·  "
    "Water balance model: PERFECT and HowLeaky (Littleboy et al. 1992)  ·  "
    "Interface: CliMate (Freebairn and McClymont 2025)"
)
