import { NextRequest } from "next/server";

const BACKEND_URL = process.env.BACKEND_URL ?? "http://localhost:8000";

export async function POST(request: NextRequest) {
  const body = await request.text();

  const cookie = request.headers.get("cookie") ?? "";
  const backendRes = await fetch(`${BACKEND_URL}/api/query/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Cookie: cookie },
    body,
  });

  if (!backendRes.ok) {
    return new Response(await backendRes.text(), { status: backendRes.status });
  }

  // Pipe the backend stream directly — no buffering
  return new Response(backendRes.body, {
    status: 200,
    headers: {
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-cache, no-transform",
      "Connection": "keep-alive",
      "X-Accel-Buffering": "no",
    },
  });
}
