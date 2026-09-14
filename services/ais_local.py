# -*- coding: utf-8 -*-
"""
OCEANIX — Local AIS Dataset Provider
Queries the AISDK CSV dataset (aisdk-2026-09-03.zip) as a fast fallback
when the GFW API is unavailable or rate-limited.

Danish Maritime Authority AIS data format:
  Columns: # Timestamp,Type of mobile,MMSI,Latitude,Longitude,
            Navigational status,ROT,SOG,COG,Heading,IMO,
            Callsign,Name,Ship type,Cargo type,Width,Length,
            Type of position fixing device,Draught,Destination,ETA,
            Data source type,A,B,C,D

Dataset: http://aisdata.ais.dk/aisdk-2026-09-03.zip
"""

import os
import io
import zipfile
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Dict, Any, Optional

logger = logging.getLogger("oceanix.ais_local")

# Columns in the AISDK CSV
AISDK_TIMESTAMP_COL  = "# Timestamp"
AISDK_MMSI_COL       = "MMSI"
AISDK_LAT_COL        = "Latitude"
AISDK_LON_COL        = "Longitude"
AISDK_NAME_COL       = "Name"
AISDK_SHIP_TYPE_COL  = "Ship type"
AISDK_SOG_COL        = "SOG"
AISDK_COG_COL        = "COG"
AISDK_IMO_COL        = "IMO"
AISDK_FLAG_COL       = None  # Not in AISDK format; will be None

# Max rows to read to avoid loading 500 MB into memory
MAX_ROWS = 200_000


class AISLocalProvider:
    """
    Reads the local AISDK CSV (possibly inside a .zip) and provides
    simple spatial + temporal filtering of vessel positions.
    """

    def __init__(self, csv_path: str):
        self.csv_path = csv_path
        self._df = None  # Lazy-loaded

    def _load_df(self):
        """Lazy-load the AIS CSV (up to MAX_ROWS) into a pandas DataFrame."""
        if self._df is not None:
            return self._df

        try:
            import pandas as pd
        except ImportError:
            raise RuntimeError("pandas is required for AIS CSV processing. pip install pandas")

        csv_path = Path(self.csv_path)
        logger.info("Loading AIS CSV from %s (up to %d rows)", csv_path, MAX_ROWS)

        if csv_path.suffix.lower() == ".zip":
            with zipfile.ZipFile(csv_path, "r") as zf:
                # Find first CSV file inside the zip
                csv_files = [f for f in zf.namelist() if f.lower().endswith(".csv")]
                if not csv_files:
                    raise RuntimeError(f"No CSV found in {csv_path}")
                with zf.open(csv_files[0]) as f:
                    df = pd.read_csv(f, nrows=MAX_ROWS, dtype=str)
        else:
            df = pd.read_csv(csv_path, nrows=MAX_ROWS, dtype=str)

        # Normalise column names (strip whitespace)
        df.columns = df.columns.str.strip()

        # Parse numeric columns
        for col in [AISDK_LAT_COL, AISDK_LON_COL, AISDK_SOG_COL, AISDK_COG_COL]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")

        # Parse timestamps
        ts_col = AISDK_TIMESTAMP_COL.lstrip("# ").strip()
        # Handle the awkward "# Timestamp" column name
        ts_candidates = [c for c in df.columns if "timestamp" in c.lower() or c == "#"]
        if ts_candidates:
            df["_parsed_ts"] = pd.to_datetime(df[ts_candidates[0]], errors="coerce", utc=True)
        else:
            df["_parsed_ts"] = None

        self._df = df
        logger.info("AIS CSV loaded: %d rows, columns: %s", len(df), list(df.columns[:10]))
        return self._df

    def search_vessels_in_area(
        self,
        bbox: List[float],
        start_time: datetime,
        end_time: datetime,
        max_vessels: int = 50,
    ) -> List[Dict[str, Any]]:
        """
        Filter AIS records to those within a bounding box and time window.
        Returns one representative record per unique MMSI.
        """
        df = self._load_df()
        min_lon, min_lat, max_lon, max_lat = bbox

        # Spatial filter
        mask = (
            df[AISDK_LAT_COL].notna() &
            df[AISDK_LON_COL].notna() &
            (df[AISDK_LAT_COL] >= min_lat) &
            (df[AISDK_LAT_COL] <= max_lat) &
            (df[AISDK_LON_COL] >= min_lon) &
            (df[AISDK_LON_COL] <= max_lon)
        )

        # Temporal filter (if timestamps are available)
        if "_parsed_ts" in df.columns and df["_parsed_ts"].notna().any():
            # Ensure tz-aware comparison
            st = start_time if start_time.tzinfo else start_time.replace(tzinfo=timezone.utc)
            et = end_time   if end_time.tzinfo   else end_time.replace(tzinfo=timezone.utc)
            mask &= (df["_parsed_ts"] >= st) & (df["_parsed_ts"] <= et)

        filtered = df[mask]
        if filtered.empty:
            logger.info("AIS CSV: no vessels found in bbox=%s within time window", bbox)
            return []

        # Deduplicate by MMSI — take the last known position
        if AISDK_MMSI_COL in filtered.columns:
            filtered = (
                filtered
                .dropna(subset=[AISDK_MMSI_COL])
                .sort_values("_parsed_ts", na_position="last")
                .groupby(AISDK_MMSI_COL)
                .last()
                .reset_index()
            )

        results = []
        for _, row in filtered.head(max_vessels).iterrows():
            results.append(self._normalise_row(row))

        logger.info("AIS CSV: returning %d vessels for area query", len(results))
        return results

    def get_stats(self) -> Dict[str, Any]:
        """Return basic statistics about the loaded AIS dataset."""
        df = self._load_df()
        stats: Dict[str, Any] = {
            "total_records": int(len(df)),
            "columns": list(df.columns),
        }
        if AISDK_MMSI_COL in df.columns:
            stats["unique_vessels"] = int(df[AISDK_MMSI_COL].nunique())
        if "_parsed_ts" in df.columns:
            ts = df["_parsed_ts"].dropna()
            if not ts.empty:
                stats["time_range_start"] = str(ts.min())
                stats["time_range_end"]   = str(ts.max())
        if AISDK_SHIP_TYPE_COL in df.columns:
            stats["top_ship_types"] = (
                df[AISDK_SHIP_TYPE_COL]
                .value_counts()
                .head(10)
                .to_dict()
            )
        return stats

    # ── Helper ─────────────────────────────────────────────────────────────

    def _normalise_row(self, row) -> Dict[str, Any]:
        """Convert a DataFrame row to the OCEANIX vessel schema."""
        def safe(col):
            try:
                val = row.get(col)
                return None if (val is None or str(val).strip() in ("", "nan", "NaN")) else str(val).strip()
            except Exception:
                return None

        lat = row.get(AISDK_LAT_COL)
        lon = row.get(AISDK_LON_COL)
        ts  = row.get("_parsed_ts")

        return {
            "mmsi":           safe(AISDK_MMSI_COL),
            "imo":            safe(AISDK_IMO_COL),
            "name":           safe(AISDK_NAME_COL) or "Unknown",
            "vessel_type":    safe(AISDK_SHIP_TYPE_COL),
            "flag":           None,  # Not in AISDK format
            "last_position":  {"lat": float(lat), "lon": float(lon)} if lat is not None and lon is not None else None,
            "speed_kts":      float(row[AISDK_SOG_COL]) if AISDK_SOG_COL in row and row[AISDK_SOG_COL] == row[AISDK_SOG_COL] else None,
            "course_deg":     float(row[AISDK_COG_COL]) if AISDK_COG_COL in row and row[AISDK_COG_COL] == row[AISDK_COG_COL] else None,
            "last_update":    ts.isoformat() if ts is not None and str(ts) != "NaT" else None,
            "source_provider": "AIS Denmark (aisdk)",
            "data_mode":      "LOCAL_AIS",
        }
