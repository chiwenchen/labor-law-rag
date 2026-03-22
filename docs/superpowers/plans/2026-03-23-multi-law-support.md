# Multi-Law Support & Law Management Page Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expand the system from 1 law (勞動基準法) to 11 HR laws, add per-law scope filtering to the chat, and add a `/laws` management page.

**Architecture:** Backend gains a law registry, per-law fetch/embed pipeline, `supported_laws` DB table, and two new API endpoints. Frontend adds a collapsible law scope selector in Sidebar, passes `law_ids` through the query chain, and adds a `/laws` page with a table + per-law update buttons.

**Tech Stack:** FastAPI, SQLAlchemy asyncpg, pgvector, pytest (backend); Next.js 14 App Router, TypeScript, Tailwind (frontend); kong0107/mojLawSplitJSON as data source.

**Spec:** `docs/superpowers/specs/2026-03-23-multi-law-support-design.md`

---

## File Map

**Backend — Create:**
- `backend/app/db/migrations/002_multi_law.sql` — DB migration (new columns, tables, constraint changes)
- `backend/app/services/law_registry.py` — LAW_REGISTRY constant + BASE_URL
- `backend/app/routers/laws.py` — GET /api/laws, POST /api/laws/{law_id}/update
- `backend/tests/test_law_registry.py`
- `backend/tests/test_fetcher_multi_law.py`
- `backend/tests/test_rag_law_filter.py`
- `backend/tests/test_laws_router.py`

**Backend — Modify:**
- `backend/app/db/models.py` — Add `SupportedLaw` model; update `LawArticle` (law_id, law_name, composite unique); update `LawUpdateLog` (law_id)
- `backend/app/services/fetcher.py` — Add `fetch_law(law_id, law_name)`; keep `fetch_labor_law_articles()` as wrapper
- `backend/app/services/indexer.py` — Scope upsert per-law; update `supported_laws` after indexing
- `backend/app/services/rag.py` — Add `law_ids` param to `_search_articles` and `query_law`; add `law_id`/`law_name` to cited articles
- `backend/app/services/scheduler.py` — Iterate over all laws in LAW_REGISTRY
- `backend/app/routers/query.py` — Add `law_ids` to `QueryRequest`; whitelist and forward
- `backend/app/main.py` — Startup seeding of `supported_laws`; include `laws` router

**Frontend — Create:**
- `frontend/src/components/LawScopeSelector.tsx` — Collapsible checkbox panel
- `frontend/src/app/laws/page.tsx` — /laws route

**Frontend — Modify:**
- `frontend/src/types/index.ts` — Add `SupportedLaw`; extend `CitedArticle` with `law_id`/`law_name`
- `frontend/src/lib/api.ts` — Add `getLaws()`, `updateLaw()`; update `postQuery()`
- `frontend/src/components/Sidebar.tsx` — Add `LawScopeSelector`; add "法規管理" nav link
- `frontend/src/app/page.tsx` — Add `selectedLawIds` state; wire to Sidebar + ChatPanel
- `frontend/src/components/ChatPanel.tsx` — Accept `selectedLawIds`; send with query

---

## Task 1: DB Migration + Model Updates

**Files:**
- Create: `backend/app/db/migrations/002_multi_law.sql`
- Modify: `backend/app/db/models.py`

- [ ] **Step 1: Write the migration SQL**

Create `backend/app/db/migrations/002_multi_law.sql`:

```sql
-- Add law_id and law_name to law_articles
ALTER TABLE law_articles
  ADD COLUMN IF NOT EXISTS law_id   VARCHAR(20)  NOT NULL DEFAULT 'N0030001',
  ADD COLUMN IF NOT EXISTS law_name VARCHAR(100) NOT NULL DEFAULT '勞動基準法';

-- Replace single-column unique constraint with composite (law_id, article_number)
ALTER TABLE law_articles
  DROP CONSTRAINT IF EXISTS law_articles_article_number_key;
ALTER TABLE law_articles
  ADD CONSTRAINT law_articles_law_id_article_number_key
    UNIQUE (law_id, article_number);

-- Add law_id to law_update_logs
ALTER TABLE law_update_logs
  ADD COLUMN IF NOT EXISTS law_id VARCHAR(20) NOT NULL DEFAULT 'N0030001';

-- Create supported_laws summary table
CREATE TABLE IF NOT EXISTS supported_laws (
  law_id        VARCHAR(20)  PRIMARY KEY,
  law_name      VARCHAR(100) NOT NULL,
  article_count INTEGER      NOT NULL DEFAULT 0,
  last_updated  TIMESTAMP WITH TIME ZONE,
  last_status   VARCHAR(20)  NOT NULL DEFAULT 'never_run'
);
```

- [ ] **Step 2: Apply migration to running DB**

```bash
docker compose exec db psql -U ${POSTGRES_USER} -d ${POSTGRES_DB} \
  -f /dev/stdin < backend/app/db/migrations/002_multi_law.sql
```

Expected: `ALTER TABLE`, `ALTER TABLE`, `ALTER TABLE`, `CREATE TABLE` (no errors).

- [ ] **Step 3: Update SQLAlchemy models**

Replace `backend/app/db/models.py` with:

```python
import uuid
from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.sql import func
from pgvector.sqlalchemy import Vector


class Base(DeclarativeBase):
    pass


class Session(Base):
    __tablename__ = "sessions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title = Column(String(100), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class LawArticle(Base):
    __tablename__ = "law_articles"
    __table_args__ = (
        UniqueConstraint("law_id", "article_number", name="law_articles_law_id_article_number_key"),
    )

    id = Column(Integer, primary_key=True)
    law_id = Column(String(20), nullable=False, default="N0030001")
    law_name = Column(String(100), nullable=False, default="勞動基準法")
    article_number = Column(String(20), nullable=False)
    title = Column(String(200))
    content = Column(Text, nullable=False)
    embedding = Column(Vector(1024))
    is_active = Column(Boolean, default=True)
    last_updated = Column(DateTime(timezone=True))
    version = Column(String(50))


class SupportedLaw(Base):
    __tablename__ = "supported_laws"

    law_id = Column(String(20), primary_key=True)
    law_name = Column(String(100), nullable=False)
    article_count = Column(Integer, nullable=False, default=0)
    last_updated = Column(DateTime(timezone=True))
    last_status = Column(String(20), nullable=False, default="never_run")


class QueryHistory(Base):
    __tablename__ = "query_history"

    id = Column(Integer, primary_key=True)
    session_id = Column(UUID(as_uuid=True), ForeignKey("sessions.id", ondelete="CASCADE"))
    question = Column(Text, nullable=False)
    answer = Column(Text)
    cited_articles = Column(JSONB)
    max_similarity_score = Column(Float)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class LawUpdateLog(Base):
    __tablename__ = "law_update_logs"

    id = Column(Integer, primary_key=True)
    law_id = Column(String(20), nullable=False, default="N0030001")
    updated_at = Column(DateTime(timezone=True), server_default=func.now())
    articles_changed = Column(Integer, default=0)
    status = Column(String(20), nullable=False)
    error_message = Column(Text)
```

- [ ] **Step 4: Verify backend still starts**

```bash
docker compose restart backend
sleep 5
docker compose logs backend | grep -E "(started|error|Error)" | head -10
```

Expected: "Application startup complete" with no errors.

- [ ] **Step 5: Commit**

```bash
git add backend/app/db/migrations/002_multi_law.sql backend/app/db/models.py
git commit -m "feat: add law_id/law_name columns and supported_laws table"
```

---

## Task 2: Law Registry

**Files:**
- Create: `backend/app/services/law_registry.py`
- Create: `backend/tests/test_law_registry.py`

- [ ] **Step 1: Write failing test**

Create `backend/tests/test_law_registry.py`:

```python
from app.services.law_registry import LAW_REGISTRY, BASE_URL, get_law_by_id


def test_registry_has_eleven_laws():
    assert len(LAW_REGISTRY) == 11


def test_registry_includes_labor_standards_act():
    ids = [law.law_id for law in LAW_REGISTRY]
    assert "N0030001" in ids


def test_all_laws_have_id_and_name():
    for law in LAW_REGISTRY:
        assert law.law_id.startswith("N")
        assert len(law.law_name) > 0


def test_base_url_format():
    url = BASE_URL.format(law_id="N0030001")
    assert "N0030001" in url
    assert url.startswith("https://")


def test_get_law_by_id_found():
    law = get_law_by_id("N0030001")
    assert law is not None
    assert law.law_name == "勞動基準法"


def test_get_law_by_id_not_found():
    assert get_law_by_id("INVALID") is None
```

- [ ] **Step 2: Run test — expect FAIL**

```bash
docker compose exec backend python -m pytest tests/test_law_registry.py -v 2>&1 | tail -15
```

Expected: `ModuleNotFoundError` or `ImportError`.

- [ ] **Step 3: Implement law_registry.py**

Create `backend/app/services/law_registry.py`:

```python
from __future__ import annotations
from dataclasses import dataclass


@dataclass(frozen=True)
class LawInfo:
    law_id: str
    law_name: str


LAW_REGISTRY: list[LawInfo] = [
    LawInfo("N0030001", "勞動基準法"),
    LawInfo("N0030002", "勞工請假規則"),
    LawInfo("N0030003", "大量解僱勞工保護法"),
    LawInfo("N0030014", "勞資爭議處理法"),
    LawInfo("N0030015", "性別平等工作法"),
    LawInfo("N0050001", "勞工保險條例"),
    LawInfo("N0060001", "勞工退休金條例"),
    LawInfo("N0060002", "職業安全衛生法"),
    LawInfo("N0060003", "勞工職業災害保險及保護法"),
    LawInfo("N0090001", "就業保險法"),
    LawInfo("N0090003", "就業服務法"),
]

VALID_LAW_IDS: frozenset[str] = frozenset(law.law_id for law in LAW_REGISTRY)

BASE_URL = (
    "https://raw.githubusercontent.com/kong0107/mojLawSplitJSON"
    "/gh-pages/FalVMingLing/{law_id}.json"
)


def get_law_by_id(law_id: str) -> LawInfo | None:
    return next((law for law in LAW_REGISTRY if law.law_id == law_id), None)
```

- [ ] **Step 4: Run tests — expect PASS**

```bash
docker compose exec backend python -m pytest tests/test_law_registry.py -v 2>&1 | tail -15
```

Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/law_registry.py backend/tests/test_law_registry.py
git commit -m "feat: add law registry with 11 supported HR laws"
```

---

## Task 3: Fetcher Generalization

**Files:**
- Modify: `backend/app/services/fetcher.py`
- Create: `backend/tests/test_fetcher_multi_law.py`

- [ ] **Step 1: Write failing test**

Create `backend/tests/test_fetcher_multi_law.py`:

```python
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from app.services.fetcher import fetch_law, fetch_labor_law_articles, LawArticleData

SAMPLE_RESPONSE = {
    "最新異動日期": "20240101",
    "法規內容": [
        {"條號": "第 1 條", "條文內容": "為規定勞動條件最低標準..."},
        {"條號": "第 2 條", "條文內容": "本法用辭定義如左..."},
        {"編章節": "第一章 總則"},  # Should be skipped
    ],
}


@pytest.mark.asyncio
async def test_fetch_law_returns_articles_with_law_id():
    mock_response = MagicMock()
    mock_response.json.return_value = SAMPLE_RESPONSE
    mock_response.raise_for_status = MagicMock()

    with patch("httpx.AsyncClient") as mock_client:
        mock_client.return_value.__aenter__.return_value.get = AsyncMock(
            return_value=mock_response
        )
        articles = await fetch_law("N0030001", "勞動基準法")

    assert len(articles) == 2
    assert all(isinstance(a, LawArticleData) for a in articles)
    assert articles[0].law_id == "N0030001"
    assert articles[0].law_name == "勞動基準法"
    assert articles[0].article_number == "1"
    assert articles[0].version == "20240101"


@pytest.mark.asyncio
async def test_fetch_law_skips_chapter_headings():
    mock_response = MagicMock()
    mock_response.json.return_value = SAMPLE_RESPONSE
    mock_response.raise_for_status = MagicMock()

    with patch("httpx.AsyncClient") as mock_client:
        mock_client.return_value.__aenter__.return_value.get = AsyncMock(
            return_value=mock_response
        )
        articles = await fetch_law("N0030002", "勞工請假規則")

    assert all(a.article_number != "" for a in articles)
    assert len(articles) == 2  # Only the 條 items, not 編章節


@pytest.mark.asyncio
async def test_fetch_labor_law_articles_is_backward_compatible():
    mock_response = MagicMock()
    mock_response.json.return_value = SAMPLE_RESPONSE
    mock_response.raise_for_status = MagicMock()

    with patch("httpx.AsyncClient") as mock_client:
        mock_client.return_value.__aenter__.return_value.get = AsyncMock(
            return_value=mock_response
        )
        articles = await fetch_labor_law_articles()

    assert articles[0].law_id == "N0030001"
    assert articles[0].law_name == "勞動基準法"
```

- [ ] **Step 2: Run test — expect FAIL**

```bash
docker compose exec backend python -m pytest tests/test_fetcher_multi_law.py -v 2>&1 | tail -15
```

Expected: FAIL — `LawArticleData` has no `law_id` field.

- [ ] **Step 3: Implement updated fetcher.py**

Replace `backend/app/services/fetcher.py`:

```python
from __future__ import annotations
from dataclasses import dataclass
import re
import httpx
from app.services.law_registry import BASE_URL


@dataclass
class LawArticleData:
    article_number: str
    content: str
    version: str
    law_id: str
    law_name: str


async def fetch_law(law_id: str, law_name: str) -> list[LawArticleData]:
    """Fetch and parse articles for one law from kong0107/mojLawSplitJSON.

    Returns a list of LawArticleData. Raises httpx.HTTPStatusError if the
    law_id URL returns a non-2xx status (e.g. 404 for unknown law codes).
    Expected duration: < 5 seconds per law.
    """
    url = BASE_URL.format(law_id=law_id)
    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
        response = await client.get(url)
        response.raise_for_status()
        data = response.json()

    version = data.get("最新異動日期", "unknown")
    articles = []
    for item in data.get("法規內容", []):
        raw_number = item.get("條號", "").strip()
        content = item.get("條文內容", "").strip()
        if not raw_number or not content:
            continue
        match = re.search(r"第\s*([\d\-]+)\s*條", raw_number)
        article_number = match.group(1) if match else raw_number
        articles.append(LawArticleData(
            article_number=article_number,
            content=content,
            version=version,
            law_id=law_id,
            law_name=law_name,
        ))
    return articles


async def fetch_labor_law_articles() -> list[LawArticleData]:
    """Backward-compatible wrapper for 勞動基準法."""
    return await fetch_law("N0030001", "勞動基準法")
```

- [ ] **Step 4: Run tests — expect PASS**

```bash
docker compose exec backend python -m pytest tests/test_fetcher_multi_law.py -v 2>&1 | tail -15
```

Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/fetcher.py backend/tests/test_fetcher_multi_law.py
git commit -m "feat: generalize fetcher to support multiple laws"
```

---

## Task 4: Indexer — Per-Law Scoping + supported_laws Update

**Files:**
- Modify: `backend/app/services/indexer.py`

- [ ] **Step 1: Update indexer.py**

Replace `backend/app/services/indexer.py`:

```python
from __future__ import annotations
import logging
from dataclasses import dataclass, field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.dialects.postgresql import insert as pg_insert
from app.db.models import LawArticle, SupportedLaw
from app.services.fetcher import LawArticleData
from app.services.embedder import get_embedder

logger = logging.getLogger(__name__)


@dataclass
class IndexResult:
    inserted: int = 0
    updated: int = 0
    skipped: int = 0
    errors: list[str] = field(default_factory=list)


async def upsert_articles(
    articles: list[LawArticleData],
    db: AsyncSession,
    law_id: str,
    law_name: str,
) -> IndexResult:
    """Upsert articles for a single law. Marks removed articles as inactive.
    Updates supported_laws article_count and last_status on completion.
    """
    result = IndexResult()
    embedder = get_embedder()

    # Load existing active articles for THIS law only
    stmt = select(LawArticle).where(
        LawArticle.law_id == law_id,
        LawArticle.is_active == True,
    )
    existing = {
        a.article_number: a
        for a in (await db.execute(stmt)).scalars().all()
    }

    incoming_numbers = {a.article_number for a in articles}

    # Mark obsolete articles (belong to this law, not in new fetch) as inactive
    for number, article in existing.items():
        if number not in incoming_numbers:
            article.is_active = False

    for article_data in articles:
        existing_article = existing.get(article_data.article_number)

        if existing_article and existing_article.content == article_data.content:
            result.skipped += 1
            continue

        try:
            embedding = embedder.get_text_embedding(article_data.content)
        except Exception as e:
            result.errors.append(
                f"Article {article_data.article_number}: embedding failed — {e}"
            )
            continue

        # NOTE: SQLAlchemy ORM requires in-place mutation to track changes.
        # This is an intentional exception to the project's immutability rule.
        if existing_article:
            existing_article.content = article_data.content
            existing_article.embedding = embedding
            existing_article.version = article_data.version
            existing_article.law_name = law_name
            result.updated += 1
        else:
            db.add(LawArticle(
                law_id=law_id,
                law_name=law_name,
                article_number=article_data.article_number,
                content=article_data.content,
                embedding=embedding,
                version=article_data.version,
                is_active=True,
            ))
            result.inserted += 1

    await db.flush()

    # Update supported_laws with real count
    count = (await db.execute(
        select(func.count()).select_from(LawArticle).where(
            LawArticle.law_id == law_id,
            LawArticle.is_active == True,
        )
    )).scalar()

    supported_law = (await db.execute(
        select(SupportedLaw).where(SupportedLaw.law_id == law_id)
    )).scalar_one_or_none()

    if supported_law:
        supported_law.article_count = count
        supported_law.last_updated = func.now()
        supported_law.last_status = "success"

    await db.commit()
    logger.info(
        f"[{law_id}] +{result.inserted} ~{result.updated} skip={result.skipped} "
        f"err={len(result.errors)} total={count}"
    )
    return result
```

- [ ] **Step 2: Verify backend starts (indexer import is checked at startup)**

```bash
docker compose restart backend && sleep 5
docker compose logs backend 2>&1 | grep -E "(startup|error|Error|import)" | head -10
```

Expected: "Application startup complete", no ImportError.

- [ ] **Step 3: Commit**

```bash
git add backend/app/services/indexer.py
git commit -m "feat: scope indexer per-law, update supported_laws after each index"
```

---

## Task 5: RAG — law_ids Filter + law_name in Citations

**Files:**
- Modify: `backend/app/services/rag.py`
- Create: `backend/tests/test_rag_law_filter.py`

- [ ] **Step 1: Write failing test**

Create `backend/tests/test_rag_law_filter.py`:

```python
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from app.services.rag import query_law, QueryResult


def make_mock_row(article_number="1", similarity=0.9, law_id="N0030001", law_name="勞動基準法"):
    row = MagicMock()
    row.article_number = article_number
    row.title = None
    row.content = "Test content"
    row.similarity = similarity
    row.law_id = law_id
    row.law_name = law_name
    return row


@pytest.mark.asyncio
async def test_query_law_cited_articles_include_law_info():
    mock_db = AsyncMock()
    mock_rows = [make_mock_row(similarity=0.9)]

    with (
        patch("app.services.rag.get_embedder") as mock_embedder,
        patch("app.services.rag._search_articles", return_value=mock_rows),
        patch("app.services.rag._call_claude", return_value="Answer"),
    ):
        mock_embedder.return_value.get_text_embedding.return_value = [0.0] * 1024
        result = await query_law("test question", mock_db)

    assert result.cited_articles[0]["law_id"] == "N0030001"
    assert result.cited_articles[0]["law_name"] == "勞動基準法"


@pytest.mark.asyncio
async def test_query_law_with_law_ids_filter_passes_to_search():
    mock_db = AsyncMock()

    with (
        patch("app.services.rag.get_embedder") as mock_embedder,
        patch("app.services.rag._search_articles", return_value=[]) as mock_search,
    ):
        mock_embedder.return_value.get_text_embedding.return_value = [0.0] * 1024
        result = await query_law("test", mock_db, law_ids=["N0030001"])

    mock_search.assert_called_once()
    _, kwargs = mock_search.call_args
    assert kwargs.get("law_ids") == ["N0030001"] or mock_search.call_args[0][2] == ["N0030001"]


@pytest.mark.asyncio
async def test_query_law_empty_law_ids_searches_all():
    mock_db = AsyncMock()

    with (
        patch("app.services.rag.get_embedder") as mock_embedder,
        patch("app.services.rag._search_articles", return_value=[]) as mock_search,
    ):
        mock_embedder.return_value.get_text_embedding.return_value = [0.0] * 1024
        await query_law("test", mock_db, law_ids=[])

    # Called with no law filter (None or [])
    call_args = mock_search.call_args
    law_ids_arg = call_args[1].get("law_ids") if call_args[1] else (call_args[0][2] if len(call_args[0]) > 2 else None)
    assert not law_ids_arg  # None or empty list
```

- [ ] **Step 2: Run test — expect FAIL**

```bash
docker compose exec backend python -m pytest tests/test_rag_law_filter.py -v 2>&1 | tail -15
```

Expected: FAIL — cited_articles missing `law_id`, `law_name`.

- [ ] **Step 3: Update rag.py**

Replace `backend/app/services/rag.py`:

```python
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
MAX_TOKENS = 1024

SYSTEM_PROMPT = """你是一位專業的台灣勞動法規助理，服務對象為企業 HR。
請只根據以下提供的法條內容回答問題，不得自行推論或引用條文以外的資訊。
如果提供的法條不足以回答問題，請明確說明「現行法條無明確規定，建議諮詢勞工局」。
回答請使用繁體中文，語氣專業清晰。"""


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
    # Format embedding as a PostgreSQL vector literal.
    # Safe to inline: embedding comes from our model, not user input.
    vec_literal = "[" + ",".join(str(x) for x in embedding) + "]"

    # law_ids are whitelisted in the router against LAW_REGISTRY before reaching here.
    law_filter = ""
    if law_ids:
        ids_literal = "ARRAY[" + ",".join(f"'{lid}'" for lid in law_ids) + "]"
        law_filter = f"AND law_id = ANY({ids_literal})"

    sql = text(f"""
        SELECT article_number, title, content, law_id, law_name,
               1 - (embedding <=> '{vec_literal}'::vector) AS similarity
        FROM law_articles
        WHERE is_active = true {law_filter}
        ORDER BY embedding <=> '{vec_literal}'::vector
        LIMIT :k
    """)
    rows = (await db.execute(sql, {"k": TOP_K})).all()
    return rows


def _call_claude(question: str, articles: list) -> str:
    context = "\n\n".join(
        f"【{row.law_name}第{row.article_number}條】\n{row.content}" for row in articles
    )
    client = Anthropic(api_key=settings.anthropic_api_key)
    try:
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=MAX_TOKENS,
            system=SYSTEM_PROMPT,
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
) -> QueryResult:
    embedder = get_embedder()
    question_embedding = embedder.get_text_embedding(question)
    articles = await _search_articles(question_embedding, db, law_ids=law_ids or None)

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
```

- [ ] **Step 4: Run tests — expect PASS**

```bash
docker compose exec backend python -m pytest tests/test_rag_law_filter.py -v 2>&1 | tail -15
```

Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/rag.py backend/tests/test_rag_law_filter.py
git commit -m "feat: add law_ids filter to RAG search, include law_id/law_name in citations"
```

---

## Task 6: Laws Router

**Files:**
- Create: `backend/app/routers/laws.py`
- Create: `backend/tests/test_laws_router.py`

- [ ] **Step 1: Write failing test**

Create `backend/tests/test_laws_router.py`:

```python
import pytest
from httpx import AsyncClient, ASGITransport
from unittest.mock import AsyncMock, patch, MagicMock
from app.main import app


@pytest.mark.asyncio
async def test_get_laws_returns_list():
    mock_laws = [
        MagicMock(
            law_id="N0030001", law_name="勞動基準法",
            article_count=98, last_updated=None, last_status="success"
        ),
        MagicMock(
            law_id="N0030002", law_name="勞工請假規則",
            article_count=0, last_updated=None, last_status="never_run"
        ),
    ]
    with patch("app.routers.laws.get_db") as mock_get_db:
        mock_db = AsyncMock()
        mock_db.execute.return_value.scalars.return_value.all.return_value = mock_laws
        mock_get_db.return_value = mock_db
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get("/api/laws")

    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)


@pytest.mark.asyncio
async def test_update_law_invalid_id_returns_404():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post("/api/laws/INVALID_CODE/update")
    assert response.status_code == 404
```

- [ ] **Step 2: Run test — expect FAIL**

```bash
docker compose exec backend python -m pytest tests/test_laws_router.py -v 2>&1 | tail -15
```

Expected: FAIL — router doesn't exist yet.

- [ ] **Step 3: Create laws.py router**

Create `backend/app/routers/laws.py`:

```python
from __future__ import annotations
import logging
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.db.database import get_db
from app.db.models import LawArticle, LawUpdateLog, SupportedLaw
from app.services.law_registry import LAW_REGISTRY, VALID_LAW_IDS, get_law_by_id
from app.services.fetcher import fetch_law
from app.services.indexer import upsert_articles
import httpx

router = APIRouter()
logger = logging.getLogger(__name__)

# Ordered list of law_ids from registry (for consistent response ordering)
_REGISTRY_ORDER = {law.law_id: i for i, law in enumerate(LAW_REGISTRY)}


@router.get("/laws")
async def list_laws(db: AsyncSession = Depends(get_db)):
    """Return all supported laws with their current status."""
    stmt = select(SupportedLaw)
    laws = (await db.execute(stmt)).scalars().all()
    sorted_laws = sorted(laws, key=lambda l: _REGISTRY_ORDER.get(l.law_id, 999))
    return [
        {
            "law_id": l.law_id,
            "law_name": l.law_name,
            "article_count": l.article_count,
            "last_updated": l.last_updated,
            "last_status": l.last_status,
        }
        for l in sorted_laws
    ]


@router.post("/laws/{law_id}/update")
async def update_law(law_id: str, db: AsyncSession = Depends(get_db)):
    """Fetch and re-embed articles for one law.

    Synchronous long-poll: takes 30–120 seconds depending on article count.
    Frontend should use a 180-second timeout for this request.
    """
    law_info = get_law_by_id(law_id)
    if law_info is None:
        raise HTTPException(status_code=404, detail="Law not found in registry")

    # Fetch articles
    try:
        articles = await fetch_law(law_info.law_id, law_info.law_name)
    except httpx.HTTPStatusError as e:
        # Mark as failed in supported_laws
        supported_law = (await db.execute(
            select(SupportedLaw).where(SupportedLaw.law_id == law_id)
        )).scalar_one_or_none()
        if supported_law:
            supported_law.last_status = "failed"
            await db.commit()
        logger.error(f"[{law_id}] Fetch failed: {e}")
        raise HTTPException(status_code=502, detail=f"法規來源無法取得：{e}")

    # Index articles (also updates supported_laws)
    index_result = await upsert_articles(articles, db, law_info.law_id, law_info.law_name)

    # Write audit log
    log = LawUpdateLog(
        law_id=law_id,
        articles_changed=index_result.inserted + index_result.updated,
        status="success",
    )
    db.add(log)
    await db.commit()

    # Return current article count from supported_laws
    supported_law = (await db.execute(
        select(SupportedLaw).where(SupportedLaw.law_id == law_id)
    )).scalar_one_or_none()
    article_count = supported_law.article_count if supported_law else len(articles)

    logger.info(f"[{law_id}] Manual update complete: count={article_count}")
    return {
        "status": "success",
        "article_count": article_count,
        "message": f"已更新 {law_info.law_name}（+{index_result.inserted} 新增 / ~{index_result.updated} 更新）",
    }
```

- [ ] **Step 4: Run tests — expect PASS**

```bash
docker compose exec backend python -m pytest tests/test_laws_router.py -v 2>&1 | tail -15
```

Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/routers/laws.py backend/tests/test_laws_router.py
git commit -m "feat: add /api/laws GET and /api/laws/{law_id}/update POST"
```

---

## Task 7: Scheduler + Main Wiring + Query Router

**Files:**
- Modify: `backend/app/services/scheduler.py`
- Modify: `backend/app/main.py`
- Modify: `backend/app/routers/query.py`

- [ ] **Step 1: Update scheduler.py to iterate all laws**

Replace `backend/app/services/scheduler.py`:

```python
import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from app.db.database import AsyncSessionLocal
from app.db.models import LawUpdateLog, SupportedLaw
from app.services.law_registry import LAW_REGISTRY
from app.services.fetcher import fetch_law
from app.services.indexer import upsert_articles
from sqlalchemy import select

logger = logging.getLogger(__name__)
scheduler = AsyncIOScheduler()


async def run_law_update(law_id: str | None = None):
    """Update one law (by law_id) or all laws (law_id=None).

    Writes one LawUpdateLog entry per law processed.
    """
    laws_to_update = (
        [law for law in LAW_REGISTRY if law.law_id == law_id]
        if law_id
        else list(LAW_REGISTRY)
    )

    for law_info in laws_to_update:
        logger.info(f"Updating {law_info.law_name} ({law_info.law_id})...")
        async with AsyncSessionLocal() as db:
            try:
                articles = await fetch_law(law_info.law_id, law_info.law_name)
                result = await upsert_articles(articles, db, law_info.law_id, law_info.law_name)
                log = LawUpdateLog(
                    law_id=law_info.law_id,
                    articles_changed=result.inserted + result.updated,
                    status="success",
                )
                logger.info(
                    f"[{law_info.law_id}] done: +{result.inserted} ~{result.updated}"
                )
            except Exception as e:
                log = LawUpdateLog(
                    law_id=law_info.law_id,
                    status="failed",
                    error_message=str(e),
                )
                # Mark supported_laws as failed
                try:
                    sl = (await db.execute(
                        select(SupportedLaw).where(SupportedLaw.law_id == law_info.law_id)
                    )).scalar_one_or_none()
                    if sl:
                        sl.last_status = "failed"
                except Exception:
                    pass
                logger.error(f"[{law_info.law_id}] failed: {e}")
            finally:
                try:
                    db.add(log)
                    await db.commit()
                except Exception as log_err:
                    logger.error(f"Failed to write update log: {log_err}")


def start_scheduler():
    scheduler.add_job(run_law_update, "cron", day_of_week="mon", hour=2, minute=0)
    scheduler.start()
    logger.info("Scheduler started — law update runs every Monday at 02:00")
```

- [ ] **Step 2: Update main.py — startup seeding + laws router**

Replace `backend/app/main.py`:

```python
from __future__ import annotations
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routers import query, sessions, articles, laws

logger = logging.getLogger(__name__)


async def _seed_supported_laws():
    """Ensure supported_laws has a row for every law in the registry.

    For pre-existing 勞動基準法 rows in law_articles, counts actual articles
    so the table shows the real count without requiring a manual re-index.
    """
    from app.db.database import AsyncSessionLocal
    from app.db.models import LawArticle, SupportedLaw
    from app.services.law_registry import LAW_REGISTRY
    from sqlalchemy import select, func

    async with AsyncSessionLocal() as db:
        for law_info in LAW_REGISTRY:
            existing = (await db.execute(
                select(SupportedLaw).where(SupportedLaw.law_id == law_info.law_id)
            )).scalar_one_or_none()
            if existing:
                continue
            # Count real articles for this law already in DB (e.g. 勞動基準法 from before migration)
            count = (await db.execute(
                select(func.count()).select_from(LawArticle).where(
                    LawArticle.law_id == law_info.law_id,
                    LawArticle.is_active == True,
                )
            )).scalar() or 0
            db.add(SupportedLaw(
                law_id=law_info.law_id,
                law_name=law_info.law_name,
                article_count=count,
                last_status="success" if count > 0 else "never_run",
            ))
        await db.commit()
    logger.info("supported_laws seeded")


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        await _seed_supported_laws()
    except Exception as e:
        logger.error(f"Failed to seed supported_laws: {e}")

    from app.services.scheduler import start_scheduler, scheduler
    try:
        start_scheduler()
    except Exception as e:
        logger.error(f"Failed to start scheduler: {e}")
    yield
    try:
        scheduler.shutdown()
    except Exception:
        pass


app = FastAPI(title="勞動法規 RAG API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(query.router, prefix="/api")
app.include_router(sessions.router, prefix="/api")
app.include_router(articles.router, prefix="/api")
app.include_router(laws.router, prefix="/api")
```

- [ ] **Step 3: Update query.py — add law_ids**

Replace `backend/app/routers/query.py`:

```python
from __future__ import annotations
import uuid
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.database import get_db
from app.db.models import Session, QueryHistory
from app.services.rag import query_law
from app.services.law_registry import VALID_LAW_IDS

router = APIRouter()


class QueryRequest(BaseModel):
    question: str
    session_id: Optional[str] = None
    law_ids: Optional[list[str]] = None


@router.post("/query")
async def handle_query(request: QueryRequest, db: AsyncSession = Depends(get_db)):
    if len(request.question) > 500:
        raise HTTPException(status_code=400, detail="問題長度不得超過 500 字")

    # Whitelist law_ids against registry — reject unknown IDs silently
    safe_law_ids = (
        [lid for lid in request.law_ids if lid in VALID_LAW_IDS]
        if request.law_ids
        else []
    )

    # Get or create session
    if request.session_id:
        try:
            session_id = uuid.UUID(request.session_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid session_id format")
    else:
        title = request.question[:20]
        session = Session(title=title)
        db.add(session)
        await db.flush()
        session_id = session.id

    result = await query_law(
        request.question,
        db,
        law_ids=safe_law_ids if safe_law_ids else None,
    )

    history = QueryHistory(
        session_id=session_id,
        question=request.question,
        answer=result.answer,
        cited_articles=result.cited_articles,
        max_similarity_score=(
            result.cited_articles[0]["similarity"] if result.cited_articles else None
        ),
    )
    db.add(history)
    await db.commit()

    return {
        "session_id": str(session_id),
        "is_out_of_scope": result.is_out_of_scope,
        "answer": result.answer,
        "warning": result.warning,
        "cited_articles": result.cited_articles,
    }
```

- [ ] **Step 4: Restart and verify**

```bash
docker compose restart backend && sleep 8
docker compose logs backend 2>&1 | grep -E "(startup|seed|error|Error)" | head -10
```

Expected: "supported_laws seeded", "Application startup complete", no errors.

- [ ] **Step 5: Verify GET /api/laws works**

```bash
curl -s http://localhost:8000/api/laws | python3 -m json.tool | head -20
```

Expected: JSON array with 11 laws; 勞動基準法 should show `article_count > 0` and `last_status: "success"`.

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/scheduler.py backend/app/main.py backend/app/routers/query.py
git commit -m "feat: wire laws router, startup seeding, multi-law scheduler, law_ids in query"
```

---

## Task 8: Frontend Types + API Client

**Files:**
- Modify: `frontend/src/types/index.ts`
- Modify: `frontend/src/lib/api.ts`

- [ ] **Step 1: Update types/index.ts**

Replace `frontend/src/types/index.ts`:

```typescript
export interface CitedArticle {
  article_number: string;
  title: string | null;
  law_id: string;
  law_name: string;
  similarity: number;
}

export interface QueryResponse {
  session_id: string;
  is_out_of_scope: boolean;
  answer: string | null;
  warning: string | null;
  cited_articles: CitedArticle[];
}

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
  cited_articles?: CitedArticle[];
  warning?: string | null;
  is_out_of_scope?: boolean;
}

export interface SessionSummary {
  id: string;
  title: string;
  created_at: string;
}

export interface LawArticle {
  article_number: string;
  title: string | null;
  content: string;
  last_updated: string | null;
  version: string | null;
}

export interface LawStatus {
  last_updated: string | null;
  status: string;
  total_active_articles: number;
}

export interface QueryHistoryItem {
  id: string;
  question: string;
  answer: string;
  cited_articles: CitedArticle[];
  max_similarity_score: number;
  created_at: string;
}

export interface SupportedLaw {
  law_id: string;
  law_name: string;
  article_count: number;
  last_updated: string | null;
  last_status: "success" | "failed" | "never_run";
}
```

- [ ] **Step 2: Update lib/api.ts**

Replace `frontend/src/lib/api.ts`:

```typescript
import type {
  QueryResponse,
  SessionSummary,
  QueryHistoryItem,
  LawArticle,
  LawStatus,
  SupportedLaw,
} from "@/types";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export async function postQuery(
  question: string,
  sessionId?: string,
  lawIds?: string[],
): Promise<QueryResponse> {
  const body: Record<string, unknown> = { question };
  if (sessionId) body.session_id = sessionId;
  if (lawIds && lawIds.length > 0) body.law_ids = lawIds;

  const res = await fetch(`${API_BASE}/api/query`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function getSessions(): Promise<SessionSummary[]> {
  const res = await fetch(`${API_BASE}/api/sessions`);
  if (!res.ok) throw new Error("Failed to fetch sessions");
  return res.json();
}

export async function getSessionHistory(sessionId: string): Promise<QueryHistoryItem[]> {
  const res = await fetch(`${API_BASE}/api/sessions/${sessionId}/history`);
  if (!res.ok) throw new Error("Failed to fetch history");
  return res.json();
}

export async function getArticle(articleNumber: string): Promise<LawArticle> {
  const res = await fetch(`${API_BASE}/api/articles/${articleNumber}`);
  if (!res.ok) throw new Error("Article not found");
  return res.json();
}

export async function getLawStatus(): Promise<LawStatus> {
  const res = await fetch(`${API_BASE}/api/law/status`);
  if (!res.ok) throw new Error("Failed to fetch law status");
  return res.json();
}

export async function getLaws(): Promise<SupportedLaw[]> {
  const res = await fetch(`${API_BASE}/api/laws`);
  if (!res.ok) throw new Error("Failed to fetch laws");
  return res.json();
}

export async function updateLaw(
  lawId: string,
): Promise<{ status: string; article_count: number; message: string }> {
  const res = await fetch(`${API_BASE}/api/laws/${lawId}/update`, {
    method: "POST",
    signal: AbortSignal.timeout(180_000), // 180 second timeout — indexing is slow
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}
```

- [ ] **Step 3: Verify TypeScript compiles**

```bash
docker compose exec frontend npx tsc --noEmit 2>&1 | head -20
```

Expected: No errors (or only unrelated pre-existing errors).

- [ ] **Step 4: Commit**

```bash
git add frontend/src/types/index.ts frontend/src/lib/api.ts
git commit -m "feat: add SupportedLaw type, getLaws/updateLaw API client, law_ids in postQuery"
```

---

## Task 9: LawScopeSelector Component

**Files:**
- Create: `frontend/src/components/LawScopeSelector.tsx`

- [ ] **Step 1: Create LawScopeSelector.tsx**

Create `frontend/src/components/LawScopeSelector.tsx`:

```tsx
"use client";
import { useEffect, useState } from "react";
import { getLaws } from "@/lib/api";
import { SupportedLaw } from "@/types";

interface Props {
  selectedLawIds: string[]; // [] means all laws selected
  onChange: (ids: string[]) => void;
}

export default function LawScopeSelector({ selectedLawIds, onChange }: Props) {
  const [laws, setLaws] = useState<SupportedLaw[]>([]);
  const [expanded, setExpanded] = useState(false);

  useEffect(() => {
    getLaws().then(setLaws).catch(console.error);
  }, []);

  // [] means all selected; otherwise the array lists the selected law_ids
  const allSelected = selectedLawIds.length === 0;
  const selectedCount = allSelected ? laws.length : selectedLawIds.length;
  const summaryLabel = allSelected || selectedCount === laws.length ? "全部" : `${selectedCount} 部`;

  function toggle(lawId: string) {
    let next: string[];
    if (allSelected) {
      // All selected → deselect just this one
      next = laws.map((l) => l.law_id).filter((id) => id !== lawId);
    } else if (selectedLawIds.includes(lawId)) {
      next = selectedLawIds.filter((id) => id !== lawId);
      // If all deselected → revert to all selected
      if (next.length === 0) next = [];
    } else {
      next = [...selectedLawIds, lawId];
      // If all manually checked → normalize to [] (all selected)
      if (next.length === laws.length) next = [];
    }
    onChange(next);
  }

  function selectAll() {
    onChange([]);
  }

  const isChecked = (lawId: string) => allSelected || selectedLawIds.includes(lawId);

  if (laws.length === 0) return null;

  return (
    <div className="border-t border-slate-800 mt-2 pt-1">
      <button
        onClick={() => setExpanded((v) => !v)}
        className="w-full flex justify-between items-center px-1 py-1.5 text-left"
      >
        <span className="text-slate-500 text-[10px] uppercase tracking-wide">
          法規範圍{" "}
          <span className="text-blue-400 normal-case font-medium">({summaryLabel})</span>
        </span>
        <span className="text-slate-600 text-[10px]">{expanded ? "▼" : "▶"}</span>
      </button>

      {expanded && (
        <div className="pb-1">
          <div className="flex justify-end px-1 mb-1">
            <button
              onClick={selectAll}
              className="text-blue-500 text-[9px] hover:text-blue-400 transition-colors"
            >
              全選
            </button>
          </div>
          <div className="flex flex-col gap-0.5 max-h-48 overflow-y-auto">
            {laws.map((law) => (
              <label
                key={law.law_id}
                className="flex items-center gap-1.5 px-1 py-0.5 cursor-pointer hover:bg-slate-800 rounded"
              >
                <input
                  type="checkbox"
                  checked={isChecked(law.law_id)}
                  onChange={() => toggle(law.law_id)}
                  className="accent-blue-500 flex-shrink-0"
                />
                <span
                  className={`text-[10px] leading-tight ${
                    isChecked(law.law_id) ? "text-slate-300" : "text-slate-500"
                  }`}
                >
                  {law.law_name}
                </span>
              </label>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Verify no TypeScript errors**

```bash
docker compose exec frontend npx tsc --noEmit 2>&1 | head -20
```

Expected: No new errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/LawScopeSelector.tsx
git commit -m "feat: add LawScopeSelector collapsible checkbox component"
```

---

## Task 10: Sidebar + page.tsx + ChatPanel Wiring

**Files:**
- Modify: `frontend/src/components/Sidebar.tsx`
- Modify: `frontend/src/app/page.tsx`
- Modify: `frontend/src/components/ChatPanel.tsx`

- [ ] **Step 1: Update Sidebar.tsx**

Replace `frontend/src/components/Sidebar.tsx`:

```tsx
"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { getSessions, getLawStatus } from "@/lib/api";
import { SessionSummary, LawStatus } from "@/types";
import LawScopeSelector from "@/components/LawScopeSelector";

interface Props {
  activeSessionId: string | null;
  onSelectSession: (id: string) => void;
  onNewSession: () => void;
  refreshKey?: number;
  selectedLawIds: string[];
  onLawScopeChange: (ids: string[]) => void;
  showLawScope?: boolean; // false on /laws page
}

export default function Sidebar({
  activeSessionId,
  onSelectSession,
  onNewSession,
  refreshKey,
  selectedLawIds,
  onLawScopeChange,
  showLawScope = true,
}: Props) {
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [status, setStatus] = useState<LawStatus | null>(null);
  const pathname = usePathname();

  useEffect(() => {
    getSessions().then(setSessions).catch(console.error);
  }, [refreshKey]);

  useEffect(() => {
    getLawStatus().then(setStatus).catch(console.error);
  }, []);

  return (
    <aside className="w-56 bg-slate-900 flex flex-col p-3 gap-3 shrink-0">
      <span className="text-blue-400 font-bold text-xs tracking-wide uppercase">查詢紀錄</span>
      <button
        onClick={onNewSession}
        className="bg-blue-700 text-white rounded-md py-2 text-xs font-medium hover:bg-blue-600 transition-colors"
      >
        + 新增查詢
      </button>

      {showLawScope && (
        <LawScopeSelector
          selectedLawIds={selectedLawIds}
          onChange={onLawScopeChange}
        />
      )}

      <div className="flex-1 overflow-y-auto flex flex-col gap-1">
        {sessions.map((s) => (
          <button
            key={s.id}
            onClick={() => onSelectSession(s.id)}
            className={`text-left px-3 py-2 rounded text-xs transition-colors ${
              s.id === activeSessionId
                ? "bg-blue-950 border-l-2 border-blue-400 text-blue-300"
                : "text-slate-400 hover:bg-slate-800"
            }`}
          >
            {s.title}
          </button>
        ))}
      </div>

      {status && (
        <div className="bg-slate-950 rounded p-2 text-xs border border-slate-800">
          <div className="text-slate-500 text-[10px] mb-1">法條版本</div>
          <div className="text-slate-400">
            {status.last_updated
              ? new Date(status.last_updated).toLocaleDateString("zh-TW")
              : "尚未更新"}
          </div>
          <div
            className={`text-[10px] mt-1 ${
              status.status === "success" ? "text-green-500" : "text-yellow-500"
            }`}
          >
            {status.status === "success" ? "✓ 最新版本" : "⚠ 更新異常"}
          </div>
        </div>
      )}

      {/* Law management nav link */}
      <Link
        href="/laws"
        className={`text-xs text-center py-1.5 rounded transition-colors ${
          pathname === "/laws"
            ? "bg-blue-950 text-blue-300 border border-blue-700"
            : "text-slate-500 hover:text-slate-300 hover:bg-slate-800"
        }`}
      >
        📋 法規管理
      </Link>
    </aside>
  );
}
```

- [ ] **Step 2: Update page.tsx**

Replace `frontend/src/app/page.tsx`:

```tsx
"use client";
import { useState, useCallback } from "react";
import Sidebar from "@/components/Sidebar";
import ChatPanel from "@/components/ChatPanel";
import ArticlePanel from "@/components/ArticlePanel";
import { ChatMessage, CitedArticle, QueryHistoryItem } from "@/types";

export default function Home() {
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [citedArticles, setCitedArticles] = useState<CitedArticle[]>([]);
  const [sidebarRefreshKey, setSidebarRefreshKey] = useState(0);
  const [selectedLawIds, setSelectedLawIds] = useState<string[]>([]); // [] = all laws

  const handleSelectSession = useCallback(async (sessionId: string) => {
    const { getSessionHistory } = await import("@/lib/api");
    setActiveSessionId(sessionId);
    setCitedArticles([]);
    const history = await getSessionHistory(sessionId);
    const msgs: ChatMessage[] = history.flatMap((h: QueryHistoryItem) => [
      { role: "user" as const, content: h.question },
      {
        role: "assistant" as const,
        content: h.answer ?? "此問題超出勞基法範圍。",
        cited_articles: h.cited_articles,
      },
    ]);
    setMessages(msgs);
    const lastCited = history.findLast((h: QueryHistoryItem) => h.cited_articles?.length)?.cited_articles;
    if (lastCited) setCitedArticles(lastCited);
  }, []);

  const handleNewSession = useCallback(() => {
    setActiveSessionId(null);
    setMessages([]);
    setCitedArticles([]);
  }, []);

  const handleNewMessage = useCallback(
    (userMsg: ChatMessage, assistantMsg: ChatMessage, sessionId: string) => {
      setMessages((prev) => [...prev, userMsg, assistantMsg]);
      if (!activeSessionId) {
        setActiveSessionId(sessionId);
        setSidebarRefreshKey((k) => k + 1);
      }
    },
    [activeSessionId]
  );

  return (
    <main className="flex h-screen bg-slate-800 text-white overflow-hidden">
      <Sidebar
        activeSessionId={activeSessionId}
        onSelectSession={handleSelectSession}
        onNewSession={handleNewSession}
        refreshKey={sidebarRefreshKey}
        selectedLawIds={selectedLawIds}
        onLawScopeChange={setSelectedLawIds}
        showLawScope={true}
      />
      <ChatPanel
        sessionId={activeSessionId}
        messages={messages}
        onNewMessage={handleNewMessage}
        onArticlesChange={setCitedArticles}
        selectedLawIds={selectedLawIds}
      />
      <ArticlePanel citedArticles={citedArticles} />
    </main>
  );
}
```

- [ ] **Step 3: Update ChatPanel.tsx — accept and forward selectedLawIds**

In `frontend/src/components/ChatPanel.tsx`, add `selectedLawIds` prop and pass to `postQuery`:

```tsx
// Add to Props interface:
selectedLawIds: string[];

// Update function signature:
export default function ChatPanel({ sessionId, messages, onNewMessage, onArticlesChange, selectedLawIds }: Props) {

// Update postQuery call inside handleSubmit:
const data = await postQuery(question, sessionId ?? undefined, selectedLawIds.length > 0 ? selectedLawIds : undefined);
```

Full updated `frontend/src/components/ChatPanel.tsx`:

```tsx
"use client";
import { useState, useRef, useEffect } from "react";
import ReactMarkdown from "react-markdown";
import { ChatMessage, CitedArticle } from "@/types";
import { postQuery } from "@/lib/api";

interface Props {
  sessionId: string | null;
  messages: ChatMessage[];
  onNewMessage: (userMsg: ChatMessage, assistantMsg: ChatMessage, sessionId: string) => void;
  onArticlesChange: (articles: CitedArticle[]) => void;
  selectedLawIds: string[];
}

export default function ChatPanel({ sessionId, messages, onNewMessage, onArticlesChange, selectedLawIds }: Props) {
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  async function handleSubmit() {
    const question = input.trim();
    if (!question || loading) return;
    if (question.length > 500) {
      alert("問題長度不得超過 500 字");
      return;
    }

    setInput("");
    setLoading(true);

    const userMsg: ChatMessage = { role: "user", content: question };

    try {
      const data = await postQuery(
        question,
        sessionId ?? undefined,
        selectedLawIds.length > 0 ? selectedLawIds : undefined,
      );
      const assistantMsg: ChatMessage = {
        role: "assistant",
        content: data.is_out_of_scope
          ? "此問題超出所選法規範圍，無法提供答案。"
          : data.answer ?? "",
        cited_articles: data.cited_articles,
        warning: data.warning,
        is_out_of_scope: data.is_out_of_scope,
      };
      onNewMessage(userMsg, assistantMsg, data.session_id);
      if (data.cited_articles?.length) onArticlesChange(data.cited_articles);
    } catch {
      const errorMsg: ChatMessage = { role: "assistant", content: "發生錯誤，請稍後重試。" };
      onNewMessage(userMsg, errorMsg, sessionId ?? "");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="flex-1 flex flex-col bg-slate-800 min-w-0">
      <div className="flex-1 overflow-y-auto p-4 flex flex-col gap-4">
        {messages.length === 0 && (
          <div className="text-slate-500 text-sm text-center mt-20">
            輸入勞動法規相關問題開始查詢
          </div>
        )}
        {messages.map((msg, i) => (
          <div key={i} className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}>
            <div
              className={`max-w-[80%] rounded-xl px-4 py-3 text-sm leading-relaxed ${
                msg.role === "user"
                  ? "bg-blue-700 text-white rounded-br-sm"
                  : "bg-slate-900 text-slate-200 rounded-bl-sm"
              }`}
            >
              {msg.role === "assistant" && (
                <div className="text-blue-400 font-semibold text-xs mb-2">🤖 AI 回覆</div>
              )}
              {msg.role === "assistant" ? (
                <div className="prose prose-invert prose-sm max-w-none prose-p:my-1 prose-headings:my-2 prose-ul:my-1 prose-ol:my-1 prose-li:my-0">
                  <ReactMarkdown>{msg.content}</ReactMarkdown>
                </div>
              ) : (
                <p className="whitespace-pre-wrap">{msg.content}</p>
              )}
              {msg.warning && (
                <div className="mt-2 text-yellow-400 text-xs bg-yellow-900/20 rounded p-2">
                  ⚠ {msg.warning}
                </div>
              )}
              {msg.cited_articles && msg.cited_articles.length > 0 && (
                <div className="mt-3 flex flex-wrap gap-2 items-center">
                  <span className="text-slate-500 text-xs">參考法條：</span>
                  {msg.cited_articles.map((c) => (
                    <span
                      key={`${c.law_id}-${c.article_number}`}
                      className="bg-blue-950 border border-blue-700 text-blue-300 px-2 py-1 rounded-full text-xs"
                      title={c.law_name}
                    >
                      {c.law_name} §{c.article_number}
                    </span>
                  ))}
                  <span className="text-slate-600 text-xs border border-slate-700 px-2 py-1 rounded-full">
                    相關度 {Math.round(msg.cited_articles[0].similarity * 100)}%
                  </span>
                </div>
              )}
            </div>
          </div>
        ))}
        {loading && (
          <div className="flex justify-start">
            <div className="bg-slate-900 text-slate-400 rounded-xl px-4 py-3 text-sm">
              查詢中...
            </div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      <div className="p-3 bg-slate-900 border-t border-slate-700 flex gap-2 items-end">
        <textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
              e.preventDefault();
              handleSubmit();
            }
          }}
          placeholder="輸入您的勞動法規問題... （Ctrl+Enter 送出）"
          rows={2}
          className="flex-1 bg-slate-800 border border-slate-700 text-slate-200 placeholder-slate-500 rounded-lg px-4 py-2.5 text-sm outline-none focus:border-blue-500 resize-none"
          disabled={loading}
          maxLength={500}
        />
        <button
          onClick={handleSubmit}
          disabled={loading || !input.trim()}
          className="bg-blue-700 text-white rounded-lg px-4 py-2.5 text-sm font-medium hover:bg-blue-600 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
        >
          送出
        </button>
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Verify TypeScript compiles and frontend loads**

```bash
docker compose exec frontend npx tsc --noEmit 2>&1 | head -20
```

Expected: No errors. Then open http://localhost:3000 — law scope panel should appear in sidebar.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/Sidebar.tsx frontend/src/app/page.tsx frontend/src/components/ChatPanel.tsx
git commit -m "feat: add law scope selector to sidebar, wire selectedLawIds through query chain"
```

---

## Task 11: Laws Page

**Files:**
- Create: `frontend/src/app/laws/page.tsx`

- [ ] **Step 1: Create laws/page.tsx**

Create `frontend/src/app/laws/page.tsx`:

```tsx
"use client";
import { useEffect, useState, useCallback } from "react";
import Link from "next/link";
import Sidebar from "@/components/Sidebar";
import { getLaws, updateLaw } from "@/lib/api";
import { SupportedLaw } from "@/types";

function StatusBadge({ status }: { status: SupportedLaw["last_status"] }) {
  if (status === "success")
    return <span className="text-green-400 text-xs">✓ 最新</span>;
  if (status === "failed")
    return <span className="text-red-400 text-xs">✗ 更新失敗</span>;
  return <span className="text-yellow-500 text-xs">⚠ 未載入</span>;
}

export default function LawsPage() {
  const [laws, setLaws] = useState<SupportedLaw[]>([]);
  const [updating, setUpdating] = useState<Record<string, boolean>>({});
  const [errors, setErrors] = useState<Record<string, string>>({});

  const fetchLaws = useCallback(async () => {
    try {
      setLaws(await getLaws());
    } catch {
      // silent — table will be empty
    }
  }, []);

  useEffect(() => {
    fetchLaws();
  }, [fetchLaws]);

  async function handleUpdate(lawId: string) {
    setUpdating((prev) => ({ ...prev, [lawId]: true }));
    setErrors((prev) => ({ ...prev, [lawId]: "" }));
    try {
      await updateLaw(lawId);
      await fetchLaws(); // refresh row
    } catch (e) {
      setErrors((prev) => ({
        ...prev,
        [lawId]: e instanceof Error ? e.message : "更新失敗",
      }));
    } finally {
      setUpdating((prev) => ({ ...prev, [lawId]: false }));
    }
  }

  return (
    <main className="flex h-screen bg-slate-800 text-white overflow-hidden">
      <Sidebar
        activeSessionId={null}
        onSelectSession={() => {}}
        onNewSession={() => {}}
        selectedLawIds={[]}
        onLawScopeChange={() => {}}
        showLawScope={false}
      />

      <div className="flex-1 flex flex-col min-w-0 p-6">
        <div className="flex items-center gap-4 mb-6">
          <Link href="/" className="text-slate-400 hover:text-white text-sm transition-colors">
            ← 返回查詢
          </Link>
          <h1 className="text-white font-semibold text-lg">法規管理</h1>
        </div>

        <div className="bg-slate-900 rounded-lg border border-slate-700 overflow-hidden">
          {/* Table header */}
          <div className="grid grid-cols-[2fr_80px_140px_100px_80px] gap-4 px-4 py-2.5 bg-slate-950 text-slate-500 text-xs font-medium uppercase tracking-wide border-b border-slate-700">
            <span>法規名稱</span>
            <span>條文數</span>
            <span>最後更新</span>
            <span>狀態</span>
            <span></span>
          </div>

          {laws.length === 0 && (
            <div className="px-4 py-8 text-center text-slate-500 text-sm">
              載入中...
            </div>
          )}

          {laws.map((law, i) => (
            <div
              key={law.law_id}
              className={`grid grid-cols-[2fr_80px_140px_100px_80px] gap-4 px-4 py-3 items-center text-sm ${
                i > 0 ? "border-t border-slate-800" : ""
              }`}
            >
              <span className="text-slate-200 font-medium">{law.law_name}</span>
              <span className="text-slate-400 text-xs">
                {law.article_count > 0 ? law.article_count : "—"}
              </span>
              <span className="text-slate-500 text-xs">
                {law.last_updated
                  ? new Date(law.last_updated).toLocaleDateString("zh-TW")
                  : "尚未更新"}
              </span>
              <span>
                <StatusBadge status={law.last_status} />
                {errors[law.law_id] && (
                  <div className="text-red-400 text-[10px] mt-0.5 leading-tight">
                    {errors[law.law_id]}
                  </div>
                )}
              </span>
              <span>
                <button
                  onClick={() => handleUpdate(law.law_id)}
                  disabled={updating[law.law_id]}
                  className={`text-xs px-3 py-1.5 rounded transition-colors w-full ${
                    law.last_status === "never_run"
                      ? "bg-blue-700 text-white hover:bg-blue-600 disabled:opacity-50"
                      : "bg-slate-700 text-slate-300 hover:bg-slate-600 disabled:opacity-50"
                  } disabled:cursor-not-allowed`}
                >
                  {updating[law.law_id] ? (
                    <span className="inline-flex items-center gap-1">
                      <svg className="animate-spin h-3 w-3" viewBox="0 0 24 24" fill="none">
                        <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                        <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
                      </svg>
                      更新中
                    </span>
                  ) : law.last_status === "never_run" ? (
                    "載入"
                  ) : (
                    "更新"
                  )}
                </button>
              </span>
            </div>
          ))}
        </div>

        <p className="text-slate-600 text-xs mt-3">
          共 {laws.length} 部法規 · 資料來源：全國法規資料庫（kong0107/mojLawSplitJSON）
        </p>
      </div>
    </main>
  );
}
```

- [ ] **Step 2: Verify TypeScript compiles**

```bash
docker compose exec frontend npx tsc --noEmit 2>&1 | head -20
```

Expected: No errors.

- [ ] **Step 3: Test the page in browser**

Open http://localhost:3000/laws — verify:
- Table shows 11 laws
- 勞動基準法 shows correct article count and "✓ 最新"
- Other laws show "⚠ 未載入"
- Sidebar "📋 法規管理" link is highlighted
- "← 返回查詢" link navigates back to `/`

- [ ] **Step 4: Test loading one law**

Click "載入" on 勞工請假規則 — verify spinner appears, then row updates with article count and "✓ 最新" after completion (may take 30–120 seconds).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/app/laws/page.tsx
git commit -m "feat: add /laws management page with per-law status and update buttons"
```

---

## Final Verification

- [ ] Open http://localhost:3000 — law scope selector visible in sidebar, collapses/expands correctly
- [ ] Select 2–3 laws, ask a question — response only cites articles from selected laws
- [ ] Deselect all → auto-reverts to all selected → query searches all laws
- [ ] Open http://localhost:3000/laws — all 11 laws listed, update buttons work
- [ ] `curl -s http://localhost:8000/api/laws | python3 -m json.tool` — 11 laws returned
- [ ] Run all backend tests: `docker compose exec backend python -m pytest tests/ -v 2>&1 | tail -20`

```bash
git add .
git commit -m "feat: multi-law support complete — 11 HR laws, law scope selector, /laws management page"
```
