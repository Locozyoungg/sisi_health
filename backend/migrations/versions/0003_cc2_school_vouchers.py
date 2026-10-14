"""CC-2 (Phase 4): school module, vouchers, re-identification support.

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-15

ROLLBACK NOTE: forward-only per spec. Rolling back means dropping the new
tables (encrypted contact maps become unreadable once their data keys are
deleted) and restoring the prior backup.
"""
from alembic import op
import sqlalchemy as sa

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(sa.text("CREATE SCHEMA IF NOT EXISTS school"))
    # ---- core ---------------------------------------------------------------
    op.create_table(
        "schools",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("county", sa.String(128)),
        sa.Column("status", sa.String(16), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        schema="core",
    )
    op.create_table(
        "school_staff",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("staff_id", sa.Uuid(), sa.ForeignKey("core.staff_users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("school_id", sa.Uuid(), sa.ForeignKey("core.schools.id", ondelete="CASCADE"), nullable=False),
        sa.Column("role_within", sa.String(16), nullable=False),  # nurse | school_admin
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("staff_id", "school_id", name="uq_school_staff_staff_school"),
        schema="core",
    )
    op.create_table(
        "students",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("school_id", sa.Uuid(), sa.ForeignKey("core.schools.id", ondelete="CASCADE"), nullable=False),
        sa.Column("pseudonym_id", sa.Uuid(), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        schema="core",
    )
    op.create_table(
        "student_contact_map",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("student_id", sa.Uuid(), sa.ForeignKey("core.students.id", ondelete="CASCADE"), nullable=False),
        sa.Column("payload_ciphertext", sa.LargeBinary(), nullable=False),
        sa.Column("key_id", sa.Uuid(), sa.ForeignKey("core.data_keys.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        schema="core",
    )
    op.create_table(
        "guardians",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("student_id", sa.Uuid(), sa.ForeignKey("core.students.id", ondelete="CASCADE"), nullable=False),
        sa.Column("contact_ciphertext", sa.LargeBinary(), nullable=False),
        sa.Column("key_id", sa.Uuid(), sa.ForeignKey("core.data_keys.id"), nullable=False),
        sa.Column("alert_consent", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        schema="core",
    )
    op.create_table(
        "pharmacies",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("location", sa.String(255)),
        sa.Column("verified", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("last_verified_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        schema="core",
    )

    # ---- school --------------------------------------------------------------
    op.create_table(
        "assessment_actions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("assessment_id", sa.Uuid(), sa.ForeignKey("diary.school_assessments.id", ondelete="CASCADE"), nullable=False),
        sa.Column("action", sa.String(24), nullable=False),  # spoke_to | referred | escalated | contacted
        sa.Column("actor_id", sa.Uuid(), sa.ForeignKey("core.staff_users.id", ondelete="SET NULL")),
        sa.Column("note", sa.String(500)),  # sanitized server-side: no symptom content
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        schema="school",
    )
    op.create_table(
        "guardian_consents",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("assessment_id", sa.Uuid(), sa.ForeignKey("diary.school_assessments.id", ondelete="CASCADE"), nullable=False),
        sa.Column("method", sa.String(16), nullable=False),  # sms_link | paper | voice
        sa.Column("recorded_by", sa.Uuid(), sa.ForeignKey("core.staff_users.id", ondelete="SET NULL")),
        sa.Column("text_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("evidence_ref", sa.String(255)),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        schema="school",
    )
    op.create_table(
        "guardian_alerts",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("assessment_id", sa.Uuid(), sa.ForeignKey("diary.school_assessments.id", ondelete="CASCADE"), nullable=False),
        sa.Column("guardian_id", sa.Uuid(), sa.ForeignKey("core.guardians.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),  # sent | skipped_safeguarding | failed
        sa.Column("channel", sa.String(16), nullable=False, server_default="sms"),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        schema="school",
    )
    op.create_table(
        "vouchers",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("code", sa.String(32), nullable=False, unique=True),
        sa.Column("assessment_id", sa.Uuid(), sa.ForeignKey("diary.school_assessments.id", ondelete="SET NULL")),
        sa.Column("school_id", sa.Uuid(), sa.ForeignKey("core.schools.id", ondelete="CASCADE"), nullable=False),
        sa.Column("category", sa.String(16), nullable=False),  # sanitary | otc_pain
        sa.Column("otc_item", sa.String(64)),  # from the clinician-approved config list; never on the voucher
        sa.Column("amount_ksh", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="issued"),  # issued | redeemed | expired | cancelled
        sa.Column("issued_by", sa.Uuid(), sa.ForeignKey("core.staff_users.id", ondelete="SET NULL")),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("redeemed_at", sa.DateTime(timezone=True)),
        sa.Column("pharmacy_id", sa.Uuid(), sa.ForeignKey("core.pharmacies.id", ondelete="SET NULL")),
        schema="school",
    )
    op.create_table(
        "voucher_redemptions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("voucher_id", sa.Uuid(), sa.ForeignKey("school.vouchers.id", ondelete="CASCADE"), nullable=False),
        sa.Column("pharmacy_id", sa.Uuid(), sa.ForeignKey("core.pharmacies.id", ondelete="SET NULL"), nullable=False),
        sa.Column("receipt_no", sa.String(64), nullable=False, unique=True),
        sa.Column("amount_ksh", sa.Integer(), nullable=False),
        sa.Column("callback_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        schema="school",
    )
    op.create_table(
        "wallets",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("owner_type", sa.String(16), nullable=False),  # school | admin | employer
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("balance_ksh", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("owner_type", "owner_id", name="uq_wallets_owner"),
        schema="school",
    )
    op.create_table(
        "wallet_ledger",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("wallet_id", sa.Uuid(), sa.ForeignKey("school.wallets.id", ondelete="CASCADE"), nullable=False),
        sa.Column("delta_ksh", sa.Integer(), nullable=False),
        sa.Column("ref_type", sa.String(24), nullable=False),  # funding | voucher_issue | redemption | reversal
        sa.Column("ref_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        schema="school",
    )
    op.create_table(
        "reconciliation_reports",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("report_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        schema="school",
    )

    # ---- diary ---------------------------------------------------------------
    op.add_column(
        "school_assessments",
        sa.Column("requested_contact", sa.Boolean(), nullable=False, server_default=sa.false()),
        schema="diary",
    )


def downgrade() -> None:
    op.execute(sa.text("DROP SCHEMA IF EXISTS school CASCADE"))
    for table in ("pharmacies", "guardians", "student_contact_map", "students", "school_staff", "schools"):
        op.execute(sa.text(f"DROP TABLE IF EXISTS core.{table} CASCADE"))
    op.execute(sa.text("ALTER TABLE diary.school_assessments DROP COLUMN IF EXISTS requested_contact"))
