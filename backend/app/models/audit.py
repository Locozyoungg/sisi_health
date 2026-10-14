"""Schema audit: append-only, hash-chained. Hashing is computed by a DB trigger
(migration 0001) so the writer and the Python verifier can never drift. Payloads are
sanitized in the service layer: never names, phone numbers, or symptom content."""
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, BigInteger, DateTime, Identity, LargeBinary, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.ids import uuid7
from app.core.time import utc_now_naive
from app.models.base import Base


class AuditEvent(Base):
    __tablename__ = "audit_events"
    __table_args__ = {"schema": "audit"}

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid7)
    seq: Mapped[int] = mapped_column(BigInteger, Identity(), unique=True)
    event_type: Mapped[str] = mapped_column(String(64))
    actor_type: Mapped[str] = mapped_column(String(16))  # user | staff | system
    actor_id: Mapped[uuid.UUID | None] = mapped_column()
    actor_role: Mapped[str | None] = mapped_column(String(32))
    resource_type: Mapped[str] = mapped_column(String(32))
    resource_id: Mapped[uuid.UUID | None] = mapped_column()
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    prev_hash: Mapped[bytes] = mapped_column(LargeBinary)
    row_hash: Mapped[bytes] = mapped_column(LargeBinary)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now_naive)
