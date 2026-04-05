"""
core/silo.py
============
SILO Patched Point API helpers used by all pages.

Public API
----------
search_stations(query)                         -> list of station dicts
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

# ── Config ─────────────────────────────────────────────────────────────────
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


# ── Station search ──────────────────────────────────────────────────────────

def search_stations(query: str) -> list:
    """
    Search SILO for stations matching a name fragment.
    Returns list of dicts: { id, name, label, lat, lon, state }
    """
    url = (f"{_BASE}?format=name"
           f"&nameFrag={urllib.parse.quote(query.strip())}"
           f"&username={urllib.parse.quote(_EMAIL)}")
    try:
        req = urllib.request.Request(url, headers=_HEADERS)
        with urllib.request.urlopen(req, timeout=15) as resp:
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
            stations.append({"id": sid, "name": name, "label": label,
                              "lat": lat, "lon": lon, "state": state})
        except (ValueError, IndexError):
            continue
    return stations


# ── Fetch ───────────────────────────────────────────────────────────────────

def fetch_station_met(station_id: int, start: str, end: str) -> pd.DataFrame:
    """
    Fetch SILO patched-point met data for a station.
    Single request returning all variables.
    """
    params = urllib.parse.urlencode({
        "station":  station_id,
        "start":    start,
        "finish":   end,
        "format":   "csv",
        "comment":  "evap_pan",
        "username": _EMAIL,
        "password": "apirequest",
    })
    # Append rain+met variables manually so commas are NOT percent-encoded
    # (SILO WAF blocks %2C in the comment parameter)
    url = f"{_BASE}?{params}"
    url = url.replace("comment=evap_pan",
                      "comment=daily_rain,max_temp,min_temp,evap_pan,radiation")

    try:
        req = urllib.request.Request(url, headers=_HEADERS)
        with urllib.request.urlopen(req, timeout=120) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
    except Exception as exc:
        raise RuntimeError(
            f"SILO fetch failed for station {station_id}: {exc}"
        ) from exc

    if "<html" in raw.lower()[:200]:
        raise RuntimeError(
            f"SILO WAF rejected request for station {station_id}.\n"
            f"Response: {raw[:300]}"
        )

    return _parse_patched_point(raw, station_id)


def _parse_patched_point(text: str, station_id: int) -> pd.DataFrame:
    """
    Parse SILO Patched Point CSV response.

    Handles all known SILO format variations:
      New (2025+): station,YYYY-MM-DD,{var},{var}_source,metadata
      Old multi-col: Date,daily_rain,max_temp,min_temp,evap_pan,...
    """
    lines = text.splitlines()

    # Find the header row — must have comma/tab AND contain a date/station indicator
    header_idx = None
    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if "," not in stripped and "\t" not in stripped:
            continue
        low = stripped.lower()
        tokens = [t.strip() for t in low.replace("\t", ",").split(",")]
        if any(t in ("date", "yyyy-mm-dd", "yyyymmdd", "station") for t in tokens):
            header_idx = i
            break
        if any("rain" in t and "source" not in t for t in tokens):
            header_idx = i
            break

    if header_idx is None:
        raise RuntimeError(
            f"Could not find header in SILO response for station {station_id}.\n"
            f"Preview: {text[:400]}"
        )

    sep = "\t" if "\t" in lines[header_idx] else ","
    csv_lines = [l for l in lines[header_idx:]
                 if l.strip() and not l.strip().startswith("#")]
    raw_df = pd.read_csv(io.StringIO("\n".join(csv_lines)), sep=sep, dtype=str)

    # Normalise column names
    raw_df.columns = [c.strip().lower().replace(" ", "_").replace("(", "_")
                      .replace(")", "").rstrip("_")
                      for c in raw_df.columns]

    # ── Date column ──────────────────────────────────────────────────────────
    date_col = None
    for c in raw_df.columns:
        if c in ("date", "yyyy-mm-dd", "yyyymmdd"):
            date_col = c
            break
    if date_col is None:
        # Fall back: first col that looks like a date
        for c in raw_df.columns:
            sample = str(raw_df[c].iloc[0]).strip()
            if len(sample) in (8, 10) and (sample.isdigit() or "-" in sample):
                date_col = c
                break
    if date_col is None:
        raise RuntimeError(
            f"No date column for station {station_id}. "
            f"Columns: {list(raw_df.columns)}"
        )

    date_raw = raw_df[date_col].astype(str).str.strip()
    sample = date_raw.iloc[0]
    fmt = "%Y%m%d" if (len(sample) == 8 and sample.isdigit()) else "%Y-%m-%d"
    dates = pd.to_datetime(date_raw, format=fmt, errors="coerce")
    valid = dates.notna()
    raw_df = raw_df[valid].copy()
    dates  = dates[valid]

    out = pd.DataFrame(index=dates)
    out.index.name = "date"

    def _get(*candidates):
        for c in candidates:
            if c in raw_df.columns:
                return pd.to_numeric(raw_df[c], errors="coerce").values
        return np.full(len(raw_df), np.nan)

    out["rain"]      = _get("daily_rain", "rain", "rainfall_mm", "rainfall")
    out["tmax"]      = _get("max_temp",   "maximum_temperature_c", "tmax")
    out["tmin"]      = _get("min_temp",   "minimum_temperature_c", "tmin")
    out["epan"]      = _get("evap_pan",   "evaporation_mm", "epan", "pan_evap",
                            "evap", "evaporation")
    out["radiation"] = _get("radiation",  "solar_radiation_mj_m2")
    out["vp"]        = _get("vp",         "vapour_pressure_hpa")

    out["tmean"] = (out["tmax"] + out["tmin"]) / 2.0
    out["year"]  = out.index.year
    out["month"] = out.index.month
    out["day"]   = out.index.day
    out["doy"]   = out.index.day_of_year

    out["rain"] = out["rain"].fillna(0.0).clip(lower=0.0)
    out["epan"] = out["epan"].fillna(0.0)

    # Fallback: estimate epan from radiation if all zero
    if out["epan"].sum() < 1.0:
        try:
            rs    = out["radiation"].fillna(out["radiation"].median())
            tmean = out["tmean"].fillna(20.0)
            out["epan"] = (rs * 0.50 + tmean * 0.06).clip(lower=0.5)
        except Exception:
            out["epan"] = 5.0

    if len(out) == 0:
        raise RuntimeError(
            f"No valid rows parsed from SILO for station {station_id}."
        )

    return out


# ── Convenience wrappers ─────────────────────────────────────────────────────

def fetch_station_rainfall(station_id: int, start: str, end: str) -> pd.DataFrame:
    """Fetch daily rainfall only. Used by 1_Season.py."""
    df = fetch_station_met(station_id, start, end)
    return df[["rain", "year", "month", "day", "doy"]]


def fetch_patched_point(station_id: int, start: str, end: str,
                        variables: str = "R") -> pd.DataFrame:
    """Full met fetch. Used by 2_Odds.py."""
    return fetch_station_met(station_id, start, end)
