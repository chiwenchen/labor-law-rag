# 勞基法 RAG 查詢系統 — 設計文件

**日期：** 2026-03-22
**狀態：** 已確認

---

## 概述

供 HR 使用的勞基法查詢工具。使用者以自然語言提問，系統從向量資料庫檢索最相關的法條，透過 Claude 生成摘要回覆，並列出引用的法條原文。

**使用情境：**
- 現階段：個人 / 少數人使用（本地 Docker Compose 部署）
- 最終目標：公司內部多人 HR 工具（AWS 部署）

---

## 系統架構

### 容器組成（Docker Compose）

| 容器 | 技術 | 職責 |
|------|------|------|
| `frontend` | Next.js + Tailwind CSS | 使用者介面 |
| `backend` | Python FastAPI | API、RAG 邏輯、排程 |
| `db` | PostgreSQL + pgvector | 法條向量儲存、查詢紀錄 |

> 排程器（APScheduler）內建在 `backend` 服務，不需要額外容器。

### 外部依賴

| 服務 | 用途 |
|------|------|
| Claude API（claude-sonnet-4-6） | 生成自然語言回覆 |
| OpenAI Embeddings API（text-embedding-ada-002） | 文字向量化（1536 維） |
| 全國法規資料庫 API（laws.moj.gov.tw） | 抓取最新勞基法條文 |

> **Embedding 模型選擇說明：** LlamaIndex 的 pgvector 整合對 OpenAI embedding 支援最完整，且 text-embedding-ada-002 輸出恰為 1536 維，成本低廉（每次查詢不到 $0.0001）。Claude API 不提供 embedding 端點，故兩者分工：OpenAI 負責向量化，Claude 負責生成回覆。

---

## 資料流

### 流程一：法條更新（每週排程）

```
APScheduler 每週觸發
    │
    ▼
呼叫全國法規資料庫 API
取得勞基法所有條文（條號、內文、修正日期）
    │
    ▼
與資料庫現有版本逐條比對
（比對鍵：article_number，UNIQUE 約束確保唯一）
    ├── 沒變動 → 跳過
    ├── 有修改 → 重新 Embedding，Upsert 向量與內容
    ├── 新條文 → Embedding，INSERT
    └── 已廢止（舊有但 API 未回傳）→ 標記 is_active = false（保留歷史，不刪除）
    │
    ▼
寫入 law_update_logs（更新時間、異動條數、狀態、錯誤訊息）
```

**錯誤重試策略：** 更新失敗時記錄錯誤訊息，保留舊版本供查詢使用，下次排程自動重試整批更新（勞基法條數少，整批重跑成本極低）。

### 流程二：使用者查詢

```
使用者輸入問題
    │
    ▼
[輸入驗證]
長度 > 500 字 → 拒絕，回傳 400
    │
    ▼
問題向量化（OpenAI text-embedding-ada-002）
    │
    ▼
pgvector 搜尋最相似的 5 條 is_active=true 法條
（回傳各條相似度分數 0~1）
    │
    ├── top-1 相似度 < 0.5 → 回覆「此問題超出勞基法範圍」，結束（不呼叫 Claude）
    ├── top-1 相似度 0.5~0.75 → 繼續，但標記需加警語
    │
    ▼
組成 Prompt（system / user role 嚴格隔離，透過 LlamaIndex API 傳入，不拼接字串）
  system: 你是勞基法助理，只能根據提供的條文回答。
          若條文中資訊不足，請明確說明「現行法條無明確規定」，不得自行推論。
  context: [5 條法條原文]
  user: [使用者問題]
    │
    ▼
呼叫 Claude API 生成回覆
    │
    ▼
組成回應：
  - AI 摘要文字
  - 若相似度 0.5~0.75：附加警語「相關性較低，建議查閱原文確認」
  - 引用法條列表（條號 + 相似度分數）
    │
    ▼
寫入 query_history（含 session_id）
    │
    ▼
回傳給前端
```

---

## 資料庫結構

### `sessions`（查詢會話）

| 欄位 | 型別 | 說明 |
|------|------|------|
| `id` | uuid PK | |
| `title` | varchar | 自動從第一個問題生成（前 20 字） |
| `created_at` | timestamp | |

### `law_articles`（法條本體）

| 欄位 | 型別 | 說明 |
|------|------|------|
| `id` | serial PK | |
| `article_number` | varchar **UNIQUE** | 條號，例如 "38" |
| `title` | varchar | 條文標題 |
| `content` | text | 條文內文 |
| `embedding` | vector(1536) | OpenAI text-embedding-ada-002 輸出 |
| `is_active` | boolean | false = 已廢止 |
| `last_updated` | timestamp | 條文最後修正日期 |
| `version` | varchar | 法規版本號 |

### `query_history`（查詢紀錄）

| 欄位 | 型別 | 說明 |
|------|------|------|
| `id` | serial PK | |
| `session_id` | uuid FK → sessions | 所屬會話 |
| `question` | text | 使用者問題 |
| `answer` | text | AI 回覆 |
| `cited_articles` | jsonb | 引用法條陣列（含條號、相似度） |
| `max_similarity_score` | float | top-1 相似度 |
| `created_at` | timestamp | |

### `law_update_logs`（更新紀錄）

| 欄位 | 型別 | 說明 |
|------|------|------|
| `id` | serial PK | |
| `updated_at` | timestamp | |
| `articles_changed` | int | 異動條數 |
| `status` | varchar | success / failed |
| `error_message` | text | 失敗時的錯誤訊息（nullable） |

---

## API 端點

### 查詢

| Method | Path | 說明 |
|--------|------|------|
| `POST` | `/api/query` | 送出問題，取得 AI 回覆 |
| `GET` | `/api/sessions` | 取得所有會話列表（左側欄） |
| `GET` | `/api/sessions/{id}/history` | 取得指定會話的問答紀錄 |

**POST /api/query 請求：**
```json
{ "session_id": "uuid（可選，空則建立新會話）", "question": "string" }
```

**POST /api/query 回應：**
```json
{
  "session_id": "uuid",
  "answer": "string",
  "warning": "string | null",
  "cited_articles": [
    { "article_number": "38", "title": "特別休假", "similarity": 0.94 }
  ]
}
```

### 法條

| Method | Path | 說明 |
|--------|------|------|
| `GET` | `/api/articles/{number}` | 取得指定條號的完整原文（右側欄用） |
| `GET` | `/api/law/status` | 取得法條版本狀態（最後更新時間） |

---

## 前端介面設計

三欄式側邊欄佈局：

```
┌──────────┬────────────────────────┬───────────────┐
│  左側欄   │       中間對話          │    右側欄      │
│          │                        │               │
│ 會話列表  │  使用者問題（右對齊）    │  法條完整原文  │
│ （依會話  │                        │               │
│ 分組）    │  AI 回覆：             │  修正日期標注  │
│          │  - 結構化摘要           │               │
│ 新增查詢  │  - 引用法條標籤         │  多條可收合    │
│ 按鈕      │  - 相關度百分比          │  展開顯示      │
│          │  - 低相關度警語（視情況） │               │
│ 法條版本  │                        │  點擊標籤切換  │
│ 狀態      │  輸入框 + 送出按鈕      │  顯示對應原文  │
│          │                        │               │
└──────────┴────────────────────────┴───────────────┘
```

**左側欄：** 會話列表（每個會話顯示第一個問題前 20 字為標題）、新增查詢按鈕、法條最後更新時間

**中間：** 對話訊息串、AI 結構化回覆、引用法條標籤（含相關度）、低相關度警語

**右側欄行為：**
- AI 回覆出現時，自動顯示 top-1 引用法條的原文
- 使用者點擊其他法條標籤時，切換右側欄顯示對應條文
- 各條文可獨立收合/展開

---

## 品質保障

### 幻覺防禦

- Prompt 明確限制 Claude 只能根據提供的法條內容回答
- 若資訊不足，要求回覆「現行法條無明確規定」
- 所有回覆附帶引用來源，讓使用者可自行驗證

### 相關性分級（基於 top-1 相似度，在呼叫 Claude 前判斷）

| 相似度 | 行為 |
|--------|------|
| > 0.75 | 正常回覆 |
| 0.5 ~ 0.75 | 呼叫 Claude，回覆附加警語「相關性較低，建議查閱原文確認」 |
| < 0.5 | 拒絕，回覆「此問題超出勞基法範圍」，**不呼叫 Claude** |

### Prompt Injection 防禦

- 輸入長度限制（500 字），超過回傳 400
- System / user role 嚴格隔離（透過 LlamaIndex API 傳入，不拼接字串）
- 查詢記錄全部保留，可事後審查異常

---

## 錯誤處理

| 情況 | 行為 |
|------|------|
| 問題與勞基法無關（相似度 < 0.5） | 回覆範圍外提示，不呼叫 Claude |
| 輸入超過 500 字 | 回傳 HTTP 400 |
| Claude API 失敗 | 顯示錯誤訊息，直接回傳檢索到的法條原文（降級模式） |
| 法條更新失敗 | 記錄 error_message 至 law_update_logs，保留舊版本，下次排程重試整批 |

---

## Tech Stack

| 層級 | 技術 |
|------|------|
| 前端 | Next.js + Tailwind CSS |
| 後端 | Python FastAPI |
| RAG 框架 | LlamaIndex |
| 向量資料庫 | PostgreSQL + pgvector |
| Embedding | OpenAI text-embedding-ada-002（1536 維） |
| 排程 | APScheduler（內建於後端） |
| LLM | Claude API（claude-sonnet-4-6） |
| 法條來源 | 全國法規資料庫 API |
| 本地部署 | Docker Compose |
| 未來部署 | AWS ECS |

---

## 擴展路徑（MVP → 多人內部工具）

MVP 階段完成後，往多人工具演進只需要：

1. 新增 `users` 資料表 + JWT 驗證
2. `sessions` 與 `query_history` 加上 `user_id` 欄位
3. 前端加入登入頁
4. 部署從 Docker Compose 搬至 AWS ECS + RDS

核心 RAG 邏輯、API 設計、資料庫結構均無需重構。
