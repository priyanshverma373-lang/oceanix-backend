# -*- coding: utf-8 -*-
"""
OCEANIX — SQLAlchemy ORM Models
Defines all database tables for the OCEANIX Maritime Forensics Platform.

PostGIS availability:
    Geometry columns (bbox, centroid, polygon, position) use GeoAlchemy2
    Geometry type when PostGIS is available.  If PostGIS is NOT installed,
    they fall back to Text (WKT, e.g. "POINT(80.5 13.2)") so the tables
    can still be created and queried without the extension.

    To enable PostGIS geometry columns:
        1. Install PostGIS for PostgreSQL 18 (see README — PostGIS section).
        2. Run: CREATE EXTENSION postgis;  inside the 'oceanix' database.
        3. Set POSTGIS_AVAILABLE=true in .env and restart the backend.

Tables created:
    satellite_scenes, incidents, spill_detections,
    vessels, ais_positions, correlation_results
"""

import os
import uuid
from datetime import datetime

from sqlalchemy import (
    Column, String, Float, Boolean, Integer, JSON,
    ForeignKey, DateTime, Text
)
from sqlalchemy.orm import declarative_base, relationship
from sqlalchemy.dialects.postgresql import UUID

# ── PostGIS optional import ──────────────────────────────────────────────────
# GeoAlchemy2 is available in requirements; actual usage requires PostGIS
# extension to be installed in PostgreSQL.
_POSTGIS_AVAILABLE = os.getenv("POSTGIS_AVAILABLE", "false").lower() == "true"

if _POSTGIS_AVAILABLE:
    try:
        from geoalchemy2 import Geometry as _Geometry  # type: ignore
        POINT   = lambda: _Geometry("POINT",   srid=4326)
        POLYGON = lambda: _Geometry("POLYGON", srid=4326)
    except ImportError:
        _POSTGIS_AVAILABLE = False

if not _POSTGIS_AVAILABLE:
    # Fallback: store geometry as WKT text
    # e.g. "POINT(80.5 13.2)" or "POLYGON((...))"
    POINT   = lambda: Text()  # noqa: E731
    POLYGON = lambda: Text()  # noqa: E731

Base = declarative_base()


# ────────────────────────────────────────────────────────────────────────────
class SatelliteScene(Base):
    """One acquired Sentinel-1 SAR scene from the Copernicus Data Space."""
    __tablename__ = "satellite_scenes"

    id               = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    scene_id         = Column(String, unique=True, nullable=False)
    platform         = Column(String)            # e.g. 'Sentinel-1A'
    product_type     = Column(String)            # e.g. 'GRD'
    acquisition_time = Column(DateTime(timezone=True))
    bbox             = Column(POLYGON())         # WKT or PostGIS geometry
    polarization     = Column(String)
    orbit_direction  = Column(String)
    source_provider  = Column(String)            # e.g. 'Copernicus Data Space'
    data_mode        = Column(String)            # 'LIVE' | 'DEMO'
    created_at       = Column(DateTime(timezone=True), default=datetime.utcnow)

    # Relationships
    detections = relationship("SpillDetection", back_populates="scene")


# ────────────────────────────────────────────────────────────────────────────
class Incident(Base):
    """A confirmed or under-investigation oil-spill incident."""
    __tablename__ = "incidents"

    id          = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    incident_id = Column(String, unique=True, nullable=False)  # e.g. 'INC-2026-09-03-001'
    data_mode   = Column(String)                               # 'LIVE' | 'DEMO'
    status      = Column(String)                               # 'UNDER_INVESTIGATION' | 'CONFIRMED' …
    created_at  = Column(DateTime(timezone=True), default=datetime.utcnow)

    # Relationships
    detections   = relationship("SpillDetection",  back_populates="incident")
    correlations = relationship("CorrelationResult", back_populates="incident")


# ────────────────────────────────────────────────────────────────────────────
class SpillDetection(Base):
    """AI model output for a single scene — one detection record per run."""
    __tablename__ = "spill_detections"

    id              = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    incident_id     = Column(UUID(as_uuid=True), ForeignKey("incidents.id"))
    scene_id        = Column(UUID(as_uuid=True), ForeignKey("satellite_scenes.id"))

    model_version   = Column(String)
    spill_detected  = Column(Boolean)
    confidence      = Column(Float,   nullable=True)  # NULL when model is NOT_CONNECTED/DEMO
    model_status    = Column(String)                  # 'READY' | 'NOT_CONNECTED' | 'DEMO'
    spill_area_km2  = Column(Float)
    centroid        = Column(POINT())                 # WKT or PostGIS geometry
    polygon         = Column(POLYGON())               # WKT or PostGIS geometry
    data_mode       = Column(String)
    inference_time_ms = Column(Integer)
    created_at      = Column(DateTime(timezone=True), default=datetime.utcnow)

    # Relationships
    incident = relationship("Incident",        back_populates="detections")
    scene    = relationship("SatelliteScene",  back_populates="detections")


# ────────────────────────────────────────────────────────────────────────────
class Vessel(Base):
    """A unique maritime vessel identified by MMSI."""
    __tablename__ = "vessels"

    id              = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    mmsi            = Column(String, unique=True)
    imo             = Column(String)
    name            = Column(String)
    vessel_type     = Column(String)
    flag            = Column(String)
    source_provider = Column(String)
    data_mode       = Column(String)
    last_updated    = Column(DateTime(timezone=True))

    # Relationships
    positions    = relationship("AISPosition",      back_populates="vessel")
    correlations = relationship("CorrelationResult", back_populates="vessel")


# ────────────────────────────────────────────────────────────────────────────
class AISPosition(Base):
    """A single AIS position broadcast from a vessel."""
    __tablename__ = "ais_positions"

    id              = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    vessel_id       = Column(UUID(as_uuid=True), ForeignKey("vessels.id"))
    timestamp       = Column(DateTime(timezone=True))
    position        = Column(POINT())    # WKT or PostGIS geometry
    speed_knots     = Column(Float)
    course          = Column(Float)
    heading         = Column(Float)
    source_provider = Column(String)
    data_mode       = Column(String)

    # Relationships
    vessel = relationship("Vessel", back_populates="positions")


# ────────────────────────────────────────────────────────────────────────────
class CorrelationResult(Base):
    """Spatial/temporal correlation between a vessel and a spill incident."""
    __tablename__ = "correlation_results"

    id                  = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    incident_id         = Column(UUID(as_uuid=True), ForeignKey("incidents.id"))
    vessel_id           = Column(UUID(as_uuid=True), ForeignKey("vessels.id"))

    rank                = Column(Integer)
    correlation_score   = Column(Float)
    spatial_score       = Column(Float)
    temporal_score      = Column(Float)
    trajectory_score    = Column(Float)
    data_quality_score  = Column(Float)
    evidence            = Column(JSON)    # e.g. ["Passed within 3.2 km", "AIS gap detected"]
    computed_at         = Column(DateTime(timezone=True), default=datetime.utcnow)

    # Relationships
    incident = relationship("Incident", back_populates="correlations")
    vessel   = relationship("Vessel",   back_populates="correlations")
