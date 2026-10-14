"""School-module service (Phase 4): nurse flag queue, action tracking,
re-identification (spec 3.1), guardian consents and RED-only guardian alerts
(spec 3.3). Nurses see pseudonyms, bands and actions ONLY — raw symptom data
for minors never leaves the encrypted payload (non-negotiable 5)."""

import secrets
import uuid
from datetime import timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit.service import record_event, sanitize_payload
from app.config import get_settings
from app.core.errors import Conflict, Forbidden, NotFound
from app.core.ids import uuid7
from app.core.time import utc_now_naive
from app.crypto.envelope import open_json
from app.crypto.key_provider import DatabaseKeyProvider
from app.k_anon import Cell, apply_k_anon
from app.models import (
    AssessmentAction,
    Guardian,
    GuardianAlert,
    GuardianConsent,
    Pharmacy,
    SchoolAssessment,
    SchoolStaff,
    Student,
    StudentContactMap,
    Voucher,
    VoucherRedemption,
    Wallet,
    WalletLedger,
)

ACTIONS = ("spoke_to", "referred", "escalated", "contacted")

# Generic guardian alert wording (spec 3.3): no symptoms, no condition names.
GUARDIAN_ALERT_TEXT = "Please contact the school nurse or take her to a clinic soon."


def _staff_school(db: Session, staff_id: uuid.UUID) -> uuid.UUID:
    row = db.execute(select(SchoolStaff).where(SchoolStaff.staff_id == staff_id)).scalars().first()
    if row is None:
        raise Forbidden("staff not bound to a school")
    return row.school_id


def _band(provider: DatabaseKeyProvider, db: Session, assessment: SchoolAssessment) -> str:
    return str(open_json(provider, db, assessment.payload_ciphertext, assessment.key_id)["band"])


def _pseudonym(db: Session, assessment: SchoolAssessment) -> str:
    if assessment.student_id is None:
        return "unlinked"
    student = db.get(Student, assessment.student_id)
    return str(student.pseudonym_id) if student else "unlinked"


def queue(
    db: Session, provider: DatabaseKeyProvider, staff_id: uuid.UUID, limit: int = 50
) -> list[dict[str, Any]]:
    """The nurse flag queue: pseudonym, band, age band, consent state, channel.
    Never answers, never indicators — severity bands and actions only."""
    school_id = _staff_school(db, staff_id)
    rows = (
        db.execute(
            select(SchoolAssessment)
            .where(
                SchoolAssessment.student_id.in_(
                    select(Student.id).where(Student.school_id == school_id)
                )
            )
            .order_by(SchoolAssessment.created_at.desc())
            .limit(limit)
        )
        .scalars()
        .all()
    )
    return [
        {
            "assessment_id": str(row.id),
            "pseudonym": _pseudonym(db, row),
            "band": _band(provider, db, row),
            "age_band": row.age_band,
            "consent_state": row.consent_state,
            "channel": row.channel,
            "requested_contact": row.requested_contact,
            "created_at": row.created_at,
        }
        for row in rows
    ]


def add_action(
    db: Session,
    *,
    staff_id: uuid.UUID,
    assessment_id: uuid.UUID,
    action: str,
    note: str | None,
) -> AssessmentAction:
    if action not in ACTIONS:
        raise Conflict(f"unknown action: {action}")
    if db.get(SchoolAssessment, assessment_id) is None:
        raise NotFound("assessment not found")
    note = sanitize_payload({"note": note or ""})["note"] or None  # never symptom content
    row = AssessmentAction(
        id=uuid7(), assessment_id=assessment_id, action=action, actor_id=staff_id, note=note
    )
    db.add(row)
    db.flush()
    record_event(
        db,
        event_type="assessment_action",
        actor_type="staff",
        actor_id=staff_id,
        actor_role=None,
        resource_type="assessment_action",
        resource_id=row.id,
        payload={"assessment_id": str(assessment_id), "action": action},
    )
    return row


def reidentify(
    db: Session,
    provider: DatabaseKeyProvider,
    *,
    staff_id: uuid.UUID,
    assessment_id: uuid.UUID,
    reason: str,
) -> dict[str, Any]:
    """Spec 3.1: only at ORANGE/RED bands or when the student asked to be
    contacted; typed reason required; audit entry; the encrypted contact map is
    the only readable source."""
    assessment = db.get(SchoolAssessment, assessment_id)
    if assessment is None:
        raise NotFound("assessment not found")
    band = _band(provider, db, assessment)
    if band not in {"ORANGE", "RED"} and not assessment.requested_contact:
        raise Forbidden("re-identification requires ORANGE/RED band or a contact request")
    if not reason or len(reason) < 5:
        raise Conflict("a typed reason is required")
    if assessment.student_id is None:
        raise NotFound("assessment not linked to an enrolled student")
    mapping = (
        db.execute(
            select(StudentContactMap).where(StudentContactMap.student_id == assessment.student_id)
        )
        .scalars()
        .first()
    )
    if mapping is None:
        raise NotFound("contact mapping not recorded")
    contact = open_json(provider, db, mapping.payload_ciphertext, mapping.key_id)
    record_event(
        db,
        event_type="student_reidentified",
        actor_type="staff",
        actor_id=staff_id,
        actor_role=None,
        resource_type="student",
        resource_id=assessment.student_id,
        payload={"reason": reason, "band": band},
    )
    return {"pseudonym": _pseudonym(db, assessment), "contact": contact}


def record_guardian_consent(
    db: Session,
    *,
    staff_id: uuid.UUID,
    assessment_id: uuid.UUID,
    method: str,
    evidence_ref: str | None,
) -> GuardianConsent:
    """Every consent path stores who, when, how, and the version of the text
    (spec 5.3). Method: sms_link | paper | voice."""
    if method not in {"sms_link", "paper", "voice"}:
        raise Conflict(f"unknown consent method: {method}")
    assessment = db.get(SchoolAssessment, assessment_id)
    if assessment is None:
        raise NotFound("assessment not found")
    row = GuardianConsent(
        id=uuid7(),
        assessment_id=assessment_id,
        method=method,
        recorded_by=staff_id,
        text_version=1,
        evidence_ref=evidence_ref,
    )
    db.add(row)
    db.flush()
    assessment.consent_state = "minor_full"  # guardian grant completes the minor's consent
    record_event(
        db,
        event_type="guardian_consent_recorded",
        actor_type="staff",
        actor_id=staff_id,
        actor_role=None,
        resource_type="guardian_consent",
        resource_id=row.id,
        payload={"method": method, "text_version": 1},
    )
    return row


def guardian_alerts(
    db: Session,
    provider: DatabaseKeyProvider,
    sms_send: Any,
) -> list[dict[str, Any]]:
    """RED-only generic guardian alerts (spec 3.3) with the safeguarding
    override: flagged assessments skip the guardian entirely (status recorded,
    never sent)."""
    report: list[dict[str, Any]] = []
    for assessment in db.execute(select(SchoolAssessment)).scalars():
        if _band(provider, db, assessment) != "RED":
            continue
        if assessment.student_id is None:
            continue
        guardian = (
            db.execute(select(Guardian).where(Guardian.student_id == assessment.student_id))
            .scalars()
            .first()
        )
        if guardian is None or not guardian.alert_consent:
            continue
        payload = open_json(provider, db, assessment.payload_ciphertext, assessment.key_id)
        if payload.get("safeguarding"):
            db.add(
                GuardianAlert(
                    id=uuid7(),
                    assessment_id=assessment.id,
                    guardian_id=guardian.id,
                    status="skipped_safeguarding",
                )
            )
            report.append({"assessment": str(assessment.id), "status": "skipped_safeguarding"})
            continue
        try:
            contact = open_json(provider, db, guardian.contact_ciphertext, guardian.key_id)
            sms_send(contact["phone"], GUARDIAN_ALERT_TEXT)
            status = "sent"
        except Exception:  # noqa: BLE001 — delivery failure recorded, not fatal
            status = "failed"
        db.add(
            GuardianAlert(
                id=uuid7(), assessment_id=assessment.id, guardian_id=guardian.id, status=status
            )
        )
        report.append({"assessment": str(assessment.id), "status": status})
    return report


def dashboard(
    db: Session, provider: DatabaseKeyProvider, *, school_id: uuid.UUID, term: str
) -> dict[str, Any]:
    """Aggregate-only dashboard through the k-anonymity module (spec 3.4).
    Never a zero when data is missing — 'not enough data yet'."""
    rows = (
        db.execute(
            select(SchoolAssessment).where(
                SchoolAssessment.student_id.in_(
                    select(Student.id).where(Student.school_id == school_id)
                )
            )
        )
        .scalars()
        .all()
    )
    cells = [
        Cell(key=(f"band_{band}",), value=sum(1 for r in rows if _band(provider, db, r) == band))
        for band in ("GREEN", "YELLOW", "ORANGE", "RED")
    ]
    cells.append(
        Cell(
            key=("consent_pending",),
            value=sum(1 for r in rows if r.consent_state == "minor_assent_only"),
        )
    )
    public = apply_k_anon(total=len(rows), counts=cells).public()
    public["term"] = term
    public["school_id"] = str(school_id)
    return public


def otc_list() -> list[str]:
    """Clinician-approved OTC pain-relief list (config; H7 to sign off). Vouchers
    carry the category only — never a medicine name on the voucher itself."""
    return getattr(get_settings(), "otc_pain_list", ["paracetamol"])


def issue_voucher(
    db: Session,
    *,
    staff_id: uuid.UUID,
    school_id: uuid.UUID,
    assessment_id: uuid.UUID | None = None,
    category: str,
    amount_ksh: int,
    ttl_days: int = 30,
) -> dict[str, Any]:
    """Single-use, expiring voucher; per-student-per-term cap enforced by the
    caller. No medicine name on the voucher (spec 5.3)."""
    if category not in {"sanitary", "otc_pain"}:
        raise Conflict(f"unknown voucher category: {category}")
    code = "SISI-" + secrets.token_hex(4).upper()
    voucher = Voucher(
        id=uuid7(),
        code=code,
        assessment_id=assessment_id,
        school_id=school_id,
        category=category,
        otc_item=otc_list()[0] if category == "otc_pain" else None,
        amount_ksh=amount_ksh,
        issued_by=staff_id,
        expires_at=utc_now_naive() + timedelta(days=ttl_days),
    )
    db.add(voucher)
    db.flush()
    record_event(
        db,
        event_type="voucher_issued",
        actor_type="staff",
        actor_id=staff_id,
        actor_role=None,
        resource_type="voucher",
        resource_id=voucher.id,
        payload={"category": category, "amount_ksh": amount_ksh},
    )
    return {"code": code, "expires_at": voucher.expires_at, "category": category}


def redeem_voucher(
    db: Session,
    *,
    pharmacy_id: uuid.UUID,
    code: str,
    receipt_no: str,
    amount_ksh: int,
    callback: dict[str, Any],
) -> dict[str, Any]:
    """Idempotent redemption: the receipt number is unique — a repeated Daraja
    callback with the same receipt returns the existing redemption (DoD)."""
    existing = (
        db.execute(select(VoucherRedemption).where(VoucherRedemption.receipt_no == receipt_no))
        .scalars()
        .first()
    )
    if existing is not None:
        return {"status": "duplicate", "voucher_id": str(existing.voucher_id)}
    voucher = db.execute(select(Voucher).where(Voucher.code == code)).scalars().first()
    if voucher is None:
        raise NotFound("voucher not found")
    if voucher.status != "issued" or voucher.expires_at < utc_now_naive():
        raise Conflict("voucher already used or expired")
    pharmacy = db.get(Pharmacy, pharmacy_id)
    if pharmacy is None or not pharmacy.verified:
        raise Forbidden("redemption requires a registered, verified pharmacy")
    if amount_ksh != voucher.amount_ksh:
        raise Conflict("amount mismatch; reconciliation will flag this")
    voucher.status = "redeemed"
    voucher.redeemed_at = utc_now_naive()
    voucher.pharmacy_id = pharmacy_id
    db.add(
        VoucherRedemption(
            id=uuid7(),
            voucher_id=voucher.id,
            pharmacy_id=pharmacy_id,
            receipt_no=receipt_no,
            amount_ksh=amount_ksh,
            callback_json=callback,
        )
    )
    db.flush()
    record_event(
        db,
        event_type="voucher_redeemed",
        actor_type="staff",
        actor_id=None,
        actor_role="pharmacy",
        resource_type="voucher",
        resource_id=voucher.id,
        payload={"receipt_no": receipt_no, "amount_ksh": amount_ksh},
    )
    return {"status": "redeemed", "voucher_id": str(voucher.id)}


def reconcile(db: Session) -> dict[str, Any]:
    """Flags mismatches: redemptions whose amount differs from the voucher's."""
    mismatches = []
    for redemption in db.execute(select(VoucherRedemption)).scalars():
        voucher = db.get(Voucher, redemption.voucher_id)
        if voucher is not None and voucher.amount_ksh != redemption.amount_ksh:
            mismatches.append(
                {
                    "voucher_id": str(voucher.id),
                    "expected_ksh": voucher.amount_ksh,
                    "actual_ksh": redemption.amount_ksh,
                    "receipt_no": redemption.receipt_no,
                }
            )
    report = {
        "mismatches": mismatches,
        "redeemed_count": len(db.execute(select(VoucherRedemption)).scalars().all()),
        "generated_at": utc_now_naive().isoformat(),
    }
    return report


def fund_wallet(db: Session, *, owner_type: str, owner_id: uuid.UUID, amount_ksh: int) -> Wallet:
    """Wallet funding (school/admin/employer); ledger is append-only."""
    wallet = (
        db.execute(
            select(Wallet).where(Wallet.owner_type == owner_type, Wallet.owner_id == owner_id)
        )
        .scalars()
        .first()
    )
    if wallet is None:
        wallet = Wallet(id=uuid7(), owner_type=owner_type, owner_id=owner_id, balance_ksh=0)
        db.add(wallet)
        db.flush()
    wallet.balance_ksh += amount_ksh
    db.add(
        WalletLedger(
            id=uuid7(),
            wallet_id=wallet.id,
            delta_ksh=amount_ksh,
            ref_type="funding",
            ref_id=uuid7(),
        )
    )
    db.flush()
    return wallet
