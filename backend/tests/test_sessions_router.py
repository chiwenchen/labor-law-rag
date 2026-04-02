"""Tests for GET /api/sessions and GET /api/sessions/{id}/history."""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4
from datetime import datetime, timezone
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.auth.store import SessionData
from app.auth.dependencies import get_current_user
from app.db.database import get_db


def _inject_auth(user_id=None, email="test@example.com", role="employee"):
    uid = user_id or uuid4()
    user = SessionData(user_id=uid, email=email, role=role)
    app.dependency_overrides[get_current_user] = lambda: user
    return uid


def _override_db(mock_db):
    async def _mock_get_db():
        yield mock_db
    app.dependency_overrides[get_db] = _mock_get_db


# ---------------------------------------------------------------------------
# GET /api/sessions
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_list_sessions_returns_empty_list():
    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    mock_db.execute.return_value = mock_result

    _inject_auth()
    _override_db(mock_db)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/api/sessions")
    finally:
        app.dependency_overrides = {}

    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.asyncio
async def test_list_sessions_returns_session_objects():
    session_id = uuid4()
    now = datetime.now(timezone.utc)

    mock_session = MagicMock()
    mock_session.id = session_id
    mock_session.title = "加班費問題"
    mock_session.created_at = now

    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [mock_session]
    mock_db = AsyncMock()
    mock_db.execute.return_value = mock_result

    _inject_auth()
    _override_db(mock_db)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/api/sessions")
    finally:
        app.dependency_overrides = {}

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["id"] == str(session_id)
    assert data[0]["title"] == "加班費問題"


@pytest.mark.asyncio
async def test_list_sessions_requires_auth():
    mock_db = AsyncMock()
    _override_db(mock_db)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/api/sessions")
    finally:
        app.dependency_overrides = {}

    assert response.status_code == 401


# ---------------------------------------------------------------------------
# GET /api/sessions/{session_id}/history
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_session_history_returns_entries():
    user_id = uuid4()
    session_id = uuid4()

    mock_session = MagicMock()
    mock_session.id = session_id

    mock_history = MagicMock()
    mock_history.id = 1
    mock_history.question = "特休幾天"
    mock_history.answer = "7天"
    mock_history.cited_articles = [{"article_number": "38"}]
    mock_history.max_similarity_score = 0.92
    mock_history.created_at = datetime.now(timezone.utc)

    call_count = 0
    mock_db = AsyncMock()

    def make_execute_result(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            # Session lookup
            return MagicMock(scalar_one_or_none=MagicMock(return_value=mock_session))
        else:
            # History query
            result = MagicMock()
            result.scalars.return_value.all.return_value = [mock_history]
            return result

    mock_db.execute = AsyncMock(side_effect=make_execute_result)

    _inject_auth(user_id=user_id)
    _override_db(mock_db)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get(f"/api/sessions/{session_id}/history")
    finally:
        app.dependency_overrides = {}

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["question"] == "特休幾天"
    assert data[0]["answer"] == "7天"


@pytest.mark.asyncio
async def test_get_session_history_invalid_uuid_returns_400():
    _inject_auth()
    mock_db = AsyncMock()
    _override_db(mock_db)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/api/sessions/not-a-uuid/history")
    finally:
        app.dependency_overrides = {}

    assert response.status_code == 400


@pytest.mark.asyncio
async def test_get_session_history_not_found_returns_404():
    mock_db = AsyncMock()
    mock_db.execute.return_value = MagicMock(scalar_one_or_none=MagicMock(return_value=None))

    _inject_auth()
    _override_db(mock_db)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get(f"/api/sessions/{uuid4()}/history")
    finally:
        app.dependency_overrides = {}

    assert response.status_code == 404
