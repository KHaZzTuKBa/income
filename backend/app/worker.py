import asyncio
import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import text

from app.db import SessionLocal
from app.services.calendar import refresh_all_forecasts
from app.services.portfolio import refresh_stored_prices
from app.services.sync import run_scheduled_sync

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger("portfel.worker")


async def heartbeat() -> None:
    try:
        async with SessionLocal() as session:
            await session.execute(text("SELECT 1"))
        logger.info("heartbeat ok")
    except Exception:
        logger.exception("heartbeat failed")


async def scheduled_sync() -> None:
    try:
        logger.info("scheduled sync started")
        await run_scheduled_sync()
        await refresh_all_forecasts()
        logger.info("scheduled sync finished")
    except Exception:
        logger.exception("scheduled sync failed")


async def scheduled_prices() -> None:
    try:
        await refresh_stored_prices()
    except Exception:
        logger.exception("price refresh failed")


async def main() -> None:
    scheduler = AsyncIOScheduler(timezone="Europe/Moscow")
    scheduler.add_job(heartbeat, "interval", minutes=5, id="heartbeat")
    scheduler.add_job(scheduled_prices, "interval", minutes=5, id="live_prices")
    scheduler.add_job(
        scheduled_sync,
        CronTrigger(hour="8,20", minute=0, timezone="Europe/Moscow"),
        id="tinkoff_sync",
    )
    scheduler.start()
    logger.info("worker started")
    await heartbeat()
    await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(main())
