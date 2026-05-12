"""Add videos table for capsule metadata.

Revision ID: 0003_add_videos_table
Revises: 0002_add_body_expression
Create Date: 2026-05-12
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision = "0003_add_videos_table"
down_revision = "0002_add_body_expression"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "videos",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
        ),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("s3_key", sa.String(length=512), nullable=False, unique=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )


def downgrade() -> None:
    op.drop_table("videos")
