"""Field-level seal/open helpers over the DatabaseKeyProvider (AES-256-GCM)."""

import json
import uuid
from typing import Any, cast

from sqlalchemy.orm import Session

from app.crypto.key_provider import DatabaseKeyProvider
from app.models import DataKey


def seal_json(
    provider: DatabaseKeyProvider,
    db: Session,
    owner_type: str,
    owner_id: uuid.UUID,
    data: dict[str, Any],
) -> tuple[bytes, uuid.UUID]:
    """Encrypt a JSON payload with the owner's data key. Returns (ciphertext, key_id)."""
    data_key = provider.get_or_create_data_key(db, owner_type, owner_id)
    plaintext = json.dumps(data, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return provider.wrap(plaintext), data_key.id


def open_json(
    provider: DatabaseKeyProvider, db: Session, blob: bytes, key_id: uuid.UUID
) -> dict[str, Any]:
    """Decrypt a JSON payload sealed by seal_json."""
    data_key = db.get(DataKey, key_id)
    if data_key is None:
        raise ValueError("data key missing")
    return cast(dict[str, Any], json.loads(provider.unwrap(blob).decode("utf-8")))
