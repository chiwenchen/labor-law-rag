from __future__ import annotations

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import require_access_role
from app.auth.store import SessionData
from app.db.database import get_db
from app.db.models import QueryHistory, Session, User

router = APIRouter()

_require_admin = require_access_role("admin")

ALLOWED_ACCESS_ROLES = {"admin", "hr", "employee"}


# ---- Request / Response schemas ----


class UpdateCreditsRequest(BaseModel):
    credits: int = Field(..., ge=0)


class UpdateAccessRoleRequest(BaseModel):
    access_role: str


# ---- Endpoints ----


@router.get("/users")
async def list_users(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    user: SessionData = Depends(_require_admin),
):
    """Paginated list of all users with session count and last query time."""
    offset = (page - 1) * limit

    # Subquery: session count per user
    session_count_sq = (
        select(
            Session.user_id,
            func.count(Session.id).label("session_count"),
        )
        .group_by(Session.user_id)
        .subquery()
    )

    # Subquery: last query time per user (via sessions -> query_history)
    last_query_sq = (
        select(
            Session.user_id,
            func.max(QueryHistory.created_at).label("last_query_at"),
        )
        .join(QueryHistory, QueryHistory.session_id == Session.id)
        .group_by(Session.user_id)
        .subquery()
    )

    stmt = (
        select(
            User.id,
            User.email,
            User.role,
            User.access_role,
            User.credits,
            User.created_at,
            func.coalesce(session_count_sq.c.session_count, 0).label("session_count"),
            last_query_sq.c.last_query_at,
        )
        .outerjoin(session_count_sq, User.id == session_count_sq.c.user_id)
        .outerjoin(last_query_sq, User.id == last_query_sq.c.user_id)
        .order_by(User.created_at.desc())
        .offset(offset)
        .limit(limit)
    )

    rows = (await db.execute(stmt)).all()

    total = (await db.execute(select(func.count()).select_from(User))).scalar() or 0

    return {
        "users": [
            {
                "id": str(r.id),
                "email": r.email,
                "role": r.role,
                "access_role": r.access_role,
                "credits": r.credits,
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "session_count": r.session_count,
                "last_query_at": r.last_query_at.isoformat() if r.last_query_at else None,
            }
            for r in rows
        ],
        "total": total,
        "page": page,
        "limit": limit,
    }


@router.get("/users/{user_id}/sessions")
async def list_user_sessions(
    user_id: UUID,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    user: SessionData = Depends(_require_admin),
):
    """Paginated list of sessions for a specific user with query counts."""
    offset = (page - 1) * limit

    # Subquery: query count per session
    query_count_sq = (
        select(
            QueryHistory.session_id,
            func.count(QueryHistory.id).label("query_count"),
        )
        .group_by(QueryHistory.session_id)
        .subquery()
    )

    stmt = (
        select(
            Session.id,
            Session.title,
            Session.created_at,
            func.coalesce(query_count_sq.c.query_count, 0).label("query_count"),
        )
        .outerjoin(query_count_sq, Session.id == query_count_sq.c.session_id)
        .where(Session.user_id == user_id)
        .order_by(Session.created_at.desc())
        .offset(offset)
        .limit(limit)
    )

    rows = (await db.execute(stmt)).all()

    total = (
        await db.execute(
            select(func.count()).select_from(Session).where(Session.user_id == user_id)
        )
    ).scalar() or 0

    return {
        "sessions": [
            {
                "id": str(r.id),
                "title": r.title,
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "query_count": r.query_count,
            }
            for r in rows
        ],
        "total": total,
        "page": page,
        "limit": limit,
    }


@router.patch("/users/{user_id}/credits")
async def update_user_credits(
    user_id: UUID,
    body: UpdateCreditsRequest,
    db: AsyncSession = Depends(get_db),
    user: SessionData = Depends(_require_admin),
):
    """Update a user's credits."""
    target = (
        await db.execute(select(User).where(User.id == user_id))
    ).scalar_one_or_none()

    if target is None:
        raise HTTPException(status_code=404, detail="User not found")

    await db.execute(
        update(User).where(User.id == user_id).values(credits=body.credits)
    )
    await db.commit()

    # Refresh to return updated state
    await db.refresh(target)

    return {
        "id": str(target.id),
        "email": target.email,
        "role": target.role,
        "access_role": target.access_role,
        "credits": target.credits,
    }


@router.patch("/users/{user_id}/access-role")
async def update_user_access_role(
    user_id: UUID,
    body: UpdateAccessRoleRequest,
    db: AsyncSession = Depends(get_db),
    user: SessionData = Depends(_require_admin),
):
    """Update a user's access role."""
    if body.access_role not in ALLOWED_ACCESS_ROLES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid access_role. Allowed: {', '.join(sorted(ALLOWED_ACCESS_ROLES))}",
        )

    target = (
        await db.execute(select(User).where(User.id == user_id))
    ).scalar_one_or_none()

    if target is None:
        raise HTTPException(status_code=404, detail="User not found")

    await db.execute(
        update(User).where(User.id == user_id).values(access_role=body.access_role)
    )
    await db.commit()

    await db.refresh(target)

    return {
        "id": str(target.id),
        "email": target.email,
        "role": target.role,
        "access_role": target.access_role,
        "credits": target.credits,
    }
