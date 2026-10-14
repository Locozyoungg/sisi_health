"""Session store contract: Postgres fallback (this environment) honors the same
semantics as Redis — put/get/delete with the 5-minute resume window."""

from datetime import timedelta

from app.core.time import utc_now_naive

from gateway.sessions.store import SESSION_TTL_SECONDS, PostgresSessionStore


def test_put_get_roundtrip():
    store = PostgresSessionStore()
    store.put("hash-a", {"state": "lang"}, ttl_seconds=60)
    assert store.get("hash-a") == {"state": "lang"}
    store.delete("hash-a")


def test_get_missing_returns_none():
    store = PostgresSessionStore()
    assert store.get("hash-never") is None


def test_expired_session_returns_none():
    store = PostgresSessionStore()
    store.put("hash-expired", {"state": "age"}, ttl_seconds=1)
    from app.db import SessionLocal
    from app.models import UssdSession
    from sqlalchemy import select

    with SessionLocal() as db:
        row = (
            db.execute(select(UssdSession).where(UssdSession.phone_hash == "hash-expired"))
            .scalars()
            .first()
        )
        row.expires_at = utc_now_naive() - timedelta(seconds=10)
        db.commit()
    assert store.get("hash-expired") is None
    store.delete("hash-expired")


def test_put_overwrites():
    store = PostgresSessionStore()
    store.put("hash-b", {"state": "q1"}, ttl_seconds=60)
    store.put("hash-b", {"state": "q2"}, ttl_seconds=60)
    assert store.get("hash-b") == {"state": "q2"}
    store.delete("hash-b")


def test_ttl_default_is_the_spec_resume_window():
    assert SESSION_TTL_SECONDS == 300
