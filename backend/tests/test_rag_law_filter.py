import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from app.services.rag import query_law


def make_mock_row(article_number="1", similarity=0.9, law_id="N0030001", law_name="勞動基準法"):
    row = MagicMock()
    row.article_number = article_number
    row.title = None
    row.content = "Test content"
    row.similarity = similarity
    row.law_id = law_id
    row.law_name = law_name
    return row


@pytest.mark.asyncio
async def test_query_law_cited_articles_include_law_info():
    mock_db = AsyncMock()
    mock_rows = [make_mock_row(similarity=0.9)]

    with (
        patch("app.services.rag.get_embedder") as mock_embedder,
        patch("app.services.rag._generate_hypothetical_doc", new_callable=AsyncMock, return_value="假設法條"),
        patch("app.services.rag._hybrid_search", return_value=mock_rows),
        patch("app.services.rag._call_claude", new_callable=AsyncMock, return_value="Answer"),
    ):
        mock_embedder.return_value.get_text_embedding.return_value = [0.0] * 1024
        result = await query_law("test question", mock_db)

    assert result.cited_articles[0]["law_id"] == "N0030001"
    assert result.cited_articles[0]["law_name"] == "勞動基準法"


@pytest.mark.asyncio
async def test_query_law_with_law_ids_filter_passes_to_search():
    mock_db = AsyncMock()

    with (
        patch("app.services.rag.get_embedder") as mock_embedder,
        patch("app.services.rag._generate_hypothetical_doc", new_callable=AsyncMock, return_value="假設法條"),
        patch("app.services.rag._hybrid_search", return_value=[]) as mock_search,
    ):
        mock_embedder.return_value.get_text_embedding.return_value = [0.0] * 1024
        await query_law("test", mock_db, law_ids=["N0030001"])

    mock_search.assert_called_once()
    _, call_kwargs = mock_search.call_args
    assert call_kwargs.get("law_ids") == ["N0030001"]


@pytest.mark.asyncio
async def test_query_law_empty_law_ids_searches_all():
    mock_db = AsyncMock()

    with (
        patch("app.services.rag.get_embedder") as mock_embedder,
        patch("app.services.rag._generate_hypothetical_doc", new_callable=AsyncMock, return_value="假設法條"),
        patch("app.services.rag._hybrid_search", return_value=[]) as mock_search,
    ):
        mock_embedder.return_value.get_text_embedding.return_value = [0.0] * 1024
        await query_law("test", mock_db, law_ids=[])

    _, call_kwargs = mock_search.call_args
    assert not call_kwargs.get("law_ids")


@pytest.mark.asyncio
async def test_query_law_none_law_ids_searches_all():
    mock_db = AsyncMock()

    with (
        patch("app.services.rag.get_embedder") as mock_embedder,
        patch("app.services.rag._generate_hypothetical_doc", new_callable=AsyncMock, return_value="假設法條"),
        patch("app.services.rag._hybrid_search", return_value=[]) as mock_search,
    ):
        mock_embedder.return_value.get_text_embedding.return_value = [0.0] * 1024
        await query_law("test", mock_db, law_ids=None)

    _, call_kwargs = mock_search.call_args
    assert call_kwargs.get("law_ids") is None
