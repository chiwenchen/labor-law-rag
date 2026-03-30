from __future__ import annotations

import resend

from app.config import settings


def send_otp_email(to_email: str, otp: str) -> None:
    resend.api_key = settings.resend_api_key
    resend.Emails.send({
        "from": settings.email_from,
        "to": to_email,
        "subject": "勞基法查詢系統 — 驗證碼",
        "text": f"你的驗證碼為：{otp}\n\n此驗證碼將於 10 分鐘後失效，請勿分享給他人。",
    })
