"""Unit tests for the FastAPI application skeleton (task 1.2).

Covers:
  - /api/v1 router mounting + health endpoint
  - structured error body {error_code, message}
  - request id propagation header
  - CORS wiring

These tests run without Redis available; the settings loader and health check
degrade gracefully (redis reported "unconfigured"/"degraded"), which is the
expected behaviour in a bare test environment.
"""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.testclient import TestClient

from app.core.errors import NotFoundError
from app.core.middleware import REQUEST_ID_HEADER
from app.main import API_V1_PREFIX, create_app


def _client() -> TestClient:
    return TestClient(create_app())


def test_health_endpoint_mounted_under_api_v1() -> None:
    client = _client()
    resp = client.get(f"{API_V1_PREFIX}/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] in {"ok", "degraded"}
    assert body["service"] == "iotaps-api"
    assert any(dep["name"] == "redis" for dep in body["dependencies"])


def test_health_not_available_without_prefix() -> None:
    # The router must be mounted under /api/v1, not at the root.
    client = _client()
    assert client.get("/health").status_code == 404


def test_request_id_header_present_and_echoed() -> None:
    client = _client()
    resp = client.get(f"{API_V1_PREFIX}/health")
    assert REQUEST_ID_HEADER in resp.headers
    assert resp.headers[REQUEST_ID_HEADER]


def test_incoming_request_id_is_preserved() -> None:
    client = _client()
    resp = client.get(
        f"{API_V1_PREFIX}/health",
        headers={REQUEST_ID_HEADER: "trace-abc-123"},
    )
    assert resp.headers[REQUEST_ID_HEADER] == "trace-abc-123"


def test_404_returns_structured_error_body() -> None:
    client = _client()
    resp = client.get("/no/such/route")
    assert resp.status_code == 404
    body = resp.json()
    assert set(body.keys()) == {"error_code", "message"}
    assert body["error_code"] == "not_found"


def test_app_error_renders_structured_body() -> None:
    app = create_app()
    router = APIRouter()

    @router.get("/boom")
    async def _boom() -> None:
        raise NotFoundError("Device not found")

    app.include_router(router)
    client = TestClient(app)

    resp = client.get("/boom")
    assert resp.status_code == 404
    assert resp.json() == {"error_code": "not_found", "message": "Device not found"}


def test_validation_error_uses_structured_body() -> None:
    app = create_app()
    router = APIRouter()

    @router.get("/needs-param")
    async def _needs_param(count: int) -> dict:  # query param, required int
        return {"count": count}

    app.include_router(router)
    client = TestClient(app)

    resp = client.get("/needs-param", params={"count": "not-an-int"})
    assert resp.status_code == 422
    body = resp.json()
    assert body["error_code"] == "validation_error"
    assert "message" in body


def test_cors_preflight_allowed(monkeypatch) -> None:
    # Build the app with a permissive CORS origin list so the test does not
    # depend on the ambient deployment `.env` (which restricts origins to the
    # production hostnames). This keeps the test asserting CORS *wiring* rather
    # than a particular deployment's allow-list.
    from app.core.config import Settings
    import app.main as main_module

    monkeypatch.setattr(
        main_module, "get_settings", lambda: Settings(cors_allow_origins="*")
    )
    client = TestClient(create_app())
    resp = client.options(
        f"{API_V1_PREFIX}/health",
        headers={
            "Origin": "https://app.example.com",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert resp.status_code in {200, 204}
    assert "access-control-allow-origin" in {k.lower() for k in resp.headers}
