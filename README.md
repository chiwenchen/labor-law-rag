# 勞動法令 RAG 查詢系統

以檢索增強生成（RAG）為核心的台灣勞動法令問答平台，支援 12 部勞動法規、混合式語意搜尋、角色導向回覆，以及即時串流輸出。

---

## 目錄

- [功能特色](#功能特色)
- [系統架構](#系統架構)
- [技術棧](#技術棧)
- [RAG 流程說明](#rag-流程說明)
- [快速開始](#快速開始)
- [環境變數設定](#環境變數設定)
- [API 端點](#api-端點)
- [支援法規](#支援法規)
- [測試](#測試)
- [專案結構](#專案結構)

---

## 功能特色

- **混合式語意搜尋**：結合 pgvector 向量搜尋與 PostgreSQL BM25 全文檢索，透過 Reciprocal Rank Fusion (RRF) 排序融合
- **HyDE（假設文件嵌入）**：先生成假設性法條文字再進行語意搜尋，提升檢索準確率
- **即時串流回覆**：逐 token 串流輸出，附帶分析步驟提示（分析問題 → 搜尋相關法條 → 撰寫回覆）
- **角色導向回覆**：人資（HR）角色聚焦合規義務；員工（Employee）角色聚焦個人權益
- **OTP 無密碼登入**：透過 Email 寄送一次性驗證碼，httpOnly cookie 管理 Session
- **多部法規切換**：前端可依需求篩選特定法規範圍進行查詢
- **自動定期更新**：每週一凌晨 2 點自動從政府開放資料來源同步最新法條
- **引用條文展示**：回覆旁側欄顯示所有引用法條原文

---

## 系統架構

```
┌─────────────────────────────────────────────────────────┐
│                       使用者瀏覽器                        │
│                  Next.js 14 前端 (port 3000)             │
│   ChatPanel │ Sidebar │ ArticlePanel │ LawScopeSelector  │
└──────────────────────┬──────────────────────────────────┘
                       │ HTTP / SSE Streaming
┌──────────────────────▼──────────────────────────────────┐
│                 FastAPI 後端 (port 8000)                  │
│                                                          │
│   Auth Router │ Query Router │ Sessions │ Laws │ Articles│
│                                                          │
│  ┌─────────────────────────────────────────────────┐    │
│  │                  RAG 引擎                         │    │
│  │  問題改寫 → HyDE → 混合搜尋 → Claude 生成          │    │
│  └─────────────────────────────────────────────────┘    │
│                                                          │
│   Embedder (BAAI/bge-m3)   │   Scheduler (APScheduler)  │
└──────────────────────┬──────────────────────────────────┘
                       │ asyncpg
┌──────────────────────▼──────────────────────────────────┐
│              PostgreSQL 16 + pgvector (port 5432)         │
│   law_articles │ users │ sessions │ query_history         │
│   supported_laws │ law_update_logs                        │
└─────────────────────────────────────────────────────────┘
```

---

## 技術棧

### 後端
| 項目 | 技術 |
|------|------|
| 框架 | FastAPI 0.111 + Uvicorn |
| 資料庫 | PostgreSQL 16 + pgvector |
| ORM | SQLAlchemy 2.0 (async) + asyncpg |
| 嵌入模型 | BAAI/bge-m3（1024 維向量） |
| 生成模型 | Anthropic Claude Sonnet 4.6（生成） / Haiku（HyDE & 問題改寫） |
| 認證 | OTP via Resend + httpOnly Cookie Session |
| 排程 | APScheduler |
| 速率限制 | SlowAPI |
| 測試 | pytest + pytest-asyncio |

### 前端
| 項目 | 技術 |
|------|------|
| 框架 | Next.js 14.2（App Router） |
| 語言 | TypeScript 5 |
| 樣式 | Tailwind CSS 3.4 + @tailwindcss/typography |
| Markdown | react-markdown + remark-gfm |
| 測試 | Playwright E2E |

### 基礎設施
- Docker + Docker Compose（三服務：db / backend / frontend）
- Hugging Face 模型快取持久化 volume

---

## RAG 流程說明

### 資料入庫（Ingestion）

```
GitHub (kong0107/mojLawSplitJSON)
    ↓  fetcher.py：HTTP 請求，解析 JSON
    ↓  indexer.py：生成 BAAI/bge-m3 嵌入向量 + tsvector 全文索引
    ↓
PostgreSQL law_articles 資料表
    • embedding  (pgvector, 1024 維)
    • content    (法條全文)
    • tsvector   (BM25 全文搜尋)
    • law_id, article_number（唯一鍵）
```

觸發時機：
- 每週一凌晨 2 點自動排程
- 手動呼叫 `POST /api/laws/{law_id}/update`

### 查詢流程（Query）

```
使用者提問
    ↓ 1. 問題改寫（Claude Haiku）：將追問語境化
    ↓ 2. HyDE（Claude Haiku）：生成假設性法條文字
    ↓ 3. 嵌入向量化（bge-m3）：問題 + 假設文件
    ↓ 4. 混合搜尋
         ├─ 向量搜尋：pgvector cosine 相似度
         ├─ BM25 搜尋：PostgreSQL tsvector
         └─ RRF 融合排序 → Top 10 法條
    ↓ 5. 相似度閾值過濾
         • < 0.45：拒絕回覆（問題與法條無關）
         • < 0.72：附加免責聲明
    ↓ 6. Claude Sonnet 4.6 生成
         • 角色導向 system prompt（hr / employee）
         • 最多引用 10 條相關法條
         • 對話歷史（最近 3 輪）
         • 串流輸出 or 完整回覆
    ↓
QueryHistory 記錄問題、回答、引用條文、相似度分數
```

---

## 快速開始

### 前置需求

- Docker & Docker Compose
- Anthropic API Key
- Resend API Key（Email OTP 服務）

### 1. 複製專案

```bash
git clone <repository-url>
cd labor-law-rag
```

### 2. 設定環境變數

```bash
cp .env.example .env
# 編輯 .env，填入必要的 API Keys 與 DB 設定
```

### 3. 啟動所有服務

```bash
docker-compose up --build
```

服務啟動後：
- 前端：http://localhost:3000
- 後端 API：http://localhost:8000
- API 文件（Swagger）：http://localhost:8000/docs

### 4. 初始化法條資料

登入後，前往法規管理頁面手動觸發首次資料同步，或呼叫 API：

```bash
curl -X POST http://localhost:8000/api/laws/{law_id}/update \
  -H "Cookie: session=<your-session-token>"
```

### 本機開發（不使用 Docker）

**後端：**
```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

**前端：**
```bash
cd frontend
npm install
npm run dev
```

---

## 環境變數設定

複製 `.env.example` 為 `.env` 並填入以下設定：

| 變數名稱 | 說明 | 必填 |
|---------|------|------|
| `ANTHROPIC_API_KEY` | Anthropic API 金鑰 | ✅ |
| `RESEND_API_KEY` | Resend Email 服務金鑰 | ✅ |
| `EMAIL_FROM` | 寄件人 Email 地址 | ✅ |
| `DATABASE_URL` | PostgreSQL 連線字串 | ✅ |
| `CORS_ORIGINS` | 允許的前端來源（逗號分隔） | ✅ |
| `SECRET_KEY` | Session 加密金鑰 | ✅ |

---

## API 端點

### 認證

| 方法 | 路徑 | 說明 |
|------|------|------|
| POST | `/api/auth/send-otp` | 發送 OTP 至 Email |
| POST | `/api/auth/verify-otp` | 驗證 OTP，建立 Session |
| GET | `/api/auth/me` | 取得目前登入使用者資訊 |
| POST | `/api/auth/logout` | 登出，清除 Session |

### 查詢

| 方法 | 路徑 | 說明 |
|------|------|------|
| POST | `/api/query` | 同步 RAG 查詢 |
| POST | `/api/query/stream` | 串流 RAG 查詢（SSE） |

**Request Body（查詢）：**
```json
{
  "question": "加班費如何計算？",
  "session_id": "optional-session-uuid",
  "law_ids": ["labor-standards-act"],
  "role": "employee"
}
```

### 對話歷史

| 方法 | 路徑 | 說明 |
|------|------|------|
| GET | `/api/sessions` | 列出所有對話 Session |
| GET | `/api/sessions/{id}` | 取得特定 Session 的對話記錄 |

### 法規管理

| 方法 | 路徑 | 說明 |
|------|------|------|
| GET | `/api/laws` | 列出所有支援的法規及更新狀態 |
| POST | `/api/laws/{law_id}/update` | 手動觸發特定法規資料更新 |

---

## 支援法規

本系統支援以下 12 部台灣勞動相關法規：

1. 勞動基準法
2. 勞動基準法施行細則
3. 勞工保險條例
4. 就業保險法
5. 職業安全衛生法
6. 勞工退休金條例
7. 性別平等工作法
8. 就業服務法
9. 勞資爭議處理法
10. 工會法
11. 勞動契約法
12. 大量解僱勞工保護法

法條資料來源：[kong0107/mojLawSplitJSON](https://github.com/kong0107/mojLawSplitJSON)（政府開放資料）

---

## 測試

### 後端單元測試與整合測試

```bash
cd backend

# 執行所有測試
pytest

# 僅執行單元測試
pytest -m unit

# 僅執行整合測試
pytest -m integration

# 含覆蓋率報告
pytest --cov=app --cov-report=html
```

### 前端 E2E 測試（Playwright）

```bash
cd frontend
npx playwright test

# 互動模式
npx playwright test --ui
```

### 前端 Lint

```bash
cd frontend
npm run lint
```

---

## 專案結構

```
labor-law-rag/
├── backend/
│   ├── app/
│   │   ├── auth/              # OTP 認證、Session 管理
│   │   ├── db/
│   │   │   ├── models.py      # SQLAlchemy ORM 模型
│   │   │   ├── database.py    # 非同步 DB 連線
│   │   │   └── migrations/    # SQL migration 腳本
│   │   ├── routers/           # API 路由（auth, query, sessions, laws）
│   │   ├── services/
│   │   │   ├── rag.py         # RAG 核心引擎
│   │   │   ├── embedder.py    # bge-m3 嵌入模型
│   │   │   ├── indexer.py     # 法條入庫邏輯
│   │   │   ├── fetcher.py     # 法條資料抓取
│   │   │   ├── law_registry.py # 12 部法規映射表
│   │   │   └── scheduler.py   # 定期更新排程
│   │   ├── main.py            # FastAPI 應用程式進入點
│   │   ├── config.py          # 環境設定（Pydantic Settings）
│   │   └── limiter.py         # 速率限制設定
│   ├── tests/                 # pytest 測試套件
│   ├── Dockerfile
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── app/               # Next.js App Router 頁面
│   │   ├── components/        # React 元件
│   │   │   ├── ChatPanel.tsx  # 對話介面（串流輸出）
│   │   │   ├── Sidebar.tsx    # Session 列表、法規篩選
│   │   │   └── ArticlePanel.tsx # 引用法條側欄
│   │   ├── lib/               # API 客戶端、認證工具
│   │   └── types/             # TypeScript 型別定義
│   ├── e2e/                   # Playwright E2E 測試
│   ├── Dockerfile
│   └── package.json
├── docker-compose.yml
└── .env.example
```

---

## 注意事項

- **OTP 儲存**：目前使用記憶體儲存（重啟後清空），正式環境建議改用 Redis
- **嵌入模型首次啟動**：BAAI/bge-m3 模型約 2GB，首次下載需要時間；已設定 Docker volume 快取避免重複下載
- **速率限制**：查詢 API 預設 10 次/分鐘；法規列表 30 次/分鐘
- **相似度閾值**：低於 0.45 的問題（非勞動法相關）將被拒絕回覆，0.45–0.72 區間附加免責聲明
