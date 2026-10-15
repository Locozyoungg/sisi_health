"""CC-3 fix (Phase 5): corridor.reminders.created_at.

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-15

Migration 0005 created `corridor.reminders` without the `created_at` column
that the mapped model declares; every query on the table failed with
UndefinedColumn. Forward-only fix (the phase is not yet released).

ROLLBACK NOTE: forward-only per spec. Rolling back means dropping the column
and restoring the prior backup.
"""
from alembic import op
import sqlalchemy as sa

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "reminders",
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        schema="corridor",
    )


def downgrade() -> None:
    op.execute(sa.text("ALTER TABLE corridor.reminders DROP COLUMN IF EXISTS created_at"))
