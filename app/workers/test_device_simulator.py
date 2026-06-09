"""Unit tests for the Device_Simulator worker (Task 11.3 / 11.4, Req 13.2-13.4).

Verifies the simulator's publishing contract without a live broker or database:
- interval 0 (and the stopped state) never publishes (Req 13.3, 13.4);
- interval > 0 publishes, then again only after the interval elapses (Req 13.2);
- stopping a running simulator (interval -> 0) ceases publishing (Req 13.4);
- the published payload is on the device's org-scoped telemetry topic and
  matches the telemetry contract accepted by the MQTT_Listener.
"""

from __future__ import annotations

import json
import random

import pytest

from app.core.mqtt_topics import telemetry_topic
from app.workers.device_simulator import (
    SimulatedDevice,
    SimulatorScheduler,
    build_telemetry_payload,
    is_publishing,
)
from app.workers.mqtt_listener import validate_telemetry_payload


class _RecordingPublisher:
    """Collects (topic, payload) tuples instead of touching a broker."""

    def __init__(self) -> None:
        self.published: list[tuple[str, str]] = []

    async def __call__(self, topic: str, payload: str) -> None:
        self.published.append((topic, payload))


def _device(interval: int, *, device_id: str = "dev-1", org_id: str = "org-1") -> SimulatedDevice:
    return SimulatedDevice(device_id=device_id, org_id=org_id, sim_interval_sec=interval)


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------
def test_is_publishing_boundary():
    assert is_publishing(_device(1)) is True
    assert is_publishing(_device(60)) is True
    assert is_publishing(_device(0)) is False
    assert is_publishing(_device(-1)) is False


def test_payload_matches_telemetry_contract():
    rng = random.Random(1234)
    payload = build_telemetry_payload(rng=rng)
    # The listener's validator is the authority on the accepted shape.
    assert validate_telemetry_payload(payload) is not None
    body = json.loads(payload)
    assert set(body["data"]) == {"temperature", "humidity"}


# ---------------------------------------------------------------------------
# Interval boundary: 0 never publishes (Req 13.3)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_interval_zero_never_publishes():
    scheduler = SimulatorScheduler()
    publisher = _RecordingPublisher()

    for t in range(5):
        await scheduler.tick([_device(0)], publisher, now_monotonic=float(t))

    assert publisher.published == []


# ---------------------------------------------------------------------------
# Interval > 0 publishes at the configured cadence (Req 13.2)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_positive_interval_publishes_on_first_tick_and_after_interval():
    scheduler = SimulatorScheduler()
    publisher = _RecordingPublisher()
    device = _device(10)

    # First tick: publishes immediately.
    await scheduler.tick([device], publisher, now_monotonic=0.0)
    assert len(publisher.published) == 1
    topic, payload = publisher.published[0]
    assert topic == telemetry_topic(device.org_id, device.device_id)
    assert validate_telemetry_payload(payload) is not None

    # Before the interval elapses: no new publish.
    await scheduler.tick([device], publisher, now_monotonic=5.0)
    assert len(publisher.published) == 1

    # At the interval boundary: publishes again.
    await scheduler.tick([device], publisher, now_monotonic=10.0)
    assert len(publisher.published) == 2

    # Well past: publishes once per due crossing.
    await scheduler.tick([device], publisher, now_monotonic=20.0)
    assert len(publisher.published) == 3


# ---------------------------------------------------------------------------
# Stopping a running simulator ceases publishing (Req 13.4)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_stop_ceases_publishing():
    scheduler = SimulatorScheduler()
    publisher = _RecordingPublisher()

    # Running at interval 5: publishes on the first tick.
    await scheduler.tick([_device(5)], publisher, now_monotonic=0.0)
    assert len(publisher.published) == 1

    # Stopped (interval -> 0): no further publishes regardless of elapsed time.
    for t in (5.0, 10.0, 15.0, 100.0):
        await scheduler.tick([_device(0)], publisher, now_monotonic=t)
    assert len(publisher.published) == 1


# ---------------------------------------------------------------------------
# Restart after stop begins publishing promptly (clean state)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_restart_after_stop_publishes_again():
    scheduler = SimulatorScheduler()
    publisher = _RecordingPublisher()

    await scheduler.tick([_device(5)], publisher, now_monotonic=0.0)
    assert len(publisher.published) == 1

    # Stop.
    await scheduler.tick([_device(0)], publisher, now_monotonic=1.0)
    assert len(publisher.published) == 1

    # Restart: should publish on the next tick without waiting a full interval.
    await scheduler.tick([_device(5)], publisher, now_monotonic=2.0)
    assert len(publisher.published) == 2


# ---------------------------------------------------------------------------
# Per-device org-scoped topics (Req 3.4 isolation)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_publishes_to_each_device_org_scoped_topic():
    scheduler = SimulatorScheduler()
    publisher = _RecordingPublisher()
    devices = [
        _device(5, device_id="d1", org_id="orgA"),
        _device(5, device_id="d2", org_id="orgB"),
        _device(0, device_id="d3", org_id="orgC"),  # not publishing
    ]

    await scheduler.tick(devices, publisher, now_monotonic=0.0)

    topics = {topic for topic, _ in publisher.published}
    assert topics == {
        telemetry_topic("orgA", "d1"),
        telemetry_topic("orgB", "d2"),
    }
