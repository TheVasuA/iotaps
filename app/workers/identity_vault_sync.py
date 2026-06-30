"""Identity_Vault_Sync worker — periodic full mirror of identity data.

Runs :func:`app.services.identity_vault.resync_all` on a fixed interval so the
off-VPS MongoDB mirror of users, device credentials, and devices stays complete
and current (at most one interval stale) regardless of which code paths created
or changed the rows. Real-time hooks in the device service keep the most
security-relevant records fresh between sweeps.

No-op when ``MONGODB_URI`` is unset (the worker idles), so it's safe to run
unconditionally under supervisor.
"""

from __future__ import annotations

import asyncio
import signal
from typing import Any, Optional

from app.core.config import get_settings
from app.core.logging import configure_logging, get_logger

logger = get_logger(__name__)


async def run(
    session_factory: Any,
    stop_event: Optional[asyncio.Event] = None,
    *,
    interval_seconds: Optional[float] = None,
) -> None:
    """Run a full identity re-sync on a fixed interval until stopped."""
    from app.services import identity_vault

    stop_event = stop_event or asyncio.Event()
    interval = interval_seconds or get_settings().mongodb_sync_interval_seconds

    while not stop_event.is_set():
        if get_settings().mongodb_enabled:
            try:
                async with session_factory() as session:
                    await identity_vault.resync_all(session)
            except Exception:  # pragma: no cover - keep the worker alive
                logger.exception("identity_vault_sync_failed")
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=interval)
        except asyncio.TimeoutError:
            pass


def main() -> None:  # pragma: no cover - process entry point
    """Process entry point (``python -m app.workers.identity_vault_sync``)."""
    configure_logging()
    logger.info("identity_vault_sync_starting")

    stop_event = asyncio.Event()

    async def _amain() -> None:
        from app.db.session import async_session_factory

        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, stop_event.set)
            except NotImplementedError:  # Windows lacks add_signal_handler
                pass
        await run(async_session_factory, stop_event)

    try:
        asyncio.run(_amain())
    except KeyboardInterrupt:
        pass
    logger.info("identity_vault_sync_stopped")


if __name__ == "__main__":
    main()
