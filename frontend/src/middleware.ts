import { NextRequest, NextResponse } from "next/server";

const BACKEND_URL = process.env.BACKEND_URL ?? "http://localhost:8000";

export async function middleware(request: NextRequest) {
  const session = request.cookies.get("session");
  if (!session?.value) {
    return NextResponse.redirect(new URL("/login", request.url));
  }

  try {
    const res = await fetch(`${BACKEND_URL}/api/auth/me`, {
      headers: { Cookie: `session=${session.value}` },
      cache: "no-store",
    });
    if (!res.ok) {
      return NextResponse.redirect(new URL("/login", request.url));
    }
  } catch {
    return NextResponse.redirect(new URL("/login", request.url));
  }

  return NextResponse.next();
}

export const config = {
  matcher: ["/((?!login|_next/static|_next/image|favicon.ico).*)"],
};
