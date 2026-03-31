from __future__ import annotations

import logging
import random
import string
from datetime import datetime, timedelta, timezone
from typing import Literal
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, EmailStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.auth.store import (
    OtpEntry,
    SessionData,
    otp_store,
    pending_store,
    session_store,
)
from app.db.database import get_db
from app.db.models import User
from app.services.email_service import send_otp_email

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth")

OTP_TTL_MINUTES = 10
COOKIE_NAME = "session"


def _normalize_email(email: str) -> str:
    """正規化 email，防止 Gmail plus-addressing 和 dot-trick 繞過帳號唯一性。
    abc+1@gmail.com → abc@gmail.com
    a.b.c@gmail.com → abc@gmail.com
    """
    local, _, domain = email.lower().partition("@")
    if domain in {"gmail.com", "googlemail.com"}:
        local = local.split("+")[0]
        local = local.replace(".", "")
    else:
        local = local.split("+")[0]
    return f"{local}@{domain}"


def _generate_otp() -> str:
    return "".join(random.choices(string.digits, k=6))


def _set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        httponly=True,
        secure=True,
        samesite="lax",
    )


async def get_user_by_email(email: str, db: AsyncSession) -> User | None:
    return (await db.execute(select(User).where(User.email == email))).scalar_one_or_none()


# ---- Request / Response schemas ----

class SendOtpRequest(BaseModel):
    email: EmailStr


class VerifyOtpRequest(BaseModel):
    email: EmailStr
    otp: str


class RegisterRequest(BaseModel):
    pending_token: str
    role: Literal["hr", "employee"]


# ---- Endpoints ----

@router.post("/otp/send")
async def send_otp(request: SendOtpRequest):
    normalized = _normalize_email(request.email)
    otp = _generate_otp()
    otp_store[normalized] = OtpEntry(
        otp=otp,
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=OTP_TTL_MINUTES),
    )
    try:
        send_otp_email(request.email, otp)  # 寄信用原始 email，存儲用正規化後的
    except Exception as e:
        logger.error(f"Failed to send OTP email to {request.email}: {e}")
        raise HTTPException(status_code=502, detail="無法寄送驗證碼，請稍後再試")
    return {"detail": "驗證碼已寄出"}


@router.post("/otp/verify")
async def verify_otp(request: VerifyOtpRequest, response: Response, db: AsyncSession = Depends(get_db)):
    normalized = _normalize_email(request.email)
    entry = otp_store.get(normalized)
    if not entry:
        raise HTTPException(status_code=400, detail="驗證碼不存在，請重新申請")
    if datetime.now(timezone.utc) > entry.expires_at:
        del otp_store[normalized]
        raise HTTPException(status_code=400, detail="驗證碼已過期，請重新申請")
    if entry.otp != request.otp:
        raise HTTPException(status_code=400, detail="驗證碼錯誤")

    del otp_store[normalized]

    user = await get_user_by_email(normalized, db)
    if user is None:
        pending_token = str(uuid4())
        pending_store[pending_token] = normalized
        return {"is_new_user": True, "pending_token": pending_token}

    token = str(uuid4())
    session_store[token] = SessionData(user_id=user.id, email=user.email, role=user.role)
    _set_session_cookie(response, token)
    return {"is_new_user": False}


@router.post("/register")
async def register(request: RegisterRequest, response: Response, db: AsyncSession = Depends(get_db)):
    email = pending_store.get(request.pending_token)
    if not email:
        raise HTTPException(status_code=400, detail="無效的註冊憑證，請重新驗證 OTP")

    user = User(email=email, role=request.role)
    db.add(user)
    await db.commit()
    await db.refresh(user)

    del pending_store[request.pending_token]

    token = str(uuid4())
    session_store[token] = SessionData(user_id=user.id, email=user.email, role=user.role)
    _set_session_cookie(response, token)
    return {"detail": "註冊成功"}


@router.post("/logout")
async def logout(request: Request, response: Response):
    token = request.cookies.get(COOKIE_NAME)
    if token and token in session_store:
        del session_store[token]
    response.delete_cookie(key=COOKIE_NAME)
    return {"detail": "已登出"}


@router.get("/me")
async def get_me(user: SessionData = Depends(get_current_user)):
    return {"email": user.email, "role": user.role}
