"""CC-6 (Phase 8): generic DB-backed auth throttle.

Revision ID: 0010
Revises: 0009
Create Date: 2026-10-17

Adds `core.auth_throttle`, one row per throttle key, backing
`app/auth/rate_limit.py`. Phase 1 rate-limited OTP requests
(`core.otp_requests`) but staff login had no brute-force protection at all, and
there was no reusable limiter for other auth surfaces. The table stores the
namespaced credential handle (e.g. `staff_login:<email>`), the current window
start, the failure count in that window, and the lockout expiry. It holds no
secret material and is written only through the shared limiter.

ROLLBACK NOTE: forward-only per spec. Rolling back means dropping
`core.auth_throttle` (all in-flight lockout state is lost — every throttled
surface starts with a clean window) and restoring the prior backup if the state
must be preserved.
"""

from alembic import op
import sqlalchemy as sa

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "auth_throttle",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("key", sa.String(128), nullable=False, unique=True),
        sa.Column(
            "window_start", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("locked_until", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        schema="core",
    )


def downgrade() -> None:
    op.execute(sa.text("DROP TABLE IF EXISTS core.auth_throttle CASCADE"))
