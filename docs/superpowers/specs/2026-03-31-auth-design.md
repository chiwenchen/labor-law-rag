# Auth System Design — Labor Law RAG

**Date:** 2026-03-31
**Scope:** Email OTP 帳號管理、登入登出、角色分流（HR / 員工）

---

## 目標

為現有的勞基法 RAG 查詢系統加入帳號管理與登入功能：

- 使用 **Email OTP**（透過 Resend）作為唯一登入方式
- 使用 **httpOnly Cookie** 維持 session（單一 server，記憶體存放）
- 首次登入時詢問身份（HR / 員工），存入 PostgreSQL
- 根據身份調整 RAG 回答角度：HR 著重合規管理，員工著重個人權益

---

## 技術選型

| 項目 | 選擇 | 原因 |
|---|---|---|
| Email 服務 | **Resend** | 設定最簡單，GitHub 帳號即可，無 sandbox 限制 |
| Session 機制 | **httpOnly Cookie + in-memory dict** | 單一 server，對外部署需防 XSS |
| 帳號存放 | **PostgreSQL** | 需要重啟後持久化 email + role |
| OTP 存放 | **In-memory dict（10 分鐘 TTL）**| 短暫使用，無需持久化 |
| Session 存放 | **In-memory dict（無 expiry）** | 用戶指定，logout 時手動刪除 |

---

## 資料模型

### PostgreSQL — `users` table（新增 migration: `003_users.sql`）

```sql
CREATE TABLE users (
  id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  email      TEXT UNIQUE NOT NULL,
  role       TEXT NOT NULL CHECK (role IN ('hr', 'employee')),
  created_at TIMESTAMPTZ DEFAULT now()
);
```

### In-memory: `otp_store: dict[str, OtpEntry]`

```python
@dataclass
class OtpEntry:
    otp: str           # 6 位數字
    expires_at: datetime  # now() + 10 分鐘
```

- Key = email
- 驗證成功後立刻 `del otp_store[email]`（防止重複使用）
- 過期的 entry 在下次 send OTP 時覆蓋

### In-memory: `pending_store: dict[str, str]`

```python
pending_store: dict[str, str] = {}
# Key = pending_token (UUID)，Value = email
```

- `otp/verify` 成功且為新用戶時，產生 pending_token 並存入 pending_store
- 回傳 `{ is_new_user: true, pending_token: "..." }` 給前端
- `register` endpoint 需帶入 pending_token 才能完成註冊，防止跳過 OTP 直接呼叫
- 註冊成功後立刻 `del pending_store[pending_token]`

### In-memory: `session_store: dict[str, SessionData]`

```python
@dataclass
class SessionData:
    user_id: UUID
    email: str
    role: Literal['hr', 'employee']
```

- Key = UUID token（存在 httpOnly cookie）
- 無 expiry
- logout 時 `del session_store[token]`

### Cookie 設定

```python
response.set_cookie(
    key="session",
    value=token,
    httponly=True,   # JS 無法存取，防 XSS
    secure=True,     # HTTPS only（production）
    samesite="lax",  # 防 CSRF
)
```

---

## 後端設計

### 新增/修改檔案

```
backend/app/
├── auth/                        # 新增
│   ├── store.py                 # otp_store + session_store
│   └── dependencies.py          # get_current_user() FastAPI dependency
├── routers/
│   ├── auth.py                  # 新增 — 5 個 endpoint
│   ├── query.py                 # 修改 — 加入 auth dependency + role
│   └── sessions.py              # 修改 — 加入 auth dependency
├── services/
│   ├── email_service.py         # 新增 — Resend OTP 發送
│   └── rag.py                   # 修改 — 加入 role 參數到 system prompt
├── db/migrations/
│   └── 003_users.sql            # 新增
└── config.py                    # 修改 — 加入 RESEND_API_KEY, EMAIL_FROM, FRONTEND_URL
```

### API Endpoints（routers/auth.py）

| Method | Path | 說明 |
|---|---|---|
| `POST` | `/api/auth/otp/send` | 產生 OTP，寫入 otp_store，用 Resend 寄信 |
| `POST` | `/api/auth/otp/verify` | 驗證 OTP；若新用戶回傳 `is_new_user: true`；若舊用戶直接建立 session、Set-Cookie |
| `POST` | `/api/auth/register` | 新用戶帶 `pending_token` + `role`，驗證 token 後 INSERT users，建立 session、Set-Cookie |
| `POST` | `/api/auth/logout` | `del session_store[token]`，Clear-Cookie |
| `GET` | `/api/auth/me` | 回傳 `{ email, role }`，未登入回 401 |

### Auth Dependency

```python
# auth/dependencies.py
async def get_current_user(request: Request) -> SessionData:
    token = request.cookies.get("session")
    if not token or token not in session_store:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return session_store[token]
```

所有需要登入的 endpoint 加上 `user: SessionData = Depends(get_current_user)`。

### Role-based RAG（rag.py）

`query_law()` 新增 `role` 參數，根據角色使用不同 system prompt：

**HR（role="hr"）：**
> 你是台灣勞基法助理，服務對象為企業 HR。請從公司管理合規的角度回答，包含：雇主義務、違規罰則、內部流程建議、勞資爭議處理方式。

**員工（role="employee"）：**
> 你是台灣勞基法助理，服務對象為勞工員工。請從勞工權益保障的角度回答，包含：個人權利、申請方式、如何向公司主張、必要時的申訴管道。

### 新增 Environment Variables

```env
# Backend
RESEND_API_KEY=re_xxxx
EMAIL_FROM=noreply@yourdomain.com   # 開發時可用 onboarding@resend.dev
FRONTEND_URL=https://yourdomain.com  # 用於 CORS allow_origins

# Frontend（Next.js）
BACKEND_URL=http://localhost:8000   # middleware 對 FastAPI 的內部呼叫
```

---

## 前端設計

### 新增/修改檔案

```
frontend/src/
├── app/
│   ├── login/
│   │   └── page.tsx        # 新增 — OTP 登入頁
│   └── layout.tsx          # 修改 — 傳入 user 資訊給 Sidebar
├── middleware.ts            # 新增 — auth guard，保護所有非 /login 路由
├── lib/
│   ├── auth.ts             # 新增 — getUser(), logout()
│   └── api.ts              # 修改 — 所有 fetch 加 credentials: 'include'
└── components/
    └── Sidebar.tsx         # 修改 — 底部顯示 email、role badge、登出
```

### /login 頁面流程（單頁三步驟）

**Step 1 — 輸入 Email**
- 輸入框 + 「寄送驗證碼」按鈕
- 送出後 loading 狀態，成功後切換到 Step 2

**Step 2 — 輸入 OTP**
- 6 格獨立輸入框，自動跳格
- 顯示「驗證碼已寄至 {email}」+ 「← 重新輸入 email」連結
- 驗證失敗顯示錯誤訊息（OTP 錯誤 / 已過期）
- 驗證成功：
  - 若 `is_new_user: true` → 切換到 Step 3
  - 若舊用戶 → 直接 redirect 到 `/`

**Step 3 — 選擇身份（新用戶限定）**
- 兩個選項卡：「👔 人資（HR）」/ 「👤 員工」
- 選擇後 POST `/api/auth/register`，成功後 redirect 到 `/`

### Auth Guard

使用 Next.js **middleware**（`frontend/src/middleware.ts`）保護所有路由：

```typescript
// middleware.ts
export async function middleware(request: NextRequest) {
  const session = request.cookies.get('session')
  if (!session) {
    return NextResponse.redirect(new URL('/login', request.url))
  }
  // 驗證 session 有效性（呼叫 /api/auth/me）
  const res = await fetch(`${process.env.BACKEND_URL}/api/auth/me`, {
    headers: { Cookie: `session=${session.value}` },
  })
  if (!res.ok) {
    return NextResponse.redirect(new URL('/login', request.url))
  }
  return NextResponse.next()
}

export const config = {
  matcher: ['/((?!login|_next|favicon).*)'],  // 排除 /login 路由
}
```

新增 env var：`BACKEND_URL=http://localhost:8000`（Next.js server 對 FastAPI 的內部呼叫用）。

### Sidebar 變更

底部新增：
- 用戶 email（小字）
- 角色 badge（`👔 人資` / `👤 員工`，不同顏色）
- 「登出」連結（呼叫 `logout()` 後 redirect 到 `/login`）

---

## 登入 / 註冊流程摘要

### 新用戶（首次註冊）
1. 輸入 email → POST `/api/auth/otp/send` → Resend 寄信
2. 輸入 OTP → POST `/api/auth/otp/verify` → `{ is_new_user: true }`
3. 選擇身份 → POST `/api/auth/register { role }` → DB INSERT + Set-Cookie
4. Redirect → `/`

### 舊用戶（登入）
1. 輸入 email → POST `/api/auth/otp/send` → Resend 寄信
2. 輸入 OTP → POST `/api/auth/otp/verify` → Set-Cookie
3. Redirect → `/`

### 登出
1. 點擊「登出」→ POST `/api/auth/logout` → `del session_store[token]` + Clear-Cookie
2. Redirect → `/login`

---

## 不在本次範圍內

- Google SSO（未來可加）
- Session expiry（用戶決定不需要）
- 多 server / Redis session（目前 single server）
- 用戶管理後台（修改 role、刪除帳號）
- 密碼登入
