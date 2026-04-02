"""Tests for stream_query_law and _extract_cited_article_numbers in app.services.rag."""
from __future__ import annotations

import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from app.services.rag import _extract_cited_article_numbers, stream_query_law


# ---------------------------------------------------------------------------
# _extract_cited_article_numbers
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_extract_cited_returns_empty_for_empty_candidates():
    result = await _extract_cited_article_numbers("任何回答", [])
    assert result == []


@pytest.mark.asyncio
async def test_extract_cited_filters_to_mentioned_articles():
    candidates = [
        {"article_number": "38"},
        {"article_number": "39"},
        {"article_number": "40"},
    ]
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text='["38", "40"]')]

    with patch("app.services.rag.AsyncAnthropic") as MockClient:
        instance = MockClient.return_value
        instance.messages.create = AsyncMock(return_value=mock_response)
        result = await _extract_cited_article_numbers("依第38條及第40條規定", candidates)

    assert result == ["38", "40"]


@pytest.mark.asyncio
async def test_extract_cited_falls_back_to_all_on_api_error():
    candidates = [
        {"article_number": "10"},
        {"article_number": "11"},
    ]

    with patch("app.services.rag.AsyncAnthropic") as MockClient:
        instance = MockClient.return_value
        instance.messages.create = AsyncMock(side_effect=Exception("API error"))
        result = await _extract_cited_article_numbers("回答內容", candidates)

    assert result == ["10", "11"]


@pytest.mark.asyncio
async def test_extract_cited_falls_back_on_invalid_json():
    candidates = [{"article_number": "5"}]
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text="not json")]

    with patch("app.services.rag.AsyncAnthropic") as MockClient:
        instance = MockClient.return_value
        instance.messages.create = AsyncMock(return_value=mock_response)
        result = await _extract_cited_article_numbers("回答", candidates)

    assert result == ["5"]


@pytest.mark.asyncio
async def test_extract_cited_falls_back_on_empty_array():
    """When Haiku returns [], fallback returns all candidates."""
    candidates = [{"article_number": "1"}, {"article_number": "2"}]
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text="[]")]

    with patch("app.services.rag.AsyncAnthropic") as MockClient:
        instance = MockClient.return_value
        instance.messages.create = AsyncMock(return_value=mock_response)
        result = await _extract_cited_article_numbers("回答", candidates)

    # Empty array → the `if isinstance(result, list) and result` is false → falls back
    assert result == ["1", "2"]


# ---------------------------------------------------------------------------
# stream_query_law
# ---------------------------------------------------------------------------

def _make_article_row(article_number="38", similarity=0.9, law_id="N0030001",
                      law_name="勞動基準法", title=None, content="法條內容"):
    row = MagicMock()
    row.article_number = article_number
    row.similarity = similarity
    row.law_id = law_id
    row.law_name = law_name
    row.title = title
    row.content = content
    return row


@pytest.mark.asyncio
async def test_stream_yields_out_of_scope_when_no_articles(mock_embedder):
    mock_db = AsyncMock()

    with patch("app.services.rag.get_embedder", return_value=mock_embedder), \
         patch("app.services.rag._generate_hypothetical_doc", new_callable=AsyncMock, return_value="假設文件"), \
         patch("app.services.rag._hybrid_search", new_callable=AsyncMock, return_value=[]):

        events = []
        async for event in stream_query_law("不相關的問題", mock_db):
            events.append(event)

    types = [e["type"] for e in events]
    assert "out_of_scope" in types


@pytest.mark.asyncio
async def test_stream_yields_out_of_scope_when_low_similarity(mock_embedder):
    low_sim_article = _make_article_row(similarity=0.3)
    mock_db = AsyncMock()

    with patch("app.services.rag.get_embedder", return_value=mock_embedder), \
         patch("app.services.rag._generate_hypothetical_doc", new_callable=AsyncMock, return_value="假設文件"), \
         patch("app.services.rag._hybrid_search", new_callable=AsyncMock, return_value=[low_sim_article]):

        events = []
        async for event in stream_query_law("問題", mock_db):
            events.append(event)

    types = [e["type"] for e in events]
    assert "out_of_scope" in types


@pytest.mark.asyncio
async def test_stream_yields_steps_tokens_and_done(mock_embedder):
    articles = [_make_article_row(similarity=0.9)]
    mock_db = AsyncMock()

    # Mock the streaming Claude response
    mock_stream_ctx = AsyncMock()

    async def fake_text_stream():
        yield "第一段"
        yield "第二段"

    mock_stream_ctx.text_stream = fake_text_stream()

    # Create async context manager
    mock_stream_cm = MagicMock()
    mock_stream_cm.__aenter__ = AsyncMock(return_value=mock_stream_ctx)
    mock_stream_cm.__aexit__ = AsyncMock(return_value=False)

    with patch("app.services.rag.get_embedder", return_value=mock_embedder), \
         patch("app.services.rag._generate_hypothetical_doc", new_callable=AsyncMock, return_value="假設文件"), \
         patch("app.services.rag._hybrid_search", new_callable=AsyncMock, return_value=articles), \
         patch("app.services.rag.AsyncAnthropic") as MockClient, \
         patch("app.services.rag._extract_cited_article_numbers", new_callable=AsyncMock, return_value=["38"]):

        instance = MockClient.return_value
        instance.messages.stream.return_value = mock_stream_cm

        events = []
        async for event in stream_query_law("加班費怎麼算", mock_db):
            events.append(event)

    types = [e["type"] for e in events]
    assert "step" in types
    assert "token" in types
    assert "done" in types

    done_event = [e for e in events if e["type"] == "done"][0]
    assert "cited_articles" in done_event
    assert done_event["answer"] == "第一段第二段"


@pytest.mark.asyncio
async def test_stream_yields_warning_for_low_similarity(mock_embedder):
    articles = [_make_article_row(similarity=0.55)]
    mock_db = AsyncMock()

    mock_stream_ctx = AsyncMock()

    async def fake_text_stream():
        yield "回答"

    mock_stream_ctx.text_stream = fake_text_stream()
    mock_stream_cm = MagicMock()
    mock_stream_cm.__aenter__ = AsyncMock(return_value=mock_stream_ctx)
    mock_stream_cm.__aexit__ = AsyncMock(return_value=False)

    with patch("app.services.rag.get_embedder", return_value=mock_embedder), \
         patch("app.services.rag._generate_hypothetical_doc", new_callable=AsyncMock, return_value="假設"), \
         patch("app.services.rag._hybrid_search", new_callable=AsyncMock, return_value=articles), \
         patch("app.services.rag.AsyncAnthropic") as MockClient, \
         patch("app.services.rag._extract_cited_article_numbers", new_callable=AsyncMock, return_value=["38"]):

        instance = MockClient.return_value
        instance.messages.stream.return_value = mock_stream_cm

        events = []
        async for event in stream_query_law("問題", mock_db):
            events.append(event)

    done_event = [e for e in events if e["type"] == "done"][0]
    assert done_event["warning"] is not None


@pytest.mark.asyncio
async def test_stream_yields_error_on_api_failure(mock_embedder):
    articles = [_make_article_row(similarity=0.9)]
    mock_db = AsyncMock()

    mock_stream_cm = MagicMock()
    mock_stream_cm.__aenter__ = AsyncMock(side_effect=Exception("connection failed"))
    mock_stream_cm.__aexit__ = AsyncMock(return_value=False)

    with patch("app.services.rag.get_embedder", return_value=mock_embedder), \
         patch("app.services.rag._generate_hypothetical_doc", new_callable=AsyncMock, return_value="假設"), \
         patch("app.services.rag._hybrid_search", new_callable=AsyncMock, return_value=articles), \
         patch("app.services.rag.AsyncAnthropic") as MockClient:

        instance = MockClient.return_value
        instance.messages.stream.return_value = mock_stream_cm

        events = []
        async for event in stream_query_law("問題", mock_db):
            events.append(event)

    types = [e["type"] for e in events]
    assert "error" in types


@pytest.mark.asyncio
async def test_stream_with_history_yields_rewrite_step(mock_embedder):
    articles = [_make_article_row(similarity=0.9)]
    mock_db = AsyncMock()

    mock_stream_ctx = AsyncMock()

    async def fake_text_stream():
        yield "回答"

    mock_stream_ctx.text_stream = fake_text_stream()
    mock_stream_cm = MagicMock()
    mock_stream_cm.__aenter__ = AsyncMock(return_value=mock_stream_ctx)
    mock_stream_cm.__aexit__ = AsyncMock(return_value=False)

    history = [
        {"role": "user", "content": "什麼是特休"},
        {"role": "assistant", "content": "特休是..."},
    ]

    with patch("app.services.rag.get_embedder", return_value=mock_embedder), \
         patch("app.services.rag._generate_hypothetical_doc", new_callable=AsyncMock, return_value="假設"), \
         patch("app.services.rag._rewrite_question", new_callable=AsyncMock, return_value="改寫後的問題"), \
         patch("app.services.rag._hybrid_search", new_callable=AsyncMock, return_value=articles), \
         patch("app.services.rag.AsyncAnthropic") as MockClient, \
         patch("app.services.rag._extract_cited_article_numbers", new_callable=AsyncMock, return_value=["38"]):

        instance = MockClient.return_value
        instance.messages.stream.return_value = mock_stream_cm

        events = []
        async for event in stream_query_law("那幾天", mock_db, history=history):
            events.append(event)

    step_events = [e for e in events if e["type"] == "step"]
    step_names = [e["step"] for e in step_events]
    assert "rewrite" in step_names
