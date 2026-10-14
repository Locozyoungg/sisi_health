"""Consistent JSON envelope for every response: {success, data, error, meta}."""

from typing import Any


def ok(data: Any, meta: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"success": True, "data": data, "error": None, "meta": meta or {}}


def err(code: str, message: str, status: int) -> dict[str, Any]:
    return {
        "success": False,
        "data": None,
        "error": {"code": code, "message": message},
        "meta": {"status": status},
    }
