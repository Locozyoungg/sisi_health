"""Load rules and red-flag patterns from /ontology, and build engines. The JSON in
/ontology is the single source of truth; both the Python and Kotlin engines run it."""

import hashlib
import json
from pathlib import Path
from typing import Any

from app.config import get_settings
from app.rules.engine import RuleEngine
from app.rules.redflags import RedFlagMatcher
from app.rules.schemas import Rule
from app.rules.validator import validate_rule_dict

RULE_SET_VERSION = "ontology-1.1"


def load_rules(ontology_dir: Path) -> list[Rule]:
    rules_dir = ontology_dir / "rules"
    if not rules_dir.is_dir():
        raise FileNotFoundError(f"ontology rules dir missing: {rules_dir}")
    rules: list[Rule] = []
    for path in sorted(rules_dir.glob("*.json")):
        with open(path, encoding="utf-8") as fh:
            rules.append(validate_rule_dict(json.load(fh)))
    return rules


def load_pattern_files(ontology_dir: Path) -> list[dict[str, Any]]:
    redflags_dir = ontology_dir / "redflags"
    files: list[dict[str, Any]] = []
    for path in sorted(redflags_dir.glob("patterns.*.json")):
        with open(path, encoding="utf-8") as fh:
            files.append(json.load(fh))
    return files


def build_engine(
    ontology_dir: Path, *, allow_unvalidated: bool, minor_age: int | None = None
) -> RuleEngine:
    if minor_age is None:
        minor_age = get_settings().self_consent_age
    return RuleEngine(
        load_rules(ontology_dir),
        rule_set_version=RULE_SET_VERSION,
        allow_unvalidated=allow_unvalidated,
        minor_age=minor_age,
    )


def build_matcher(ontology_dir: Path) -> RedFlagMatcher:
    return RedFlagMatcher(load_pattern_files(ontology_dir))


def rule_content_hash(rule_dict: dict[str, Any]) -> str:
    canonical = json.dumps(rule_dict, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
