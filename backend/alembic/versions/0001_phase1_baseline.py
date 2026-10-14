"""Phase 1 baseline: all schemas, tables, and the audit hash-chain triggers.

Revision ID: 0001
Revises:
Create Date: 2026-10-14

ROLLBACK NOTE: forward-only per spec. A rollback of this baseline means dropping
the schemas in reverse dependency order (diary, rules, consent, audit, core) and
restoring the previous backup — data is envelope-encrypted and unrecoverable
without the master key, so rollback is a restore operation, not a downgrade.
"""
from alembic import op
import sqlalchemy as sa

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")
    for schema in ("core", "diary", "audit", "consent", "rules"):
        op.execute(sa.text(f"CREATE SCHEMA IF NOT EXISTS {schema}"))

    # ---- core -------------------------------------------------------------
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("pseudonym_id", sa.Uuid(), unique=True),
        sa.Column("phone_encrypted", sa.LargeBinary()),
        sa.Column("phone_hash", sa.String(64), unique=True),
        sa.Column("birth_date_encrypted", sa.LargeBinary()),
        sa.Column("age_band", sa.String(8)),
        sa.Column("language", sa.String(8), nullable=False, server_default="en"),
        sa.Column("status", sa.String(16), nullable=False, server_default="active"),
        sa.Column("processing_restricted", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("erased_at", sa.DateTime(timezone=True)),
        schema="core",
    )
    op.create_table(
        "devices",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("core.users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("device_key_hash", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("user_id", "device_key_hash", name="uq_devices_user_device"),
        schema="core",
    )
    op.create_table(
        "refresh_tokens",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("core.users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("family_id", sa.Uuid(), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("device_id", sa.Uuid(), sa.ForeignKey("core.devices.id", ondelete="SET NULL")),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("rotated_at", sa.DateTime(timezone=True)),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        schema="core",
    )
    op.create_table(
        "otp_requests",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("phone_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("code_hash", sa.String(64)),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
        sa.Column("request_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("window_start", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("locked_until", sa.DateTime(timezone=True)),
        sa.Column("last_request_at", sa.DateTime(timezone=True)),
        schema="core",
    )
    op.create_table(
        "staff_users",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("email", sa.String(255), nullable=False, unique=True),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("totp_secret_encrypted", sa.LargeBinary()),
        sa.Column("totp_confirmed", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("role", sa.String(32), nullable=False),
        sa.Column("disabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("last_active_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        schema="core",
    )
    op.create_table(
        "data_keys",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("owner_type", sa.String(16), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("wrapped_key", sa.LargeBinary(), nullable=False),
        sa.Column("key_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        schema="core",
    )
    op.create_index("ix_data_keys_owner", "data_keys", ["owner_type", "owner_id"], schema="core")
    op.create_table(
        "config_values",
        sa.Column("key", sa.String(64), primary_key=True),
        sa.Column("value_json", sa.JSON(), nullable=False),
        sa.Column("updated_by", sa.Uuid()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        schema="core",
    )

    # ---- diary ------------------------------------------------------------
    op.create_table(
        "diary_entries",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("core.users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("client_id", sa.Uuid(), nullable=False),
        sa.Column("idempotency_key", sa.String(64), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("user_id", "client_id", name="uq_diary_entries_user_client"),
        schema="diary",
    )
    op.create_table(
        "diary_entry_versions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("entry_id", sa.Uuid(), sa.ForeignKey("diary.diary_entries.id", ondelete="CASCADE"), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("payload_ciphertext", sa.LargeBinary(), nullable=False),
        sa.Column("key_id", sa.Uuid(), sa.ForeignKey("core.data_keys.id"), nullable=False),
        sa.Column("server_ts", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("entry_id", "version", name="uq_diary_versions_entry_version"),
        schema="diary",
    )
    op.create_table(
        "rule_evaluations",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("core.users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("rule_set_version", sa.String(32), nullable=False),
        sa.Column("payload_ciphertext", sa.LargeBinary(), nullable=False),
        sa.Column("key_id", sa.Uuid(), sa.ForeignKey("core.data_keys.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        schema="diary",
    )
    op.create_table(
        "erasure_jobs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("core.users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("requested_via", sa.String(16), nullable=False),
        sa.Column("deadline_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("report_json", sa.JSON()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        schema="diary",
    )
    op.create_table(
        "processing_flags",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("core.users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("flag", sa.String(32), nullable=False),
        sa.Column("set_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        schema="diary",
    )

    # ---- audit ------------------------------------------------------------
    op.create_table(
        "audit_events",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("seq", sa.BigInteger(), sa.Identity(), nullable=False, unique=True),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("actor_type", sa.String(16), nullable=False),
        sa.Column("actor_id", sa.Uuid()),
        sa.Column("actor_role", sa.String(32)),
        sa.Column("resource_type", sa.String(32), nullable=False),
        sa.Column("resource_id", sa.Uuid()),
        sa.Column("payload", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("prev_hash", sa.LargeBinary(), nullable=False),
        sa.Column("row_hash", sa.LargeBinary(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        schema="audit",
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION audit.chain_insert() RETURNS trigger AS $$
        DECLARE
            prev bytea;
        BEGIN
            PERFORM pg_advisory_xact_lock(424242);
            SELECT row_hash INTO prev FROM audit.audit_events ORDER BY seq DESC LIMIT 1;
            NEW.prev_hash := coalesce(prev, '\\x00'::bytea);
            NEW.row_hash := digest(
                NEW.prev_hash || convert_to(
                    jsonb_build_object(
                        'event_type',    NEW.event_type,
                        'actor_type',    NEW.actor_type,
                        'actor_id',      NEW.actor_id,
                        'actor_role',    NEW.actor_role,
                        'resource_type', NEW.resource_type,
                        'resource_id',   NEW.resource_id,
                        'payload',       NEW.payload,
                        'created_at',    NEW.created_at
                    )::text, 'UTF8'),
                'sha256');
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION audit.block_mutation() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'audit.audit_events is append-only';
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        "CREATE TRIGGER audit_chain BEFORE INSERT ON audit.audit_events "
        "FOR EACH ROW EXECUTE FUNCTION audit.chain_insert()"
    )
    op.execute(
        "CREATE TRIGGER audit_no_update BEFORE UPDATE ON audit.audit_events "
        "FOR EACH ROW EXECUTE FUNCTION audit.block_mutation()"
    )
    op.execute(
        "CREATE TRIGGER audit_no_delete BEFORE DELETE ON audit.audit_events "
        "FOR EACH ROW EXECUTE FUNCTION audit.block_mutation()"
    )

    # ---- consent ----------------------------------------------------------
    op.create_table(
        "consent_texts",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("key", sa.String(64), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("language", sa.String(8), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("body_text", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("key", "version", "language", name="uq_consent_texts_key_version_lang"),
        schema="consent",
    )
    op.create_table(
        "consent_events",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("core.users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("event_type", sa.String(32), nullable=False),
        sa.Column("text_id", sa.Uuid(), sa.ForeignKey("consent.consent_texts.id")),
        sa.Column("method", sa.String(16), nullable=False),
        sa.Column("recorded_by", sa.Uuid()),
        sa.Column("evidence_ref", sa.String(255)),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        schema="consent",
    )
    op.create_table(
        "dsr_requests",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("core.users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("type", sa.String(16), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="open"),
        sa.Column("payload", sa.JSON()),
        sa.Column("deadline_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("handler_id", sa.Uuid()),
        schema="consent",
    )
    op.create_table(
        "processing_register",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("processor_name", sa.String(128), nullable=False),
        sa.Column("location", sa.String(128), nullable=False),
        sa.Column("purpose", sa.String(255), nullable=False),
        sa.Column("safeguard", sa.String(255), nullable=False),
        sa.Column("diary_content_allowed", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        schema="consent",
    )

    # ---- rules ------------------------------------------------------------
    op.create_table(
        "rule_versions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("rule_id", sa.String(64), nullable=False),
        sa.Column("version", sa.String(16), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="draft"),
        sa.Column("created_by", sa.Uuid()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("activated_at", sa.DateTime(timezone=True)),
        sa.Column("rolled_back_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("rule_id", "version", name="uq_rule_versions_rule_version"),
        schema="rules",
    )
    op.create_index(
        "uq_rule_versions_active_per_rule",
        "rule_versions",
        ["rule_id"],
        unique=True,
        postgresql_where=sa.text("status = 'active'"),
        schema="rules",
    )
    op.create_table(
        "rule_activations",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("rule_version_id", sa.Uuid(), sa.ForeignKey("rules.rule_versions.id"), nullable=False),
        sa.Column("author_id", sa.Uuid(), nullable=False),
        sa.Column("approver_id", sa.Uuid()),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("decided_at", sa.DateTime(timezone=True)),
        sa.Column("note", sa.String(255)),
        schema="rules",
    )


def downgrade() -> None:
    # Forward-only per spec: see ROLLBACK NOTE above. Provided only for completeness.
    for schema in ("diary", "rules", "consent", "audit", "core"):
        op.execute(sa.text(f"DROP SCHEMA IF EXISTS {schema} CASCADE"))
