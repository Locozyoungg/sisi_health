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
        "school:queue",
        "school:actions",
        "school:reidentify",
        "school:consents",
        "school:dashboard",
        "vouchers:issue",
        "vouchers:redeem",
        "vouchers:reconcile",
        "corridor:queue",
        "corridor:consults",
        "corridor:referrals",
        "corridor:surgery",
        "corridor:facilities:read",
        "corridor:facilities:write",
        "corridor:tracking",
        "corridor:aggregates",
        "corridor:reminders",
        "corridor:education:read",
    },
    "nurse": {
        "rules:read",
        "school:queue",
        "school:actions",
        "school:reidentify",
        "school:consents",
        "school:dashboard",
        "corridor:queue",
        "corridor:consults",
        "corridor:tracking",
        "corridor:reminders",
        "corridor:facilities:read",
        "corridor:education:read",
    },
    "gynecologist": {
        "rules:read",
        "rules:activate",
        "corridor:queue",
        "corridor:consults",
        "corridor:referrals",
        "corridor:surgery",
        "corridor:facilities:read",
        "corridor:education:read",
    },
    "school_admin": {
        "rules:read",
        "school:queue",
        "school:actions",
        "school:consents",
        "school:dashboard",
        "vouchers:issue",
        "vouchers:reconcile",
        "corridor:education:read",
    },
    "employer_admin": set(),
    "moh_viewer": {"rules:read", "corridor:aggregates"},
    "pharmacy": {"vouchers:redeem"},
}

VALID_ROLES = set(ROLE_PERMISSIONS)


def has_permission(role: str, permission: str) -> bool:
    return permission in ROLE_PERMISSIONS.get(role, set())


class PermissionDenied(Forbidden):
    def __init__(self, role: str, permission: str) -> None:
        super().__init__(f"role {role} lacks permission {permission}")
        self.code = "permission_denied"
