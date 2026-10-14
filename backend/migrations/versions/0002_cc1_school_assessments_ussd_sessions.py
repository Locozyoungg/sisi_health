"""CC-1 (Phase 3): school assessments + USSD session fallback store.

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-14

ROLLBACK NOTE: forward-only per spec. Rolling back means dropping the two new
tables (assessment ciphertext becomes unreadable once its data key is deleted;
assessments hold no other recoverable value) and restoring the prior backup.
"""
from alembic import op
import sqlalchemy as sa

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "school_assessments",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("phone_hash", sa.String(64), nullable=False),
        sa.Column("age_band", sa.String(8), nullable=False),
        sa.Column("language", sa.String(8), nullable=False),
        sa.Column("consent_state", sa.String(24), nullable=False, server_default="none"),
        # none | self_granted | minor_assent_only | minor_full (guardian+assent)
        sa.Column("payload_ciphertext", sa.LargeBinary(), nullable=False),
        sa.Column("key_id", sa.Uuid(), sa.ForeignKey("core.data_keys.id"), nullable=False),
        sa.Column("channel", sa.String(16), nullable=False),  # ussd | whatsapp
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        schema="diary",
    )
    op.create_index(
        "ix_school_assessments_phone_hash",
        "school_assessments",
        ["phone_hash", "created_at"],
        schema="diary",
    )

    op.create_table(
        "ussd_sessions",
        sa.Column("phone_hash", sa.String(64), primary_key=True),
        sa.Column("state_json", sa.JSON(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        schema="core",
    )


def downgrade() -> None:
    # Forward-only per spec: see ROLLBACK NOTE above.
    op.execute(sa.text("DROP TABLE IF EXISTS diary.school_assessments CASCADE"))
    op.execute(sa.text("DROP TABLE IF EXISTS core.ussd_sessions CASCADE"))
