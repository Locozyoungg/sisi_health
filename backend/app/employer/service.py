"""Employer service (Phase 7): employer records, staff binding, wallet (reusing
the Phase 4 wallet/ledger tables with owner_type='employer') and the aggregate
k-anonymized dashboard.

Privacy posture: the dashboard publishes band cells and a total only — never an
employee row, never a name, never a band per person. Cells pass through
`app.k_anon` so small cells are suppressed with complementary suppression and
below the threshold the answer is "not enough data yet", never a zero (spec 3.4).
The employer link (`core.users.employer_id`) is an admin-action opt-in and every
create/bind/fund writes an audit event with a counts-only payload."""

import uuid
from collections.abc import Sequence
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit.service import record_event
from app.core.errors import Conflict, Forbidden, NotFound
from app.core.ids import uuid7
from app.crypto.envelope import open_json
from app.crypto.key_provider import DatabaseKeyProvider
from app.k_anon import Cell, apply_k_anon
from app.models import (
    Employer,
    EmployerStaff,
    RuleEvaluation,
    StaffUser,
    User,
    Wallet,
    WalletLedger,
)
from app.school.service import fund_wallet

# Same four bands the deterministic rules engine can assign (non-negotiable 1:
# the engine decides the band; this module only counts them).
BANDS = ("GREEN", "YELLOW", "ORANGE", "RED")

BIND_ROLES = ("employer_admin",)

DEFAULT_TERM = "2026-T1"


def create_employer(db: Session, *, staff_id: uuid.UUID, name: str, county: str | None) -> Employer:
    """Register an employer. The name is stored on the row only — never in the
    audit payload (audit payloads are counts-only)."""
    name = name.strip()
    if len(name) < 2:
        raise Conflict("employer name is required")
    employer = Employer(id=uuid7(), name=name, county=county, status="active")
    db.add(employer)
    db.flush()
    record_event(
        db,
        event_type="employer_created",
        actor_type="staff",
        actor_id=staff_id,
        actor_role=None,
        resource_type="employer",
        resource_id=employer.id,
        payload={"county": county, "status": employer.status},
    )
    return employer


def bind_staff(
    db: Session,
    *,
    staff_id: uuid.UUID,
    employer_id: uuid.UUID,
    role_within: str = "employer_admin",
) -> EmployerStaff:
    """Bind a staff account to an employer. Idempotent for the same pair."""
    if role_within not in BIND_ROLES:
        raise Conflict(f"unknown employer role: {role_within}")
    if db.get(Employer, employer_id) is None:
        raise NotFound("employer not found")
    if db.get(StaffUser, staff_id) is None:
        raise NotFound("staff not found")
    existing = (
        db.execute(
            select(EmployerStaff).where(
                EmployerStaff.staff_id == staff_id, EmployerStaff.employer_id == employer_id
            )
        )
        .scalars()
        .first()
    )
    if existing is not None:
        return existing
    row = EmployerStaff(
        id=uuid7(), staff_id=staff_id, employer_id=employer_id, role_within=role_within
    )
    db.add(row)
    db.flush()
    record_event(
        db,
        event_type="employer_staff_bound",
        actor_type="staff",
        actor_id=staff_id,
        actor_role=None,
        resource_type="employer_staff",
        resource_id=row.id,
        payload={"employer_id": str(employer_id), "role_within": role_within},
    )
    return row


def resolve_employer(db: Session, staff: StaffUser, employer_id: uuid.UUID) -> Employer:
    """Own-scoping: an `employer_admin` may only reach the employer it is bound to
    (any other employer id — or none — is Forbidden); a `super_admin` may reach
    any employer id."""
    employer = db.get(Employer, employer_id)
    if employer is None:
        raise NotFound("employer not found")
    if staff.role == "super_admin":
        return employer
    bindings = (
        db.execute(select(EmployerStaff).where(EmployerStaff.staff_id == staff.id)).scalars().all()
    )
    if not bindings:
        raise Forbidden("staff not bound to an employer")
    if not any(b.employer_id == employer_id for b in bindings):
        raise Forbidden("not your employer")
    return employer


def fund(db: Session, *, staff_id: uuid.UUID, employer_id: uuid.UUID, amount_ksh: int) -> Wallet:
    """Fund an employer wallet. Ledger rows are append-only (written by
    `school.service.fund_wallet`) and funding must be strictly positive."""
    if amount_ksh <= 0:
        raise Conflict("funding amount must be greater than zero")
    if db.get(Employer, employer_id) is None:
        raise NotFound("employer not found")
    wallet = fund_wallet(db, owner_type="employer", owner_id=employer_id, amount_ksh=amount_ksh)
    record_event(
        db,
        event_type="employer_wallet_funded",
        actor_type="staff",
        actor_id=staff_id,
        actor_role=None,
        resource_type="wallet",
        resource_id=wallet.id,
        payload={"amount_ksh": amount_ksh, "owner_type": "employer"},
    )
    return wallet


def wallet_view(db: Session, employer_id: uuid.UUID) -> dict[str, Any]:
    """Wallet balance. A wallet row only exists after the first funding; an
    unfunded employer still gets a 0 balance (not an error)."""
    wallet = (
        db.execute(
            select(Wallet).where(Wallet.owner_type == "employer", Wallet.owner_id == employer_id)
        )
        .scalars()
        .first()
    )
    return {
        "employer_id": str(employer_id),
        "balance_ksh": wallet.balance_ksh if wallet else 0,
        "updated_at": wallet.updated_at if wallet else None,
    }


def ledger_view(db: Session, employer_id: uuid.UUID) -> list[dict[str, Any]]:
    """Ledger entries, newest first. Append-only: this module has no update or
    delete path — a correction is a new `reversal` row."""
    wallet = (
        db.execute(
            select(Wallet).where(Wallet.owner_type == "employer", Wallet.owner_id == employer_id)
        )
        .scalars()
        .first()
    )
    if wallet is None:
        return []
    rows = (
        db.execute(
            select(WalletLedger)
            .where(WalletLedger.wallet_id == wallet.id)
            # created_at is the documented order; the uuid7 id breaks ties for
            # rows written in the same transaction.
            .order_by(WalletLedger.created_at.desc(), WalletLedger.id.desc())
        )
        .scalars()
        .all()
    )
    return [
        {
            "delta_ksh": row.delta_ksh,
            "ref_type": row.ref_type,
            "ref_id": str(row.ref_id),
            "created_at": row.created_at,
        }
        for row in rows
    ]


def _band(provider: DatabaseKeyProvider, db: Session, row: RuleEvaluation) -> str:
    return str(open_json(provider, db, row.payload_ciphertext, row.key_id)["band"])


def dashboard(
    db: Session, provider: DatabaseKeyProvider, *, employer_id: uuid.UUID, term: str
) -> dict[str, Any]:
    """Aggregate-only dashboard through the k-anonymity module (spec 3.4) — the
    same module the school dashboard uses. Cells are band counts plus the
    evaluation total; small cells are suppressed with complementary suppression
    and below MIN_STUDENTS linked employees nothing is published at all.

    `term` is decorative until a real term calendar exists (the school dashboard
    behaves the same way): it is echoed on the response and no date filtering is
    applied — every evaluation of a currently linked employee is counted."""
    employees = (
        db.execute(select(User).where(User.employer_id == employer_id, User.status == "active"))
        .scalars()
        .all()
    )
    user_ids = [employee.id for employee in employees]
    rows: Sequence[RuleEvaluation] = []
    if user_ids:
        rows = (
            db.execute(select(RuleEvaluation).where(RuleEvaluation.user_id.in_(user_ids)))
            .scalars()
            .all()
        )
    bands = [_band(provider, db, row) for row in rows]
    cells = [Cell(key=(f"band_{band}",), value=bands.count(band)) for band in BANDS]
    cells.append(Cell(key=("evaluations_total",), value=len(rows)))
    public = apply_k_anon(total=len(employees), counts=cells).public()
    public["term"] = term
    public["employer_id"] = str(employer_id)
    return public


def link_employee(
    db: Session, *, staff_id: uuid.UUID, employer_id: uuid.UUID, user_id: uuid.UUID
) -> dict[str, Any]:
    """Opt-in employer linkage (A39): a super_admin action that sets
    `users.employer_id`. Audited; counts-only payload."""
    if db.get(Employer, employer_id) is None:
        raise NotFound("employer not found")
    user = db.get(User, user_id)
    if user is None:
        raise NotFound("user not found")
    user.employer_id = employer_id
    record_event(
        db,
        event_type="employer_employee_linked",
        actor_type="staff",
        actor_id=staff_id,
        actor_role=None,
        resource_type="user",
        resource_id=user.id,
        payload={"employer_id": str(employer_id)},
    )
    return {"user_id": str(user.id), "employer_id": str(employer_id)}
