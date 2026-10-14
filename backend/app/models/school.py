"""Phase 4 mapped models: school module, vouchers, wallets, guardians, pharmacies
from typing import Any
(schema layouts match migration 0003 / CC-2)."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
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


class School(Base):
    __tablename__ = "schools"
    __table_args__ = {"schema": "core"}

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid7)
    name: Mapped[str] = mapped_column(String(255))
    county: Mapped[str | None] = mapped_column(String(128))
    status: Mapped[str] = mapped_column(String(16), default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now_naive)


class SchoolStaff(Base):
    __tablename__ = "school_staff"
    __table_args__ = (
        UniqueConstraint("staff_id", "school_id", name="uq_school_staff_staff_school"),
        {"schema": "core"},
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid7)
    staff_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("core.staff_users.id", ondelete="CASCADE")
    )
    school_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("core.schools.id", ondelete="CASCADE"))
    role_within: Mapped[str] = mapped_column(String(16))  # nurse | school_admin
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now_naive)


class Student(Base):
    __tablename__ = "students"
    __table_args__ = {"schema": "core"}

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid7)
    school_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("core.schools.id", ondelete="CASCADE"))
    pseudonym_id: Mapped[uuid.UUID] = mapped_column(unique=True, default=uuid7)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now_naive)


class StudentContactMap(Base):
    """Envelope-encrypted name/phone per student. Only the re-identify path reads
    this table (spec 3.1); every read requires a typed reason and an audit entry."""

    __tablename__ = "student_contact_map"
    __table_args__ = {"schema": "core"}

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid7)
    student_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("core.students.id", ondelete="CASCADE")
    )
    payload_ciphertext: Mapped[bytes] = mapped_column(LargeBinary)
    key_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("core.data_keys.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now_naive)


class Guardian(Base):
    __tablename__ = "guardians"
    __table_args__ = {"schema": "core"}

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid7)
    student_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("core.students.id", ondelete="CASCADE")
    )
    contact_ciphertext: Mapped[bytes] = mapped_column(LargeBinary)
    key_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("core.data_keys.id"))
    alert_consent: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now_naive)


class Pharmacy(Base):
    __tablename__ = "pharmacies"
    __table_args__ = {"schema": "core"}

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid7)
    name: Mapped[str] = mapped_column(String(255))
    location: Mapped[str | None] = mapped_column(String(255))
    verified: Mapped[bool] = mapped_column(Boolean, default=False)
    last_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now_naive)


class AssessmentAction(Base):
    __tablename__ = "assessment_actions"
    __table_args__ = {"schema": "school"}

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid7)
    assessment_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("diary.school_assessments.id", ondelete="CASCADE")
    )
    action: Mapped[str] = mapped_column(String(24))  # spoke_to | referred | escalated | contacted
    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("core.staff_users.id", ondelete="SET NULL")
    )
    note: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now_naive)


class GuardianConsent(Base):
    __tablename__ = "guardian_consents"
    __table_args__ = {"schema": "school"}

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid7)
    assessment_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("diary.school_assessments.id", ondelete="CASCADE")
    )
    method: Mapped[str] = mapped_column(String(16))  # sms_link | paper | voice
    recorded_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("core.staff_users.id", ondelete="SET NULL")
    )
    text_version: Mapped[int] = mapped_column(Integer, default=1)
    evidence_ref: Mapped[str | None] = mapped_column(String(255))
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now_naive)


class GuardianAlert(Base):
    __tablename__ = "guardian_alerts"
    __table_args__ = {"schema": "school"}

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid7)
    assessment_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("diary.school_assessments.id", ondelete="CASCADE")
    )
    guardian_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("core.guardians.id", ondelete="CASCADE")
    )
    status: Mapped[str] = mapped_column(String(24))  # sent | skipped_safeguarding | failed
    channel: Mapped[str] = mapped_column(String(16), default="sms")
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now_naive)


class Voucher(Base):
    __tablename__ = "vouchers"
    __table_args__ = {"schema": "school"}

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid7)
    code: Mapped[str] = mapped_column(String(32), unique=True)
    assessment_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("diary.school_assessments.id", ondelete="SET NULL")
    )
    school_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("core.schools.id", ondelete="CASCADE"))
    category: Mapped[str] = mapped_column(String(16))  # sanitary | otc_pain
    otc_item: Mapped[str | None] = mapped_column(String(64))  # from clinician-approved config list
    amount_ksh: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(16), default="issued")
    issued_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("core.staff_users.id", ondelete="SET NULL")
    )
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now_naive)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    redeemed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    pharmacy_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("core.pharmacies.id", ondelete="SET NULL")
    )


class VoucherRedemption(Base):
    __tablename__ = "voucher_redemptions"
    __table_args__ = {"schema": "school"}

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid7)
    voucher_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("school.vouchers.id", ondelete="CASCADE")
    )
    pharmacy_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("core.pharmacies.id", ondelete="SET NULL")
    )
    receipt_no: Mapped[str] = mapped_column(String(64), unique=True)
    amount_ksh: Mapped[int] = mapped_column(Integer)
    callback_json: Mapped[dict[str, Any]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now_naive)


class Wallet(Base):
    __tablename__ = "wallets"
    __table_args__ = (
        UniqueConstraint("owner_type", "owner_id", name="uq_wallets_owner"),
        {"schema": "school"},
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid7)
    owner_type: Mapped[str] = mapped_column(String(16))  # school | admin | employer
    owner_id: Mapped[uuid.UUID] = mapped_column()
    balance_ksh: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now_naive)


class WalletLedger(Base):
    __tablename__ = "wallet_ledger"
    __table_args__ = {"schema": "school"}

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid7)
    wallet_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("school.wallets.id", ondelete="CASCADE")
    )
    delta_ksh: Mapped[int] = mapped_column(Integer)
    ref_type: Mapped[str] = mapped_column(
        String(24)
    )  # funding | voucher_issue | redemption | reversal
    ref_id: Mapped[uuid.UUID] = mapped_column()
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now_naive)


class ReconciliationReport(Base):
    __tablename__ = "reconciliation_reports"
    __table_args__ = {"schema": "school"}

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid7)
    report_json: Mapped[dict[str, Any]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now_naive)
