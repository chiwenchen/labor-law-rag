from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.db.database import get_db
from app.db.models import LawArticle, LawUpdateLog

router = APIRouter()


@router.get("/articles/{article_number}")
async def get_article(article_number: str, db: AsyncSession = Depends(get_db)):
    stmt = select(LawArticle).where(
        LawArticle.article_number == article_number,
        LawArticle.is_active == True,
    )
    article = (await db.execute(stmt)).scalar_one_or_none()
    if not article:
        raise HTTPException(status_code=404, detail="法條不存在")
    return {
        "article_number": article.article_number,
        "title": article.title,
        "content": article.content,
        "last_updated": article.last_updated,
        "version": article.version,
    }


@router.get("/law/status")
async def law_status(db: AsyncSession = Depends(get_db)):
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
async def trigger_update():
    """Manually trigger a law update — use this once to seed initial data."""
    import asyncio
    from app.services.scheduler import run_law_update
    asyncio.create_task(run_law_update())
    return {"message": "法條更新已觸發，請稍後查詢 /api/law/status 確認進度"}
