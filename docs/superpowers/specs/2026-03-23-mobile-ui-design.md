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

Add `selectedArticle: CitedArticle | null` state for the bottom sheet. Pass `onArticleSelect` to `ChatPanel`, pass `selectedArticle` + `onClose` to `ArticleSheet`.

### 2. `frontend/src/components/Sidebar.tsx`

**New props:**
```typescript
mobileOpen?: boolean;
onMobileClose?: () => void;
```

**Mobile positioning** — change `<aside>` classes:
- Before: `w-56 bg-slate-900 flex flex-col p-3 gap-3 shrink-0`
- After: `fixed inset-y-0 left-0 z-40 w-72 bg-slate-900 flex flex-col p-3 gap-3 shrink-0 transition-transform duration-300 md:relative md:translate-x-0 md:w-56 md:z-auto` + conditional `translate-x-0` or `-translate-x-full` based on `mobileOpen`

**Mobile close button** — add ✕ button visible only on mobile (`md:hidden`), top-right of sidebar, calls `onMobileClose`.

### 3. `frontend/src/components/ChatPanel.tsx`

**New prop:**
```typescript
onOpenDrawer: () => void;
onArticleSelect: (article: CitedArticle) => void;
```

**Mobile header bar** — add above the message list, hidden on desktop (`md:hidden`):
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
- Placeholder: `"輸入問題..."` (no Ctrl+Enter hint — add `md:placeholder:content-['輸入您的勞動法規問題…（Ctrl+Enter送出）']` or just simplify the placeholder text)
- Submit button: add `rounded-full w-10 h-10 p-0 flex items-center justify-center` on mobile, keep rectangular on desktop via `md:rounded-lg md:w-auto md:h-auto md:px-4 md:py-2.5`

**Citation badges** — make tappable on mobile: wrap each badge in a button, `onClick={() => onArticleSelect(c)}`. On desktop they remain non-interactive spans.

**Message bubble max-width** — change `max-w-[80%]` to `max-w-[90%] md:max-w-[80%]` for more reading width on mobile.

### 4. `frontend/src/components/ArticlePanel.tsx`

Add `hidden md:flex` to the outer `<aside>` — completely hidden on mobile. No other changes.

### 5. `frontend/src/components/ArticleSheet.tsx` *(new file)*

Bottom sheet component for mobile article viewing. Shown when `article !== null`.

```typescript
interface Props {
  article: CitedArticle | null;
  onClose: () => void;
}
```

**Structure:**
```tsx
// Fixed overlay + sheet, mobile only (hidden md:hidden on the whole thing)
<div className="md:hidden">
  {/* Backdrop */}
  {article && <div className="fixed inset-0 z-40 bg-black/50" onClick={onClose} />}
  {/* Sheet */}
  <div className={`fixed bottom-0 left-0 right-0 z-50 bg-slate-900 rounded-t-2xl border-t border-slate-700 transition-transform duration-300 ${article ? "translate-y-0" : "translate-y-full"}`}>
    {/* Drag handle */}
    <div className="flex justify-center pt-3 pb-1">
      <div className="w-8 h-1 bg-slate-600 rounded-full" />
    </div>
    {/* Header */}
    <div className="flex justify-between items-start px-4 pb-3">
      <div>
        <div className="text-green-400 font-bold text-sm">{article?.law_name} 第 {article?.article_number} 條</div>
      </div>
      <button onClick={onClose} className="text-slate-500 text-xl leading-none">✕</button>
    </div>
    {/* Content — fetches full article text */}
    <ArticleSheetBody article={article} />
  </div>
</div>
```

`ArticleSheetBody` is an internal component that calls `getArticle(article.article_number, article.law_id)` when `article` changes, shows a loading state, then renders the full content.

Max height: `max-h-[70vh] overflow-y-auto` on the content area.

### 6. `frontend/src/app/laws/page.tsx`

**Mobile: card list instead of fixed-column table.**

The table grid (`grid-cols-[2fr_80px_140px_100px_80px]`) overflows on mobile. On mobile, render each law as a card:

```tsx
{/* Desktop table row */}
<div className="hidden md:grid grid-cols-[2fr_80px_140px_100px_80px] ...">
  ...existing row...
</div>

{/* Mobile card */}
<div className="md:hidden px-4 py-3 ...">
  <div className="flex justify-between items-start mb-1">
    <span className="text-slate-200 font-medium text-sm">{law.law_name}</span>
    <StatusBadge status={law.last_status} />
  </div>
  <div className="text-slate-500 text-xs mb-2">
    {law.article_count > 0 ? `${law.article_count} 條` : "尚未載入"} ·{" "}
    {law.last_updated ? new Date(law.last_updated).toLocaleDateString("zh-TW") : "從未更新"}
  </div>
  <button onClick={() => handleUpdate(law.law_id)} ...>
    {/* same button logic */}
  </button>
</div>
```

Table header row: add `hidden md:grid` to hide on mobile.

Laws page sidebar: on mobile, the Sidebar should be hidden entirely (`hidden md:flex`) since the laws page is already a management page — no drawer needed. Add a simple mobile top bar with "← 返回" and title instead.

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
