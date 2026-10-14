"""Diary sync (encrypted, append-only) and read-back. Consent is enforced here:
no consent, no diary processing."""

from typing import Annotated, Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import ProviderDep
from app.api.envelope import ok
from app.auth.deps import get_current_user
from app.consent.service import require_consent
from app.db import get_db
from app.diary.service import SyncEntry, get_entries, sync_entries
from app.models import User
from app.users.service import age_of

router = APIRouter()


class SyncIn(BaseModel):
    entries: list[SyncEntry] = Field(min_length=1, max_length=200)


@router.post("/sync")
def sync(
    body: SyncIn,
    db: Annotated[Session, Depends(get_db)],
    provider: ProviderDep,
    user: Annotated[User, Depends(get_current_user)],
) -> dict[str, Any]:
    require_consent(db, user, age_of(provider, db, user))
    result = sync_entries(db, provider, user, body.entries)
    db.commit()
    return ok(result)


@router.get("/entries")
def entries(
    db: Annotated[Session, Depends(get_db)],
    provider: ProviderDep,
    user: Annotated[User, Depends(get_current_user)],
) -> dict[str, Any]:
    require_consent(db, user, age_of(provider, db, user))
    return ok(get_entries(db, provider, user))
