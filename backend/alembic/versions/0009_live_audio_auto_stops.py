"""Add auto_stop_loudness and auto_stop_phonation to stop_reason_enum.

Supports the live phonation/loudness extension: sessions cut by 3 s of
continuous clipping use auto_stop_loudness; sessions cut by 5 pitch
breaks in a 10 s rolling window use auto_stop_phonation. Existing rows
are untouched.

ALTER TYPE ADD VALUE cannot run inside a transaction block on older
Postgres versions, so we use autocommit_block. The IF NOT EXISTS clause
makes the migration idempotent in case the value was already added
manually before this migration ran.

Downgrade is intentionally a no-op: removing enum values from a
Postgres enum is not directly supported and would require rebuilding
the type, which is risky if rows reference the value.

Revision ID: 0009_live_audio_auto_stops
Revises: 0008_loudness_noise_floor
Create Date: 2026-05-17
"""

from __future__ import annotations

from alembic import op


revision = "0009_live_audio_auto_stops"
down_revision = "0008_loudness_noise_floor"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute(
            "ALTER TYPE stop_reason_enum ADD VALUE IF NOT EXISTS 'auto_stop_loudness'"
        )
        op.execute(
            "ALTER TYPE stop_reason_enum ADD VALUE IF NOT EXISTS 'auto_stop_phonation'"
        )


def downgrade() -> None:
    # Intentional no-op. Removing a value from a Postgres enum requires
    # recreating the type and rewriting any tables that reference it.
    # If a rollback is needed it must be done manually and supervised.
    pass
