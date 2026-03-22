import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from app.services.rag import query_law, QueryResult

@pytest.mark.asyncio
async def test_out_of_scope_question_returns_rejection(mock_embedder):
    """Questions with max similarity < 0.5 should be rejected without calling Claude."""
    with patch("app.services.rag.get_embedder", return_value=mock_embedder), \
         patch("app.services.rag._search_articles", return_value=[]):
        result = await query_law("我想跟你聊感情", AsyncMock())

    assert result.is_out_of_scope is True
    assert result.answer is None

@pytest.mark.asyncio
async def test_valid_question_returns_answer(mock_embedder):
    """Valid question should call Claude and return an answer with citations."""
    mock_article = MagicMock()
    mock_article.article_number = "38"
    mock_article.title = "特別休假"
    mock_article.content = "勞工應給予特別休假..."
    mock_article.similarity = 0.92

    with patch("app.services.rag.get_embedder", return_value=mock_embedder), \
         patch("app.services.rag._search_articles", return_value=[mock_article]), \
         patch("app.services.rag._call_claude", return_value="員工滿一年可享有7天特休。"):
        result = await query_law("員工到職一年有幾天特休？", AsyncMock())

    assert result.is_out_of_scope is False
    assert "特休" in result.answer
    assert len(result.cited_articles) == 1
    assert result.cited_articles[0]["article_number"] == "38"

@pytest.mark.asyncio
async def test_low_similarity_adds_warning(mock_embedder):
    """Questions with similarity 0.5-0.75 should get a warning."""
    mock_article = MagicMock()
    mock_article.article_number = "1"
    mock_article.title = None
    mock_article.content = "為規定勞動條件..."
    mock_article.similarity = 0.60

    with patch("app.services.rag.get_embedder", return_value=mock_embedder), \
         patch("app.services.rag._search_articles", return_value=[mock_article]), \
         patch("app.services.rag._call_claude", return_value="相關回覆"):
        result = await query_law("這個問題勉強相關", AsyncMock())

    assert result.warning is not None
    assert result.is_out_of_scope is False
