"""System stats publisher — pushes live server metrics to admin WebSocket.

Publishes RAM, disk, CPU, MQTT connections, and other system stats to the
Redis admin:stats pub/sub channel every 5 seconds. The WebSocket gateway
delivers these to Super_Admin clients subscribed to "admin:stats".
"""

from __future__ import annotations

import asyncio
import json
import shutil
import os

from app.core import redis_keys as rk
from app.core.logging import get_logger, configure_logging
from app.core.redis_client import get_redis

logger = get_logger(__name__)

PUBLISH_INTERVAL = 5  # seconds


def _get_memory_stats() -> dict:
    """Get system memory stats using /proc/meminfo (Linux)."""
    try:
        with open("/proc/meminfo") as f:
            lines = f.readlines()
        info = {}
        for line in lines:
            parts = line.split()
            if len(parts) >= 2:
                info[parts[0].rstrip(":")] = int(parts[1]) * 1024  # KB to bytes
        total = info.get("MemTotal", 0)
        available = info.get("MemAvailable", 0)
        used = total - available
        return {
            "total_bytes": total,
            "used_bytes": used,
            "available_bytes": available,
            "percent": round((used / total) * 100, 1) if total else 0,
        }
    except Exception:
        return {"total_bytes": 0, "used_bytes": 0, "available_bytes": 0, "percent": 0}


def _get_disk_stats() -> dict:
    """Get disk usage for the root filesystem."""
    try:
        usage = shutil.disk_usage("/")
        return {
            "total_bytes": usage.total,
            "used_bytes": usage.used,
            "free_bytes": usage.free,
            "percent": round((usage.used / usage.total) * 100, 1) if usage.total else 0,
        }
    except Exception:
        return {"total_bytes": 0, "used_bytes": 0, "free_bytes": 0, "percent": 0}


def _get_cpu_stats() -> dict:
    """Get CPU usage from /proc/stat (Linux). Returns average across all cores."""
    try:
        with open("/proc/stat") as f:
            line = f.readline()  # first line is aggregate
        parts = line.split()
        # user, nice, system, idle, iowait, irq, softirq
        if len(parts) >= 5:
            idle = int(parts[4])
            total = sum(int(p) for p in parts[1:])
            # Store for delta calculation (approximate)
            return {"idle": idle, "total": total}
    except Exception:
        pass
    return {"idle": 0, "total": 0}


async def _get_mqtt_connections(redis) -> int:
    """Get online device count from Redis ONLINE_DEVICES set."""
    try:
        return await redis.scard(rk.ONLINE_DEVICES)
    except Exception:
        return 0


async def _get_redis_info(redis) -> dict:
    """Get Redis memory usage."""
    try:
        info = await redis.info("memory")
        return {
            "used_bytes": info.get("used_memory", 0),
            "peak_bytes": info.get("used_memory_peak", 0),
        }
    except Exception:
        return {"used_bytes": 0, "peak_bytes": 0}


async def _get_ingest_queue_size(redis) -> int:
    """Get the telemetry ingest queue length."""
    try:
        return await redis.llen(rk.INGEST_QUEUE)
    except Exception:
        return 0


_prev_cpu = {"idle": 0, "total": 0}


def _calc_cpu_percent() -> float:
    """Calculate CPU usage as a percentage since last call."""
    global _prev_cpu
    current = _get_cpu_stats()
    if current["total"] == 0:
        return 0.0
    idle_delta = current["idle"] - _prev_cpu["idle"]
    total_delta = current["total"] - _prev_cpu["total"]
    _prev_cpu = current
    if total_delta == 0:
        return 0.0
    return round((1 - idle_delta / total_delta) * 100, 1)


async def publish_stats(redis) -> None:
    """Collect and publish system stats."""
    memory = _get_memory_stats()
    disk = _get_disk_stats()
    cpu_percent = _calc_cpu_percent()
    mqtt_connections = await _get_mqtt_connections(redis)
    redis_info = await _get_redis_info(redis)
    queue_size = await _get_ingest_queue_size(redis)

    stats = {
        "type": "system_stats",
        "ram": memory,
        "disk": disk,
        "cpu_percent": cpu_percent,
        "mqtt_connections": mqtt_connections,
        "redis_memory": redis_info,
        "ingest_queue_size": queue_size,
        "max_connections_design": 10000,
    }

    await redis.publish(rk.admin_stats_channel(), json.dumps(stats))


async def main():
    """Main loop: publish system stats every PUBLISH_INTERVAL seconds."""
    configure_logging("INFO")
    logger.info("stats_publisher_starting")

    # Wait for Redis to be available
    redis = None
    while redis is None:
        redis = get_redis()
        if redis is None:
            await asyncio.sleep(2)

    # Initial CPU reading (first delta will be since boot)
    _get_cpu_stats()
    await asyncio.sleep(1)

    logger.info("stats_publisher_running", extra={"interval": PUBLISH_INTERVAL})
    while True:
        try:
            await publish_stats(redis)
        except Exception:
            logger.exception("stats_publish_failed")
        await asyncio.sleep(PUBLISH_INTERVAL)


if __name__ == "__main__":
    asyncio.run(main())
