"""Tests for GET /api/articles/{article_number} and POST /api/law/trigger-update."""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.db.database import get_db


def _override_db(mock_db):
    async def _mock_get_db():
        yield mock_db
    app.dependency_overrides[get_db] = _mock_get_db


# ---------------------------------------------------------------------------
# GET /api/articles/{article_number}
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_article_returns_article():
    mock_article = MagicMock()
    mock_article.article_number = "38"
    mock_article.title = "特別休假"
    mock_article.content = "勞工在同一雇主或事業單位..."
    mock_article.last_updated = None
    mock_article.version = "20240101"
    mock_article.law_id = "N0030001"
    mock_article.law_name = "勞動基準法"

    mock_db = AsyncMock()
    mock_db.execute.return_value = MagicMock(scalar_one_or_none=MagicMock(return_value=mock_article))

    _override_db(mock_db)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/api/articles/38")
    finally:
        app.dependency_overrides = {}

    assert response.status_code == 200
    data = response.json()
    assert data["article_number"] == "38"
    assert data["law_name"] == "勞動基準法"
    assert data["content"] == "勞工在同一雇主或事業單位..."


@pytest.mark.asyncio
async def test_get_article_not_found_returns_404():
    mock_db = AsyncMock()
    mock_db.execute.return_value = MagicMock(scalar_one_or_none=MagicMock(return_value=None))

    _override_db(mock_db)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/api/articles/999")
    finally:
        app.dependency_overrides = {}

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_article_with_valid_law_id_filter():
    mock_article = MagicMock()
    mock_article.article_number = "38"
    mock_article.title = None
    mock_article.content = "內容"
    mock_article.last_updated = None
    mock_article.version = None
    mock_article.law_id = "N0030001"
    mock_article.law_name = "勞動基準法"

    mock_db = AsyncMock()
    mock_db.execute.return_value = MagicMock(scalar_one_or_none=MagicMock(return_value=mock_article))

    _override_db(mock_db)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/api/articles/38?law_id=N0030001")
    finally:
        app.dependency_overrides = {}

    assert response.status_code == 200


@pytest.mark.asyncio
async def test_get_article_with_invalid_law_id_returns_404():
    mock_db = AsyncMock()
    _override_db(mock_db)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/api/articles/38?law_id=INVALID")
    finally:
        app.dependency_overrides = {}

    assert response.status_code == 404


# ---------------------------------------------------------------------------
# POST /api/law/trigger-update
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_trigger_update_returns_accepted():
    with patch("app.routers.articles._update_lock") as mock_lock:
        mock_lock.locked.return_value = False
        mock_lock.__aenter__ = AsyncMock()
        mock_lock.__aexit__ = AsyncMock()
        with patch("app.services.scheduler.run_law_update", new_callable=AsyncMock):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.post("/api/law/trigger-update")

    assert response.status_code == 200
    assert "觸發" in response.json()["message"]


@pytest.mark.asyncio
async def test_trigger_update_returns_409_when_locked():
    # Reset slowapi rate-limiter storage so previous test doesn't cause 429
    from app.limiter import limiter as app_limiter
    app_limiter.reset()

    with patch("app.routers.articles._update_lock") as mock_lock:
        mock_lock.locked.return_value = True
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post("/api/law/trigger-update")

    assert response.status_code == 409
