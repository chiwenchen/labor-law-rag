import pytest
from httpx import AsyncClient, ASGITransport
from unittest.mock import AsyncMock, patch, MagicMock
from uuid import uuid4
from app.main import app
from app.auth.store import session_store, SessionData


def _inject_hr_session(client: AsyncClient) -> None:
    token = str(uuid4())
    session_store[token] = SessionData(user_id=uuid4(), email="hr@test.com", role="hr")
    client.cookies.set("session", token)


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
        _inject_hr_session(client)
        response = await client.post("/api/laws/INVALID_CODE/update")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_update_law_valid_id_returns_success():
    import sys
    from types import ModuleType
    from app.main import app
    from app.db.database import get_db

    # IndexResult dataclass — define locally to avoid importing llama_index
    from dataclasses import dataclass, field as dc_field

    @dataclass
    class _IndexResult:
        inserted: int = 0
        updated: int = 0
        skipped: int = 0
        errors: list = dc_field(default_factory=list)

    # Inject stub modules so the router's lazy imports don't trigger llama_index
    mock_upsert = AsyncMock(return_value=_IndexResult(inserted=0, updated=0, skipped=0))
    stub_indexer = ModuleType("app.services.indexer")
    stub_indexer.upsert_articles = mock_upsert
    stub_indexer.IndexResult = _IndexResult

    mock_fetch = AsyncMock(return_value=[])
    stub_fetcher = sys.modules.get("app.services.fetcher")

    mock_db = AsyncMock()
    mock_sl = MagicMock()
    mock_sl.article_count = 98
    mock_db.execute.return_value.scalar_one_or_none = MagicMock(return_value=mock_sl)

    app.dependency_overrides[get_db] = lambda: mock_db
    original_indexer = sys.modules.get("app.services.indexer")
    sys.modules["app.services.indexer"] = stub_indexer
    try:
        with patch("app.services.fetcher.fetch_law", return_value=[]):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                _inject_hr_session(client)
                response = await client.post("/api/laws/N0030001/update")
    finally:
        app.dependency_overrides.clear()
        if original_indexer is None:
            sys.modules.pop("app.services.indexer", None)
        else:
            sys.modules["app.services.indexer"] = original_indexer

    assert response.status_code == 200
    data = response.json()
    assert "status" in data
    assert "article_count" in data
    assert "message" in data


@pytest.mark.asyncio
async def test_update_law_fetch_failure_returns_502():
    import sys
    from types import ModuleType
    from app.main import app
    from app.db.database import get_db
    import httpx

    # Inject stub indexer so the router's lazy import doesn't trigger llama_index
    stub_indexer = ModuleType("app.services.indexer")
    stub_indexer.upsert_articles = AsyncMock()

    mock_db = AsyncMock()
    mock_db.execute.return_value.scalar_one_or_none = MagicMock(return_value=None)

    app.dependency_overrides[get_db] = lambda: mock_db
    original_indexer = sys.modules.get("app.services.indexer")
    sys.modules["app.services.indexer"] = stub_indexer
    try:
        with patch("app.services.fetcher.fetch_law", side_effect=httpx.HTTPStatusError(
            "404", request=MagicMock(), response=MagicMock(status_code=404)
        )):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                _inject_hr_session(client)
                response = await client.post("/api/laws/N0030001/update")
    finally:
        app.dependency_overrides.clear()
        if original_indexer is None:
            sys.modules.pop("app.services.indexer", None)
        else:
            sys.modules["app.services.indexer"] = original_indexer

    assert response.status_code == 502
