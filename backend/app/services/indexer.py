from dataclasses import dataclass, field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.db.models import LawArticle
from app.services.fetcher import LawArticleData
from app.services.embedder import get_embedder


@dataclass
class IndexResult:
    inserted: int = 0
    updated: int = 0
    skipped: int = 0
    errors: list[str] = field(default_factory=list)


async def upsert_articles(
    articles: list[LawArticleData],
    db: AsyncSession,
) -> IndexResult:
    result = IndexResult()
    embedder = get_embedder()

    # Load all existing articles into a dict keyed by article_number
    stmt = select(LawArticle).where(LawArticle.is_active == True)
    existing = {a.article_number: a for a in (await db.execute(stmt)).scalars().all()}

    incoming_numbers = {a.article_number for a in articles}

    # Mark obsolete articles as inactive
    for number, article in existing.items():
        if number not in incoming_numbers:
            article.is_active = False

    for article_data in articles:
        existing_article = existing.get(article_data.article_number)

        if existing_article and existing_article.content == article_data.content:
            result.skipped += 1
            continue

        embedding = embedder.get_text_embedding(article_data.content)

        if existing_article:
            existing_article.content = article_data.content
            existing_article.embedding = embedding
            existing_article.version = article_data.version
            result.updated += 1
        else:
            new_article = LawArticle(
                article_number=article_data.article_number,
                content=article_data.content,
                embedding=embedding,
                version=article_data.version,
                is_active=True,
            )
            db.add(new_article)
            result.inserted += 1

    await db.commit()
    return result
