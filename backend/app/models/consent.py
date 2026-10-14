"""Schema consent: versioned consent texts, consent/revoke events, DSR requests,
and the cross-border processing register."""

import uuid
from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.ids import uuid7
from app.core.time import utc_now_naive
from app.models.base import Base


class ConsentText(Base):
    __tablename__ = "consent_texts"
    __table_args__ = {"schema": "consent"}

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid7)
    key: Mapped[str] = mapped_column(String(64))  # e.g. guardian_consent
    version: Mapped[int] = mapped_column(Integer)
    language: Mapped[str] = mapped_column(String(8))
    title: Mapped[str] = mapped_column(String(255))
    body_text: Mapped[str] = mapped_column(Text)
    content_hash: Mapped[str] = mapped_column(String(64))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now_naive)


class ConsentEvent(Base):
    __tablename__ = "consent_events"
    __table_args__ = {"schema": "consent"}

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid7)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("core.users.id", ondelete="CASCADE"))
    # guardian_grant | minor_assent | self_grant | revoke
    event_type: Mapped[str] = mapped_column(String(32))
    text_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("consent.consent_texts.id"))
    # digital | sms_link | paper | voice
    method: Mapped[str] = mapped_column(String(16))
    recorded_by: Mapped[uuid.UUID | None] = mapped_column()  # staff id (nurse-assisted capture)
    evidence_ref: Mapped[str | None] = mapped_column(String(255))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now_naive)


class DsrRequest(Base):
    __tablename__ = "dsr_requests"
    __table_args__ = {"schema": "consent"}

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid7)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("core.users.id", ondelete="CASCADE"))
    # access | correction | portability | erasure | objection
    type: Mapped[str] = mapped_column(String(16))
    # open | processing | fulfilled | rejected
    status: Mapped[str] = mapped_column(String(16), default="open")
    payload: Mapped[dict | None] = mapped_column(JSON)
    deadline_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now_naive)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    handler_id: Mapped[uuid.UUID | None] = mapped_column()


class ProcessingRegister(Base):
    __tablename__ = "processing_register"
    __table_args__ = {"schema": "consent"}

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid7)
    processor_name: Mapped[str] = mapped_column(String(128))
    location: Mapped[str] = mapped_column(String(128))
    purpose: Mapped[str] = mapped_column(String(255))
    safeguard: Mapped[str] = mapped_column(String(255))
    diary_content_allowed: Mapped[bool] = mapped_column(Boolean, default=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now_naive)
