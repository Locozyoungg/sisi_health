"""UUIDv7 generation (RFC 9562). All SISI ids are UUIDv7; no auto-increment ids are exposed."""

import os
import time
import uuid

_LAST: tuple[int, int] | None = None


def uuid7() -> uuid.UUID:
    """Return a time-ordered UUIDv7. Monotonic within the process."""
    global _LAST
    ts = time.time_ns() // 1_000_000
    if _LAST is not None:
        ts = max(ts, _LAST[0] + 1) if _LAST[0] == ts else ts
        if _LAST[0] >= ts and _LAST[1] >= 0xFFFF:
            ts = _LAST[0] + 1
    rand_a = os.urandom(2)
    if _LAST is not None and _LAST[0] == ts:
        rand_a = (int.from_bytes(rand_a, "big") + 1).to_bytes(2, "big")
    rand_b = os.urandom(8)
    b = bytearray(ts.to_bytes(6, "big"))
    b += rand_a
    b += rand_b
    b[6] = (b[6] & 0x0F) | 0x70  # version 7
    b[8] = (b[8] & 0x3F) | 0x80  # variant 10
    _LAST = (ts, int.from_bytes(rand_a, "big"))
    return uuid.UUID(bytes=bytes(b))
