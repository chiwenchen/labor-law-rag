from dataclasses import dataclass
import httpx

LAW_API_BASE = "https://law.moj.gov.tw/api/CH/Laws"
LABOR_LAW_PCODE = "C0030001"


@dataclass
class LawArticleData:
    article_number: str
    content: str
    version: str


async def fetch_labor_law_articles() -> list[LawArticleData]:
    url = f"{LAW_API_BASE}/{LABOR_LAW_PCODE}/AllArticles"
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(url)
        await response.raise_for_status()
        data = await response.json()

    version = data.get("LawFetchDate", "unknown")
    articles = []
    for item in data.get("LawArticles", []):
        if item.get("ArticleType") != "A":
            continue
        article_number = item.get("ArticleNo", "").strip()
        content = item.get("ArticleContent", "").strip()
        if article_number and content:
            articles.append(LawArticleData(
                article_number=article_number,
                content=content,
                version=version,
            ))
    return articles
