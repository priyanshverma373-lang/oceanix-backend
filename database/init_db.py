# -*- coding: utf-8 -*-
"""
OCEANIX — Database Initialisation
Creates all tables defined in models.py against the live PostgreSQL database.

Usage:
    python -m database.init_db          # run standalone
    await init_db()                     # called from FastAPI lifespan
"""

import asyncio
import logging

from database.connection import engine, check_db_connection
from database.models import Base

logger = logging.getLogger("oceanix.init_db")


async def init_db() -> None:
    """
    Create all ORM-defined tables in the target database (CREATE TABLE IF NOT EXISTS).
    Safe to call on every startup — existing tables are never dropped or altered.
    """
    ok, info = await check_db_connection()
    if not ok:
        logger.error("Cannot initialise DB — connection failed: %s", info)
        raise RuntimeError(f"DB connection failed: {info}")

    logger.info("DB connection verified: %s", info)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    logger.info(
        "Tables ensured: %s",
        list(Base.metadata.tables.keys()),
    )


if __name__ == "__main__":
    import sys
    import os

    # Allow running from the backend/ directory
    sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

    from dotenv import load_dotenv
    load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "..", "..", ".env"))

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    asyncio.run(init_db())
    print("[OK] Database tables created/verified successfully.")
