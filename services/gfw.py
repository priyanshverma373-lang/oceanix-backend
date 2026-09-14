# -*- coding: utf-8 -*-
"""
OCEANIX — Global Fishing Watch (GFW) Provider
Implements AIS/vessel data queries via the Global Fishing Watch API v3.

Requires environment variable:
    GFW_API_TOKEN    (JWT token from GFW dashboard)

API docs: https://globalfishingwatch.org/our-apis/documentation/
"""

import os
import logging
import httpx
from datetime import datetime
from typing import List, Dict, Any, Optional
from .providers import AISProvider

logger = logging.getLogger("oceanix.gfw")

GFW_API_BASE = "https://gateway.api.globalfishingwatch.org/v3"


class GlobalFishingWatchProvider(AISProvider):
    """
    AIS tracking data via Global Fishing Watch API v3.

    Requires environment variable:
        GFW_API_TOKEN
    """

    def __init__(self):
        self.api_token = os.getenv("GFW_API_TOKEN")

    def _auth_headers(self) -> Dict[str, str]:
        if not self.api_token:
            raise RuntimeError(
                "GFW_API_TOKEN is not set. "
                "Register at https://globalfishingwatch.org/our-apis/"
            )
        return {
            "Authorization": f"Bearer {self.api_token}",
            "Content-Type":  "application/json",
        }

    # ── AISProvider interface ─────────────────────────────────────────────────

    def get_vessel_info(self, query: str) -> Optional[Dict[str, Any]]:
        """
        Search for a vessel by MMSI, IMO, or name via the GFW Vessels API.
        Returns normalised vessel dict or None.
        """
        logger.info("GFW vessel search: %r", query)
        try:
            resp = httpx.get(
                f"{GFW_API_BASE}/vessels/search",
                params={
                    "query":      query,
                    "limit":      5,
                    "datasets[]": "public-global-fishing-vessels:latest",
                },
                headers=self._auth_headers(),
                timeout=15,
            )
        except httpx.ConnectError as e:
            raise RuntimeError(f"Cannot connect to GFW API: {e}") from e

        if resp.status_code == 401:
            raise RuntimeError("GFW API returned 401 — check GFW_API_TOKEN")
        if resp.status_code == 403:
            raise RuntimeError(
                "GFW API returned 403 — your token does not have access to this endpoint"
            )
        if resp.status_code == 404:
            return None

        resp.raise_for_status()

        entries = resp.json().get("entries", [])
        if not entries:
            logger.info("GFW: no results for %r", query)
            return None

        # Prefer best match
        vessel = entries[0]
        logger.info("GFW returned vessel: %s", vessel.get("shipname", "unknown"))
        return self._normalise_vessel(vessel)

    def get_vessel_track(
        self,
        mmsi: str,
        start_time: datetime,
        end_time: datetime,
    ) -> List[Dict[str, Any]]:
        """
        Retrieve AIS track positions for a vessel within a time range.
        Uses GFW Events API (port visits, fishing events, track points).

        Note: Full track data often requires enterprise access.
        Returns empty list if not accessible.
        """
        logger.info("GFW vessel track requested for MMSI %s", mmsi)
        # First get the internal GFW vessel ID for the MMSI
        vessel_info = self.get_vessel_info(mmsi)
        if not vessel_info or not vessel_info.get("gfw_id"):
            logger.warning("GFW: no vessel found for MMSI %s to get track", mmsi)
            return []

        gfw_id = vessel_info["gfw_id"]
        try:
            resp = httpx.get(
                f"{GFW_API_BASE}/vessels/{gfw_id}/tracks",
                params={
                    "startDate": start_time.strftime("%Y-%m-%d"),
                    "endDate":   end_time.strftime("%Y-%m-%d"),
                    "datasets[]": "public-global-fishing-vessels:latest",
                },
                headers=self._auth_headers(),
                timeout=30,
            )
            if resp.status_code in (403, 404):
                logger.warning("GFW track not accessible for vessel %s (status %d)", gfw_id, resp.status_code)
                return []
            resp.raise_for_status()
            raw = resp.json()
            # GFW returns GeoJSON LineString; extract as list of position dicts
            coords = raw.get("features", [{}])[0].get("geometry", {}).get("coordinates", [])
            times  = raw.get("features", [{}])[0].get("properties", {}).get("times", [])
            return [
                {"lon": c[0], "lat": c[1], "timestamp": t}
                for c, t in zip(coords, times)
            ]
        except Exception as exc:
            logger.warning("GFW track query failed: %s", exc)
            return []

    def search_vessels_in_area(
        self,
        bbox: List[float],
        start_time: datetime,
        end_time: datetime,
    ) -> List[Dict[str, Any]]:
        """
        Find vessels that were active in a bounding box during a time window.

        Uses GFW Events API to find fishing events, port visits, or encounters.
        This endpoint typically requires registration-level access (free tier
        may return limited results or require BigQuery for historical data).
        """
        logger.info("GFW area search: bbox=%s %s→%s", bbox, start_time, end_time)
        min_lon, min_lat, max_lon, max_lat = bbox
        try:
            # Use GFW /events endpoint with geometry filter
            resp = httpx.post(
                f"{GFW_API_BASE}/events",
                json={
                    "datasets": ["public-global-fishing-events:latest"],
                    "startDate": start_time.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "endDate":   end_time.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "geometry": {
                        "type": "Polygon",
                        "coordinates": [[
                            [min_lon, min_lat], [max_lon, min_lat],
                            [max_lon, max_lat], [min_lon, max_lat],
                            [min_lon, min_lat]
                        ]],
                    },
                    "limit": 50,
                },
                headers=self._auth_headers(),
                timeout=30,
            )
            if resp.status_code in (403, 404, 422):
                logger.warning(
                    "GFW events API returned %d — may require higher-tier access", resp.status_code
                )
                return []
            resp.raise_for_status()
            events = resp.json().get("entries", [])
            # Deduplicate by vessel
            seen = set()
            vessels = []
            for ev in events:
                vessel = ev.get("vessel", {})
                vid = vessel.get("id")
                if vid and vid not in seen:
                    seen.add(vid)
                    vessels.append(self._normalise_vessel(vessel))
            logger.info("GFW events returned %d unique vessels in area", len(vessels))
            return vessels
        except Exception as exc:
            logger.warning("GFW area search failed: %s", exc)
            return []

    # ── Normalization ────────────────────────────────────────────────────────

    def _normalise_vessel(self, raw: Dict) -> Dict[str, Any]:
        """Map GFW vessel dict to OCEANIX schema."""
        return {
            "gfw_id":        raw.get("id"),
            "mmsi":          raw.get("mmsi") or raw.get("ssvid"),
            "imo":           raw.get("imo"),
            "name":          raw.get("shipname") or raw.get("name") or "Unknown",
            "vessel_type":   raw.get("vesselType") or raw.get("gearType"),
            "flag":          raw.get("flag"),
            "source_provider": "Global Fishing Watch",
            "data_mode":     "LIVE",
        }
