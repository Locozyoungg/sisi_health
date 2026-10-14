"""Session store behind a protocol (spec 2: USSD session state in Redis with a
5-minute resume window keyed by phone hash; assumption A19: a Postgres-backed
fallback keeps dev working where Redis is unavailable)."""

import json
from datetime import timedelta
from typing import Any, Protocol, cast

import redis as redis_lib
from app.core.time import utc_now_naive
from app.db import SessionLocal
from app.models import UssdSession
from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from gateway.config import GatewaySettings

SESSION_TTL_SECONDS = 300  # 5-minute resume window (spec 5.3)


class SessionStore(Protocol):
    def get(self, phone_hash: str) -> dict[str, Any] | None: ...

    def put(
        self, phone_hash: str, state: dict[str, Any], ttl_seconds: int = SESSION_TTL_SECONDS
    ) -> None: ...

    def delete(self, phone_hash: str) -> None: ...


class RedisSessionStore:
    def __init__(self, settings: GatewaySettings) -> None:
        self._client = redis_lib.Redis.from_url(settings.redis_url, socket_connect_timeout=0.5)

    def get(self, phone_hash: str) -> dict[str, Any] | None:
        raw = cast(bytes | None, self._client.get(phone_hash))
        return json.loads(raw) if raw else None

    def put(
        self, phone_hash: str, state: dict[str, Any], ttl_seconds: int = SESSION_TTL_SECONDS
    ) -> None:
        self._client.set(phone_hash, json.dumps(state), ex=ttl_seconds)

    def delete(self, phone_hash: str) -> None:
        self._client.delete(phone_hash)


class PostgresSessionStore:
    """Dev/test fallback (assumption A19). Same interface, same TTL semantics."""

    def get(self, phone_hash: str) -> dict[str, Any] | None:
        with SessionLocal() as db:
            row = (
                db.execute(select(UssdSession).where(UssdSession.phone_hash == phone_hash))
                .scalars()
                .first()
            )
        if row is None:
            return None
        if row.expires_at < utc_now_naive():
            self.delete(phone_hash)
            return None
        return row.state_json

    def put(
        self, phone_hash: str, state: dict[str, Any], ttl_seconds: int = SESSION_TTL_SECONDS
    ) -> None:
        with SessionLocal() as db:
            stmt = pg_insert(UssdSession).values(
                phone_hash=phone_hash,
                state_json=state,
                expires_at=utc_now_naive() + timedelta(seconds=ttl_seconds),
                updated_at=utc_now_naive(),
            )
            stmt = stmt.on_conflict_do_update(
                index_elements=["phone_hash"],
                set_={
                    "state_json": stmt.excluded.state_json,
                    "expires_at": stmt.excluded.expires_at,
                    "updated_at": utc_now_naive(),
                },
            )
            db.execute(stmt)
            db.commit()

    def delete(self, phone_hash: str) -> None:
        with SessionLocal() as db:
            db.execute(delete(UssdSession).where(UssdSession.phone_hash == phone_hash))
            db.commit()


def build_session_store(settings: GatewaySettings) -> SessionStore:
    """auto: Redis when reachable (spec), Postgres fallback otherwise."""
    if settings.ussd_session_backend == "postgres":
        return PostgresSessionStore()
    if settings.ussd_session_backend == "redis":
        return RedisSessionStore(settings)
    try:
        store = RedisSessionStore(settings)
        store.put("__probe__", {"probe": True}, ttl_seconds=5)  # raises if Redis is down
        return store
    except Exception:  # noqa: BLE001 — any Redis failure falls back per A19
        return PostgresSessionStore()
