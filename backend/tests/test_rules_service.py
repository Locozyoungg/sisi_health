"""Rules activation workflow: two-person approval, golden-suite gate, rollback,
audit entries (spec 5.5)."""

import json

import pytest
from sqlalchemy import select

from app.core.errors import Conflict, PreconditionFailed
from app.models import RuleVersion
from app.rules.service import (
    approve_activation,
    register_rule_version,
    request_activation,
    rollback_rule,
)


def _rule_dict(rule_id: str = "anemia-risk-flag") -> dict:
    from app.config import get_settings

    path = get_settings().ontology_dir / "rules" / f"{rule_id}.json"
    return json.loads(path.read_text(encoding="utf-8"))


def test_register_rule_version(db, make_staff):
    author = make_staff("gynecologist")
    version = register_rule_version(db, _rule_dict(), created_by=author.id)
    db.commit()
    assert version.status == "draft"
    again = register_rule_version(db, _rule_dict(), created_by=author.id)
    assert again.id == version.id  # idempotent per rule+version


def test_activation_two_person_and_rollback(db, make_staff):
    author = make_staff("gynecologist")
    approver = make_staff("gynecologist")
    version = register_rule_version(db, _rule_dict(), created_by=author.id)
    db.commit()

    activation = request_activation(
        db, rule_id=version.rule_id, version=version.version, author=author
    )
    db.commit()
    assert activation.status == "pending"

    with pytest.raises(Conflict, match="differ"):
        approve_activation(db, activation_id=activation.id, approver=author)
    db.rollback()

    approved = approve_activation(db, activation_id=activation.id, approver=approver)
    db.commit()
    assert approved.status == "approved"
    active = (
        db.execute(
            select(RuleVersion).where(
                RuleVersion.rule_id == version.rule_id, RuleVersion.status == "active"
            )
        )
        .scalars()
        .first()
    )
    assert active is not None and active.version == version.version

    restored = rollback_rule(db, rule_id=version.rule_id, staff=approver)
    db.commit()
    assert restored is None  # nothing prior to restore
    assert (
        db.execute(
            select(RuleVersion).where(
                RuleVersion.rule_id == version.rule_id, RuleVersion.status == "active"
            )
        )
        .scalars()
        .first()
        is None
    )


def test_activation_restores_previous_version(db, make_staff):
    author = make_staff("gynecologist")
    approver = make_staff("gynecologist")
    v1 = register_rule_version(db, _rule_dict(), created_by=author.id)
    db.commit()
    act1 = request_activation(db, rule_id=v1.rule_id, version=v1.version, author=author)
    db.commit()
    approve_activation(db, activation_id=act1.id, approver=approver)
    db.commit()

    # register v2 (payload identical for simplicity; rule_id+version distinct)
    data = _rule_dict()
    data["version"] = "1.0.1"
    v2 = register_rule_version(db, data, created_by=author.id)
    db.commit()
    act2 = request_activation(db, rule_id=v2.rule_id, version=v2.version, author=author)
    db.commit()
    approve_activation(db, activation_id=act2.id, approver=approver)
    db.commit()

    restored = rollback_rule(db, rule_id=v2.rule_id, staff=approver)
    db.commit()
    assert restored is not None and restored.version == "1.0.0"


def test_golden_gate_blocks_bad_activation(db, make_staff):
    """A version that breaks the golden cases must not activate (spec 5.5)."""
    author = make_staff("gynecologist")
    approver = make_staff("gynecologist")
    data = _rule_dict()
    data["version"] = "1.0.1"
    # Lower the thresholds so everyone matches -> golden gc-01 (GREEN) breaks.
    for node in data["logic"]["operands"]:
        node["value"] = 0
    version = register_rule_version(db, data, created_by=author.id)
    db.commit()
    activation = request_activation(
        db, rule_id=version.rule_id, version=version.version, author=author
    )
    db.commit()
    with pytest.raises(PreconditionFailed, match="golden"):
        approve_activation(db, activation_id=activation.id, approver=approver)
    db.rollback()
    assert (
        db.execute(
            select(RuleVersion).where(
                RuleVersion.rule_id == version.rule_id, RuleVersion.status == "active"
            )
        )
        .scalars()
        .first()
        is None
    )


def test_activation_writes_audit_entries(db, make_staff):
    from app.models import AuditEvent

    author = make_staff("gynecologist")
    approver = make_staff("gynecologist")
    version = register_rule_version(db, _rule_dict(), created_by=author.id)
    db.commit()
    activation = request_activation(
        db, rule_id=version.rule_id, version=version.version, author=author
    )
    db.commit()
    approve_activation(db, activation_id=activation.id, approver=approver)
    db.commit()
    events = [e.event_type for e in db.execute(select(AuditEvent)).scalars()]
    assert "rule_version_registered" in events
    assert "rule_activation_requested" in events
    assert "rule_activated" in events
