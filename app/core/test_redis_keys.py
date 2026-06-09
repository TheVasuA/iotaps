"""Unit tests for Redis key namespaces (Task 1.4, Req 3.4/3.5 supporting layout)."""

from datetime import datetime, timezone

from app.core import redis_keys as rk


def test_static_namespaces_are_prefixed():
    assert rk.INGEST_QUEUE == "iotaps:ingest:telemetry"
    assert rk.ONLINE_DEVICES == "iotaps:online_devices"


def test_pubsub_channels():
    assert rk.telemetry_channel("dev1") == "iotaps:telemetry:dev1"
    assert rk.device_channel("dev1") == "iotaps:device:dev1"
    assert rk.dashboard_channel("dash1") == "iotaps:dashboard:dash1"


def test_refresh_and_command_and_ratelimit_keys():
    assert rk.refresh_token_key("jti123") == "iotaps:refresh:jti123"
    assert rk.command_queue_key("dev1") == "iotaps:cmdq:dev1"
    assert rk.rate_limit_ip_key("1.2.3.4") == "iotaps:ratelimit:ip:1.2.3.4"
    assert rk.rate_limit_org_key("org1") == "iotaps:ratelimit:org:org1"


def test_quota_key_formats():
    # Explicit yyyymm string is passed through.
    assert rk.quota_key("org1", "202501") == "iotaps:quota:org1:202501"
    # Datetime is formatted to its UTC month.
    dt = datetime(2025, 3, 9, 12, 0, tzinfo=timezone.utc)
    assert rk.quota_key("org1", dt) == "iotaps:quota:org1:202503"
    # Default uses the current UTC month (shape check, not value).
    key = rk.quota_key("org1")
    assert key.startswith("iotaps:quota:org1:")
    assert len(key.rsplit(":", 1)[1]) == 6


def test_ws_presence_keys():
    assert rk.ws_presence_key("user1") == "iotaps:ws:presence:user1"
    assert rk.ws_subscriptions_key("sess1") == "iotaps:ws:subs:sess1"
