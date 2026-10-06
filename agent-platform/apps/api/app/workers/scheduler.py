"""Scheduler entrypoint: `python -m app.workers.scheduler`.

Only enqueues work. Safe to run several instances (see app.scheduler.sweeps).
"""

from __future__ import annotations

import asyncio
import signal
from collections.abc import Awaitable, Callable

from app.core.config import get_settings
from app.core.logging import configure_logging, get_logger
from app.db.session import dispose_engine
from app.scheduler.sweeps import expire_approvals, fire_due_schedules, recover_stale_executions, wake_due_timers
from app.workers.queue import ArqQueue

log = get_logger(__name__)


async def _every(interval_s: float, name: str, fn: Callable[[], Awaitable[int]], stop: asyncio.Event) -> None:
    while not stop.is_set():
        try:
            count = await fn()
            if count:
                log.info("sweep", sweep=name, count=count)
        except Exception as exc:  # noqa: BLE001 - keep sweeping
            log.warning("sweep_failed", sweep=name, error=str(exc))
        try:
            await asyncio.wait_for(stop.wait(), timeout=interval_s)
        except TimeoutError:
            pass


async def run() -> None:
    settings = get_settings()
    configure_logging(settings.log_level, settings.log_json)
    queue = ArqQueue()
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop.set)
    log.info("scheduler_started")
    await asyncio.gather(
        _every(5, "schedules", lambda: fire_due_schedules(queue), stop),
        _every(10, "timers", lambda: wake_due_timers(queue), stop),
        _every(15, "recovery", lambda: recover_stale_executions(queue), stop),
        _every(60, "approval_expiry", lambda: expire_approvals(queue), stop),
    )
    await queue.close()
    await dispose_engine()


if __name__ == "__main__":
    asyncio.run(run())
