from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.db.database import get_db
from app.db.models import Session, QueryHistory

router = APIRouter()


@router.get("/sessions")
async def list_sessions(db: AsyncSession = Depends(get_db)):
    stmt = select(Session).order_by(Session.created_at.desc()).limit(50)
    sessions = (await db.execute(stmt)).scalars().all()
    return [{"id": str(s.id), "title": s.title, "created_at": s.created_at} for s in sessions]


@router.get("/sessions/{session_id}/history")
async def get_session_history(session_id: str, db: AsyncSession = Depends(get_db)):
    stmt = select(QueryHistory).where(
        QueryHistory.session_id == session_id
    ).order_by(QueryHistory.created_at.asc())
    history = (await db.execute(stmt)).scalars().all()
    return [
        {
            "id": h.id,
            "question": h.question,
            "answer": h.answer,
            "cited_articles": h.cited_articles,
            "max_similarity_score": h.max_similarity_score,
            "created_at": h.created_at,
        }
        for h in history
    ]
