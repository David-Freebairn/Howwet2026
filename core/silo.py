"""
core/silo.py
============
SILO Patched Point API helpers used by all pages.

Public API
----------
search_stations(query)                       -> list of station dicts
fetch_station_rainfall(station_id, start, end) -> pd.DataFrame
fetch_patched_point(station_id, start, end)    -> pd.DataFrame
fetch_station_met(station_id, start, end)      -> pd.DataFrame
"""

import urllib.parse
import urllib.request
import io
import pandas as pd
import numpy as np
from pathlib import Path

# ── Config ──────────────────────────────────────────────────────────────────
_BASE  = "https://www.longpaddock.qld.gov.au/cgi-bin/silo/PatchedPointDataset.php"
_EMAIL = "david.freebairn@gmail.com"

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "text/plain, text/csv, */*",
    "Referer": "https://www.longpaddock.qld.gov.au/silo/",
}


# ── Station search ───────────────────────────────────────────────────────────

def search_stations(query: str) -> list:
    """
    Search SILO for stations matching a name fragment.

    Returns list of dicts:
        { id, name, label, lat, lon, state }
    """
    url = (f"{_BASE}?format=name"
           f"&nameFrag={urllib.parse.quote(query.strip())}"
           f"&username={urllib.parse.quote(_EMAIL)}")
    try:
        with urllib.request.urlopen(url, timeout=15) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
    except Exception as exc:
        raise RuntimeError(f"SILO station search failed: {exc}") from exc

    stations = []
    for line in raw.strip().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "|" not in line:
            continue
        parts = [p.strip() for p in line.split("|")]
        if len(parts) < 2:
            continue
        try:
            sid   = int(parts[0])
            name  = parts[1].strip()
            lat   = float(parts[2]) if len(parts) > 2 and parts[2] else None
            lon   = float(parts[3]) if len(parts) > 3 and parts[3] else None
            state = parts[4].strip() if len(parts) > 4 else ""
            label = name
            if state:
                label += f"  [{state}]"
            if lat is not None and lon is not None:
                label += f"  ({lat:.3f}, {lon:.3f})"
            stations.append({
                "id":    sid,
                "name":  name,
                "label": label,
                "lat":   lat,
                "lon":   lon,
                "state": state,
            })
        except (ValueError, IndexError):
            continue
    return stations


# ── Core fetch ───────────────────────────────────────────────────────────────

def fetch_station_met(station_id: int, start: str, end: str) -> pd.DataFrame:
    """
    Fetch SILO patched-point data for a station number.

    Returns DataFrame indexed by date with columns:
        rain, epan, tmax, tmin, tmean, radiation, year, month, day, doy

    Fetches evap_pan as a SEPARATE request because the SILO WAF silently
    drops it when requested alongside other variables. Falls back to a
    radiation-based estimate if evap_pan is still unavailable.
    """
    import requests as _req

    def _fetch_var(var: str) -> str:
        """Single-variable fetch — avoids WAF multi-var block."""
        params = {
            "station":  station_id,
            "start":    start,
            "finish":   end,
            "format":   "csv",
            "comment":  var,
            "username": _EMAIL,
            "password": "apirequest",
        }
        r = _req.get(_BASE, params=params, headers=_HEADERS, timeout=120)
        r.raise_for_status()
        return r.text

    def _parse(raw: str) -> pd.DataFrame:
        """Parse SILO CSV — handles YYYYMMDD and YYYY-MM-DD date formats."""
        lines = raw.splitlines()
        hi = next(
            (i for i, ln in enumerate(lines)
             if ln.strip().lower().startswith("date") or
                ln.strip().lower().startswith("yyyy")),
            None,
        )
        if hi is None:
            raise ValueError(
                f"No header row in SILO response for station {station_id}.\n"
                f"Preview: {raw[:400]}"
            )
        df = pd.read_csv(io.StringIO("\n".join(lines[hi:])))
        df.columns = [c.strip().lower() for c in df.columns]

        date_col = next(
            (c for c in df.columns if "date" in c or "yyyy" in c), None
        )
        if date_col is None:
            raise ValueError(
                f"No date column for station {station_id}. "
                f"Columns: {list(df.columns)}"
            )

        sample = str(df[date_col].iloc[0]).strip()
        fmt = "%Y%m%d" if (len(sample) == 8 and sample.isdigit()) else "%Y-%m-%d"
        df.index = pd.to_datetime(df[date_col].astype(str), format=fmt)
        df.index.name = "date"
        return df

    # ── 1. Main variables ────────────────────────────────────────────────────
    raw_main = _fetch_var("daily_rain,max_temp,min_temp,radiation")
    df_main  = _parse(raw_main)

    col_map = {
        "daily_rain":             "rain",
        "rain":                   "rain",
        "max_temp":               "tmax",
        "maximum_temperature":    "tmax",
        "min_temp":               "tmin",
        "minimum_temperature":    "tmin",
        "radiation":              "radiation",
        "solar_radiation":        "radiation",
    }
    out = pd.DataFrame(index=df_main.index)
    for src, dst in col_map.items():
        if src in df_main.columns and dst not in out.columns:
            out[dst] = df_main[src].values

    for col in ["rain", "tmax", "tmin", "radiation"]:
        if col not in out.columns:
            out[col] = np.nan

    # ── 2. Fetch evap_pan separately ─────────────────────────────────────────
    try:
        raw_evap = _fetch_var("evap_pan")
        df_evap  = _parse(raw_evap)
        for src in ["evap_pan", "evap", "epan", "evaporation",
                    "evap_morton_lake", "evap_morton_wet", "evap_asce"]:
            if src in df_evap.columns and df_evap[src].fillna(0).sum() > 1.0:
                out["epan"] = df_evap[src].values
                break
    except Exception:
        pass

    # ── 3. Fallback: estimate from radiation + temperature ───────────────────
    if "epan" not in out.columns or out["epan"].fillna(0).sum() < 1.0:
        try:
            rs    = out["radiation"].fillna(out["radiation"].median())
            tmean = ((out["tmax"].fillna(25) + out["tmin"].fillna(15)) / 2)
            out["epan"] = (rs * 0.50 + tmean * 0.06).clip(lower=0.5)
        except Exception:
            out["epan"] = 5.0

    # ── Clean up ─────────────────────────────────────────────────────────────
    out["epan"]  = out["epan"].fillna(0.0)
    out["rain"]  = out["rain"].fillna(0.0)
    out["tmean"] = (out["tmax"] + out["tmin"]) / 2.0
    out["year"]  = out.index.year
    out["month"] = out.index.month
    out["day"]   = out.index.day
    out["doy"]   = out.index.day_of_year

    return out


# ── Convenience wrappers (keep existing call signatures working) ─────────────

def fetch_station_rainfall(station_id: int, start: str, end: str) -> pd.DataFrame:
    """Fetch daily rainfall only. Used by 1_Season.py."""
    df = fetch_station_met(station_id, start, end)
    return df[["rain", "year", "month", "day", "doy"]]


def fetch_patched_point(station_id: int, start: str, end: str,
                        variables: str = "R") -> pd.DataFrame:
    """Full met fetch. Used by 2_Odds.py."""
    return fetch_station_met(station_id, start, end)
