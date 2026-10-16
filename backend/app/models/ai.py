"""Phase 6 mapped models: AI conversation layer RAG tables (schema layouts match
migration 0007 / CC-4). `ChunkEmbedding.embedding` is informational only — the
ai service writes embeddings via raw SQL casts (CAST(:emb AS vector|jsonb)) so
one code path serves both the pgvector and the JSONB fallback mode."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.ids import uuid7
from app.core.time import utc_now_naive
from app.models.base import Base


class ContentChunk(Base):
    __tablename__ = "content_chunks"
    __table_args__ = {"schema": "ai"}

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid7)
    chunk_id: Mapped[str] = mapped_column(Text, unique=True)  # f"{slug}#{n}"
    slug: Mapped[str] = mapped_column(Text)
    language: Mapped[str] = mapped_column(String(8))
    audience: Mapped[str] = mapped_column(String(16))
    title: Mapped[str] = mapped_column(Text)
    text: Mapped[str] = mapped_column(Text)
    sources: Mapped[list[Any]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now_naive)


class ChunkEmbedding(Base):
    __tablename__ = "chunk_embeddings"
    __table_args__ = (
        UniqueConstraint("chunk_id", "model", name="uq_chunk_embeddings_chunk_model"),
        {"schema": "ai"},
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid7)
    chunk_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("ai.content_chunks.id", ondelete="CASCADE")
    )
    model: Mapped[str] = mapped_column(String(64))
    dim: Mapped[int] = mapped_column(Integer)
    embedding: Mapped[list[Any]] = mapped_column(JSON)  # raw-SQL writes only (CC-4)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now_naive)
