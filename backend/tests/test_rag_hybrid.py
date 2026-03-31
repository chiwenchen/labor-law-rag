"""Tests for HyDE + Hybrid BM25+Vector search components."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from app.services.rag import (
    _build_bm25_query,
    _generate_hypothetical_doc,
    query_law,
)


# ---------------------------------------------------------------------------
# _build_bm25_query — pure function, no mocking needed
# ---------------------------------------------------------------------------

def test_build_bm25_query_basic():
    result = _build_bm25_query("資遣費 加密貨幣")
    assert "資遣費" in result
    assert "加密貨幣" in result
    assert "|" in result  # OR operator


def test_build_bm25_query_strips_punctuation():
    result = _build_bm25_query("安胎假要怎麼請？")
    assert "？" not in result
    assert "安胎假要怎麼請" in result


def test_build_bm25_query_empty_string():
    result = _build_bm25_query("")
    assert result == ""


def test_build_bm25_query_only_punctuation():
    result = _build_bm25_query("？！。，")
    assert result == ""


def test_build_bm25_query_multiple_tokens():
    result = _build_bm25_query("勞動基準法 第22條 工資")
    tokens = [t.strip() for t in result.split("|")]
    assert len(tokens) >= 2


# ---------------------------------------------------------------------------
# _generate_hypothetical_doc — now async, mocks AsyncAnthropic
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_generate_hypothetical_doc_returns_text():
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text="工資之給付應以法定通用貨幣為之...")]

    with patch("app.services.rag.AsyncAnthropic") as mock_anthropic:
        mock_anthropic.return_value.messages.create = AsyncMock(return_value=mock_response)
        result = await _generate_hypothetical_doc("資遣費可以用加密貨幣發嗎")

    assert "法定通用貨幣" in result or len(result) > 0
    # Verify it called Haiku (cheap model)
    call_kwargs = mock_anthropic.return_value.messages.create.call_args[1]
    assert "haiku" in call_kwargs["model"]


@pytest.mark.asyncio
async def test_generate_hypothetical_doc_falls_back_on_error():
    """If Claude API fails, fall back to original question text."""
    with patch("app.services.rag.AsyncAnthropic") as mock_anthropic:
        mock_anthropic.return_value.messages.create = AsyncMock(side_effect=Exception("API error"))
        result = await _generate_hypothetical_doc("資遣費問題")

    assert result == "資遣費問題"  # fallback = original question


# ---------------------------------------------------------------------------
# query_law — HyDE integration: verifies hypothetical doc is used for search
# ---------------------------------------------------------------------------

def make_mock_row(similarity=0.85, article_number="22", law_id="N0030001", law_name="勞動基準法"):
    row = MagicMock()
    row.article_number = article_number
    row.title = None
    row.content = "工資之給付，應以法定通用貨幣為之。"
    row.similarity = similarity
    row.law_id = law_id
    row.law_name = law_name
    return row


@pytest.mark.asyncio
async def test_query_law_uses_hyde_embedding_for_search(mock_embedder):
    """query_law should embed the hypothetical doc (not just the question) for search."""
    hyde_text = "工資之給付應以法定通用貨幣為之，資遣費亦適用此規定。"
    mock_rows = [make_mock_row()]

    with patch("app.services.rag.get_embedder", return_value=mock_embedder), \
         patch("app.services.rag._generate_hypothetical_doc", new_callable=AsyncMock, return_value=hyde_text) as mock_hyde, \
         patch("app.services.rag._hybrid_search", return_value=mock_rows) as mock_search, \
         patch("app.services.rag._call_claude", new_callable=AsyncMock, return_value="不合法"):
        result = await query_law("資遣費可以用加密貨幣發嗎", AsyncMock())

    # HyDE was called
    mock_hyde.assert_called_once_with("資遣費可以用加密貨幣發嗎")
    # Embedder was called twice: once for hyde_text, once for original question
    assert mock_embedder.get_text_embedding.call_count == 2
    calls = [c[0][0] for c in mock_embedder.get_text_embedding.call_args_list]
    assert hyde_text in calls
    assert "資遣費可以用加密貨幣發嗎" in calls
    # Search was called
    mock_search.assert_called_once()


@pytest.mark.asyncio
async def test_query_law_hyde_failure_still_searches(mock_embedder):
    """If HyDE generation fails (falls back to question), search still proceeds."""
    mock_rows = [make_mock_row()]

    with patch("app.services.rag.get_embedder", return_value=mock_embedder), \
         patch("app.services.rag._generate_hypothetical_doc", new_callable=AsyncMock, return_value="資遣費問題"), \
         patch("app.services.rag._hybrid_search", return_value=mock_rows), \
         patch("app.services.rag._call_claude", new_callable=AsyncMock, return_value="回覆"):
        result = await query_law("資遣費問題", AsyncMock())

    assert result.is_out_of_scope is False
    assert result.answer == "回覆"


@pytest.mark.asyncio
async def test_query_law_passes_law_ids_to_hybrid_search(mock_embedder):
    """law_ids filter must be forwarded to _hybrid_search."""
    with patch("app.services.rag.get_embedder", return_value=mock_embedder), \
         patch("app.services.rag._generate_hypothetical_doc", new_callable=AsyncMock, return_value="假設法條"), \
         patch("app.services.rag._hybrid_search", return_value=[]) as mock_search:
        await query_law("測試問題", AsyncMock(), law_ids=["N0030001", "N0030002"])

    _, kwargs = mock_search.call_args
    assert kwargs["law_ids"] == ["N0030001", "N0030002"]


@pytest.mark.asyncio
async def test_query_law_cited_articles_have_no_similarity_for_bm25_only_results(mock_embedder):
    """Articles surfaced purely by BM25 (vscore=0) should still be included."""
    bm25_only_row = make_mock_row(similarity=0.0, article_number="22")  # vscore=0 from BM25
    bm25_only_row.similarity = 0.51  # RRF boosted above threshold

    with patch("app.services.rag.get_embedder", return_value=mock_embedder), \
         patch("app.services.rag._generate_hypothetical_doc", new_callable=AsyncMock, return_value="假設法條"), \
         patch("app.services.rag._hybrid_search", return_value=[bm25_only_row]), \
         patch("app.services.rag._call_claude", new_callable=AsyncMock, return_value="答案"):
        result = await query_law("勞動基準法第22條", AsyncMock())

    assert result.is_out_of_scope is False
    assert result.cited_articles[0]["article_number"] == "22"
