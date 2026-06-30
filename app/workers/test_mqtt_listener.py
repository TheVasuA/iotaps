"""Unit tests for the MQTT_Listener worker (Task 5.1, Req 6.1, 30.1).

Covers topic parsing, payload validation, and the Redis side effects of
dispatch (telemetry enqueue + presence tracking) using fakeredis so no live
broker/Redis is required.
"""

import json

import pytest
from fakeredis import aioredis as fake_aioredis

from app.core import redis_keys as rk
from app.core.mqtt_topics import MessageType
from app.workers import mqtt_listener as ml


@pytest.fixture
def redis():
    return fake_aioredis.FakeRedis(decode_responses=True)


# ---------------------------------------------------------------------------
# Topic parsing
# ---------------------------------------------------------------------------
def test_parse_topic_valid_telemetry():
    parsed = ml.parse_topic("iotaps/org1/dev1/telemetry")
    assert parsed == ml.ParsedTopic("org1", "dev1", MessageType.TELEMETRY)


def test_parse_topic_valid_status_and_ack():
    assert ml.parse_topic("iotaps/o/d/status").message_type is MessageType.STATUS
    assert ml.parse_topic("iotaps/o/d/ack").message_type is MessageType.ACK


@pytest.mark.parametrize(
    "topic",
    [
        "",
        "iotaps/org1/dev1",  # too few segments
        "iotaps/org1/dev1/telemetry/extra",  # too many segments
        "other/org1/dev1/telemetry",  # wrong root
        "iotaps//dev1/telemetry",  # empty org
        "iotaps/org1//telemetry",  # empty device
        "iotaps/org1/dev1/bogus",  # unknown type
    ],
)
def test_parse_topic_rejects_malformed(topic):
    assert ml.parse_topic(topic) is None


# ---------------------------------------------------------------------------
# Telemetry payload validation
# ---------------------------------------------------------------------------
def test_validate_telemetry_accepts_contract_payload():
    payload = json.dumps({"ts": "2025-01-01T00:00:00Z", "data": {"temp": 24.1, "hum": 60}})
    result = ml.validate_telemetry_payload(payload)
    assert result["data"] == {"temp": 24.1, "hum": 60}


def test_validate_telemetry_accepts_bytes():
    payload = json.dumps({"ts": "2025-01-01T00:00:00Z", "data": {"temp": 1}}).encode()
    assert ml.validate_telemetry_payload(payload) is not None


@pytest.mark.parametrize(
    "payload",
    [
        "not json",
        "[1, 2, 3]",  # not an object
        json.dumps({"data": {"temp": 1}}),  # missing ts
        json.dumps({"ts": "", "data": {"temp": 1}}),  # empty ts
        json.dumps({"ts": 123, "data": {"temp": 1}}),  # ts not a string
        json.dumps({"ts": "t"}),  # missing data
        json.dumps({"ts": "t", "data": {}}),  # empty data
        json.dumps({"ts": "t", "data": {"temp": "hot"}}),  # non-numeric value
        json.dumps({"ts": "t", "data": {"on": True}}),  # bool rejected
        json.dumps({"ts": "t", "data": [1, 2]}),  # data not an object
    ],
)
def test_validate_telemetry_rejects_invalid(payload):
    assert ml.validate_telemetry_payload(payload) is None


# ---------------------------------------------------------------------------
# Status payload validation
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("status", ["online", "offline"])
def test_validate_status_accepts_known_values(status):
    payload = json.dumps({"status": status, "ts": "2025-01-01T00:00:00Z"})
    assert ml.validate_status_payload(payload) == status


@pytest.mark.parametrize(
    "payload",
    ["bad json", json.dumps({"status": "unknown"}), json.dumps({"ts": "t"}), "[1]"],
)
def test_validate_status_rejects_invalid(payload):
    assert ml.validate_status_payload(payload) is None


# ---------------------------------------------------------------------------
# handle_telemetry -> ingest queue (Req 6.1)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_handle_telemetry_enqueues_envelope(redis):
    parsed = ml.ParsedTopic("org1", "dev1", MessageType.TELEMETRY)
    payload = json.dumps({"ts": "2025-01-01T00:00:00Z", "data": {"temp": 24.1}})

    assert await ml.handle_telemetry(redis, parsed, payload) is True

    assert await redis.llen(rk.INGEST_QUEUE) == 1
    envelope = json.loads(await redis.lindex(rk.INGEST_QUEUE, 0))
    assert envelope == {
        "org_id": "org1",
        "device_id": "dev1",
        "ts": "2025-01-01T00:00:00Z",
        "data": {"temp": 24.1},
    }


@pytest.mark.asyncio
async def test_handle_telemetry_rejects_invalid_without_enqueue(redis):
    parsed = ml.ParsedTopic("org1", "dev1", MessageType.TELEMETRY)
    assert await ml.handle_telemetry(redis, parsed, "garbage") is False
    assert await redis.llen(rk.INGEST_QUEUE) == 0


# ---------------------------------------------------------------------------
# handle_status -> presence set
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_handle_status_online_then_offline(redis):
    parsed = ml.ParsedTopic("org1", "dev1", MessageType.STATUS)

    await ml.handle_status(redis, parsed, json.dumps({"status": "online", "ts": "t"}))
    assert await redis.sismember(rk.ONLINE_DEVICES, "dev1")

    await ml.handle_status(redis, parsed, json.dumps({"status": "offline", "ts": "t"}))
    assert not await redis.sismember(rk.ONLINE_DEVICES, "dev1")


@pytest.mark.asyncio
async def test_handle_status_invalid_does_not_change_set(redis):
    parsed = ml.ParsedTopic("org1", "dev1", MessageType.STATUS)
    assert await ml.handle_status(redis, parsed, "bad") is None
    assert await redis.scard(rk.ONLINE_DEVICES) == 0


# ---------------------------------------------------------------------------
# dispatch routing
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_dispatch_routes_telemetry_to_queue(redis):
    payload = json.dumps({"ts": "t", "data": {"temp": 1}})
    await ml.dispatch(redis, "iotaps/org1/dev1/telemetry", payload)
    assert await redis.llen(rk.INGEST_QUEUE) == 1


@pytest.mark.asyncio
async def test_dispatch_routes_status_to_presence(redis):
    await ml.dispatch(redis, "iotaps/org1/dev1/status", json.dumps({"status": "online"}))
    assert await redis.sismember(rk.ONLINE_DEVICES, "dev1")


@pytest.mark.asyncio
async def test_dispatch_ignores_unparseable_topic(redis):
    await ml.dispatch(redis, "garbage/topic", b"{}")
    assert await redis.llen(rk.INGEST_QUEUE) == 0
    assert await redis.scard(rk.ONLINE_DEVICES) == 0


# ---------------------------------------------------------------------------
# Command integration: ACK confirmation + reconnect flush (Req 9.4, 9.6)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_handle_ack_confirms_known_command(redis):
    from app.services import command_service as cs

    cid = "cmd-1"
    record = cs.CommandRecord(
        command_id=cid,
        device_id="dev1",
        org_id="org1",
        type="on",
        value=None,
        target=None,
        status=cs.CommandStatus.SENT,
        created_at="2025-01-01T00:00:00+00:00",
        updated_at="2025-01-01T00:00:00+00:00",
    )
    await redis.set(rk.command_record_key(cid), json.dumps(record.to_dict()))

    parsed = ml.ParsedTopic("org1", "dev1", MessageType.ACK)
    assert await ml.handle_ack(redis, parsed, json.dumps({"command_id": cid, "result": "ok"}))

    stored = json.loads(await redis.get(rk.command_record_key(cid)))
    assert stored["status"] == "CONFIRMED"


@pytest.mark.asyncio
async def test_handle_status_online_flushes_queued_commands(redis):
    from app.services import command_service as cs

    cid = "cmd-q"
    record = cs.CommandRecord(
        command_id=cid,
        device_id="dev1",
        org_id="org1",
        type="off",
        value=None,
        target=None,
        status=cs.CommandStatus.QUEUED,
        created_at="2025-01-01T00:00:00+00:00",
        updated_at="2025-01-01T00:00:00+00:00",
    )
    await redis.set(rk.command_record_key(cid), json.dumps(record.to_dict()))
    await redis.rpush(
        rk.command_queue_key("dev1"),
        json.dumps({"command_id": cid, "type": "off", "value": None}),
    )

    published: list[tuple[str, str]] = []

    async def publisher(topic, payload):
        published.append((topic, payload))

    parsed = ml.ParsedTopic("org1", "dev1", MessageType.STATUS)
    await ml.handle_status(
        redis, parsed, json.dumps({"status": "online", "ts": "t"}), publisher
    )

    # Command flushed -> SENT and published; queue drained.
    stored = json.loads(await redis.get(rk.command_record_key(cid)))
    assert stored["status"] == "SENT"
    assert len(published) == 1
    assert await redis.llen(rk.command_queue_key("dev1")) == 0
