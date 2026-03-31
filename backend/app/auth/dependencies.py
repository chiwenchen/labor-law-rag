from __future__ import annotations

from fastapi import HTTPException, Request

from app.auth.store import SessionData, session_store


async def get_current_user(request: Request) -> SessionData:
    """從 httpOnly cookie 取得 session，回傳 SessionData。未登入則拋出 401。"""
    token = request.cookies.get("session")
    if not token or token not in session_store:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return session_store[token]
