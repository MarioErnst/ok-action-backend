"""add lex_result column to live_sessions

Revision ID: e3f4a5b6c7d8
Revises: d2e3f4a5b6c7
Create Date: 2026-05-08 12:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "e3f4a5b6c7d8"
down_revision: Union[str, None] = "d2e3f4a5b6c7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # lex_result holds the linguistic-versatility analysis Gemini produces
    # at session close when the user selected the 'lex' dimension. Stored as
    # JSONB so the shape can evolve without further migrations.
    op.add_column(
        "live_sessions",
        sa.Column(
            "lex_result",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("live_sessions", "lex_result")
