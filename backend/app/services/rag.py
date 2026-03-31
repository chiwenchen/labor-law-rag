from __future__ import annotations
import asyncio
import logging
import math
import re
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)
from typing import AsyncIterator, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from anthropic import AsyncAnthropic
from app.config import settings


def get_embedder():
    from app.services.embedder import get_embedder as _get_embedder
    return _get_embedder()


SIMILARITY_REJECT_THRESHOLD = 0.45
SIMILARITY_WARN_THRESHOLD = 0.72
TOP_K = 10

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


HYDE_PROMPT = """你是台灣勞動法規專家。
以下是一個勞工提出的問題，請用「法條條文的語氣與格式」，寫出最可能回答這個問題的相關法條內容。
不要回答問題，只需寫出「法條風格的文字段落」，約100-150字，可以包含條號推測。

問題：{question}

請直接輸出法條風格的文字，不要加前言或解釋："""

REWRITE_PROMPT = """你是台灣勞動法規查詢助理。
以下是對話歷史，請將「最後問題」改寫為一個完整的獨立問句，使其不依賴對話歷史也能被理解。
若問題本身已完整（不依賴前文），直接回傳原問題，不要做任何修改。
只輸出改寫後的問句，不要加任何前言或解釋。

對話歷史：
{history}

最後問題：{question}"""


@dataclass
class QueryResult:
    is_out_of_scope: bool
    answer: Optional[str]
    warning: Optional[str]
    cited_articles: list


async def _generate_hypothetical_doc(question: str) -> str:
    """Use Haiku to generate a hypothetical law article text for HyDE."""
    client = AsyncAnthropic(api_key=settings.anthropic_api_key)
    try:
        response = await client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=200,
            messages=[{"role": "user", "content": HYDE_PROMPT.format(question=question)}],
        )
        return response.content[0].text
    except Exception:
        # Fallback: use original question if HyDE fails
        return question


async def _rewrite_question(question: str, history: list[dict]) -> str:
    """Rewrite a follow-up question into a self-contained query using conversation history."""
    history_text = "\n".join(
        f"{'用戶' if m['role'] == 'user' else 'AI'}：{m['content'][:300]}"
        for m in history[-6:]  # last 3 exchanges
    )
    client = AsyncAnthropic(api_key=settings.anthropic_api_key)
    try:
        response = await client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=100,
            messages=[{
                "role": "user",
                "content": REWRITE_PROMPT.format(history=history_text, question=question),
            }],
        )
        rewritten = response.content[0].text.strip()
        return rewritten if rewritten else question
    except Exception:
        return question


def _build_bm25_query(question: str) -> str:
    """Convert question to a tsquery-compatible string."""
    # Remove punctuation, split to tokens, join with OR operator
    tokens = re.sub(r"[？！。，、；：「」『』【】\s]+", " ", question).split()
    # Filter empty tokens
    tokens = [t for t in tokens if t]
    if not tokens:
        return ""
    return " | ".join(tokens)


async def _hybrid_search(
    hyde_embedding: list[float],
    question_embedding: list[float],
    question: str,
    db: AsyncSession,
    law_ids: list[str] | None = None,
) -> list:
    """Hybrid search: RRF fusion of HyDE vector search + BM25 keyword search."""

    # Validate embeddings
    for emb in (hyde_embedding, question_embedding):
        if not all(isinstance(x, (int, float)) and math.isfinite(x) for x in emb):
            raise ValueError("Embedding contains non-finite values")

    # Average HyDE and original question embeddings for ensemble
    ensemble = [(a + b) / 2 for a, b in zip(hyde_embedding, question_embedding)]

    law_filter = ""
    params: dict = {"k": TOP_K, "rrf_k": 60, "embedding": "[" + ",".join(str(x) for x in ensemble) + "]"}
    if law_ids:
        from app.services.law_registry import VALID_LAW_IDS
        invalid = [lid for lid in law_ids if lid not in VALID_LAW_IDS]
        if invalid:
            raise ValueError(f"Unknown law_ids: {invalid}")
        law_filter = "AND law_id = ANY(:law_ids)"
        params["law_ids"] = law_ids

    bm25_query = _build_bm25_query(question)
    has_bm25 = bool(bm25_query)

    if has_bm25:
        params["bm25_query"] = bm25_query
        sql = text(f"""
            WITH vector_ranked AS (
                SELECT id,
                       1 - (embedding <=> CAST(:embedding AS vector)) AS vscore,
                       ROW_NUMBER() OVER (ORDER BY embedding <=> CAST(:embedding AS vector)) AS vrank
                FROM law_articles
                WHERE is_active = true {law_filter}
            ),
            bm25_ranked AS (
                SELECT id,
                       ts_rank_cd(search_vector, to_tsquery('simple', :bm25_query)) AS bscore,
                       ROW_NUMBER() OVER (
                           ORDER BY ts_rank_cd(search_vector, to_tsquery('simple', :bm25_query)) DESC
                       ) AS brank
                FROM law_articles
                WHERE is_active = true
                  AND search_vector @@ to_tsquery('simple', :bm25_query)
                  {law_filter}
            ),
            rrf AS (
                SELECT
                    COALESCE(v.id, b.id) AS id,
                    (1.0 / (:rrf_k + COALESCE(v.vrank, 1000))) +
                    (1.0 / (:rrf_k + COALESCE(b.brank, 1000))) AS rrf_score,
                    COALESCE(v.vscore, 0) AS vscore
                FROM vector_ranked v
                FULL OUTER JOIN bm25_ranked b ON v.id = b.id
            )
            SELECT la.article_number, la.title, la.content, la.law_id, la.law_name,
                   r.vscore AS similarity
            FROM rrf r
            JOIN law_articles la ON la.id = r.id
            ORDER BY r.rrf_score DESC
            LIMIT :k
        """)
    else:
        # BM25 query is empty; fall back to pure vector search
        sql = text(f"""
            SELECT article_number, title, content, law_id, law_name,
                   1 - (embedding <=> CAST(:embedding AS vector)) AS similarity
            FROM law_articles
            WHERE is_active = true {law_filter}
            ORDER BY embedding <=> CAST(:embedding AS vector)
            LIMIT :k
        """)

    rows = (await db.execute(sql, params)).all()
    return rows


def _build_claude_messages(question: str, context: str, history: list[dict]) -> list[dict]:
    """Build the messages list for Claude, optionally prepending conversation history."""
    user_content = f"相關法條：\n{context}\n\n問題：{question}"
    if history:
        history_text = "\n".join(
            f"{'用戶' if m['role'] == 'user' else 'AI'}：{m['content'][:500]}"
            for m in history[-6:]
        )
        user_content = f"對話歷史（供參考）：\n{history_text}\n\n相關法條：\n{context}\n\n當前問題：{question}"
    return [{"role": "user", "content": user_content}]


async def _call_claude(question: str, articles: list, history: list[dict] | None = None, role: str = "hr") -> str:
    context = "\n\n".join(
        f"【{row.law_name}第{row.article_number}條】\n{row.content}" for row in articles
    )
    client = AsyncAnthropic(api_key=settings.anthropic_api_key)
    try:
        response = await client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=2048,
            system=_get_system_prompt(role),
            messages=_build_claude_messages(question, context, history or []),
        )
        return response.content[0].text
    except Exception as e:
        raise RuntimeError(f"Claude API call failed: {e}") from e


async def query_law(
    question: str,
    db: AsyncSession,
    law_ids: list[str] | None = None,
    history: list[dict] | None = None,
    role: str = "hr",
) -> QueryResult:
    embedder = get_embedder()

    # Rewrite follow-up questions into self-contained queries using history
    search_question = await _rewrite_question(question, history) if history else question

    # Parallelize: HyDE generation and question embedding don't depend on each other
    hypothetical_doc, question_embedding = await asyncio.gather(
        _generate_hypothetical_doc(search_question),
        asyncio.to_thread(embedder.get_text_embedding, search_question),
    )

    # Embed HyDE output (depends on HyDE result above)
    hyde_embedding = await asyncio.to_thread(embedder.get_text_embedding, hypothetical_doc)

    articles = await _hybrid_search(
        hyde_embedding, question_embedding, search_question, db, law_ids=law_ids
    )

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

    answer = await _call_claude(question, articles, history=history, role=role)

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


async def stream_query_law(
    question: str,
    db: AsyncSession,
    law_ids: list[str] | None = None,
    history: list[dict] | None = None,
    role: str = "hr",
) -> AsyncIterator[dict]:
    """Retrieves articles then streams Claude's answer token-by-token."""
    embedder = get_embedder()

    # Rewrite follow-up questions using conversation history
    if history:
        yield {"type": "step", "step": "rewrite", "label": "理解對話脈絡"}
        search_question = await _rewrite_question(question, history)
    else:
        search_question = question

    yield {"type": "step", "step": "hyde", "label": "分析問題"}

    hypothetical_doc, question_embedding = await asyncio.gather(
        _generate_hypothetical_doc(search_question),
        asyncio.to_thread(embedder.get_text_embedding, search_question),
    )
    hyde_embedding = await asyncio.to_thread(embedder.get_text_embedding, hypothetical_doc)

    yield {"type": "step", "step": "search", "label": "搜尋相關法條"}

    articles = await _hybrid_search(
        hyde_embedding, question_embedding, search_question, db, law_ids=law_ids
    )

    if not articles or articles[0].similarity < SIMILARITY_REJECT_THRESHOLD:
        yield {"type": "out_of_scope"}
        return

    yield {"type": "step", "step": "generate", "label": f"找到 {len(articles)} 條相關法條，撰寫回覆"}

    warning = None
    if articles[0].similarity < SIMILARITY_WARN_THRESHOLD:
        warning = "相關性較低，建議查閱原文確認或諮詢專業人士。"

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

    context = "\n\n".join(
        f"【{row.law_name}第{row.article_number}條】\n{row.content}" for row in articles
    )
    client = AsyncAnthropic(api_key=settings.anthropic_api_key)

    full_answer = ""
    try:
        async with client.messages.stream(
            model="claude-sonnet-4-6",
            max_tokens=2048,
            system=_get_system_prompt(role),
            messages=_build_claude_messages(question, context, history or []),
        ) as stream:
            async for text_chunk in stream.text_stream:
                full_answer += text_chunk
                yield {"type": "token", "text": text_chunk}
    except Exception as e:
        logger.error(f"Streaming query failed: {e}")
        yield {"type": "error", "message": "查詢過程中發生錯誤，請稍後再試"}
        return

    yield {
        "type": "done",
        "cited_articles": cited,
        "warning": warning,
        "answer": full_answer,
    }
