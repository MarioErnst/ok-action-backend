"""Add extended phonation metrics columns.

Adds three nullable columns to `phonation_session_exercises` that the new
voiceSegmentation-driven worklet pipeline emits per exercise:

- `max_sustained_voicing_ms`: longest uninterrupted voiced block (ms). Best
  proxy for breath support without penalising natural pauses.
- `db_slope`: slope of dB over time within voiced blocks (db/sec). Negative
  means the user fades as the exercise progresses.
- `weak_phrase_endings_count`: count of voiced blocks whose end is N dB below
  their start, indicating loss of support at clause endings.

All columns are nullable so legacy rows captured before this migration are
still valid; consumers must handle `None`.

Revision ID: 0004_phonation_metrics
Revises: 0003_add_videos_table
Create Date: 2026-05-13
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0004_phonation_metrics"
down_revision = "0003_add_videos_table"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "phonation_session_exercises",
        sa.Column("max_sustained_voicing_ms", sa.Integer(), nullable=True),
    )
    op.add_column(
        "phonation_session_exercises",
        sa.Column("db_slope", sa.Numeric(6, 3), nullable=True),
    )
    op.add_column(
        "phonation_session_exercises",
        sa.Column("weak_phrase_endings_count", sa.Integer(), nullable=True),
    )
    op.create_check_constraint(
        "ck_phonation_exercise_max_sustained_voicing_ms",
        "phonation_session_exercises",
        "max_sustained_voicing_ms IS NULL OR max_sustained_voicing_ms >= 0",
    )
    op.create_check_constraint(
        "ck_phonation_exercise_weak_phrase_endings_count",
        "phonation_session_exercises",
        "weak_phrase_endings_count IS NULL OR weak_phrase_endings_count >= 0",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_phonation_exercise_weak_phrase_endings_count",
        "phonation_session_exercises",
        type_="check",
    )
    op.drop_constraint(
        "ck_phonation_exercise_max_sustained_voicing_ms",
        "phonation_session_exercises",
        type_="check",
    )
    op.drop_column("phonation_session_exercises", "weak_phrase_endings_count")
    op.drop_column("phonation_session_exercises", "db_slope")
    op.drop_column("phonation_session_exercises", "max_sustained_voicing_ms")
