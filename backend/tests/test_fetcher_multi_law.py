import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from app.services.fetcher import fetch_law, fetch_labor_law_articles, LawArticleData

SAMPLE_RESPONSE = {
    "最新異動日期": "20240101",
    "法規內容": [
        {"條號": "第 1 條", "條文內容": "為規定勞動條件最低標準..."},
        {"條號": "第 2 條", "條文內容": "本法用辭定義如左..."},
        {"編章節": "第一章 總則"},  # Should be skipped
    ],
}


@pytest.mark.asyncio
async def test_fetch_law_returns_articles_with_law_id():
    mock_response = MagicMock()
    mock_response.json.return_value = SAMPLE_RESPONSE
    mock_response.raise_for_status = MagicMock()

    with patch("httpx.AsyncClient") as mock_client:
        mock_client.return_value.__aenter__.return_value.get = AsyncMock(
            return_value=mock_response
        )
        articles = await fetch_law("N0030001", "勞動基準法")

    assert len(articles) == 2
    assert all(isinstance(a, LawArticleData) for a in articles)
    assert articles[0].law_id == "N0030001"
    assert articles[0].law_name == "勞動基準法"
    assert articles[0].article_number == "1"
    assert articles[0].version == "20240101"


@pytest.mark.asyncio
async def test_fetch_law_skips_chapter_headings():
    mock_response = MagicMock()
    mock_response.json.return_value = SAMPLE_RESPONSE
    mock_response.raise_for_status = MagicMock()

    with patch("httpx.AsyncClient") as mock_client:
        mock_client.return_value.__aenter__.return_value.get = AsyncMock(
            return_value=mock_response
        )
        articles = await fetch_law("N0030002", "勞工請假規則")

    assert all(a.article_number != "" for a in articles)
    assert len(articles) == 2  # Only the 條 items, not 編章節


@pytest.mark.asyncio
async def test_fetch_labor_law_articles_is_backward_compatible():
    mock_response = MagicMock()
    mock_response.json.return_value = SAMPLE_RESPONSE
    mock_response.raise_for_status = MagicMock()

    with patch("httpx.AsyncClient") as mock_client:
        mock_client.return_value.__aenter__.return_value.get = AsyncMock(
            return_value=mock_response
        )
        articles = await fetch_labor_law_articles()

    assert articles[0].law_id == "N0030001"
    assert articles[0].law_name == "勞動基準法"
