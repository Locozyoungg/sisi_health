"""Screening + HPV vaccination schedule config (spec 5.4.1: age-based prompts are
driven by /ontology/config/screening_schedule.json, NEVER hard-coded). Values are
PLACEHOLDERS pending MoH confirmation (human task); the `verified` flag records
that they are drafts."""

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.config import get_settings
from app.core.errors import PreconditionFailed

REQUIRED_STATES = (
    "referred",
    "screened",
    "result_received",
    "further_assessment",
    "treatment",
    "follow_up",
)


@lru_cache
def screening_schedule() -> dict[str, Any]:
    path: Path = get_settings().screening_config_path
    if not path.exists():
        raise PreconditionFailed(f"screening config missing: {path}")
    data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data.get("screening_start_age"), int):
        raise PreconditionFailed("screening config: screening_start_age must be an int")
    intervals = data.get("reminder_intervals_days", {})
    missing = [s for s in REQUIRED_STATES if s not in intervals]
    if missing:
        raise PreconditionFailed(f"screening config: missing intervals for {missing}")
    if not isinstance(data.get("hpv_vaccine_schedule"), list):
        raise PreconditionFailed("screening config: hpv_vaccine_schedule must be a list")
    return data


def reminder_interval_days(state: str) -> int:
    return int(screening_schedule()["reminder_intervals_days"][state])
