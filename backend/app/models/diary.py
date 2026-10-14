"""Schema diary: separately encrypted append-only symptom events, evaluations, erasure jobs.
Every payload column holds envelope-encrypted ciphertext; plaintext never touches this schema."""
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, LargeBinary, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.ids import uuid7
from app.core.time import utc_now_naive
from app.models.base import Base


class DiaryEntry(Base):
    __tablename__ = "diary_entries"
    __table_args__ = {"schema": "diary"}

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid7)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("core.users.id", ondelete="CASCADE"))
    client_id: Mapped[uuid.UUID] = mapped_column()  # client-generated UUIDv7
    idempotency_key: Mapped[str] = mapped_column(String(64), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now_naive)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now_naive, onupdate=utc_now_naive
    )


class DiaryEntryVersion(Base):
    __tablename__ = "diary_entry_versions"
    __table_args__ = {"schema": "diary"}

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid7)
    entry_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("diary.diary_entries.id", ondelete="CASCADE")
    )
    version: Mapped[int] = mapped_column(Integer)
    payload_ciphertext: Mapped[bytes] = mapped_column(LargeBinary)
    key_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("core.data_keys.id"))
    server_ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now_naive)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now_naive)


class RuleEvaluation(Base):
    __tablename__ = "rule_evaluations"
    __table_args__ = {"schema": "diary"}

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid7)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("core.users.id", ondelete="CASCADE"))
    rule_set_version: Mapped[str] = mapped_column(String(32))
    payload_ciphertext: Mapped[bytes] = mapped_column(LargeBinary)
    key_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("core.data_keys.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now_naive)


class ErasureJob(Base):
    __tablename__ = "erasure_jobs"
    __table_args__ = {"schema": "diary"}

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid7)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("core.users.id", ondelete="CASCADE"))
    status: Mapped[str] = mapped_column(
        String(16), default="pending"
    )  # pending|processing|done|failed
    requested_via: Mapped[str] = mapped_column(String(16))  # dsr | revocation
    deadline_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    report_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now_naive)


class SchoolAssessment(Base):
    """One-time USSD/WhatsApp assessment (CC-1, spec 5.3). Answers and band are
    envelope-encrypted (per-assessment data key); plaintext columns are limited
    to the phone hash, age band, consent state, language, channel, timestamps."""

    __tablename__ = "school_assessments"
    __table_args__ = {"schema": "diary"}

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid7)
    phone_hash: Mapped[str] = mapped_column(String(64))
    age_band: Mapped[str] = mapped_column(String(8))
    language: Mapped[str] = mapped_column(String(8))
    # none | self_granted | minor_assent_only | minor_full
    consent_state: Mapped[str] = mapped_column(String(24), default="none")
    payload_ciphertext: Mapped[bytes] = mapped_column(LargeBinary)
    key_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("core.data_keys.id"))
    channel: Mapped[str] = mapped_column(String(16))  # ussd | whatsapp
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now_naive)


class ProcessingFlag(Base):
    """Restriction flags that survive erasure only as long as the processing register needs them;
    no personal content. (Right-to-objection marker.)"""

    __tablename__ = "processing_flags"
    __table_args__ = {"schema": "diary"}

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid7)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("core.users.id", ondelete="CASCADE"))
    flag: Mapped[str] = mapped_column(String(32))
    set_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now_naive)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
