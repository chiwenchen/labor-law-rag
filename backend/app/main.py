from __future__ import annotations
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routers import query, sessions, articles, laws, auth

logger = logging.getLogger(__name__)


async def _seed_supported_laws():
    """Ensure supported_laws has a row for every law in the registry.

    For pre-existing 勞動基準法 rows in law_articles, counts actual articles
    so the table shows the real count without requiring a manual re-index.
    """
    from app.db.database import AsyncSessionLocal
    from app.db.models import LawArticle, SupportedLaw
    from app.services.law_registry import LAW_REGISTRY
    from sqlalchemy import select, func

    async with AsyncSessionLocal() as db:
        for law_info in LAW_REGISTRY:
            existing = (await db.execute(
                select(SupportedLaw).where(SupportedLaw.law_id == law_info.law_id)
            )).scalar_one_or_none()
            if existing:
                continue
            # Count real articles for this law already in DB (e.g. 勞動基準法 from before migration)
            count = (await db.execute(
                select(func.count()).select_from(LawArticle).where(
                    LawArticle.law_id == law_info.law_id,
                    LawArticle.is_active == True,
                )
            )).scalar() or 0
            db.add(SupportedLaw(
                law_id=law_info.law_id,
                law_name=law_info.law_name,
                article_count=count,
                last_status="success" if count > 0 else "never_run",
            ))
        await db.commit()
    logger.info("supported_laws seeded")


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        await _seed_supported_laws()
    except Exception as e:
        logger.error(f"Failed to seed supported_laws: {e}")

    from app.services.scheduler import start_scheduler, scheduler
    try:
        start_scheduler()
    except Exception as e:
        logger.error(f"Failed to start scheduler: {e}")
    yield
    try:
        scheduler.shutdown()
    except Exception:
        pass


app = FastAPI(title="勞動法規 RAG API", lifespan=lifespan)

from app.config import settings

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_url, "http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=True,
)

app.include_router(query.router, prefix="/api")
app.include_router(sessions.router, prefix="/api")
app.include_router(articles.router, prefix="/api")
app.include_router(laws.router, prefix="/api")
app.include_router(auth.router, prefix="/api")
