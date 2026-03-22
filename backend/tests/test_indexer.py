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
