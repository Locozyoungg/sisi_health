"""User profile (non-medical)."""

from typing import Annotated, Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.envelope import ok
from app.auth.deps import get_current_user
from app.db import get_db
from app.models import User
from app.users.service import public_view

router = APIRouter()


class ProfilePatch(BaseModel):
    language: str | None = None


@router.get("/me")
def me(
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> dict[str, Any]:
    return ok(public_view(user))


@router.patch("/me")
def patch_me(
    body: ProfilePatch,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> dict[str, Any]:
    if body.language in {"en", "sw"}:
        user.language = body.language
        db.commit()
    return ok(public_view(user))
