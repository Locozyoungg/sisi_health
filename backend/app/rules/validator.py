"""Rule loading and validation: JSON Schema (draft 2020-12) + pydantic + semantic
checks. A rule that fails any check never reaches the engine."""

import json
from pathlib import Path

import jsonschema
from pydantic import ValidationError as PydanticError

from app.rules.bands import Band
from app.rules.schemas import LogicNode, Rule

_SCHEMA_PATH = Path(__file__).resolve().parents[3] / "ontology" / "schema" / "rule.schema.json"


class RuleValidationError(ValueError):
    pass


def _load_json_schema() -> dict:
    with open(_SCHEMA_PATH, encoding="utf-8") as fh:
        return json.load(fh)


def _collect_inputs(node: LogicNode, acc: set[str]) -> None:
    if node.input:
        acc.add(node.input)
    for child in node.operands or []:
        _collect_inputs(child, acc)


def _semantic_checks(rule: Rule) -> None:
    if rule.min_age < 13:
        raise RuleValidationError(f"{rule.id}: min_age must be >= 13")
    if rule.red_flag and rule.output_band not in (Band.ORANGE, Band.RED):
        raise RuleValidationError(f"{rule.id}: red-flag rules must output ORANGE or RED")
    if rule.clinically_validated:
        if not (rule.reviewer_name and rule.reviewer_registration_no and rule.signed_at):
            raise RuleValidationError(
                f"{rule.id}: clinically_validated=true requires reviewer_name, "
                "reviewer_registration_no, and signed_at"
            )
    else:
        if rule.reviewer_name or rule.reviewer_registration_no or rule.signed_at:
            raise RuleValidationError(
                f"{rule.id}: clinically_validated=false requires empty sign-off fields"
            )
    declared = {i.name for i in rule.inputs}
    referenced: set[str] = set()
    _collect_inputs(rule.logic, referenced)
    undeclared = referenced - declared
    if undeclared:
        raise RuleValidationError(f"{rule.id}: logic references undeclared inputs {sorted(undeclared)}")


def validate_rule_dict(data: dict) -> Rule:
    """Validate one rule dict against the ontology schema + semantics. Returns the Rule."""
    errors = list(jsonschema.Draft202012Validator(_load_json_schema()).iter_errors(data))
    if errors:
        detail = errors[0].message or "invalid rule"
        raise RuleValidationError(f"schema violation at {list(errors[0].path)}: {detail}")
    try:
        rule = Rule.model_validate(data)
    except PydanticError as exc:
        raise RuleValidationError(f"invalid rule fields: {exc}") from exc
    _semantic_checks(rule)
    return rule
