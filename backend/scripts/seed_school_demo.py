"""Seed the Phase 4 demo school world (idempotent, synthetic ONLY):
- school 1 (fixed UUID, used by the web console defaults) with 4 assessments
  at mixed bands -> queue has rows, dashboard shows 'not enough data yet'
- school 2 (fixed UUID ...0002 "Demo Academy", Kisumu — Phase 8 deliverable 5)
  with 30 GREEN-heavy assessments -> its dashboard reports enough_data and the
  small band cells come back suppressed (spec 3.4)
- e2e staff (nurse + school admin for school 1, nurse for school 2) with a
  FIXED TOTP secret so every demo account opens with the same authenticator
- 25 enrolled students per school with encrypted contact maps + guardians
  (alert consent)
- a verified pharmacy for redemption tests
NEVER real patient data (non-negotiable 2). Safe to re-run: the second run is a
no-op and still exits 0."""

import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.staff import _seal_totp, create_staff
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
SCHOOL_2_ID = uuid.UUID("00000000-0000-0000-0000-000000000002")
# Fixed base32 secret ("Hello!") so Playwright can compute the TOTP in JS.
E2E_TOTP_SECRET = "JBSWY3DPEHPK3PXP"  # noqa: S105 — synthetic e2e demo secret, never real

STUDENTS_PER_SCHOOL = 25
# School 1 keeps exactly 4 assessments: the console e2e asserts its dashboard
# still reads "not enough data yet" (MIN_STUDENTS = 20, app/k_anon.py) and its
# nurse queue keeps rows. School 2 sits above the threshold with one tiny
# YELLOW cell so GREEN publishes and the small cells are suppressed.
ASSESSMENT_BANDS: dict[uuid.UUID, tuple[str, ...]] = {
    SCHOOL_ID: ("GREEN", "YELLOW", "ORANGE", "RED"),
    SCHOOL_2_ID: ("GREEN",) * 27 + ("YELLOW", "ORANGE", "RED"),
}
# Synthetic contact blocks, one per school (never real subscriber numbers and
# never colliding with the +2547000001xx..+2547000004xx blocks owned by the
# seed_demo / seed_corridor_demo / seed_employer_demo user phones).
CONTACT_OFFSET: dict[uuid.UUID, int] = {SCHOOL_ID: 0, SCHOOL_2_ID: 500}


def _ensure_school(db: Session, school_id: uuid.UUID, name: str, county: str) -> School:
    school = db.get(School, school_id)
    if school is None:
        school = School(id=school_id, name=name, county=county)
        db.add(school)
        db.flush()
        print(f"[seed] school {name} ({school_id}) created")
    return school


def _ensure_staff(
    db: Session,
    provider: DatabaseKeyProvider,
    *,
    email: str,
    role: str,
    school: School,
    role_within: str,
) -> StaffUser:
    """Staff account with the FIXED demo TOTP secret, bound to one school.
    Idempotent: an existing account keeps its secret and its binding."""
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
        blob, _key_id = _seal_totp(provider, db, staff.id, E2E_TOTP_SECRET)
        staff.totp_secret_encrypted = blob
        db.flush()
        print(f"[seed] staff {email} (role={role}) with fixed e2e TOTP")
    binding = (
        db.execute(select(SchoolStaff).where(SchoolStaff.staff_id == staff.id)).scalars().first()
    )
    if binding is None:
        db.add(
            SchoolStaff(
                id=uuid.uuid4(),
                staff_id=staff.id,
                school_id=school.id,
                role_within=role_within,
            )
        )
        print(f"[seed] bound {email} to {school.name}")
    return staff


def _ensure_students(
    db: Session, provider: DatabaseKeyProvider, school: School, offset: int
) -> list[Student]:
    """One school's students, each with an encrypted contact map and a guardian
    (alert consent). Idempotent: returns the existing students unchanged."""
    students = list(
        db.execute(select(Student).where(Student.school_id == school.id)).scalars().all()
    )
    if students:
        return students
    for i in range(STUDENTS_PER_SCHOOL):
        student = Student(id=uuid.uuid4(), school_id=school.id, pseudonym_id=uuid.uuid4())
        db.add(student)
        db.flush()
        contact_blob, key_id = seal_json(
            provider,
            db,
            "student",
            student.id,
            {"name": f"Student {i}", "phone": f"+2547{offset + i:08d}"},
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
            {"name": f"Guardian {i}", "phone": f"+2548{offset + i:08d}"},
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
        db.flush()
        students.append(student)
    print(f"[seed] {len(students)} synthetic students + contact maps + guardians ({school.name})")
    return students


def _ensure_assessments(
    db: Session,
    provider: DatabaseKeyProvider,
    school: School,
    students: list[Student],
    bands: tuple[str, ...],
) -> int:
    """One encrypted USSD assessment per band entry, spread across the school's
    students. Idempotent: nothing is added once the school has any assessment.
    Returns the number created."""
    existing = (
        db.execute(
            select(SchoolAssessment)
            .where(
                SchoolAssessment.student_id.in_(
                    select(Student.id).where(Student.school_id == school.id)
                )
            )
            .limit(1)
        )
        .scalars()
        .first()
    )
    if existing is not None:
        return 0
    for index, band in enumerate(bands):
        assessment_id = uuid.uuid4()
        payload = {
            "band": band,
            "indicators": ["x"],
            "urgent": band == "RED",
            "safeguarding": False,
            "answers": {"pain": 7},
            "age": 15,
            "language": "en",
            "rule_set_version": "ontology-1.0",
        }
        blob, key_id = seal_json(provider, db, "assessment", assessment_id, payload)
        db.add(
            SchoolAssessment(
                id=assessment_id,
                phone_hash=uuid.uuid4().hex,
                age_band="13-17",
                language="en",
                consent_state="self_granted",
                payload_ciphertext=blob,
                key_id=key_id,
                channel="ussd",
                student_id=students[index % len(students)].id,
            )
        )
    mix = "/".join(dict.fromkeys(bands))
    print(f"[seed] {len(bands)} synthetic assessments ({mix}) for {school.name}")
    return len(bands)


def main() -> int:
    settings = get_settings()
    if settings.env not in {"dev", "demo"}:
        print("seed_school_demo refuses to run outside dev/demo")
        return 1
    provider = DatabaseKeyProvider(settings)
    with SessionLocal() as db:
        school = _ensure_school(db, SCHOOL_ID, "Demo Secondary", "Nairobi")
        school_2 = _ensure_school(db, SCHOOL_2_ID, "Demo Academy", "Kisumu")

        _ensure_staff(
            db,
            provider,
            email="nurse-e2e@sisi.demo",
            role="nurse",
            school=school,
            role_within="nurse",
        )
        _ensure_staff(
            db,
            provider,
            email="schooladmin-e2e@sisi.demo",
            role="school_admin",
            school=school,
            role_within="school_admin",
        )
        _ensure_staff(
            db,
            provider,
            email="nurse2-e2e@sisi.demo",
            role="nurse",
            school=school_2,
            role_within="nurse",
        )

        for school_row in (school, school_2):
            students = _ensure_students(db, provider, school_row, CONTACT_OFFSET[school_row.id])
            _ensure_assessments(db, provider, school_row, students, ASSESSMENT_BANDS[school_row.id])

        pharmacy = db.execute(select(Pharmacy)).scalars().first()
        if pharmacy is None:
            db.add(Pharmacy(id=uuid.uuid4(), name="Demo Pharmacy", verified=True))
            print("[seed] verified pharmacy")
        db.commit()
    print("[seed] school demo done")
    return 0


if __name__ == "__main__":
    sys.exit(main())
