from __future__ import annotations
import math
from dataclasses import dataclass, field
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from anthropic import Anthropic
from app.config import settings


def get_embedder():
    from app.services.embedder import get_embedder as _get_embedder
    return _get_embedder()

SIMILARITY_REJECT_THRESHOLD = 0.45
SIMILARITY_WARN_THRESHOLD = 0.72
TOP_K = 8
MAX_TOKENS = 1024

_SYSTEM_PROMPT_HR = """你是一位專業的台灣勞動法規助理，服務對象為企業 HR。
請從公司管理合規的角度回答，包含：雇主義務、違規罰則、內部流程建議、勞資爭議處理方式。
請只根據以下提供的法條內容回答問題，不得自行推論或引用條文以外的資訊。
如果提供的法條不足以回答問題，請明確說明「現行法條無明確規定，建議諮詢勞工局」。
回答請使用繁體中文，語氣專業清晰。"""

_SYSTEM_PROMPT_EMPLOYEE = """你是一位專業的台灣勞動法規助理，服務對象為勞工員工。
請從勞工權益保障的角度回答，包含：個人權利、申請方式、如何向公司主張、必要時的申訴管道。
請只根據以下提供的法條內容回答問題，不得自行推論或引用條文以外的資訊。
如果提供的法條不足以回答問題，請明確說明「現行法條無明確規定，建議諮詢勞工局」。
回答請使用繁體中文，語氣專業清晰。"""


def _get_system_prompt(role: str) -> str:
    return _SYSTEM_PROMPT_EMPLOYEE if role == "employee" else _SYSTEM_PROMPT_HR


@dataclass
class QueryResult:
    is_out_of_scope: bool
    answer: Optional[str]
    warning: Optional[str]
    cited_articles: list


async def _search_articles(
    embedding: list[float],
    db: AsyncSession,
    law_ids: list[str] | None = None,
) -> list:
    # Defensive: validate law_ids are from the registry
    if law_ids:
        from app.services.law_registry import VALID_LAW_IDS
        invalid = [lid for lid in law_ids if lid not in VALID_LAW_IDS]
        if invalid:
            raise ValueError(f"Unknown law_ids: {invalid}")

    # Validate all embedding values are finite floats before inlining into SQL
    if not all(isinstance(x, (int, float)) and math.isfinite(x) for x in embedding):
        raise ValueError("Embedding contains non-finite values")

    # Format embedding as a PostgreSQL vector literal.
    # Safe to inline: embedding comes from our model, not user input.
    vec_literal = "[" + ",".join(str(x) for x in embedding) + "]"

    law_filter = ""
    params: dict = {"k": TOP_K}
    if law_ids:
        law_filter = "AND law_id = ANY(:law_ids)"
        params["law_ids"] = law_ids

    sql = text(f"""
        SELECT article_number, title, content, law_id, law_name,
               1 - (embedding <=> '{vec_literal}'::vector) AS similarity
        FROM law_articles
        WHERE is_active = true {law_filter}
        ORDER BY embedding <=> '{vec_literal}'::vector
        LIMIT :k
    """)
    rows = (await db.execute(sql, params)).all()
    return rows


def _call_claude(question: str, articles: list, role: str = "hr") -> str:
    context = "\n\n".join(
        f"【{row.law_name}第{row.article_number}條】\n{row.content}" for row in articles
    )
    client = Anthropic(api_key=settings.anthropic_api_key)
    try:
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=MAX_TOKENS,
            system=_get_system_prompt(role),
            messages=[
                {"role": "user", "content": f"相關法條：\n{context}\n\n問題：{question}"}
            ],
        )
        return response.content[0].text
    except Exception as e:
        raise RuntimeError(f"Claude API call failed: {e}") from e


async def query_law(
    question: str,
    db: AsyncSession,
    law_ids: list[str] | None = None,
    role: str = "hr",
) -> QueryResult:
    embedder = get_embedder()
    question_embedding = embedder.get_text_embedding(question)
    articles = await _search_articles(question_embedding, db, law_ids=law_ids)

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

    answer = _call_claude(question, articles, role=role)

    cited = [
        {
            "article_number": row.article_number,
            "title": row.title,
            "law_id": row.law_id,
            "law_name": row.law_name,
            "similarity": round(row.similarity, 3),
        }
        for row in articles
    ]

    return QueryResult(
        is_out_of_scope=False,
        answer=answer,
        warning=warning,
        cited_articles=cited,
    )
