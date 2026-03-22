import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.database import AsyncSessionLocal
from app.db.models import LawUpdateLog
from app.services.fetcher import fetch_labor_law_articles
from app.services.indexer import upsert_articles

logger = logging.getLogger(__name__)
scheduler = AsyncIOScheduler()

async def run_law_update():
    logger.info("Starting weekly law update...")
    log = None
    async with AsyncSessionLocal() as db:
        try:
            articles = await fetch_labor_law_articles()
            result = await upsert_articles(articles, db)
            log = LawUpdateLog(
                articles_changed=result.inserted + result.updated,
                status="success",
            )
            logger.info(f"Law update complete: +{result.inserted} ~{result.updated} skip{result.skipped}")
        except Exception as e:
            log = LawUpdateLog(status="failed", error_message=str(e))
            logger.error(f"Law update failed: {e}")
        finally:
            if log is not None:
                try:
                    db.add(log)
                    await db.commit()
                except Exception as log_err:
                    logger.error(f"Failed to write update log: {log_err}")

def start_scheduler():
    scheduler.add_job(run_law_update, "cron", day_of_week="mon", hour=2, minute=0)
    scheduler.start()
    logger.info("Scheduler started — law update runs every Monday at 02:00")
