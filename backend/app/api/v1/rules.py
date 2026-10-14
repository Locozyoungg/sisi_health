"""Rules endpoints: evaluate (user), read + activation workflow (clinicians)."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import ProviderDep
from app.api.envelope import ok
from app.auth.deps import get_current_user, require
from app.config import Settings, get_settings
from app.core.errors import NotFound
from app.crypto.key_provider import DatabaseKeyProvider
from app.db import get_db
from app.diary.service import compute_features
from app.models import RuleVersion, StaffUser, User
from app.rules.loader import RULE_SET_VERSION, build_engine
from app.rules.service import approve_activation, register_rule_version, request_activation, rollback_rule
from app.users.service import age_of

router = APIRouter()


class EvaluateResult(BaseModel):
    band: str
    indicators: list[str]
    urgent: bool
    safeguarding: bool
    rule_set_version: str
    evaluated_at: str


@router.post("/evaluate")
def evaluate(
    db: Annotated[Session, Depends(get_db)],
    provider: ProviderDep,
    user: Annotated[User, Depends(get_current_user)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> dict:
    from app.consent.service import require_consent
    from app.crypto.envelope import seal_json
    from app.core.ids import uuid7
    from app.models import RuleEvaluation

    require_consent(db, user, age_of(provider, db, user))
    features, diary_days = compute_features(db, provider, user)
    engine = build_engine(settings.ontology_dir, allow_unvalidated=settings.allow_unvalidated_rules)
    evaluation = engine.evaluate(age=age_of(provider, db, user) or 0, diary_days=diary_days, features=features)
    blob, key_id = seal_json(provider, db, "user", user.id, evaluation.model_dump(mode="json"))
    db.add(
        RuleEvaluation(
            id=uuid7(),
            user_id=user.id,
            rule_set_version=RULE_SET_VERSION,
            payload_ciphertext=blob,
            key_id=key_id,
        )
    )
    db.commit()
    return ok(evaluation.model_dump(mode="json"))


class ActivationIn(BaseModel):
    rule_id: str
    version: str = Field(pattern=r"^[0-9]+\.[0-9]+\.[0-9]+$")


@router.get("")
def list_rules(
    db: Annotated[Session, Depends(get_db)],
    _staff: Annotated[StaffUser, Depends(require("rules:read"))],
) -> dict:
    rows = db.execute(select(RuleVersion).order_by(RuleVersion.rule_id, RuleVersion.version)).scalars().all()
    return ok(
        [
            {
                "rule_id": r.rule_id,
                "version": r.version,
                "status": r.status,
                "content_hash": r.content_hash,
                "clinically_validated": r.payload.get("clinically_validated"),
            }
            for r in rows
        ]
    )


@router.get("/{rule_id}/versions/{version}")
def get_rule(
    rule_id: str,
    version: str,
    db: Annotated[Session, Depends(get_db)],
    _staff: Annotated[StaffUser, Depends(require("rules:read"))],
) -> dict:
    row = db.execute(
        select(RuleVersion).where(RuleVersion.rule_id == rule_id, RuleVersion.version == version)
    ).scalars().first()
    if row is None:
        raise NotFound("rule version not found")
    return ok(row.payload)


@router.post("/registrations")
def register_rule(
    body: ActivationIn,
    db: Annotated[Session, Depends(get_db)],
    staff: Annotated[StaffUser, Depends(require("rules:activate"))],
    settings: Annotated[Settings, Depends(get_settings)],
) -> dict:
    import json

    path = settings.ontology_dir / "rules" / f"{body.rule_id}.json"
    if not path.exists():
        raise NotFound(f"no rule file {body.rule_id}.json in /ontology/rules")
    rule_dict = json.loads(path.read_text(encoding="utf-8"))
    version = register_rule_version(db, rule_dict, created_by=staff.id)
    db.commit()
    return ok({"rule_id": version.rule_id, "version": version.version, "status": version.status})


@router.post("/activations")
def activate_request(
    body: ActivationIn,
    db: Annotated[Session, Depends(get_db)],
    staff: Annotated[StaffUser, Depends(require("rules:activate"))],
) -> dict:
    activation = request_activation(db, rule_id=body.rule_id, version=body.version, author=staff)
    db.commit()
    return ok({"activation_id": str(activation.id), "status": activation.status})


@router.post("/activations/{activation_id}/approve")
def activate_approve(
    activation_id: uuid.UUID,
    db: Annotated[Session, Depends(get_db)],
    staff: Annotated[StaffUser, Depends(require("rules:activate"))],
) -> dict:
    activation = approve_activation(db, activation_id=activation_id, approver=staff)
    db.commit()
    return ok({"activation_id": str(activation.id), "status": activation.status})


@router.post("/rollback")
def rollback(
    body: ActivationIn,
    db: Annotated[Session, Depends(get_db)],
    staff: Annotated[StaffUser, Depends(require("rules:activate"))],
) -> dict:
    restored = rollback_rule(db, rule_id=body.rule_id, staff=staff)
    db.commit()
    return ok({"rule_id": body.rule_id, "restored_version": restored.version if restored else None})
