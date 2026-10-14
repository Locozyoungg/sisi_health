"""SQLAlchemy models for all five schemas."""

from app.models.audit import AuditEvent
from app.models.base import Base
from app.models.consent import ConsentEvent, ConsentText, DsrRequest, ProcessingRegister
from app.models.core import (
    ConfigValue,
    DataKey,
    Device,
    OtpRequest,
    RefreshToken,
    StaffUser,
    User,
)
from app.models.diary import (
    DiaryEntry,
    DiaryEntryVersion,
    ErasureJob,
    ProcessingFlag,
    RuleEvaluation,
)
from app.models.rules import RuleActivation, RuleVersion

__all__ = [
    "AuditEvent",
    "Base",
    "ConfigValue",
    "ConsentEvent",
    "ConsentText",
    "DataKey",
    "Device",
    "DiaryEntry",
    "DiaryEntryVersion",
    "DsrRequest",
    "ErasureJob",
    "OtpRequest",
    "ProcessingFlag",
    "ProcessingRegister",
    "RefreshToken",
    "RuleActivation",
    "RuleEvaluation",
    "RuleVersion",
    "StaffUser",
    "User",
]
