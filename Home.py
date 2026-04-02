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
.tool-card {
    border: 1.5px solid #d0dcea;
    border-radius: 10px;
    padding: 1.4rem 1.6rem;
    background: #fff;
    margin-bottom: 1rem;
    box-shadow: 0 1px 4px rgba(11,31,58,0.05);
}
.tool-title { font-size: 1.3rem; font-weight: 700; color: #1a4a6e; margin-bottom: 0.3rem; }
.tool-desc  { font-size: 1rem; color: #444; line-height: 1.6; }
.data-badge {
    display: inline-block;
    font-size: 0.78rem; font-weight: 600;
    background: #eef5ff; color: #2979c4;
    border: 1px solid #b8d4f0;
    border-radius: 4px; padding: 2px 8px;
    margin-top: 0.6rem;
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
    st.markdown("""
    <div class="tool-card">
        <div class="tool-title">📈 How's the season?</div>
        <div class="tool-desc">
            Compare this season's cumulative rainfall against all years on record.
            See where you sit as a percentile and how far above or below the median you are.
        </div>
        <span class="data-badge">SILO Patched Point</span>
    </div>
    """, unsafe_allow_html=True)
    st.page_link("pages/1_Season.py", label="Open →", icon="📈")

with col2:
    st.markdown("""
    <div class="tool-card">
        <div class="tool-title">🎲 What are the odds?</div>
        <div class="tool-desc">
            How often has a rainfall threshold been exceeded within a given
            number of days, during a chosen season?
            Year-by-year frequency analysis with downloadable results.
        </div>
        <span class="data-badge">SILO Patched Point</span>
    </div>
    """, unsafe_allow_html=True)
    st.page_link("pages/2_Odds.py", label="Open →", icon="🎲")

with col3:
    st.markdown("""
    <div class="tool-card">
        <div class="tool-title">💧 How much rain stored?</div>
        <div class="tool-desc">
            Run the PERFECT/HowLeaky water balance model for any location in Australia.
            Track plant available soil water over a fallow period against historical years.
        </div>
        <span class="data-badge">SILO Patched Point</span>
    </div>
    """, unsafe_allow_html=True)
    st.page_link("pages/3_Howwet.py", label="Open →", icon="💧")

st.divider()
st.caption(
    "Data: Queensland Government SILO climate database · "
    "Water balance: PERFECT / HowLeaky model (Littleboy et al. 1992)"
)
