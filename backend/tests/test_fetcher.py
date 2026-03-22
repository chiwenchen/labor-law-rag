import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from app.services.fetcher import fetch_labor_law_articles, LawArticleData

MOCK_RESPONSE = {
    "最新異動日期": "20240117",
    "法規內容": [
        {
            "條號": "第 38 條",
            "條文內容": "勞工在同一雇主或事業單位，繼續工作滿一定期間者，應依下列規定給予特別休假..."
        }
    ]
}

def _make_mock_response(data: dict) -> MagicMock:
    mock_response = MagicMock()
    mock_response.raise_for_status.return_value = None
    mock_response.json.return_value = data
    return mock_response

@pytest.mark.asyncio
async def test_fetch_returns_list_of_articles():
    with patch("httpx.AsyncClient") as mock_client:
        mock_client.return_value.__aenter__.return_value.get = AsyncMock(
            return_value=_make_mock_response(MOCK_RESPONSE)
        )
        articles = await fetch_labor_law_articles()
    assert len(articles) == 1
    assert articles[0].article_number == "38"
    assert "特別休假" in articles[0].content

@pytest.mark.asyncio
async def test_fetch_skips_non_article_entries():
    """Entries without 條號 (e.g. chapter headings like 編章節) should be excluded."""
    response_data = {
        "最新異動日期": "20240117",
        "法規內容": [
            {"編章節": "第一章 總則"},
            {"條號": "第 1 條", "條文內容": "為規定勞動條件最低標準..."},
        ]
    }
    with patch("httpx.AsyncClient") as mock_client:
        mock_client.return_value.__aenter__.return_value.get = AsyncMock(
            return_value=_make_mock_response(response_data)
        )
        articles = await fetch_labor_law_articles()
    assert len(articles) == 1
    assert articles[0].article_number == "1"
