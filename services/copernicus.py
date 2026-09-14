# -*- coding: utf-8 -*-
"""
OCEANIX — Copernicus Data Space Provider
Implements the SatelliteDataProvider interface using the
Copernicus Data Space Ecosystem OData API.

Authentication:
  Uses username + password (Resource Owner Password Credentials) since
  client_credentials requires a separately registered OAuth application.
  Set in .env:
    COPERNICUS_USERNAME=your_email@example.com
    COPERNICUS_PASSWORD=your_password

Registration: https://dataspace.copernicus.eu/
Auth docs:    https://documentation.dataspace.copernicus.eu/APIs/Token.html
OData docs:   https://documentation.dataspace.copernicus.eu/APIs/OData.html
"""

import os
import logging
import httpx
from datetime import datetime
from typing import List, Dict, Any, Optional
from .providers import SatelliteDataProvider

logger = logging.getLogger("oceanix.copernicus")

TOKEN_URL     = (
    "https://identity.dataspace.copernicus.eu"
    "/auth/realms/CDSE/protocol/openid-connect/token"
)
CATALOGUE_URL = "https://catalogue.dataspace.copernicus.eu/odata/v1"
DOWNLOAD_URL  = "https://zipper.dataspace.copernicus.eu/zip"


class CopernicusProvider(SatelliteDataProvider):
    """
    Live Sentinel-1 data via Copernicus Data Space Ecosystem.

    Requires environment variables:
        COPERNICUS_USERNAME    (your CDSE account email)
        COPERNICUS_PASSWORD    (your CDSE account password)
    """

    def __init__(self):
        self.username  = os.getenv("COPERNICUS_USERNAME")
        self.password  = os.getenv("COPERNICUS_PASSWORD")
        self._token: Optional[str] = None

    # ── Auth ────────────────────────────────────────────────────────────────
    def _get_token(self) -> str:
        """
        Obtain a short-lived OAuth2 access token using Resource Owner
        Password Credentials (username + password).
        """
        if not self.username or not self.password:
            raise RuntimeError(
                "COPERNICUS_USERNAME / COPERNICUS_PASSWORD not set. "
                "Register at https://dataspace.copernicus.eu/ and set these in .env"
            )
        logger.debug("Requesting Copernicus auth token for user %s", self.username)
        resp = httpx.post(
            TOKEN_URL,
            data={
                "grant_type": "password",
                "client_id":  "cdse-public",
                "username":   self.username,
                "password":   self.password,
            },
            timeout=20,
        )
        if resp.status_code == 401:
            raise RuntimeError(
                "Copernicus authentication failed — check COPERNICUS_USERNAME and COPERNICUS_PASSWORD"
            )
        resp.raise_for_status()
        token = resp.json().get("access_token")
        if not token:
            raise RuntimeError("Copernicus token response missing access_token field")
        logger.info("Copernicus token obtained successfully")
        return token

    def _auth_headers(self) -> Dict[str, str]:
        self._token = self._get_token()
        return {"Authorization": f"Bearer {self._token}"}

    # ── SatelliteDataProvider interface ─────────────────────────────────────
    def search_scenes(
        self,
        bbox: List[float],            # [min_lon, min_lat, max_lon, max_lat]
        start_time: datetime,
        end_time:   datetime,
        platform:   str = "SENTINEL-1",
        product_type: str = "GRD",
        max_results:  int = 20,
    ) -> List[Dict[str, Any]]:
        """
        Query Copernicus OData catalogue for Sentinel-1 GRD scenes
        intersecting a bounding box within a time range.
        """
        min_lon, min_lat, max_lon, max_lat = bbox
        wkt = (
            f"POLYGON(({min_lon} {min_lat},{max_lon} {min_lat},"
            f"{max_lon} {max_lat},{min_lon} {max_lat},{min_lon} {min_lat}))"
        )
        start_str = start_time.strftime("%Y-%m-%dT%H:%M:%SZ")
        end_str   = end_time.strftime("%Y-%m-%dT%H:%M:%SZ")

        odata_filter = (
            f"Collection/Name eq '{platform}' and "
            f"Attributes/OData.CSC.StringAttribute/any(att:"
            f"att/Name eq 'productType' and "
            f"att/OData.CSC.StringAttribute/Value eq '{product_type}') and "
            f"ContentDate/Start gt {start_str} and "
            f"ContentDate/Start lt {end_str} and "
            f"OData.CSC.Intersects(area=geography'SRID=4326;{wkt}')"
        )
        params = {
            "$filter":  odata_filter,
            "$top":     max_results,
            "$orderby": "ContentDate/Start desc",
            "$expand":  "Attributes",
        }
        logger.info(
            "Querying Copernicus catalog: bbox=%s, %s → %s", bbox, start_str, end_str
        )
        resp = httpx.get(
            f"{CATALOGUE_URL}/Products",
            params=params,
            headers=self._auth_headers(),
            timeout=30,
        )
        resp.raise_for_status()
        raw = resp.json().get("value", [])
        logger.info("Copernicus catalog returned %d raw results", len(raw))
        return [self._normalise_scene(s) for s in raw]

    def get_scene_metadata(self, scene_id: str) -> Dict[str, Any]:
        resp = httpx.get(
            f"{CATALOGUE_URL}/Products('{scene_id}')",
            params={"$expand": "Attributes"},
            headers=self._auth_headers(),
            timeout=15,
        )
        resp.raise_for_status()
        return self._normalise_scene(resp.json())

    def download_scene(self, scene_id: str, output_dir: str) -> str:
        """
        Download the zipped scene product from the Copernicus zipper service.
        Returns the path to the downloaded zip file.
        Note: Large files (800 MB+) — use only when necessary.
        """
        import pathlib
        headers = self._auth_headers()
        url = f"{DOWNLOAD_URL}?id={scene_id}"
        out_path = pathlib.Path(output_dir) / f"{scene_id}.zip"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        logger.info("Downloading Copernicus scene %s → %s", scene_id, out_path)
        with httpx.stream("GET", url, headers=headers, timeout=600, follow_redirects=True) as r:
            r.raise_for_status()
            with open(out_path, "wb") as f:
                for chunk in r.iter_bytes(chunk_size=65536):
                    f.write(chunk)
        logger.info("Download complete: %s", out_path)
        return str(out_path)

    # ── Helper ──────────────────────────────────────────────────────────────
    def _normalise_scene(self, raw: Dict) -> Dict[str, Any]:
        """Normalise Copernicus OData response to OCEANIX schema."""
        attrs: Dict[str, Any] = {}
        for a in raw.get("Attributes", []):
            attrs[a["Name"]] = a.get("Value") or a.get("OData.CSC.StringAttribute", {}).get("Value")
        return {
            "scene_id":         raw.get("Id"),
            "name":             raw.get("Name"),
            "platform":         attrs.get("platformShortName", "Sentinel-1"),
            "product_type":     attrs.get("productType", "GRD"),
            "polarization":     attrs.get("polarisationChannels"),
            "orbit_direction":  attrs.get("orbitDirection"),
            "acquisition_time": raw.get("ContentDate", {}).get("Start"),
            "size_mb":          round((raw.get("ContentLength") or 0) / 1e6, 1),
            "source_provider":  "Copernicus Data Space",
            "data_mode":        "LIVE",
            "download_url":     raw.get("S3Path"),
        }
