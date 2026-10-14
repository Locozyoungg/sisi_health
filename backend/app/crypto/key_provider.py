"""Master-key handling and the DatabaseKeyProvider (envelope encryption)."""

import base64
import os
import uuid
from typing import Protocol

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings
from app.core.errors import PreconditionFailed
from app.core.ids import uuid7
from app.core.time import utc_now_naive
from app.models import DataKey


class KeyProvider(Protocol):
    def master(self) -> bytes: ...

    def get_or_create_data_key(
        self, db: Session, owner_type: str, owner_id: uuid.UUID
    ) -> DataKey: ...

    def get_data_key(self, db: Session, owner_type: str, owner_id: uuid.UUID) -> DataKey | None: ...

    def delete_data_keys(self, db: Session, owner_type: str, owner_id: uuid.UUID) -> int: ...


class DatabaseKeyProvider:
    """Envelope provider: per-record data keys in core.data_keys, wrapped by a master key."""

    def __init__(self, settings: Settings) -> None:
        self._master = self._load_master(settings)

    @staticmethod
    def _load_master(settings: Settings) -> bytes:
        if settings.master_key_b64:
            key = base64.b64decode(settings.master_key_b64)
            if len(key) != 32:
                raise PreconditionFailed("SISI_MASTER_KEY_B64 must decode to 32 bytes")
            return key
        path = settings.master_key_file
        if path.exists():
            return path.read_bytes()
        if settings.env in {"dev", "demo"}:
            key = os.urandom(32)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(key)
            return key
        raise PreconditionFailed("master key file missing; set SISI_MASTER_KEY_B64")

    def master(self) -> bytes:
        return self._master

    def wrap(self, plain: bytes) -> bytes:
        nonce = os.urandom(12)
        return nonce + AESGCM(self._master).encrypt(nonce, plain, None)

    def unwrap(self, blob: bytes) -> bytes:
        nonce, ct = blob[:12], blob[12:]
        return AESGCM(self._master).decrypt(nonce, ct, None)

    def get_or_create_data_key(self, db: Session, owner_type: str, owner_id: uuid.UUID) -> DataKey:
        existing = self.get_data_key(db, owner_type, owner_id)
        if existing is not None:
            return existing
        key = DataKey(
            id=uuid7(),
            owner_type=owner_type,
            owner_id=owner_id,
            wrapped_key=self.wrap(os.urandom(32)),
            key_version=1,
            active=True,
            created_at=utc_now_naive(),
        )
        db.add(key)
        db.flush()
        return key

    def get_data_key(self, db: Session, owner_type: str, owner_id: uuid.UUID) -> DataKey | None:
        return (
            db.execute(
                select(DataKey)
                .where(
                    DataKey.owner_type == owner_type,
                    DataKey.owner_id == owner_id,
                    DataKey.active.is_(True),
                )
                .order_by(DataKey.key_version.desc())
            )
            .scalars()
            .first()
        )

    def unwrap_data_key(self, data_key: DataKey) -> bytes:
        return self.unwrap(data_key.wrapped_key)

    def delete_data_keys(self, db: Session, owner_type: str, owner_id: uuid.UUID) -> int:
        keys = (
            db.execute(
                select(DataKey).where(
                    DataKey.owner_type == owner_type, DataKey.owner_id == owner_id
                )
            )
            .scalars()
            .all()
        )
        for key in keys:
            db.delete(key)
        db.flush()
        return len(keys)
