# TODOS

## RAG 搜尋品質

### 跨法規查詢命中率不足
**Priority:** P2
**What:** 用戶問跨法規的問題（如「資遣費新舊制差別」）時，搜尋只回傳勞基法條文，漏掉勞工退休金條例第 12 條。
**Why:** TOP_K=10 的向量搜尋偏向語意最近的單一法規，跨法規的問題容易漏。用戶得到不完整的答案。
**Context:** 測試問題「公司要資遣我，資遣費怎麼算？有新舊制的差別嗎？」只撈到勞基法第 17、84-2、18 條，完全沒有勞工退休金條例。勞工退休金條例已有 61 條法條且全部有 embedding。
**Possible fixes:**
1. 增加 TOP_K（15-20），讓更多法條有機會被撈到
2. 在 LLM prompt 加指示，讓它提及知道但未被提供的相關法條
3. 對「新舊制」等關鍵詞做法規路由，自動加入相關 law_id
**Discovered:** 2026-04-02，/qa regression test

## Completed

### Out-of-scope detection 未正確設定 flag
**Priority:** P3
**What:** 非勞動法問題（如「台北哪裡有好吃的牛肉麵」）LLM 正確拒答，但 `is_out_of_scope` flag 沒有設為 true。
**Why:** similarity score 0.633 高於 reject threshold 0.45，所以不觸發 out_of_scope。但 LLM 自行判斷超出範圍。
**Context:** 前端靠這個 flag 決定是否顯示引用法條面板。flag 沒設但 LLM 拒答時，UI 可能顯示空的法條面板。
**Possible fixes:** 在 LLM 回答後二次檢查回答內容是否為拒答，如果是則 override is_out_of_scope=True。
**Discovered:** 2026-04-03，RAG stress test

### 颱風假問題只引用勞基法，缺少相關行政命令
**Priority:** P3
**What:** 颱風假問題只找到勞基法條文（3條），但颱風假主要規範在「天然災害發生事業單位勞工出勤管理及工資給付要點」（行政命令），不在勞基法裡。
**Why:** 系統只 index 了法律層級的法規，沒有行政命令/要點。
**Context:** 這是 RAG 的法規覆蓋範圍問題，不是搜尋品質問題。需要擴充法規資料庫。
**Discovered:** 2026-04-03，RAG stress test
