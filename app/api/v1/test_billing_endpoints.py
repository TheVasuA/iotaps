"""Endpoint tests for the Billing API (Task 14.3, Req 16).

Exercises GET /billing/plans and POST /billing/quote end to end via the FastAPI
app. These endpoints are pure pricing reads (no tenant data), so no DB override
is needed - only a valid bearer token. Verifies tier rates, exact boundaries,
the fixed annual price, auth enforcement, and request validation.
"""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.core.security import jwt as jwt_service
from app.core.security.principal import ROLE_PROJECT_CENTER
from app.main import API_V1_PREFIX, create_app


def _settings() -> Settings:
    return Settings(jwt_secret="test-secret", jwt_algorithm="HS256")


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setattr(jwt_service, "get_settings", _settings, raising=False)
    app = create_app()
    return TestClient(app)


def _url(path: str) -> str:
    return f"{API_V1_PREFIX}{path}"


def _auth() -> dict[str, str]:
    token = jwt_service.create_access_token(
        user_id=str(uuid.uuid4()),
        org_id=str(uuid.uuid4()),
        role=ROLE_PROJECT_CENTER,
        settings=_settings(),
    )
    return {"Authorization": f"Bearer {token}"}


def test_plans_requires_auth(client):
    assert client.get(_url("/billing/plans")).status_code == 401


def test_quote_requires_auth(client):
    resp = client.post(
        _url("/billing/quote"), json={"device_count": 5, "billing_cycle": "monthly"}
    )
    assert resp.status_code == 401


def test_get_plans(client):
    resp = client.get(_url("/billing/plans"), headers=_auth())
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["free"]["max_devices"] == 2
    assert body["pro"]["annual_unit_price"] == 948
    assert [t["unit_price_monthly"] for t in body["pricing_tiers"]] == [99, 79, 69, 59]


@pytest.mark.parametrize(
    "device_count, unit_price",
    [(1, 99), (10, 99), (11, 79), (50, 79), (51, 69), (200, 69), (201, 59)],
)
def test_quote_monthly_tiers(client, device_count, unit_price):
    resp = client.post(
        _url("/billing/quote"),
        json={"device_count": device_count, "billing_cycle": "monthly"},
        headers=_auth(),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["unit_price"] == unit_price
    assert body["total"] == device_count * unit_price


def test_quote_yearly_fixed_price(client):
    resp = client.post(
        _url("/billing/quote"),
        json={"device_count": 30, "billing_cycle": "yearly"},
        headers=_auth(),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["unit_price"] == 948
    assert body["total"] == 30 * 948


def test_quote_rejects_zero_devices(client):
    resp = client.post(
        _url("/billing/quote"),
        json={"device_count": 0, "billing_cycle": "monthly"},
        headers=_auth(),
    )
    assert resp.status_code == 422


def test_quote_rejects_bad_cycle(client):
    resp = client.post(
        _url("/billing/quote"),
        json={"device_count": 5, "billing_cycle": "weekly"},
        headers=_auth(),
    )
    assert resp.status_code == 422
    assert resp.json()["error_code"] == "validation_error"
