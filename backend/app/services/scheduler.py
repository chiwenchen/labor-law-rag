import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from app.db.database import AsyncSessionLocal
from app.db.models import LawUpdateLog, SupportedLaw
from app.services.law_registry import LAW_REGISTRY
from app.services.fetcher import fetch_law
from app.services.indexer import upsert_articles
from sqlalchemy import select

logger = logging.getLogger(__name__)
scheduler = AsyncIOScheduler()


async def run_law_update(law_id: str | None = None):
    """Update one law (by law_id) or all laws (law_id=None).

    Writes one LawUpdateLog entry per law processed.
    """
    laws_to_update = (
        [law for law in LAW_REGISTRY if law.law_id == law_id]
        if law_id
        else list(LAW_REGISTRY)
    )

    for law_info in laws_to_update:
        logger.info(f"Updating {law_info.law_name} ({law_info.law_id})...")
        async with AsyncSessionLocal() as db:
            try:
                articles = await fetch_law(law_info.law_id, law_info.law_name)
                result = await upsert_articles(articles, db, law_info.law_id, law_info.law_name)
                log = LawUpdateLog(
                    law_id=law_info.law_id,
                    articles_changed=result.inserted + result.updated,
                    status="success",
                )
                logger.info(
                    f"[{law_info.law_id}] done: +{result.inserted} ~{result.updated}"
                )
            except Exception as e:
                log = LawUpdateLog(
                    law_id=law_info.law_id,
                    status="failed",
                    error_message=str(e),
                )
                # Mark supported_laws as failed
                try:
                    sl = (await db.execute(
                        select(SupportedLaw).where(SupportedLaw.law_id == law_info.law_id)
                    )).scalar_one_or_none()
                    if sl:
                        sl.last_status = "failed"
                except Exception:
                    pass
                logger.error(f"[{law_info.law_id}] failed: {e}")
            finally:
                try:
                    db.add(log)
                    await db.commit()
                except Exception as log_err:
                    logger.error(f"Failed to write update log: {log_err}")


def start_scheduler():
    scheduler.add_job(run_law_update, "cron", day_of_week="mon", hour=2, minute=0)
    scheduler.start()
    logger.info("Scheduler started — law update runs every Monday at 02:00")
