from __future__ import annotations

import asyncio
import logging
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.db.database import get_db
from app.db.models import LawArticle, LawUpdateLog
from app.main import limiter

router = APIRouter()
logger = logging.getLogger(__name__)

# Guard against concurrent trigger-update invocations
_update_lock = asyncio.Lock()


@router.get("/articles/{article_number}")
@limiter.limit("30/minute")
async def get_article(
    article_number: str,
    request: Request,
    law_id: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    from app.services.law_registry import VALID_LAW_IDS
    if law_id and law_id not in VALID_LAW_IDS:
        raise HTTPException(status_code=404, detail="法條不存在")

    stmt = select(LawArticle).where(
        LawArticle.article_number == article_number,
        LawArticle.is_active == True,
    )
    if law_id:
        stmt = stmt.where(LawArticle.law_id == law_id)
    article = (await db.execute(stmt)).scalar_one_or_none()
    if not article:
        raise HTTPException(status_code=404, detail="法條不存在")
    return {
        "article_number": article.article_number,
        "title": article.title,
        "content": article.content,
        "last_updated": article.last_updated,
        "version": article.version,
        "law_id": article.law_id,
        "law_name": article.law_name,
    }


@router.get("/law/status")
@limiter.limit("30/minute")
async def law_status(request: Request, db: AsyncSession = Depends(get_db)):
    stmt = select(LawUpdateLog).order_by(LawUpdateLog.updated_at.desc()).limit(1)
    log = (await db.execute(stmt)).scalar_one_or_none()
    count_stmt = select(func.count()).select_from(LawArticle).where(LawArticle.is_active == True)
    total = (await db.execute(count_stmt)).scalar()
    return {
        "last_updated": log.updated_at if log else None,
        "status": log.status if log else "never_run",
        "total_active_articles": total,
    }


@router.post("/law/trigger-update")
@limiter.limit("1/minute")
async def trigger_update(request: Request):
    """Manually trigger a law update — use this once to seed initial data."""
    if _update_lock.locked():
        raise HTTPException(status_code=409, detail="法條更新正在進行中，請稍後再試")

    from app.services.scheduler import run_law_update

    async def _guarded_update():
        async with _update_lock:
            await run_law_update()

    asyncio.create_task(_guarded_update())
    return {"message": "法條更新已觸發，請稍後查詢 /api/law/status 確認進度"}
