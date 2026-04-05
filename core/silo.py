"""
core/silo.py
============
SILO climate data helpers used by all pages.

Uses DataDrillDataset.php (lat/lon) with urllib.request.
Each variable is fetched in a separate request — multi-variable
comment strings trigger the SILO WAF and are rejected.

Proven working approach from app.py development (March 2026):
  - urllib.request only (requests library triggers WAF)
  - Single variable per call
  - DataDrill endpoint with lat/lon from station search
  - New response format: latitude,longitude,YYYY-MM-DD,{var},{var}_source,...
"""

import urllib.parse
import urllib.request
import io
import pandas as pd
import numpy as np

# ── Config ───────────────────────────────────────────────────────────────────
_DATADRILL  = "https://www.longpaddock.qld.gov.au/cgi-bin/silo/DataDrillDataset.php"
_PATCHEDPT  = "https://www.longpaddock.qld.gov.au/cgi-bin/silo/PatchedPointDataset.php"
_EMAIL      = "david.freebairn@gmail.com"

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "text/plain, text/csv, */*",
    "Referer": "https://www.longpaddock.qld.gov.au/silo/",
}


# ── Station search (PatchedPoint - name search only) ─────────────────────────

def search_stations(query: str) -> list:
    """Search SILO for stations matching a name fragment."""
    url = (f"{_PATCHEDPT}?format=name"
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


# ── Low-level DataDrill fetch ─────────────────────────────────────────────────

def _fetch_one(lat: float, lon: float, start: str, end: str,
               variable: str) -> str:
    """
    Fetch a single variable from SILO DataDrill using urllib.request.
    Returns raw CSV text.

    Key: urllib.request not requests (requests triggers WAF).
    Single variable only — multi-variable comment is WAF-blocked.
    """
    base = urllib.parse.urlencode({
        "lat":      lat,
        "lon":      lon,
        "start":    start,
        "finish":   end,
        "format":   "csv",
        "username": _EMAIL,
        "password": "apirequest",
    })
    url = f"{_DATADRILL}?{base}&comment={variable}"
    req = urllib.request.Request(url, headers=_HEADERS)
    with urllib.request.urlopen(req, timeout=60) as resp:
        raw = resp.read().decode("utf-8", errors="replace")
    if "<html" in raw.lower()[:200]:
        raise RuntimeError(
            f"SILO WAF rejected {variable} request.\n"
            f"Response: {raw[:200]}"
        )
    return raw


def _parse_one(raw: str, col_name: str) -> pd.Series:
    """
    Parse a single-variable DataDrill response.

    New format (2025+):
        latitude,longitude,YYYY-MM-DD,{var},{var}_source,metadata,...
    Old format:
        Date,daily_rain,max_temp,...
    """
    lines = raw.splitlines()

    # Find header row
    hi = next(
        (i for i, ln in enumerate(lines)
         if ln.strip() and "," in ln and
            any(t in ln.strip().lower()
                for t in ("date", "yyyy", "latitude", "station"))),
        None,
    )
    if hi is None:
        raise RuntimeError(
            f"No header in SILO response for {col_name}.\n"
            f"Preview: {raw[:300]}"
        )

    df = pd.read_csv(io.StringIO("\n".join(lines[hi:])), dtype=str, low_memory=False)
    df.columns = [c.strip().lower() for c in df.columns]

    # Find date column
    date_col = next(
        (c for c in df.columns
         if c in ("date", "yyyy-mm-dd", "yyyymmdd") or
            ("yyyy" in c and "source" not in c)),
        None,
    )
    if date_col is None:
        raise RuntimeError(
            f"No date column for {col_name}. Columns: {list(df.columns)}"
        )

    # Parse dates
    dates = pd.to_datetime(
        df[date_col].astype(str).str.strip(), errors="coerce"
    )

    # Find value column: skip lat, lon, date, source, metadata cols
    skip = {date_col, "latitude", "longitude", "station", "metadata"}
    skip.update(c for c in df.columns if "_source" in c)
    val_cols = [c for c in df.columns if c not in skip]

    if not val_cols:
        raise RuntimeError(
            f"No value column for {col_name}. Columns: {list(df.columns)}"
        )

    values = pd.to_numeric(df[val_cols[0]], errors="coerce")

    s = pd.Series(values.values, index=dates, name=col_name)
    s = s[s.index.notna()]
    s = s[~s.index.duplicated(keep="first")]
    return s.sort_index()


# ── Core fetch ────────────────────────────────────────────────────────────────

def fetch_station_met(station_id: int, start: str, end: str,
                      lat: float = None, lon: float = None) -> pd.DataFrame:
    """
    Fetch SILO climate data for a station.

    Uses DataDrill (lat/lon) with one urllib.request call per variable.
    lat/lon are taken from the station dict returned by search_stations().
    If not provided, raises an error — lat/lon are required for DataDrill.
    """
    if lat is None or lon is None:
        raise RuntimeError(
            "fetch_station_met requires lat and lon. "
            "Pass them from the station dict returned by search_stations()."
        )

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
            raw = _fetch_one(lat, lon, start, end, var_code)
            series[col_name] = _parse_one(raw, col_name)
        except Exception:
            series[col_name] = None

    if series.get("rain") is None:
        raise RuntimeError(
            f"Could not fetch rainfall for station {station_id} "
            f"({lat}, {lon})."
        )

    idx = series["rain"].index
    out = pd.DataFrame(index=idx)
    out.index.name = "date"

    for col in ["rain", "tmax", "tmin", "epan", "radiation"]:
        s = series.get(col)
        out[col] = s.reindex(idx).values if s is not None else np.nan

    out["tmean"] = (out["tmax"] + out["tmin"]) / 2.0
    out["year"]  = out.index.year
    out["month"] = out.index.month
    out["day"]   = out.index.day
    out["doy"]   = out.index.day_of_year

    out["rain"] = out["rain"].fillna(0.0).clip(lower=0.0)
    out["epan"] = out["epan"].fillna(0.0)

    # Fallback: estimate epan from radiation if missing
    if out["epan"].sum() < 1.0:
        try:
            rs    = out["radiation"].fillna(out["radiation"].median())
            tmean = out["tmean"].fillna(20.0)
            out["epan"] = (rs * 0.50 + tmean * 0.06).clip(lower=0.5)
        except Exception:
            out["epan"] = 5.0

    return out


# ── Convenience wrappers ──────────────────────────────────────────────────────

def fetch_station_rainfall(station_id: int, start: str, end: str,
                           lat: float = None, lon: float = None) -> pd.DataFrame:
    """Fetch daily rainfall only. Used by 1_Season.py."""
    df = fetch_station_met(station_id, start, end, lat=lat, lon=lon)
    return df[["rain", "year", "month", "day", "doy"]]


def fetch_patched_point(station_id: int, start: str, end: str,
                        variables: str = "R",
                        lat: float = None, lon: float = None) -> pd.DataFrame:
    """Full met fetch. Used by 2_Odds.py."""
    return fetch_station_met(station_id, start, end, lat=lat, lon=lon)
