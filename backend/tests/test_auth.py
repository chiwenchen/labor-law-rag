import pytest
from unittest.mock import patch
from fastapi.testclient import TestClient
from app.main import app


@pytest.fixture
def client():
    return TestClient(app, raise_server_exceptions=False)


def test_get_me_without_cookie_returns_401(client):
    """未帶 session cookie 應回 401。"""
    response = client.get("/api/auth/me")
    assert response.status_code == 401


def test_get_me_with_invalid_token_returns_401(client):
    """帶無效的 session token 應回 401。"""
    response = client.get("/api/auth/me", cookies={"session": "invalid-token"})
    assert response.status_code == 401
