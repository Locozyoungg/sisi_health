"""User lifecycle: registration with age check (<13 blocked), encryption of PII,
age derivation for consent and rules."""

import json
import uuid
from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.otp import phone_hash
from app.config import Settings
from app.core.errors import Conflict, ValidationError
from app.core.ids import uuid7
from app.core.time import utc_now_naive
from app.crypto.key_provider import DatabaseKeyProvider
from app.models import User

MIN_AGE = 13


def _encrypt_pii(provider: DatabaseKeyProvider, db: Session, user_id: uuid.UUID, data: dict) -> bytes:
    data_key = provider.get_or_create_data_key(db, "user", user_id)
    return provider.wrap(json.dumps(data, separators=(",", ":")).encode("utf-8"))


def _decrypt_pii(provider: DatabaseKeyProvider, db: Session, user: User) -> dict:
    if user.birth_date_encrypted is None and user.phone_encrypted is None:
        return {}
    data_key = provider.get_data_key(db, "user", user.id)
    if data_key is None:
        return {}
    out: dict = {}
    if user.birth_date_encrypted is not None:
        out["birth_date"] = json.loads(provider.unwrap(user.birth_date_encrypted).decode())
    if user.phone_encrypted is not None:
        out["phone"] = json.loads(provider.unwrap(user.phone_encrypted).decode())
    return out


def create_user(
    db: Session,
    provider: DatabaseKeyProvider,
    *,
    phone: str,
    birth_date: date,
    language: str,
    settings: Settings,
) -> User:
    """Register a user. Users under 13 are blocked (spec 3.2)."""
    today = date.today()
    age = today.year - birth_date.year - ((today.month, today.day) < (birth_date.month, birth_date.day))
    if age < MIN_AGE:
        raise ValidationError("users under 13 cannot use SISI Health")
    ph = phone_hash(phone, settings)
    if db.execute(select(User).where(User.phone_hash == ph)).scalars().first():
        raise Conflict("phone already registered")
    user = User(
        id=uuid7(),
        pseudonym_id=uuid7(),
        age_band="13-17" if age < settings.self_consent_age else "18+",
        language=language if language in {"en", "sw"} else "en",
        created_at=utc_now_naive(),
    )
    db.add(user)
    db.flush()
    user.phone_encrypted = _encrypt_pii(provider, db, user.id, {"phone": phone})
    user.birth_date_encrypted = _encrypt_pii(provider, db, user.id, {"birth_date": birth_date.isoformat()})
    user.phone_hash = ph
    db.flush()
    return user


def get_by_phone(db: Session, phone: str, settings: Settings) -> User | None:
    return db.execute(
        select(User).where(User.phone_hash == phone_hash(phone, settings))
    ).scalars().first()


def age_of(provider: DatabaseKeyProvider, db: Session, user: User) -> int | None:
    pii = _decrypt_pii(provider, db, user)
    birth = pii.get("birth_date")
    if not birth:
        return None
    born = date.fromisoformat(birth)
    today = date.today()
    return today.year - born.year - ((today.month, today.day) < (born.month, born.day))


def public_view(user: User) -> dict:
    """Non-PII projection: pseudonym, age band, language, status."""
    return {
        "id": str(user.pseudonym_id or user.id),
        "age_band": user.age_band,
        "language": user.language,
        "status": user.status,
        "created_at": user.created_at,
    }
