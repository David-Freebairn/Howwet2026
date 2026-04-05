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

SILO format note (2025+)
------------------------
Each variable must be fetched with a separate comment=X request.
The response format is:
    station,YYYY-MM-DD,{variable},{variable}_source,metadata
Variables are merged by date after fetching.
"""

import urllib.parse
import urllib.request
import io
import pandas as pd
import numpy as np

# ── Config ───────────────────────────────────────────────────────────────────
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


# ── Low-level fetch ───────────────────────────────────────────────────────────

def _fetch_one(station_id: int, start: str, end: str, variable: str) -> str:
    """
    Fetch a single variable from SILO patched-point.
    Appends comment after urlencode so no %2C encoding issues.
    """
    base = urllib.parse.urlencode({
        "station":  station_id,
        "start":    start,
        "finish":   end,
        "format":   "csv",
        "username": _EMAIL,
        "password": "apirequest",
    })
    url = f"{_BASE}?{base}&comment={variable}"
    req = urllib.request.Request(url, headers=_HEADERS)
    with urllib.request.urlopen(req, timeout=60) as resp:
        raw = resp.read().decode("utf-8", errors="replace")
    if "<html" in raw.lower()[:200]:
        raise RuntimeError(f"WAF rejected: {raw[:200]}")
    return raw


def _parse_one(raw: str, varname: str) -> pd.Series:
    """
    Parse a single-variable SILO response into a Series indexed by date.

    Handles both formats:
      New: station,YYYY-MM-DD,{var},{var}_source,metadata
      Old: Date,daily_rain,max_temp,...  (header starts with date/yyyy)
    """
    lines = raw.splitlines()

    # Find header row — now may start with "station" as well
    hi = next(
        (i for i, ln in enumerate(lines)
         if ln.strip() and not ln.strip().startswith("#") and
            ("," in ln or "\t" in ln) and
            any(tok in ln.strip().lower()
                for tok in ("date", "yyyy", "station"))),
        None,
    )
    if hi is None:
        raise RuntimeError(f"No header in SILO response for {varname}.\nPreview: {raw[:300]}")

    df = pd.read_csv(io.StringIO("\n".join(lines[hi:])))
    df.columns = [c.strip().lower() for c in df.columns]

    # Find date column — could be "date", "yyyy-mm-dd", or similar
    date_col = next(
        (c for c in df.columns
         if c in ("date", "yyyy-mm-dd", "yyyymmdd") or
            (("date" in c or "yyyy" in c) and "source" not in c)),
        None,
    )
    if date_col is None:
        raise RuntimeError(
            f"No date column for {varname}. Columns: {list(df.columns)}"
        )

    # Parse dates
    sample = str(df[date_col].iloc[0]).strip()
    fmt = "%Y%m%d" if (len(sample) == 8 and sample.isdigit()) else "%Y-%m-%d"
    dates = pd.to_datetime(df[date_col].astype(str).str.strip(), format=fmt)

    # Find the data column — skip station, date, source, metadata columns
    skip = {date_col, "station", "metadata"}
    skip.update(c for c in df.columns if c.endswith("_source"))
    data_cols = [c for c in df.columns if c not in skip]

    if not data_cols:
        raise RuntimeError(
            f"No data column for {varname}. Columns: {list(df.columns)}"
        )

    values = pd.to_numeric(df[data_cols[0]], errors="coerce").values
    return pd.Series(values, index=dates, name=varname)


# ── Station search ───────────────────────────────────────────────────────────

def search_stations(query: str) -> list:
    """Search SILO for stations matching a name fragment."""
    base = urllib.parse.urlencode({
        "format":   "name",
        "nameFrag": query.strip(),
        "username": _EMAIL,
    })
    url = f"{_BASE}?{base}"
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


# ── Core fetch ───────────────────────────────────────────────────────────────

def fetch_station_met(station_id: int, start: str, end: str) -> pd.DataFrame:
    """
    Fetch SILO patched-point met data for a station.

    Fetches each variable separately (new SILO format requires this)
    and merges by date.
    """
    # Variables to fetch: (silo_code, output_column_name)
    variables = [
        ("daily_rain", "rain"),
        ("max_temp",   "tmax"),
        ("min_temp",   "tmin"),
        ("evap_pan",   "epan"),
        ("radiation",  "radiation"),
    ]

    series = {}
    for var_code, col_name in variables:
        try:
            raw = _fetch_one(station_id, start, end, var_code)
            series[col_name] = _parse_one(raw, var_code)
        except Exception as e:
            # Non-fatal — will fall back for missing vars
            series[col_name] = None

    # Get date index from rain (always present)
    if series.get("rain") is None:
        raise RuntimeError(
            f"Could not fetch rainfall for station {station_id}."
        )

    out = pd.DataFrame(index=series["rain"].index)
    out.index.name = "date"

    for col_name in ["rain", "tmax", "tmin", "epan", "radiation"]:
        s = series.get(col_name)
        if s is not None:
            # Reindex to align dates (handles any minor mismatches)
            out[col_name] = s.reindex(out.index).values
        else:
            out[col_name] = np.nan

    out["tmean"] = (out["tmax"] + out["tmin"]) / 2.0
    out["year"]  = out.index.year
    out["month"] = out.index.month
    out["day"]   = out.index.day
    out["doy"]   = out.index.day_of_year

    out["rain"] = out["rain"].fillna(0.0).clip(lower=0.0)
    out["epan"] = out["epan"].fillna(0.0)

    # Fallback: estimate epan from radiation if missing or all zero
    if out["epan"].sum() < 1.0:
        try:
            rs    = out["radiation"].fillna(out["radiation"].median())
            tmean = out["tmean"].fillna(20.0)
            out["epan"] = (rs * 0.50 + tmean * 0.06).clip(lower=0.5)
        except Exception:
            out["epan"] = 5.0

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
