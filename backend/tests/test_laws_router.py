import pytest
from httpx import AsyncClient, ASGITransport
from unittest.mock import AsyncMock, patch, MagicMock
from app.main import app


@pytest.mark.asyncio
async def test_get_laws_returns_list():
    mock_laws = [
        MagicMock(
            law_id="N0030001", law_name="勞動基準法",
            article_count=98, last_updated=None, last_status="success"
        ),
        MagicMock(
            law_id="N0030002", law_name="勞工請假規則",
            article_count=0, last_updated=None, last_status="never_run"
        ),
    ]

    mock_execute_result = MagicMock()
    mock_execute_result.scalars.return_value.all.return_value = mock_laws

    mock_db = AsyncMock()
    mock_db.execute.return_value = mock_execute_result

    async def mock_get_db():
        yield mock_db

    app.dependency_overrides = {}
    from app.db.database import get_db
    app.dependency_overrides[get_db] = mock_get_db

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/api/laws")

    app.dependency_overrides = {}

    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)


@pytest.mark.asyncio
async def test_update_law_invalid_id_returns_404():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post("/api/laws/INVALID_CODE/update")
    assert response.status_code == 404
