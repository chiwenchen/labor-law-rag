"""Seed test users with realistic query sessions for admin dashboard demo.

Each user persona asks questions in their own style, testing RAG across
different labor law topics and phrasings.

Usage:
    docker-compose exec backend python scripts/seed_test_users.py
"""

import asyncio
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import text

from app.db.database import AsyncSessionLocal
from app.db.models import AuthSession, QueryHistory, Session, User


# ── Test user personas ──────────────────────────────────────────────

PERSONAS = [
    {
        "email": "hr.wang@testcompany.com",
        "role": "hr",
        "access_role": "hr",
        "credits": 50,
        "sessions": [
            {
                "title": "員工加班費爭議處理",
                "questions": [
                    "員工主張加班費計算錯誤，HR該怎麼處理？",
                    "加班費的計算基準是什麼？月薪制跟時薪制有差嗎？",
                ],
                "days_ago": 1,
            },
            {
                "title": "育嬰留停申請流程",
                "questions": [
                    "員工申請育嬰留停，公司可以拒絕嗎？",
                    "育嬰留停期間的勞健保怎麼處理？",
                    "留停結束後員工回來，職位已經被別人佔了怎麼辦？",
                ],
                "days_ago": 3,
            },
            {
                "title": "試用期解僱風險",
                "questions": [
                    "試用期員工表現不好可以直接解僱嗎？需要資遣費嗎？",
                ],
                "days_ago": 7,
            },
        ],
    },
    {
        "email": "employee.chen@testcompany.com",
        "role": "employee",
        "access_role": "employee",
        "credits": 15,
        "sessions": [
            {
                "title": "特休假天數",
                "questions": [
                    "我在公司做了兩年半，有幾天特休？",
                    "特休沒用完可以換錢嗎？",
                ],
                "days_ago": 0,
            },
            {
                "title": "懷孕請假權益",
                "questions": [
                    "懷孕期間產檢假有幾天？要扣薪水嗎？",
                    "產假是幾天？薪水怎麼算？",
                ],
                "days_ago": 2,
            },
            {
                "title": "被資遣的權益",
                "questions": [
                    "公司要裁員把我資遣，我有什麼權益？",
                    "資遣預告期是多久？",
                    "可以要求公司開非自願離職證明嗎？",
                ],
                "days_ago": 5,
            },
            {
                "title": "職災相關",
                "questions": [
                    "上班途中出車禍算不算職災？",
                ],
                "days_ago": 10,
            },
        ],
    },
    {
        "email": "newbie.lin@testcompany.com",
        "role": "employee",
        "access_role": "employee",
        "credits": 0,  # credits exhausted — tests 402 scenario
        "sessions": [
            {
                "title": "基本勞動權益",
                "questions": [
                    "第一份工作，想了解基本的勞動權益有哪些？",
                    "老闆說沒有加班費因為是責任制，這合法嗎？",
                ],
                "days_ago": 4,
            },
        ],
    },
    {
        "email": "manager.liu@testcompany.com",
        "role": "hr",
        "access_role": "employee",
        "credits": 100,
        "sessions": [
            {
                "title": "勞資會議法規",
                "questions": [
                    "勞資會議多久要開一次？沒開會有什麼罰則？",
                    "勞資會議的代表怎麼選出來？",
                ],
                "days_ago": 1,
            },
            {
                "title": "工時彈性安排",
                "questions": [
                    "四週變形工時怎麼排班才合法？",
                    "變形工時需要經過勞資會議同意嗎？",
                    "排班超過連續工作六天違法嗎？",
                ],
                "days_ago": 6,
            },
        ],
    },
    {
        "email": "parttime.zhang@testcompany.com",
        "role": "employee",
        "access_role": "employee",
        "credits": 30,
        "sessions": [
            {
                "title": "兼職勞動權益",
                "questions": [
                    "打工族有勞健保嗎？工讀生跟正職的差別在哪？",
                    "兼職的加班費怎麼算？跟全職一樣嗎？",
                ],
                "days_ago": 2,
            },
        ],
    },
]


async def seed():
    async with AsyncSessionLocal() as db:
        for persona in PERSONAS:
            # Check if user already exists
            existing = (
                await db.execute(
                    text("SELECT id FROM users WHERE email = :email"),
                    {"email": persona["email"]},
                )
            ).scalar_one_or_none()

            if existing:
                print(f"  SKIP {persona['email']} (already exists)")
                continue

            # Create user
            user_id = uuid.uuid4()
            user = User(
                id=user_id,
                email=persona["email"],
                role=persona["role"],
                access_role=persona["access_role"],
                credits=persona["credits"],
            )
            db.add(user)
            await db.flush()

            # Create sessions + query history (no actual RAG calls — static answers)
            for sess_data in persona["sessions"]:
                session = Session(
                    title=sess_data["title"],
                    user_id=user_id,
                )
                db.add(session)
                await db.flush()

                base_time = datetime.now(timezone.utc) - timedelta(days=sess_data["days_ago"])
                for i, question in enumerate(sess_data["questions"]):
                    qh = QueryHistory(
                        session_id=session.id,
                        question=question,
                        answer=f"[測試資料] 此為 {persona['email']} 的模擬查詢回答。",
                        cited_articles=[],
                        max_similarity_score=0.85,
                    )
                    db.add(qh)

            print(f"  ✓ {persona['email']} ({persona['role']}/{persona['access_role']}, {persona['credits']} credits, {sum(len(s['questions']) for s in persona['sessions'])} queries)")

        await db.commit()
        print("\nDone. Test users seeded.")


if __name__ == "__main__":
    asyncio.run(seed())
