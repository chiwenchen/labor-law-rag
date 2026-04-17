from __future__ import annotations
from dataclasses import dataclass
import re
import httpx
from app.services.law_registry import BASE_URL


@dataclass
class LawArticleData:
    article_number: str
    content: str
    version: str
    law_id: str
    law_name: str


async def fetch_law(law_id: str, law_name: str) -> list[LawArticleData]:
    """Fetch and parse articles for one law from kong0107/mojLawSplitJSON.

    Returns a list of LawArticleData. Raises httpx.HTTPStatusError if the
    law_id URL returns a non-2xx status (e.g. 404 for unknown law codes).
    Expected duration: < 5 seconds per law.
    """
    url = BASE_URL.format(law_id=law_id)
    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
        response = await client.get(url)
        response.raise_for_status()
        data = response.json()

    actual_name = data.get("法規名稱", "")
    if actual_name and actual_name != law_name:
        raise ValueError(
            f"Law name mismatch for {law_id}: "
            f"expected '{law_name}', got '{actual_name}'"
        )

    version = data.get("最新異動日期", "unknown")
    articles = []
    for item in data.get("法規內容", []):
        raw_number = item.get("條號", "").strip()
        content = item.get("條文內容", "").strip()
        if not raw_number or not content:
            continue
        match = re.search(r"第\s*([\d\-]+)\s*條", raw_number)
        article_number = match.group(1) if match else raw_number
        articles.append(LawArticleData(
            article_number=article_number,
            content=content,
            version=version,
            law_id=law_id,
            law_name=law_name,
        ))
    return articles


async def fetch_labor_law_articles() -> list[LawArticleData]:
    """Backward-compatible wrapper for 勞動基準法."""
    return await fetch_law("N0030001", "勞動基準法")
