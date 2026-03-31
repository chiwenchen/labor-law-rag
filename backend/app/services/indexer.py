from __future__ import annotations
import logging
from dataclasses import dataclass, field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.db.models import LawArticle, SupportedLaw
from app.services.fetcher import LawArticleData
from app.services.embedder import get_embedder

logger = logging.getLogger(__name__)


@dataclass
class IndexResult:
    inserted: int = 0
    updated: int = 0
    skipped: int = 0
    errors: list[str] = field(default_factory=list)


async def upsert_articles(
    articles: list[LawArticleData],
    db: AsyncSession,
    law_id: str,
    law_name: str,
) -> IndexResult:
    """Upsert articles for a single law. Marks removed articles as inactive.
    Updates supported_laws article_count and last_status on completion.
    """
    result = IndexResult()
    embedder = get_embedder()

    # Load existing active articles for THIS law only
    stmt = select(LawArticle).where(
        LawArticle.law_id == law_id,
        LawArticle.is_active == True,
    )
    existing = {
        a.article_number: a
        for a in (await db.execute(stmt)).scalars().all()
    }

    incoming_numbers = {a.article_number for a in articles}

    # Mark obsolete articles (belong to this law, not in new fetch) as inactive
    for number, article in existing.items():
        if number not in incoming_numbers:
            article.is_active = False

    for article_data in articles:
        existing_article = existing.get(article_data.article_number)

        if existing_article and existing_article.content == article_data.content:
            result.skipped += 1
            continue

        try:
            embedding = embedder.get_text_embedding(article_data.content)
        except Exception as e:
            result.errors.append(
                f"Article {article_data.article_number}: embedding failed — {e}"
            )
            continue

        from sqlalchemy import func as sa_func
        search_vec = sa_func.to_tsvector("simple", article_data.content)

        # NOTE: SQLAlchemy ORM requires in-place mutation to track changes.
        # This is an intentional exception to the project's immutability rule.
        if existing_article:
            existing_article.content = article_data.content
            existing_article.embedding = embedding
            existing_article.search_vector = search_vec
            existing_article.version = article_data.version
            existing_article.law_name = law_name
            result.updated += 1
        else:
            db.add(LawArticle(
                law_id=law_id,
                law_name=law_name,
                article_number=article_data.article_number,
                content=article_data.content,
                embedding=embedding,
                search_vector=search_vec,
                version=article_data.version,
                is_active=True,
            ))
            result.inserted += 1

    await db.flush()

    # Update supported_laws with real count
    count = (await db.execute(
        select(func.count()).select_from(LawArticle).where(
            LawArticle.law_id == law_id,
            LawArticle.is_active == True,
        )
    )).scalar()

    supported_law = (await db.execute(
        select(SupportedLaw).where(SupportedLaw.law_id == law_id)
    )).scalar_one_or_none()

    if supported_law:
        supported_law.article_count = count
        supported_law.last_updated = func.now()
        supported_law.last_status = "success"

    await db.flush()
    logger.info(
        f"[{law_id}] +{result.inserted} ~{result.updated} skip={result.skipped} "
        f"err={len(result.errors)} total={count}"
    )
    return result
