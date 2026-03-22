import pytest
from unittest.mock import AsyncMock, patch
from app.services.fetcher import fetch_labor_law_articles, LawArticleData

MOCK_RESPONSE = {
    "LawArticles": [
        {
            "ArticleType": "A",
            "ArticleNo": "38",
            "ArticleContent": "勞工在同一雇主或事業單位，繼續工作滿一定期間者，應依下列規定給予特別休假..."
        }
    ],
    "LawFetchDate": "2024-01-17"
}

@pytest.mark.asyncio
async def test_fetch_returns_list_of_articles():
    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = MOCK_RESPONSE
        articles = await fetch_labor_law_articles()
    assert len(articles) == 1
    assert articles[0].article_number == "38"
    assert "特別休假" in articles[0].content

@pytest.mark.asyncio
async def test_fetch_skips_non_article_entries():
    """Entries with ArticleType != 'A' (e.g. chapter headings) should be excluded."""
    response = {"LawArticles": [
        {"ArticleType": "C", "ArticleNo": "", "ArticleContent": "第一章 總則"},
        {"ArticleType": "A", "ArticleNo": "1", "ArticleContent": "為規定勞動條件最低標準..."},
    ], "LawFetchDate": "2024-01-17"}
    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = response
        articles = await fetch_labor_law_articles()
    assert len(articles) == 1
    assert articles[0].article_number == "1"
