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

export async function getArticle(articleNumber: string, lawId?: string): Promise<LawArticle> {
  const url = lawId
    ? `${API_BASE}/api/articles/${articleNumber}?law_id=${lawId}`
    : `${API_BASE}/api/articles/${articleNumber}`;
  const res = await fetch(url);
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
    signal: AbortSignal.timeout(180_000),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}
