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
| 全國法規資料庫 API（laws.moj.gov.tw） | 抓取最新勞基法條文 |

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
    ├── 沒變動 → 跳過
    ├── 有修改 → 重新 Embedding，更新向量
    ├── 新條文 → Embedding，寫入
    └── 已廢止 → 標記 is_active = false（保留歷史，不刪除）
    │
    ▼
寫入 law_update_logs（更新時間、異動條數、狀態）
```

### 流程二：使用者查詢

```
使用者輸入問題
    │
    ▼
[輸入驗證]
長度 > 500 字 或含惡意內容 → 拒絕
    │
    ▼
問題向量化（Embedding）
    │
    ▼
pgvector 搜尋最相似的 5 條法條（附相似度分數 0~1）
    │
    ├── 最高分 < 0.5 → 回覆「超出勞基法範圍」，結束
    │
    ▼
組成 Prompt（system / user role 隔離）
  system: 你是勞基法助理，只能根據提供的條文回答
  context: [5 條法條原文]
  user: [使用者問題]
    │
    ▼
呼叫 Claude API 生成回覆
    │
    ▼
回傳給前端：
  - AI 摘要文字
  - 引用法條列表（條號 + 相似度分數）
    │
    ▼
寫入 query_history
```

---

## 資料庫結構

### `law_articles`（法條本體）

| 欄位 | 型別 | 說明 |
|------|------|------|
| `id` | serial PK | |
| `article_number` | varchar | 條號，例如 "38" |
| `title` | varchar | 條文標題 |
| `content` | text | 條文內文 |
| `embedding` | vector(1536) | pgvector 向量 |
| `is_active` | boolean | false = 已廢止 |
| `last_updated` | timestamp | 條文最後修正日期 |
| `version` | varchar | 法規版本號 |

### `query_history`（查詢紀錄）

| 欄位 | 型別 | 說明 |
|------|------|------|
| `id` | serial PK | |
| `question` | text | 使用者問題 |
| `answer` | text | AI 回覆 |
| `cited_articles` | jsonb | 引用法條陣列 |
| `max_similarity_score` | float | 最高相似度 |
| `created_at` | timestamp | |

### `law_update_logs`（更新紀錄）

| 欄位 | 型別 | 說明 |
|------|------|------|
| `id` | serial PK | |
| `updated_at` | timestamp | |
| `articles_changed` | int | 異動條數 |
| `status` | varchar | success / failed |

---

## 前端介面設計

三欄式側邊欄佈局：

```
┌──────────┬────────────────────────┬───────────────┐
│  左側欄   │       中間對話          │    右側欄      │
│          │                        │               │
│ 查詢紀錄  │  使用者問題（右對齊）    │  法條完整原文  │
│ 列表      │                        │               │
│          │  AI 回覆：             │  修正日期標注  │
│ 新增查詢  │  - 結構化摘要           │               │
│ 按鈕      │  - 引用法條標籤         │  多條可收合    │
│          │  - 相關度百分比          │  展開顯示      │
│ 法條版本  │                        │               │
│ 狀態      │  輸入框 + 送出按鈕      │  隨對話自動    │
│          │                        │  更新          │
└──────────┴────────────────────────┴───────────────┘
```

**左側欄：** 查詢紀錄列表、新增查詢按鈕、法條版本與最後更新時間
**中間：** 對話訊息串、AI 結構化回覆、引用法條標籤（含相關度）
**右側欄：** 點擊法條標籤後顯示完整原文，可收合展開

---

## 品質保障

### 幻覺防禦

- Prompt 明確限制 Claude 只能根據提供的法條內容回答
- 若資訊不足，要求回覆「現行法條無明確規定」
- 所有回覆附帶引用來源，讓使用者可自行驗證

### 相關性分級

| 相似度 | 行為 |
|--------|------|
| > 0.75 | 正常回覆 |
| 0.5 ~ 0.75 | 回覆 + 加警語「相關性較低，建議查閱原文確認」 |
| < 0.5 | 拒絕，回覆「此問題超出勞基法範圍」 |

### Prompt Injection 防禦

- 輸入長度限制（500 字）
- System / user role 嚴格隔離（透過 LlamaIndex API，不拼接字串）
- 查詢記錄全部保留，可事後審查異常

---

## 錯誤處理

| 情況 | 行為 |
|------|------|
| 問題與勞基法無關 | 回覆範圍外提示，不呼叫 Claude |
| Claude API 失敗 | 顯示錯誤訊息，直接回傳檢索到的法條原文 |
| 法條更新失敗 | 記錄 log，保留舊版本，下次排程重試 |
| 使用者輸入過長 / 惡意 | 輸入層攔截，回傳 400 錯誤 |

---

## Tech Stack

| 層級 | 技術 |
|------|------|
| 前端 | Next.js + Tailwind CSS |
| 後端 | Python FastAPI |
| RAG 框架 | LlamaIndex |
| 向量資料庫 | PostgreSQL + pgvector |
| 排程 | APScheduler（內建於後端） |
| LLM | Claude API（claude-sonnet-4-6） |
| 法條來源 | 全國法規資料庫 API |
| 本地部署 | Docker Compose |
| 未來部署 | AWS ECS |

---

## 擴展路徑（MVP → 多人內部工具）

MVP 階段完成後，往多人工具演進只需要：

1. 新增 `users` 資料表 + JWT 驗證
2. `query_history` 加上 `user_id` 欄位
3. 前端加入登入頁
4. 部署從 Docker Compose 搬至 AWS ECS + RDS

核心 RAG 邏輯、資料庫結構、API 設計均無需重構。
