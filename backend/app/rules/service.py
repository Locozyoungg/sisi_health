"""Two-person rule activation (spec 5.5): author and clinician approver must differ,
the golden test suite must pass before activation, rollback is instant, and every
transition writes an audit entry."""

import json
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit.service import record_event
from app.core.errors import Conflict, NotFound, PreconditionFailed
from app.core.ids import uuid7
from app.core.time import utc_now_naive
from app.models import RuleActivation, RuleVersion, StaffUser
from app.rules.loader import load_rules, rule_content_hash
from app.rules.validator import validate_rule_dict


def register_rule_version(
    db: Session, rule_dict: dict[str, Any], *, created_by: uuid.UUID | None
) -> RuleVersion:
    """Register a rule from /ontology as a draft version (idempotent per rule+version)."""
    rule = validate_rule_dict(rule_dict)
    content_hash = rule_content_hash(rule_dict)
    existing = (
        db.execute(
            select(RuleVersion).where(
                RuleVersion.rule_id == rule.id, RuleVersion.version == rule.version
            )
        )
        .scalars()
        .first()
    )
    if existing is not None:
        return existing
    version = RuleVersion(
        id=uuid7(),
        rule_id=rule.id,
        version=rule.version,
        payload=rule_dict,
        content_hash=content_hash,
        status="draft",
        created_by=created_by,
        created_at=utc_now_naive(),
    )
    db.add(version)
    db.flush()
    record_event(
        db,
        event_type="rule_version_registered",
        actor_type="staff",
        actor_id=created_by,
        actor_role=None,
        resource_type="rule_version",
        resource_id=version.id,
        payload={"rule_id": rule.id, "version": rule.version, "content_hash": content_hash},
    )
    return version


def _run_golden_check(db: Session, rule_version: RuleVersion) -> None:
    """Activation gate: the full rules test suite (golden cases) must pass with the
    CANDIDATE payload active (not the ontology file). Runs in-process here; CI runs
    the same cases."""
    from app.config import get_settings
    from app.rules.engine import RuleEngine

    settings = get_settings()
    golden_path = settings.ontology_dir / "golden" / "cases.json"
    golden = json.loads(golden_path.read_text(encoding="utf-8"))
    ontology_rules = {r.id: r for r in load_rules(settings.ontology_dir)}
    candidate = validate_rule_dict(rule_version.payload)
    ontology_rules[candidate.id] = candidate
    engine = RuleEngine(
        list(ontology_rules.values()),
        rule_set_version="candidate",
        allow_unvalidated=True,  # the golden suite always runs; sign-off is a separate gate
    )
    failures = []
    for case in golden["cases"]:
        result = engine.evaluate(
            age=case["age"], diary_days=case["diary_days"], features=case["features"]
        )
        if (
            result.band != case["expected_band"]
            or sorted(result.indicators) != sorted(case["expected_indicators"])
            or result.urgent != case["expected_escalations"]["urgent"]
            or result.safeguarding != case["expected_escalations"]["safeguarding"]
        ):
            failures.append(case["id"])
    if failures:
        raise PreconditionFailed(
            f"golden test suite failed on cases: {', '.join(failures)}; activation blocked"
        )


def request_activation(
    db: Session, *, rule_id: str, version: str, author: StaffUser
) -> RuleActivation:
    """Author requests activation of a rule version (workflow step 1 of 2)."""
    rule_version = (
        db.execute(
            select(RuleVersion).where(
                RuleVersion.rule_id == rule_id, RuleVersion.version == version
            )
        )
        .scalars()
        .first()
    )
    if rule_version is None:
        raise NotFound(f"rule version not registered: {rule_id}@{version}")
    if rule_version.status == "active":
        raise Conflict("rule version already active")
    activation = RuleActivation(
        id=uuid7(),
        rule_version_id=rule_version.id,
        author_id=author.id,
        status="pending",
        requested_at=utc_now_naive(),
    )
    rule_version.status = "pending_approval"
    db.add(activation)
    db.flush()
    record_event(
        db,
        event_type="rule_activation_requested",
        actor_type="staff",
        actor_id=author.id,
        actor_role=author.role,
        resource_type="rule_activation",
        resource_id=activation.id,
        payload={"rule_id": rule_id, "version": version},
    )
    return activation


def approve_activation(
    db: Session, *, activation_id: uuid.UUID, approver: StaffUser
) -> RuleActivation:
    """Clinician approves (step 2 of 2). Author and approver must differ; the golden
    suite must pass; previous active version is rolled back; audit entry written."""
    activation = db.get(RuleActivation, activation_id)
    if activation is None:
        raise NotFound("activation request not found")
    if activation.status != "pending":
        raise Conflict("activation already decided")
    if activation.author_id == approver.id:
        raise Conflict("two-person approval: approver must differ from author")
    rule_version = db.get(RuleVersion, activation.rule_version_id)
    if rule_version is None:
        raise NotFound("rule version missing")

    _run_golden_check(db, rule_version)

    previous = (
        db.execute(
            select(RuleVersion).where(
                RuleVersion.rule_id == rule_version.rule_id, RuleVersion.status == "active"
            )
        )
        .scalars()
        .first()
    )
    if previous is not None:
        previous.status = "rolled_back"
        previous.rolled_back_at = utc_now_naive()
        db.flush()  # persist the rollback before activating (partial unique index on active)
    rule_version.status = "active"
    rule_version.activated_at = utc_now_naive()
    activation.status = "approved"
    activation.approver_id = approver.id
    activation.decided_at = utc_now_naive()
    db.flush()
    record_event(
        db,
        event_type="rule_activated",
        actor_type="staff",
        actor_id=approver.id,
        actor_role=approver.role,
        resource_type="rule_version",
        resource_id=rule_version.id,
        payload={
            "rule_id": rule_version.rule_id,
            "version": rule_version.version,
            "rolled_back": previous.version if previous else None,
        },
    )
    return activation


def rollback_rule(db: Session, *, rule_id: str, staff: StaffUser) -> RuleVersion | None:
    """Instant rollback of the active version. Restores the previous version if one exists."""
    active = (
        db.execute(
            select(RuleVersion).where(
                RuleVersion.rule_id == rule_id, RuleVersion.status == "active"
            )
        )
        .scalars()
        .first()
    )
    if active is None:
        raise NotFound("no active version to roll back")
    active.status = "rolled_back"
    active.rolled_back_at = utc_now_naive()
    db.flush()  # persist before restoring (partial unique index on active)
    restored = (
        db.execute(
            select(RuleVersion)
            .where(
                RuleVersion.rule_id == rule_id,
                RuleVersion.status == "rolled_back",
                RuleVersion.id != active.id,  # never self-restore the row just rolled back
            )
            .order_by(RuleVersion.activated_at.desc().nulls_last())
        )
        .scalars()
        .first()
    )
    if restored is not None:
        restored.status = "active"
        restored.activated_at = utc_now_naive()
    db.flush()
    record_event(
        db,
        event_type="rule_rolled_back",
        actor_type="staff",
        actor_id=staff.id,
        actor_role=staff.role,
        resource_type="rule_version",
        resource_id=active.id,
        payload={
            "rule_id": rule_id,
            "version": active.version,
            "restored": restored.version if restored else None,
        },
    )
    return restored
