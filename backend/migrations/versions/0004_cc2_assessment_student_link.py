"""CC-2 follow-up: link assessments to enrolled students (queue/re-identification
must follow the real mapping, not heuristics).

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-15

ROLLBACK NOTE: forward-only per spec; restore from backup to roll back.
"""
from alembic import op
import sqlalchemy as sa

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "school_assessments",
        sa.Column("student_id", sa.Uuid(), sa.ForeignKey("core.students.id", ondelete="SET NULL")),
        schema="diary",
    )


def downgrade() -> None:
    op.execute(sa.text("ALTER TABLE diary.school_assessments DROP COLUMN IF EXISTS student_id"))
