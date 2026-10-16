"""CC-5 (Phase 7): employer admin (minimal) — employers, staff binding, user link.

Revision ID: 0009
Revises: 0008
Create Date: 2026-10-16

Adds the minimal employer surface approved for Phase 7 (spec build order item 7):
`core.employers`, `core.employer_staff` (staff -> employer binding) and the
nullable `core.users.employer_id` link that lets the aggregate dashboard count a
sponsor's own employees. Wallet and ledger tables are NOT duplicated — the
Phase 4 `school.wallets` / `school.wallet_ledger` already model
`owner_type='employer'` (CC-2), so the employer module reuses
`app.school.service.fund_wallet`. The link is an admin-action opt-in: a
super_admin sets `users.employer_id` explicitly and the change is audited.

ROLLBACK NOTE: forward-only per spec. Rolling back means dropping
`core.employer_staff` and `core.employers` (the `users.employer_id` FK is
dropped first) and restoring the prior backup; employer wallet rows in
`school.wallets` would be orphaned, so the backup restore is the real rollback.
"""

from alembic import op
import sqlalchemy as sa

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ---- core.employers -----------------------------------------------------
    op.create_table(
        "employers",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("county", sa.String(128)),
        sa.Column("status", sa.String(16), nullable=False, server_default="active"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        schema="core",
    )
    op.create_table(
        "employer_staff",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "staff_id",
            sa.Uuid(),
            sa.ForeignKey("core.staff_users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "employer_id",
            sa.Uuid(),
            sa.ForeignKey("core.employers.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("role_within", sa.String(16), nullable=False, server_default="employer_admin"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("staff_id", "employer_id", name="uq_employer_staff_staff_employer"),
        schema="core",
    )
    # ---- core.users.employer_id (admin-action opt-in link) ------------------
    op.add_column(
        "users",
        sa.Column(
            "employer_id", sa.Uuid(), sa.ForeignKey("core.employers.id", ondelete="SET NULL")
        ),
        schema="core",
    )


def downgrade() -> None:
    op.execute(sa.text("ALTER TABLE core.users DROP COLUMN IF EXISTS employer_id"))
    op.execute(sa.text("DROP TABLE IF EXISTS core.employer_staff CASCADE"))
    op.execute(sa.text("DROP TABLE IF EXISTS core.employers CASCADE"))
