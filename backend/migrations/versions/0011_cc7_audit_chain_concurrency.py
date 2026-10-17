"""CC-7 (Phase 8): audit chain integrity under concurrent inserts.

Revision ID: 0011
Revises: 0010
Create Date: 2026-10-17

The chain trigger serialized inserts with pg_advisory_xact_lock, but the
IDENTITY seq value is assigned BEFORE triggers fire — so concurrent
transactions got seqs in row-formation order while the hash chain followed
lock-acquisition order. When the orders differed, the chain broke in pairwise
swaps (reproduced by the 1,000-concurrent-USSD load test; verifier flagged 42
breaks). Fix: seq is now assigned INSIDE the lock (a plain sequence owned by
the column, nextval taken in the trigger after the advisory lock), so seq
order always equals chain order.

Existing data with breaks must be re-anchored with
`scripts/repair_audit_chain.py` (dev/demo only).

ROLLBACK NOTE: forward-only per spec. Rolling back means restoring the
previous trigger + IDENTITY (re-anchoring again) and restoring the backup.
"""
from alembic import op
import sqlalchemy as sa

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    max_seq = bind.execute(sa.text("SELECT COALESCE(max(seq), 0) FROM audit.audit_events")).scalar_one()

    # seq becomes trigger-assigned under the advisory lock (no identity default).
    op.execute(sa.text("ALTER TABLE audit.audit_events ALTER COLUMN seq DROP IDENTITY"))
    op.execute(sa.text("CREATE SEQUENCE IF NOT EXISTS audit.audit_events_seq_seq OWNED BY audit.audit_events.seq"))
    if max_seq > 0:  # a fresh DB starts at 1; setval(0) is out of bounds
        op.execute(sa.text(f"SELECT setval('audit.audit_events_seq_seq', {int(max_seq)})"))

    op.execute(
        sa.text(
            """
            CREATE OR REPLACE FUNCTION audit.chain_insert() RETURNS trigger AS $$
            DECLARE
                prev bytea;
            BEGIN
                PERFORM pg_advisory_xact_lock(424242);
                -- seq is assigned under the lock so seq order == chain order.
                NEW.seq := nextval('audit.audit_events_seq_seq');
                SELECT row_hash INTO prev FROM audit.audit_events ORDER BY seq DESC LIMIT 1;
                NEW.prev_hash := coalesce(prev, '\\x00'::bytea);
                NEW.row_hash := digest(
                    NEW.prev_hash || convert_to(
                        jsonb_build_object(
                            'event_type',    NEW.event_type,
                            'actor_type',    NEW.actor_type,
                            'actor_id',      NEW.actor_id,
                            'actor_role',    NEW.actor_role,
                            'resource_type', NEW.resource_type,
                            'resource_id',   NEW.resource_id,
                            'payload',       NEW.payload,
                            'created_at',    NEW.created_at
                        )::text, 'UTF8'),
                    'sha256');
                RETURN NEW;
            END;
            $$ LANGUAGE plpgsql;
            """
        )
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            """
            CREATE OR REPLACE FUNCTION audit.chain_insert() RETURNS trigger AS $$
            DECLARE
                prev bytea;
            BEGIN
                PERFORM pg_advisory_xact_lock(424242);
                SELECT row_hash INTO prev FROM audit.audit_events ORDER BY seq DESC LIMIT 1;
                NEW.prev_hash := coalesce(prev, '\\x00'::bytea);
                NEW.row_hash := digest(
                    NEW.prev_hash || convert_to(
                        jsonb_build_object(
                            'event_type',    NEW.event_type,
                            'actor_type',    NEW.actor_type,
                            'actor_id',      NEW.actor_id,
                            'actor_role',    NEW.actor_role,
                            'resource_type', NEW.resource_type,
                            'resource_id',   NEW.resource_id,
                            'payload',       NEW.payload,
                            'created_at',    NEW.created_at
                        )::text, 'UTF8'),
                    'sha256');
                RETURN NEW;
            END;
            $$ LANGUAGE plpgsql;
            """
        )
    )
