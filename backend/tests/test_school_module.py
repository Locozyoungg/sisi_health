"""Phase 4 backend tests: nurse console privacy, re-identification gating and
audit, guardian consents/alerts, vouchers (single-use, idempotency,
reconciliation), k-anonymized dashboard."""

import uuid
from datetime import timedelta

import pytest
from sqlalchemy import select

from app.audit.verifier import verify_chain
from app.core.errors import Conflict, Forbidden
from app.core.time import utc_now_naive
from app.crypto.envelope import seal_json
from app.models import (
    AuditEvent,
    Guardian,
    GuardianAlert,
    GuardianConsent,
    Pharmacy,
    School,
    SchoolAssessment,
    SchoolStaff,
    Student,
    StudentContactMap,
    Voucher,
    VoucherRedemption,
)
from app.school import service


@pytest.fixture()
def school_world(db, provider, make_staff):
    """A school, enrolled students with contact maps + guardians, a pharmacy,
    and assessments at various bands."""
    school = School(id=uuid.uuid4(), name="Demo Secondary", county="Nairobi")
    db.add(school)
    nurse = make_staff("nurse")
    db.add(
        SchoolStaff(id=uuid.uuid4(), staff_id=nurse.id, school_id=school.id, role_within="nurse")
    )
    admin = make_staff("school_admin")
    db.add(
        SchoolStaff(
            id=uuid.uuid4(), staff_id=admin.id, school_id=school.id, role_within="school_admin"
        )
    )
    pharmacy = Pharmacy(
        id=uuid.uuid4(), name="Demo Pharmacy", verified=True, last_verified_at=utc_now_naive()
    )
    db.add(pharmacy)
    students = []
    for i in range(25):
        student = Student(id=uuid.uuid4(), school_id=school.id, pseudonym_id=uuid.uuid4())
        db.add(student)
        contact_blob, key_id = seal_json(
            provider, db, "student", student.id, {"name": f"Student {i}", "phone": f"+2547{i:08d}"}
        )
        db.add(
            StudentContactMap(
                id=uuid.uuid4(),
                student_id=student.id,
                payload_ciphertext=contact_blob,
                key_id=key_id,
            )
        )
        guardian_blob, g_key_id = seal_json(
            provider,
            db,
            "guardian",
            student.id,
            {"name": f"Guardian {i}", "phone": f"+2548{i:08d}"},
        )
        db.add(
            Guardian(
                id=uuid.uuid4(),
                student_id=student.id,
                contact_ciphertext=guardian_blob,
                key_id=g_key_id,
                alert_consent=True,
            )
        )
        students.append(student)
    db.flush()

    def assessment(
        band: str, student_idx: int, safeguarding: bool = False, consent: str = "self_granted"
    ):
        assessment_id = uuid.uuid4()  # owns its data key (erasure finds it)
        payload = {
            "band": band,
            "indicators": ["x"],
            "urgent": band == "RED",
            "safeguarding": safeguarding,
            "answers": {"pain": 7},
            "age": 15,
            "language": "en",
        }
        blob, key_id = seal_json(provider, db, "assessment", assessment_id, payload)
        row = SchoolAssessment(
            id=assessment_id,
            phone_hash=uuid.uuid4().hex,
            age_band="13-17",
            language="en",
            consent_state=consent,
            payload_ciphertext=blob,
            key_id=key_id,
            channel="ussd",
            student_id=students[student_idx].id,
        )
        db.add(row)
        return row

    red = assessment("RED", 0)
    orange = assessment("ORANGE", 1)
    green = assessment("GREEN", 2)
    red_safe = assessment("RED", 3, safeguarding=True)
    db.commit()
    return {
        "school": school,
        "nurse": nurse,
        "admin": admin,
        "pharmacy": pharmacy,
        "red": red,
        "orange": orange,
        "green": green,
        "red_safe": red_safe,
    }


def test_queue_never_exposes_narratives(db, provider, school_world):
    rows = service.queue(db, provider, school_world["nurse"].id)
    assert len(rows) == 4
    for row in rows:
        assert set(row.keys()) == {
            "assessment_id",
            "pseudonym",
            "band",
            "age_band",
            "consent_state",
            "channel",
            "requested_contact",
            "created_at",
        }
        assert "answers" not in row and "indicators" not in row
        assert row["pseudonym"] != "unlinked"


def test_reidentify_gates_on_band(db, provider, school_world):
    with pytest.raises(Forbidden):
        service.reidentify(
            db,
            provider,
            staff_id=school_world["nurse"].id,
            assessment_id=school_world["green"].id,
            reason="parent asked to call",
        )
    result = service.reidentify(
        db,
        provider,
        staff_id=school_world["nurse"].id,
        assessment_id=school_world["orange"].id,
        reason="nurse follow-up needed",
    )
    assert result["contact"]["name"].startswith("Student")


def test_reidentify_requires_reason_and_writes_audit(db, provider, school_world):
    with pytest.raises(Conflict):
        service.reidentify(
            db,
            provider,
            staff_id=school_world["nurse"].id,
            assessment_id=school_world["red"].id,
            reason="x",
        )
    service.reidentify(
        db,
        provider,
        staff_id=school_world["nurse"].id,
        assessment_id=school_world["red"].id,
        reason="urgent follow-up required",
    )
    db.commit()
    events = db.execute(select(AuditEvent)).scalars().all()
    assert any(e.event_type == "student_reidentified" for e in events)
    assert verify_chain(db)["ok"] is True


def test_guardian_consent_methods_recorded(db, provider, school_world):
    row = service.record_guardian_consent(
        db,
        staff_id=school_world["nurse"].id,
        assessment_id=school_world["red"].id,
        method="voice",
        evidence_ref="rec-001.wav",
    )
    db.commit()
    stored = db.get(GuardianConsent, row.id)
    assert stored.method == "voice" and stored.text_version == 1
    assert db.get(SchoolAssessment, school_world["red"].id).consent_state == "minor_full"


def test_guardian_alerts_red_only_and_safeguarding_override(db, provider, school_world):
    sent: list[str] = []
    report = service.guardian_alerts(db, provider, lambda phone, msg: sent.append(phone))
    db.commit()
    statuses = {r["status"] for r in report}
    assert "sent" in statuses  # red assessment alerted
    assert "skipped_safeguarding" in statuses  # safeguarding override skipped its guardian
    assert len(sent) == 1
    alerts = db.execute(select(GuardianAlert)).scalars().all()
    assert any(a.status == "skipped_safeguarding" for a in alerts)


def test_dashboard_k_anonymized(db, provider, school_world):
    public = service.dashboard(db, provider, school_id=school_world["school"].id, term="2026-T1")
    # Only 4 assessments exist: below the 20-student threshold nothing publishes.
    assert public["enough_data"] is False
    assert public["message"] == "not_enough_data"


def test_dashboard_above_threshold_suppresses_small_cells(db, provider, school_world):
    """≥20 assessments: bands publish, but any 1..4 cell is suppressed with a
    complementary partner (spec 3.4)."""
    from app.models import Student

    students = db.execute(select(Student)).scalars().all()
    for i in range(5, 25):  # 20 more assessments -> 24 total
        assessment_id = uuid.uuid4()
        payload = {
            "band": "GREEN",
            "indicators": [],
            "urgent": False,
            "safeguarding": False,
            "answers": {},
            "age": 14,
            "language": "en",
        }
        blob, key_id = seal_json(provider, db, "assessment", assessment_id, payload)
        db.add(
            SchoolAssessment(
                id=assessment_id,
                phone_hash=uuid.uuid4().hex,
                age_band="13-17",
                language="en",
                consent_state="minor_assent_only",
                payload_ciphertext=blob,
                key_id=key_id,
                channel="ussd",
                student_id=students[i].id,
            )
        )
    db.commit()
    public = service.dashboard(db, provider, school_id=school_world["school"].id, term="2026-T1")
    assert public["enough_data"] is True
    cells = public["cells"]
    # GREEN (21) publishes; RED (1) and consent_pending (20) — RED must be suppressed.
    assert cells["band_GREEN"] == 21
    assert cells["band_RED"] is None  # suppressed, never a small number
    suppressed = [k for k, v in cells.items() if v is None]
    assert len(suppressed) >= 1


def test_voucher_issue_redeem_and_idempotency(db, school_world):
    issued = service.issue_voucher(
        db,
        staff_id=school_world["admin"].id,
        school_id=school_world["school"].id,
        assessment_id=school_world["red"].id,
        category="sanitary",
        amount_ksh=300,
    )
    db.commit()
    assert issued["code"].startswith("SISI-")
    first = service.redeem_voucher(
        db,
        pharmacy_id=school_world["pharmacy"].id,
        code=issued["code"],
        receipt_no="MPESA-RCPT-1",
        amount_ksh=300,
        callback={"ok": True},
    )
    db.commit()
    assert first["status"] == "redeemed"
    # Same receipt redelivered: idempotent duplicate, no second redemption.
    again = service.redeem_voucher(
        db,
        pharmacy_id=school_world["pharmacy"].id,
        code=issued["code"],
        receipt_no="MPESA-RCPT-1",
        amount_ksh=300,
        callback={"ok": True},
    )
    assert again["status"] == "duplicate"
    assert len(db.execute(select(VoucherRedemption)).scalars().all()) == 1
    # The voucher itself is single-use.
    with pytest.raises(Conflict):
        service.redeem_voucher(
            db,
            pharmacy_id=school_world["pharmacy"].id,
            code=issued["code"],
            receipt_no="MPESA-RCPT-2",
            amount_ksh=300,
            callback={},
        )


def test_voucher_reconciliation_flags_mismatches(db, school_world):
    issued = service.issue_voucher(
        db,
        staff_id=school_world["admin"].id,
        school_id=school_world["school"].id,
        category="otc_pain",
        amount_ksh=100,
    )
    db.commit()
    with pytest.raises(Conflict):
        service.redeem_voucher(
            db,
            pharmacy_id=school_world["pharmacy"].id,
            code=issued["code"],
            receipt_no="MPESA-RCPT-MISMATCH",
            amount_ksh=150,
            callback={},
        )
    db.rollback()
    report = service.reconcile(db)
    assert report["redeemed_count"] == 0


def test_voucher_expiry_blocks_redemption(db, school_world):
    issued = service.issue_voucher(
        db,
        staff_id=school_world["admin"].id,
        school_id=school_world["school"].id,
        category="sanitary",
        amount_ksh=300,
        ttl_days=1,
    )
    db.commit()
    voucher = db.execute(select(Voucher).where(Voucher.code == issued["code"])).scalars().first()
    voucher.expires_at = utc_now_naive() - timedelta(days=1)
    db.commit()
    with pytest.raises(Conflict):
        service.redeem_voucher(
            db,
            pharmacy_id=school_world["pharmacy"].id,
            code=issued["code"],
            receipt_no="MPESA-RCPT-EXPIRED",
            amount_ksh=300,
            callback={},
        )
