# -*- coding: utf-8 -*-
"""
OCEANIX — FastAPI Backend Entry Point
Provides all API endpoints for the OCEANIX Maritime Oil Spill Intelligence Platform.

Endpoints:
  GET  /api/system/status        - Health check for all services
  GET  /api/satellite/scenes     - Search Copernicus for Sentinel-1 scenes
  GET  /api/satellite/image      - Serve a satellite image (real or fallback)
  GET  /api/satellite/samples    - List fallback Kaggle sample images with metadata
  GET  /api/vessels/search       - GFW vessel lookup by MMSI or name
  GET  /api/vessels/area         - Vessels in a bounding box + time window (AIS CSV or GFW)
  GET  /api/ais/stats            - Statistics summary from the local AIS CSV dataset
"""

import os
import logging
import random
import json
from contextlib import asynccontextmanager
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, Any, List, Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("oceanix.api")

# ── Database ───────────────────────────────────────────────────
from database.connection import check_db_connection
from database.init_db import init_db

# ── Lifespan (startup / shutdown) ────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialise DB tables at startup; clean up engine on shutdown."""
    try:
        await init_db()
        logger.info("PostgreSQL tables initialised successfully.")
    except Exception as exc:
        logger.warning("DB initialisation failed at startup (running without DB): %s", exc)
    yield
    # Shutdown: dispose engine connection pool
    from database.connection import engine
    await engine.dispose()
    logger.info("Database engine disposed.")

# ── App ─────────────────────────────────────────────────────────────
app = FastAPI(
    title="OCEANIX API",
    description="Backend services for the OCEANIX Maritime Forensics Platform",
    version="1.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],        # In production, restrict to your frontend origin
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Static file serving (Kaggle/local satellite sample images) ────────────────
BASE_DIR = Path(__file__).parent
STATIC_DIR = BASE_DIR / "static"
STATIC_DIR.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# ── Operational mode ─────────────────────────────────────────────────────────
DATA_MODE = os.getenv("OCEANIX_DATA_MODE", "DEMO")


# ══════════════════════════════════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════════════════════════════════

def _satellite_sample_manifest() -> List[Dict[str, Any]]:
    """Return a list of known local Kaggle Sentinel-1 SAR sample image records."""
    samples_dir = BASE_DIR / "static" / "satellite_samples"
    if not samples_dir.exists():
        return []

    # Hard-coded metadata for the 5 Kaggle Class_1 (oil-spill-relevant) images
    # These are REFERENCE samples from a Kaggle dataset — NOT live satellite data.
    records = [
        {
            "sample_id": "KGL-S1-OIL-00001",
            "filename": "class_1_00001.jpg",
            "label": "Oil-Spill Class (Kaggle Dataset)",
            "polarization": "VV",
            "platform": "Sentinel-1",
            "product_type": "GRD",
            "acquisition_time": "2023-04-15T06:12:00Z",
            "scene_id": "S1A_IW_GRDH_KGL001",
            "aoi_description": "North Sea reference sample",
            "source": "Kaggle SAR Oil Spill Dataset",
            "data_mode": "DEMO_REFERENCE",
        },
        {
            "sample_id": "KGL-S1-OIL-00002",
            "filename": "class_1_00002.jpg",
            "label": "Oil-Spill Class (Kaggle Dataset)",
            "polarization": "VV",
            "platform": "Sentinel-1",
            "product_type": "GRD",
            "acquisition_time": "2023-06-22T04:30:00Z",
            "scene_id": "S1B_IW_GRDH_KGL002",
            "aoi_description": "Persian Gulf reference sample",
            "source": "Kaggle SAR Oil Spill Dataset",
            "data_mode": "DEMO_REFERENCE",
        },
        {
            "sample_id": "KGL-S1-OIL-00003",
            "filename": "class_1_00003.jpg",
            "label": "Oil-Spill Class (Kaggle Dataset)",
            "polarization": "VV/VH",
            "platform": "Sentinel-1",
            "product_type": "GRD",
            "acquisition_time": "2023-08-09T08:55:00Z",
            "scene_id": "S1A_IW_GRDH_KGL003",
            "aoi_description": "Bay of Bengal reference sample",
            "source": "Kaggle SAR Oil Spill Dataset",
            "data_mode": "DEMO_REFERENCE",
        },
        {
            "sample_id": "KGL-S1-OIL-00004",
            "filename": "class_1_00004.jpg",
            "label": "Oil-Spill Class (Kaggle Dataset)",
            "polarization": "VV",
            "platform": "Sentinel-1",
            "product_type": "GRD",
            "acquisition_time": "2023-11-03T02:18:00Z",
            "scene_id": "S1B_IW_GRDH_KGL004",
            "aoi_description": "Arabian Sea reference sample",
            "source": "Kaggle SAR Oil Spill Dataset",
            "data_mode": "DEMO_REFERENCE",
        },
        {
            "sample_id": "KGL-S1-OIL-00005",
            "filename": "class_1_00005.jpg",
            "label": "Oil-Spill Class (Kaggle Dataset)",
            "polarization": "VH",
            "platform": "Sentinel-1",
            "product_type": "GRD",
            "acquisition_time": "2024-01-17T09:40:00Z",
            "scene_id": "S1A_IW_GRDH_KGL005",
            "aoi_description": "Gulf of Oman reference sample",
            "source": "Kaggle SAR Oil Spill Dataset",
            "data_mode": "DEMO_REFERENCE",
        },
        {
            "sample_id": "KGL-S1-CLN-00001",
            "filename": "class_0_clean_00001.jpg",
            "label": "Clean Water / No Spill Class (Kaggle Dataset)",
            "polarization": "VV",
            "platform": "Sentinel-1",
            "product_type": "GRD",
            "acquisition_time": "2023-03-11T07:00:00Z",
            "scene_id": "S1A_IW_GRDH_KGL_CLN001",
            "aoi_description": "Indian Ocean clean-water reference",
            "source": "Kaggle SAR Oil Spill Dataset",
            "data_mode": "DEMO_REFERENCE",
        },
    ]
    # Only return records where the file actually exists
    return [r for r in records if (samples_dir / r["filename"]).exists()]


# ══════════════════════════════════════════════════════════════════════════════
# System Status
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/")
def read_root():
    return {"message": "OCEANIX API v1.1 is running", "docs": "/docs"}


@app.get("/api/system/status")
async def get_system_status() -> Dict[str, Any]:
    """
    Returns live health/connectivity status for all external services and internal models.
    Performs a real PostgreSQL query to determine database status.
    Checks environment variables without exposing their values.
    """
    has_copernicus = bool(
        os.getenv("COPERNICUS_USERNAME") and os.getenv("COPERNICUS_PASSWORD")
    )
    has_gfw = bool(os.getenv("GFW_API_TOKEN"))
    ais_csv = os.getenv("AIS_CSV_PATH", "")
    has_ais_csv = bool(ais_csv and (Path(ais_csv).exists() or ais_csv.lower().endswith(".zip")))
    samples_dir = BASE_DIR / "static" / "satellite_samples"
    sample_count = len(list(samples_dir.glob("*.jpg"))) if samples_dir.exists() else 0

    # ── Real PostgreSQL health check ────────────────────────────────
    db_ok, db_info = await check_db_connection()
    if db_ok:
        db_status_block = {
            "status": "READY",
            "note": db_info,
        }
    else:
        db_status_block = {
            "status": "NOT_CONNECTED",
            "note": f"PostgreSQL connection failed: {db_info}",
        }

    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "mode": DATA_MODE,
        "satellite_provider": {
            "name": "Copernicus Data Space (Sentinel-1)",
            "status": "READY" if has_copernicus else "NOT_CONFIGURED",
            "note": "Set COPERNICUS_USERNAME and COPERNICUS_PASSWORD in .env"
                    if not has_copernicus else "Credentials found — will query on demand",
        },
        "ais_provider": {
            "name": "Global Fishing Watch API v3",
            "status": "READY" if has_gfw else "NOT_CONFIGURED",
            "note": "GFW token found" if has_gfw else "Set GFW_API_TOKEN in .env",
        },
        "ais_local": {
            "name": "Local AIS CSV (aisdk)",
            "status": "AVAILABLE" if has_ais_csv else "NOT_CONFIGURED",
            "path": ais_csv if has_ais_csv else None,
        },
        "satellite_samples": {
            "name": "Kaggle SAR Reference Samples",
            "status": "AVAILABLE",
            "count": sample_count,
        },
        "model": {
            "name": "OilSpillNet-v0.1 (U-Net / DeepLabV3+)",
            "status": "NOT_CONNECTED",
            "note": "Trained weights/checkpoint missing. Running fallback synthetic DEMO mode.",
            "last_inference": None,
        },
        "database": db_status_block,
    }


# ══════════════════════════════════════════════════════════════════════════════
# Satellite — Copernicus Catalog
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/api/satellite/scenes")
def search_satellite_scenes(
    min_lon: float = Query(72.0, description="Bounding box minimum longitude"),
    min_lat: float = Query(8.0,  description="Bounding box minimum latitude"),
    max_lon: float = Query(81.0, description="Bounding box maximum longitude"),
    max_lat: float = Query(22.0, description="Bounding box maximum latitude"),
    days_back: int  = Query(7,   description="Look-back window in days", ge=1, le=90),
    max_results: int = Query(10, description="Maximum number of scenes to return", ge=1, le=50),
) -> Dict[str, Any]:
    """
    Query the Copernicus Data Space OData catalog for Sentinel-1 GRD scenes
    intersecting the given bounding box within the last `days_back` days.

    Falls back to a demo scene list if credentials are not configured or the
    API call fails.
    """
    has_copernicus = bool(
        os.getenv("COPERNICUS_USERNAME") and os.getenv("COPERNICUS_PASSWORD")
    )

    if has_copernicus:
        try:
            from services.copernicus import CopernicusProvider
            provider = CopernicusProvider()
            end_dt   = datetime.now(timezone.utc)
            start_dt = end_dt - timedelta(days=days_back)
            scenes   = provider.search_scenes(
                bbox=[min_lon, min_lat, max_lon, max_lat],
                start_time=start_dt,
                end_time=end_dt,
                max_results=max_results,
            )
            logger.info("Copernicus catalog returned %d scenes", len(scenes))
            return {"data_mode": "LIVE", "source": "Copernicus Data Space", "scenes": scenes}
        except Exception as exc:
            logger.warning("Copernicus catalog query failed: %s", exc)
            # Fall through to demo fallback

    # ── Demo fallback scene list ──────────────────────────────────────────────
    logger.info("Returning DEMO satellite scene list (Copernicus not configured or unavailable)")
    demo_scenes = [
        {
            "scene_id": "S1A_IW_GRDH_1SDV_20260903T054712_20260903T054737_055293_06C1E3",
            "name": "S1A_IW_GRDH_1SDV_20260903T054712",
            "platform": "Sentinel-1A",
            "product_type": "GRD",
            "polarization": "VV VH",
            "orbit_direction": "DESCENDING",
            "acquisition_time": "2026-09-03T05:47:12Z",
            "size_mb": 892.4,
            "source_provider": "Copernicus Data Space",
            "data_mode": "DEMO",
        },
        {
            "scene_id": "S1B_IW_GRDH_1SDV_20260902T112012_20260902T112037_031856_03B928",
            "name": "S1B_IW_GRDH_1SDV_20260902T112012",
            "platform": "Sentinel-1B",
            "product_type": "GRD",
            "polarization": "VV VH",
            "orbit_direction": "ASCENDING",
            "acquisition_time": "2026-09-02T11:20:12Z",
            "size_mb": 876.1,
            "source_provider": "Copernicus Data Space",
            "data_mode": "DEMO",
        },
        {
            "scene_id": "S1A_IW_GRDH_1SDV_20260901T041526_20260901T041551_055183_06BF11",
            "name": "S1A_IW_GRDH_1SDV_20260901T041526",
            "platform": "Sentinel-1A",
            "product_type": "GRD",
            "polarization": "VV VH",
            "orbit_direction": "DESCENDING",
            "acquisition_time": "2026-09-01T04:15:26Z",
            "size_mb": 904.7,
            "source_provider": "Copernicus Data Space",
            "data_mode": "DEMO",
        },
    ]
    return {"data_mode": "DEMO", "source": "Demo fallback (Copernicus not configured)", "scenes": demo_scenes}


# ══════════════════════════════════════════════════════════════════════════════
# Satellite — Sample / Fallback Image Serving
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/api/satellite/samples")
def list_satellite_samples() -> Dict[str, Any]:
    """
    Returns a list of local Sentinel-1 SAR reference images with metadata.
    These are Kaggle dataset samples, clearly labelled DEMO_REFERENCE.
    They are NOT live or real-time satellite data.
    """
    samples = _satellite_sample_manifest()
    for s in samples:
        s["url"] = f"/static/satellite_samples/{s['filename']}"
    return {
        "data_mode": "DEMO_REFERENCE",
        "source": "Kaggle SAR Oil Spill Dataset (Reference Samples)",
        "disclaimer": (
            "These images are reference samples from the Kaggle Sentinel-1 SAR dataset. "
            "They are NOT live or current satellite imagery. "
            "When the Copernicus Processing API is available, real imagery will be served instead."
        ),
        "samples": samples,
    }


@app.get("/api/satellite/image")
def get_satellite_image(
    scene_id: Optional[str] = Query(None, description="Copernicus scene ID to fetch (real pipeline)"),
    sample_id: Optional[str] = Query(None, description="Kaggle sample ID for fallback"),
) -> Dict[str, Any]:
    """
    Returns image metadata and a URL for displaying a Sentinel-1 SAR image.

    Priority:
    1. If `scene_id` is provided and Copernicus credentials exist → try real API.
    2. If that fails, or `sample_id` is provided → return the matching fallback sample.
    3. If neither → return a random fallback from Class_1 (oil-spill class).
    """
    samples = _satellite_sample_manifest()

    # Try real Copernicus download (only when explicitly requested and configured)
    if scene_id and os.getenv("COPERNICUS_USERNAME"):
        logger.info("Copernicus download for scene %s requested but not yet implemented in image pipeline", scene_id)
        # Future: call provider.download_scene() + rasterio preprocessing + serve PNG
        # For now fall through to sample

    # Return specific sample if requested
    if sample_id:
        match = next((s for s in samples if s["sample_id"] == sample_id), None)
        if match:
            match["url"] = f"/static/satellite_samples/{match['filename']}"
            return {"data_mode": "DEMO_REFERENCE", "image": match}
        raise HTTPException(status_code=404, detail=f"Sample {sample_id!r} not found")

    # Random oil-spill-class fallback
    oil_samples = [s for s in samples if "class_1" in s["filename"].lower()]
    if not oil_samples:
        raise HTTPException(status_code=503, detail="No satellite samples available")
    chosen = random.choice(oil_samples)
    chosen["url"] = f"/static/satellite_samples/{chosen['filename']}"
    return {"data_mode": "DEMO_REFERENCE", "image": chosen}


# ══════════════════════════════════════════════════════════════════════════════
# Vessels — Global Fishing Watch
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/api/vessels/search")
def search_vessel(
    query: str = Query(..., description="MMSI, IMO, or vessel name to search"),
) -> Dict[str, Any]:
    """
    Search GFW for vessel information by MMSI, IMO, or name.
    Falls back to demo vessels if GFW is unavailable.
    """
    has_gfw = bool(os.getenv("GFW_API_TOKEN"))

    if has_gfw:
        try:
            from services.gfw import GlobalFishingWatchProvider
            provider = GlobalFishingWatchProvider()
            # Use MMSI search if query looks numeric, else name search
            result = provider.get_vessel_info(query)
            if result:
                logger.info("GFW returned vessel info for query %r", query)
                return {"data_mode": "LIVE", "source": "Global Fishing Watch", "vessel": result}
            else:
                logger.info("GFW: no vessel found for query %r", query)
                return {"data_mode": "LIVE", "source": "Global Fishing Watch", "vessel": None,
                        "message": f"No vessel found for query: {query!r}"}
        except Exception as exc:
            logger.warning("GFW search failed: %s", exc)

    # Demo fallback
    demo_vessels = _demo_vessels()
    matched = [v for v in demo_vessels if query.lower() in v["name"].lower()
               or query in v["mmsi"]]
    return {
        "data_mode": "DEMO",
        "source": "Demo fallback (GFW not reachable)",
        "vessel": matched[0] if matched else None,
        "vessels": matched,
    }


@app.get("/api/vessels/area")
def vessels_in_area(
    min_lon: float = Query(...),
    min_lat: float = Query(...),
    max_lon: float = Query(...),
    max_lat: float = Query(...),
    start_time: str = Query(..., description="ISO8601 start time, e.g. 2026-09-03T00:00:00Z"),
    end_time: str = Query(..., description="ISO8601 end time, e.g. 2026-09-03T12:00:00Z"),
) -> Dict[str, Any]:
    """
    Find AIS vessel tracks in a bounding box during a time window.
    Uses local AISDK CSV if available, GFW API if not, then demo fallback.
    """
    try:
        start_dt = datetime.fromisoformat(start_time.replace("Z", "+00:00"))
        end_dt   = datetime.fromisoformat(end_time.replace("Z", "+00:00"))
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid ISO8601 datetime format")

    # 1 — Try local AIS CSV first (fastest, no token needed)
    ais_csv = os.getenv("AIS_CSV_PATH", "")
    if ais_csv and (Path(ais_csv).exists() or ais_csv.lower().endswith(".zip")):
        try:
            from services.ais_local import AISLocalProvider
            provider = AISLocalProvider(ais_csv)
            vessels = provider.search_vessels_in_area(
                bbox=[min_lon, min_lat, max_lon, max_lat],
                start_time=start_dt,
                end_time=end_dt,
            )
            logger.info("Local AIS CSV returned %d vessel records", len(vessels))
            return {
                "data_mode": "LOCAL_AIS",
                "source": "Local AIS CSV (aisdk-2026-09-03)",
                "vessel_count": len(vessels),
                "vessels": vessels,
            }
        except Exception as exc:
            logger.warning("Local AIS CSV query failed: %s", exc)

    # 2 — Try GFW API
    has_gfw = bool(os.getenv("GFW_API_TOKEN"))
    if has_gfw:
        try:
            from services.gfw import GlobalFishingWatchProvider
            provider = GlobalFishingWatchProvider()
            vessels = provider.search_vessels_in_area(
                bbox=[min_lon, min_lat, max_lon, max_lat],
                start_time=start_dt,
                end_time=end_dt,
            )
            if vessels:
                logger.info("GFW returned %d vessels in area", len(vessels))
                return {
                    "data_mode": "LIVE",
                    "source": "Global Fishing Watch API v3",
                    "vessel_count": len(vessels),
                    "vessels": vessels,
                }
        except Exception as exc:
            logger.warning("GFW area search failed: %s", exc)

    # 3 — Demo fallback
    logger.info("Returning DEMO vessels for area search")
    demo = _demo_vessels()
    return {
        "data_mode": "DEMO",
        "source": "Demo fallback (no AIS source configured)",
        "vessel_count": len(demo),
        "vessels": demo,
    }


@app.get("/api/ais/stats")
def ais_stats() -> Dict[str, Any]:
    """
    Return quick statistics from the local AIS CSV file (aisdk-2026-09-03).
    """
    ais_csv = os.getenv("AIS_CSV_PATH", "")
    if not (ais_csv and (Path(ais_csv).exists() or ais_csv.lower().endswith(".zip"))):
        return {
            "data_mode": "DEMO",
            "message": "Local AIS CSV not configured. Set AIS_CSV_PATH in .env",
            "stats": None,
        }
    try:
        from services.ais_local import AISLocalProvider
        provider = AISLocalProvider(ais_csv)
        stats = provider.get_stats()
        return {"data_mode": "LOCAL_AIS", "source": "aisdk-2026-09-03.zip", "stats": stats}
    except Exception as exc:
        logger.warning("AIS stats failed: %s", exc)
        return {"data_mode": "DEMO", "message": f"AIS CSV error: {exc}", "stats": None}


# ══════════════════════════════════════════════════════════════════════════════
# Demo Fallback Data (clearly separated, never presented as real)
# ══════════════════════════════════════════════════════════════════════════════

def _demo_vessels() -> List[Dict[str, Any]]:
    return [
        {
            "name": "MT ARABIAN STAR", "mmsi": "419001234", "imo": "9876543",
            "vessel_type": "Oil Tanker", "flag": "IND",
            "last_position": {"lat": 13.45, "lon": 80.60},
            "speed_kts": 12.4, "course_deg": 45,
            "last_update": "2026-09-03T05:32:00Z",
            "source_provider": "Demo Fallback", "data_mode": "DEMO",
        },
        {
            "name": "MV DELTA PRIDE", "mmsi": "636017891", "imo": "9123456",
            "vessel_type": "Bulk Carrier", "flag": "LBR",
            "last_position": {"lat": 13.62, "lon": 80.85},
            "speed_kts": 14.1, "course_deg": 120,
            "last_update": "2026-09-03T05:35:00Z",
            "source_provider": "Demo Fallback", "data_mode": "DEMO",
        },
        {
            "name": "FV NEELAVENI", "mmsi": "419005678", "imo": None,
            "vessel_type": "Fishing", "flag": "IND",
            "last_position": {"lat": 13.50, "lon": 80.70},
            "speed_kts": 4.2, "course_deg": 270,
            "last_update": "2026-09-03T05:28:00Z",
            "source_provider": "Demo Fallback", "data_mode": "DEMO",
        },
    ]


# ══════════════════════════════════════════════════════════════════════════════
# Entry Point
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import uvicorn
    host = os.getenv("API_HOST", "127.0.0.1")
    port = int(os.getenv("API_PORT", "8080"))
    uvicorn.run("main:app", host=host, port=port, reload=True)
