from __future__ import annotations
from dataclasses import dataclass
from typing import Literal
from uuid import UUID


@dataclass
class SessionData:
    user_id: UUID
    email: str
    role: Literal["hr", "employee"]
    access_role: str = "employee"
