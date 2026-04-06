"""
pages/2_Odds.py — What are the odds?
======================================
Rainfall frequency analysis using SILO Patched Point data.
Ported from rainfall_app.py — SILO calls now use core.silo.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import streamlit as st
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from datetime import date

from core.silo import search_stations, fetch_patched_point
from core.styles import apply_styles, save_station, load_station

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(page_title="What are the odds?", page_icon="🎲", layout="wide")

MONTHS = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]

apply_styles()


# ── Session state ─────────────────────────────────────────────────────────────
for key, default in [
    ("df", None), ("station_name", None), ("stations", []),
    ("last_search", ""), ("selected_station", None),
    ("search_error", None), ("search_input", ""),
    ("station_confirmed", False), ("station_chosen", None),
]:
    if key not in st.session_state:
        st.session_state[key] = default

# Pre-populate from shared station if arriving from another page
_shared = load_station()
if _shared and not st.session_state.get("search_input"):
    st.session_state["search_input"]      = _shared.get("name", "")
    st.session_state["selected_station"]  = _shared
    st.session_state["stations"]          = [_shared]
    st.session_state["last_search"]       = _shared.get("name", "")
    st.session_state["station_confirmed"] = True
    st.session_state["station_chosen"]    = _shared.get("label", "")


# ── Helpers ───────────────────────────────────────────────────────────────────

@st.cache_data(ttl=3600, show_spinner=False)
def _search(term):
    return search_stations(term)


@st.cache_data(ttl=3600, show_spinner=False)
def _fetch(station_id, start, end):
    return fetch_patched_point(station_id, start, end, variables="R")


def parse_df(df: pd.DataFrame) -> pd.DataFrame:
    """Ensure the rainfall DataFrame has year/month/day columns."""
    if "year" not in df.columns:
        df["year"] = df.index.year
    if "month" not in df.columns:
        df["month"] = df.index.month
    if "day" not in df.columns:
        df["day"] = df.index.day
    return df


def assign_season_year(df, sm, sd, em, ed):
    df = df.copy()
    mo = df.index.month if "month" not in df.columns else df["month"]
    dy = df.index.day   if "day"   not in df.columns else df["day"]
    yr = df.index.year  if "year"  not in df.columns else df["year"]

    crosses = (sm > em) or (sm == em and sd > ed)
    after_start = (mo > sm) | ((mo == sm) & (dy >= sd))
    before_end  = (mo < em) | ((mo == em) & (dy <= ed))
    mask = after_start & before_end if not crosses else after_start | before_end
    df = df[mask].copy()

    mo2 = df.index.month if "month" not in df.columns else df["month"]
    dy2 = df.index.day   if "day"   not in df.columns else df["day"]
    yr2 = df.index.year  if "year"  not in df.columns else df["year"]

    if crosses:
        after = (mo2 > sm) | ((mo2 == sm) & (dy2 >= sd))
        df["season_year"] = np.where(after, yr2, yr2 - 1)
    else:
        df["season_year"] = yr2
    return df


def season_label(sm, sd, em, ed):
    return f"{sd} {MONTHS[sm-1]} – {ed} {MONTHS[em-1]}"


# ── Header ────────────────────────────────────────────────────────────────────
st.title("🎲 What are the odds?")
st.caption("*Rainfall frequency analysis — how often has it happened before?*")

# ── Panel 1 — Site ────────────────────────────────────────────────────────────
def do_search():
    term = st.session_state.search_input
    if term and term != st.session_state.last_search:
        st.session_state.last_search = term
        st.session_state.stations = []
        st.session_state.selected_station = None
        st.session_state.station_confirmed = False
        st.session_state.station_chosen = None
        try:
            st.session_state.stations = _search(term)
        except Exception as e:
            st.session_state.search_error = str(e)


with st.container(border=True):
    st.markdown('<p class="section-title">Select site</p>', unsafe_allow_html=True)
    col1, col2 = st.columns([2.5, 1.0])
    with col1:
        st.text_input(
            "station", label_visibility="collapsed",
            placeholder="Search station — e.g. Roma, Cairns  (press Enter)",
            key="search_input", on_change=do_search,
        )
    with col2:
        start_year = st.number_input(
            "Records from year", min_value=1889,
            max_value=date.today().year, value=1900, step=1,
        )
    start_date = date(int(start_year), 1, 1)

    if st.session_state.get("search_error"):
        st.error(f"Search failed: {st.session_state.search_error}")
        st.session_state.search_error = None

    if st.session_state.stations:
        labels = [s["label"] for s in st.session_state.stations]
        if len(labels) == 1:
            selected_label = labels[0]
            st.success(f"Found: **{labels[0]}**")
        else:
            confirmed = st.session_state.get("station_confirmed", False)
            chosen    = st.session_state.get("station_chosen") or labels[0]
            if chosen not in labels:
                chosen = labels[0]
            if confirmed:
                c1, c2 = st.columns([6, 1])
                with c1:
                    st.success(f"📍 {chosen}")
                with c2:
                    if st.button("Change", key="change_btn"):
                        st.session_state.station_confirmed = False
                selected_label = chosen
            else:
                current_index = labels.index(chosen) if chosen in labels else 0
                st.caption(f"**{len(labels)} stations found** — click to select:")
                def on_station_pick():
                    st.session_state.station_chosen    = st.session_state.station_select
                    st.session_state.station_confirmed = True
                selected_label = st.radio(
                    "Station", options=labels, index=current_index,
                    key="station_select", label_visibility="collapsed",
                    on_change=on_station_pick,
                )
                st.session_state.station_chosen = selected_label
        st.session_state.selected_station = next(
            s for s in st.session_state.stations if s["label"] == selected_label
        )
        save_station(st.session_state.selected_station)
    elif st.session_state.last_search:
        st.warning("No stations found. Try a shorter search term.")

selected_station = st.session_state.get("selected_station") or load_station()


# ── Panel 2 — Query ───────────────────────────────────────────────────────────
with st.container(border=True):
    st.markdown('<p class="section-title">Set up query</p>', unsafe_allow_html=True)

    r1a, r1b, r1c, r1d, r1e, r1f, r1g = st.columns([2.0, 0.9, 0.7, 1.1, 0.9, 0.5, 1.5])
    with r1a: st.markdown('<span style="font-size:1rem">Explore how often</span>',
                          unsafe_allow_html=True)
    with r1b: threshold = st.number_input("mm", label_visibility="collapsed",
                                          min_value=1, max_value=9999, value=25, step=5)
    with r1c: st.markdown('<span style="font-size:1rem">mm rain occurs over</span>',
                          unsafe_allow_html=True)
    with r1d: win_days = st.number_input("days", label_visibility="collapsed",
                                         min_value=1, max_value=365, value=5, step=1)
    with r1e: st.markdown('<span style="font-size:1rem">days</span>', unsafe_allow_html=True)

    st.markdown("")
    r2a, r2b, r2c, r2d, r2e, r2f, r2g = st.columns([1.6, 1.5, 0.9, 0.4, 1.5, 0.9, 1.0])
    with r2a: st.markdown('<span style="font-size:1rem">during the season</span>',
                          unsafe_allow_html=True)
    with r2b: start_mon = st.selectbox("sm", MONTHS, index=0, label_visibility="collapsed")
    with r2c: start_day = st.number_input("sd", min_value=1, max_value=31, value=1,
                                          label_visibility="collapsed")
    with r2d: st.markdown('<span style="font-size:1rem">to</span>', unsafe_allow_html=True)
    with r2e: end_mon = st.selectbox("em", MONTHS, index=11, label_visibility="collapsed")
    with r2f: end_day = st.number_input("ed", min_value=1, max_value=31, value=31,
                                         label_visibility="collapsed")

run_btn = st.button("Fetch data and run analysis", type="primary",
                    disabled=selected_station is None,
                    use_container_width=True)


# ── Analysis ──────────────────────────────────────────────────────────────────
if run_btn and selected_station:
    sid  = selected_station["id"]
    name = selected_station["name"]
    end_str   = date.today().strftime("%Y%m%d")
    start_str = start_date.strftime("%Y%m%d")

    with st.spinner(f"Fetching data for {name}..."):
        try:
            df = _fetch(sid, start_str, end_str)
            df = parse_df(df)
        except Exception as e:
            st.error(f"Data fetch failed: {e}")
            st.stop()

    years    = sorted(df["year"].unique())
    yr_from, yr_to = years[0], years[-1]
    ann_mean = df.groupby("year")["rain"].sum().mean()

    st.markdown(f"""<div class="chip-row">
      <div class="chip">✅ <b>{name}</b></div>
      <div class="chip"><b>{yr_from}–{yr_to}</b> period</div>
      <div class="chip">Annual mean <b>{int(round(ann_mean))} mm</b></div>
    </div>""", unsafe_allow_html=True)

    try:
        sm = MONTHS.index(start_mon) + 1
        em = MONTHS.index(end_mon)   + 1
        sd_i, ed_i = int(start_day), int(end_day)
        slabel = season_label(sm, sd_i, em, ed_i)

        sub = assign_season_year(df, sm, sd_i, em, ed_i)
        sub = sub[(sub["season_year"] >= yr_from) & (sub["season_year"] <= yr_to)]

        if sub.empty:
            st.warning("No data in that season/year range.")
            st.stop()

        results = []
        for sy, grp in sub.sort_values("season_year").groupby("season_year"):
            rolled = grp["rain"].rolling(window=int(win_days), min_periods=int(win_days)).sum()
            mx = rolled.max()
            if not np.isnan(mx):
                results.append({"season_year": sy, "max_roll_mm": mx,
                                 "met_criteria": int(mx >= threshold)})

        if not results:
            st.warning("Not enough days to compute rolling window.")
            st.stop()

        annual_max = pd.DataFrame(results)
        rain       = annual_max["max_roll_mm"].values
        n          = len(rain)
        n_exceed   = int(np.sum(rain >= threshold))
        pct        = n_exceed / n * 100

        ann_mean = round(df.groupby("year")["rain"].sum().mean())
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Station", name)
        c2.metric("Period", f"{yr_from}–{yr_to}")
        c3.metric("Years exceeded", f"{n_exceed} of {n}")
        c4.metric("Exceedance frequency", f"{int(round(pct))}%")
        st.caption(f"Query: ≥ {int(threshold)} mm rain in any {int(win_days)}-day window · {slabel} · Annual mean {ann_mean} mm")

        # Chart
        NAVY = "#0b1f3a"; BLUE = "#2979c4"; BRIGHT = "#4da6ff"
        MISS = "#b8cfe8"; BG = "#f7fafd"; GRID = "#dde5ee"

        fig, ax = plt.subplots(figsize=(14, 4.0))
        fig.patch.set_facecolor(BG); ax.set_facecolor(BG)

        colours = [BRIGHT if r >= threshold else MISS for r in annual_max["max_roll_mm"]]
        bars = ax.bar(annual_max["season_year"], annual_max["max_roll_mm"],
                      color=colours, width=0.72, zorder=3, linewidth=0, alpha=0.95)
        for bar, r in zip(bars, annual_max["max_roll_mm"]):
            if r >= threshold:
                bar.set_edgecolor(BLUE); bar.set_linewidth(0.8)

        ax.axhline(threshold, color=NAVY, lw=1.8, ls="--", zorder=4)
        ax.text(annual_max["season_year"].max() + 0.5,
                threshold + rain.max() * 0.018,
                f"▶  {int(threshold)} mm",
                color=NAVY, fontsize=9.5, va="bottom",
                fontweight="bold", fontfamily="monospace")

        ax.set_xlabel("Season year", fontsize=10, color="#3a5a7a", labelpad=6)
        ax.set_ylabel(f"Max {int(win_days)}-day rainfall  (mm)",
                      fontsize=10, color="#3a5a7a", labelpad=6)
        ax.tick_params(colors="#3a5a7a", labelsize=9)
        if n > 30: ax.tick_params(axis="x", rotation=45)
        ax.grid(True, axis="y", color=GRID, lw=0.9, zorder=0)
        ax.set_axisbelow(True)
        for sp in ["top", "right", "left"]: ax.spines[sp].set_visible(False)
        ax.spines["bottom"].set_color(GRID)
        ax.set_title(
            f"{name}   ·   {slabel}   ·   {int(win_days)}-day window   ·   {yr_from}–{yr_to}",
            fontsize=11, fontweight="bold", color=NAVY, pad=10,
        )
        from matplotlib.patches import Patch
        ax.legend(handles=[
            Patch(color=BRIGHT, edgecolor=BLUE, linewidth=0.8,
                  label=f"≥ {int(threshold)} mm  ({n_exceed} yrs)"),
            Patch(color=MISS, label=f"< {int(threshold)} mm  ({n - n_exceed} yrs)"),
        ], fontsize=9, loc="upper left", framealpha=0.95, edgecolor=GRID, fancybox=False)
        fig.tight_layout(pad=1.1)


        # ── Bar chart ─────────────────────────────────────────────────────
        st.pyplot(fig)
        plt.close(fig)

        # ── Build JPEG summary for download (keep matplotlib version) ─────
        import io as _io
        from matplotlib.patches import FancyBboxPatch
        summary_fig, summary_ax = plt.subplots(figsize=(10, 4.0))
        summary_fig.patch.set_facecolor("#ffffff")
        summary_ax.set_facecolor("#ffffff")
        summary_ax.set_xlim(0, 10); summary_ax.set_ylim(0, 4.0)
        summary_ax.axis("off")
        summary_ax.add_patch(FancyBboxPatch((0.08, 0.08), 9.84, 3.84,
            boxstyle="round,pad=0.12", facecolor="#ffffff",
            edgecolor="#c8d8ec", linewidth=1.5, zorder=0))
        summary_ax.add_patch(FancyBboxPatch((0.08, 3.28), 9.84, 0.68,
            boxstyle="round,pad=0.12", facecolor="#2979c4",
            edgecolor="none", zorder=1))
        summary_ax.text(5, 3.62, "What are the odds?   ·   Rain frequency summary",
            ha="center", va="center", fontsize=12.5, fontweight="bold",
            color="white", zorder=2)
        summary_ax.text(0.4, 2.95, name,
            ha="left", va="center", fontsize=15, fontweight="bold",
            color="#0b1f3a", zorder=2)
        summary_ax.text(0.4, 2.6,
            f"Season: {slabel}     Record: {yr_from}–{yr_to}",
            ha="left", va="center", fontsize=10.5, color="#4a6e94", zorder=2)
        summary_ax.plot([0.4, 9.6], [2.38, 2.38], color="#d0dcea", lw=1.0, zorder=2)
        summary_ax.text(0.4, 2.12,
            f"Query:  >= {int(threshold)} mm rain within any {int(win_days)}-day window  .  {slabel}",
            ha="left", va="center", fontsize=10.5, color="#5a7a9a", zorder=2)
        summary_ax.text(4.2, 1.28, f"{n_exceed} of {n} years",
            ha="center", va="center", fontsize=21, fontweight="bold",
            color="#0b1f3a", zorder=2)
        summary_ax.text(4.2, 0.72, "met or exceeded the threshold",
            ha="center", va="center", fontsize=10, color="#6a8aaa", zorder=2)
        summary_ax.text(8.8, 1.4, f"{int(round(pct))}%",
            ha="center", va="center", fontsize=40, fontweight="bold",
            color="#2979c4", zorder=2)
        summary_ax.text(8.8, 0.6, "exceedance frequency",
            ha="center", va="center", fontsize=9, color="#8aaac4", zorder=2)
        summary_ax.plot([6.5, 6.5], [0.35, 1.85], color="#d0dcea", lw=1.0, zorder=2)
        summary_fig.tight_layout(pad=0)

        # Show on screen
        st.pyplot(summary_fig)

        jpeg_buf = _io.BytesIO()
        summary_fig.savefig(jpeg_buf, format="jpeg", dpi=150,
                            bbox_inches="tight", facecolor="#ffffff")
        jpeg_buf.seek(0)
        plt.close(summary_fig)

        # ── Downloads ─────────────────────────────────────────────────────
        dl1, dl2 = st.columns(2)
        with dl1:
            export = annual_max.copy()
            export["window_days"]  = int(win_days)
            export["threshold_mm"] = threshold
            export["season"]       = slabel
            st.download_button(
                "💾  Export CSV",
                data=export.to_csv(index=False),
                file_name=f"rolling_window_{name.replace(' ', '_')}.csv",
                mime="text/csv",
            )
        with dl2:
            st.download_button(
                "🖼️  Download summary image",
                data=jpeg_buf,
                file_name=f"rain_summary_{name.replace(' ', '_')}.jpg",
                mime="image/jpeg",
            )

    except Exception as e:
        st.error(f"Analysis error: {e}")
