"""Employer endpoints (Phase 7): admin actions (create, bind, fund) and the
own-scoped reads (wallet, ledger, k-anonymized dashboard)."""

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import ProviderDep
from app.api.envelope import ok
from app.auth.deps import require
from app.db import get_db
from app.employer import service
from app.models import StaffUser

router = APIRouter(tags=["employer"])

AdminDep = Annotated[StaffUser, Depends(require("employer:admin"))]
WalletDep = Annotated[StaffUser, Depends(require("employer:wallet"))]
DashboardDep = Annotated[StaffUser, Depends(require("employer:dashboard"))]


class CreateIn(BaseModel):
    name: str = Field(min_length=2, max_length=255)
    county: str | None = Field(default=None, max_length=128)


class BindIn(BaseModel):
    staff_id: uuid.UUID
    role_within: str = Field(default="employer_admin", pattern=r"^employer_admin$")


class FundIn(BaseModel):
    # Positivity is enforced in the service (Conflict), so the ledger rule lives
    # with the ledger code and not only in the request schema.
    amount_ksh: int


class LinkIn(BaseModel):
    user_id: uuid.UUID


@router.post("/employers")
def create_employer(
    body: CreateIn,
    db: Annotated[Session, Depends(get_db)],
    staff: AdminDep,
) -> dict[str, Any]:
    employer = service.create_employer(db, staff_id=staff.id, name=body.name, county=body.county)
    db.commit()
    return ok({"id": str(employer.id), "name": employer.name, "status": employer.status})


@router.post("/employers/{employer_id}/staff")
def bind_staff(
    employer_id: uuid.UUID,
    body: BindIn,
    db: Annotated[Session, Depends(get_db)],
    staff: AdminDep,
) -> dict[str, Any]:
    row = service.bind_staff(
        db,
        staff_id=body.staff_id,
        employer_id=employer_id,
        role_within=body.role_within,
    )
    db.commit()
    return ok(
        {
            "id": str(row.id),
            "employer_id": str(row.employer_id),
            "role_within": row.role_within,
        }
    )


@router.post("/employers/{employer_id}/fund")
def fund(
    employer_id: uuid.UUID,
    body: FundIn,
    db: Annotated[Session, Depends(get_db)],
    staff: AdminDep,
) -> dict[str, Any]:
    wallet = service.fund(
        db, staff_id=staff.id, employer_id=employer_id, amount_ksh=body.amount_ksh
    )
    db.commit()
    return ok({"balance_ksh": wallet.balance_ksh})


@router.post("/employers/{employer_id}/employees")
def link_employee(
    employer_id: uuid.UUID,
    body: LinkIn,
    db: Annotated[Session, Depends(get_db)],
    staff: AdminDep,
) -> dict[str, Any]:
    result = service.link_employee(
        db, staff_id=staff.id, employer_id=employer_id, user_id=body.user_id
    )
    db.commit()
    return ok(result)


@router.get("/employers/{employer_id}/wallet")
def wallet(
    employer_id: uuid.UUID,
    db: Annotated[Session, Depends(get_db)],
    staff: WalletDep,
) -> dict[str, Any]:
    service.resolve_employer(db, staff, employer_id)
    return ok(service.wallet_view(db, employer_id))


@router.get("/employers/{employer_id}/ledger")
def ledger(
    employer_id: uuid.UUID,
    db: Annotated[Session, Depends(get_db)],
    staff: WalletDep,
) -> dict[str, Any]:
    service.resolve_employer(db, staff, employer_id)
    return ok(service.ledger_view(db, employer_id))


@router.get("/employers/{employer_id}/dashboard")
def dashboard(
    employer_id: uuid.UUID,
    db: Annotated[Session, Depends(get_db)],
    provider: ProviderDep,
    staff: DashboardDep,
    term: str = service.DEFAULT_TERM,
) -> dict[str, Any]:
    service.resolve_employer(db, staff, employer_id)
    return ok(service.dashboard(db, provider, employer_id=employer_id, term=term))
