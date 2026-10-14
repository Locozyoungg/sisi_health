"""Severity bands. The rules engine assigns bands; the LLM never does (non-negotiable 1)."""

from collections.abc import Iterable
from enum import StrEnum


class Band(StrEnum):
    GREEN = "GREEN"
    YELLOW = "YELLOW"
    ORANGE = "ORANGE"
    RED = "RED"


NOT_ENOUGH_DATA = "NOT_ENOUGH_DATA"

SEVERITY: dict[Band, int] = {
    Band.GREEN: 0,
    Band.YELLOW: 1,
    Band.ORANGE: 2,
    Band.RED: 3,
}

BAND_LABELS_EN: dict[str, str] = {
    "GREEN": "self-care",
    "YELLOW": "see a nurse",
    "ORANGE": "see a doctor soon",
    "RED": "urgent",
}


def max_band(bands: Iterable[Band]) -> Band:
    """Highest-urgency band. Safety asymmetry: uncertainty resolves upward, never down."""
    return max(bands, key=lambda b: SEVERITY[b])


def band_at_least(band: Band, floor: Band) -> bool:
    return SEVERITY[band] >= SEVERITY[floor]
