"""CC-4 fix (Phase 6): ai.chunk_embeddings.embedding json -> jsonb.

Revision ID: 0008
Revises: 0007
Create Date: 2026-10-15

Migration 0007's JSONB fallback branch used SQLAlchemy's generic JSON type,
which materializes as Postgres `json`; the documented fallback type is `jsonb`
(binary storage, faster brute-force reads). Forward-only fix (the phase is not
yet released).

ROLLBACK NOTE: forward-only per spec. Rolling back means altering the column
back to json and restoring the prior backup.
"""
from alembic import op
import sqlalchemy as sa

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Conditional like 0007: the JSONB fallback branch of 0007 materializes as
    # Postgres `json` (SQLAlchemy generic JSON); the pgvector branch is
    # vector(768) with no cast to jsonb and an ivfflat index — it must be
    # skipped untouched.
    bind = op.get_bind()
    row = bind.execute(
        sa.text(
            "SELECT data_type FROM information_schema.columns "
            "WHERE table_schema='ai' AND table_name='chunk_embeddings' "
            "AND column_name='embedding'"
        )
    ).first()
    if row is not None and row[0] == "json":
        op.execute(
            sa.text(
                "ALTER TABLE ai.chunk_embeddings "
                "ALTER COLUMN embedding TYPE jsonb USING embedding::jsonb"
            )
        )


def downgrade() -> None:
    op.execute(
        sa.text(
            "ALTER TABLE ai.chunk_embeddings "
            "ALTER COLUMN embedding TYPE json USING embedding::json"
        )
    )
