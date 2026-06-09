"""Device_Simulator worker (Task 11.3, Req 13.1-13.4).

A virtual device emits fake telemetry without physical hardware (Req 13). The
simulator is configured through the Devices API:

    POST /devices/{id}/simulator       {interval_sec}  -> mark simulator + interval
    POST /devices/{id}/simulator/stop                  -> interval = 0 (cease)

This worker drives the *publishing* side: it periodically loads the org's
simulator devices from Postgres and, for each one whose ``sim_interval_sec`` is
greater than zero, publishes a simulated telemetry message to that device's
org-scoped MQTT topic ``iotaps/{org_id}/{device_id}/telemetry`` at the
configured cadence. The MQTT_Listener (Task 5.1) then ingests those messages
exactly as it would real-hardware telemetry, so simulated devices flow through
the same pipeline (queue -> Batch_Writer -> pub/sub -> WebSocket).

Behavioural contract (the acceptance criteria this worker realises):
- Req 13.2: WHILE a simulator runs with interval > 0, it publishes at that
  interval.
- Req 13.3: WHERE the interval is 0, it does not publish.
- Req 13.4: WHEN stopped (interval set to 0), it ceases publishing.

Design notes:
- The publish topic is the device's *org-scoped* telemetry topic, so messages
  are confined to the owning organization's topic tree (Req 3.4/3.5). The live
  ``main`` loop connects to the broker with the backend's internal credentials
  (the per-org MQTT credential secret is stored only as a hash and is not
  recoverable); the org scoping is enforced by the topic the worker publishes
  to.
- The core scheduling/publishing logic is split into pure, side-effect-free
  helpers and an injectable ``publisher`` so it can be unit-tested with
  ``fakeredis``-style fakes and without a live broker or database (Task 11.4).
"""

from __future__ import annotations

import asyncio
import json
import random
import signal
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Iterable, Optional

from app.core.logging import configure_logging, get_logger
from app.core.mqtt_topics import telemetry_topic

logger = get_logger(__name__)

# How often the worker wakes to evaluate which simulators are due to publish.
# Kept small relative to typical device intervals so a device configured at N
# seconds publishes close to every N seconds.
TICK_INTERVAL_SECONDS = 1.0

# How often the live loop reloads the simulator device set from Postgres so
# start/stop/interval changes made via the API are picked up.
RELOAD_INTERVAL_SECONDS = 10.0

# Async callable that publishes a JSON telemetry payload to an MQTT topic.
# Injected so the scheduling/publishing logic can be unit-tested without a
# live broker.
Publisher = Callable[[str, str], Awaitable[None]]


@dataclass(frozen=True)
class SimulatedDevice:
    """A simulator device's identity + publish interval (subset of ``devices``)."""

    device_id: str
    org_id: str
    sim_interval_sec: int


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------
def is_publishing(device: SimulatedDevice) -> bool:
    """Return ``True`` when the device should publish telemetry.

    A simulator publishes only while its configured interval is greater than
    zero (Req 13.2); an interval of zero suppresses publishing (Req 13.3, and
    the stopped state of Req 13.4 which sets the interval to zero).
    """
    return device.sim_interval_sec > 0


def build_telemetry_payload(
    *, now: Optional[datetime] = None, rng: Optional[random.Random] = None
) -> str:
    """Build a simulated telemetry payload matching the device contract.

    Produces ``{"ts": "<iso8601>", "data": {"temperature": .., "humidity": ..}}``
    with plausible random sensor values. The shape matches
    ``validate_telemetry_payload`` in the MQTT_Listener so the message is
    accepted by the ingestion pipeline. Kept pure (time + RNG injectable) so the
    output is deterministic under test.
    """
    now = now or _now()
    rng = rng or random
    payload = {
        "ts": now.isoformat(),
        "data": {
            "temperature": round(rng.uniform(15.0, 35.0), 2),
            "humidity": round(rng.uniform(30.0, 90.0), 2),
        },
    }
    return json.dumps(payload)


# ---------------------------------------------------------------------------
# Scheduling state
# ---------------------------------------------------------------------------
class SimulatorScheduler:
    """Tracks per-device due times and publishes telemetry when devices are due.

    The scheduler is intentionally storage-agnostic: callers feed it the current
    set of simulator devices on each tick (so API-driven start/stop/interval
    changes are honoured) and an injected ``publisher``. It guarantees:

    - a device with ``sim_interval_sec <= 0`` is never published (Req 13.3/13.4);
    - a publishing device emits roughly every ``sim_interval_sec`` seconds, with
      the first publish on the first tick it is seen (Req 13.2);
    - removing a device (it is no longer in the supplied set) drops its tracked
      state so a later restart begins cleanly.
    """

    def __init__(self) -> None:
        # device_id -> monotonic-ish next due timestamp (seconds).
        self._next_due: dict[str, float] = {}

    async def tick(
        self,
        devices: Iterable[SimulatedDevice],
        publisher: Publisher,
        *,
        now_monotonic: float,
        now: Optional[datetime] = None,
        rng: Optional[random.Random] = None,
    ) -> list[str]:
        """Publish telemetry for every device that is due. Returns published ids.

        ``now_monotonic`` is a seconds-valued clock used purely for scheduling
        (a test can pass an incrementing counter); ``now`` is the wall-clock used
        only to stamp the payload.
        """
        published: list[str] = []
        seen: set[str] = set()

        for device in devices:
            seen.add(device.device_id)

            if not is_publishing(device):
                # Not publishing (interval 0 / stopped): ensure no stale due time
                # lingers so a later restart publishes promptly (Req 13.3/13.4).
                self._next_due.pop(device.device_id, None)
                continue

            due_at = self._next_due.get(device.device_id)
            if due_at is None or now_monotonic >= due_at:
                payload = build_telemetry_payload(now=now, rng=rng)
                topic = telemetry_topic(device.org_id, device.device_id)
                try:
                    await publisher(topic, payload)
                    published.append(device.device_id)
                except Exception:  # pragma: no cover - a publish failure must not
                    # crash the loop; the device stays due and is retried next tick.
                    logger.exception(
                        "simulator_publish_failed",
                        extra={"device_id": device.device_id, "org_id": device.org_id},
                    )
                    continue
                self._next_due[device.device_id] = now_monotonic + device.sim_interval_sec

        # Forget devices that are no longer present so restarts begin cleanly.
        for stale in set(self._next_due) - seen:
            self._next_due.pop(stale, None)

        return published


# ---------------------------------------------------------------------------
# Device loading (live)
# ---------------------------------------------------------------------------
async def load_simulator_devices() -> list[SimulatedDevice]:
    """Load every device flagged as a simulator from Postgres (live).

    Returns all simulator devices (including those with interval 0 so the
    scheduler can drop their state); the scheduler decides which actually
    publish. Isolated here so the run loop can be tested with a fake loader.
    """
    from sqlalchemy import select

    from app.db.session import async_session_factory
    from app.models.device import Device

    async with async_session_factory() as session:
        result = await session.execute(
            select(Device.id, Device.org_id, Device.sim_interval_sec).where(
                Device.is_simulator.is_(True)
            )
        )
        return [
            SimulatedDevice(
                device_id=str(row[0]),
                org_id=str(row[1]),
                sim_interval_sec=int(row[2]),
            )
            for row in result.all()
        ]


# ---------------------------------------------------------------------------
# Run loop + entry point
# ---------------------------------------------------------------------------
async def run(
    publisher: Publisher,
    loader: Callable[[], Awaitable[list[SimulatedDevice]]] = load_simulator_devices,
    stop_event: Optional[asyncio.Event] = None,
    *,
    tick_interval: float = TICK_INTERVAL_SECONDS,
    reload_interval: float = RELOAD_INTERVAL_SECONDS,
) -> None:
    """Continuously publish simulated telemetry until ``stop_event`` is set.

    Reloads the simulator device set every ``reload_interval`` seconds (so API
    start/stop changes take effect) and evaluates due devices every
    ``tick_interval`` seconds.
    """
    stop_event = stop_event or asyncio.Event()
    scheduler = SimulatorScheduler()
    devices: list[SimulatedDevice] = []
    last_reload = -reload_interval  # force an immediate load on the first tick
    loop = asyncio.get_event_loop()

    while not stop_event.is_set():
        now_monotonic = loop.time()
        if now_monotonic - last_reload >= reload_interval:
            try:
                devices = await loader()
            except Exception:  # pragma: no cover - keep running on a load failure
                logger.exception("simulator_device_load_failed")
            last_reload = now_monotonic

        await scheduler.tick(devices, publisher, now_monotonic=now_monotonic)

        try:
            await asyncio.wait_for(stop_event.wait(), timeout=tick_interval)
        except asyncio.TimeoutError:
            continue


async def _mqtt_publisher_factory() -> Publisher:  # pragma: no cover - needs broker
    """Build a publisher backed by a short-lived aiomqtt connection per publish.

    Matches the Commands API publisher pattern. Imported lazily so unit tests do
    not require the broker client library.
    """
    import aiomqtt

    from app.core.config import get_settings

    settings = get_settings()

    async def _publish(topic: str, payload: str) -> None:
        async with aiomqtt.Client(
            hostname=settings.mqtt_host, port=settings.mqtt_port
        ) as client:
            await client.publish(topic, payload)

    return _publish


def main() -> None:  # pragma: no cover - process entry point
    """Process entry point (``python -m app.workers.device_simulator``)."""
    configure_logging()
    logger.info("device_simulator_starting")

    stop_event = asyncio.Event()

    async def _amain() -> None:
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, stop_event.set)
            except NotImplementedError:  # Windows lacks add_signal_handler
                pass
        publisher = await _mqtt_publisher_factory()
        await run(publisher, stop_event=stop_event)

    try:
        asyncio.run(_amain())
    except KeyboardInterrupt:
        pass
    logger.info("device_simulator_stopped")


if __name__ == "__main__":
    main()
