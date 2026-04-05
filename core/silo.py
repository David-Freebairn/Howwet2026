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

WAF note
--------
SILO's firewall blocks requests where the 'comment' parameter has
URL-encoded commas (%2C). The fix is to build the URL manually so
commas stay as literal characters. The requests library always
encodes commas; urllib.request.urlopen with a hand-built URL string
does not — so we use that here.
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

# All variables — commas must stay literal in the URL (not %2C)
_VARIABLES = "daily_rain,max_temp,min_temp,evap_pan,radiation"


# ── Station search ───────────────────────────────────────────────────────────

def search_stations(query: str) -> list:
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


# ── Core fetch ───────────────────────────────────────────────────────────────

def fetch_station_met(station_id: int, start: str, end: str) -> pd.DataFrame:
    """
    Fetch SILO patched-point data for a station.

    Builds the URL manually so commas in the comment parameter are NOT
    percent-encoded. Encoding them as %2C triggers the SILO WAF.
    """
    base_params = (
        f"station={station_id}"
        f"&start={start}"
        f"&finish={end}"
        f"&format=csv"
        f"&comment={_VARIABLES}"
        f"&username={urllib.parse.quote(_EMAIL)}"
        f"&password=apirequest"
    )
    url = f"{_BASE}?{base_params}"

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

    return _parse(raw, station_id)


def _parse(raw: str, station_id: int) -> pd.DataFrame:
    lines = raw.splitlines()
    hi = next(
        (i for i, ln in enumerate(lines)
         if ln.strip().lower().startswith("date") or
            ln.strip().lower().startswith("yyyy")),
        None,
    )
    if hi is None:
        raise RuntimeError(
            f"No header row in SILO response for station {station_id}.\n"
            f"Preview: {raw[:400]}"
        )

    df_raw = pd.read_csv(io.StringIO("\n".join(lines[hi:])))
    df_raw.columns = [c.strip().lower() for c in df_raw.columns]

    date_col = next(
        (c for c in df_raw.columns if "date" in c or "yyyy" in c), None
    )
    if date_col is None:
        raise RuntimeError(
            f"No date column for station {station_id}. "
            f"Columns: {list(df_raw.columns)}"
        )

    sample = str(df_raw[date_col].iloc[0]).strip()
    fmt = "%Y%m%d" if (len(sample) == 8 and sample.isdigit()) else "%Y-%m-%d"
    index = pd.to_datetime(df_raw[date_col].astype(str), format=fmt)

    out = pd.DataFrame(index=index)
    out.index.name = "date"

    def _col(*candidates):
        for c in candidates:
            if c in df_raw.columns:
                return pd.to_numeric(df_raw[c], errors="coerce").values
        return np.full(len(df_raw), np.nan)

    out["rain"]      = _col("daily_rain", "rain", "rainfall")
    out["tmax"]      = _col("max_temp",   "maximum_temperature", "tmax")
    out["tmin"]      = _col("min_temp",   "minimum_temperature", "tmin")
    out["epan"]      = _col("evap_pan",   "evap", "evaporation", "epan", "pan_evap")
    out["radiation"] = _col("radiation",  "solar_radiation")

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
