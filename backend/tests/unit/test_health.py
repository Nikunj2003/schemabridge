"""The health endpoint is how a misconfigured deployment is diagnosed."""

from __future__ import annotations

from fastapi.testclient import TestClient

from main import app

client = TestClient(app)


def test_health_reports_ok() -> None:
    response = client.get("/api/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert "version" in body


def test_health_reports_dependency_configuration() -> None:
    body = client.get("/api/health").json()
    # Booleans, never the credentials themselves.
    assert isinstance(body["model_configured"], bool)
    assert isinstance(body["database_configured"], bool)


def test_health_never_leaks_credentials() -> None:
    raw = client.get("/api/health").text
    for secret in ("nvapi-", "mongodb+srv://", "password"):
        assert secret not in raw


def test_routes_are_namespaced_under_api() -> None:
    # The platform routes /api/* here without stripping the prefix, so a
    # handler mounted at the bare path would be unreachable in production.
    paths = [r.path for r in app.routes if hasattr(r, "path")]
    assert "/api/health" in paths
    assert "/health" not in paths


def test_every_route_lives_under_api() -> None:
    """The frontend catch-all owns everything outside /api.

    A route declared outside that prefix is routed to the UI and 404s, so this
    guards against adding one by accident — including the docs helper paths
    FastAPI mounts at the root by default.
    """
    stray = [
        route.path
        for route in app.routes
        if hasattr(route, "path") and not route.path.startswith("/api")
    ]
    assert stray == [], f"routes unreachable behind the frontend catch-all: {stray}"
