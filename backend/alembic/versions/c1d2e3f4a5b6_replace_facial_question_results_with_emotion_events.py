"""replace facial question_results with emotion_events

Revision ID: c1d2e3f4a5b6
Revises: 3f8b1c2d4e5a
Create Date: 2026-05-07 23:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "c1d2e3f4a5b6"
down_revision: Union[str, None] = "3f8b1c2d4e5a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Drop legacy facial expression tables. IF EXISTS makes this safe whether
    # the previous migration was applied or not (some local DBs ended up
    # without these tables due to an out-of-band reset).
    op.execute("DROP TABLE IF EXISTS facial_expression_question_results CASCADE")
    op.execute("DROP TABLE IF EXISTS facial_expression_sessions CASCADE")

    # Recreate sessions table with the new emotion-tracking shape.
    op.create_table(
        "facial_expression_sessions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.Column("dominant_emotion", sa.String(length=20), nullable=True),
        sa.Column("dominant_percentage", sa.Integer(), nullable=True),
        sa.Column(
            "emotion_distribution",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    # One row per detected change of dominant emotion during a session.
    # gestures stores the active gestures and their intensities at that instant.
    op.create_table(
        "facial_expression_emotion_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("t_ms", sa.Integer(), nullable=False),
        sa.Column("emotion", sa.String(length=20), nullable=False),
        sa.Column(
            "gestures",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["session_id"], ["facial_expression_sessions.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_facial_expression_emotion_events_session_id",
        "facial_expression_emotion_events",
        ["session_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_facial_expression_emotion_events_session_id",
        table_name="facial_expression_emotion_events",
    )
    op.drop_table("facial_expression_emotion_events")
    op.drop_table("facial_expression_sessions")
