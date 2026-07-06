"""Tests for the health and version endpoints."""

import pytest
from fastapi.testclient import TestClient

import finsight
from finsight import app as app_module
from finsight.app import app


async def _ok() -> bool:
    return True


async def _fail() -> bool:
    return False


def test_version_reports_package_version() -> None:
    with TestClient(app) as client:
        payload = client.get("/version").json()
    assert payload["version"] == finsight.__version__


def test_healthz_ok_when_dependencies_up(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(app_module, "_check_database", _ok)
    monkeypatch.setattr(app_module, "_check_cache", _ok)
    with TestClient(app) as client:
        resp = client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok", "checks": {"database": "ok", "cache": "ok"}}


def test_healthz_503_when_database_down(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(app_module, "_check_database", _fail)
    monkeypatch.setattr(app_module, "_check_cache", _ok)
    with TestClient(app) as client:
        resp = client.get("/healthz")
    assert resp.status_code == 503
    assert resp.json()["checks"]["database"] == "unavailable"


def test_healthz_503_when_cache_down(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(app_module, "_check_database", _ok)
    monkeypatch.setattr(app_module, "_check_cache", _fail)
    with TestClient(app) as client:
        resp = client.get("/healthz")
    assert resp.status_code == 503
    assert resp.json()["checks"]["cache"] == "unavailable"
