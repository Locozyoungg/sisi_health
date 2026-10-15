"""Phase 5 mapped models: specialist corridor + cervical screening & navigation
(schema layouts match migration 0005 / CC-3). Envelope-encrypted columns hold
computed feature snapshots and patient notes — corridor code never opens raw
diary ciphertext (non-negotiable 5)."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    LargeBinary,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.ids import uuid7
from app.core.time import utc_now_naive
from app.models.base import Base


class ConsultRequest(Base):
    __tablename__ = "consult_requests"
    __table_args__ = {"schema": "corridor"}

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid7)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("core.users.id", ondelete="CASCADE"))
    status: Mapped[str] = mapped_column(String(24), default="pending_nurse_review")
    band: Mapped[str] = mapped_column(String(16))
    urgent: Mapped[bool] = mapped_column(Boolean, default=False)
    safeguarding: Mapped[bool] = mapped_column(Boolean, default=False)
    indicators: Mapped[list[Any]] = mapped_column(JSON, default=list)
    features_ciphertext: Mapped[bytes] = mapped_column(LargeBinary)
    features_key_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("core.data_keys.id"))
    patient_note_ciphertext: Mapped[bytes | None] = mapped_column(LargeBinary)
    patient_note_key_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("core.data_keys.id")
    )
    preferred_county: Mapped[str | None] = mapped_column(String(128))
    preferred_language: Mapped[str] = mapped_column(String(8), default="en")
    chaperone_requested: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now_naive)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now_naive, onupdate=utc_now_naive
    )


class ConsultEvent(Base):
    __tablename__ = "consult_events"
    __table_args__ = {"schema": "corridor"}

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid7)
    request_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("corridor.consult_requests.id", ondelete="CASCADE")
    )
    event_type: Mapped[str] = mapped_column(String(32))
    status_from: Mapped[str | None] = mapped_column(String(24))
    status_to: Mapped[str | None] = mapped_column(String(24))
    actor_type: Mapped[str] = mapped_column(String(16))  # user | staff
    actor_id: Mapped[uuid.UUID | None] = mapped_column()
    note: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now_naive)


class ConsultSession(Base):
    """One-time JWT-gated Jitsi session. `recorded` must stay False (spec 5.4)."""

    __tablename__ = "consult_sessions"
    __table_args__ = (
        CheckConstraint("recorded IS FALSE", name="ck_consult_sessions_no_recording"),
        {"schema": "corridor"},
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid7)
    request_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("corridor.consult_requests.id", ondelete="CASCADE")
    )
    gynecologist_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("core.staff_users.id", ondelete="SET NULL")
    )
    modality: Mapped[str] = mapped_column(String(8), default="video")  # video | audio
    status: Mapped[str] = mapped_column(String(16), default="scheduled")
    scheduled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    room_name: Mapped[str] = mapped_column(String(64), unique=True)
    recorded: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now_naive)


class ConsultConsent(Base):
    __tablename__ = "consult_consents"
    __table_args__ = {"schema": "corridor"}

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid7)
    request_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("corridor.consult_requests.id", ondelete="CASCADE")
    )
    kind: Mapped[str] = mapped_column(String(24))
    method: Mapped[str] = mapped_column(String(16), default="digital")
    recorded_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("core.staff_users.id", ondelete="SET NULL")
    )
    text_version: Mapped[int] = mapped_column(Integer, default=1)
    evidence_ref: Mapped[str | None] = mapped_column(String(255))
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now_naive)


class Facility(Base):
    __tablename__ = "facilities"
    __table_args__ = {"schema": "corridor"}

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid7)
    name: Mapped[str] = mapped_column(String(255))
    county: Mapped[str] = mapped_column(String(128))
    level: Mapped[str] = mapped_column(String(16), default="primary")
    catchment_counties: Mapped[list[Any]] = mapped_column(JSON, default=list)
    languages: Mapped[list[Any]] = mapped_column(JSON, default=list)
    services: Mapped[list[Any]] = mapped_column(JSON, default=list)
    screening_tests: Mapped[list[Any]] = mapped_column(JSON, default=list)
    opening_hours: Mapped[list[Any] | None] = mapped_column(JSON)
    estimated_cost_ksh_min: Mapped[int | None] = mapped_column(Integer)
    estimated_cost_ksh_max: Mapped[int | None] = mapped_column(Integer)
    cost_note: Mapped[str | None] = mapped_column(String(255))
    phone: Mapped[str | None] = mapped_column(String(32))
    email: Mapped[str | None] = mapped_column(String(255))
    last_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    verified_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("core.staff_users.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now_naive)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now_naive, onupdate=utc_now_naive
    )


class Referral(Base):
    __tablename__ = "referrals"
    __table_args__ = {"schema": "corridor"}

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid7)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("core.users.id", ondelete="CASCADE"))
    consult_request_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("corridor.consult_requests.id", ondelete="SET NULL")
    )
    facility_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("corridor.facilities.id", ondelete="SET NULL")
    )
    status: Mapped[str] = mapped_column(String(24), default="draft")
    sections: Mapped[list[Any]] = mapped_column(JSON, default=list)
    approved_sections: Mapped[list[Any]] = mapped_column(JSON, default=list)
    letter_ciphertext: Mapped[bytes | None] = mapped_column(LargeBinary)
    letter_key_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("core.data_keys.id"))
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("core.staff_users.id", ondelete="SET NULL")
    )
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now_naive)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now_naive, onupdate=utc_now_naive
    )


class SharingApproval(Base):
    __tablename__ = "sharing_approvals"
    __table_args__ = {"schema": "corridor"}

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid7)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("core.users.id", ondelete="CASCADE"))
    resource_type: Mapped[str] = mapped_column(String(16))  # referral | follow_up
    resource_id: Mapped[uuid.UUID] = mapped_column()
    action: Mapped[str] = mapped_column(String(16))  # approved | revoked
    method: Mapped[str] = mapped_column(String(16), default="digital")
    evidence_ref: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now_naive)


class SurgeryCase(Base):
    __tablename__ = "surgery_cases"
    __table_args__ = {"schema": "corridor"}

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid7)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("core.users.id", ondelete="CASCADE"))
    referral_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("corridor.referrals.id", ondelete="SET NULL")
    )
    facility_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("corridor.facilities.id", ondelete="SET NULL")
    )
    gynecologist_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("core.staff_users.id", ondelete="SET NULL")
    )
    status: Mapped[str] = mapped_column(String(24), default="diagnostic")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now_naive)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now_naive, onupdate=utc_now_naive
    )


class SurgeryEvent(Base):
    __tablename__ = "surgery_events"
    __table_args__ = {"schema": "corridor"}

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid7)
    case_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("corridor.surgery_cases.id", ondelete="CASCADE")
    )
    event_type: Mapped[str] = mapped_column(String(32))
    status_from: Mapped[str | None] = mapped_column(String(24))
    status_to: Mapped[str | None] = mapped_column(String(24))
    actor_type: Mapped[str] = mapped_column(String(16))  # user | staff
    actor_id: Mapped[uuid.UUID | None] = mapped_column()
    note: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now_naive)


class PricingStub(Base):
    """Indicative partner-hospital pricing. `indicative` must stay True (spec 5.4)."""

    __tablename__ = "pricing_stubs"
    __table_args__ = (
        CheckConstraint("indicative IS TRUE", name="ck_pricing_stubs_indicative"),
        {"schema": "corridor"},
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid7)
    procedure: Mapped[str] = mapped_column(String(128))
    facility_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("corridor.facilities.id", ondelete="CASCADE")
    )
    amount_ksh_min: Mapped[int] = mapped_column(Integer)
    amount_ksh_max: Mapped[int] = mapped_column(Integer)
    currency: Mapped[str] = mapped_column(String(8), default="KES")
    source: Mapped[str] = mapped_column(String(255))
    indicative: Mapped[bool] = mapped_column(Boolean, default=True)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    note: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now_naive)


class OutcomeLog(Base):
    __tablename__ = "outcome_logs"
    __table_args__ = {"schema": "corridor"}

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid7)
    case_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("corridor.surgery_cases.id", ondelete="CASCADE")
    )
    outcome_category: Mapped[str] = mapped_column(String(32))
    note: Mapped[str | None] = mapped_column(String(500))
    recorded_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("core.staff_users.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now_naive)


class FollowUpTracker(Base):
    """Cervical follow-up tracker. Status-only for staff: no results-detail
    column exists anywhere (hard limit, spec 5.4.1)."""

    __tablename__ = "follow_up_tracker"
    __table_args__ = {"schema": "corridor"}

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid7)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("core.users.id", ondelete="CASCADE"))
    facility_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("corridor.facilities.id", ondelete="SET NULL")
    )
    status: Mapped[str] = mapped_column(String(24), default="referred")
    consent_to_share: Mapped[bool] = mapped_column(Boolean, default=False)
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reminders_sent: Mapped[int] = mapped_column(Integer, default=0)
    last_reminder_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    lost_to_follow_up: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now_naive)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now_naive, onupdate=utc_now_naive
    )


class TrackerEvent(Base):
    __tablename__ = "tracker_events"
    __table_args__ = {"schema": "corridor"}

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid7)
    tracker_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("corridor.follow_up_tracker.id", ondelete="CASCADE")
    )
    status_from: Mapped[str | None] = mapped_column(String(24))
    status_to: Mapped[str] = mapped_column(String(24))
    actor_type: Mapped[str] = mapped_column(String(16))  # user | staff | system
    actor_id: Mapped[uuid.UUID | None] = mapped_column()
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now_naive)


class Reminder(Base):
    """Generic wording only — message_key never names a condition (spec 3.5/5.4.1)."""

    __tablename__ = "reminders"
    __table_args__ = (
        UniqueConstraint("user_id", "kind", "due_at", name="uq_reminders_user_kind_due"),
        {"schema": "corridor"},
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid7)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("core.users.id", ondelete="CASCADE"))
    kind: Mapped[str] = mapped_column(String(24))  # screening | follow_up | hpv_vaccine
    status: Mapped[str] = mapped_column(String(16), default="pending")
    message_key: Mapped[str] = mapped_column(String(64))
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    channel: Mapped[str] = mapped_column(String(8), default="sms")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now_naive)
