"""Endpoint tests for the partner wallet & payout API (Task 16.3, Req 18.4-18.6, 26.3).

Exercises GET /partner/wallet, POST /partner/payouts, and the Super_Admin
approval route POST /admin/payouts/{id}/approve end to end against an in-memory
SQLite DB (via a dependency override). No live RazorpayX call is made: the
transfer is offline (``RazorpayXClient`` mints a local ``pout_`` id). Covers:

    - wallet read returns balance + commission history (Req 18.4)
    - payout request within balance -> PENDING (Req 18.4)
    - payout request exceeding balance -> rejected, wallet untouched (Req 18.6)
    - Super_Admin approval debits the wallet, transfers, sets PAID (Req 18.5, 26.3)
    - approval requires Super_Admin (Project_Center forbidden)
"""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool
from sqlalchemy.sql.schema import ColumnDefault

from app.core.config import Settings
from app.core.security import jwt as jwt_service
from app.core.security.principal import ROLE_PROJECT_CENTER, ROLE_SUPER_ADMIN
from app.db.base import Base
from app.db.session import get_session
from app.main import API_V1_PREFIX, create_app
from app.models.billing import Commission, PartnerWallet, Payout
from app.models.organization import Organization

import app.models  # noqa: F401  (register all models on Base.metadata)

_TABLES = [
    Organization.__table__,
    PartnerWallet.__table__,
    Commission.__table__,
    Payout.__table__,
]


def _prepare_tables() -> None:
    for table in _TABLES:
        if "id" in table.c:
            col = table.c.id
            col.server_default = None
            col.default = ColumnDefault(lambda: uuid.uuid4())


def _settings() -> Settings:
    return Settings(jwt_secret="test-secret", jwt_algorithm="HS256")


@pytest.fixture()
def engine():
    _prepare_tables()
    return create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )


@pytest.fixture()
async def session_factory(engine):
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=_TABLES))
    yield async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    await engine.dispose()


@pytest.fixture()
async def seeded(session_factory):
    async with session_factory() as s:
        org = Organization(name="Org", type="project_center", plan="pro")
        s.add(org)
        await s.flush()
        wallet = PartnerWallet(org_id=org.id, balance=Decimal("100"))
        s.add(wallet)
        await s.flush()
        s.add(Commission(org_id=org.id, wallet_id=wallet.id, amount=Decimal("50")))
        s.add(Commission(org_id=org.id, wallet_id=wallet.id, amount=Decimal("50")))
        await s.commit()
        return {"org_id": str(org.id), "wallet_id": str(wallet.id)}


@pytest.fixture()
def client(session_factory, monkeypatch):
    monkeypatch.setattr(jwt_service, "get_settings", _settings, raising=False)
    app = create_app()

    async def _override_session():
        async with session_factory() as s:
            yield s

    app.dependency_overrides[get_session] = _override_session
    return TestClient(app)


def _url(path: str) -> str:
    return f"{API_V1_PREFIX}{path}"


def _auth(org_id: str, role: str = ROLE_PROJECT_CENTER) -> dict[str, str]:
    token = jwt_service.create_access_token(
        user_id=str(uuid.uuid4()), org_id=org_id, role=role, settings=_settings()
    )
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# wallet
# ---------------------------------------------------------------------------
def test_wallet_requires_auth(client):
    assert client.get(_url("/partner/wallet")).status_code == 401


def test_get_wallet_returns_balance_and_commissions(client, seeded):
    resp = client.get(_url("/partner/wallet"), headers=_auth(seeded["org_id"]))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert Decimal(str(body["balance"])) == Decimal("100")
    assert len(body["commissions"]) == 2


# ---------------------------------------------------------------------------
# payout request (Req 18.4, 18.6)
# ---------------------------------------------------------------------------
def test_payout_request_within_balance(client, seeded):
    resp = client.post(
        _url("/partner/payouts"),
        json={"amount": 40, "destination": "upi:org@bank"},
        headers=_auth(seeded["org_id"]),
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["status"] == "PENDING"
    assert Decimal(str(body["amount"])) == Decimal("40")
    assert body["destination"] == "upi:org@bank"


def test_payout_request_exceeding_balance_rejected(client, seeded):
    resp = client.post(
        _url("/partner/payouts"),
        json={"amount": 150},
        headers=_auth(seeded["org_id"]),
    )
    assert resp.status_code == 422, resp.text
    assert resp.json()["error_code"] == "insufficient_balance"
    # Wallet balance unchanged.
    wallet = client.get(_url("/partner/wallet"), headers=_auth(seeded["org_id"]))
    assert Decimal(str(wallet.json()["balance"])) == Decimal("100")


def test_payout_request_rejects_non_positive(client, seeded):
    resp = client.post(
        _url("/partner/payouts"),
        json={"amount": 0},
        headers=_auth(seeded["org_id"]),
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# admin approval (Req 18.5, 26.3)
# ---------------------------------------------------------------------------
def test_approve_payout_debits_wallet_and_pays(client, seeded):
    # Request a payout as the partner.
    created = client.post(
        _url("/partner/payouts"),
        json={"amount": 60, "destination": "upi:org@bank"},
        headers=_auth(seeded["org_id"]),
    ).json()
    payout_id = created["id"]

    # Approve as Super_Admin.
    resp = client.post(
        _url(f"/admin/payouts/{payout_id}/approve"),
        headers=_auth(str(uuid.uuid4()), role=ROLE_SUPER_ADMIN),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "PAID"
    assert body["razorpayx_payout_id"].startswith("pout_")
    assert body["approved_at"] is not None

    # Wallet debited to 40, still >= 0.
    wallet = client.get(_url("/partner/wallet"), headers=_auth(seeded["org_id"]))
    assert Decimal(str(wallet.json()["balance"])) == Decimal("40")


def test_approve_payout_requires_super_admin(client, seeded):
    created = client.post(
        _url("/partner/payouts"),
        json={"amount": 10},
        headers=_auth(seeded["org_id"]),
    ).json()
    payout_id = created["id"]

    resp = client.post(
        _url(f"/admin/payouts/{payout_id}/approve"),
        headers=_auth(seeded["org_id"], role=ROLE_PROJECT_CENTER),
    )
    assert resp.status_code == 403
