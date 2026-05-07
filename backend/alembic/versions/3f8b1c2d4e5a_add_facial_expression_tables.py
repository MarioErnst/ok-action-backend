"""add_facial_expression_tables

Revision ID: 3f8b1c2d4e5a
Revises: 177abcd602b1
Create Date: 2026-05-07 10:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "3f8b1c2d4e5a"
down_revision: Union[str, None] = "177abcd602b1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "facial_expression_sessions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("baseline_pucker", sa.Numeric(precision=5, scale=4), nullable=False),
        sa.Column("baseline_brow_down", sa.Numeric(precision=5, scale=4), nullable=False),
        sa.Column("baseline_lips_down", sa.Numeric(precision=5, scale=4), nullable=False),
        sa.Column("overall_score", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "facial_expression_question_results",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("question_id", sa.String(length=50), nullable=False),
        sa.Column("question_text", sa.Text(), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.Column("frames", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("pucker_score", sa.Integer(), nullable=True),
        sa.Column("brow_down_score", sa.Integer(), nullable=True),
        sa.Column("lips_down_score", sa.Integer(), nullable=True),
        sa.Column("question_score", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["session_id"], ["facial_expression_sessions.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("facial_expression_question_results")
    op.drop_table("facial_expression_sessions")
