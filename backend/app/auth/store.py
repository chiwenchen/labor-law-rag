from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime
from typing import Literal
from uuid import UUID


@dataclass
class OtpEntry:
    otp: str
    expires_at: datetime


@dataclass
class SessionData:
    user_id: UUID
    email: str
    role: Literal["hr", "employee"]


# Key = email（正規化後）
otp_store: dict[str, OtpEntry] = {}

# Key = pending_token (UUID str), Value = email（正規化後）
pending_store: dict[str, str] = {}

# Key = session token (UUID str)
session_store: dict[str, SessionData] = {}
