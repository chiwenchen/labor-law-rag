const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export async function postQuery(question: string, sessionId?: string) {
  const res = await fetch(`${API_BASE}/api/query`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question, session_id: sessionId }),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function getSessions() {
  const res = await fetch(`${API_BASE}/api/sessions`);
  if (!res.ok) throw new Error("Failed to fetch sessions");
  return res.json();
}

export async function getSessionHistory(sessionId: string) {
  const res = await fetch(`${API_BASE}/api/sessions/${sessionId}/history`);
  if (!res.ok) throw new Error("Failed to fetch history");
  return res.json();
}

export async function getArticle(articleNumber: string) {
  const res = await fetch(`${API_BASE}/api/articles/${articleNumber}`);
  if (!res.ok) throw new Error("Article not found");
  return res.json();
}

export async function getLawStatus() {
  const res = await fetch(`${API_BASE}/api/law/status`);
  if (!res.ok) throw new Error("Failed to fetch law status");
  return res.json();
}
