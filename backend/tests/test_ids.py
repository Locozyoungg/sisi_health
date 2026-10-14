"""UUIDv7: version, variant, monotonicity, uniqueness (non-negotiable 6)."""

from app.core.ids import uuid7


def test_uuid7_version_and_variant():
    value = uuid7()
    assert value.version == 7
    assert value.variant.upper() in ("RFC_4122", "SPECIFIED IN RFC 4122")


def test_uuid7_monotonic():
    values = [uuid7() for _ in range(1000)]
    assert all(a.int < b.int for a, b in zip(values, values[1:], strict=False))


def test_uuid7_unique():
    assert len({uuid7() for _ in range(5000)}) == 5000
