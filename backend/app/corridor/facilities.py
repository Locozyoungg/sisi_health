"""Facility directory for the referral engine (spec 5.4) with screening fields
and the 90-day staleness flag (spec 5.4.1). Staleness is computed, never stored;
entries not verified in 90 days are shown with a warning."""

import uuid
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit.service import record_event
from app.core.errors import Conflict, NotFound
from app.core.ids import uuid7
from app.core.time import utc_now_naive
from app.models import Facility

STALENESS_DAYS = 90
STALE_WARNING = "Facility details were not verified in the last 90 days. Verify before referring."
SCREENING_TESTS = {"hpv_test", "via", "pap_smear"}


def _validate(fields: dict[str, Any]) -> None:
    if fields.get("level") not in {None, "primary", "secondary", "tertiary"}:
        raise Conflict("level must be primary, secondary, or tertiary")
    tests = fields.get("screening_tests")
    if tests is not None:
        unknown = set(tests) - SCREENING_TESTS
        if unknown:
            raise Conflict(f"unknown screening tests: {sorted(unknown)}")
    for key in ("catchment_counties", "languages", "services", "screening_tests"):
        value = fields.get(key)
        if value is not None and not isinstance(value, list):
            raise Conflict(f"{key} must be a list")


def _stale(last_verified_at: datetime | None) -> bool:
    if last_verified_at is None:
        return True
    return (utc_now_naive() - last_verified_at) > timedelta(days=STALENESS_DAYS)


def public_view(facility: Facility) -> dict[str, Any]:
    stale = _stale(facility.last_verified_at)
    return {
        "id": str(facility.id),
        "name": facility.name,
        "county": facility.county,
        "level": facility.level,
        "catchment_counties": facility.catchment_counties,
        "languages": facility.languages,
        "services": facility.services,
        "screening_tests": facility.screening_tests,
        "opening_hours": facility.opening_hours,
        "estimated_cost_ksh_min": facility.estimated_cost_ksh_min,
        "estimated_cost_ksh_max": facility.estimated_cost_ksh_max,
        "cost_note": facility.cost_note,
        "last_verified_at": facility.last_verified_at,
        "stale": stale,
        "warning": STALE_WARNING if stale else None,
    }


def list_facilities(
    db: Session,
    *,
    county: str | None = None,
    level: str | None = None,
    language: str | None = None,
    screening: str | None = None,
) -> list[dict[str, Any]]:
    rows = db.execute(select(Facility).order_by(Facility.name)).scalars().all()
    out = []
    for facility in rows:
        if county and facility.county != county:
            continue
        if level and facility.level != level:
            continue
        if language and language not in (facility.languages or []):
            continue
        if screening and screening not in (facility.screening_tests or []):
            continue
        out.append(public_view(facility))
    return out


def create_facility(db: Session, *, staff_id: uuid.UUID, fields: dict[str, Any]) -> dict[str, Any]:
    _validate(fields)
    if not fields.get("name") or not fields.get("county"):
        raise Conflict("name and county are required")
    facility = Facility(
        id=uuid7(),
        name=fields["name"],
        county=fields["county"],
        level=fields.get("level", "primary"),
        catchment_counties=fields.get("catchment_counties", []),
        languages=fields.get("languages", []),
        services=fields.get("services", []),
        screening_tests=fields.get("screening_tests", []),
        opening_hours=fields.get("opening_hours"),
        estimated_cost_ksh_min=fields.get("estimated_cost_ksh_min"),
        estimated_cost_ksh_max=fields.get("estimated_cost_ksh_max"),
        cost_note=fields.get("cost_note"),
        phone=fields.get("phone"),
        email=fields.get("email"),
    )
    db.add(facility)
    db.flush()
    record_event(
        db,
        event_type="facility_created",
        actor_type="staff",
        actor_id=staff_id,
        actor_role=None,
        resource_type="facility",
        resource_id=facility.id,
        payload={"county": facility.county},
    )
    return public_view(facility)


def update_facility(
    db: Session, *, staff_id: uuid.UUID, facility_id: uuid.UUID, fields: dict[str, Any]
) -> dict[str, Any]:
    facility = db.get(Facility, facility_id)
    if facility is None:
        raise NotFound("facility not found")
    _validate(fields)
    for key in ("name", "county", "level", "catchment_counties", "languages", "services",
                "screening_tests", "opening_hours", "estimated_cost_ksh_min",
                "estimated_cost_ksh_max", "cost_note", "phone", "email"):
        if key in fields:
            setattr(facility, key, fields[key])
    facility.updated_at = utc_now_naive()
    db.flush()
    record_event(
        db,
        event_type="facility_updated",
        actor_type="staff",
        actor_id=staff_id,
        actor_role=None,
        resource_type="facility",
        resource_id=facility.id,
        payload={"county": facility.county},
    )
    return public_view(facility)


def delete_facility(db: Session, *, staff_id: uuid.UUID, facility_id: uuid.UUID) -> None:
    facility = db.get(Facility, facility_id)
    if facility is None:
        raise NotFound("facility not found")
    db.delete(facility)
    db.flush()
    record_event(
        db,
        event_type="facility_deleted",
        actor_type="staff",
        actor_id=staff_id,
        actor_role=None,
        resource_type="facility",
        resource_id=facility_id,
        payload={},
    )


def verify_facility(
    db: Session, *, staff_id: uuid.UUID, facility_id: uuid.UUID
) -> dict[str, Any]:
    """Verification resets the staleness clock (spec 5.4.1)."""
    facility = db.get(Facility, facility_id)
    if facility is None:
        raise NotFound("facility not found")
    facility.last_verified_at = utc_now_naive()
    facility.verified_by = staff_id
    facility.updated_at = utc_now_naive()
    db.flush()
    record_event(
        db,
        event_type="facility_verified",
        actor_type="staff",
        actor_id=staff_id,
        actor_role=None,
        resource_type="facility",
        resource_id=facility.id,
        payload={},
    )
    return public_view(facility)
