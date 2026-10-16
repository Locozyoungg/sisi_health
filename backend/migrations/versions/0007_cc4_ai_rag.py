"""CC-4 (Phase 6): AI conversation layer RAG tables, conditional pgvector.

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-15

Adds schema `ai`: `content_chunks` (deterministic chunk ids `{slug}#{n}`) and
`chunk_embeddings`. The embedding column is `vector(768)` with an ivfflat cosine
index when the pgvector extension is available on the server, else JSONB
(brute-force cosine in Python). The gate MUST read `pg_available_extensions`:
`CREATE EXTENSION IF EXISTS vector` errors when the extension is unavailable
(IF EXISTS only skips already-installed). CI's test/ai jobs run the
pgvector/pgvector:pg16-alpine image (vector branch); the dev portable Postgres
and the gateway job (plain postgres:16) exercise the JSONB branch.

ROLLBACK NOTE: forward-only per spec. Rolling back means dropping schema `ai`
and restoring the prior backup; embeddings are re-derivable from /ontology.
"""
from alembic import op
import sqlalchemy as sa

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    has_vector = bool(
        bind.execute(
            sa.text("SELECT 1 FROM pg_available_extensions WHERE name='vector'")
        ).scalar()
    )
    op.execute(sa.text("CREATE SCHEMA IF NOT EXISTS ai"))

    op.create_table(
        "content_chunks",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("chunk_id", sa.Text(), nullable=False, unique=True),
        sa.Column("slug", sa.Text(), nullable=False),
        sa.Column("language", sa.String(8), nullable=False),
        sa.Column("audience", sa.String(16), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("sources", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        schema="ai",
    )
    op.create_index(
        "ix_ai_content_chunks_language_slug", "content_chunks", ["language", "slug"], schema="ai"
    )

    if has_vector:
        op.execute(sa.text("CREATE EXTENSION IF NOT EXISTS vector"))
        op.execute(
            sa.text(
                "CREATE TABLE ai.chunk_embeddings ("
                "id uuid PRIMARY KEY, "
                "chunk_id uuid NOT NULL REFERENCES ai.content_chunks(id) ON DELETE CASCADE, "
                "model varchar(64) NOT NULL, "
                "dim integer NOT NULL, "
                "embedding vector(768) NOT NULL, "
                "created_at timestamptz NOT NULL DEFAULT now(), "
                "CONSTRAINT uq_chunk_embeddings_chunk_model UNIQUE (chunk_id, model))"
            )
        )
        op.execute(
            sa.text(
                "CREATE INDEX ix_ai_chunk_embeddings_embedding_ivfflat "
                "ON ai.chunk_embeddings USING ivfflat (embedding vector_cosine_ops) "
                "WITH (lists = 10)"
            )
        )
    else:
        op.create_table(
            "chunk_embeddings",
            sa.Column("id", sa.Uuid(), primary_key=True),
            sa.Column(
                "chunk_id",
                sa.Uuid(),
                sa.ForeignKey("ai.content_chunks.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("model", sa.String(64), nullable=False),
            sa.Column("dim", sa.Integer(), nullable=False),
            sa.Column("embedding", sa.JSON(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.UniqueConstraint("chunk_id", "model", name="uq_chunk_embeddings_chunk_model"),
            schema="ai",
        )


def downgrade() -> None:
    op.execute(sa.text("DROP SCHEMA IF EXISTS ai CASCADE"))
