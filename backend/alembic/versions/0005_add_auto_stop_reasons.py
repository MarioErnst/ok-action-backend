"""Add auto_stop_strikes and auto_stop_emotion to stop_reason_enum.

Supports the new Live Session strike system: sessions cut by the audio
strike counter use auto_stop_strikes; sessions cut by sustained negative
facial expression use auto_stop_emotion. Existing rows are untouched.

Postgres ALTER TYPE ADD VALUE cannot run inside a transaction block on
older Postgres versions and even on modern versions the new value cannot
be USED in the same transaction where it was added. We use
autocommit_block to issue each ADD VALUE outside the migration's main
transaction. The IF NOT EXISTS clause makes the migration idempotent in
case the value was already added manually.

The downgrade is a no-op: removing enum values from a Postgres enum is
not directly supported and would require rebuilding the type, which is
risky if any rows reference the value. If a rollback is ever necessary,
do it manually and supervised.
"""

from __future__ import annotations

from alembic import op


revision = "0005_add_auto_stop_reasons"
down_revision = "0004_phonation_metrics"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE stop_reason_enum ADD VALUE IF NOT EXISTS 'auto_stop_strikes'")
        op.execute("ALTER TYPE stop_reason_enum ADD VALUE IF NOT EXISTS 'auto_stop_emotion'")


def downgrade() -> None:
    # Intentional no-op. Removing a value from a Postgres enum requires
    # recreating the type and rewriting any tables that reference it.
    # If a rollback is needed it must be done manually and supervised.
    pass
