import json
import uuid
from typing import Literal, Optional
from fastapi import APIRouter, Body, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.auth.dependencies import get_current_user
from app.auth.store import SessionData
from app.db.database import get_db, AsyncSessionLocal
from app.db.models import Session, QueryHistory
from app.services.rag import query_law, stream_query_law
from app.services.law_registry import VALID_LAW_IDS
from app.limiter import limiter

router = APIRouter()


class HistoryMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(max_length=2000)


class QueryRequest(BaseModel):
    question: str
    session_id: Optional[str] = None
    law_ids: Optional[list[str]] = None
    history: Optional[list[HistoryMessage]] = Field(default=None, max_length=20)


@router.post("/query")
@limiter.limit("10/minute")
async def handle_query(
    request: Request,
    body: QueryRequest = Body(...),
    db: AsyncSession = Depends(get_db),
    user: SessionData = Depends(get_current_user),
):
    if len(body.question) > 500:
        raise HTTPException(status_code=400, detail="問題長度不得超過 500 字")

    # Whitelist law_ids against registry — silently drop unknown IDs
    safe_law_ids = (
        [lid for lid in body.law_ids if lid in VALID_LAW_IDS]
        if body.law_ids
        else []
    )

    # Get or create session
    if body.session_id:
        try:
            session_id = uuid.UUID(body.session_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid session_id format")
        # Validate session exists
        existing_session = (await db.execute(
            select(Session).where(Session.id == session_id)
        )).scalar_one_or_none()
        if existing_session is None:
            raise HTTPException(status_code=404, detail="Session not found")
    else:
        title = body.question[:20]
        session = Session(title=title, user_id=user.user_id)
        db.add(session)
        await db.flush()
        session_id = session.id

    conv_history = (
        [{"role": m.role, "content": m.content} for m in body.history]
        if body.history else None
    )

    result = await query_law(
        body.question,
        db,
        law_ids=safe_law_ids if safe_law_ids else None,
        history=conv_history,
        role=user.role,
    )

    history = QueryHistory(
        session_id=session_id,
        question=body.question,
        answer=result.answer,
        cited_articles=result.cited_articles,
        max_similarity_score=(
            result.cited_articles[0].get("similarity") if result.cited_articles else None
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


@router.post("/query/stream")
@limiter.limit("10/minute")
async def handle_query_stream(
    request: Request,
    body: QueryRequest = Body(...),
    db: AsyncSession = Depends(get_db),
    user: SessionData = Depends(get_current_user),
):
    if len(body.question) > 500:
        raise HTTPException(status_code=400, detail="問題長度不得超過 500 字")

    safe_law_ids = (
        [lid for lid in body.law_ids if lid in VALID_LAW_IDS]
        if body.law_ids
        else []
    )

    # Create/validate session before streaming — commit immediately so the
    # session row exists before the streaming generator runs in its own DB session.
    if body.session_id:
        try:
            session_id = uuid.UUID(body.session_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid session_id format")
        existing_session = (await db.execute(
            select(Session).where(Session.id == session_id)
        )).scalar_one_or_none()
        if existing_session is None:
            raise HTTPException(status_code=404, detail="Session not found")
    else:
        title = body.question[:20]
        session = Session(title=title, user_id=user.user_id)
        db.add(session)
        await db.flush()
        session_id = session.id
        await db.commit()  # Commit now — get_db closes the session after the route returns

    law_ids_arg = safe_law_ids if safe_law_ids else None
    conv_history = (
        [{"role": m.role, "content": m.content} for m in body.history]
        if body.history else None
    )
    question = body.question
    user_role = user.role

    async def event_stream():
        # Use a fresh session independent of the request's get_db lifecycle
        async with AsyncSessionLocal() as fresh_db:
            async for event in stream_query_law(
                question,
                fresh_db,
                law_ids=law_ids_arg,
                history=conv_history,
                role=user_role,
            ):
                if event["type"] in ("done", "out_of_scope"):
                    event["session_id"] = str(session_id)
                    cited = event.get("cited_articles", [])
                    history = QueryHistory(
                        session_id=session_id,
                        question=question,
                        answer=event.get("answer"),
                        cited_articles=cited,
                        max_similarity_score=(
                            cited[0].get("similarity") if cited else None
                        ),
                    )
                    fresh_db.add(history)
                    await fresh_db.commit()

                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
