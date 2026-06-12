"""APScheduler — fires the daily Telegram briefing at BRIEFING_TIME local time.

APScheduler defaults to UTC; timezone MUST be set explicitly (see CLAUDE.md).
"""
import logging
import os

from apscheduler.schedulers.asyncio import AsyncIOScheduler

logger = logging.getLogger("dashboard.scheduler")

_scheduler: AsyncIOScheduler | None = None


async def _fire_briefing():
    from .telegram_bot import send_daily_briefing
    await send_daily_briefing()


def start_scheduler() -> None:
    global _scheduler
    tz = os.environ.get("TZ", "America/Los_Angeles")
    briefing_time = os.environ.get("BRIEFING_TIME", "07:30")
    try:
        hour, minute = (int(x) for x in briefing_time.split(":"))
    except ValueError:
        logger.error("Bad BRIEFING_TIME %r — falling back to 07:30", briefing_time)
        hour, minute = 7, 30

    _scheduler = AsyncIOScheduler(timezone=tz)
    _scheduler.add_job(_fire_briefing, "cron", hour=hour, minute=minute,
                       id="daily_briefing")
    _scheduler.start()
    logger.info("Scheduler started — briefing daily at %02d:%02d %s",
                hour, minute, tz)


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler:
        _scheduler.shutdown(wait=False)
        _scheduler = None
