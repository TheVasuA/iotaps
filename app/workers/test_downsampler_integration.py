"""Integration test for continuous-aggregate downsampling output (Task 6.2).

This exercises the *real* TimescaleDB continuous aggregate that the Downsampler
worker drives. It inserts raw rows into the ``telemetry`` hypertable, refreshes
the ``telemetry_5m`` rollup through the worker's own
``downsampler.refresh_aggregate`` executor, and asserts the materialised buckets
hold the expected per-key averages defined by the continuous aggregate in
``alembic/versions/0001_initial_schema.py`` / design.md::

    SELECT device_id, org_id, time_bucket('5 minutes', ts) AS bucket,
           jsonb_object_agg(k, avg_v) AS data
    FROM telemetry, LATERAL jsonb_each_text(data) AS e(k, v),
         LATERAL (SELECT avg((v)::numeric) AS avg_v) agg
    GROUP BY device_id, org_id, bucket

A live TimescaleDB/Postgres is not guaranteed in every test environment, so the
test connects up-front and calls ``pytest.skip`` when the database (or the
``telemetry_5m`` continuous aggregate) is unavailable. When a database *is*
present, it verifies the downsampling output end to end.

Validates: Requirements 6.6
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text

from app.db.session import engine
from app.workers import downsampler as ds

pytestmark = pytest.mark.asyncio

# Exceptions that all mean "the database isn't reachable / usable here" and so
# should translate into a clean skip rather than a failure.
_UNAVAILABLE_ERRORS: tuple[type[BaseException], ...] = (
    ConnectionError,
    OSError,
    ModuleNotFoundError,  # asyncpg driver not installed
)
try:  # pragma: no cover - depends on optional deps being importable
    from sqlalchemy.exc import DBAPIError, InterfaceError, OperationalError

    _UNAVAILABLE_ERRORS += (OperationalError, InterfaceError, DBAPIError)
except Exception:  # pragma: no cover
    pass


async def _connect_or_skip():
    """Open a connection and confirm the downsampling cagg exists, else skip."""
    try:
        conn = await engine.connect()
    except _UNAVAILABLE_ERRORS as exc:  # pragma: no cover - env dependent
        pytest.skip(f"TimescaleDB/Postgres unavailable: {exc}")
    except Exception as exc:  # pragma: no cover - treat any connect failure as unavailable
        pytest.skip(f"TimescaleDB/Postgres unavailable: {exc}")

    try:
        # The telemetry_5m rollup must be a registered TimescaleDB continuous
        # aggregate for the refresh procedure to work.
        exists = await conn.scalar(
            text(
                "SELECT 1 FROM timescaledb_information.continuous_aggregates "
                "WHERE view_name = 'telemetry_5m'"
            )
        )
    except Exception as exc:  # pragma: no cover - no timescaledb / not migrated
        await conn.close()
        pytest.skip(f"TimescaleDB continuous aggregates not available: {exc}")

    if not exists:
        await conn.close()
        pytest.skip("telemetry_5m continuous aggregate is not present (schema not migrated)")

    return conn


async def test_continuous_aggregate_5m_matches_expected_averages():
    """Inserted raw telemetry rolls up into 5m buckets of per-key averages."""
    conn = await _connect_or_skip()

    org_id = uuid.uuid4()
    device_id = uuid.uuid4()

    # Two distinct 5-minute buckets, with known per-key averages.
    base = datetime(2021, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    bucket_a = base                       # 00:00 bucket
    bucket_b = base + timedelta(minutes=5)  # 00:05 bucket

    rows = [
        # bucket A: temp avg = (10+20+30)/3 = 20, hum avg = (40+50+60)/3 = 50
        (base + timedelta(minutes=0), {"temp": 10, "hum": 40}),
        (base + timedelta(minutes=1), {"temp": 20, "hum": 50}),
        (base + timedelta(minutes=2), {"temp": 30, "hum": 60}),
        # bucket B: temp avg = (100+200)/2 = 150, hum avg = (200+400)/2 = 300
        (base + timedelta(minutes=5), {"temp": 100, "hum": 200}),
        (base + timedelta(minutes=6), {"temp": 200, "hum": 400}),
    ]

    try:
        # ---- insert raw telemetry --------------------------------------
        async with conn.begin():
            for ts, data in rows:
                await conn.execute(
                    text(
                        "INSERT INTO telemetry (org_id, device_id, ts, data) "
                        "VALUES (:org_id, :device_id, :ts, CAST(:data AS jsonb)) "
                        "ON CONFLICT (device_id, ts) DO NOTHING"
                    ),
                    {
                        "org_id": org_id,
                        "device_id": device_id,
                        "ts": ts,
                        "data": json.dumps(data),
                    },
                )

        # ---- drive the rollup through the worker's refresh executor -----
        # refresh_continuous_aggregate cannot run in a transaction block, so the
        # worker issues it on an AUTOCOMMIT connection of its own.
        await ds.refresh_aggregate(
            "telemetry_5m", base, base + timedelta(minutes=10)
        )

        # ---- assert the materialised buckets ----------------------------
        result = await conn.execute(
            text(
                "SELECT bucket, data FROM telemetry_5m "
                "WHERE device_id = :device_id ORDER BY bucket"
            ),
            {"device_id": device_id},
        )
        fetched = result.all()
    finally:
        # Clean up the rows we inserted and re-refresh so the materialised
        # rollup for this device does not linger.
        try:
            async with conn.begin():
                await conn.execute(
                    text("DELETE FROM telemetry WHERE device_id = :device_id"),
                    {"device_id": device_id},
                )
            await ds.refresh_aggregate(
                "telemetry_5m", base, base + timedelta(minutes=10)
            )
        finally:
            await conn.close()

    # asyncpg returns jsonb as a string; normalise to a dict.
    buckets = []
    for bucket, data in fetched:
        if isinstance(data, str):
            data = json.loads(data)
        buckets.append((bucket, data))

    assert len(buckets) == 2, f"expected two 5m buckets, got {buckets!r}"

    (ts_a, data_a), (ts_b, data_b) = buckets

    assert ts_a == bucket_a
    assert float(data_a["temp"]) == pytest.approx(20.0)
    assert float(data_a["hum"]) == pytest.approx(50.0)

    assert ts_b == bucket_b
    assert float(data_b["temp"]) == pytest.approx(150.0)
    assert float(data_b["hum"]) == pytest.approx(300.0)
