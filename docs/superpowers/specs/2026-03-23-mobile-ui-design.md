# Mobile UI Optimization Design

**Goal:** Make the chat interface fully usable on mobile (375px+) without breaking the desktop layout.

**Architecture:** Responsive Tailwind breakpoints (`md:`) on existing components. Sidebar becomes a slide-in drawer on mobile. ArticlePanel hidden on mobile, replaced by a new `ArticleSheet` bottom sheet triggered by citation badge taps. Laws page table becomes a card list on mobile.

**Tech Stack:** Next.js 14 App Router, Tailwind CSS, TypeScript. No new dependencies.

---

## Out of Scope

- Tablet-specific layout (treat tablet same as desktop at `md:`)
- Swipe gesture for drawer (click/tap only)
- Laws page drawer navigation (laws page uses full-width layout, no sidebar on mobile)
- Push notifications, PWA manifest

---

## Breakpoints

- **Mobile:** `< 768px` (default, no prefix)
- **Desktop:** `≥ 768px` (`md:` prefix)

All changes are additive Tailwind classes. Desktop styles are unchanged.

---

## Component Changes

### 1. `frontend/src/app/page.tsx`

Add `drawerOpen: boolean` state (default `false`).

Pass to `Sidebar`:
- `mobileOpen={drawerOpen}`
- `onMobileClose={() => setDrawerOpen(false)}`

Pass to `ChatPanel`:
- `onOpenDrawer={() => setDrawerOpen(true)}`

Add overlay `<div>` between Sidebar and ChatPanel: visible only when `drawerOpen && mobile`, `onClick` closes drawer:
```tsx
{drawerOpen && (
  <div
    className="fixed inset-0 z-30 bg-black/50 md:hidden"
    onClick={() => setDrawerOpen(false)}
  />
)}
```

Add `selectedArticle: CitedArticle | null` state (default `null`) for the bottom sheet. Pass `onArticleSelect` to `ChatPanel`, pass `selectedArticle` + `onClose={() => setSelectedArticle(null)}` to `ArticleSheet`.

Import `ArticleSheet` from `@/components/ArticleSheet`. Render `<ArticleSheet>` as the **last child of `<main>`**, after `<ArticlePanel>`:

```tsx
<main className="flex h-screen bg-slate-800 text-white overflow-hidden">
  {/* overlay */}
  <Sidebar ... />
  <ChatPanel ... />
  <ArticlePanel ... />
  <ArticleSheet article={selectedArticle} onClose={() => setSelectedArticle(null)} />
</main>
```

`position: fixed` on `ArticleSheet`'s inner elements is unaffected by `overflow-hidden` on `<main>` (overflow alone does not create a containing block for fixed elements).

### 2. `frontend/src/components/Sidebar.tsx`

**Updated `Props` interface** — add two optional fields to the existing interface:

```typescript
interface Props {
  activeSessionId: string | null;
  onSelectSession: (id: string) => void;
  onNewSession: () => void;
  refreshKey?: number;
  selectedLawIds: string[];
  onLawScopeChange: (ids: string[]) => void;
  showLawScope?: boolean;
  mobileOpen?: boolean;       // NEW
  onMobileClose?: () => void; // NEW
}
```

Destructure both in the function signature.

**Mobile positioning** — replace the `<aside>` class string with a single definitive value:

```tsx
<aside
  className={`fixed inset-y-0 left-0 z-40 w-72 bg-slate-900 flex flex-col p-3 gap-3 shrink-0 transition-transform duration-300 relative md:relative md:translate-x-0 md:w-56 md:z-auto ${
    mobileOpen ? "translate-x-0" : "-translate-x-full"
  }`}
>
```

Mechanism: on mobile (`< 768px`) `fixed` applies and the drawer slides in/out via `translate-x-0` / `-translate-x-full`. At `md:` breakpoint, `md:relative` overrides `fixed`, and `md:translate-x-0` ensures the sidebar is always visible regardless of `mobileOpen`. `md:z-auto` removes the elevated stacking context on desktop.

**Mobile close button** — add an absolutely-positioned ✕ button inside the `<aside>`, as the first child after the opening tag:

```tsx
<button
  onClick={onMobileClose}
  className="md:hidden absolute top-3 right-3 text-slate-500 hover:text-slate-300 text-lg leading-none p-1"
  aria-label="關閉選單"
>
  ✕
</button>
```

The existing `<span className="text-blue-400 ...">查詢紀錄</span>` stays unchanged. No DOM restructuring needed.

### 3. `frontend/src/components/ChatPanel.tsx`

**Updated `Props` interface** — add two new fields to the existing interface:

```typescript
interface Props {
  sessionId: string | null;
  messages: ChatMessage[];
  onNewMessage: (userMsg: ChatMessage, assistantMsg: ChatMessage, sessionId: string) => void;
  onArticlesChange: (articles: CitedArticle[]) => void;
  selectedLawIds: string[];
  onOpenDrawer: () => void;                          // NEW
  onArticleSelect: (article: CitedArticle) => void;  // NEW
}
```

Destructure both in the function signature.

**Mobile header bar** — add above the message list (before the scrollable `flex-1` div), hidden on desktop (`md:hidden`):
```tsx
<div className="md:hidden flex items-center gap-3 px-4 py-3 bg-slate-900 border-b border-slate-700 shrink-0">
  <button onClick={onOpenDrawer} className="text-slate-400 text-xl">☰</button>
  <span className="text-slate-200 text-sm font-medium flex-1">勞動法規查詢</span>
  <span className="text-slate-500 text-xs bg-slate-800 px-2 py-0.5 rounded-full">
    {selectedLawIds.length === 0 ? "全部法規" : `${selectedLawIds.length} 部`}
  </span>
</div>
```

**Input bar** — update placeholder and submit button for mobile:
- Placeholder: Simplify to `"輸入問題..."` for both breakpoints (single value, no responsive switching needed).
- Submit button: change to a circular icon button on mobile, rectangular on desktop:
  ```tsx
  <button
    onClick={handleSubmit}
    disabled={loading || !input.trim()}
    className="bg-blue-700 text-white disabled:opacity-50 disabled:cursor-not-allowed transition-colors rounded-full w-10 h-10 p-0 flex items-center justify-center text-lg md:rounded-lg md:w-auto md:h-auto md:px-4 md:py-2.5 md:text-sm md:font-medium"
  >
    <span className="md:hidden">↑</span>
    <span className="hidden md:inline">送出</span>
  </button>
  ```
  Mobile shows `↑` icon inside the circle; desktop shows `送出` text in the original rectangular button.

**Citation badges** — replace each `<span>` badge with a `<button>` that triggers `onArticleSelect`. The `key` prop moves to the `<button>`:

```tsx
{msg.cited_articles.map((c) => (
  <button
    key={`${c.law_id}-${c.article_number}`}
    onClick={() => onArticleSelect(c)}
    className="bg-blue-950 border border-blue-700 text-blue-300 px-2 py-1 rounded-full text-xs"
    title={c.law_name}
  >
    {c.law_name} §{c.article_number}
  </button>
))}
```

**Message bubble max-width** — change `max-w-[80%]` to `max-w-[90%] md:max-w-[80%]` for more reading width on mobile.

### 4. `frontend/src/components/ArticlePanel.tsx`

The component has **two `<aside>` branches**: the empty-state aside (`articles.length === 0`) and the populated aside. Add `hidden` and the appropriate `md:` restore class to **both** branches:

- Empty-state aside (currently `w-60 bg-slate-900 p-3 text-xs text-slate-600 flex items-center justify-center shrink-0`): change to `hidden md:flex w-60 bg-slate-900 p-3 text-xs text-slate-600 items-center justify-center shrink-0` — i.e., prepend `hidden md:flex` and keep `items-center justify-center` (do not drop them).
- Populated aside (currently `w-60 bg-slate-900 flex flex-col p-3 gap-2 overflow-y-auto shrink-0`): change to `hidden md:flex w-60 bg-slate-900 flex-col p-3 gap-2 overflow-y-auto shrink-0` — i.e., prepend `hidden md:flex` and remove the standalone `flex` (now implied by `md:flex`).

### 5. `frontend/src/components/ArticleSheet.tsx` *(new file)*

Bottom sheet component for mobile article viewing. Shown when `article !== null`.

```typescript
interface Props {
  article: CitedArticle | null;
  onClose: () => void;
}
```

**Animation note:** The sheet is always rendered in the DOM (never conditionally mounted). It starts off-screen via `translate-y-full` and slides up to `translate-y-0` when `article !== null`. This means `translate-y-full` and `translate-y-0` must be present in the source so Tailwind's JIT includes them — they are standard classes and will not be purged.

**Structure:**
```tsx
// Fixed overlay + sheet, mobile only (hidden on md+)
<div className="md:hidden">
  {/* Backdrop — only rendered when article is set */}
  {article && <div className="fixed inset-0 z-40 bg-black/50" onClick={onClose} />}
  {/* Sheet — always in DOM, slides in/out via transform */}
  <div className={`fixed bottom-0 left-0 right-0 z-50 bg-slate-900 rounded-t-2xl border-t border-slate-700 transition-transform duration-300 ${article ? "translate-y-0" : "translate-y-full"}`}>
    {/* Drag handle */}
    <div className="flex justify-center pt-3 pb-1 shrink-0">
      <div className="w-8 h-1 bg-slate-600 rounded-full" />
    </div>
    {/* Header — shrink-0 so it doesn't scroll away */}
    <div className="flex justify-between items-start px-4 pb-3 shrink-0">
      <div>
        <div className="text-green-400 font-bold text-sm">{article?.law_name} 第 {article?.article_number} 條</div>
      </div>
      <button onClick={onClose} className="text-slate-500 text-xl leading-none">✕</button>
    </div>
    {/* Scrollable content area — max 70vh, overflow scrolls */}
    <div className="max-h-[70vh] overflow-y-auto">
      <ArticleSheetBody article={article} />
    </div>
  </div>
</div>
```

`ArticleSheetBody` is an internal component inside the same file:

```tsx
function ArticleSheetBody({ article }: { article: CitedArticle | null }) {
  const [lawArticle, setLawArticle] = useState<LawArticle | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(false);

  useEffect(() => {
    if (!article) {
      setLawArticle(null);
      setError(false);
      return;
    }
    setLawArticle(null);
    setError(false);
    setLoading(true);
    getArticle(article.article_number, article.law_id)
      .then(setLawArticle)
      .catch(() => setError(true))
      .finally(() => setLoading(false));
  }, [article]);

  // Guard: article is null (sheet is closed) — render nothing
  if (!article) return null;

  if (loading) {
    return <div className="px-4 pb-6 text-slate-500 text-sm">查詢中...</div>;
  }
  if (error || !lawArticle) {
    return <div className="px-4 pb-6 text-red-400 text-sm">無法載入條文</div>;
  }
  return (
    <div className="px-4 pb-6">
      <p className="text-slate-400 text-[11px] leading-relaxed whitespace-pre-wrap">
        {lawArticle.content}
      </p>
      {lawArticle.version && (
        <div className="text-slate-600 text-[10px] mt-2">修正日期：{lawArticle.version}</div>
      )}
    </div>
  );
}
```

Import `LawArticle` from `@/types` and `getArticle` from `@/lib/api` in `ArticleSheet.tsx`.

### 6. `frontend/src/app/laws/page.tsx`

**Mobile: card list instead of fixed-column table.**

The table grid (`grid-cols-[2fr_80px_140px_100px_80px]`) overflows on mobile. Refactor each row by replacing the single outer `<div>` with an outer wrapper that keeps only the `key` and the conditional `border-t border-slate-800` divider, and move the grid/card content into two sibling divs inside:

```tsx
{laws.map((law, i) => (
  <div key={law.law_id} className={i > 0 ? "border-t border-slate-800" : ""}>
    {/* Desktop grid row */}
    <div className="hidden md:grid grid-cols-[2fr_80px_140px_100px_80px] gap-4 px-4 py-3 items-center text-sm">
      <span className="text-slate-200 font-medium">{law.law_name}</span>
      <span className="text-slate-400 text-xs">{law.article_count > 0 ? law.article_count : "—"}</span>
      <span className="text-slate-500 text-xs">
        {law.last_updated ? new Date(law.last_updated).toLocaleDateString("zh-TW") : "尚未更新"}
      </span>
      <span>
        <StatusBadge status={law.last_status} />
        {errors[law.law_id] && (
          <div className="text-red-400 text-[10px] mt-0.5 leading-tight">{errors[law.law_id]}</div>
        )}
      </span>
      <span>{/* update button — see existing code */}</span>
    </div>

    {/* Mobile card */}
    <div className="md:hidden px-4 py-3">
      <div className="flex justify-between items-start mb-1">
        <span className="text-slate-200 font-medium text-sm">{law.law_name}</span>
        <StatusBadge status={law.last_status} />
      </div>
      <div className="text-slate-500 text-xs mb-2">
        {law.article_count > 0 ? `${law.article_count} 條` : "尚未載入"} ·{" "}
        {law.last_updated ? new Date(law.last_updated).toLocaleDateString("zh-TW") : "從未更新"}
      </div>
      {errors[law.law_id] && (
        <div className="text-red-400 text-[10px] mb-1">{errors[law.law_id]}</div>
      )}
      <button
        onClick={() => handleUpdate(law.law_id)}
        disabled={updating[law.law_id]}
        className={`text-xs px-3 py-1.5 rounded transition-colors ${
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
        ) : law.last_status === "never_run" ? "載入" : "更新"}
      </button>
    </div>
  </div>
))}
```

Table header row: add `hidden md:grid` to hide on mobile (keep other classes identical).

**Laws page structure on mobile:**

Hide the `<Sidebar>` element on mobile by adding a wrapper class to the Sidebar JSX in `laws/page.tsx`:

```tsx
<div className="hidden md:block">
  <Sidebar
    activeSessionId={null}
    onSelectSession={() => {}}
    onNewSession={() => {}}
    selectedLawIds={[]}
    onLawScopeChange={() => {}}
    showLawScope={false}
  />
</div>
```

This hides the entire Sidebar component output on mobile without touching `Sidebar.tsx` internals.

Add a mobile-only top bar as a **sibling before** the `<div className="flex-1 flex flex-col min-w-0 p-6">` content div, so it spans the full width outside the padded container:

```tsx
<main className="flex h-screen bg-slate-800 text-white overflow-hidden">
  <div className="hidden md:block">
    <Sidebar ... />
  </div>

  {/* Mobile top bar — outside padded content div so it spans full width */}
  <div className="md:hidden fixed top-0 left-0 right-0 z-10 flex items-center gap-3 px-4 py-3 bg-slate-900 border-b border-slate-700">
    <Link href="/" className="text-blue-400 text-sm">← 返回</Link>
    <span className="text-slate-200 text-sm font-medium flex-1">法規管理</span>
  </div>

  <div className="flex-1 flex flex-col min-w-0 p-6 md:p-6 pt-[52px] md:pt-6">
    {/* existing content — add top padding on mobile to clear the fixed top bar */}
    {/* The existing desktop ← 返回查詢 link: add hidden md:flex to its parent div */}
    <div className="hidden md:flex items-center gap-4 mb-6">
      <Link href="/" className="text-slate-400 hover:text-white text-sm transition-colors">← 返回查詢</Link>
      <h1 className="text-white font-semibold text-lg">法規管理</h1>
    </div>
    ...
  </div>
</main>
```

Key points:
- The fixed mobile top bar is `52px` tall (`py-3` = 12px × 2 + `text-sm` line ≈ 20px → ~52px total). Add `pt-[52px] md:pt-6` to the content div to prevent content from hiding behind it on mobile.
- The existing `← 返回查詢` desktop link + `h1` header gets `hidden md:flex` so it only shows on desktop.
- `md:p-6` restores full padding on desktop (overrides the `pt-[52px]`).

---

## Error Handling

- Drawer open/close: no error states needed (pure CSS)
- `ArticleSheet` fetch fails: show "無法載入條文" inline in sheet body, keep sheet open so user can dismiss manually
- Sheet opened before fetch completes: show spinner (`查詢中...`)

---

## File Summary

| File | Change |
|------|--------|
| `frontend/src/app/page.tsx` | Add `drawerOpen`, `selectedArticle` state; overlay div; wire props |
| `frontend/src/components/Sidebar.tsx` | Add `mobileOpen`/`onMobileClose` props; fixed drawer positioning; ✕ button |
| `frontend/src/components/ChatPanel.tsx` | Add mobile header bar; `onOpenDrawer`/`onArticleSelect` props; badge tap; input tweaks |
| `frontend/src/components/ArticlePanel.tsx` | Add `hidden md:flex` |
| `frontend/src/components/ArticleSheet.tsx` | **New** bottom sheet component |
| `frontend/src/app/laws/page.tsx` | Mobile card list; mobile top bar |
