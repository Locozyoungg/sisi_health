"""API error hierarchy, mapped to a consistent JSON envelope (see docs/role-matrix.md
for who may see what; error messages never leak phone numbers, names, or symptom data)."""

from typing import Any


class AppError(Exception):
    status_code = 500
    code = "internal_error"

    def __init__(self, message: str = "", details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = message or "An unexpected error occurred."
        self.details = details or {}


class ValidationError(AppError):
    status_code = 422
    code = "validation_error"


class Unauthorized(AppError):
    status_code = 401
    code = "unauthorized"


class Forbidden(AppError):
    status_code = 403
    code = "forbidden"


class NotFound(AppError):
    status_code = 404
    code = "not_found"


class Conflict(AppError):
    status_code = 409
    code = "conflict"


class RateLimited(AppError):
    status_code = 429
    code = "rate_limited"


class Locked(AppError):
    status_code = 423
    code = "locked"


class PreconditionFailed(AppError):
    status_code = 428
    code = "precondition_failed"


class UnvalidatedRulesError(AppError):
    status_code = 409
    code = "rules_not_validated"
