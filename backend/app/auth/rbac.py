"""RBAC: role -> permission sets (docs/role-matrix.md is the human-readable source;
tests assert every endpoint denies unauthorized roles)."""

from app.core.errors import Forbidden

ROLE_PERMISSIONS: dict[str, set[str]] = {
    "super_admin": {
        "rules:read",
        "rules:activate",
        "dsr:process",
        "audit:read",
        "audit:verify",
        "admin:users",
        "admin:dsr",
    },
    "nurse": {"rules:read"},
    "gynecologist": {"rules:read", "rules:activate"},
    "school_admin": {"rules:read"},
    "employer_admin": set(),
    "moh_viewer": {"rules:read"},
}

VALID_ROLES = set(ROLE_PERMISSIONS)


def has_permission(role: str, permission: str) -> bool:
    return permission in ROLE_PERMISSIONS.get(role, set())


class PermissionDenied(Forbidden):
    def __init__(self, role: str, permission: str) -> None:
        super().__init__(f"role {role} lacks permission {permission}")
        self.code = "permission_denied"
