import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch, MagicMock
from uuid import UUID, uuid4
from fastapi.testclient import TestClient
from app.main import app
from app.auth.store import otp_store, pending_store, session_store, OtpEntry, SessionData


@pytest.fixture(autouse=True)
def clear_stores():
    """每個測試前清空 in-memory stores。"""
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


# ---- GET /api/auth/me ----

def test_get_me_without_cookie_returns_401(client):
    response = client.get("/api/auth/me")
    assert response.status_code == 401


def test_get_me_with_valid_session_returns_user(client):
    token = str(uuid4())
    session_store[token] = SessionData(user_id=uuid4(), email="hr@test.com", role="hr")
    response = client.get("/api/auth/me", cookies={"session": token})
    assert response.status_code == 200
    data = response.json()
    assert data["email"] == "hr@test.com"
    assert data["role"] == "hr"


# ---- POST /api/auth/otp/send ----

def test_otp_send_stores_otp_and_calls_email(client):
    with patch("app.routers.auth.send_otp_email") as mock_send:
        response = client.post("/api/auth/otp/send", json={"email": "user@test.com"})
    assert response.status_code == 200
    assert "user@test.com" in otp_store
    mock_send.assert_called_once()


def test_otp_send_invalid_email_returns_422(client):
    response = client.post("/api/auth/otp/send", json={"email": "not-an-email"})
    assert response.status_code == 422


def test_otp_send_normalizes_gmail_plus_address(client):
    """abc+1@gmail.com 和 abc@gmail.com 應視為同一帳號。"""
    with patch("app.routers.auth.send_otp_email"):
        client.post("/api/auth/otp/send", json={"email": "abc+1@gmail.com"})
    # 正規化後存成 abc@gmail.com
    assert "abc@gmail.com" in otp_store
    assert "abc+1@gmail.com" not in otp_store


# ---- POST /api/auth/otp/verify ----

def test_otp_verify_wrong_otp_returns_400(client):
    otp_store["user@test.com"] = OtpEntry(
        otp="123456",
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=10),
    )
    response = client.post("/api/auth/otp/verify", json={"email": "user@test.com", "otp": "000000"})
    assert response.status_code == 400


def test_otp_verify_expired_otp_returns_400(client):
    otp_store["user@test.com"] = OtpEntry(
        otp="123456",
        expires_at=datetime.now(timezone.utc) - timedelta(minutes=1),
    )
    response = client.post("/api/auth/otp/verify", json={"email": "user@test.com", "otp": "123456"})
    assert response.status_code == 400


def test_otp_verify_new_user_returns_pending_token(client):
    otp_store["new@test.com"] = OtpEntry(
        otp="654321",
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=10),
    )
    with patch("app.routers.auth.get_user_by_email", new_callable=AsyncMock, return_value=None):
        response = client.post("/api/auth/otp/verify", json={"email": "new@test.com", "otp": "654321"})
    assert response.status_code == 200
    data = response.json()
    assert data["is_new_user"] is True
    assert "pending_token" in data


def test_otp_verify_existing_user_sets_cookie(client):
    otp_store["hr@test.com"] = OtpEntry(
        otp="111111",
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=10),
    )
    mock_user = MagicMock()
    mock_user.id = uuid4()
    mock_user.email = "hr@test.com"
    mock_user.role = "hr"
    with patch("app.routers.auth.get_user_by_email", new_callable=AsyncMock, return_value=mock_user):
        response = client.post("/api/auth/otp/verify", json={"email": "hr@test.com", "otp": "111111"})
    assert response.status_code == 200
    assert response.json()["is_new_user"] is False
    assert "session" in response.cookies


# ---- POST /api/auth/register ----

def test_register_invalid_pending_token_returns_400(client):
    response = client.post("/api/auth/register", json={"pending_token": "bad-token", "role": "hr"})
    assert response.status_code == 400


def test_register_invalid_role_returns_422(client):
    token = str(uuid4())
    pending_store[token] = "new@test.com"
    response = client.post("/api/auth/register", json={"pending_token": token, "role": "manager"})
    assert response.status_code == 422


# ---- POST /api/auth/logout ----

def test_logout_clears_session(client):
    token = str(uuid4())
    session_store[token] = SessionData(user_id=uuid4(), email="u@test.com", role="employee")
    response = client.post("/api/auth/logout", cookies={"session": token})
    assert response.status_code == 200
    assert token not in session_store
