"""Add nullable prompt_id FK to pause_metrics.

Lets the pauses module persist which prompt from the unified catalog the
user practised on. NULL is permitted on legacy rows captured before the
catalog migration. ON DELETE RESTRICT prevents removing a prompt that is
still referenced by historical sessions, matching the convention used by
precision_rounds.prompt_id.

Revision ID: 0006_pause_metrics_prompt_id
Revises: 0005_add_auto_stop_reasons
Create Date: 2026-05-13
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision = "0006_pause_metrics_prompt_id"
down_revision = "0005_add_auto_stop_reasons"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "pause_metrics",
        sa.Column("prompt_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_pause_metrics_prompt_id",
        "pause_metrics",
        "prompts",
        ["prompt_id"],
        ["id"],
        ondelete="RESTRICT",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_pause_metrics_prompt_id", "pause_metrics", type_="foreignkey"
    )
    op.drop_column("pause_metrics", "prompt_id")
