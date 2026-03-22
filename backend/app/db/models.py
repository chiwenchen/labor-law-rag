import uuid
from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.sql import func
from pgvector.sqlalchemy import Vector


class Base(DeclarativeBase):
    pass


class Session(Base):
    __tablename__ = "sessions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title = Column(String(100), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class LawArticle(Base):
    __tablename__ = "law_articles"
    __table_args__ = (
        UniqueConstraint("law_id", "article_number", name="law_articles_law_id_article_number_key"),
    )

    id = Column(Integer, primary_key=True)
    law_id = Column(String(20), nullable=False, default="N0030001")
    law_name = Column(String(100), nullable=False, default="勞動基準法")
    article_number = Column(String(20), nullable=False)
    title = Column(String(200))
    content = Column(Text, nullable=False)
    embedding = Column(Vector(1024))
    is_active = Column(Boolean, default=True)
    last_updated = Column(DateTime(timezone=True))
    version = Column(String(50))


class SupportedLaw(Base):
    __tablename__ = "supported_laws"

    law_id = Column(String(20), primary_key=True)
    law_name = Column(String(100), nullable=False)
    article_count = Column(Integer, nullable=False, default=0)
    last_updated = Column(DateTime(timezone=True))
    last_status = Column(String(20), nullable=False, default="never_run")


class QueryHistory(Base):
    __tablename__ = "query_history"

    id = Column(Integer, primary_key=True)
    session_id = Column(UUID(as_uuid=True), ForeignKey("sessions.id", ondelete="CASCADE"))
    question = Column(Text, nullable=False)
    answer = Column(Text)
    cited_articles = Column(JSONB)
    max_similarity_score = Column(Float)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class LawUpdateLog(Base):
    __tablename__ = "law_update_logs"

    id = Column(Integer, primary_key=True)
    law_id = Column(String(20), nullable=False, default="N0030001")
    updated_at = Column(DateTime(timezone=True), server_default=func.now())
    articles_changed = Column(Integer, default=0)
    status = Column(String(20), nullable=False)
    error_message = Column(Text)
