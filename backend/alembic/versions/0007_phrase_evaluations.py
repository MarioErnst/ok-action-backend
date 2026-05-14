"""Add per-phrase evaluation tables for accentuation and pronunciation.

Both tables persist one row per phrase evaluated inside a session, keyed by
composite PK (session_id, phrase_index). They reference the unified
`prompts` catalog with ON DELETE RESTRICT so deleting a phrase used by
historical sessions is blocked (matches the precision/linguistic_versatility
rounds convention).

The four sub-scores per row enable two new flows:
- detail per phrase in the session history (UI breakdown)
- insights/weakest-prompts query: aggregate avg sub-score by prompt_id
  to surface the prompts where the user has the lowest performance.

Revision ID: 0007_phrase_evaluations
Revises: 0006_pause_metrics_prompt_id
Create Date: 2026-05-14
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision = "0007_phrase_evaluations"
down_revision = "0006_pause_metrics_prompt_id"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "accentuation_phrase_evaluations",
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("phrase_index", sa.SmallInteger(), nullable=False),
        sa.Column("prompt_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("pronunciation_score", sa.SmallInteger(), nullable=False),
        sa.Column("rhythm_score", sa.SmallInteger(), nullable=False),
        sa.Column("intonation_score", sa.SmallInteger(), nullable=False),
        sa.Column("stress_score", sa.SmallInteger(), nullable=False),
        sa.ForeignKeyConstraint(
            ["session_id"], ["sessions.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["prompt_id"], ["prompts.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint(
            "session_id", "phrase_index", name="pk_accentuation_phrase_evaluations"
        ),
        sa.CheckConstraint(
            "pronunciation_score BETWEEN 0 AND 100",
            name="ck_acc_phrase_pronunciation_score",
        ),
        sa.CheckConstraint(
            "rhythm_score BETWEEN 0 AND 100",
            name="ck_acc_phrase_rhythm_score",
        ),
        sa.CheckConstraint(
            "intonation_score BETWEEN 0 AND 100",
            name="ck_acc_phrase_intonation_score",
        ),
        sa.CheckConstraint(
            "stress_score BETWEEN 0 AND 100",
            name="ck_acc_phrase_stress_score",
        ),
        sa.CheckConstraint(
            "phrase_index >= 0",
            name="ck_acc_phrase_index_non_negative",
        ),
    )
    op.create_index(
        "ix_accentuation_phrase_evaluations_prompt",
        "accentuation_phrase_evaluations",
        ["prompt_id"],
    )

    op.create_table(
        "pronunciation_phrase_evaluations",
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("phrase_index", sa.SmallInteger(), nullable=False),
        sa.Column("prompt_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("vowel_score", sa.SmallInteger(), nullable=False),
        sa.Column("consonant_score", sa.SmallInteger(), nullable=False),
        sa.Column("fluency_score", sa.SmallInteger(), nullable=False),
        sa.Column("intelligibility_score", sa.SmallInteger(), nullable=False),
        sa.ForeignKeyConstraint(
            ["session_id"], ["sessions.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["prompt_id"], ["prompts.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint(
            "session_id", "phrase_index", name="pk_pronunciation_phrase_evaluations"
        ),
        sa.CheckConstraint(
            "vowel_score BETWEEN 0 AND 100",
            name="ck_pron_phrase_vowel_score",
        ),
        sa.CheckConstraint(
            "consonant_score BETWEEN 0 AND 100",
            name="ck_pron_phrase_consonant_score",
        ),
        sa.CheckConstraint(
            "fluency_score BETWEEN 0 AND 100",
            name="ck_pron_phrase_fluency_score",
        ),
        sa.CheckConstraint(
            "intelligibility_score BETWEEN 0 AND 100",
            name="ck_pron_phrase_intelligibility_score",
        ),
        sa.CheckConstraint(
            "phrase_index >= 0",
            name="ck_pron_phrase_index_non_negative",
        ),
    )
    op.create_index(
        "ix_pronunciation_phrase_evaluations_prompt",
        "pronunciation_phrase_evaluations",
        ["prompt_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_pronunciation_phrase_evaluations_prompt",
        table_name="pronunciation_phrase_evaluations",
    )
    op.drop_table("pronunciation_phrase_evaluations")
    op.drop_index(
        "ix_accentuation_phrase_evaluations_prompt",
        table_name="accentuation_phrase_evaluations",
    )
    op.drop_table("accentuation_phrase_evaluations")
