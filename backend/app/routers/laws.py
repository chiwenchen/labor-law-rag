from __future__ import annotations
import logging
import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.db.database import get_db
from app.db.models import LawUpdateLog, SupportedLaw
from app.services.law_registry import LAW_REGISTRY, get_law_by_id
from app.main import limiter
from app.auth.dependencies import get_current_user, require_access_role
from app.auth.store import SessionData

router = APIRouter()
logger = logging.getLogger(__name__)

# Ordered list of law_ids from registry (for consistent response ordering)
_REGISTRY_ORDER = {law.law_id: i for i, law in enumerate(LAW_REGISTRY)}


@router.get("/laws")
@limiter.limit("30/minute")
async def list_laws(request: Request, db: AsyncSession = Depends(get_db)):
    """Return all supported laws with their current status."""
    stmt = select(SupportedLaw)
    laws = (await db.execute(stmt)).scalars().all()
    sorted_laws = sorted(laws, key=lambda l: _REGISTRY_ORDER.get(l.law_id, 999))
    return [
        {
            "law_id": l.law_id,
            "law_name": l.law_name,
            "article_count": l.article_count,
            "last_updated": l.last_updated,
            "last_status": l.last_status,
        }
        for l in sorted_laws
    ]


_require_admin_or_hr = require_access_role("admin", "hr")


@router.post("/laws/{law_id}/update")
@limiter.limit("2/minute")
async def update_law(
    law_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: SessionData = Depends(_require_admin_or_hr),
):
    """Fetch and re-embed articles for one law.

    Synchronous long-poll: takes 30–120 seconds depending on article count.
    Frontend should use a 180-second timeout for this request.
    """
    law_info = get_law_by_id(law_id)
    if law_info is None:
        raise HTTPException(status_code=404, detail="Law not found in registry")

    from app.services.fetcher import fetch_law
    from app.services.indexer import upsert_articles

    # Fetch articles
    try:
        articles = await fetch_law(law_info.law_id, law_info.law_name)
    except (httpx.HTTPStatusError, httpx.RequestError) as e:
        supported_law = (await db.execute(
            select(SupportedLaw).where(SupportedLaw.law_id == law_id)
        )).scalar_one_or_none()
        if supported_law:
            supported_law.last_status = "failed"
        # Write failure audit log
        log = LawUpdateLog(
            law_id=law_id,
            articles_changed=0,
            status="failed",
            error_message=str(e)[:500],
        )
        db.add(log)
        await db.commit()
        logger.error(f"[{law_id}] Fetch failed: {e}")
        raise HTTPException(status_code=502, detail="法規來源暫時無法取得，請稍後再試")

    # Index articles (also updates supported_laws)
    index_result = await upsert_articles(articles, db, law_info.law_id, law_info.law_name)

    # Write audit log
    log = LawUpdateLog(
        law_id=law_id,
        articles_changed=index_result.inserted + index_result.updated,
        status="success",
    )
    db.add(log)
    await db.commit()

    # Return current article count from supported_laws
    supported_law = (await db.execute(
        select(SupportedLaw).where(SupportedLaw.law_id == law_id)
    )).scalar_one_or_none()
    article_count = supported_law.article_count if supported_law else len(articles)

    logger.info(f"[{law_id}] Manual update complete: count={article_count}")
    return {
        "status": "success",
        "article_count": article_count,
        "message": f"已更新 {law_info.law_name}（+{index_result.inserted} 新增 / ~{index_result.updated} 更新）",
    }
