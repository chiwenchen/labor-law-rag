# 勞基法 RAG 查詢系統 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Docker Compose RAG chatbot that lets HR query Taiwan's Labor Standards Act in natural language, returning AI summaries with cited law articles.

**Architecture:** FastAPI backend uses LlamaIndex to query pgvector for relevant law articles, then sends them to Claude API for response generation. A weekly APScheduler job fetches updated articles from 全國法規資料庫 API and re-embeds any changes using local BAAI/bge-m3. Next.js frontend renders a 3-column layout (session history / chat / law article viewer).

**Tech Stack:** Python 3.11, FastAPI, LlamaIndex, PostgreSQL + pgvector, BAAI/bge-m3 (sentence-transformers), Claude API (claude-sonnet-4-6), Next.js 14, Tailwind CSS, Docker Compose, pytest, APScheduler

---

## File Map

```
labor-law-rag/
├── docker-compose.yml
├── .env.example
├── backend/
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── app/
│   │   ├── main.py               # FastAPI app, router registration, lifespan
│   │   ├── config.py             # Pydantic Settings (env vars)
│   │   ├── db/
│   │   │   ├── database.py       # SQLAlchemy async engine + session factory
│   │   │   ├── models.py         # ORM models: LawArticle, Session, QueryHistory, LawUpdateLog
│   │   │   └── migrations/
│   │   │       └── init.sql      # CREATE TABLE + pgvector extension
│   │   ├── services/
│   │   │   ├── embedder.py       # Singleton bge-m3 HuggingFaceEmbedding wrapper
│   │   │   ├── fetcher.py        # HTTP client for 全國法規資料庫 API
│   │   │   ├── indexer.py        # Upsert articles into pgvector via LlamaIndex
│   │   │   ├── rag.py            # LlamaIndex query engine: embed question → search → Claude
│   │   │   └── scheduler.py      # APScheduler weekly job wiring
│   │   └── routers/
│   │       ├── query.py          # POST /api/query
│   │       ├── sessions.py       # GET /api/sessions, GET /api/sessions/{id}/history
│   │       └── articles.py       # GET /api/articles/{number}, GET /api/law/status
│   └── tests/
│       ├── conftest.py           # pytest fixtures: test DB, test client, mock embedder
│       ├── test_fetcher.py
│       ├── test_indexer.py
│       ├── test_rag.py
│       └── test_api.py
└── frontend/
    ├── Dockerfile
    ├── package.json
    └── src/
        ├── app/
        │   ├── layout.tsx
        │   └── page.tsx          # Root page, assembles 3 panels
        ├── components/
        │   ├── Sidebar.tsx       # Session list + version status
        │   ├── ChatPanel.tsx     # Message thread + input box
        │   └── ArticlePanel.tsx  # Law article full text viewer
        ├── lib/
        │   └── api.ts            # Typed fetch wrappers for all 5 API endpoints
        └── types/
            └── index.ts          # Shared TypeScript interfaces
```

---

## Task 1: Project Scaffold + Docker Compose

**Files:**
- Create: `docker-compose.yml`
- Create: `.env.example`
- Create: `backend/Dockerfile`
- Create: `backend/requirements.txt`
- Create: `frontend/Dockerfile`

- [ ] **Step 1: Create `.env.example`**

```bash
# .env.example
ANTHROPIC_API_KEY=your_claude_api_key_here
POSTGRES_USER=laborlaw
POSTGRES_PASSWORD=laborlaw
POSTGRES_DB=laborlaw
DATABASE_URL=postgresql+asyncpg://laborlaw:laborlaw@db:5432/laborlaw
```

- [ ] **Step 2: Create `backend/requirements.txt`**

```
fastapi==0.111.0
uvicorn[standard]==0.29.0
sqlalchemy[asyncio]==2.0.30
asyncpg==0.29.0
psycopg2-binary==2.9.9
pgvector==0.3.2
llama-index==0.10.43
llama-index-vector-stores-postgres==0.1.14
llama-index-embeddings-huggingface==0.2.3
llama-index-llms-anthropic==0.3.0
sentence-transformers==3.0.1
anthropic==0.28.0
apscheduler==3.10.4
httpx==0.27.0
pydantic-settings==2.3.0
pytest==8.2.0
pytest-asyncio==0.23.7
```

- [ ] **Step 3: Create `backend/Dockerfile`**

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app/ ./app/
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
```

- [ ] **Step 4: Create `frontend/Dockerfile`**

```dockerfile
FROM node:20-alpine
WORKDIR /app
COPY package*.json .
RUN npm ci
COPY . .
CMD ["npm", "run", "dev"]
```

- [ ] **Step 5: Create `docker-compose.yml`**

```yaml
version: "3.9"
services:
  db:
    image: pgvector/pgvector:pg16
    environment:
      POSTGRES_USER: ${POSTGRES_USER}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
      POSTGRES_DB: ${POSTGRES_DB}
    ports:
      - "5432:5432"
    volumes:
      - pgdata:/var/lib/postgresql/data
      - ./backend/app/db/migrations/init.sql:/docker-entrypoint-initdb.d/init.sql

  backend:
    build: ./backend
    env_file: .env
    ports:
      - "8000:8000"
    volumes:
      - ./backend:/app
      - hf_cache:/root/.cache/huggingface
    depends_on:
      - db

  frontend:
    build: ./frontend
    ports:
      - "3000:3000"
    volumes:
      - ./frontend:/app
      - /app/node_modules
    depends_on:
      - backend

volumes:
  pgdata:
  hf_cache:
```

> `hf_cache` volume prevents re-downloading the bge-m3 model (2GB) on every restart.

- [ ] **Step 6: Copy `.env.example` to `.env` and fill in `ANTHROPIC_API_KEY`**

```bash
cp .env.example .env
# Edit .env and set your real ANTHROPIC_API_KEY
```

- [ ] **Step 7: Commit**

```bash
git add docker-compose.yml .env.example backend/Dockerfile backend/requirements.txt frontend/Dockerfile
git commit -m "chore: project scaffold and Docker Compose"
```

---

## Task 2: Database Schema + Config

**Files:**
- Create: `backend/app/db/migrations/init.sql`
- Create: `backend/app/config.py`
- Create: `backend/app/db/database.py`
- Create: `backend/app/db/models.py`

- [ ] **Step 1: Create `backend/app/db/migrations/init.sql`**

```sql
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title VARCHAR(100) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now()
);

CREATE TABLE IF NOT EXISTS law_articles (
    id SERIAL PRIMARY KEY,
    article_number VARCHAR(20) UNIQUE NOT NULL,
    title VARCHAR(200),
    content TEXT NOT NULL,
    embedding vector(1024),
    is_active BOOLEAN DEFAULT true,
    last_updated TIMESTAMP WITH TIME ZONE,
    version VARCHAR(50)
);

CREATE INDEX IF NOT EXISTS law_articles_embedding_idx
    ON law_articles USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 10);

CREATE TABLE IF NOT EXISTS query_history (
    id SERIAL PRIMARY KEY,
    session_id UUID REFERENCES sessions(id) ON DELETE CASCADE,
    question TEXT NOT NULL,
    answer TEXT,
    cited_articles JSONB,
    max_similarity_score FLOAT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now()
);

CREATE TABLE IF NOT EXISTS law_update_logs (
    id SERIAL PRIMARY KEY,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now(),
    articles_changed INTEGER DEFAULT 0,
    status VARCHAR(20) NOT NULL,
    error_message TEXT
);
```

- [ ] **Step 2: Create `backend/app/config.py`**

```python
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    anthropic_api_key: str
    database_url: str
    postgres_user: str = "laborlaw"
    postgres_password: str = "laborlaw"
    postgres_db: str = "laborlaw"

    class Config:
        env_file = ".env"

settings = Settings()
```

- [ ] **Step 3: Create `backend/app/db/database.py`**

```python
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from app.config import settings

engine = create_async_engine(settings.database_url, echo=False)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)

async def get_db() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        yield session
```

- [ ] **Step 4: Create `backend/app/db/models.py`**

```python
import uuid
from sqlalchemy import Column, Integer, String, Text, Boolean, Float, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB
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
    id = Column(Integer, primary_key=True)
    article_number = Column(String(20), unique=True, nullable=False)
    title = Column(String(200))
    content = Column(Text, nullable=False)
    embedding = Column(Vector(1024))
    is_active = Column(Boolean, default=True)
    last_updated = Column(DateTime(timezone=True))
    version = Column(String(50))

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
    updated_at = Column(DateTime(timezone=True), server_default=func.now())
    articles_changed = Column(Integer, default=0)
    status = Column(String(20), nullable=False)
    error_message = Column(Text)
```

- [ ] **Step 5: Commit**

```bash
git add backend/app/
git commit -m "feat: database schema, config, and ORM models"
```

---

## Task 3: Embedding Service

**Files:**
- Create: `backend/app/services/embedder.py`
- Create: `backend/tests/conftest.py`

The embedder wraps bge-m3 as a singleton so the model is only loaded once per process.

- [ ] **Step 1: Create `backend/tests/conftest.py`**

```python
import pytest
from unittest.mock import MagicMock

@pytest.fixture
def mock_embedder(monkeypatch):
    """Returns a fixed 1024-dim vector for any input — avoids loading bge-m3 in tests."""
    mock = MagicMock()
    mock.get_text_embedding.return_value = [0.1] * 1024
    mock.get_text_embedding_batch.return_value = [[0.1] * 1024]
    return mock
```

- [ ] **Step 2: Write failing test for embedder**

Create `backend/tests/test_embedder.py`:

```python
from app.services.embedder import get_embedder

def test_embedder_returns_1024_dim_vector():
    embedder = get_embedder()
    vector = embedder.get_text_embedding("員工特休假天數規定")
    assert len(vector) == 1024
    assert all(isinstance(v, float) for v in vector)

def test_embedder_is_singleton():
    assert get_embedder() is get_embedder()
```

- [ ] **Step 3: Run test to verify it fails**

```bash
cd backend && python -m pytest tests/test_embedder.py -v
```

Expected: `ModuleNotFoundError` or `ImportError`

- [ ] **Step 4: Create `backend/app/services/embedder.py`**

```python
from llama_index.embeddings.huggingface import HuggingFaceEmbedding

_embedder: HuggingFaceEmbedding | None = None

def get_embedder() -> HuggingFaceEmbedding:
    global _embedder
    if _embedder is None:
        _embedder = HuggingFaceEmbedding(
            model_name="BAAI/bge-m3",
            embed_batch_size=32,
        )
    return _embedder
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
cd backend && python -m pytest tests/test_embedder.py -v
```

Expected: PASS (note: first run downloads bge-m3, ~2GB, takes a few minutes)

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/embedder.py backend/tests/
git commit -m "feat: bge-m3 embedding service singleton"
```

---

## Task 4: Law Fetcher (全國法規資料庫 API)

**Files:**
- Create: `backend/app/services/fetcher.py`
- Create: `backend/tests/test_fetcher.py`

The 全國法規資料庫 REST API docs are at: `https://law.moj.gov.tw/api/swagger/index.html`

Key endpoint: `GET https://law.moj.gov.tw/api/CH/Laws/{pcode}/AllArticles`
- 勞動基準法 pcode: `C0030001`
- Response: JSON with `LawArticles` array, each item has `ArticleNo`, `ArticleContent`

- [ ] **Step 1: Write failing test for fetcher**

Create `backend/tests/test_fetcher.py`:

```python
import pytest
from unittest.mock import AsyncMock, patch
from app.services.fetcher import fetch_labor_law_articles, LawArticleData

MOCK_RESPONSE = {
    "LawArticles": [
        {
            "ArticleType": "A",
            "ArticleNo": "38",
            "ArticleContent": "勞工在同一雇主或事業單位，繼續工作滿一定期間者，應依下列規定給予特別休假..."
        }
    ],
    "LawFetchDate": "2024-01-17"
}

@pytest.mark.asyncio
async def test_fetch_returns_list_of_articles():
    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = MOCK_RESPONSE
        articles = await fetch_labor_law_articles()
    assert len(articles) == 1
    assert articles[0].article_number == "38"
    assert "特別休假" in articles[0].content

@pytest.mark.asyncio
async def test_fetch_skips_non_article_entries():
    """Entries with ArticleType != 'A' (e.g. chapter headings) should be excluded."""
    response = {"LawArticles": [
        {"ArticleType": "C", "ArticleNo": "", "ArticleContent": "第一章 總則"},
        {"ArticleType": "A", "ArticleNo": "1", "ArticleContent": "為規定勞動條件最低標準..."},
    ], "LawFetchDate": "2024-01-17"}
    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = response
        articles = await fetch_labor_law_articles()
    assert len(articles) == 1
    assert articles[0].article_number == "1"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd backend && python -m pytest tests/test_fetcher.py -v
```

Expected: `ModuleNotFoundError`

- [ ] **Step 3: Create `backend/app/services/fetcher.py`**

```python
from dataclasses import dataclass
import httpx

LAW_API_BASE = "https://law.moj.gov.tw/api/CH/Laws"
LABOR_LAW_PCODE = "C0030001"

@dataclass
class LawArticleData:
    article_number: str
    content: str
    version: str

async def fetch_labor_law_articles() -> list[LawArticleData]:
    url = f"{LAW_API_BASE}/{LABOR_LAW_PCODE}/AllArticles"
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = client.get(url)  # intentional bug for TDD
        response.raise_for_status()
        data = response.json()

    version = data.get("LawFetchDate", "unknown")
    articles = []
    for item in data.get("LawArticles", []):
        if item.get("ArticleType") != "A":
            continue
        article_number = item.get("ArticleNo", "").strip()
        content = item.get("ArticleContent", "").strip()
        if article_number and content:
            articles.append(LawArticleData(
                article_number=article_number,
                content=content,
                version=version,
            ))
    return articles
```

> **Note:** The fetcher uses `client.get` (sync call inside async context) intentionally as a placeholder — the test will catch this. Fix it in the next step.

- [ ] **Step 4: Run test — expect it to fail with async error**

```bash
cd backend && python -m pytest tests/test_fetcher.py -v
```

- [ ] **Step 5: Fix the async bug in fetcher.py**

Replace `response = client.get(url)` with `response = await client.get(url)`

- [ ] **Step 6: Run tests to verify they pass**

```bash
cd backend && python -m pytest tests/test_fetcher.py -v
```

Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add backend/app/services/fetcher.py backend/tests/test_fetcher.py
git commit -m "feat: law article fetcher for 全國法規資料庫 API"
```

---

## Task 5: Law Indexer (Upsert Pipeline)

**Files:**
- Create: `backend/app/services/indexer.py`
- Create: `backend/tests/test_indexer.py`

The indexer takes a list of `LawArticleData`, compares with DB, and upserts changed articles into pgvector.

- [ ] **Step 1: Write failing tests for indexer**

Create `backend/tests/test_indexer.py`:

```python
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from app.services.indexer import upsert_articles, IndexResult
from app.services.fetcher import LawArticleData

SAMPLE_ARTICLES = [
    LawArticleData(article_number="1", content="為規定勞動條件最低標準...", version="2024-01-17"),
    LawArticleData(article_number="38", content="勞工應給予特別休假...", version="2024-01-17"),
]

@pytest.mark.asyncio
async def test_upsert_new_articles_inserts_all(mock_embedder):
    """When DB is empty, all articles should be inserted."""
    mock_db = AsyncMock()
    mock_db.execute.return_value.scalars.return_value.all.return_value = []

    with patch("app.services.indexer.get_embedder", return_value=mock_embedder):
        result = await upsert_articles(SAMPLE_ARTICLES, mock_db)

    assert result.inserted == 2
    assert result.updated == 0
    assert result.skipped == 0

@pytest.mark.asyncio
async def test_upsert_unchanged_articles_skips(mock_embedder):
    """Articles with unchanged content should be skipped."""
    from app.db.models import LawArticle
    existing = MagicMock(spec=LawArticle)
    existing.article_number = "38"
    existing.content = "勞工應給予特別休假..."

    mock_db = AsyncMock()
    mock_db.execute.return_value.scalars.return_value.all.return_value = [existing]

    with patch("app.services.indexer.get_embedder", return_value=mock_embedder):
        result = await upsert_articles(
            [LawArticleData("38", "勞工應給予特別休假...", "2024-01-17")],
            mock_db
        )

    assert result.skipped == 1
    assert result.updated == 0
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd backend && python -m pytest tests/test_indexer.py -v
```

- [ ] **Step 3: Create `backend/app/services/indexer.py`**

```python
from dataclasses import dataclass, field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.db.models import LawArticle
from app.services.fetcher import LawArticleData
from app.services.embedder import get_embedder

@dataclass
class IndexResult:
    inserted: int = 0
    updated: int = 0
    skipped: int = 0
    errors: list[str] = field(default_factory=list)

async def upsert_articles(
    articles: list[LawArticleData],
    db: AsyncSession,
) -> IndexResult:
    result = IndexResult()
    embedder = get_embedder()

    # Load all existing articles into a dict keyed by article_number
    stmt = select(LawArticle).where(LawArticle.is_active == True)
    existing = {a.article_number: a for a in (await db.execute(stmt)).scalars().all()}

    incoming_numbers = {a.article_number for a in articles}

    # Mark obsolete articles as inactive
    for number, article in existing.items():
        if number not in incoming_numbers:
            article.is_active = False

    for article_data in articles:
        existing_article = existing.get(article_data.article_number)

        if existing_article and existing_article.content == article_data.content:
            result.skipped += 1
            continue

        embedding = embedder.get_text_embedding(article_data.content)

        if existing_article:
            existing_article.content = article_data.content
            existing_article.embedding = embedding
            existing_article.version = article_data.version
            result.updated += 1
        else:
            new_article = LawArticle(
                article_number=article_data.article_number,
                content=article_data.content,
                embedding=embedding,
                version=article_data.version,
                is_active=True,
            )
            db.add(new_article)
            result.inserted += 1

    await db.commit()
    return result
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd backend && python -m pytest tests/test_indexer.py -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/indexer.py backend/tests/test_indexer.py
git commit -m "feat: law article upsert indexer"
```

---

## Task 6: RAG Query Engine

**Files:**
- Create: `backend/app/services/rag.py`
- Create: `backend/tests/test_rag.py`

The RAG engine embeds a user question, retrieves top-5 law articles from pgvector, checks similarity threshold, then calls Claude to generate a response.

- [ ] **Step 1: Write failing tests**

Create `backend/tests/test_rag.py`:

```python
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from app.services.rag import query_law, QueryResult

@pytest.mark.asyncio
async def test_out_of_scope_question_returns_rejection(mock_embedder):
    """Questions with max similarity < 0.5 should be rejected without calling Claude."""
    mock_db = AsyncMock()
    # Simulate pgvector returning very low similarity scores
    mock_db.execute.return_value.all.return_value = []

    with patch("app.services.rag.get_embedder", return_value=mock_embedder), \
         patch("app.services.rag._search_articles", return_value=[]):
        result = await query_law("我想跟你聊感情", mock_db)

    assert result.is_out_of_scope is True
    assert result.answer is None

@pytest.mark.asyncio
async def test_valid_question_returns_answer(mock_embedder):
    """Valid question should call Claude and return an answer with citations."""
    mock_article = MagicMock()
    mock_article.article_number = "38"
    mock_article.content = "勞工應給予特別休假..."
    mock_article.similarity = 0.92

    mock_claude_response = MagicMock()
    mock_claude_response.content[0].text = "員工滿一年可享有7天特休。"

    with patch("app.services.rag.get_embedder", return_value=mock_embedder), \
         patch("app.services.rag._search_articles", return_value=[mock_article]), \
         patch("app.services.rag._call_claude", return_value="員工滿一年可享有7天特休。"):
        result = await query_law("員工到職一年有幾天特休？", mock_db := AsyncMock())

    assert result.is_out_of_scope is False
    assert "特休" in result.answer
    assert len(result.cited_articles) == 1
    assert result.cited_articles[0]["article_number"] == "38"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd backend && python -m pytest tests/test_rag.py -v
```

- [ ] **Step 3: Create `backend/app/services/rag.py`**

```python
from dataclasses import dataclass, field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from anthropic import Anthropic
from app.services.embedder import get_embedder
from app.config import settings

SIMILARITY_REJECT_THRESHOLD = 0.5
SIMILARITY_WARN_THRESHOLD = 0.75
TOP_K = 5

SYSTEM_PROMPT = """你是一位專業的台灣勞基法助理，服務對象為企業 HR。
請只根據以下提供的法條內容回答問題，不得自行推論或引用條文以外的資訊。
如果提供的法條不足以回答問題，請明確說明「現行法條無明確規定，建議諮詢勞工局」。
回答請使用繁體中文，語氣專業清晰。"""

@dataclass
class CitedArticle:
    article_number: str
    title: str | None
    similarity: float

@dataclass
class QueryResult:
    is_out_of_scope: bool
    answer: str | None
    warning: str | None
    cited_articles: list[dict]

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
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd backend && python -m pytest tests/test_rag.py -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/rag.py backend/tests/test_rag.py
git commit -m "feat: LlamaIndex RAG query engine with similarity threshold"
```

---

## Task 7: FastAPI App + All API Endpoints

**Files:**
- Create: `backend/app/main.py`
- Create: `backend/app/routers/query.py`
- Create: `backend/app/routers/sessions.py`
- Create: `backend/app/routers/articles.py`
- Create: `backend/tests/test_api.py`

- [ ] **Step 1: Write failing API tests**

Create `backend/tests/test_api.py`:

```python
import pytest
from httpx import AsyncClient, ASGITransport
from unittest.mock import patch, AsyncMock
from app.main import app
from app.services.rag import QueryResult

@pytest.mark.asyncio
async def test_query_endpoint_returns_answer():
    mock_result = QueryResult(
        is_out_of_scope=False,
        answer="員工滿一年可享有7天特休。",
        warning=None,
        cited_articles=[{"article_number": "38", "title": None, "similarity": 0.92}],
    )
    with patch("app.routers.query.query_law", return_value=mock_result), \
         patch("app.routers.query.get_db", return_value=AsyncMock()):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post("/api/query", json={"question": "員工到職一年有幾天特休？"})

    assert response.status_code == 200
    data = response.json()
    assert data["answer"] == "員工滿一年可享有7天特休。"
    assert len(data["cited_articles"]) == 1

@pytest.mark.asyncio
async def test_query_endpoint_rejects_long_input():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/api/query", json={"question": "a" * 501})
    assert response.status_code == 400

@pytest.mark.asyncio
async def test_query_endpoint_returns_out_of_scope():
    mock_result = QueryResult(is_out_of_scope=True, answer=None, warning=None, cited_articles=[])
    with patch("app.routers.query.query_law", return_value=mock_result), \
         patch("app.routers.query.get_db", return_value=AsyncMock()):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post("/api/query", json={"question": "我想聊感情"})
    assert response.status_code == 200
    assert response.json()["is_out_of_scope"] is True

@pytest.mark.asyncio
async def test_law_status_endpoint():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/law/status")
    assert response.status_code == 200
    assert "last_updated" in response.json()
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd backend && python -m pytest tests/test_api.py -v
```

- [ ] **Step 3: Create `backend/app/routers/query.py`**

```python
import uuid
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, insert
from app.db.database import get_db
from app.db.models import Session, QueryHistory
from app.services.rag import query_law

router = APIRouter()

class QueryRequest(BaseModel):
    question: str
    session_id: str | None = None

@router.post("/query")
async def handle_query(request: QueryRequest, db: AsyncSession = Depends(get_db)):
    if len(request.question) > 500:
        raise HTTPException(status_code=400, detail="問題長度不得超過 500 字")

    # Get or create session
    if request.session_id:
        session_id = uuid.UUID(request.session_id)
    else:
        title = request.question[:20]
        session = Session(title=title)
        db.add(session)
        await db.flush()
        session_id = session.id

    result = await query_law(request.question, db)

    # Save to history
    history = QueryHistory(
        session_id=session_id,
        question=request.question,
        answer=result.answer,
        cited_articles=result.cited_articles,
        max_similarity_score=result.cited_articles[0]["similarity"] if result.cited_articles else None,
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

- [ ] **Step 4: Create `backend/app/routers/sessions.py`**

```python
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.db.database import get_db
from app.db.models import Session, QueryHistory

router = APIRouter()

@router.get("/sessions")
async def list_sessions(db: AsyncSession = Depends(get_db)):
    stmt = select(Session).order_by(Session.created_at.desc()).limit(50)
    sessions = (await db.execute(stmt)).scalars().all()
    return [{"id": str(s.id), "title": s.title, "created_at": s.created_at} for s in sessions]

@router.get("/sessions/{session_id}/history")
async def get_session_history(session_id: str, db: AsyncSession = Depends(get_db)):
    stmt = select(QueryHistory).where(
        QueryHistory.session_id == session_id
    ).order_by(QueryHistory.created_at.asc())
    history = (await db.execute(stmt)).scalars().all()
    return [
        {
            "id": h.id,
            "question": h.question,
            "answer": h.answer,
            "cited_articles": h.cited_articles,
            "max_similarity_score": h.max_similarity_score,
            "created_at": h.created_at,
        }
        for h in history
    ]
```

- [ ] **Step 5: Create `backend/app/routers/articles.py`**

```python
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.db.database import get_db
from app.db.models import LawArticle, LawUpdateLog

router = APIRouter()

@router.get("/articles/{article_number}")
async def get_article(article_number: str, db: AsyncSession = Depends(get_db)):
    stmt = select(LawArticle).where(
        LawArticle.article_number == article_number,
        LawArticle.is_active == True,
    )
    article = (await db.execute(stmt)).scalar_one_or_none()
    if not article:
        raise HTTPException(status_code=404, detail="法條不存在")
    return {
        "article_number": article.article_number,
        "title": article.title,
        "content": article.content,
        "last_updated": article.last_updated,
        "version": article.version,
    }

@router.get("/law/status")
async def law_status(db: AsyncSession = Depends(get_db)):
    stmt = select(LawUpdateLog).order_by(LawUpdateLog.updated_at.desc()).limit(1)
    log = (await db.execute(stmt)).scalar_one_or_none()
    count_stmt = select(func.count()).select_from(LawArticle).where(LawArticle.is_active == True)
    total = (await db.execute(count_stmt)).scalar()
    return {
        "last_updated": log.updated_at if log else None,
        "status": log.status if log else "never_run",
        "total_active_articles": total,
    }
```

- [ ] **Step 6: Create `backend/app/main.py`**

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routers import query, sessions, articles

@asynccontextmanager
async def lifespan(app: FastAPI):
    yield  # scheduler starts here in Task 8

app = FastAPI(title="勞基法 RAG API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(query.router, prefix="/api")
app.include_router(sessions.router, prefix="/api")
app.include_router(articles.router, prefix="/api")
```

- [ ] **Step 7: Run all tests**

```bash
cd backend && python -m pytest tests/ -v
```

Expected: All PASS

- [ ] **Step 8: Commit**

```bash
git add backend/app/main.py backend/app/routers/ backend/tests/test_api.py
git commit -m "feat: FastAPI app with all 5 API endpoints"
```

---

## Task 8: Weekly Update Scheduler

**Files:**
- Create: `backend/app/services/scheduler.py`
- Modify: `backend/app/main.py` (lifespan hook)

- [ ] **Step 1: Create `backend/app/services/scheduler.py`**

```python
import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.database import AsyncSessionLocal
from app.db.models import LawUpdateLog
from app.services.fetcher import fetch_labor_law_articles
from app.services.indexer import upsert_articles

logger = logging.getLogger(__name__)
scheduler = AsyncIOScheduler()

async def run_law_update():
    logger.info("Starting weekly law update...")
    async with AsyncSessionLocal() as db:
        try:
            articles = await fetch_labor_law_articles()
            result = await upsert_articles(articles, db)
            log = LawUpdateLog(
                articles_changed=result.inserted + result.updated,
                status="success",
            )
            logger.info(f"Law update complete: +{result.inserted} ~{result.updated} skip{result.skipped}")
        except Exception as e:
            log = LawUpdateLog(status="failed", error_message=str(e))
            logger.error(f"Law update failed: {e}")
        db.add(log)
        await db.commit()

def start_scheduler():
    scheduler.add_job(run_law_update, "cron", day_of_week="mon", hour=2, minute=0)
    scheduler.start()
    logger.info("Scheduler started — law update runs every Monday at 02:00")
```

- [ ] **Step 2: Wire scheduler into `backend/app/main.py` lifespan**

Replace the `lifespan` function:

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    from app.services.scheduler import start_scheduler
    start_scheduler()
    yield
    from app.services.scheduler import scheduler
    scheduler.shutdown()
```

- [ ] **Step 3: Manual trigger endpoint (for initial data load)**

Add to `backend/app/routers/articles.py`:

```python
@router.post("/law/trigger-update")
async def trigger_update():
    """Manually trigger a law update — use this once to seed initial data."""
    from app.services.scheduler import run_law_update
    import asyncio
    asyncio.create_task(run_law_update())
    return {"message": "法條更新已觸發，請稍後查詢 /api/law/status 確認進度"}
```

- [ ] **Step 4: Start containers and trigger initial data load**

```bash
docker compose up --build -d
# Wait for backend to be healthy
curl -X POST http://localhost:8000/api/law/trigger-update
# Check status
curl http://localhost:8000/api/law/status
```

Expected: `{"last_updated": "...", "status": "success", "total_active_articles": 86}`

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/scheduler.py backend/app/main.py backend/app/routers/articles.py
git commit -m "feat: APScheduler weekly law update + manual trigger endpoint"
```

---

## Task 9: Next.js Frontend Setup + Types

**Files:**
- Create: `frontend/package.json`
- Create: `frontend/src/types/index.ts`
- Create: `frontend/src/lib/api.ts`
- Create: `frontend/src/app/layout.tsx`

- [ ] **Step 1: Initialize Next.js app**

```bash
cd frontend
npx create-next-app@14 . --typescript --tailwind --app --src-dir --import-alias "@/*"
```

> If prompted, accept all defaults. The `--src-dir` flag generates files under `src/app/` and `src/components/`, matching the file map.

- [ ] **Step 2: Create `frontend/src/types/index.ts`**

```typescript
export interface CitedArticle {
  article_number: string;
  title: string | null;
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
```

- [ ] **Step 3: Create `frontend/src/lib/api.ts`**

```typescript
const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export async function postQuery(question: string, sessionId?: string) {
  const res = await fetch(`${API_BASE}/api/query`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question, session_id: sessionId }),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function getSessions() {
  const res = await fetch(`${API_BASE}/api/sessions`);
  if (!res.ok) throw new Error("Failed to fetch sessions");
  return res.json();
}

export async function getSessionHistory(sessionId: string) {
  const res = await fetch(`${API_BASE}/api/sessions/${sessionId}/history`);
  if (!res.ok) throw new Error("Failed to fetch history");
  return res.json();
}

export async function getArticle(articleNumber: string) {
  const res = await fetch(`${API_BASE}/api/articles/${articleNumber}`);
  if (!res.ok) throw new Error("Article not found");
  return res.json();
}

export async function getLawStatus() {
  const res = await fetch(`${API_BASE}/api/law/status`);
  if (!res.ok) throw new Error("Failed to fetch law status");
  return res.json();
}
```

- [ ] **Step 4: Commit**

```bash
git add frontend/
git commit -m "feat: Next.js setup, TypeScript types, API client"
```

---

## Task 10: Frontend — Sidebar Component

**Files:**
- Create: `frontend/src/components/Sidebar.tsx`

- [ ] **Step 1: Create `frontend/src/components/Sidebar.tsx`**

```tsx
"use client";
import { useEffect, useState } from "react";
import { getSessions, getLawStatus } from "@/lib/api";
import { SessionSummary, LawStatus } from "@/types";

interface Props {
  activeSessionId: string | null;
  onSelectSession: (id: string) => void;
  onNewSession: () => void;
}

export default function Sidebar({ activeSessionId, onSelectSession, onNewSession }: Props) {
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [status, setStatus] = useState<LawStatus | null>(null);

  useEffect(() => {
    getSessions().then(setSessions).catch(console.error);
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
          <div className={`text-[10px] mt-1 ${status.status === "success" ? "text-green-500" : "text-yellow-500"}`}>
            {status.status === "success" ? "✓ 最新版本" : "⚠ 更新異常"}
          </div>
        </div>
      )}
    </aside>
  );
}
```

- [ ] **Step 2: Verify it compiles**

```bash
cd frontend && npm run build 2>&1 | tail -20
```

Expected: No TypeScript errors for Sidebar.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/Sidebar.tsx
git commit -m "feat: Sidebar component with session list and law version status"
```

---

## Task 11: Frontend — Article Panel

**Files:**
- Create: `frontend/src/components/ArticlePanel.tsx`

- [ ] **Step 1: Create `frontend/src/components/ArticlePanel.tsx`**

```tsx
"use client";
import { useEffect, useState } from "react";
import { getArticle } from "@/lib/api";
import { LawArticle, CitedArticle } from "@/types";

interface Props {
  citedArticles: CitedArticle[];
}

export default function ArticlePanel({ citedArticles }: Props) {
  const [articles, setArticles] = useState<LawArticle[]>([]);
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set());

  useEffect(() => {
    if (citedArticles.length === 0) return;
    Promise.all(citedArticles.map((c) => getArticle(c.article_number)))
      .then(setArticles)
      .catch(console.error);
    setCollapsed(new Set(citedArticles.slice(1).map((c) => c.article_number)));
  }, [citedArticles]);

  if (articles.length === 0) {
    return (
      <aside className="w-60 bg-slate-900 p-3 text-xs text-slate-600 flex items-center justify-center shrink-0">
        引用法條將顯示於此
      </aside>
    );
  }

  return (
    <aside className="w-60 bg-slate-900 flex flex-col p-3 gap-2 overflow-y-auto shrink-0">
      <span className="text-blue-400 font-bold text-xs tracking-wide uppercase">法條原文</span>
      {articles.map((article) => {
        const isCollapsed = collapsed.has(article.article_number);
        return (
          <div key={article.article_number} className="bg-slate-800 rounded p-3">
            <button
              className="w-full text-left"
              onClick={() =>
                setCollapsed((prev) => {
                  const next = new Set(prev);
                  isCollapsed ? next.delete(article.article_number) : next.add(article.article_number);
                  return next;
                })
              }
            >
              <div className="text-green-400 font-bold text-xs mb-1">
                第 {article.article_number} 條{article.title ? `（${article.title}）` : ""}
              </div>
              <div className="text-slate-500 text-[10px]">{isCollapsed ? "展開原文 ▼" : "收合 ▲"}</div>
            </button>
            {!isCollapsed && (
              <p className="text-slate-400 text-[11px] leading-relaxed mt-2 whitespace-pre-wrap">
                {article.content}
              </p>
            )}
            {article.version && (
              <div className="text-slate-600 text-[10px] mt-2">修正日期：{article.version}</div>
            )}
          </div>
        );
      })}
    </aside>
  );
}
```

- [ ] **Step 2: Verify it compiles**

```bash
cd frontend && npm run build 2>&1 | tail -20
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/ArticlePanel.tsx
git commit -m "feat: ArticlePanel component with collapsible law articles"
```

---

## Task 12: Frontend — Chat Panel + Main Page

**Files:**
- Create: `frontend/src/components/ChatPanel.tsx`
- Modify: `frontend/src/app/page.tsx`

- [ ] **Step 1: Create `frontend/src/components/ChatPanel.tsx`**

```tsx
"use client";
import { useState, useRef, useEffect } from "react";
import { ChatMessage, CitedArticle } from "@/types";
import { postQuery } from "@/lib/api";

interface Props {
  sessionId: string | null;
  messages: ChatMessage[];
  onNewMessage: (userMsg: ChatMessage, assistantMsg: ChatMessage, sessionId: string) => void;
  onArticlesChange: (articles: CitedArticle[]) => void;
}

export default function ChatPanel({ sessionId, messages, onNewMessage, onArticlesChange }: Props) {
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
      const data = await postQuery(question, sessionId ?? undefined);
      const assistantMsg: ChatMessage = {
        role: "assistant",
        content: data.is_out_of_scope
          ? "此問題超出勞基法範圍，無法提供答案。"
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
            輸入勞基法相關問題開始查詢
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
              <p className="whitespace-pre-wrap">{msg.content}</p>
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
                      key={c.article_number}
                      className="bg-blue-950 border border-blue-700 text-blue-300 px-2 py-1 rounded-full text-xs"
                    >
                      §{c.article_number}
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

      <div className="p-3 bg-slate-900 border-t border-slate-700 flex gap-2">
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && !e.shiftKey && handleSubmit()}
          placeholder="輸入您的勞基法問題..."
          className="flex-1 bg-slate-800 border border-slate-700 text-slate-200 placeholder-slate-500 rounded-lg px-4 py-2.5 text-sm outline-none focus:border-blue-500"
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

- [ ] **Step 2: Update `frontend/src/app/page.tsx`**

```tsx
"use client";
import { useState, useCallback } from "react";
import Sidebar from "@/components/Sidebar";
import ChatPanel from "@/components/ChatPanel";
import ArticlePanel from "@/components/ArticlePanel";
import { ChatMessage, CitedArticle } from "@/types";

export default function Home() {
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [citedArticles, setCitedArticles] = useState<CitedArticle[]>([]);

  const handleSelectSession = useCallback(async (sessionId: string) => {
    const { getSessionHistory } = await import("@/lib/api");
    setActiveSessionId(sessionId);
    setCitedArticles([]);
    const history = await getSessionHistory(sessionId);
    const msgs: ChatMessage[] = history.flatMap((h: any) => [
      { role: "user" as const, content: h.question },
      {
        role: "assistant" as const,
        content: h.answer ?? "此問題超出勞基法範圍。",
        cited_articles: h.cited_articles,
      },
    ]);
    setMessages(msgs);
    const lastCited = history.findLast((h: any) => h.cited_articles?.length)?.cited_articles;
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
      if (!activeSessionId) setActiveSessionId(sessionId);
    },
    [activeSessionId]
  );

  return (
    <main className="flex h-screen bg-slate-800 text-white overflow-hidden">
      <Sidebar
        activeSessionId={activeSessionId}
        onSelectSession={handleSelectSession}
        onNewSession={handleNewSession}
      />
      <ChatPanel
        sessionId={activeSessionId}
        messages={messages}
        onNewMessage={handleNewMessage}
        onArticlesChange={setCitedArticles}
      />
      <ArticlePanel citedArticles={citedArticles} />
    </main>
  );
}
```

- [ ] **Step 3: Update `frontend/src/app/layout.tsx`**

```tsx
import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "勞基法查詢助手",
  description: "HR 勞基法 RAG 查詢系統",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="zh-TW">
      <body className="bg-slate-900">{children}</body>
    </html>
  );
}
```

- [ ] **Step 4: Build to verify no TypeScript errors**

```bash
cd frontend && npm run build
```

Expected: Build succeeds with no type errors.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/
git commit -m "feat: ChatPanel and main page — full 3-column UI"
```

---

## Task 13: End-to-End Smoke Test

Verify the full stack works together.

- [ ] **Step 1: Start the full stack**

```bash
docker compose up --build
```

Wait for all services to be healthy. Backend logs should show "Scheduler started".

- [ ] **Step 2: Seed initial law data**

```bash
curl -X POST http://localhost:8000/api/law/trigger-update
# Wait ~1-2 minutes, then check:
curl http://localhost:8000/api/law/status
```

Expected: `"status": "success"`, `"total_active_articles"` > 0

- [ ] **Step 3: Test a query via API**

```bash
curl -X POST http://localhost:8000/api/query \
  -H "Content-Type: application/json" \
  -d '{"question": "員工到職滿一年有幾天特休？"}'
```

Expected: JSON with `answer` containing 特休 content and `cited_articles` with `§38`

- [ ] **Step 4: Test out-of-scope rejection**

```bash
curl -X POST http://localhost:8000/api/query \
  -H "Content-Type: application/json" \
  -d '{"question": "我想跟你聊感情"}'
```

Expected: `"is_out_of_scope": true`

- [ ] **Step 5: Open frontend**

Navigate to `http://localhost:3000` in browser.
- Type a question in the input box
- Verify AI answer appears in middle panel
- Verify cited article appears in right panel
- Verify session is saved in left sidebar

- [ ] **Step 6: Run all backend tests one final time**

```bash
cd backend && python -m pytest tests/ -v --tb=short
```

Expected: All PASS

- [ ] **Step 7: Final commit**

```bash
git add .
git commit -m "feat: complete labor law RAG system — MVP ready"
```

---

## Notes for Implementation

- **API 確認：** Task 4 uses `https://law.moj.gov.tw/api/CH/Laws/C0030001/AllArticles`. Verify the exact endpoint and response structure at `https://law.moj.gov.tw/api/swagger/index.html` before implementing — the pcode and response shape must be confirmed against the live API docs.
- **bge-m3 首次下載：** Task 3 Step 5 will download ~2GB on first run inside Docker. The `hf_cache` volume ensures this only happens once.
- **pgvector-sqlalchemy：** The `Vector` column type requires `pip install pgvector`. It is included in `requirements.txt`.
- **Similarity scores:** pgvector returns cosine distance (`<=>`) not similarity. The query in `rag.py` converts: `similarity = 1 - distance`. Scores near 1.0 = most similar.
