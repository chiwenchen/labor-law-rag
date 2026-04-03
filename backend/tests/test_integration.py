"""
Integration tests covering:

1. Cookie secure flag respects FRONTEND_URL (http → insecure, https → secure)
2. OTP bypass via config-based feature flags (skip_otp_verification, full_auth_emails)
3. Query endpoint body parsing works with @limiter.limit decorator
4. Stream endpoint body parsing works with @limiter.limit decorator
5. Full auth → query flow succeeds end-to-end
"""
from __future__ import annotations

import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from fastapi.testclient import TestClient
from httpx import AsyncClient, ASGITransport

from app.main import app
from app.auth.store import SessionData
from app.auth.dependencies import get_current_user
from app.db.database import get_db
from app.services.rag import QueryResult


DEV_TEST_EMAIL = "devtest@example.com"
FULL_AUTH_EMAIL = "cwchen2000@gmail.com"


def _make_mock_db():
    mock_db = AsyncMock()
    mock_db.execute.return_value = MagicMock(scalar_one_or_none=MagicMock(return_value=None))
    return mock_db


def _override_db(mock_db):
    async def _mock_get_db():
        yield mock_db
    app.dependency_overrides[get_db] = _mock_get_db


def _inject_auth(email="test@example.com", role="employee", access_role="employee"):
    user = SessionData(user_id=uuid4(), email=email, role=role, access_role=access_role)
    app.dependency_overrides[get_current_user] = lambda: user


@pytest.fixture
def client():
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def authed_client(client):
    """TestClient with get_current_user overridden — no DB needed."""
    _inject_auth()
    yield client
    app.dependency_overrides.pop(get_current_user, None)


# ---------------------------------------------------------------------------
# 1. Cookie secure flag
# ---------------------------------------------------------------------------

class TestCookieSecureFlag:
    def test_cookie_is_insecure_for_http_frontend(self, client):
        mock_db = _make_mock_db()
        mock_user = MagicMock()
        mock_user.id = uuid4()
        mock_user.email = DEV_TEST_EMAIL
        mock_user.role = "employee"
        mock_user.access_role = "employee"

        _override_db(mock_db)
        try:
            with patch("app.routers.auth._get_user_by_email", new_callable=AsyncMock, return_value=mock_user):
                with patch("app.routers.auth.settings") as mock_settings:
                    mock_settings.skip_otp_verification = True
                    mock_settings.full_auth_email_list = [FULL_AUTH_EMAIL]
                    mock_settings.frontend_url = "http://localhost:3000"
                    response = client.post(
                        "/api/auth/otp/verify",
                        json={"email": DEV_TEST_EMAIL, "otp": "000000"},
                    )
        finally:
            app.dependency_overrides = {}

        assert response.status_code == 200
        set_cookie = response.headers.get("set-cookie", "")
        assert "session=" in set_cookie
        assert "Secure" not in set_cookie, "Cookie must NOT be Secure over HTTP"

    def test_cookie_is_secure_for_https_frontend(self, client):
        mock_db = _make_mock_db()
        mock_user = MagicMock()
        mock_user.id = uuid4()
        mock_user.email = DEV_TEST_EMAIL
        mock_user.role = "employee"
        mock_user.access_role = "employee"

        _override_db(mock_db)
        try:
            with patch("app.routers.auth._get_user_by_email", new_callable=AsyncMock, return_value=mock_user):
                with patch("app.routers.auth.settings") as mock_settings:
                    mock_settings.skip_otp_verification = True
                    mock_settings.full_auth_email_list = [FULL_AUTH_EMAIL]
                    mock_settings.frontend_url = "https://example.com"
                    response = client.post(
                        "/api/auth/otp/verify",
                        json={"email": DEV_TEST_EMAIL, "otp": "000000"},
                    )
        finally:
            app.dependency_overrides = {}

        assert response.status_code == 200
        set_cookie = response.headers.get("set-cookie", "")
        assert "Secure" in set_cookie, "Cookie must be Secure over HTTPS"


# ---------------------------------------------------------------------------
# 2. OTP bypass for test email
# ---------------------------------------------------------------------------

class TestOtpBypass:
    def test_dev_mode_accepts_any_otp(self, client):
        """When skip_otp_verification=True and email not in full_auth_emails, any OTP works."""
        mock_db = _make_mock_db()
        mock_user = MagicMock()
        mock_user.id = uuid4()
        mock_user.email = DEV_TEST_EMAIL
        mock_user.role = "employee"
        mock_user.access_role = "employee"

        _override_db(mock_db)
        try:
            with patch("app.routers.auth.settings") as mock_settings:
                mock_settings.skip_otp_email = True
                mock_settings.skip_otp_verification = True
                mock_settings.full_auth_email_list = [FULL_AUTH_EMAIL]
                mock_settings.frontend_url = "http://localhost:3000"

                client.post("/api/auth/otp/send", json={"email": DEV_TEST_EMAIL})

                with patch("app.routers.auth._get_user_by_email", new_callable=AsyncMock, return_value=mock_user):
                    response = client.post(
                        "/api/auth/otp/verify",
                        json={"email": DEV_TEST_EMAIL, "otp": "000000"},
                    )
        finally:
            app.dependency_overrides = {}

        assert response.status_code == 200
        assert response.json()["is_new_user"] is False
        assert "session" in response.cookies

    def test_dev_mode_accepts_wrong_otp_without_prior_send(self, client):
        """Dev bypass works even when no OTP was ever sent."""
        mock_db = _make_mock_db()
        mock_user = MagicMock()
        mock_user.id = uuid4()
        mock_user.email = DEV_TEST_EMAIL
        mock_user.role = "hr"
        mock_user.access_role = "employee"

        _override_db(mock_db)
        try:
            with patch("app.routers.auth.settings") as mock_settings, \
                 patch("app.routers.auth._get_user_by_email", new_callable=AsyncMock, return_value=mock_user):
                mock_settings.skip_otp_verification = True
                mock_settings.full_auth_email_list = [FULL_AUTH_EMAIL]
                mock_settings.frontend_url = "http://localhost:3000"
                response = client.post(
                    "/api/auth/otp/verify",
                    json={"email": DEV_TEST_EMAIL, "otp": "999999"},
                )
        finally:
            app.dependency_overrides = {}

        assert response.status_code == 200

    def test_full_auth_email_still_validates_otp(self, client):
        """Emails in full_auth_emails must go through full OTP validation even in dev mode."""
        mock_db = _make_mock_db()
        _override_db(mock_db)
        try:
            with patch("app.routers.auth.settings") as mock_settings:
                mock_settings.skip_otp_verification = True
                mock_settings.full_auth_email_list = [FULL_AUTH_EMAIL]
                mock_settings.frontend_url = "http://localhost:3000"
                response = client.post(
                    "/api/auth/otp/verify",
                    json={"email": FULL_AUTH_EMAIL, "otp": "000000"},
                )
        finally:
            app.dependency_overrides = {}
        assert response.status_code == 400


# ---------------------------------------------------------------------------
# 3 & 4. Query endpoint body parsing
# ---------------------------------------------------------------------------

class TestQueryBodyParsing:
    def test_query_endpoint_parses_body_not_query_param(self, authed_client):
        mock_result = QueryResult(
            is_out_of_scope=False,
            answer="加班費計算說明",
            warning=None,
            cited_articles=[],
        )
        mock_db = _make_mock_db()

        async def mock_get_db():
            yield mock_db

        app.dependency_overrides[get_db] = mock_get_db
        try:
            with patch("app.routers.query.query_law", return_value=mock_result), \
                 patch("app.routers.query.check_and_deduct_credit", new_callable=AsyncMock):
                response = authed_client.post("/api/query", json={"question": "加班費怎麼算"})
        finally:
            app.dependency_overrides.pop(get_db, None)

        assert response.status_code != 422, f"Got 422 — body param parsed as query param: {response.text}"
        assert response.status_code == 200

    def test_stream_endpoint_parses_body_not_query_param(self, authed_client):
        mock_db = _make_mock_db()

        async def mock_get_db():
            yield mock_db

        async def mock_stream(*args, **kwargs):
            yield '{"type": "step", "content": "分析問題"}'

        app.dependency_overrides[get_db] = mock_get_db
        try:
            with patch("app.routers.query.stream_query_law", return_value=mock_stream()), \
                 patch("app.routers.query.check_and_deduct_credit", new_callable=AsyncMock):
                response = authed_client.post("/api/query/stream", json={"question": "加班費怎麼算"})
        finally:
            app.dependency_overrides.pop(get_db, None)

        assert response.status_code != 422, f"Got 422 — body param parsed as query param: {response.text}"
        assert response.status_code == 200

    def test_query_rejects_missing_question(self, authed_client):
        response = authed_client.post("/api/query", json={})
        assert response.status_code == 422

    def test_query_rejects_long_question(self, authed_client):
        response = authed_client.post("/api/query", json={"question": "a" * 501})
        assert response.status_code == 400


# ---------------------------------------------------------------------------
# 5. Full auth → query flow
# ---------------------------------------------------------------------------

class TestFullAuthQueryFlow:
    @pytest.mark.asyncio
    async def test_login_then_query(self):
        """Simulate: verify OTP (dev bypass) → get session cookie → query."""
        mock_user = MagicMock()
        mock_user.id = uuid4()
        mock_user.email = DEV_TEST_EMAIL
        mock_user.role = "employee"
        mock_user.access_role = "employee"

        mock_result = QueryResult(
            is_out_of_scope=False,
            answer="可以申請普通傷病給付。",
            warning=None,
            cited_articles=[],
        )

        mock_db = AsyncMock()
        mock_db.execute.return_value = MagicMock(scalar_one_or_none=MagicMock(return_value=None))
        mock_db.commit = AsyncMock()
        mock_db.add = MagicMock()

        async def mock_get_db():
            yield mock_db

        app.dependency_overrides[get_db] = mock_get_db

        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                with patch("app.routers.auth.settings") as mock_settings:
                    mock_settings.skip_otp_email = True
                    mock_settings.skip_otp_verification = True
                    mock_settings.full_auth_email_list = [FULL_AUTH_EMAIL]
                    mock_settings.frontend_url = "http://localhost:3000"

                    # Step 1: send OTP (skipped in dev mode)
                    r = await client.post("/api/auth/otp/send", json={"email": DEV_TEST_EMAIL})
                    assert r.status_code == 200

                    # Step 2: verify OTP (dev bypass — any code works)
                    with patch("app.routers.auth._get_user_by_email", new_callable=AsyncMock, return_value=mock_user):
                        r = await client.post(
                            "/api/auth/otp/verify",
                            json={"email": DEV_TEST_EMAIL, "otp": "000000"},
                        )
                    assert r.status_code == 200
                    assert r.json()["is_new_user"] is False
                    session_cookie = r.cookies.get("session")
                    assert session_cookie, "Session cookie must be set after login"

                # Step 3: query using the session cookie
                # Override get_current_user so the query step doesn't need DB auth
                app.dependency_overrides[get_current_user] = lambda: SessionData(
                    user_id=mock_user.id, email=mock_user.email, role=mock_user.role, access_role="employee"
                )
                with patch("app.routers.query.query_law", return_value=mock_result), \
                     patch("app.routers.query.check_and_deduct_credit", new_callable=AsyncMock):
                    r = await client.post(
                        "/api/query",
                        json={"question": "切除子宮可以申請勞保給付嗎"},
                        cookies={"session": session_cookie},
                    )
                assert r.status_code == 200
                assert r.json()["answer"] == "可以申請普通傷病給付。"
        finally:
            app.dependency_overrides = {}
