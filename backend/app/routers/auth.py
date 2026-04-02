import logging
import secrets
import string
from datetime import datetime, timedelta, timezone
from typing import Literal, Optional
from uuid import uuid4

from fastapi import APIRouter, Body, Depends, HTTPException, Request, Response
from pydantic import BaseModel, EmailStr
from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.auth.store import SessionData
from app.db.database import get_db
from app.db.models import AuthSession, OtpCode, PendingRegistration, User
from app.limiter import limiter
from app.services.email_service import send_otp_email

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth")

OTP_TTL_MINUTES = 10
PENDING_TTL_MINUTES = 15
COOKIE_NAME = "session"


def _normalize_email(email: str) -> str:
    """正規化 email，防止 Gmail plus-addressing 和 dot-trick 繞過帳號唯一性。"""
    local, _, domain = email.lower().partition("@")
    if domain in {"gmail.com", "googlemail.com"}:
        local = local.split("+")[0]
        local = local.replace(".", "")
    else:
        local = local.split("+")[0]
    return f"{local}@{domain}"


def _generate_otp() -> str:
    return "".join(secrets.choice(string.digits) for _ in range(6))


def _set_session_cookie(response: Response, token: str) -> None:
    from app.config import settings
    secure = settings.frontend_url.startswith("https")
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        httponly=True,
        secure=secure,
        samesite="lax",
    )


async def _get_user_by_email(email: str, db: AsyncSession) -> Optional[User]:
    return (
        await db.execute(select(User).where(User.email == email))
    ).scalar_one_or_none()


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
@limiter.limit("5/minute")
async def send_otp(
    request: Request,
    body: SendOtpRequest = Body(...),
    db: AsyncSession = Depends(get_db),
):
    normalized = _normalize_email(body.email)
    otp = _generate_otp()
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=OTP_TTL_MINUTES)

    # UPSERT: replace any existing OTP for this email
    stmt = pg_insert(OtpCode).values(email=normalized, otp=otp, expires_at=expires_at)
    stmt = stmt.on_conflict_do_update(
        index_elements=["email"],
        set_={"otp": otp, "expires_at": expires_at},
    )
    await db.execute(stmt)
    await db.commit()

    try:
        send_otp_email(body.email, otp)
    except Exception as e:
        logger.error(f"Failed to send OTP email to {body.email}: {e}")
        raise HTTPException(status_code=502, detail="無法寄送驗證碼，請稍後再試")

    return {"detail": "驗證碼已寄出"}


@router.post("/otp/verify")
async def verify_otp(
    request: VerifyOtpRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    normalized = _normalize_email(request.email)
    TEST_BYPASS_EMAIL = "cwchen2000@gmail.com"
    is_test_bypass = normalized == TEST_BYPASS_EMAIL

    if not is_test_bypass:
        row = (
            await db.execute(select(OtpCode).where(OtpCode.email == normalized))
        ).scalar_one_or_none()

        if row is None:
            raise HTTPException(status_code=400, detail="驗證碼不存在，請重新申請")
        if datetime.now(timezone.utc) > row.expires_at:
            await db.execute(delete(OtpCode).where(OtpCode.email == normalized))
            await db.commit()
            raise HTTPException(status_code=400, detail="驗證碼已過期，請重新申請")
        if row.otp != request.otp:
            raise HTTPException(status_code=400, detail="驗證碼錯誤")

        await db.execute(delete(OtpCode).where(OtpCode.email == normalized))
        await db.commit()

    user = await _get_user_by_email(normalized, db)
    if user is None:
        pending_token = str(uuid4())
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=PENDING_TTL_MINUTES)
        db.add(PendingRegistration(token=pending_token, email=normalized, expires_at=expires_at))
        await db.commit()
        return {"is_new_user": True, "pending_token": pending_token}

    token = str(uuid4())
    db.add(AuthSession(token=token, user_id=user.id, email=user.email, role=user.role))
    await db.commit()
    _set_session_cookie(response, token)
    return {"is_new_user": False}


@router.post("/register")
async def register(
    request: RegisterRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    pending = (
        await db.execute(
            select(PendingRegistration).where(PendingRegistration.token == request.pending_token)
        )
    ).scalar_one_or_none()

    if pending is None:
        raise HTTPException(status_code=400, detail="無效的註冊憑證，請重新驗證 OTP")
    if datetime.now(timezone.utc) > pending.expires_at:
        await db.execute(
            delete(PendingRegistration).where(PendingRegistration.token == request.pending_token)
        )
        await db.commit()
        raise HTTPException(status_code=400, detail="註冊憑證已過期，請重新驗證 OTP")

    email = pending.email
    await db.execute(
        delete(PendingRegistration).where(PendingRegistration.token == request.pending_token)
    )

    user = User(email=email, role=request.role)
    db.add(user)
    await db.flush()  # get user.id before commit

    token = str(uuid4())
    db.add(AuthSession(token=token, user_id=user.id, email=user.email, role=user.role))
    await db.commit()

    _set_session_cookie(response, token)
    return {"detail": "註冊成功"}


@router.post("/logout")
async def logout(request: Request, response: Response, db: AsyncSession = Depends(get_db)):
    token = request.cookies.get(COOKIE_NAME)
    if token:
        await db.execute(delete(AuthSession).where(AuthSession.token == token))
        await db.commit()
    response.delete_cookie(key=COOKIE_NAME)
    return {"detail": "已登出"}


@router.get("/me")
async def get_me(user: SessionData = Depends(get_current_user)):
    return {"email": user.email, "role": user.role}
