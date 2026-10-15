"""CC-3 (Phase 5): specialist corridor + cervical screening & navigation.

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-15

Adds schema `corridor`: consult requests/sessions/consents, facility directory
(with screening fields and staleness), referrals + patient sharing approvals,
surgery navigation with indicative pricing stubs, the cervical follow-up
tracker (status-only for staff: no results-detail column exists anywhere), and
screening reminders. Envelope-encrypted columns hold the computed features
snapshot and the patient note — corridor code never opens raw diary ciphertext
(non-negotiable 5). `consult_sessions.recorded` and `pricing_stubs.indicative`
carry CHECK constraints that document the no-recording / indicative-only
invariants.

ROLLBACK NOTE: forward-only per spec. Rolling back means dropping schema
`corridor` and restoring the prior backup; features snapshots become unreadable
once their data keys are deleted.
"""
from alembic import op
import sqlalchemy as sa

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(sa.text("CREATE SCHEMA IF NOT EXISTS corridor"))

    # ---- consult requests / review / sessions -------------------------------
    op.create_table(
        "consult_requests",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("core.users.id", ondelete="CASCADE"), nullable=False),
        sa.Column(
            "status",
            sa.String(24),
            nullable=False,
            server_default="pending_nurse_review",
            comment="pending_nurse_review | approved | declined | scheduled | completed | missed | cancelled",
        ),
        sa.Column("band", sa.String(16), nullable=False),
        sa.Column("urgent", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("safeguarding", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("indicators", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("features_ciphertext", sa.LargeBinary(), nullable=False),
        sa.Column("features_key_id", sa.Uuid(), sa.ForeignKey("core.data_keys.id"), nullable=False),
        sa.Column("patient_note_ciphertext", sa.LargeBinary()),
        sa.Column("patient_note_key_id", sa.Uuid(), sa.ForeignKey("core.data_keys.id")),
        sa.Column("preferred_county", sa.String(128)),
        sa.Column("preferred_language", sa.String(8), nullable=False, server_default="en"),
        sa.Column("chaperone_requested", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        schema="corridor",
    )
    op.create_index(
        "ix_corridor_consult_requests_status", "consult_requests", ["status"], schema="corridor"
    )
    op.create_table(
        "consult_events",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("request_id", sa.Uuid(), sa.ForeignKey("corridor.consult_requests.id", ondelete="CASCADE"), nullable=False),
        sa.Column("event_type", sa.String(32), nullable=False),
        sa.Column("status_from", sa.String(24)),
        sa.Column("status_to", sa.String(24)),
        sa.Column("actor_type", sa.String(16), nullable=False),  # user | staff
        sa.Column("actor_id", sa.Uuid()),
        sa.Column("note", sa.String(500)),  # sanitized server-side: no symptom content
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        schema="corridor",
    )
    op.create_table(
        "consult_sessions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("request_id", sa.Uuid(), sa.ForeignKey("corridor.consult_requests.id", ondelete="CASCADE"), nullable=False),
        sa.Column("gynecologist_id", sa.Uuid(), sa.ForeignKey("core.staff_users.id", ondelete="SET NULL")),
        sa.Column("modality", sa.String(8), nullable=False, server_default="video"),  # video | audio
        sa.Column(
            "status",
            sa.String(16),
            nullable=False,
            server_default="scheduled",
            comment="scheduled | in_progress | completed | no_show | cancelled",
        ),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("room_name", sa.String(64), nullable=False, unique=True),
        sa.Column(
            "recorded",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
            comment="No recording by default (spec 5.4); enforced by CHECK.",
        ),
        sa.CheckConstraint("recorded IS FALSE", name="ck_consult_sessions_no_recording"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        schema="corridor",
    )
    op.create_table(
        "consult_consents",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("request_id", sa.Uuid(), sa.ForeignKey("corridor.consult_requests.id", ondelete="CASCADE"), nullable=False),
        sa.Column(
            "kind",
            sa.String(24),
            nullable=False,
            comment="guardian_consent | minor_assent | chaperone_requested | chaperone_confirmed",
        ),
        sa.Column("method", sa.String(16), nullable=False, server_default="digital"),  # digital | sms_link | paper | voice
        sa.Column("recorded_by", sa.Uuid(), sa.ForeignKey("core.staff_users.id", ondelete="SET NULL")),
        sa.Column("text_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("evidence_ref", sa.String(255)),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        schema="corridor",
    )

    # ---- facility directory (referral engine + screening fields) ------------
    op.create_table(
        "facilities",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("county", sa.String(128), nullable=False),
        sa.Column("level", sa.String(16), nullable=False, server_default="primary"),  # primary | secondary | tertiary
        sa.Column("catchment_counties", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("languages", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("services", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column(
            "screening_tests",
            sa.JSON(),
            nullable=False,
            server_default="[]",
            comment="hpv_test | via | pap_smear (screening fields, spec 5.4.1)",
        ),
        sa.Column("opening_hours", sa.JSON()),
        sa.Column("estimated_cost_ksh_min", sa.Integer()),
        sa.Column("estimated_cost_ksh_max", sa.Integer()),
        sa.Column("cost_note", sa.String(255)),  # indicative + sourced, never medical advice
        sa.Column("phone", sa.String(32)),  # business contact, never patient data
        sa.Column("email", sa.String(255)),
        sa.Column("last_verified_at", sa.DateTime(timezone=True)),
        sa.Column("verified_by", sa.Uuid(), sa.ForeignKey("core.staff_users.id", ondelete="SET NULL")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        schema="corridor",
    )
    op.create_index(
        "ix_corridor_facilities_county_verified",
        "facilities",
        ["county", "last_verified_at"],
        schema="corridor",
    )

    # ---- referrals + patient-approved sharing -------------------------------
    op.create_table(
        "referrals",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("core.users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("consult_request_id", sa.Uuid(), sa.ForeignKey("corridor.consult_requests.id", ondelete="SET NULL")),
        sa.Column("facility_id", sa.Uuid(), sa.ForeignKey("corridor.facilities.id", ondelete="SET NULL")),
        sa.Column(
            "status",
            sa.String(24),
            nullable=False,
            server_default="draft",
            comment="draft | awaiting_approval | approved | sent | revoked",
        ),
        sa.Column("sections", sa.JSON(), nullable=False, server_default="[]"),  # offered sections
        sa.Column("approved_sections", sa.JSON(), nullable=False, server_default="[]"),  # patient-approved subset
        sa.Column("letter_ciphertext", sa.LargeBinary()),
        sa.Column("letter_key_id", sa.Uuid(), sa.ForeignKey("core.data_keys.id")),
        sa.Column("created_by", sa.Uuid(), sa.ForeignKey("core.staff_users.id", ondelete="SET NULL")),
        sa.Column("approved_at", sa.DateTime(timezone=True)),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.Column("sent_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        schema="corridor",
    )
    op.create_table(
        "sharing_approvals",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("core.users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("resource_type", sa.String(16), nullable=False),  # referral | follow_up
        sa.Column("resource_id", sa.Uuid(), nullable=False),
        sa.Column("action", sa.String(16), nullable=False),  # approved | revoked
        sa.Column("method", sa.String(16), nullable=False, server_default="digital"),
        sa.Column("evidence_ref", sa.String(255)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        schema="corridor",
    )

    # ---- surgery navigation (indicative only, spec 5.4) ---------------------
    op.create_table(
        "surgery_cases",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("core.users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("referral_id", sa.Uuid(), sa.ForeignKey("corridor.referrals.id", ondelete="SET NULL")),
        sa.Column("facility_id", sa.Uuid(), sa.ForeignKey("corridor.facilities.id", ondelete="SET NULL")),
        sa.Column("gynecologist_id", sa.Uuid(), sa.ForeignKey("core.staff_users.id", ondelete="SET NULL")),
        sa.Column(
            "status",
            sa.String(24),
            nullable=False,
            server_default="diagnostic",
            comment="diagnostic | surgical_evaluation | surgery | follow_up | closed | cancelled",
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        schema="corridor",
    )
    op.create_table(
        "surgery_events",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("case_id", sa.Uuid(), sa.ForeignKey("corridor.surgery_cases.id", ondelete="CASCADE"), nullable=False),
        sa.Column("event_type", sa.String(32), nullable=False),
        sa.Column("status_from", sa.String(24)),
        sa.Column("status_to", sa.String(24)),
        sa.Column("actor_type", sa.String(16), nullable=False),  # user | staff
        sa.Column("actor_id", sa.Uuid()),
        sa.Column("note", sa.String(500)),  # sanitized server-side
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        schema="corridor",
    )
    op.create_table(
        "pricing_stubs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("procedure", sa.String(128), nullable=False),
        sa.Column("facility_id", sa.Uuid(), sa.ForeignKey("corridor.facilities.id", ondelete="CASCADE"), nullable=False),
        sa.Column("amount_ksh_min", sa.Integer(), nullable=False),
        sa.Column("amount_ksh_max", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(8), nullable=False, server_default="KES"),
        sa.Column("source", sa.String(255), nullable=False),  # indicative pricing must be sourced
        sa.Column(
            "indicative",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
            comment="Indicative only, never medical advice (spec 5.4); enforced by CHECK.",
        ),
        sa.CheckConstraint("indicative IS TRUE", name="ck_pricing_stubs_indicative"),
        sa.Column("verified_at", sa.DateTime(timezone=True)),
        sa.Column("note", sa.String(255)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        schema="corridor",
    )
    op.create_table(
        "outcome_logs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("case_id", sa.Uuid(), sa.ForeignKey("corridor.surgery_cases.id", ondelete="CASCADE"), nullable=False),
        sa.Column(
            "outcome_category",
            sa.String(32),
            nullable=False,
            comment="completed_surgery | follow_up_scheduled | referred_on | cancelled | no_show",
        ),
        sa.Column("note", sa.String(500)),  # sanitized server-side
        sa.Column("recorded_by", sa.Uuid(), sa.ForeignKey("core.staff_users.id", ondelete="SET NULL")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        schema="corridor",
    )

    # ---- cervical follow-up tracker (status only, no results detail) --------
    op.create_table(
        "follow_up_tracker",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("core.users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("facility_id", sa.Uuid(), sa.ForeignKey("corridor.facilities.id", ondelete="SET NULL")),
        sa.Column(
            "status",
            sa.String(24),
            nullable=False,
            server_default="referred",
            comment="referred | screened | result_received | further_assessment | treatment | follow_up | completed",
        ),
        sa.Column("consent_to_share", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("due_at", sa.DateTime(timezone=True)),
        sa.Column("reminders_sent", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_reminder_at", sa.DateTime(timezone=True)),
        sa.Column(
            "lost_to_follow_up",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
            comment="Derived by the reminder job (status only for nurses, spec 5.4.1).",
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        schema="corridor",
    )
    op.create_index(
        "ix_corridor_tracker_status_due", "follow_up_tracker", ["status", "due_at"], schema="corridor"
    )
    op.create_table(
        "tracker_events",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tracker_id", sa.Uuid(), sa.ForeignKey("corridor.follow_up_tracker.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status_from", sa.String(24)),
        sa.Column("status_to", sa.String(24), nullable=False),
        sa.Column("actor_type", sa.String(16), nullable=False),  # user | staff | system
        sa.Column("actor_id", sa.Uuid()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        schema="corridor",
    )

    # ---- screening reminders (generic wording only) -------------------------
    op.create_table(
        "reminders",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("core.users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("kind", sa.String(24), nullable=False, comment="screening | follow_up | hpv_vaccine"),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),  # pending | sent | skipped_no_consent | failed
        sa.Column("message_key", sa.String(64), nullable=False),  # generic wording only, never condition names
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True)),
        sa.Column("channel", sa.String(8), nullable=False, server_default="sms"),
        sa.UniqueConstraint("user_id", "kind", "due_at", name="uq_reminders_user_kind_due"),
        schema="corridor",
    )
    op.create_index("ix_corridor_reminders_due_status", "reminders", ["due_at", "status"], schema="corridor")


def downgrade() -> None:
    op.execute(sa.text("DROP SCHEMA IF EXISTS corridor CASCADE"))
