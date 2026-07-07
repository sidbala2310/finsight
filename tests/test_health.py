"""Tests for the health and version endpoints."""

import asyncio
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

import finsight
from finsight import app as app_module
from finsight.app import app
from finsight.config import get_settings


async def _ok() -> bool:
    return True


async def _fail() -> bool:
    return False


def test_root_redirects_to_docs() -> None:
    with TestClient(app) as client:
        resp = client.get("/", follow_redirects=False)
    assert resp.status_code == 307
    assert resp.headers["location"] == "/docs"


def test_version_reports_package_version() -> None:
    with TestClient(app) as client:
        payload = client.get("/version").json()
    assert payload["version"] == finsight.__version__


def test_readyz_ok_when_dependencies_up(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(app_module, "_check_database", _ok)
    monkeypatch.setattr(app_module, "_check_cache", _ok)
    with TestClient(app) as client:
        resp = client.get("/readyz")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok", "checks": {"database": "ok", "cache": "ok"}}


def test_readyz_503_when_database_down(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(app_module, "_check_database", _fail)
    monkeypatch.setattr(app_module, "_check_cache", _ok)
    with TestClient(app) as client:
        resp = client.get("/readyz")
    assert resp.status_code == 503
    assert resp.json()["checks"]["database"] == "unavailable"


def test_readyz_503_when_cache_down(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(app_module, "_check_database", _ok)
    monkeypatch.setattr(app_module, "_check_cache", _fail)
    with TestClient(app) as client:
        resp = client.get("/readyz")
    assert resp.status_code == 503
    assert resp.json()["checks"]["cache"] == "unavailable"


@pytest.fixture
def unreachable_deps(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """
    Point settings at ports where nothing listens;
    restore the cached settings after.
    """
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@127.0.0.1:59999/none")
    monkeypatch.setenv("REDIS_URL", "redis://127.0.0.1:59999/0")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_check_database_returns_false_when_unreachable(unreachable_deps: None) -> None:
    assert asyncio.run(app_module._check_database()) is False


def test_check_cache_returns_false_when_unreachable(unreachable_deps: None) -> None:
    assert asyncio.run(app_module._check_cache()) is False
