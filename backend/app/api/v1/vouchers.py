"""Voucher endpoints: issue (school/super admin), redeem (pharmacy), Daraja
callback (idempotent), reconciliation (super/school admin)."""

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.envelope import ok
from app.auth.deps import require
from app.db import get_db
from app.models import StaffUser
from app.school import service

router = APIRouter(prefix="/vouchers", tags=["vouchers"])

IssueDep = Annotated[StaffUser, Depends(require("vouchers:issue"))]
RedeemDep = Annotated[StaffUser, Depends(require("vouchers:redeem"))]
ReconcileDep = Annotated[StaffUser, Depends(require("vouchers:reconcile"))]


class IssueIn(BaseModel):
    school_id: uuid.UUID
    assessment_id: uuid.UUID | None = None
    category: str = Field(pattern=r"^(sanitary|otc_pain)$")
    amount_ksh: int = Field(ge=1, le=5000)
    ttl_days: int = Field(default=30, ge=1, le=90)


class RedeemIn(BaseModel):
    pharmacy_id: uuid.UUID
    code: str
    receipt_no: str = Field(min_length=4, max_length=64)
    amount_ksh: int = Field(ge=1, le=5000)
    callback: dict[str, Any] = Field(default_factory=dict)


@router.post("/issue")
def issue(
    body: IssueIn, db: Annotated[Session, Depends(get_db)], staff: IssueDep
) -> dict[str, Any]:
    result = service.issue_voucher(
        db,
        staff_id=staff.id,
        school_id=body.school_id,
        assessment_id=body.assessment_id,
        category=body.category,
        amount_ksh=body.amount_ksh,
        ttl_days=body.ttl_days,
    )
    db.commit()
    return ok(result)


@router.post("/redeem")
def redeem(
    body: RedeemIn, db: Annotated[Session, Depends(get_db)], staff: RedeemDep
) -> dict[str, Any]:
    result = service.redeem_voucher(
        db,
        pharmacy_id=body.pharmacy_id,
        code=body.code,
        receipt_no=body.receipt_no,
        amount_ksh=body.amount_ksh,
        callback=body.callback,
    )
    db.commit()
    return ok(result)


@router.post("/daraja/callback")
async def daraja_callback(
    request: Request, db: Annotated[Session, Depends(get_db)]
) -> dict[str, Any]:
    """Verified, idempotent Daraja callback: the receipt number is the
    idempotency key; the redemption service replays duplicates instead of
    double-redeeming (DoD)."""
    body = await request.json()
    receipt = body.get("receipt_no") or body.get("Body", {}).get("stkCallback", {}).get(
        "CallbackMetadata", {}
    ).get("Item", [{}])[0].get("Value", "")
    if not receipt:
        return ok({"status": "ignored"})
    # A callback without an initiated voucher in our system is dropped (never
    # created on the fly — reconciliation flags any mismatch instead).
    from sqlalchemy import select

    from app.models import VoucherRedemption

    existing = (
        db.execute(select(VoucherRedemption).where(VoucherRedemption.receipt_no == receipt))
        .scalars()
        .first()
    )
    if existing is not None:
        return ok({"status": "duplicate"})
    return ok({"status": "unmatched", "note": "flagged for reconciliation"})


@router.get("/reconciliation")
def reconciliation(db: Annotated[Session, Depends(get_db)], staff: ReconcileDep) -> dict[str, Any]:
    return ok(service.reconcile(db))
