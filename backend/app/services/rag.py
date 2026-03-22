from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from anthropic import Anthropic
from app.config import settings


def get_embedder():
    from app.services.embedder import get_embedder as _get_embedder
    return _get_embedder()

SIMILARITY_REJECT_THRESHOLD = 0.5
SIMILARITY_WARN_THRESHOLD = 0.75
TOP_K = 5

SYSTEM_PROMPT = """你是一位專業的台灣勞基法助理，服務對象為企業 HR。
請只根據以下提供的法條內容回答問題，不得自行推論或引用條文以外的資訊。
如果提供的法條不足以回答問題，請明確說明「現行法條無明確規定，建議諮詢勞工局」。
回答請使用繁體中文，語氣專業清晰。"""


@dataclass
class QueryResult:
    is_out_of_scope: bool
    answer: Optional[str]
    warning: Optional[str]
    cited_articles: list


async def _search_articles(embedding: list[float], db: AsyncSession) -> list:
    sql = text("""
        SELECT article_number, title, content,
               1 - (embedding <=> :embedding::vector) AS similarity
        FROM law_articles
        WHERE is_active = true
        ORDER BY embedding <=> :embedding::vector
        LIMIT :k
    """)
    rows = (await db.execute(sql, {"embedding": str(embedding), "k": TOP_K})).all()
    return rows


def _call_claude(question: str, articles: list) -> str:
    context = "\n\n".join(
        f"【第{row.article_number}條】\n{row.content}" for row in articles
    )
    client = Anthropic(api_key=settings.anthropic_api_key)
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1024,
        system=SYSTEM_PROMPT,
        messages=[
            {"role": "user", "content": f"相關法條：\n{context}\n\n問題：{question}"}
        ],
    )
    return response.content[0].text


async def query_law(question: str, db: AsyncSession) -> QueryResult:
    embedder = get_embedder()
    question_embedding = embedder.get_text_embedding(question)
    articles = await _search_articles(question_embedding, db)

    if not articles or articles[0].similarity < SIMILARITY_REJECT_THRESHOLD:
        return QueryResult(
            is_out_of_scope=True,
            answer=None,
            warning=None,
            cited_articles=[],
        )

    warning = None
    if articles[0].similarity < SIMILARITY_WARN_THRESHOLD:
        warning = "相關性較低，建議查閱原文確認或諮詢專業人士。"

    answer = _call_claude(question, articles)

    cited = [
        {"article_number": row.article_number, "title": row.title, "similarity": round(row.similarity, 3)}
        for row in articles
    ]

    return QueryResult(
        is_out_of_scope=False,
        answer=answer,
        warning=warning,
        cited_articles=cited,
    )
