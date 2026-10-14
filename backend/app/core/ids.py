"""UUIDv7 generation (RFC 9562). All SISI ids are UUIDv7; no auto-increment ids are
exposed (non-negotiable 6). Monotonic within the process via a rand_a counter."""

import os
import time
import uuid

_last_ts = 0
_last_rand_a = 0


def uuid7() -> uuid.UUID:
    """Return a time-ordered UUIDv7, monotonic within the process."""
    global _last_ts, _last_rand_a
    ts = time.time_ns() // 1_000_000
    if ts <= _last_ts:
        if _last_rand_a >= 0xFFF:
            _last_ts += 1  # counter exhausted within the same millisecond: bump time
            _last_rand_a = 0
        else:
            _last_rand_a += 1
            ts = _last_ts
    else:
        _last_rand_a = 0
        _last_ts = ts

    b = bytearray(16)
    b[0:6] = ts.to_bytes(6, "big")
    b[6] = 0x70 | (_last_rand_a >> 8)  # version 7 in the high nibble, rand_a high bits
    b[7] = _last_rand_a & 0xFF
    rand_b = os.urandom(8)
    b[8] = 0x80 | (rand_b[0] & 0x3F)  # variant 10
    b[9:16] = rand_b[1:]
    return uuid.UUID(bytes=bytes(b))
