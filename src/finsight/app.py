"""FastAPI application: walking skeleton with health and version endpoints."""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import asyncpg
import redis.asyncio as redis
from fastapi import FastAPI, Response

import finsight
from finsight.config import get_settings
from finsight.logging_config import setup_logging

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    setup_logging()
    logger.info("starting finsight (env=%s)", get_settings().app_env)
    yield
    logger.info("shutting down")


async def _check_database() -> bool:
    try:
        conn = await asyncpg.connect(get_settings().database_url, timeout=3)
        try:
            await conn.fetchval("SELECT 1")
        finally:
            await conn.close()
        return True
    except Exception:
        logger.exception("database health check failed")
        return False


async def _check_cache() -> bool:
    client = redis.from_url(get_settings().redis_url, socket_connect_timeout=3)
    try:
        await client.ping()
        return True
    except Exception:
        logger.exception("cache health check failed")
        return False
    finally:
        await client.aclose()


app = FastAPI(title="FinSight", version=finsight.__version__, lifespan=lifespan)


@app.get("/version")
async def version() -> dict[str, str]:
    return {"version": finsight.__version__, "env": get_settings().app_env}


@app.get("/healthz")
async def healthz(response: Response) -> dict[str, object]:
    db_ok = await _check_database()
    cache_ok = await _check_cache()
    healthy = db_ok and cache_ok
    if not healthy:
        response.status_code = 503
    return {
        "status": "ok" if healthy else "degraded",
        "checks": {
            "database": "ok" if db_ok else "unavailable",
            "cache": "ok" if cache_ok else "unavailable",
        },
    }
