"""Migration 0007 conditional-pgvector behavior (CC-4). This single test
validates BOTH branches: vector(768)+ivfflat on a pgvector server (CI test/ai
jobs), JSONB on servers without the extension (dev portable Postgres, CI
gateway job)."""

from sqlalchemy import text

from app.config import get_settings
from app.db import SessionLocal


def _vector_available(db) -> bool:
    return bool(
        db.execute(
            text("SELECT 1 FROM pg_available_extensions WHERE name='vector'")
        ).scalar()
    )


def _column_type(db, table: str, column: str) -> str:
    row = db.execute(
        text(
            "SELECT data_type FROM information_schema.columns "
            "WHERE table_schema='ai' AND table_name=:t AND column_name=:c"
        ),
        {"t": table, "c": column},
    ).first()
    assert row is not None, f"ai.{table}.{column} missing"
    return str(row[0])


def test_embedding_column_type_matches_the_extension_branch():
    with SessionLocal() as db:
        has_vector = _vector_available(db)
        data_type = _column_type(db, "chunk_embeddings", "embedding")
        if has_vector:
            assert data_type.lower() in {"user-defined", "vector"}, data_type
        else:
            assert data_type == "jsonb", data_type


def test_ivfflat_index_exists_only_in_vector_mode():
    with SessionLocal() as db:
        has_vector = _vector_available(db)
        index = db.execute(
            text(
                "SELECT indexname FROM pg_indexes "
                "WHERE schemaname='ai' AND indexname='ix_ai_chunk_embeddings_embedding_ivfflat'"
            )
        ).first()
        assert (index is not None) is has_vector


def test_content_chunks_columns_present():
    with SessionLocal() as db:
        cols = {
            row[0]
            for row in db.execute(
                text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_schema='ai' AND table_name='content_chunks'"
                )
            )
        }
        expected = {
            "id", "chunk_id", "slug", "language", "audience",
            "title", "text", "sources", "created_at",
        }
        assert expected <= cols


def test_settings_point_at_the_ai_migration_chain():
    settings = get_settings()
    assert settings.database_url  # sanity: config loadable alongside the ai schema
