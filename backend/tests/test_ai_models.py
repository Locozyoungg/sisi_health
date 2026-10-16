"""Phase 6 RAG models (CC-4 / migration 0007): ai schema, unique chunk ids,
FK cascade. Embeddings are written via raw SQL by the ai service; the ORM
mapping is metadata-only."""

from sqlalchemy import text

from app.models import ChunkEmbedding, ContentChunk


def test_ai_tables_live_in_the_ai_schema():
    assert ContentChunk.__table__.schema == "ai"
    assert ChunkEmbedding.__table__.schema == "ai"
    assert ContentChunk.__table__.columns["chunk_id"].unique is True
    constraint = next(
        c
        for c in ChunkEmbedding.__table__.constraints
        if getattr(c, "name", None) == "uq_chunk_embeddings_chunk_model"
    )
    assert constraint is not None


def test_chunk_embeddings_cascade_on_chunk_delete(db):
    from app.core.ids import uuid7

    chunk = ContentChunk(
        id=uuid7(), chunk_id="test-slug#1", slug="test-slug", language="en",
        audience="patient", title="Test", text="Test chunk text.",
    )
    db.add(chunk)
    db.flush()
    db.add(
        ChunkEmbedding(
            id=uuid7(), chunk_id=chunk.id, model="stub", dim=768, embedding=[0.1, 0.2]
        )
    )
    db.flush()
    db.delete(chunk)
    db.flush()
    left = db.execute(
        text("SELECT count(*) FROM ai.chunk_embeddings")
    ).scalar()
    assert left == 0


def test_chunk_id_is_unique(db):
    from app.core.ids import uuid7

    db.add(
        ContentChunk(
            id=uuid7(), chunk_id="dup#1", slug="dup", language="en",
            audience="patient", title="A", text="A",
        )
    )
    db.flush()
    import pytest
    from sqlalchemy.exc import IntegrityError

    db.add(
        ContentChunk(
            id=uuid7(), chunk_id="dup#1", slug="dup", language="en",
            audience="patient", title="B", text="B",
        )
    )
    with pytest.raises(IntegrityError):
        db.flush()
    db.rollback()
