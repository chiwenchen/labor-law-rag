from __future__ import annotations

from typing import Callable

from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.store import SessionData
from app.db.database import get_db
from app.db.models import AuthSession


async def get_current_user(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> SessionData:
    """Look up the session cookie in auth_sessions; raise 401 if missing or invalid."""
    token = request.cookies.get("session")
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")

    row = (
        await db.execute(select(AuthSession).where(AuthSession.token == token))
    ).scalar_one_or_none()

    if row is None:
        raise HTTPException(status_code=401, detail="Not authenticated")

    return SessionData(
        user_id=row.user_id,
        email=row.email,
        role=row.role,
        access_role=row.access_role,
    )


def require_access_role(*allowed_roles: str) -> Callable:
    """FastAPI dependency factory that checks the user's access_role against allowed roles."""

    async def _check(user: SessionData = Depends(get_current_user)) -> SessionData:
        if user.access_role not in allowed_roles:
            raise HTTPException(status_code=403, detail="權限不足")
        return user

    return _check
