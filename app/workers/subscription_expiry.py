"""Subscription_Expiry worker — emails customers before their plan lapses.

This is the "payment low count days" notification: it periodically scans active
subscriptions and emails the owning organization as the renewal date approaches
(at 7, 3, and 1 days remaining) and once when the plan has expired.

Design notes:
  * **Idempotent reminders.** Each (subscription, threshold) reminder is sent at
    most once. A Redis guard key with a TTL longer than the check interval
    prevents duplicate emails when the sweep runs multiple times per day.
  * **Best-effort.** Email failures are swallowed by :mod:`email_service`; a bad
    row never stops the sweep (the loop keeps going).
  * **Pure-ish core.** :func:`due_reminders` decides what to send for a list of
    subscriptions given "now" and is unit-testable without a DB or SMTP.
"""

from __future__ import annotations

import asyncio
import math
import signal
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable, Optional, Sequence

from sqlalchemy import select

from app.core.logging import configure_logging, get_logger

logger = get_logger(__name__)

# Days-remaining thresholds at which to send a reminder. 0 == "expired".
WARNING_THRESHOLDS = (7, 3, 1)

# How often the sweep runs. Several times a day so a crossing is caught promptly
# while the Redis guard keeps each reminder one-shot.
CHECK_INTERVAL_SECONDS = 6 * 3600.0

# TTL for the per-(subscription, threshold) dedupe guard. Longer than the check
# interval so repeated sweeps on the same day don't resend.
_GUARD_TTL_SECONDS = 30 * 3600

SUB_STATUS_ACTIVE = "active"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(dt: datetime) -> datetime:
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt


def days_until(period_end: datetime, now: datetime) -> int:
    """Whole days remaining until ``period_end`` (ceil), negative once past."""
    delta = _aware(period_end) - now
    return math.ceil(delta.total_seconds() / 86400.0)


@dataclass(frozen=True)
class Reminder:
    """One reminder to send: which subscription, which threshold."""

    subscription_id: str
    org_id: str
    threshold: int  # 7/3/1 for warnings, 0 for expired
    days_left: int
    period_end: datetime
    device_count: int | None


def due_reminders(
    subscriptions: Iterable[Any], now: Optional[datetime] = None
) -> list[Reminder]:
    """Decide which reminders are due for the given subscriptions.

    Pure function (no DB/Redis): for each active subscription with a period end,
    emits a warning Reminder when days-left hits a threshold, or an expired
    Reminder (threshold 0) once the period end has passed.
    """
    now = now or _now()
    out: list[Reminder] = []
    for sub in subscriptions:
        end = getattr(sub, "current_period_end", None)
        if end is None:
            continue
        if (getattr(sub, "status", None) or "") != SUB_STATUS_ACTIVE:
            continue
        left = days_until(end, now)
        if left <= 0:
            threshold = 0
        else:
            # Fire when the subscription crosses INTO a threshold bucket: pick
            # the smallest threshold >= days-left (so 5 days left -> the "7"
            # bucket, 2 -> "3", 1 -> "1"). The Redis guard makes each bucket
            # one-shot, so this is robust to the exact time of day the sweep
            # runs, unlike requiring days-left to equal a threshold exactly.
            candidates = [t for t in WARNING_THRESHOLDS if left <= t]
            if not candidates:
                continue
            threshold = min(candidates)
        out.append(
            Reminder(
                subscription_id=str(getattr(sub, "id", "")),
                org_id=str(getattr(sub, "org_id", "")),
                threshold=threshold,
                days_left=left,
                period_end=_aware(end),
                device_count=getattr(sub, "device_count", None),
            )
        )
    return out


# ---------------------------------------------------------------------------
# Sweep (live DB + Redis + email)
# ---------------------------------------------------------------------------
async def _already_sent(redis: Any, reminder: Reminder) -> bool:
    """Mark this (subscription, threshold) reminder as sent; True if already was.

    Uses SET NX with a TTL as an atomic one-shot guard. If Redis is unavailable
    the reminder is allowed through (better a possible duplicate than silence).
    """
    if redis is None:
        return False
    key = f"iotaps:subexpiry:{reminder.subscription_id}:{reminder.threshold}"
    try:
        was_set = await redis.set(key, "1", nx=True, ex=_GUARD_TTL_SECONDS)
        return not bool(was_set)
    except Exception:  # pragma: no cover - guard must not break the sweep
        return False


async def sweep(session_factory: Any, redis: Any, *, now: Optional[datetime] = None) -> int:
    """Find due reminders and email them. Returns the count of emails attempted."""
    from app.models.billing import Subscription
    from app.services import email_service

    now = now or _now()
    async with session_factory() as session:
        rows = (
            await session.execute(
                select(Subscription).where(Subscription.status == SUB_STATUS_ACTIVE)
            )
        ).scalars().all()

        reminders = due_reminders(rows, now)
        sent = 0
        for reminder in reminders:
            if await _already_sent(redis, reminder):
                continue
            try:
                if reminder.threshold == 0:
                    await email_service.notify_subscription_expired(
                        session, reminder.org_id, period_end=reminder.period_end
                    )
                else:
                    await email_service.notify_subscription_expiring(
                        session,
                        reminder.org_id,
                        days_left=reminder.days_left,
                        period_end=reminder.period_end,
                        device_count=reminder.device_count,
                    )
                sent += 1
            except Exception:  # pragma: no cover - keep going on a bad row
                logger.warning(
                    "subscription_expiry_email_failed",
                    exc_info=True,
                    extra={"subscription_id": reminder.subscription_id},
                )
        if sent:
            logger.info("subscription_expiry_reminders_sent", extra={"count": sent})
        return sent


# ---------------------------------------------------------------------------
# Run loop + entry point
# ---------------------------------------------------------------------------
async def run(
    session_factory: Any,
    redis: Any,
    stop_event: Optional[asyncio.Event] = None,
    *,
    interval_seconds: float = CHECK_INTERVAL_SECONDS,
) -> None:
    """Run the expiry sweep on a fixed interval until ``stop_event`` is set."""
    stop_event = stop_event or asyncio.Event()
    while not stop_event.is_set():
        try:
            await sweep(session_factory, redis)
        except Exception:  # pragma: no cover - keep the worker alive
            logger.exception("subscription_expiry_sweep_failed")
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=interval_seconds)
        except asyncio.TimeoutError:
            pass


def main() -> None:  # pragma: no cover - process entry point
    """Process entry point (``python -m app.workers.subscription_expiry``)."""
    configure_logging()
    logger.info("subscription_expiry_starting")

    stop_event = asyncio.Event()

    async def _amain() -> None:
        from app.core.redis_client import get_redis
        from app.db.session import async_session_factory

        redis = get_redis()  # may be None; sweep tolerates it
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, stop_event.set)
            except NotImplementedError:  # Windows lacks add_signal_handler
                pass
        await run(async_session_factory, redis, stop_event)

    try:
        asyncio.run(_amain())
    except KeyboardInterrupt:
        pass
    logger.info("subscription_expiry_stopped")


if __name__ == "__main__":
    main()
