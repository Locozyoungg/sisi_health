"""Schema rules: activation/approval state for ontology rule versions. The JSON in
/ontology is the canonical payload; the DB stores a copy keyed by content hash plus
the two-person approval workflow."""
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.ids import uuid7
from app.core.time import utc_now_naive
from app.models.base import Base


class RuleVersion(Base):
    __tablename__ = "rule_versions"
    __table_args__ = (
        Index(
            "uq_rule_versions_active_per_rule",
            "rule_id",
            unique=True,
            postgresql_where="status = 'active'",
        ),
        {"schema": "rules"},
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid7)
    rule_id: Mapped[str] = mapped_column(String(64))
    version: Mapped[str] = mapped_column(String(16))
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)
    content_hash: Mapped[str] = mapped_column(String(64))
    # draft | pending_approval | active | rolled_back
    status: Mapped[str] = mapped_column(String(20), default="draft")
    created_by: Mapped[uuid.UUID | None] = mapped_column()
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now_naive)
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    rolled_back_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class RuleActivation(Base):
    __tablename__ = "rule_activations"
    __table_args__ = {"schema": "rules"}

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid7)
    rule_version_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("rules.rule_versions.id"))
    author_id: Mapped[uuid.UUID] = mapped_column()
    approver_id: Mapped[uuid.UUID | None] = mapped_column()
    # pending | approved | rejected
    status: Mapped[str] = mapped_column(String(16), default="pending")
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now_naive)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    note: Mapped[str | None] = mapped_column(String(255))
