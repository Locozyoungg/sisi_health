"""Load rules and red-flag patterns from /ontology, and build engines. The JSON in
/ontology is the single source of truth; both the Python and Kotlin engines run it."""

import json
import hashlib
from pathlib import Path

from app.rules.engine import RuleEngine
from app.rules.redflags import RedFlagMatcher
from app.rules.schemas import Rule
from app.rules.validator import validate_rule_dict

RULE_SET_VERSION = "ontology-1.0"


def load_rules(ontology_dir: Path) -> list[Rule]:
    rules_dir = ontology_dir / "rules"
    if not rules_dir.is_dir():
        raise FileNotFoundError(f"ontology rules dir missing: {rules_dir}")
    rules: list[Rule] = []
    for path in sorted(rules_dir.glob("*.json")):
        with open(path, encoding="utf-8") as fh:
            rules.append(validate_rule_dict(json.load(fh)))
    return rules


def load_pattern_files(ontology_dir: Path) -> list[dict]:
    redflags_dir = ontology_dir / "redflags"
    files: list[dict] = []
    for path in sorted(redflags_dir.glob("patterns.*.json")):
        with open(path, encoding="utf-8") as fh:
            files.append(json.load(fh))
    return files


def build_engine(ontology_dir: Path, *, allow_unvalidated: bool) -> RuleEngine:
    return RuleEngine(
        load_rules(ontology_dir),
        rule_set_version=RULE_SET_VERSION,
        allow_unvalidated=allow_unvalidated,
    )


def build_matcher(ontology_dir: Path) -> RedFlagMatcher:
    return RedFlagMatcher(load_pattern_files(ontology_dir))


def rule_content_hash(rule_dict: dict) -> str:
    canonical = json.dumps(rule_dict, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
