"""Add nullable noise_floor_db to loudness_metrics.

The frontend measures the ambient noise floor during a short calibration
window before each session and sends the value with the session payload.
NULL is allowed for rows persisted before the calibration UX rolled out.

Revision ID: 0008_loudness_noise_floor
Revises: 0007_phrase_evaluations
Create Date: 2026-05-14
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0008_loudness_noise_floor"
down_revision = "0007_phrase_evaluations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "loudness_metrics",
        sa.Column("noise_floor_db", sa.Numeric(8, 2), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("loudness_metrics", "noise_floor_db")
