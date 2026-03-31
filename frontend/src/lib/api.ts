import type {
  QueryResponse,
  SessionSummary,
  QueryHistoryItem,
  LawArticle,
  LawStatus,
  SupportedLaw,
  StreamEvent,
} from "@/types";

// Empty string = relative path, so requests go to the same host (works with ngrok, docker, etc.)
const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "";

export async function postQuery(
  question: string,
  sessionId?: string,
  lawIds?: string[],
  history?: Array<{ role: string; content: string }>,
): Promise<QueryResponse> {
  const body: Record<string, unknown> = { question };
  if (sessionId) body.session_id = sessionId;
  if (lawIds && lawIds.length > 0) body.law_ids = lawIds;
  if (history && history.length > 0) body.history = history;

  const res = await fetch(`${API_BASE}/api/query`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    credentials: "include",
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function* streamQuery(
  question: string,
  sessionId?: string,
  lawIds?: string[],
  history?: Array<{ role: string; content: string }>,
): AsyncGenerator<StreamEvent> {
  const body: Record<string, unknown> = { question };
  if (sessionId) body.session_id = sessionId;
  if (lawIds?.length) body.law_ids = lawIds;
  if (history?.length) body.history = history;

  const res = await fetch(`${API_BASE}/api/query/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(await res.text());

  const reader = res.body!.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop() ?? "";
      for (const line of lines) {
        if (line.startsWith("data: ") && line.length > 6) {
          yield JSON.parse(line.slice(6)) as StreamEvent;
        }
      }
    }
  } finally {
    reader.releaseLock();
  }
}

export async function getSessions(): Promise<SessionSummary[]> {
  const res = await fetch(`${API_BASE}/api/sessions`, {
    credentials: "include",
  });
  if (!res.ok) throw new Error("Failed to fetch sessions");
  return res.json();
}

export async function getSessionHistory(sessionId: string): Promise<QueryHistoryItem[]> {
  const res = await fetch(`${API_BASE}/api/sessions/${sessionId}/history`, {
    credentials: "include",
  });
  if (!res.ok) throw new Error("Failed to fetch history");
  return res.json();
}

export async function getArticle(articleNumber: string, lawId?: string): Promise<LawArticle> {
  const url = lawId
    ? `${API_BASE}/api/articles/${articleNumber}?law_id=${lawId}`
    : `${API_BASE}/api/articles/${articleNumber}`;
  const res = await fetch(url, { credentials: "include" });
  if (!res.ok) throw new Error("Article not found");
  return res.json();
}

export async function getLawStatus(): Promise<LawStatus> {
  const res = await fetch(`${API_BASE}/api/law/status`, {
    credentials: "include",
  });
  if (!res.ok) throw new Error("Failed to fetch law status");
  return res.json();
}

export async function getLaws(): Promise<SupportedLaw[]> {
  const res = await fetch(`${API_BASE}/api/laws`, {
    credentials: "include",
  });
  if (!res.ok) throw new Error("Failed to fetch laws");
  return res.json();
}

export async function updateLaw(
  lawId: string,
): Promise<{ status: string; article_count: number; message: string }> {
  const res = await fetch(`${API_BASE}/api/laws/${lawId}/update`, {
    method: "POST",
    credentials: "include",
    signal: AbortSignal.timeout(180_000),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}
