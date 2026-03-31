"""
Integration tests covering bugs fixed in fix/cookie-secure:

1. Cookie secure flag respects FRONTEND_URL (http → insecure, https → secure)
2. OTP bypass for test email (cwchen2000@gmail.com accepts any OTP)
3. Query endpoint body parsing works with @limiter.limit decorator
4. Stream endpoint body parsing works with @limiter.limit decorator
5. Full auth → query flow succeeds end-to-end
"""
from __future__ import annotations

import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from fastapi.testclient import TestClient
from httpx import AsyncClient, ASGITransport

from app.main import app
from app.auth.store import otp_store, pending_store, session_store, SessionData
from app.services.rag import QueryResult


TEST_BYPASS_EMAIL = "cwchen2000@gmail.com"


@pytest.fixture(autouse=True)
def clear_stores():
    otp_store.clear()
    pending_store.clear()
    session_store.clear()
    yield
    otp_store.clear()
    pending_store.clear()
    session_store.clear()


@pytest.fixture
def client():
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def authed_client(client):
    """TestClient with a valid session cookie pre-set."""
    token = str(uuid4())
    session_store[token] = SessionData(user_id=uuid4(), email="test@example.com", role="employee")
    client.cookies.set("session", token)
    return client


# ---------------------------------------------------------------------------
# 1. Cookie secure flag
# ---------------------------------------------------------------------------

class TestCookieSecureFlag:
    def test_cookie_is_insecure_for_http_frontend(self, client):
        """When FRONTEND_URL starts with http://, session cookie must NOT be secure."""
        from datetime import datetime, timedelta, timezone
        from app.auth.store import OtpEntry

        with patch("app.config.settings") as mock_settings:
            mock_settings.frontend_url = "http://localhost:3000"
            otp_store[TEST_BYPASS_EMAIL] = OtpEntry(
                otp="123456",
                expires_at=datetime.now(timezone.utc) + timedelta(minutes=10),
            )
            mock_user = MagicMock()
            mock_user.id = uuid4()
            mock_user.email = TEST_BYPASS_EMAIL
            mock_user.role = "employee"

            with patch("app.routers.auth.get_user_by_email", new_callable=AsyncMock, return_value=mock_user):
                with patch("app.config.settings", mock_settings):
                    response = client.post(
                        "/api/auth/otp/verify",
                        json={"email": TEST_BYPASS_EMAIL, "otp": "000000"},
                    )

        assert response.status_code == 200
        set_cookie = response.headers.get("set-cookie", "")
        assert "session=" in set_cookie
        assert "Secure" not in set_cookie, "Cookie must NOT be Secure over HTTP"

    def test_cookie_is_secure_for_https_frontend(self, client):
        """When FRONTEND_URL starts with https://, session cookie must be Secure."""
        from datetime import datetime, timedelta, timezone
        from app.auth.store import OtpEntry

        with patch("app.config.settings") as mock_settings:
            mock_settings.frontend_url = "https://example.com"
            otp_store[TEST_BYPASS_EMAIL] = OtpEntry(
                otp="123456",
                expires_at=datetime.now(timezone.utc) + timedelta(minutes=10),
            )
            mock_user = MagicMock()
            mock_user.id = uuid4()
            mock_user.email = TEST_BYPASS_EMAIL
            mock_user.role = "employee"

            with patch("app.routers.auth.get_user_by_email", new_callable=AsyncMock, return_value=mock_user):
                with patch("app.config.settings", mock_settings):
                    response = client.post(
                        "/api/auth/otp/verify",
                        json={"email": TEST_BYPASS_EMAIL, "otp": "000000"},
                    )

        assert response.status_code == 200
        set_cookie = response.headers.get("set-cookie", "")
        assert "Secure" in set_cookie, "Cookie must be Secure over HTTPS"


# ---------------------------------------------------------------------------
# 2. OTP bypass for test email
# ---------------------------------------------------------------------------

class TestOtpBypass:
    def test_bypass_email_accepts_any_otp(self, client):
        """cwchen2000@gmail.com should pass verification with any 6-digit OTP."""
        with patch("app.routers.auth.send_otp_email"):
            client.post("/api/auth/otp/send", json={"email": TEST_BYPASS_EMAIL})

        mock_user = MagicMock()
        mock_user.id = uuid4()
        mock_user.email = TEST_BYPASS_EMAIL
        mock_user.role = "employee"

        with patch("app.routers.auth.get_user_by_email", new_callable=AsyncMock, return_value=mock_user):
            response = client.post(
                "/api/auth/otp/verify",
                json={"email": TEST_BYPASS_EMAIL, "otp": "000000"},
            )

        assert response.status_code == 200
        assert response.json()["is_new_user"] is False
        assert "session" in response.cookies

    def test_bypass_email_accepts_wrong_otp_without_entry(self, client):
        """Bypass works even when no OTP was ever sent (no entry in otp_store)."""
        mock_user = MagicMock()
        mock_user.id = uuid4()
        mock_user.email = TEST_BYPASS_EMAIL
        mock_user.role = "hr"

        with patch("app.routers.auth.get_user_by_email", new_callable=AsyncMock, return_value=mock_user):
            response = client.post(
                "/api/auth/otp/verify",
                json={"email": TEST_BYPASS_EMAIL, "otp": "999999"},
            )

        assert response.status_code == 200

    def test_non_bypass_email_still_validates_otp(self, client):
        """Normal emails must still pass OTP validation."""
        response = client.post(
            "/api/auth/otp/verify",
            json={"email": "normal@example.com", "otp": "000000"},
        )
        assert response.status_code == 400


# ---------------------------------------------------------------------------
# 3 & 4. Query endpoint body parsing (SlowAPI + FastAPI Body() fix)
# ---------------------------------------------------------------------------

class TestQueryBodyParsing:
    def test_query_endpoint_parses_body_not_query_param(self, authed_client):
        """POST /api/query must parse `question` from body, not as a query param.
        Previously broke due to @limiter.limit + from __future__ import annotations.
        """
        mock_result = QueryResult(
            is_out_of_scope=False,
            answer="加班費計算說明",
            warning=None,
            cited_articles=[],
        )
        mock_db = AsyncMock()

        async def mock_get_db():
            yield mock_db

        from app.db.database import get_db
        app.dependency_overrides[get_db] = mock_get_db

        try:
            with patch("app.routers.query.query_law", return_value=mock_result):
                response = authed_client.post("/api/query", json={"question": "加班費怎麼算"})
        finally:
            app.dependency_overrides = {}

        # Must NOT be 422 (body mis-parsed as query param)
        assert response.status_code != 422, f"Got 422 — body param parsed as query param: {response.text}"
        assert response.status_code == 200

    def test_stream_endpoint_parses_body_not_query_param(self, authed_client):
        """POST /api/query/stream must parse `question` from body."""
        mock_db = AsyncMock()

        async def mock_get_db():
            yield mock_db

        from app.db.database import get_db
        app.dependency_overrides[get_db] = mock_get_db

        async def mock_stream(*args, **kwargs):
            yield '{"type": "step", "content": "分析問題"}'

        try:
            with patch("app.routers.query.stream_query_law", return_value=mock_stream()):
                response = authed_client.post("/api/query/stream", json={"question": "加班費怎麼算"})
        finally:
            app.dependency_overrides = {}

        assert response.status_code != 422, f"Got 422 — body param parsed as query param: {response.text}"
        assert response.status_code == 200

    def test_query_rejects_missing_question(self, authed_client):
        """Body without `question` should return 422."""
        response = authed_client.post("/api/query", json={})
        assert response.status_code == 422

    def test_query_rejects_long_question(self, authed_client):
        """Question over 500 chars should return 400."""
        response = authed_client.post("/api/query", json={"question": "a" * 501})
        assert response.status_code == 400


# ---------------------------------------------------------------------------
# 5. Full auth → query flow
# ---------------------------------------------------------------------------

class TestFullAuthQueryFlow:
    @pytest.mark.asyncio
    async def test_login_then_query(self):
        """Simulate: send OTP → verify → query. Cookie must persist between requests."""
        mock_user = MagicMock()
        mock_user.id = uuid4()
        mock_user.email = TEST_BYPASS_EMAIL
        mock_user.role = "employee"

        mock_result = QueryResult(
            is_out_of_scope=False,
            answer="可以申請普通傷病給付。",
            warning=None,
            cited_articles=[],
        )

        mock_db = AsyncMock()

        async def mock_get_db():
            yield mock_db

        from app.db.database import get_db
        app.dependency_overrides[get_db] = mock_get_db

        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                # Step 1: send OTP
                with patch("app.routers.auth.send_otp_email"):
                    r = await client.post("/api/auth/otp/send", json={"email": TEST_BYPASS_EMAIL})
                assert r.status_code == 200

                # Step 2: verify OTP (bypass)
                with patch("app.routers.auth.get_user_by_email", new_callable=AsyncMock, return_value=mock_user):
                    r = await client.post(
                        "/api/auth/otp/verify",
                        json={"email": TEST_BYPASS_EMAIL, "otp": "000000"},
                    )
                assert r.status_code == 200
                assert r.json()["is_new_user"] is False

                session_cookie = r.cookies.get("session")
                assert session_cookie, "Session cookie must be set after login"

                # Step 3: query with session cookie
                with patch("app.routers.query.query_law", return_value=mock_result):
                    r = await client.post(
                        "/api/query",
                        json={"question": "切除子宮可以申請勞保給付嗎"},
                        cookies={"session": session_cookie},
                    )
                assert r.status_code == 200
                assert r.json()["answer"] == "可以申請普通傷病給付。"
        finally:
            app.dependency_overrides = {}
