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
    UssdSession,
)
from app.models.diary import (
    DiaryEntry,
    DiaryEntryVersion,
    ErasureJob,
    ProcessingFlag,
    RuleEvaluation,
    SchoolAssessment,
)
from app.models.rules import RuleActivation, RuleVersion
from app.models.school import (
    AssessmentAction,
    Guardian,
    GuardianAlert,
    GuardianConsent,
    Pharmacy,
    ReconciliationReport,
    School,
    SchoolStaff,
    Student,
    StudentContactMap,
    Voucher,
    VoucherRedemption,
    Wallet,
    WalletLedger,
)

__all__ = [
    "AssessmentAction",
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
    "Guardian",
    "GuardianAlert",
    "GuardianConsent",
    "OtpRequest",
    "Pharmacy",
    "ProcessingFlag",
    "ProcessingRegister",
    "ReconciliationReport",
    "RefreshToken",
    "RuleActivation",
    "RuleEvaluation",
    "RuleVersion",
    "School",
    "SchoolAssessment",
    "SchoolStaff",
    "StaffUser",
    "Student",
    "StudentContactMap",
    "User",
    "UssdSession",
    "Voucher",
    "VoucherRedemption",
    "Wallet",
    "WalletLedger",
]
