# Multi-Law Support & Law Management Page Design

> **For agentic workers:** Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this spec.

**Goal:** Expand the RAG system from single-law (勞動基準法) to 11 HR-related laws, with a law scope selector in the chat UI and a dedicated law management page.

**Architecture:** Multi-law backend with per-law fetch/embed pipeline; frontend adds collapsible law scope filter in Sidebar and a new `/laws` table-style page reusing the existing Sidebar.

**Tech Stack:** FastAPI + SQLAlchemy asyncpg + pgvector (backend), Next.js 14 App Router + Tailwind (frontend), kong0107/mojLawSplitJSON as data source.

---

## Supported Laws

| 法規名稱 | mojLawSplitJSON 代碼 |
|---------|---------------------|
| 勞動基準法 | N0030001 |
| 勞工請假規則 | N0030002 |
| 大量解僱勞工保護法 | N0030003 |
| 勞資爭議處理法 | N0030014 |
| 性別平等工作法 | N0030015 |
| 勞工保險條例 | N0050001 |
| 勞工退休金條例 | N0060001 |
| 職業安全衛生法 | N0060002 |
| 勞工職業災害保險及保護法 | N0060003 |
| 就業保險法 | N0090001 |
| 就業服務法 | N0090003 |

> **Note:** Law codes must be verified against `https://raw.githubusercontent.com/kong0107/mojLawSplitJSON/gh-pages/FalVMingLing/{code}.json` before implementation. Codes are best-effort estimates; fetcher must log a warning and mark `last_status = 'failed'` if a code returns 404.

---

## Backend Changes

### 1. Database Schema

**`law_articles` table — add two columns:**
```sql
ALTER TABLE law_articles ADD COLUMN law_id VARCHAR(20) NOT NULL DEFAULT 'N0030001';
ALTER TABLE law_articles ADD COLUMN law_name VARCHAR(100) NOT NULL DEFAULT '勞動基準法';
```

Existing rows (勞動基準法) are covered by the defaults. Note: `law_articles.last_updated` is a per-article field (when that specific row was last written); `supported_laws.last_updated` (below) is a per-law-fetch field (when the last successful fetch completed for that law). These are distinct concepts.

**New `supported_laws` table:**
```sql
CREATE TABLE supported_laws (
  law_id        VARCHAR(20) PRIMARY KEY,
  law_name      VARCHAR(100) NOT NULL,
  article_count INTEGER NOT NULL DEFAULT 0,
  last_updated  TIMESTAMP,       -- when the last successful fetch completed
  last_status   VARCHAR(20) DEFAULT 'never_run'  -- 'success' | 'failed' | 'never_run'
);
```

**`law_update_logs` table — add `law_id` column:**
```sql
ALTER TABLE law_update_logs ADD COLUMN law_id VARCHAR(20) NOT NULL DEFAULT 'N0030001';
```

Existing rows default to 'N0030001'. All future writes to `law_update_logs` must include `law_id`. The table is NOT deprecated — it remains the per-run audit log; `supported_laws` is the current-state summary.

### 2. Startup Seeding (`app/main.py` lifespan)

On startup, seed `supported_laws` with all 11 laws using INSERT ... ON CONFLICT DO NOTHING. For 勞動基準法 specifically, if inserting for the first time, query the real article count from `law_articles` and use it instead of 0:

```python
# Pseudo-code for startup seeding
for law in LAW_REGISTRY:
    existing = await db.execute(select(SupportedLaw).where(SupportedLaw.law_id == law["law_id"]))
    if not existing.scalar():
        count = await db.scalar(
            select(func.count()).where(LawArticle.law_id == law["law_id"], LawArticle.is_active == True)
        )
        db.add(SupportedLaw(
            law_id=law["law_id"],
            law_name=law["law_name"],
            article_count=count or 0,
            last_status="success" if count else "never_run",
        ))
```

This ensures 勞動基準法 shows the correct article count (e.g. 98) immediately after migration, without requiring a manual re-index.

### 3. Law Registry (`app/services/law_registry.py`)

Single source of truth for all supported laws:

```python
LAW_REGISTRY = [
    {"law_id": "N0030001", "law_name": "勞動基準法"},
    {"law_id": "N0030002", "law_name": "勞工請假規則"},
    {"law_id": "N0030003", "law_name": "大量解僱勞工保護法"},
    {"law_id": "N0030014", "law_name": "勞資爭議處理法"},
    {"law_id": "N0030015", "law_name": "性別平等工作法"},
    {"law_id": "N0050001", "law_name": "勞工保險條例"},
    {"law_id": "N0060001", "law_name": "勞工退休金條例"},
    {"law_id": "N0060002", "law_name": "職業安全衛生法"},
    {"law_id": "N0060003", "law_name": "勞工職業災害保險及保護法"},
    {"law_id": "N0090001", "law_name": "就業保險法"},
    {"law_id": "N0090003", "law_name": "就業服務法"},
]
BASE_URL = "https://raw.githubusercontent.com/kong0107/mojLawSplitJSON/gh-pages/FalVMingLing/{law_id}.json"
```

### 4. Fetcher (`app/services/fetcher.py`)

Generalize from single-law to per-law fetch:

```python
async def fetch_law(law_id: str, law_name: str) -> list[dict]:
    """Fetch and parse articles for one law.
    Returns list of dicts: {article_number, title, content, version, law_id, law_name}
    Raises HTTPError if the law_id URL returns 404.
    """
```

Current `fetch_articles()` becomes a thin wrapper: `fetch_law("N0030001", "勞動基準法")`.

### 5. Indexer (`app/services/indexer.py`)

`update_articles(articles, law_id, law_name)` uses **upsert** strategy (same as current):
- INSERT new articles (identified by `law_id + article_number` composite key)
- UPDATE changed articles (content or title differs)
- Mark `is_active = False` for articles in DB that are no longer in the fetched list for that law

After successful indexing, update `supported_laws`:
```python
# Set article_count to actual active count for this law
count = SELECT COUNT(*) FROM law_articles WHERE law_id = :law_id AND is_active = true
UPDATE supported_laws SET article_count = count, last_updated = NOW(), last_status = 'success'
WHERE law_id = :law_id
```

On failure, set `last_status = 'failed'` without changing `article_count` or `last_updated`. Write to `law_update_logs` with `law_id` on both success and failure.

### 6. RAG (`app/services/rag.py`)

`query_law()` accepts optional `law_ids`:

```python
async def query_law(
    question: str,
    db: AsyncSession,
    law_ids: list[str] | None = None,
) -> QueryResult:
```

SQL filter (only added when `law_ids` is a non-empty list):
```sql
AND law_id = ANY(:law_ids)
```

`None` or empty list = no filter = search all laws. The behaviour of `law_ids=[]` and `law_ids=None` is identical — both search all active articles regardless of law.

### 7. API Endpoints

**Existing — modified:**
```
POST /api/query
Body: { question: str, session_id?: str, law_ids?: str[] }
```
`law_ids` is optional; absent, null, or empty array all mean "all laws".

**New — add as `app/routers/laws.py`:**

```
GET /api/laws
Response: [{ law_id, law_name, article_count, last_updated, last_status }]
# version field is intentionally omitted — version is per-article, not per-law
```

```
POST /api/laws/{law_id}/update
Response: { status: str, article_count: int, message: str }
```

**Synchronous long-poll:** This endpoint runs fetch + embed synchronously and returns when complete. Embedding 100–300 articles takes approximately 30–120 seconds. The frontend must use a long timeout (≥ 180 seconds) for this request. The response is returned only after the operation fully completes. A future async-job pattern is out of scope; document the expected duration in the API docstring so operators are aware.

---

## Frontend Changes

### 1. Types (`src/types/index.ts`)

```typescript
interface SupportedLaw {
  law_id: string;
  law_name: string;
  article_count: number;
  last_updated: string | null;
  last_status: 'success' | 'failed' | 'never_run';
}
```

Add `law_ids?: string[]` to the query request shape.

### 2. API Client (`src/lib/api.ts`)

```typescript
getLaws(): Promise<SupportedLaw[]>
updateLaw(lawId: string): Promise<{ status: string; article_count: number; message: string }>
// timeout: 180_000ms for updateLaw
```

Update `postQuery()` to accept and forward optional `law_ids`.

### 3. Sidebar (`src/components/Sidebar.tsx`)

Add collapsible law scope panel below the "新增查詢" button:

- Header row: "法規範圍 (全部)" or "法規範圍 (3 部)" + ▼/▶ arrow
- Expanded: full checkbox list of all 11 laws fetched from `GET /api/laws`
- "全選 / 取消全選" shortcut link
- **State rule:** `selectedLawIds` is an array of checked law_id strings.
  - All 11 checked (or all unchecked → auto-revert) → treat as `[]` when sending to backend
  - Partial selection → send exact array to backend
  - "If all unchecked, revert to all checked" is enforced in the toggle handler

```typescript
// New props added to Sidebar
selectedLawIds: string[]          // [] means all laws selected
onLawScopeChange: (ids: string[]) => void
```

### 4. Page (`src/app/page.tsx`)

Add `selectedLawIds` state (default `[]`). Pass to `Sidebar` and `ChatPanel`. When `selectedLawIds` has length === 11 (all selected), treat it as `[]` before passing to `postQuery`.

### 5. ChatPanel (`src/components/ChatPanel.tsx`)

Receives `selectedLawIds: string[]`. Passes it to `postQuery()` as `law_ids` (omit the field entirely when the array is empty).

### 6. Laws Page (`src/app/laws/page.tsx`)

New route `/laws`. Uses the same full-page layout (`flex h-screen`).

**Left: Sidebar (adapted)**
- Session list is shown but clicking a session navigates to `/?session={id}` (a new query param that `page.tsx` reads to restore that session) — this is navigation, not in-page state selection
- Law scope panel is hidden (not relevant on the laws management page)
- "← 返回查詢" link at top navigates to `/`
- "📋 法規管理" link at bottom is in active/highlighted state

**Right: Main area (full width, no ArticlePanel)**

Table layout:
```
法規名稱 | 條文數 | 最後更新 | 狀態 | 操作
```

Status badges:
- `success` → green "✓ 最新"
- `failed` → red "✗ 更新失敗"
- `never_run` → orange "⚠ 未載入"

操作 column:
- `success` / `failed` → "更新" button (secondary style)
- `never_run` → "載入" button (primary blue)
- While a row is updating → spinner icon, button disabled, other rows unaffected

Update flow: button click → `POST /api/laws/{law_id}/update` (180s timeout) → disable button, show spinner → on response, refresh only that row's data → re-enable button. No full page reload.

### 7. Navigation

Add "📋 法規管理" link at the bottom of `Sidebar`. Visible on both `/` and `/laws`. Uses `next/link`; active state (blue highlight) when `pathname === '/laws'`.

---

## Error Handling

- Law code 404 from source: mark `last_status = 'failed'`, log to `law_update_logs`, continue with other laws in batch
- Embedding failure mid-law: rollback that law's in-flight changes, mark `last_status = 'failed'`, don't affect other laws
- Update endpoint timeout on frontend: show "更新逾時，請稍後再試" inline; backend continues and will complete (status visible on next page load)
- Update button shows error message inline on non-2xx response

---

## Out of Scope

- Async job pattern for long-running updates (synchronous long-poll is acceptable for now)
- Per-law update scheduling (all laws share the existing weekly scheduler)
- Law enable/disable toggle (all 11 are always active)
- Search filtering on the laws page
- User authentication
- `/?session={id}` deep-link implementation (session restoration from URL) — the `/laws` page links to `/` without session param for now; session restoration is a separate feature
