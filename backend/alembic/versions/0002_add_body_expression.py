"""Add body expression module.

Revision ID: 0002_add_body_expression
Revises: 0001_uniform_schema
Create Date: 2026-05-11
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0002_add_body_expression"
down_revision = "0001_uniform_schema"
branch_labels = None
depends_on = None


BODY_FRAMING_MODE_VALUES = ("upper_body", "full_body", "mixed")


def upgrade() -> None:
    op.execute("ALTER TYPE module_enum ADD VALUE IF NOT EXISTS 'body_expression'")
    op.execute(
        "CREATE TYPE body_framing_mode_enum AS ENUM "
        f"({', '.join(repr(v) for v in BODY_FRAMING_MODE_VALUES)})"
    )

    op.create_table(
        "body_expression_metrics",
        sa.Column(
            "session_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("sessions.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("posture_score", sa.SmallInteger, nullable=False),
        sa.Column("openness_score", sa.SmallInteger, nullable=False),
        sa.Column("gesture_score", sa.SmallInteger, nullable=False),
        sa.Column("stability_score", sa.SmallInteger, nullable=False),
        sa.Column("energy_score", sa.SmallInteger, nullable=False),
        sa.Column("framing_score", sa.SmallInteger, nullable=False),
        sa.Column("tracked_pct", sa.SmallInteger, nullable=False),
        sa.Column("hands_visible_pct", sa.SmallInteger, nullable=False),
        sa.Column("excessive_movement_pct", sa.SmallInteger, nullable=False),
        sa.Column("calibration_quality_pct", sa.SmallInteger, nullable=False),
        sa.Column(
            "framing_mode",
            postgresql.ENUM(
                *BODY_FRAMING_MODE_VALUES,
                name="body_framing_mode_enum",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.CheckConstraint(
            "posture_score BETWEEN 0 AND 100",
            name="ck_body_posture_score",
        ),
        sa.CheckConstraint(
            "openness_score BETWEEN 0 AND 100",
            name="ck_body_openness_score",
        ),
        sa.CheckConstraint(
            "gesture_score BETWEEN 0 AND 100",
            name="ck_body_gesture_score",
        ),
        sa.CheckConstraint(
            "stability_score BETWEEN 0 AND 100",
            name="ck_body_stability_score",
        ),
        sa.CheckConstraint(
            "energy_score BETWEEN 0 AND 100",
            name="ck_body_energy_score",
        ),
        sa.CheckConstraint(
            "framing_score BETWEEN 0 AND 100",
            name="ck_body_framing_score",
        ),
        sa.CheckConstraint(
            "tracked_pct BETWEEN 0 AND 100",
            name="ck_body_tracked_pct",
        ),
        sa.CheckConstraint(
            "hands_visible_pct BETWEEN 0 AND 100",
            name="ck_body_hands_visible_pct",
        ),
        sa.CheckConstraint(
            "excessive_movement_pct BETWEEN 0 AND 100",
            name="ck_body_excessive_movement_pct",
        ),
        sa.CheckConstraint(
            "calibration_quality_pct BETWEEN 0 AND 100",
            name="ck_body_calibration_quality_pct",
        ),
    )


def downgrade() -> None:
    op.drop_table("body_expression_metrics")
    op.execute("DROP TYPE IF EXISTS body_framing_mode_enum")
    # PostgreSQL cannot remove a single enum value portably. The module_enum
    # value remains after downgrade, but no table depends on it.
