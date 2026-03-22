import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from app.services.indexer import upsert_articles, IndexResult
from app.services.fetcher import LawArticleData

SAMPLE_ARTICLES = [
    LawArticleData(article_number="1", content="為規定勞動條件最低標準...", version="2024-01-17"),
    LawArticleData(article_number="38", content="勞工應給予特別休假...", version="2024-01-17"),
]

@pytest.mark.asyncio
async def test_upsert_new_articles_inserts_all(mock_embedder):
    """When DB is empty, all articles should be inserted."""
    execute_result = MagicMock()
    execute_result.scalars.return_value.all.return_value = []

    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(return_value=execute_result)

    with patch("app.services.indexer.get_embedder", return_value=mock_embedder):
        result = await upsert_articles(SAMPLE_ARTICLES, mock_db)

    assert result.inserted == 2
    assert result.updated == 0
    assert result.skipped == 0

@pytest.mark.asyncio
async def test_upsert_unchanged_articles_skips(mock_embedder):
    """Articles with unchanged content should be skipped."""
    from app.db.models import LawArticle
    existing = MagicMock(spec=LawArticle)
    existing.article_number = "38"
    existing.content = "勞工應給予特別休假..."

    execute_result = MagicMock()
    execute_result.scalars.return_value.all.return_value = [existing]

    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(return_value=execute_result)

    with patch("app.services.indexer.get_embedder", return_value=mock_embedder):
        result = await upsert_articles(
            [LawArticleData("38", "勞工應給予特別休假...", "2024-01-17")],
            mock_db
        )

    assert result.skipped == 1
    assert result.updated == 0

@pytest.mark.asyncio
async def test_upsert_changed_articles_updates(mock_embedder):
    """Articles with changed content should be updated with new embedding."""
    from app.db.models import LawArticle
    existing = MagicMock(spec=LawArticle)
    existing.article_number = "38"
    existing.content = "舊版本內容"

    execute_result = MagicMock()
    execute_result.scalars.return_value.all.return_value = [existing]
    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(return_value=execute_result)

    with patch("app.services.indexer.get_embedder", return_value=mock_embedder):
        result = await upsert_articles(
            [LawArticleData("38", "新版本內容", "2024-01-17")],
            mock_db
        )

    assert result.updated == 1
    assert result.inserted == 0
    assert result.skipped == 0
    assert existing.content == "新版本內容"

@pytest.mark.asyncio
async def test_upsert_marks_obsolete_articles_inactive(mock_embedder):
    """Articles in DB but not in incoming list should be marked is_active=False."""
    from app.db.models import LawArticle
    obsolete = MagicMock(spec=LawArticle)
    obsolete.article_number = "99"
    obsolete.content = "舊廢止法條"
    obsolete.is_active = True

    execute_result = MagicMock()
    execute_result.scalars.return_value.all.return_value = [obsolete]
    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(return_value=execute_result)

    with patch("app.services.indexer.get_embedder", return_value=mock_embedder):
        # Pass empty incoming list — all existing become obsolete
        result = await upsert_articles([], mock_db)

    assert obsolete.is_active is False

@pytest.mark.asyncio
async def test_upsert_records_embedding_error(mock_embedder):
    """If embedding fails for an article, it should be recorded in errors, not crash."""
    mock_embedder.get_text_embedding.side_effect = RuntimeError("model error")

    execute_result = MagicMock()
    execute_result.scalars.return_value.all.return_value = []
    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(return_value=execute_result)

    with patch("app.services.indexer.get_embedder", return_value=mock_embedder):
        result = await upsert_articles(
            [LawArticleData("1", "為規定勞動條件...", "2024-01-17")],
            mock_db
        )

    assert result.inserted == 0
    assert len(result.errors) == 1
    assert "1" in result.errors[0]
