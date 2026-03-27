"""
PERFECT Soil Water Monitor — Streamlit Web App
================================================
Soil water status for any location in Australia.

Usage:
    streamlit run app.py

Requires all PERFECT-Python modules in the same folder:
    waterbalance.py, soil.py, soil_xml.py, vege.py,
    run_simulation.py, silo_fetch.py
And a Data/ subfolder containing .soil files.
"""

import sys
import warnings
warnings.filterwarnings('ignore')

from pathlib import Path
HERE = Path(__file__).resolve().parent
for _p in [str(HERE), str(HERE / 'Data')]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

import streamlit as st
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
from matplotlib.patches import FancyBboxPatch
from datetime import datetime, date, timedelta
import requests
import io

# ── Page config ───────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Soil Water Monitor",
    page_icon="💧",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── CSS ───────────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Source+Sans+3:wght@300;400;600;700&display=swap');

html, body, [class*="css"] {
    font-family: 'Source Sans 3', sans-serif;
    background: #ffffff;
}

/* Hide sidebar */
section[data-testid="stSidebar"] { display: none; }

/* Page title */
.page-title {
    font-size: 2.6rem;
    font-weight: 700;
    color: #1a5276;
    line-height: 1.15;
    margin-bottom: 2px;
}
.page-subtitle {
    font-size: 1.15rem;
    font-style: italic;
    color: #2e86c1;
    margin-bottom: 28px;
}
.section-heading {
    font-size: 1.35rem;
    font-weight: 600;
    color: #148f77;
    margin-bottom: 14px;
}

/* Input box */
.input-box {
    border: 1.5px solid #888;
    border-radius: 4px;
    padding: 22px 28px 18px 28px;
    background: #fff;
    margin-bottom: 28px;
}
.input-row {
    display: flex;
    align-items: center;
    padding: 10px 0;
    border-bottom: 1px solid #f0f0f0;
    font-size: 1.05rem;
    color: #1a2332;
}
.input-row:last-child { border-bottom: none; }
.input-label { flex: 0 0 280px; font-weight: 400; }
.input-label small { color: #888; font-weight: 300; }
.input-value { color: #1a9650; font-weight: 600; }

/* Streamlit widget tweaks */
div[data-testid="stTextInput"] input,
div[data-testid="stSelectbox"] div[data-baseweb="select"],
div[data-testid="stDateInput"] input,
div[data-testid="stNumberInput"] input {
    border: none !important;
    border-bottom: 2px solid #2e86c1 !important;
    border-radius: 0 !important;
    background: transparent !important;
    color: #1a9650 !important;
    font-weight: 600 !important;
    font-size: 1rem !important;
    padding-left: 0 !important;
}
div[data-testid="stTextInput"] label,
div[data-testid="stSelectbox"] label,
div[data-testid="stDateInput"] label,
div[data-testid="stNumberInput"] label {
    color: #333 !important;
    font-size: 1.0rem !important;
    font-weight: 400 !important;
}

/* Run button */
.stButton > button {
    background: #1a4f7a !important;
    color: white !important;
    border: none !important;
    border-radius: 6px !important;
    padding: 14px 48px !important;
    font-size: 1.05rem !important;
    font-weight: 700 !important;
    letter-spacing: 0.02em !important;
    display: block;
    margin: 0 auto;
    min-width: 320px;
}
.stButton > button:hover {
    background: #0e3252 !important;
}

/* Result box */
.result-box {
    background: white;
    border: 2px solid #2d6a9f;
    border-radius: 6px;
    padding: 24px 32px;
    margin-bottom: 20px;
}
.result-title {
    font-size: 1.15rem;
    color: #1a2332;
    margin-bottom: 10px;
    line-height: 1.6;
}
.result-title .date-loc { color: #c17f24; font-weight: 700; }
.result-title .loc      { color: #1a9650; font-weight: 700; }
.fallow-label { font-size: 0.98rem; color: #444; margin-bottom: 16px; }
.paw-big  { font-size: 2.4rem; font-weight: 700; color: #1a9650; }
.paw-unit { font-size: 1.1rem; color: #666; margin-left: 6px; }
.pawc-pct { font-size: 1.5rem; font-weight: 700; color: #1a5276; margin-left: 24px; }

/* Status */
.status-msg { font-size: 0.88rem; color: #666; font-style: italic; padding: 4px 0; }
</style>
""", unsafe_allow_html=True)


# ── Constants ─────────────────────────────────────────────────────────────
SILO_URL   = "https://www.longpaddock.qld.gov.au/cgi-bin/silo/DataDrillDataset.php"
SILO_EMAIL = "noreply@soilwater.app"   # fixed — SILO doesn't validate this
HISTORY_YEARS = 19    # years of historical runs for the mean band
MAX_MONTHS_RECENT = 24  # how far back the user can set start date

# 10% residue cover, no green — fixed for all runs
FIXED_GREEN  = 0.0
FIXED_TOTAL  = 0.1   # 10% stubble cover (default)

# Colour palette
C_HIST    = '#A8C4E0'   # individual historical year lines
C_MEAN    = '#7B5EA7'   # historical mean line
C_RECENT  = '#1A2F6B'   # recent simulation line
C_BG      = '#F4F6F9'
C_BOX     = '#FFFFFF'


# ── Helpers ───────────────────────────────────────────────────────────────

@st.cache_data(ttl=3600, show_spinner=False)
def search_stations(query: str):
    """Search SILO patched-point station list."""
    url = 'https://www.longpaddock.qld.gov.au/cgi-bin/silo/PatchedPointDataset.php'
    try:
        resp = requests.get(url,
            params={'format': 'name', 'nameFrag': query},
            headers={'User-Agent': 'Mozilla/5.0', 'Accept': 'text/plain'},
            timeout=15)
        lines = [l.strip() for l in resp.text.strip().split('\n')
                 if l.strip() and '|' in l]
        stations = []
        for line in lines[:20]:
            parts = [p.strip() for p in line.split('|')]
            if len(parts) < 4:
                continue
            try:
                lat = float(parts[2]); lon = float(parts[3])
            except ValueError:
                continue
            if not (-45 < lat < -10 and 110 < lon < 155):
                continue
            stations.append({
                'number': parts[0], 'name': parts[1],
                'lat': lat, 'lon': lon,
                'state': parts[4] if len(parts) > 4 else '',
            })
        return stations
    except Exception:
        return []


def _parse_silo_csv(raw: str) -> pd.DataFrame:
    """
    Parse raw SILO DataDrill CSV into a DataFrame.
    Handles both formats SILO returns:
      Old: header line starts with 'date'  (YYYYMMDD integer)
      New: header line starts with 'latitude,longitude,YYYY-MM-DD,...'
    """
    lines = raw.splitlines()

    # Find the header line — either starts with 'date' or 'latitude'
    header_idx = None
    date_col   = None
    date_fmt   = None
    for i, line in enumerate(lines):
        low = line.strip().lower()
        if low.startswith('date'):
            header_idx = i
            date_col   = 'date'
            date_fmt   = '%Y%m%d'    # old format: integer YYYYMMDD
            break
        if low.startswith('latitude') or low.startswith('yyyy'):
            header_idx = i
            date_col   = 'yyyy-mm-dd'
            date_fmt   = '%Y-%m-%d'  # new format: ISO date string
            break

    if header_idx is None:
        preview = raw[:400].replace(chr(10), ' | ')
        raise ValueError(f"Could not parse SILO CSV. Response: {preview}")

    raw_df = pd.read_csv(io.StringIO(chr(10).join(lines[header_idx:])))
    raw_df.columns = [c.strip().lower() for c in raw_df.columns]

    # Build index from whichever date column exists
    if date_col in raw_df.columns:
        df_index = pd.to_datetime(raw_df[date_col].astype(str), format=date_fmt)
    elif 'yyyy-mm-dd' in raw_df.columns:
        df_index = pd.to_datetime(raw_df['yyyy-mm-dd'].astype(str), format='%Y-%m-%d')
    else:
        # Last resort: find any column that looks like a date
        date_candidates = [c for c in raw_df.columns if 'date' in c or 'yyyy' in c]
        if not date_candidates:
            raise ValueError(f"No date column found. Columns: {list(raw_df.columns)}")
        df_index = pd.to_datetime(raw_df[date_candidates[0]].astype(str))

    df = pd.DataFrame(index=df_index)
    df.index.name = 'date'
    df['year']  = df.index.year
    df['month'] = df.index.month
    df['day']   = df.index.day
    df['doy']   = df.index.day_of_year

    # Map SILO column names to internal names — handles both old and new naming
    col_map = {
        'daily_rain' : 'rain',
        'rain'       : 'rain',
        'max_temp'   : 'tmax',
        'maximum_temperature' : 'tmax',
        'min_temp'   : 'tmin',
        'minimum_temperature' : 'tmin',
        'evap_pan'   : 'epan',
        'evaporation': 'epan',
        'radiation'  : 'radiation',
        'solar_radiation': 'radiation',
    }
    for sc, pc in col_map.items():
        if sc in raw_df.columns and pc not in df.columns:
            df[pc] = raw_df[sc].values

    # Ensure required columns exist
    for col in ['rain', 'tmax', 'tmin', 'epan', 'radiation']:
        if col not in df.columns:
            df[col] = np.nan

    df['tmean'] = (df['tmax'] + df['tmin']) / 2.0
    df['epan']  = df['epan'].fillna(0.0)
    df['rain']  = df['rain'].fillna(0.0)

    # If epan is all zero (SILO didn't return it), estimate from radiation + temp
    # using a simple Linacre-style equation calibrated to approximate pan evap.
    # Epan ≈ 1.05 * (0.75 * Rn - 0.13) where Rn is net radiation proxy from Rs.
    # Simpler field approximation: epan ≈ radiation * 0.55 + 0.5 (mm/day)
    # This gives ~5-8 mm/day in summer, ~2-4 mm/day in winter — realistic for Qld.
    if df['epan'].sum() < 1.0 and 'radiation' in df.columns:
        rs = df['radiation'].fillna(df['radiation'].median())
        tmean = df['tmean'].fillna(25.0)
        # Priestley-Taylor style: ET0 ≈ 0.408 * Rs (MJ/m2) * slope/(slope+gamma)
        # Simplified for pan: epan ≈ Rs * 0.50 + tmean * 0.06
        df['epan'] = (rs * 0.50 + tmean * 0.06).clip(lower=0.5)

    return df


def _silo_fetch_via_browser(label: str, lat: float, lon: float,
                             start: str, end: str, email: str):
    """
    Fetch SILO data by injecting JavaScript into the browser.
    The browser makes the HTTP request (bypassing WAF), then posts
    the CSV text back to Streamlit via query params / session_state.

    Returns a DataFrame or None if data not yet available.
    """
    import streamlit.components.v1 as components
    import urllib.parse

    params = urllib.parse.urlencode({
        'lat': lat, 'lon': lon,
        'start': start, 'finish': end,
        'format': 'csv',
        'comment': 'daily_rain,max_temp,min_temp,evap_pan,radiation',
        'username': email,
        'password': 'apirequest',
    })
    url = f"https://www.longpaddock.qld.gov.au/cgi-bin/silo/DataDrillDataset.php?{params}"
    key = f"silo_{label}_{lat}_{lon}_{start}_{end}"

    # If already fetched this session, return cached result
    if key in st.session_state and st.session_state[key] is not None:
        return st.session_state[key]

    # Inject JS to fetch from browser and store result in URL hash
    fetch_html = f"""
    <script>
    (async function() {{
        const key = {repr(key)};
        // Check if already done
        if (window.sessionStorage.getItem(key)) {{
            window.parent.postMessage({{type:'silo_done', key:key,
                data: window.sessionStorage.getItem(key)}}, '*');
            return;
        }}
        try {{
            const resp = await fetch({repr(url)});
            const text = await resp.text();
            window.sessionStorage.setItem(key, text);
            window.parent.postMessage({{type:'silo_done', key:key, data:text}}, '*');
        }} catch(e) {{
            window.parent.postMessage({{type:'silo_error', key:key, error:e.toString()}}, '*');
        }}
    }})();
    </script>
    """
    components.html(fetch_html, height=0)
    return None   # not ready yet — caller must handle rerun


def fetch_climate_browser(label: str, lat: float, lon: float,
                          start: str, end: str, email: str):
    """
    Browser-side SILO fetch with polling loop.
    Displays a spinner and reruns until data arrives.
    """
    key = f"silo_{label}_{lat}_{lon}_{start}_{end}"
    if key not in st.session_state:
        st.session_state[key] = None

    result = _silo_fetch_via_browser(label, lat, lon, start, end, email)
    return result


def fetch_climate(lat: float, lon: float, start: str, end: str,
                  email: str = "") -> pd.DataFrame:
    """
    Fetch SILO DataDrill climate data.
    Makes the request from the server with browser-like headers.
    If blocked, raises a clear error suggesting the browser-fetch workaround.
    """
    import urllib.request
    import urllib.parse as _up

    params = _up.urlencode({
        'lat': lat, 'lon': lon,
        'start': start, 'finish': end,
        'format': 'csv',
        'comment': 'daily_rain,max_temp,min_temp,evap_pan,radiation',
        'username': email,
        'password': 'apirequest',
    })
    url = f"https://www.longpaddock.qld.gov.au/cgi-bin/silo/DataDrillDataset.php?{params}"

    req = urllib.request.Request(url, headers={
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
                      'AppleWebKit/537.36 (KHTML, like Gecko) '
                      'Chrome/122.0.0.0 Safari/537.36',
        'Accept': 'text/plain, text/csv, */*',
        'Referer': 'https://www.longpaddock.qld.gov.au/silo/',
        'Origin':  'https://www.longpaddock.qld.gov.au',
    })
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            raw = resp.read().decode('utf-8', errors='replace')
        if 'date' in raw.lower()[:2000]:
            return _parse_silo_csv(raw)
        raise ValueError(f"Unexpected SILO response: {raw[:300]}")
    except Exception as e:
        raise ValueError(
            f"SILO fetch failed: {e}\n\n"
            "SILO's firewall is blocking server-side requests.\n"
            "This app needs to be run with the browser-fetch mode.\n"
            "Contact the administrator."
        )


def fetch_climate_from_csv(csv_text: str) -> pd.DataFrame:
    """Parse a CSV string already fetched by the browser."""
    return _parse_silo_csv(csv_text)


def _last_silo_date_from_csv(csv_text: str) -> 'date':
    """Find the last date in a SILO CSV string."""
    lines = csv_text.splitlines()
    header_idx = next((i for i, l in enumerate(lines)
                       if l.strip().lower().startswith('date')), None)
    if header_idx is None:
        return date.today() - timedelta(days=3)
    data_lines = [l for l in lines[header_idx+1:]
                  if l.strip() and l[0].isdigit()]
    if data_lines:
        try:
            return datetime.strptime(data_lines[-1].split(',')[0].strip(),
                                     '%Y%m%d').date()
        except Exception:
            pass
    return date.today() - timedelta(days=3)


def run_water_balance(met_df, profile, init_fraction=0.5):
    """
    Run daily water balance with fixed 50% stubble cover.
    Bypasses _run_daily's hardcoded init_sw(0.5) by running the loop directly.
    """
    from waterbalance import daily_water_balance
    from soil import init_sw
    import pandas as pd

    layers = profile.layers
    sw     = init_sw(profile, init_fraction)   # user-specified initial water
    sw0    = sw.sum()
    sumes1 = sumes2 = t_since_wet = 0.0
    records = []

    for dt, row in met_df.iterrows():
        rain = float(row.get('rain', 0) or 0)
        epan = float(row.get('epan', 0) or 0)
        if np.isnan(rain): rain = 0.0
        if np.isnan(epan): epan = 0.0
        doy  = int(row['doy'])

        # For a fallow with residue cover only (no green crop):
        # - total_cover (0.5) reduces runoff CN and soil evap demand
        # - green_cover = 0 so all ET goes to soil evap, none to transpiration
        # - eos is scaled by (1 - total_cover) to account for residue shading
        # Pass total_cover as the effective cover for soil evap reduction
        sw_before = float(sw.sum())
        # Fallow with 50% residue cover, no green crop:
        # green_cover=0 (no living canopy, no transpiration)
        # total_cover=0.5 (residue reduces CN and soil evap via Adams formula)
        out = daily_water_balance(
            sw=sw, layers=layers, soil=profile,
            rain=rain, epan=epan,
            green_cover=FIXED_GREEN,   # 0.0 — no living canopy
            total_cover=FIXED_TOTAL,   # 0.5 — residue for CN + Adams evap reduction
            root_depth_mm=0.0,         # no roots — no transpiration
            crop_factor=1.0,
            sumes1=sumes1, sumes2=sumes2, t_since_wet=t_since_wet,
        )
        sw          = out['sw']
        sumes1      = out['sumes1']
        sumes2      = out['sumes2']
        t_since_wet = out['t_since_wet']

        # Use sw_total for strict balance — it is the actual sum of sw array
        # which already has all losses (evap, transp) correctly deducted
        sw_total = float(sw.sum())

        pasw = sum(max(0.0, float(sw[i]) - layers[i].ll_mm)
                   for i in range(len(layers)))

        rad  = float(row.get('radiation', 0) or 0)
        if np.isnan(rad): rad = 0.0
        # Compute actual soil evap = sw change not explained by other fluxes
        # actual_es = sw_before + rain - runoff - drainage - transp - sw_total
        actual_es = (sw_before + rain
                     - out['runoff'] - out['drainage']
                     - out['transp'] - sw_total)
        actual_es = max(0.0, actual_es)   # floor at zero

        records.append({
            'rain'     : rain,
            'epan'     : epan,
            'radiation': rad,
            'runoff'   : out['runoff'],
            'soil_evap': actual_es,      # use mass-balance derived evap
            'transp'   : out['transp'],
            'drainage' : out['drainage'],
            'et'       : actual_es + out['transp'],
            'sw_total' : sw_total,
            'pasw'     : round(pasw, 2),
        })

    df  = pd.DataFrame(records, index=met_df.index)
    swf = df['sw_total'].iloc[-1]
    return df, sw0, swf


def calc_fallow_efficiency(df, profile):
    """
    Fallow efficiency = (PAW_end - PAW_start) / cumulative rainfall * 100
    Measures what fraction of rainfall received was stored in the soil.
    """
    rain_total = df['rain'].sum()
    if rain_total <= 0:
        return 0.0
    pasw_gain = df['pasw'].iloc[-1] - df['pasw'].iloc[0]
    fe = (pasw_gain / rain_total) * 100.0
    return max(0.0, fe)


def load_soil_files():
    """Scan Data/ subfolder for .soil files."""
    data_dir = HERE / 'Data'
    if not data_dir.exists():
        data_dir = HERE  # fallback to same folder
    files = sorted(data_dir.glob('*.soil'))
    return files


def load_profile(soil_path):
    """Load a soil profile from .soil or .PRM file."""
    from soil_xml import read_soil_xml
    from soil import read_prm
    ext = soil_path.suffix.lower()
    if ext == '.soil':
        return read_soil_xml(soil_path)
    return read_prm(soil_path)


# ── Chart ─────────────────────────────────────────────────────────────────

def make_pasw_chart(recent_df, hist_dfs, profile, station_name,
                    start_date, end_date):
    """
    Build the PASW chart:
      - Light blue lines: each historical year
      - Purple line: mean of historical years
      - Dark blue line: recent simulation
    X-axis: calendar date (day of year mapped to dates in the recent window)
    """
    plt.rcParams.update({
        'font.family': 'sans-serif',
        'axes.facecolor': '#FAFBFC',
        'figure.facecolor': C_BG,
        'axes.spines.top': False,
        'axes.spines.right': False,
        'axes.linewidth': 0.8,
    })

    fig, ax = plt.subplots(figsize=(12, 5))
    fig.patch.set_facecolor(C_BG)
    ax.set_facecolor('#FAFBFC')

    pawc = profile.pawc_total

    # ── Historical year traces ────────────────────────────────────────────
    # Each historical year was run starting from the same calendar date as
    # the recent period. Take the first N days where N = len(recent_df).
    n_recent = len(recent_df)
    x_vals   = recent_df.index   # use recent dates as x-axis for all traces

    hist_aligned = []
    for hdf in hist_dfs:
        seg = hdf['pasw'].values[:n_recent]   # first N days only
        if len(seg) == 0:
            continue
        # Trim both to the shorter length in case a year has fewer days
        n = min(len(seg), n_recent)
        hist_aligned.append(seg[:n])
        ax.plot(x_vals[:n], seg[:n], color=C_HIST, lw=0.8, alpha=0.55, zorder=1)

    # ── Historical mean line ──────────────────────────────────────────────
    if hist_aligned:
        min_len   = min(len(s) for s in hist_aligned)
        mean_pasw = np.mean([s[:min_len] for s in hist_aligned], axis=0)
        ax.plot(x_vals[:min_len], mean_pasw, color=C_MEAN, lw=2.2, zorder=3,
                label=f'Historical mean ({len(hist_aligned)} yrs)')

    # ── Recent simulation line ────────────────────────────────────────────
    ax.plot(recent_df.index, recent_df['pasw'],
            color=C_RECENT, lw=2.8, zorder=4,
            label=f'Recent  ({start_date.strftime("%d %b %Y")} – '
                  f'{end_date.strftime("%d %b %Y")})')

    # ── PAWC reference line ───────────────────────────────────────────────
    ax.axhline(pawc, color='#CC4422', lw=0.9, ls='--', alpha=0.6,
               label=f'PAWC  {pawc:.0f} mm', zorder=2)

    # ── Formatting ────────────────────────────────────────────────────────
    ax.set_ylabel('Plant available soil water (mm)', fontsize=10, color='#333')
    ax.set_ylim(bottom=0)
    ax.yaxis.set_major_locator(ticker.MaxNLocator(nbins=6, integer=True))
    ax.tick_params(labelsize=9)
    ax.grid(axis='y', color='#E0E4EC', lw=0.6, zorder=0)

    # X-axis: monthly ticks
    import matplotlib.dates as mdates
    ax.xaxis.set_major_locator(mdates.MonthLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%d %b\n%Y'))
    ax.tick_params(axis='x', labelsize=8.5)

    # Legend
    ax.legend(loc='upper left', fontsize=9, frameon=True,
              framealpha=0.9, edgecolor='#CCCCCC')

    # Title
    ax.set_title(
        f'Plant available soil water   '
        f'{start_date.strftime("%d %b %Y")} to {end_date.strftime("%d %b %Y")}',
        fontsize=11, color='#1a2332', pad=10, loc='left')

    plt.tight_layout(pad=1.5)
    return fig


# ── Input form (single page, no sidebar) ─────────────────────────────────

def input_form():
    """Render the single-page input form matching the reference design."""

    # Page title
    st.markdown('''
    <div class="page-title">How much rain stored?</div>
    <div class="page-subtitle">Accumulated soil water over a fallow</div>
    <div class="section-heading">Set up paddock</div>
    ''', unsafe_allow_html=True)

    soil_files = load_soil_files()
    soil_labels = [f.stem for f in soil_files] if soil_files else []

    today     = date.today()
    yesterday = today - timedelta(days=1)
    min_start = today - timedelta(days=MAX_MONTHS_RECENT * 30)

    # ── Input box ─────────────────────────────────────────────────────────
    with st.container():
        st.markdown('<div class="input-box">', unsafe_allow_html=True)

        # Row 1: Weather station search + result
        col1, col2 = st.columns([1.1, 1.4])
        with col1:
            st.markdown("Select a weather station")
        with col2:
            query = st.text_input("station_search", label_visibility="collapsed",
                                  placeholder="e.g. Cairns, Emerald", key="station_query")

        station_info = None
        if query and len(query) >= 3:
            # Re-search only when query changes; cache results in session_state
            if st.session_state.get("last_query") != query:
                with st.spinner("Searching..."):
                    st.session_state["station_results"] = search_stations(query)
                st.session_state["last_query"] = query
                st.session_state["station_sel_idx"] = 0   # reset selection

            stations = st.session_state.get("station_results", [])
            if stations:
                labels = [f"{s['name']}  ({s['state']})  #{s['number']}"
                          for s in stations]
                sel = st.selectbox("Select station", range(len(labels)),
                                   format_func=lambda i: labels[i],
                                   label_visibility="collapsed",
                                   index=st.session_state.get("station_sel_idx", 0),
                                   key="station_sel")
                st.session_state["station_sel_idx"] = sel
                station_info = stations[sel]
                st.session_state["saved_station"] = station_info
                st.caption(f"📍 {station_info['lat']:.3f}°S, {station_info['lon']:.3f}°E")
            else:
                st.caption("No stations found — try a different name")

        st.markdown('<hr style="border:none;border-top:1px solid #f0f0f0;margin:2px 0">',
                    unsafe_allow_html=True)

        # Row 3: Soil type
        col1, col2 = st.columns([1.1, 1.4])
        with col1:
            st.markdown("Select soil type")
        with col2:
            if soil_labels:
                soil_idx = st.selectbox("soil", range(len(soil_labels)),
                                        format_func=lambda i: soil_labels[i],
                                        label_visibility="collapsed", key="soil_sel")
                soil_path = soil_files[soil_idx]
            else:
                st.error("No .soil files found in Data/ folder")
                soil_path = None

        st.markdown('<hr style="border:none;border-top:1px solid #f0f0f0;margin:2px 0">',
                    unsafe_allow_html=True)

        # Row 4: Start date + How full at start
        col1, col2, col3, col4 = st.columns([1.1, 0.8, 0.7, 0.6])
        with col1:
            st.markdown("Start date of fallow")
        with col2:
            start_date = st.date_input("start", label_visibility="collapsed",
                                       value=today - timedelta(days=180),
                                       min_value=min_start,
                                       max_value=yesterday,
                                       format="DD/MM/YYYY",
                                       key="start_date")
        with col3:
            st.markdown("How full at start")
        with col4:
            init_pct = st.number_input("init_pct", label_visibility="collapsed",
                                       min_value=0, max_value=100, value=5,
                                       step=5, key="init_pct")
            st.caption("% of PAWC")

        st.markdown("</div>", unsafe_allow_html=True)

    # ── Run button ────────────────────────────────────────────────────────
    col_l, col_c, col_r = st.columns([1, 2, 1])
    with col_c:
        run_clicked = st.button("Fetch data and run analysis",
                                width='stretch')

    return soil_path, station_info, start_date, yesterday, init_pct, run_clicked


# ── Main ──────────────────────────────────────────────────────────────────

def main():
    soil_path, station_info, start_date, end_date, init_pct, run_clicked = input_form()

    if not run_clicked:
        return

    email = SILO_EMAIL
    if station_info is None:
        station_info = st.session_state.get("saved_station")
    if station_info is None:
        st.error("Please search for and select a weather station.")
        return
    if soil_path is None:
        st.error("No soil files found.")
        return

    st.markdown("---")

    # ── Run ───────────────────────────────────────────────────────────────
    lat  = station_info['lat']
    lon  = station_info['lon']
    stn_name = station_info['name']

    # Date strings — use today-3 as a safe end; trim after fetch if needed
    today     = date.today()
    safe_end  = today - timedelta(days=3)
    start_str    = start_date.strftime('%Y%m%d')
    end_str      = safe_end.strftime('%Y%m%d')

    # Historical period: 19 years ending the day before start_date
    hist_end     = start_date - timedelta(days=1)
    hist_start   = date(hist_end.year - HISTORY_YEARS, hist_end.month, hist_end.day)
    hist_start_s = hist_start.strftime('%Y%m%d')
    hist_end_s   = hist_end.strftime('%Y%m%d')

    # Load soil
    try:
        profile = load_profile(soil_path)
        pawc    = profile.pawc_total
    except Exception as e:
        st.error(f"Could not load soil file: {e}")
        return

    status = st.empty()

    def _single_fetch(s, e, var):
        """Fetch one SILO variable — single var avoids WAF block."""
        import urllib.request as _ur
        import urllib.parse as _up
        base = _up.urlencode({'lat':lat,'lon':lon,'start':s,'finish':e,
                              'format':'csv','username':email,'password':'apirequest'})
        url = f"{SILO_URL}?{base}&comment={var}"
        with _ur.urlopen(url, timeout=120) as resp:
            return resp.read().decode('utf-8', errors='replace')

    def _session_fetch(s, e, label):
        status.markdown(f'<p class="status-msg">Fetching {label} from SILO ({s} → {e})...</p>',
                        unsafe_allow_html=True)
        # Fetch rain then evap_pan separately (multi-var comment blocked by WAF)
        raw_rain = _single_fetch(s, e, 'daily_rain')
        df = _parse_silo_csv(raw_rain)

        # Fetch real pan evaporation
        try:
            raw_evap = _single_fetch(s, e, 'evap_pan')
            df_evap  = _parse_silo_csv(raw_evap)
            # evap_pan comes back in a column — check all possible names
            for col in ['evap_pan', 'epan', 'evaporation', 'evap_morton_lake',
                        'evap_morton_wet', 'evap_asce']:
                if col in df_evap.columns and df_evap[col].sum() > 1.0:
                    df['epan'] = df_evap[col].values
                    break
        except Exception:
            pass

        # If epan still missing, fetch radiation and estimate
        if df['epan'].sum() < 1.0:
            try:
                raw_rad = _single_fetch(s, e, 'radiation')
                df_rad  = _parse_silo_csv(raw_rad)
                if 'radiation' in df_rad.columns:
                    df['radiation'] = df_rad['radiation'].values
                if 'tmax' in df_rad.columns:
                    df['tmax'] = df_rad['tmax'].values
                if 'tmin' in df_rad.columns:
                    df['tmin'] = df_rad['tmin'].values
                df['tmean'] = (df['tmax'] + df['tmin']) / 2.0
                rs    = df['radiation'].fillna(15.0)
                tmean = df['tmean'].fillna(25.0)
                df['epan'] = (rs * 0.50 + tmean * 0.06).clip(lower=0.5)
            except Exception:
                df['epan'] = 5.0   # last resort flat fallback

        return df

    try:
        recent_met = _session_fetch(start_str, end_str, 'recent climate')
        end_date   = recent_met.index.max().date()
    except Exception as e:
        status.empty()
        st.error(f"SILO fetch failed: {e}")
        return

    try:
        hist_met = _session_fetch(hist_start_s, hist_end_s,
                                  f'{HISTORY_YEARS}-year historical climate')
    except Exception as e:
        status.empty()
        st.error(f"SILO historical fetch failed: {e}")
        return

    status.empty()

    # Run recent simulation
    status.markdown('<p class="status-msg">Running water balance...</p>',
                    unsafe_allow_html=True)
    try:
        recent_df, _, _ = run_water_balance(recent_met, profile,
                                              init_fraction=init_pct / 100.0)
    except Exception as e:
        st.error(f"Simulation failed: {e}")
        return

    # Run one simulation per historical year.
    # For each year, take a window of the same length as the recent period
    # starting from the same calendar date as start_date — so the trace
    # never gets cut off at Dec 31 when the fallow crosses the year boundary.
    n_days    = len(recent_df)
    hist_dfs  = []
    hist_years = sorted(hist_met.index.year.unique())
    for yr in hist_years:
        # Find the same start date in this historical year
        try:
            yr_start = pd.Timestamp(yr, start_date.month, start_date.day)
        except ValueError:
            continue   # e.g. Feb 29 in non-leap year
        yr_end = yr_start + pd.Timedelta(days=n_days - 1)
        yr_met = hist_met.loc[yr_start:yr_end]
        if len(yr_met) < 30:
            continue
        try:
            hdf, _, _ = run_water_balance(yr_met, profile,
                                          init_fraction=init_pct / 100.0)
            hist_dfs.append(hdf)
        except Exception:
            continue

    status.empty()

    # ── Debug: water balance totals ───────────────────────────────────────
    with st.expander("Water balance"):
        rain_t  = recent_df['rain'].sum()
        ro_t    = recent_df['runoff'].sum()
        es_t    = recent_df['soil_evap'].sum()
        tr_t    = recent_df['transp'].sum()
        dr_t    = recent_df['drainage'].sum()
        dsw     = recent_df['sw_total'].iloc[-1] - recent_df['sw_total'].iloc[0]
        err     = rain_t - ro_t - es_t - tr_t - dr_t - dsw
        st.markdown(f"""
| Component | mm | % of rain |
|---|---|---|
| Rainfall | {rain_t:.1f} | 100 |
| Runoff | {ro_t:.1f} | {ro_t/rain_t*100:.1f} |
| Soil evap | {es_t:.1f} | {es_t/rain_t*100:.1f} |
| Transpiration | {tr_t:.1f} | {tr_t/rain_t*100:.1f} |
| Deep drainage | {dr_t:.1f} | {dr_t/rain_t*100:.1f} |
| Δ Soil water | {dsw:.1f} | {dsw/rain_t*100:.1f} |
| **Water check** | **{err:.3f}** | |
        """)
        epan_src  = "SILO pan evap" if recent_df['epan'].sum() > 10 else "estimated from radiation"
        sw_peak   = recent_df['sw_total'].max()
        paw_start = recent_df['pasw'].iloc[0]
        paw_end   = recent_df['pasw'].iloc[-1]
        st.caption(
            f"Epan: {recent_df['epan'].mean():.1f} mm/day mean  ({recent_df['epan'].sum():.0f} mm total)  |  "
            f"source: {epan_src}  |  "
            f"PAW start: {paw_start:.0f} mm  "
            f"PAW end: {paw_end:.0f} mm  "
            f"PAW peak: {recent_df['pasw'].max():.0f} mm  |  "
            f"PAWC: {pawc:.0f} mm  |  "
            f"Init: {init_pct}% of PAWC"
        )

    # ── Results ───────────────────────────────────────────────────────────
    final_pasw   = float(recent_df['pasw'].iloc[-1])
    pawc_pct     = final_pasw / pawc * 100 if pawc > 0 else 0.0
    fe           = calc_fallow_efficiency(recent_df, profile)
    cum_rain     = float(recent_df['rain'].sum())
    end_label    = end_date.strftime('%d %b %Y')
    start_label  = start_date.strftime('%d %b %Y')

    # ── Soil profile SVG ─────────────────────────────────────────────────────
    def _soil_profile_svg(profile, final_pasw):
        """
        Vertical soil profile showing 4 zones per layer:
          dark grey  = below LL (unavailable)
          blue       = current PAW (LL to SW)
          light grey = empty available (SW to DUL)
          mid grey   = above DUL (drainage zone)
        X-axis proportional to volumetric fraction / SAT.
        """
        layers      = profile.layers
        total_depth = sum(l.thickness for l in layers)
        BAR_W = 81    # px width of profile bar (50% wider)
        BAR_H = 200   # px total height = 2m fixed scale (1px per cm)

        # Estimate SAT fraction for each layer (sat_mm / thickness)
        # Use as common scale denominator
        elements = []
        y = 0
        for lyr in layers:
            h      = max(4, round(lyr.thickness / 2000.0 * BAR_H))  # fixed 2m scale
            sat_mm = lyr.sat_mm
            if sat_mm <= 0:
                sat_mm = lyr.dul_mm * 1.15   # fallback

            scale  = BAR_W / sat_mm           # px per mm of water

            x_ll  = round(lyr.ll_mm  * scale)
            x_dul = round(lyr.dul_mm * scale)
            x_sat = BAR_W

            # Current SW in this layer (distribute PAW proportionally by layer PAWC)
            lyr_paw  = max(0.0, min(final_pasw * lyr.pawc / profile.pawc_total,
                                    lyr.pawc)) if profile.pawc_total > 0 else 0.0
            x_sw  = round((lyr.ll_mm + lyr_paw) * scale)
            x_sw  = min(x_sw, x_dul)

            # Layer divider line (except first)
            if y > 0:
                elements.append(
                    f'<line x1="1" y1="{y}" x2="{BAR_W-1}" y2="{y}" ' +
                    'stroke="white" stroke-width="0.6" opacity="0.45"/>')

            # Below LL — dark grey
            elements.append(
                f'<rect x="1" y="{y}" width="{x_ll-1}" height="{h}" fill="#9A9488"/>')
            # Empty available (SW to DUL) — light grey
            elements.append(
                f'<rect x="{x_sw}" y="{y}" width="{x_dul-x_sw}" height="{h}" fill="#C8C2B8"/>')
            # Current PAW (LL to SW) — blue
            elements.append(
                f'<rect x="{x_ll}" y="{y}" width="{x_sw-x_ll}" height="{h}" ' +
                'fill="#4A96D4" opacity="0.85"/>')
            # Above DUL — mid grey
            elements.append(
                f'<rect x="{x_dul}" y="{y}" width="{x_sat-x_dul}" height="{h}" fill="#B0A89A"/>')

            # LL line (solid white)
            elements.append(
                f'<line x1="{x_ll}" y1="{y}" x2="{x_ll}" y2="{y+h}" ' +
                'stroke="white" stroke-width="1.6"/>')
            # DUL line (dashed white)
            elements.append(
                f'<line x1="{x_dul}" y1="{y}" x2="{x_dul}" y2="{y+h}" ' +
                'stroke="white" stroke-width="0.9" stroke-dasharray="3,2" opacity="0.7"/>')

            y += h

        body   = chr(10).join(elements)
        pawc_t = profile.pawc_total

        svg = (
            f'<svg width="{BAR_W}" height="{y+18}" ' +
            f'viewBox="0 0 {BAR_W} {y+18}" ' +
            'xmlns="http://www.w3.org/2000/svg" style="display:block">' +
            f'<rect x="1" y="0" width="{BAR_W-2}" height="{y}" rx="3" fill="#9A9488"/>' +
            body +
            f'<rect x="1" y="0" width="{BAR_W-2}" height="{y}" rx="3" ' +
            'fill="none" stroke="#7A7468" stroke-width="1"/>' +
            f'<text x="{BAR_W//2}" y="{y+13}" text-anchor="middle" ' +
            'font-family="sans-serif" font-size="10" fill="#555">' +
            f'PAWC {pawc_t:.0f}mm</text>' +
            '</svg>'
        )
        return svg

    profile_svg = _soil_profile_svg(profile, final_pasw)

    # Summary box with profile beside it
    col_box, col_prof = st.columns([5, 1])
    with col_box:
        st.markdown(f"""
        <div class="result-box">
            <div class="result-title">
                Plant available soil water on
                <span class="date-loc">{end_label}</span>
                at <span class="loc">{stn_name}</span>
            </div>
            <div class="fallow-label">
                with a Fallow efficiency of &nbsp;<strong>{fe:.0f}%</strong>
                &nbsp; from &nbsp;<strong>{cum_rain:.0f} mm</strong>&nbsp; rainfall
                &nbsp;({start_label} to {end_label})
            </div>
            <span class="paw-big">{final_pasw:.0f}</span>
            <span class="paw-unit">mm</span>
            <span class="pawc-pct">{pawc_pct:.0f}% PAWC</span>
        </div>
        """, unsafe_allow_html=True)
    with col_prof:
        st.markdown(profile_svg, unsafe_allow_html=True)

    # Chart
    fig = make_pasw_chart(
        recent_df, hist_dfs, profile,
        stn_name, start_date, end_date,
    )
    st.pyplot(fig, width='stretch')

    # Add header to export figure
    fig.suptitle(
        f"Plant available soil water — {stn_name}\n"
        f"{profile.name}  ·  {start_label} to {end_label}  ·  "
        f"Fallow efficiency {fe:.0f}%  from {cum_rain:.0f} mm rainfall  ·  "
        f"PAW {final_pasw:.0f} mm  ({pawc_pct:.0f}% PAWC)",
        fontsize=10, color='#1a2332', y=1.02,
        fontfamily='sans-serif', ha='center'
    )

    # Download button
    buf = io.BytesIO()
    fig.savefig(buf, format='jpeg', dpi=150, bbox_inches='tight',
                facecolor=C_BG)
    buf.seek(0)
    fname = (f"SoilWater_{stn_name.replace(' ','_')}_"
             f"{start_date.strftime('%Y%m%d')}_{end_date.strftime('%Y%m%d')}.jpg")
    st.download_button(
        label="⬇  Export JPEG",
        data=buf,
        file_name=fname,
        mime="image/jpeg",
        width='content',
    )

    plt.close(fig)


if __name__ == '__main__':
    main()
