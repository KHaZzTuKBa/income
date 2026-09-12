import asyncio
import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import text

from app.db import SessionLocal

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


async def main() -> None:
    scheduler = AsyncIOScheduler(timezone="Europe/Moscow")
    scheduler.add_job(heartbeat, "interval", minutes=5, id="heartbeat")
    scheduler.start()
    logger.info("worker started")
    await heartbeat()
    await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(main())
