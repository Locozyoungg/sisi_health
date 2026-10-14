"""Router aggregation."""

from fastapi import APIRouter

from app.api.v1 import (
    admin,
    audit,
    auth,
    consent,
    diary,
    dsr,
    health,
    rules,
    school,
    staff_auth,
    users,
    vouchers,
)

router = APIRouter()
router.include_router(health.router)
router.include_router(auth.router, prefix="/auth", tags=["auth"])
router.include_router(staff_auth.router, prefix="/staff/auth", tags=["staff-auth"])
router.include_router(users.router, prefix="/users", tags=["users"])
router.include_router(consent.router, prefix="/consent", tags=["consent"])
router.include_router(dsr.router, prefix="/dsr", tags=["dsr"])
router.include_router(diary.router, prefix="/diary", tags=["diary"])
router.include_router(rules.router, prefix="/rules", tags=["rules"])
router.include_router(audit.router, prefix="/audit", tags=["audit"])
router.include_router(admin.router, prefix="/admin", tags=["admin"])
router.include_router(school.router, tags=["school"])
router.include_router(vouchers.router, tags=["vouchers"])
