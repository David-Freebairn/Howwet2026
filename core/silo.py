"""
core/silo.py
============
SILO Patched Point API helpers used by all pages.

Public API
----------
search_stations(query)          -> list of station dicts
fetch_station_met(station_id, start, end) -> pd.DataFrame
"""

import urllib.parse
import urllib.request
import io
import pandas as pd
import numpy as np
from pathlib import Path

# ── Config ─────────────────────────────────────────────────────────────────
_BASE  = "https://www.longpaddock.qld.gov.au/cgi-bin/silo/PatchedPointDataset.php"
_EMAIL = "david.freebairn@gmail.com"   # SILO requires a registered email


# ── Station search ──────────────────────────────────────────────────────────

def search_stations(query: str) -> list[dict]:
    """
    Search SILO for stations matching a name fragment.

    Returns list of dicts:
        { id: int, name: str, label: str, lat: float, lon: float, state: str }
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


# ── Fetch met data ──────────────────────────────────────────────────────────

def fetch_station_rainfall(station_id: int, start: str, end: str) -> pd.DataFrame:
    """
    Fetch daily rainfall only from SILO Patched Point.
    Used by 1_Season.py.

    Returns
    -------
    pd.DataFrame indexed by date with columns:
        rain, year, month, day, doy
    """
    df = fetch_station_met(station_id, start, end)
    return df[["rain", "year", "month", "day", "doy"]]


def fetch_patched_point(station_id: int, start: str, end: str,
                        variables: str = "R") -> pd.DataFrame:
    """
    Fetch full daily met from SILO Patched Point.
    Used by 2_Odds.py.

    Parameters
    ----------
    station_id : int    SILO station number
    start      : str    YYYYMMDD
    end        : str    YYYYMMDD
    variables  : str    SILO comment code (default "R" = rainfall only,
                        "RD" = rain + extras). Ignored — always fetches
                        full set so all pages get what they need.

    Returns
    -------
    pd.DataFrame indexed by date — same columns as fetch_station_met.
    """
    return fetch_station_met(station_id, start, end)


def fetch_station_met(station_id: int, start: str, end: str) -> pd.DataFrame:
    """
    Fetch daily climate from SILO Patched Point for a known station ID.

    Parameters
    ----------
    station_id : int    SILO station number
    start      : str    YYYYMMDD
    end        : str    YYYYMMDD

    Returns
    -------
    pd.DataFrame indexed by date with columns:
        rain, epan, tmax, tmin, tmean, radiation, vp, year, month, day, doy
    """
    url = (f"{_BASE}"
           f"?station={station_id}"
           f"&start={start}&finish={end}"
           f"&format=csv&comment=R"
           f"&username={urllib.parse.quote(_EMAIL)}")
    try:
        with urllib.request.urlopen(url, timeout=90) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
    except Exception as exc:
        raise RuntimeError(
            f"SILO fetch failed for station {station_id} "
            f"({start}–{end}): {exc}"
        ) from exc

    return _parse_patched_point(raw, station_id)


# ── Parser ──────────────────────────────────────────────────────────────────

def _parse_patched_point(text: str, station_id: int) -> pd.DataFrame:
    """
    Parse SILO Patched Point CSV response into a clean DataFrame.

    Handles all known SILO format variations:
      - comment=R  : Date,daily_rain,max_temp,min_temp,evap_pan,...
      - comment=RD : Date,Rainfall(mm),MaxTemp(C),...
      - DataDrill  : Date,daily_rain,...
    Date column may be YYYYMMDD integer or YYYY-MM-DD string.
    """
    lines = text.splitlines()
    preview = "\n".join(lines[:15])

    # ── Check for server-side errors first ───────────────────────────────
    low_text = text.lower()
    if "rejected" in low_text and len(text) < 500:
        raise RuntimeError(
            f"SILO rejected the request (station {station_id}).\n"
            "The station ID may be invalid, or SILO may be temporarily unavailable.\n"
            f"Response:\n{preview}"
        )

    # ── Find the header row ───────────────────────────────────────────────
    # Criteria: a comma-separated line where one token looks like a date
    # label ("date", "yyyy") or contains "rain"
    header_idx = None
    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        low = stripped.lower()
        if "," not in low and "\t" not in low:
            continue
        # Looks like a header if it has 'date' or 'rain' in a field
        tokens = [t.strip().lower() for t in low.replace("\t", ",").split(",")]
        if any(t in ("date", "yyyy", "yyyymmdd") for t in tokens):
            header_idx = i
            break
        if any("rain" in t and "source" not in t for t in tokens):
            header_idx = i
            break

    if header_idx is None:
        raise RuntimeError(
            f"Could not find data header in SILO response "
            f"for station {station_id}.\n"
            f"First 15 lines:\n{preview}"
        )

    # ── Parse the CSV from the header row onward ──────────────────────────
    sep = "\t" if "\t" in lines[header_idx] else ","
    csv_text = "\n".join(
        l for l in lines[header_idx:]
        if l.strip() and not l.strip().startswith("#")
    )
    raw_df = pd.read_csv(io.StringIO(csv_text), sep=sep, dtype=str)

    # Normalise column names: lowercase, strip whitespace and unit suffixes
    # e.g. "Rainfall(mm)" -> "rainfall_mm", "Date" -> "date"
    def _norm_col(c):
        c = c.strip().lower()
        c = c.replace("(", "_").replace(")", "").replace(" ", "_")
        c = c.rstrip("_")
        return c

    raw_df.columns = [_norm_col(c) for c in raw_df.columns]

    # ── Identify the date column ──────────────────────────────────────────
    date_col = None
    for candidate in ("date", "yyyy", "yyyymmdd"):
        if candidate in raw_df.columns:
            date_col = candidate
            break
    if date_col is None:
        # Fall back to first column if it looks numeric (YYYYMMDD)
        first = raw_df.columns[0]
        if raw_df[first].str.match(r"^\d{8}$").any():
            date_col = first

    if date_col is None:
        raise RuntimeError(
            f"Could not identify date column in SILO data for station {station_id}.\n"
            f"Columns found: {list(raw_df.columns)}\n"
            f"Header line: {lines[header_idx]}"
        )

    # ── Parse dates — handle YYYYMMDD int or YYYY-MM-DD string ───────────
    date_raw = raw_df[date_col].astype(str).str.strip()
    # Try YYYYMMDD first (most common)
    dates = pd.to_datetime(date_raw, format="%Y%m%d", errors="coerce")
    # Fall back to ISO format
    mask_failed = dates.isna()
    if mask_failed.any():
        dates[mask_failed] = pd.to_datetime(
            date_raw[mask_failed], format="%Y-%m-%d", errors="coerce"
        )
    # Final fallback — let pandas infer
    still_failed = dates.isna()
    if still_failed.any():
        dates[still_failed] = pd.to_datetime(
            date_raw[still_failed], errors="coerce"
        )

    # ── Build standardised output DataFrame ──────────────────────────────
    df = pd.DataFrame(index=dates)
    df.index.name = "date"
    df = df[df.index.notna()].copy()
    valid_mask = dates.notna().values

    def _get_col(raw, *candidates):
        """Return first matching column as float array, or NaN array."""
        for c in candidates:
            if c in raw.columns:
                return pd.to_numeric(raw.loc[valid_mask, c], errors="coerce").values
        return np.full(valid_mask.sum(), np.nan)

    df["rain"]      = _get_col(raw_df, "daily_rain", "rainfall_mm", "rain", "rainfall")
    df["tmax"]      = _get_col(raw_df, "max_temp",   "maxtemp_c",   "tmax", "maximum_temperature_c")
    df["tmin"]      = _get_col(raw_df, "min_temp",   "mintemp_c",   "tmin", "minimum_temperature_c")
    df["epan"]      = _get_col(raw_df, "evap_pan",   "evaporation_mm", "epan", "pan_evap")
    df["radiation"] = _get_col(raw_df, "radiation",  "solar_radiation_mj_m2")
    df["vp"]        = _get_col(raw_df, "vp",         "vapour_pressure_hpa")

    df["tmean"] = np.where(
        np.isnan(df["tmax"].values) | np.isnan(df["tmin"].values),
        np.nan,
        (df["tmax"].values + df["tmin"].values) / 2.0,
    )

    df["year"]  = df.index.year
    df["month"] = df.index.month
    df["day"]   = df.index.day
    df["doy"]   = df.index.day_of_year

    # Ensure epan and rain have no NaN (model needs numeric values)
    df["epan"] = np.where(np.isnan(df["epan"].values), 0.0, df["epan"].values)
    df["rain"] = np.where(np.isnan(df["rain"].values), 0.0,
                          np.maximum(0.0, df["rain"].values))

    if len(df) == 0:
        raise RuntimeError(
            f"SILO returned data for station {station_id} but no valid rows "
            f"could be parsed. Check station ID and date range."
        )

    return df
