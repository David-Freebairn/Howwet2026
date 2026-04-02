"""
core/silo.py — Unified SILO API layer
======================================
Single module used by all three apps:
  - Season  (How is the season going?)
  - Odds    (What are the odds?)
  - Howwet  (Soil water monitor)

Public API
----------
  search_stations(query)
      Search SILO station list by name fragment.
      Returns list of dicts: {id, name, label, lat, lon, state}
      Used by: Season, Odds (patched-point station search)

  fetch_patched_point(station_id, start, end, variables='R')
      Fetch daily data from SILO Patched Point Dataset by station number.
      Returns pd.DataFrame indexed by date.
      Used by: Season (rainfall only), Odds (rainfall only)

  fetch_datadrill(lat, lon, start, end, email)
      Fetch daily gridded data from SILO DataDrill by lat/lon.
      Returns pd.DataFrame indexed by date with full met variables.
      Used by: Howwet (soil water monitor)

Both fetch functions return a DataFrame with standardised column names:
  rain, tmax, tmin, tmean, epan, radiation, rhmax, rhmin,
  year, month, day, doy

SILO endpoints
--------------
  PatchedPointDataset.php  — station-based, records back to 1889
  DataDrillDataset.php     — gridded interpolation, any lat/lon

Notes
-----
  - SILO's WAF requires a browser-like User-Agent; this is set on all requests.
  - username can be any valid-looking email (SILO doesn't validate).
  - DataDrill requires password='apirequest'.
  - Streamlit @st.cache_data decorators are applied to expensive network calls.
"""

import io
import urllib.parse
import urllib.request
import ssl

import numpy as np
import pandas as pd
import requests

# ── Constants ─────────────────────────────────────────────────────────────────

PATCHED_URL  = "https://www.longpaddock.qld.gov.au/cgi-bin/silo/PatchedPointDataset.php"
DATADRILL_URL = "https://www.longpaddock.qld.gov.au/cgi-bin/silo/DataDrillDataset.php"

# Fixed email — SILO requires a username but doesn't validate it
SILO_EMAIL = "a@b.com"

# Full variable set for DataDrill (Howwet needs all of these)
DATADRILL_VARIABLES = "daily_rain,max_temp,min_temp,evap_pan,rh_tmax,rh_tmin,radiation"

# Browser-like headers required by SILO's WAF
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/plain, text/csv, */*",
    "Referer": "https://www.longpaddock.qld.gov.au/silo/",
}


# ── Station search ────────────────────────────────────────────────────────────

def search_stations(query: str, max_results: int = 20) -> list[dict]:
    """
    Search SILO Patched Point station list by name fragment.

    Parameters
    ----------
    query       : partial station name (e.g. 'Roma', 'Cairns')
    max_results : cap on returned stations

    Returns
    -------
    List of dicts:
        id    : int    SILO station number
        name  : str    station name
        label : str    display label with state and coordinates
        lat   : float  latitude (negative = south)
        lon   : float  longitude
        state : str    state abbreviation
    """
    url = (
        f"{PATCHED_URL}"
        f"?format=name"
        f"&nameFrag={urllib.parse.quote(query)}"
        f"&username={urllib.parse.quote(SILO_EMAIL)}"
    )

    try:
        req = urllib.request.Request(url, headers=_HEADERS)
        ctx = ssl.create_default_context()
        with urllib.request.urlopen(req, context=ctx, timeout=15) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
    except Exception as e:
        raise ConnectionError(f"SILO station search failed: {e}") from e

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
            name  = parts[1]
            lat   = float(parts[2]) if len(parts) > 2 and parts[2] else None
            lon   = float(parts[3]) if len(parts) > 3 and parts[3] else None
            state = parts[4] if len(parts) > 4 else ""

            # Validate Australian coordinates
            if lat is not None and lon is not None:
                if not (-45 < lat < -10 and 110 < lon < 155):
                    continue

            label = name
            if state:
                label += f"  [{state}]"
            if lat is not None and lon is not None:
                label += f"  ({lat:.3f}, {lon:.3f})"

            stations.append({
                "id"   : sid,
                "name" : name,
                "label": label,
                "lat"  : lat,
                "lon"  : lon,
                "state": state,
            })

            if len(stations) >= max_results:
                break

        except (ValueError, IndexError):
            continue

    return stations


# ── Patched Point fetch (Season + Odds) ──────────────────────────────────────

def fetch_patched_point(
    station_id: int,
    start: str,
    end: str,
    variables: str = "R",
) -> pd.DataFrame:
    """
    Fetch daily data from SILO Patched Point Dataset by station number.

    Parameters
    ----------
    station_id : SILO station number
    start      : start date YYYYMMDD
    end        : end date YYYYMMDD
    variables  : SILO comment codes — 'R' = rainfall only (default)
                 Use 'daily_rain,max_temp,...' for full met variables.

    Returns
    -------
    pd.DataFrame indexed by date with columns:
        rain, year, month, day, doy
        (plus tmax, tmin etc. if requested via variables)
    """
    url = (
        f"{PATCHED_URL}"
        f"?station={station_id}"
        f"&start={start}&finish={end}"
        f"&format=csv&comment={urllib.parse.quote(variables)}"
        f"&username={urllib.parse.quote(SILO_EMAIL)}"
    )

    try:
        req = urllib.request.Request(url, headers=_HEADERS)
        ctx = ssl.create_default_context()
        with urllib.request.urlopen(req, context=ctx, timeout=60) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
    except Exception as e:
        raise ConnectionError(f"SILO patched-point fetch failed: {e}") from e

    return _parse_silo_csv(raw, source="patched_point")


# ── DataDrill fetch (Howwet) ──────────────────────────────────────────────────

def fetch_datadrill(
    lat: float,
    lon: float,
    start: str,
    end: str,
    email: str = SILO_EMAIL,
    variables: str = DATADRILL_VARIABLES,
    cache_path: str = None,
) -> pd.DataFrame:
    """
    Fetch daily gridded data from SILO DataDrill by lat/lon.

    Parameters
    ----------
    lat        : latitude (negative = south)
    lon        : longitude
    start      : start date YYYYMMDD
    end        : end date YYYYMMDD
    email      : username for SILO API (any valid-looking email)
    variables  : comma-separated SILO variable codes
    cache_path : optional path to cache CSV locally

    Returns
    -------
    pd.DataFrame indexed by date with columns:
        rain, tmax, tmin, tmean, epan, radiation, rhmax, rhmin,
        year, month, day, doy
    """
    import pathlib

    # Check cache
    if cache_path and pathlib.Path(cache_path).exists():
        df = pd.read_csv(cache_path, index_col="date", parse_dates=True)
        return df

    params = {
        "lat"     : lat,
        "lon"     : lon,
        "start"   : start,
        "finish"  : end,
        "format"  : "csv",
        "comment" : variables,
        "username": email,
        "password": "apirequest",
    }

    try:
        resp = requests.get(
            DATADRILL_URL, params=params,
            headers=_HEADERS, timeout=120
        )
        resp.raise_for_status()
        raw = resp.text
    except Exception as e:
        raise ConnectionError(
            f"SILO DataDrill fetch failed: {e}\n"
            "Check your internet connection or try again in a few minutes.\n"
            "If the problem persists, download data manually from "
            "https://www.longpaddock.qld.gov.au/silo/"
        ) from e

    df = _parse_silo_csv(raw, source="datadrill")

    # Estimate pan evaporation from radiation if missing
    df = _fill_epan(df)

    # Cache to disk
    if cache_path:
        import pathlib as _pl
        _pl.Path(cache_path).parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(cache_path)

    return df


# ── Shared CSV parser ─────────────────────────────────────────────────────────

def _parse_silo_csv(raw: str, source: str = "unknown") -> pd.DataFrame:
    """
    Parse raw SILO CSV text into a standardised DataFrame.

    Handles all four SILO response formats:
      1. Patched point — 'date' column as YYYYMMDD integer, comma-separated
      2. Patched point — whitespace-separated (older format)
      3. DataDrill old — 'date' column as YYYYMMDD integer
      4. DataDrill new — 'yyyy-mm-dd' or 'latitude,longitude,...' header

    All outputs have the same column names regardless of source.
    """
    lines = raw.splitlines()

    if not lines:
        raise ValueError("SILO returned an empty response.")

    # Check for WAF rejection
    raw_lower = raw.lower()
    if "rejected" in raw_lower or "support id" in raw_lower or "blocked" in raw_lower:
        raise ConnectionError(
            "SILO request was blocked by the server firewall.\n"
            "Try again in a few minutes, or from a different network."
        )

    # Find header line — handles all known SILO formats:
    #   Old patched point : "date,daily_rain,..."         date=YYYYMMDD integer
    #   New patched point : "station,YYYY-MM-DD,..."      date=ISO string
    #   DataDrill old     : "date,daily_rain,..."         date=YYYYMMDD integer
    #   DataDrill new     : "latitude,longitude,YYYY-MM-DD,..."
    header_idx = None
    date_col   = None
    date_fmt   = None

    for i, line in enumerate(lines):
        low = line.strip().lower()
        if not low or low.startswith("#"):
            continue
        if low.startswith("station,yyyy") or low.startswith("station,20") or low.startswith("station,19") or low.startswith("station,18"):
            # New patched point format: station,YYYY-MM-DD,daily_rain,...
            header_idx = i
            date_col   = "yyyy-mm-dd"
            date_fmt   = "%Y-%m-%d"
            break
        if low.startswith("date"):
            header_idx = i
            date_col   = "date"
            date_fmt   = "%Y%m%d"
            break
        if low.startswith("latitude") or low.startswith("yyyy"):
            header_idx = i
            date_col   = "yyyy-mm-dd"
            date_fmt   = "%Y-%m-%d"
            break
        # Whitespace-separated patched point: first token looks like YYYYMMDD
        if len(low.split()) >= 5:
            try:
                candidate = int(low.split()[0])
                if 18800101 <= candidate <= 21001231:
                    header_idx = i
                    date_col   = None
                    break
            except ValueError:
                pass

    if header_idx is None:
        preview = raw[:400].replace("\n", " | ")
        raise ValueError(
            f"Could not parse SILO response from {source}.\n"
            f"First 400 chars: {preview}"
        )

    # ── Whitespace-separated path (older patched-point format) ────────────
    if date_col is None:
        # Look for a header line just before the data
        # Typical header: "Date  DOY  Rain  ..."
        for j in range(max(0, header_idx - 5), header_idx):
            low_j = lines[j].strip().lower()
            if "date" in low_j and ("rain" in low_j or "doy" in low_j):
                col_names = lines[j].strip().lower().split()
                data_lines = [l for l in lines[header_idx:]
                              if l.strip() and not l.strip().startswith("#")]
                raw_df = pd.read_csv(
                    io.StringIO("\n".join(data_lines)),
                    sep=r"\s+", names=col_names, header=None,
                )
                raw_df.columns = [c.strip().lower() for c in raw_df.columns]
                df_index = pd.to_datetime(
                    raw_df["date"].astype(str), format="%Y%m%d", errors="coerce"
                )
                return _build_standard_df(raw_df, df_index)

        # No recognisable header — try treating first data line as clue
        data_lines = [l for l in lines[header_idx:]
                      if l.strip() and not l.strip().startswith("#")]
        guessed_cols = ["date", "doy", "rain"]
        raw_df = pd.read_csv(
            io.StringIO("\n".join(data_lines)),
            sep=r"\s+", names=guessed_cols, header=None,
        )
        df_index = pd.to_datetime(
            raw_df["date"].astype(str), format="%Y%m%d", errors="coerce"
        )
        return _build_standard_df(raw_df, df_index)

    # ── CSV path ──────────────────────────────────────────────────────────
    csv_text = "\n".join(lines[header_idx:])
    raw_df   = pd.read_csv(io.StringIO(csv_text))
    raw_df.columns = [c.strip().lower().split("(")[0].strip() for c in raw_df.columns]

    # New patched point format has 'station' + 'yyyy-mm-dd' columns
    # Rename 'yyyy-mm-dd' to a known key if present
    if "yyyy-mm-dd" in raw_df.columns:
        date_col = "yyyy-mm-dd"
        date_fmt = "%Y-%m-%d"

    # Resolve date column
    if date_col and date_col in raw_df.columns:
        df_index = pd.to_datetime(
            raw_df[date_col].astype(str), format=date_fmt, errors="coerce"
        )
    elif "yyyy-mm-dd" in raw_df.columns:
        df_index = pd.to_datetime(raw_df["yyyy-mm-dd"], errors="coerce")
    else:
        candidates = [c for c in raw_df.columns if "date" in c or "yyyy" in c]
        if not candidates:
            raise ValueError(
                f"No date column found. Columns: {list(raw_df.columns)}"
            )
        df_index = pd.to_datetime(raw_df[candidates[0]].astype(str), errors="coerce")

    return _build_standard_df(raw_df, df_index)


def _build_standard_df(raw_df: pd.DataFrame, df_index: pd.DatetimeIndex) -> pd.DataFrame:
    """
    Map raw SILO column names to standard internal names and
    return a clean DataFrame indexed by date.
    """
    df = pd.DataFrame(index=df_index)
    df.index.name = "date"
    df = df[df.index.notna()]   # drop any unparseable dates

    df["year"]  = df.index.year
    df["month"] = df.index.month
    df["day"]   = df.index.day
    df["doy"]   = df.index.day_of_year

    # Column name map — handles both old and new SILO naming conventions
    col_map = {
        # rainfall
        "daily_rain"          : "rain",
        "rain"                : "rain",
        # temperature
        "max_temp"            : "tmax",
        "maximum_temperature" : "tmax",
        "tmax"                : "tmax",
        "min_temp"            : "tmin",
        "minimum_temperature" : "tmin",
        "tmin"                : "tmin",
        # pan evaporation
        "evap_pan"            : "epan",
        "evaporation"         : "epan",
        "evap"                : "epan",
        # radiation
        "radiation"           : "radiation",
        "solar_radiation"     : "radiation",
        "rad"                 : "radiation",
        # relative humidity
        "rh_tmax"             : "rhmax",
        "rh_tmin"             : "rhmin",
        "rhmax"               : "rhmax",
        "rhmin"               : "rhmin",
        # vapour pressure
        "vp"                  : "vp",
        "vapour_pressure"     : "vp",
    }

    for src_col, dst_col in col_map.items():
        if src_col in raw_df.columns and dst_col not in df.columns:
            vals = raw_df[src_col].values[: len(df)]
            df[dst_col] = pd.to_numeric(vals, errors="coerce")

    # Derived columns
    if "tmax" in df.columns and "tmin" in df.columns:
        df["tmean"] = (df["tmax"] + df["tmin"]) / 2.0

    # Clean negatives and fill missing rain
    if "rain" in df.columns:
        df["rain"] = df["rain"].fillna(0.0).clip(lower=0.0)

    return df.sort_index()


def _fill_epan(df: pd.DataFrame) -> pd.DataFrame:
    """
    Estimate pan evaporation from radiation + temperature if SILO
    didn't return it (some DataDrill calls omit evap_pan).
    Uses a simple empirical approximation suitable for Queensland:
        epan ≈ radiation * 0.50 + tmean * 0.06   (mm/day)
    """
    if "epan" not in df.columns or df["epan"].fillna(0).sum() < 1.0:
        if "radiation" in df.columns:
            rs    = df["radiation"].fillna(df["radiation"].median())
            tmean = df.get("tmean", pd.Series(25.0, index=df.index)).fillna(25.0)
            df["epan"] = (rs * 0.50 + tmean * 0.06).clip(lower=0.5)
        else:
            df["epan"] = 4.0   # fallback constant
    return df


# ── WAF-robust multi-variable fetch (Howwet) ─────────────────────────────────

def fetch_datadrill_robust(
    lat: float,
    lon: float,
    start: str,
    end: str,
    email: str = SILO_EMAIL,
) -> pd.DataFrame:
    """
    Fetch full met variables from SILO DataDrill, working around the WAF
    that sometimes blocks multi-variable requests from server-side code.

    Strategy:
      1. Try all variables in one request (fast path)
      2. If that fails or returns incomplete data, fetch each variable
         separately and merge (slow but reliable)

    Always returns a DataFrame with at minimum:
      rain, epan, tmax, tmin, tmean, radiation, year, month, day, doy

    The temperature columns (tmax, tmin, tmean) are included even if the
    caller only needs rain today — so adding temperature-based features
    later requires no changes to the fetch call.
    """
    variables = [
        "daily_rain",
        "evap_pan",
        "max_temp",
        "min_temp",
        "radiation",
    ]

    # ── Fast path: all variables in one request ───────────────────────────
    try:
        df = fetch_datadrill(
            lat, lon, start, end, email,
            variables=",".join(variables),
        )
        # Check we got the key columns
        if "rain" in df.columns and df["rain"].sum() >= 0:
            df = _fill_epan(df)
            return df
    except Exception:
        pass  # fall through to per-variable fetch

    # ── Slow path: one variable at a time ─────────────────────────────────
    frames = {}
    for var in variables:
        try:
            frames[var] = fetch_datadrill(
                lat, lon, start, end, email, variables=var
            )
        except Exception:
            pass

    if "daily_rain" not in frames:
        raise ConnectionError(
            "Could not fetch rainfall from SILO. "
            "Check your internet connection and try again."
        )

    df = frames["daily_rain"].copy()

    # Merge other variables in by date index
    col_map = {
        "evap_pan"  : "epan",
        "max_temp"  : "tmax",
        "min_temp"  : "tmin",
        "radiation" : "radiation",
    }
    for var, col in col_map.items():
        if var in frames and col in frames[var].columns:
            df[col] = frames[var][col].reindex(df.index)

    # Derived columns
    if "tmax" in df.columns and "tmin" in df.columns:
        df["tmean"] = (df["tmax"] + df["tmin"]) / 2.0

    df = _fill_epan(df)
    return df


# ── Convenience: rainfall-only DataFrame (Season + Odds) ─────────────────────

def fetch_station_rainfall(station_id: int, start: str, end: str) -> pd.DataFrame:
    """
    Fetch rainfall only from a patched-point station.
    Used by Season and Odds pages.
    """
    df = fetch_patched_point(station_id, start, end, variables="R")
    return df[["year", "month", "day", "rain"]].copy()


# ── Convenience: full met DataFrame (Howwet) ─────────────────────────────────

def fetch_station_met(station_id: int, start: str, end: str) -> pd.DataFrame:
    """
    Fetch full daily met from a patched-point station using P51 variables.
    Returns DataFrame with: rain, epan, tmax, tmin, tmean, radiation, vp,
                            year, month, day, doy.
    Used by Howwet — same station-search flow as Season and Odds.
    Falls back to radiation-based epan estimate if station has no pan evap.
    """
    variables = "daily_rain,evap_pan,max_temp,min_temp,radiation,vp"
    df = fetch_patched_point(station_id, start, end, variables=variables)
    df = _fill_epan(df)
    return df


# ── Standalone test ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=== Station search: Roma ===")
    stations = search_stations("Roma")
    for s in stations[:5]:
        print(f"  {s['id']:6d}  {s['name']:<35}  {s['state']}")

    if stations:
        sid = stations[0]["id"]
        print(f"\n=== Patched point rainfall: station {sid} (last 2 years) ===")
        df = fetch_station_rainfall(sid, "20230101", "20241231")
        print(f"  {len(df)} days  rain total: {df['rain'].sum():.0f} mm")
        print(df.tail())

    print("\n=== DataDrill: Dalby QLD (3 days) ===")
    df2 = fetch_datadrill(-27.28, 151.26, "20260101", "20260103")
    print(df2[["rain", "tmax", "tmin", "epan", "radiation"]])
