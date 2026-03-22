from __future__ import annotations
import uuid
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.database import get_db
from app.db.models import Session, QueryHistory
from app.services.rag import query_law
from app.services.law_registry import VALID_LAW_IDS

router = APIRouter()


class QueryRequest(BaseModel):
    question: str
    session_id: Optional[str] = None
    law_ids: Optional[list[str]] = None


@router.post("/query")
async def handle_query(request: QueryRequest, db: AsyncSession = Depends(get_db)):
    if len(request.question) > 500:
        raise HTTPException(status_code=400, detail="問題長度不得超過 500 字")

    # Whitelist law_ids against registry — silently drop unknown IDs
    safe_law_ids = (
        [lid for lid in request.law_ids if lid in VALID_LAW_IDS]
        if request.law_ids
        else []
    )

    # Get or create session
    if request.session_id:
        try:
            session_id = uuid.UUID(request.session_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid session_id format")
    else:
        title = request.question[:20]
        session = Session(title=title)
        db.add(session)
        await db.flush()
        session_id = session.id

    result = await query_law(
        request.question,
        db,
        law_ids=safe_law_ids if safe_law_ids else None,
    )

    history = QueryHistory(
        session_id=session_id,
        question=request.question,
        answer=result.answer,
        cited_articles=result.cited_articles,
        max_similarity_score=(
            result.cited_articles[0]["similarity"] if result.cited_articles else None
        ),
    )
    db.add(history)
    await db.commit()

    return {
        "session_id": str(session_id),
        "is_out_of_scope": result.is_out_of_scope,
        "answer": result.answer,
        "warning": result.warning,
        "cited_articles": result.cited_articles,
    }
