"""Seed the Phase 4 demo school world (idempotent, synthetic ONLY):
- school 1 (fixed UUID, used by the web console defaults) with 4 assessments
  at mixed bands -> queue has rows, dashboard shows 'not enough data yet'
- e2e staff (nurse + school admin) with a FIXED TOTP secret for Playwright
- 25 enrolled students with encrypted contact maps + guardians (alert consent)
- a verified pharmacy for redemption tests
NEVER real patient data (non-negotiable 2)."""

import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select

from app.auth.staff import create_staff
from app.config import get_settings
from app.crypto.envelope import seal_json
from app.crypto.key_provider import DatabaseKeyProvider
from app.db import SessionLocal
from app.models import (
    Guardian,
    Pharmacy,
    School,
    SchoolAssessment,
    SchoolStaff,
    StaffUser,
    Student,
    StudentContactMap,
)

SCHOOL_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")
# Fixed base32 secret ("Hello!") so Playwright can compute the TOTP in JS.
E2E_TOTP_SECRET = "JBSWY3DPEHPK3PXP"  # noqa: S105 — synthetic e2e demo secret, never real


def main() -> int:
    settings = get_settings()
    if settings.env not in {"dev", "demo"}:
        print("seed_school_demo refuses to run outside dev/demo")
        return 1
    provider = DatabaseKeyProvider(settings)
    with SessionLocal() as db:
        school = db.get(School, SCHOOL_ID)
        if school is None:
            school = School(id=SCHOOL_ID, name="Demo Secondary", county="Nairobi")
            db.add(school)
            db.flush()
            print("[seed] school created")

        for email, role in (
            ("nurse-e2e@sisi.demo", "nurse"),
            ("schooladmin-e2e@sisi.demo", "school_admin"),
        ):
            staff = db.execute(select(StaffUser).where(StaffUser.email == email)).scalars().first()
            if staff is None:
                staff = create_staff(
                    db,
                    provider,
                    email=email,
                    password="demo-password-123",  # noqa: S106 — demo seed only
                    role=role,
                )
                # Pin the TOTP secret to the fixed e2e secret instead of a random one.
                from app.auth.staff import _seal_totp

                blob, _key_id = _seal_totp(provider, db, staff.id, E2E_TOTP_SECRET)
                staff.totp_secret_encrypted = blob
                db.flush()
                print(f"[seed] staff {email} (role={role}) with fixed e2e TOTP")
            binding = db.execute(
                select(SchoolStaff).where(SchoolStaff.staff_id == staff.id)
            ).scalars().first()
            if binding is None:
                db.add(SchoolStaff(id=uuid.uuid4(), staff_id=staff.id, school_id=school.id,
                                   role_within="nurse" if role == "nurse" else "school_admin"))
                print(f"[seed] bound {email} to the school")

        students = db.execute(select(Student).where(Student.school_id == school.id)).scalars().all()
        if not students:
            for i in range(25):
                student = Student(id=uuid.uuid4(), school_id=school.id, pseudonym_id=uuid.uuid4())
                db.add(student)
                db.flush()
                contact_blob, key_id = seal_json(
                    provider, db, "student", student.id,
                    {"name": f"Student {i}", "phone": f"+2547{i:08d}"},
                )
                db.add(StudentContactMap(id=uuid.uuid4(), student_id=student.id,
                                         payload_ciphertext=contact_blob, key_id=key_id))
                guardian_blob, g_key_id = seal_json(
                    provider, db, "guardian", student.id,
                    {"name": f"Guardian {i}", "phone": f"+2548{i:08d}"},
                )
                db.add(Guardian(id=uuid.uuid4(), student_id=student.id,
                                contact_ciphertext=guardian_blob, key_id=g_key_id,
                                alert_consent=True))
                db.flush()
                students.append(student)
            print("[seed] 25 synthetic students + contact maps + guardians")

        has_assessments = db.execute(select(SchoolAssessment)).scalars().first()
        if has_assessments is None:
            for band, idx in (("GREEN", 0), ("YELLOW", 1), ("ORANGE", 2), ("RED", 3)):
                assessment_id = uuid.uuid4()
                payload = {"band": band, "indicators": ["x"], "urgent": band == "RED",
                           "safeguarding": False, "answers": {"pain": 7}, "age": 15,
                           "language": "en", "rule_set_version": "ontology-1.0"}
                blob, key_id = seal_json(provider, db, "assessment", assessment_id, payload)
                db.add(SchoolAssessment(
                    id=assessment_id, phone_hash=uuid.uuid4().hex, age_band="13-17",
                    language="en", consent_state="self_granted", payload_ciphertext=blob,
                    key_id=key_id, channel="ussd", student_id=students[idx].id,
                ))
            print("[seed] 4 synthetic assessments (GREEN/YELLOW/ORANGE/RED)")

        pharmacy = db.execute(select(Pharmacy)).scalars().first()
        if pharmacy is None:
            db.add(Pharmacy(id=uuid.uuid4(), name="Demo Pharmacy", verified=True))
            print("[seed] verified pharmacy")
        db.commit()
    print("[seed] school demo done")
    return 0


if __name__ == "__main__":
    sys.exit(main())
