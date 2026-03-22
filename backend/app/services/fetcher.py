from dataclasses import dataclass
import re
import httpx

LAW_JSON_URL = (
    "https://raw.githubusercontent.com/kong0107/mojLawSplitJSON"
    "/gh-pages/FalVMingLing/N0030001.json"
)


@dataclass
class LawArticleData:
    article_number: str
    content: str
    version: str


async def fetch_labor_law_articles() -> list[LawArticleData]:
    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
        response = await client.get(LAW_JSON_URL)
        response.raise_for_status()
        data = response.json()

    version = data.get("最新異動日期", "unknown")
    articles = []
    for item in data.get("法規內容", []):
        # Skip chapter headings (編章節), only process articles (條號)
        raw_number = item.get("條號", "").strip()
        content = item.get("條文內容", "").strip()
        if not raw_number or not content:
            continue
        # Normalize: "第 38 條" → "38", "第 30-1 條" → "30-1"
        match = re.search(r"第\s*([\d\-]+)\s*條", raw_number)
        article_number = match.group(1) if match else raw_number
        articles.append(LawArticleData(
            article_number=article_number,
            content=content,
            version=version,
        ))
    return articles
