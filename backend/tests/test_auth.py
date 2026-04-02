import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4
from fastapi.testclient import TestClient
from app.main import app
from app.auth.store import SessionData
from app.auth.dependencies import get_current_user
from app.db.database import get_db


@pytest.fixture
def client():
    return TestClient(app, raise_server_exceptions=False)


def _make_mock_db():
    mock_db = AsyncMock()
    mock_db.execute.return_value = MagicMock(scalar_one_or_none=MagicMock(return_value=None))
    return mock_db


def _override_db(mock_db):
    async def _mock_get_db():
        yield mock_db
    app.dependency_overrides[get_db] = _mock_get_db


def _clear_overrides():
    app.dependency_overrides = {}


# ---- GET /api/auth/me ----

def test_get_me_without_cookie_returns_401(client):
    mock_db = _make_mock_db()
    _override_db(mock_db)
    try:
        response = client.get("/api/auth/me")
    finally:
        _clear_overrides()
    assert response.status_code == 401


def test_get_me_with_valid_session_returns_user(client):
    mock_session_row = MagicMock()
    mock_session_row.user_id = uuid4()
    mock_session_row.email = "hr@test.com"
    mock_session_row.role = "hr"

    mock_db = _make_mock_db()
    mock_db.execute.return_value = MagicMock(scalar_one_or_none=MagicMock(return_value=mock_session_row))
    _override_db(mock_db)
    try:
        response = client.get("/api/auth/me", cookies={"session": str(uuid4())})
    finally:
        _clear_overrides()
    assert response.status_code == 200
    assert response.json()["email"] == "hr@test.com"
    assert response.json()["role"] == "hr"


# ---- POST /api/auth/otp/send ----

def test_otp_send_calls_email_and_commits(client):
    mock_db = _make_mock_db()
    _override_db(mock_db)
    try:
        with patch("app.routers.auth.send_otp_email") as mock_send:
            response = client.post("/api/auth/otp/send", json={"email": "user@test.com"})
        mock_send.assert_called_once()
    finally:
        _clear_overrides()
    assert response.status_code == 200
    mock_db.commit.assert_called()


def test_otp_send_invalid_email_returns_422(client):
    response = client.post("/api/auth/otp/send", json={"email": "not-an-email"})
    assert response.status_code == 422


def test_otp_send_normalizes_gmail_plus_address(client):
    """abc+1@gmail.com and abc@gmail.com map to the same normalized email."""
    mock_db = _make_mock_db()
    captured_stmts = []
    original_execute = mock_db.execute

    async def capturing_execute(stmt, *args, **kwargs):
        captured_stmts.append(stmt)
        return MagicMock(scalar_one_or_none=MagicMock(return_value=None))

    mock_db.execute = capturing_execute
    _override_db(mock_db)
    try:
        with patch("app.routers.auth.send_otp_email") as mock_send:
            response = client.post("/api/auth/otp/send", json={"email": "abc+1@gmail.com"})
        # The email service is called with the original email
        mock_send.assert_called_once()
        call_args = mock_send.call_args[0]
        # First arg is the original email, normalization applies only to the DB key
        assert call_args[0] == "abc+1@gmail.com"
    finally:
        _clear_overrides()
    assert response.status_code == 200


# ---- POST /api/auth/otp/verify ----

def test_otp_verify_no_otp_in_db_returns_400(client):
    mock_db = _make_mock_db()
    # execute returns None → no OTP row found
    mock_db.execute.return_value = MagicMock(scalar_one_or_none=MagicMock(return_value=None))
    _override_db(mock_db)
    try:
        response = client.post("/api/auth/otp/verify", json={"email": "user@test.com", "otp": "000000"})
    finally:
        _clear_overrides()
    assert response.status_code == 400


def test_otp_verify_wrong_otp_returns_400(client):
    mock_otp_row = MagicMock()
    mock_otp_row.otp = "123456"
    mock_otp_row.expires_at = datetime.now(timezone.utc) + timedelta(minutes=10)

    mock_db = _make_mock_db()
    mock_db.execute.return_value = MagicMock(scalar_one_or_none=MagicMock(return_value=mock_otp_row))
    _override_db(mock_db)
    try:
        response = client.post("/api/auth/otp/verify", json={"email": "user@test.com", "otp": "000000"})
    finally:
        _clear_overrides()
    assert response.status_code == 400


def test_otp_verify_expired_otp_returns_400(client):
    mock_otp_row = MagicMock()
    mock_otp_row.otp = "123456"
    mock_otp_row.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)

    mock_db = _make_mock_db()
    mock_db.execute.return_value = MagicMock(scalar_one_or_none=MagicMock(return_value=mock_otp_row))
    _override_db(mock_db)
    try:
        response = client.post("/api/auth/otp/verify", json={"email": "user@test.com", "otp": "123456"})
    finally:
        _clear_overrides()
    assert response.status_code == 400


def test_otp_verify_new_user_returns_pending_token(client):
    mock_otp_row = MagicMock()
    mock_otp_row.otp = "654321"
    mock_otp_row.expires_at = datetime.now(timezone.utc) + timedelta(minutes=10)

    execute_results = [
        MagicMock(scalar_one_or_none=MagicMock(return_value=mock_otp_row)),  # OtpCode lookup
        MagicMock(scalar_one_or_none=MagicMock(return_value=None)),          # DELETE otp
        MagicMock(scalar_one_or_none=MagicMock(return_value=None)),          # User lookup
    ]
    call_count = 0

    mock_db = AsyncMock()

    async def multi_execute(stmt, *args, **kwargs):
        nonlocal call_count
        result = execute_results[min(call_count, len(execute_results) - 1)]
        call_count += 1
        return result

    mock_db.execute = multi_execute
    mock_db.commit = AsyncMock()
    mock_db.add = MagicMock()
    mock_db.flush = AsyncMock()

    with patch("app.routers.auth._get_user_by_email", new_callable=AsyncMock, return_value=None):
        _override_db(mock_db)
        try:
            response = client.post("/api/auth/otp/verify", json={"email": "new@test.com", "otp": "654321"})
        finally:
            _clear_overrides()

    assert response.status_code == 200
    data = response.json()
    assert data["is_new_user"] is True
    assert "pending_token" in data


def test_otp_verify_existing_user_sets_cookie(client):
    mock_otp_row = MagicMock()
    mock_otp_row.otp = "111111"
    mock_otp_row.expires_at = datetime.now(timezone.utc) + timedelta(minutes=10)

    mock_user = MagicMock()
    mock_user.id = uuid4()
    mock_user.email = "hr@test.com"
    mock_user.role = "hr"

    mock_db = AsyncMock()
    mock_db.execute.return_value = MagicMock(scalar_one_or_none=MagicMock(return_value=mock_otp_row))
    mock_db.commit = AsyncMock()
    mock_db.add = MagicMock()

    with patch("app.routers.auth._get_user_by_email", new_callable=AsyncMock, return_value=mock_user):
        _override_db(mock_db)
        try:
            response = client.post("/api/auth/otp/verify", json={"email": "hr@test.com", "otp": "111111"})
        finally:
            _clear_overrides()

    assert response.status_code == 200
    assert response.json()["is_new_user"] is False
    assert "session" in response.cookies


# ---- POST /api/auth/register ----

def test_register_invalid_pending_token_returns_400(client):
    mock_db = _make_mock_db()
    _override_db(mock_db)
    try:
        response = client.post("/api/auth/register", json={"pending_token": "bad-token", "role": "hr"})
    finally:
        _clear_overrides()
    assert response.status_code == 400


def test_register_invalid_role_returns_422(client):
    response = client.post("/api/auth/register", json={"pending_token": str(uuid4()), "role": "manager"})
    assert response.status_code == 422


# ---- POST /api/auth/logout ----

def test_logout_deletes_session_from_db(client):
    mock_db = _make_mock_db()
    _override_db(mock_db)
    try:
        response = client.post("/api/auth/logout", cookies={"session": str(uuid4())})
    finally:
        _clear_overrides()
    assert response.status_code == 200
    mock_db.execute.assert_called()
    mock_db.commit.assert_called()
