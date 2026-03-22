from __future__ import annotations

import pytest
from httpx import AsyncClient, ASGITransport
from unittest.mock import patch, AsyncMock
from app.main import app
from app.services.rag import QueryResult


@pytest.mark.asyncio
async def test_query_endpoint_returns_answer():
    mock_result = QueryResult(
        is_out_of_scope=False,
        answer="員工滿一年可享有7天特休。",
        warning=None,
        cited_articles=[{"article_number": "38", "title": None, "similarity": 0.92}],
    )

    mock_db = AsyncMock()

    async def mock_get_db():
        yield mock_db

    app.dependency_overrides = {}
    from app.db.database import get_db
    app.dependency_overrides[get_db] = mock_get_db

    with patch("app.routers.query.query_law", return_value=mock_result):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post("/api/query", json={"question": "員工到職一年有幾天特休？"})

    app.dependency_overrides = {}

    assert response.status_code == 200
    data = response.json()
    assert data["answer"] == "員工滿一年可享有7天特休。"
    assert len(data["cited_articles"]) == 1


@pytest.mark.asyncio
async def test_query_endpoint_rejects_long_input():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/api/query", json={"question": "a" * 501})
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_query_endpoint_returns_out_of_scope():
    mock_result = QueryResult(is_out_of_scope=True, answer=None, warning=None, cited_articles=[])

    mock_db = AsyncMock()

    async def mock_get_db():
        yield mock_db

    app.dependency_overrides = {}
    from app.db.database import get_db
    app.dependency_overrides[get_db] = mock_get_db

    with patch("app.routers.query.query_law", return_value=mock_result):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post("/api/query", json={"question": "我想聊感情"})

    app.dependency_overrides = {}

    assert response.status_code == 200
    assert response.json()["is_out_of_scope"] is True


@pytest.mark.asyncio
async def test_law_status_endpoint():
    from unittest.mock import MagicMock

    mock_db = AsyncMock()

    # Mock execute to return a synchronous result object (since await db.execute() resolves the coroutine)
    mock_execute_result = MagicMock()
    mock_execute_result.scalar_one_or_none.return_value = None
    mock_execute_result.scalar.return_value = 0
    mock_db.execute.return_value = mock_execute_result

    async def mock_get_db():
        yield mock_db

    app.dependency_overrides = {}
    from app.db.database import get_db
    app.dependency_overrides[get_db] = mock_get_db

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/law/status")

    app.dependency_overrides = {}

    assert response.status_code == 200
    assert "last_updated" in response.json()
