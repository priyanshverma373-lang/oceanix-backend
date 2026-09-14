# -*- coding: utf-8 -*-
"""
OCEANIX — PostgreSQL Database Connection
Provides an async SQLAlchemy engine and session factory backed by asyncpg.

Usage:
    from database.connection import get_db, engine, check_db_connection

    # In FastAPI dependency injection:
    async def my_route(db: AsyncSession = Depends(get_db)):
        ...

    # Health-check:
    ok, reason = await check_db_connection()
"""

import os
import logging
from typing import AsyncGenerator, Tuple

from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy import text

load_dotenv()

logger = logging.getLogger("oceanix.db")

# ── Build DATABASE_URL ──────────────────────────────────────────────────────
# We prefer the single DATABASE_URL env var; fall back to individual parts.
_db_url = os.getenv("DATABASE_URL", "")

if not _db_url or "postgresql" not in _db_url:
    _host = os.getenv("DB_HOST", "127.0.0.1")
    _port = os.getenv("DB_PORT", "5432")
    _user = os.getenv("DB_USER", "")
    _pwd  = os.getenv("DB_PASSWORD", "")
    _name = os.getenv("DB_NAME", "oceanix")
    _db_url = f"postgresql+asyncpg://{_user}:{_pwd}@{_host}:{_port}/{_name}"

# Ensure the URL uses the asyncpg driver expected by SQLAlchemy async
if _db_url.startswith("postgresql://") and "+asyncpg" not in _db_url:
    _db_url = _db_url.replace("postgresql://", "postgresql+asyncpg://", 1)

DATABASE_URL: str = _db_url

# ── Engine ──────────────────────────────────────────────────────────────────
engine = create_async_engine(
    DATABASE_URL,
    echo=False,          # set True during development to log SQL
    pool_pre_ping=True,  # verify connection health before each use
    pool_size=5,
    max_overflow=10,
    pool_timeout=30,
)

# ── Session factory ─────────────────────────────────────────────────────────
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


# ── FastAPI dependency ───────────────────────────────────────────────────────
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Yield an async database session; roll back on error."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


# ── Health check ─────────────────────────────────────────────────────────────
async def check_db_connection() -> Tuple[bool, str]:
    """
    Attempt a lightweight real query against the database.

    Returns:
        (True, info_string)   on success
        (False, error_string) on any failure
    """
    try:
        async with engine.connect() as conn:
            result = await conn.execute(
                text("SELECT current_database(), version(), NOW()")
            )
            row = result.fetchone()
            db_name    = row[0]
            pg_version = row[1].split(",")[0]  # e.g. "PostgreSQL 18.6 on ..."
            server_ts  = str(row[2])
        return True, (
            f"Connected to '{db_name}' — {pg_version} — "
            f"server time: {server_ts}"
        )
    except Exception as exc:
        logger.warning("DB health-check failed: %s", exc)
        return False, str(exc)
