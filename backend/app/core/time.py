"""Time helpers. Non-negotiable 6: UTC in storage, Africa/Nairobi in display."""

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

NAIROBI = ZoneInfo("Africa/Nairobi")


def utc_now() -> datetime:
    """Current time, UTC. Use for ALL stored timestamps."""
    return datetime.now(timezone.utc)


def to_nairobi(dt: datetime) -> datetime:
    """Convert a stored UTC timestamp to Africa/Nairobi for display."""
    return dt.astimezone(NAIROBI)


def utc_now_naive() -> datetime:
    """UTC now without tzinfo, for DB columns (timestamptz normalizes to UTC)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)
