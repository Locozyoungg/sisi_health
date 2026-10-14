"""Envelope encryption: seal/open roundtrip, wrong-key failure, key persistence."""

import uuid

import pytest
from sqlalchemy import select

from app.crypto.envelope import open_json, seal_json
from app.crypto.key_provider import DatabaseKeyProvider
from app.models import DataKey


def test_roundtrip(db, provider: DatabaseKeyProvider):
    owner = uuid.uuid4()
    payload = {"pain": 7, "bleeding_volume": 3, "symptoms": {"dyschezia": True}}
    blob, key_id = seal_json(provider, db, "user", owner, payload)
    assert payload != blob
    assert open_json(provider, db, blob, key_id) == payload


def test_wrong_key_fails(db, provider: DatabaseKeyProvider):
    from cryptography.exceptions import InvalidTag

    owner = uuid.uuid4()
    blob, key_id = seal_json(provider, db, "user", owner, {"secret": "x"})
    other = DatabaseKeyProvider.__new__(DatabaseKeyProvider)
    other._master = b"z" * 32  # noqa: SLF001 — deliberate wrong-key test
    with pytest.raises(InvalidTag):
        open_json(other, db, blob, key_id)


def test_data_key_persisted_once(db, provider: DatabaseKeyProvider):
    owner = uuid.uuid4()
    provider.get_or_create_data_key(db, "user", owner)
    provider.get_or_create_data_key(db, "user", owner)
    keys = db.execute(select(DataKey).where(DataKey.owner_id == owner)).scalars().all()
    assert len(keys) == 1


def test_delete_data_keys(db, provider: DatabaseKeyProvider):
    owner = uuid.uuid4()
    provider.get_or_create_data_key(db, "user", owner)
    assert provider.delete_data_keys(db, "user", owner) == 1
    assert provider.get_data_key(db, "user", owner) is None
