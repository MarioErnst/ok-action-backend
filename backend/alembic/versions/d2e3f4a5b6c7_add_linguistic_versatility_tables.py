"""add linguistic_versatility tables

Revision ID: d2e3f4a5b6c7
Revises: c1d2e3f4a5b6
Create Date: 2026-05-08 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "d2e3f4a5b6c7"
down_revision: Union[str, None] = "c1d2e3f4a5b6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Three open-ended prompts that invite ~30s answers. Long answers give Gemini
# enough text to measure lexical diversity reliably (TTR-style metrics on
# fewer than ~50 words are too noisy to be meaningful).
SEED_QUESTIONS = [
    {
        "text": "Contanos sobre algún proyecto, viaje o experiencia personal que recuerdes con cariño. Detallá qué hiciste, quiénes te acompañaron y qué aprendiste.",
        "category": "personal_experience",
        "difficulty_level": "basic",
    },
    {
        "text": "Si tuvieras que convencer a alguien de probar tu hobby o actividad favorita, ¿qué le dirías? Describí los aspectos que te apasionan y por qué la disfrutás.",
        "category": "persuasion",
        "difficulty_level": "intermediate",
    },
    {
        "text": "¿Cómo creés que serán las ciudades dentro de 50 años? Pensá en transporte, viviendas, trabajo y vida cotidiana.",
        "category": "speculative",
        "difficulty_level": "advanced",
    },
]


def upgrade() -> None:
    op.create_table(
        "linguistic_versatility_questions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("category", sa.String(length=100), nullable=False),
        sa.Column("difficulty_level", sa.String(length=20), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "linguistic_versatility_sessions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        # mode distinguishes guided sessions (with predefined questions) from
        # free sessions (single chunk of free speech). Both share the same table
        # so history queries return everything in one place.
        sa.Column("mode", sa.String(length=20), nullable=False),
        sa.Column("total_rounds", sa.Integer(), nullable=False),
        sa.Column("completed_rounds", sa.Integer(), nullable=False),
        sa.Column("overall_score", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "linguistic_versatility_rounds",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("session_id", sa.Uuid(), nullable=False),
        # question_id is nullable because free-mode sessions have a single round
        # without a predefined question.
        sa.Column("question_id", sa.Uuid(), nullable=True),
        sa.Column("question_text", sa.Text(), nullable=True),
        sa.Column("versatility_score", sa.Integer(), nullable=True),
        sa.Column("vocabulary_richness", sa.Integer(), nullable=True),
        sa.Column("feedback", sa.Text(), nullable=True),
        sa.Column("audio_intelligible", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["session_id"], ["linguistic_versatility_sessions.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["question_id"], ["linguistic_versatility_questions.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_linguistic_versatility_rounds_session_id",
        "linguistic_versatility_rounds",
        ["session_id"],
    )

    # Seed the three predefined questions in the same migration so a fresh
    # environment is usable immediately after upgrade.
    questions_table = sa.table(
        "linguistic_versatility_questions",
        sa.column("id", sa.Uuid()),
        sa.column("text", sa.Text()),
        sa.column("category", sa.String()),
        sa.column("difficulty_level", sa.String()),
        sa.column("is_active", sa.Boolean()),
        sa.column("created_at", sa.DateTime(timezone=True)),
    )
    import uuid
    from datetime import datetime, timezone

    op.bulk_insert(
        questions_table,
        [
            {
                "id": uuid.uuid4(),
                "text": q["text"],
                "category": q["category"],
                "difficulty_level": q["difficulty_level"],
                "is_active": True,
                "created_at": datetime.now(timezone.utc),
            }
            for q in SEED_QUESTIONS
        ],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_linguistic_versatility_rounds_session_id",
        table_name="linguistic_versatility_rounds",
    )
    op.drop_table("linguistic_versatility_rounds")
    op.drop_table("linguistic_versatility_sessions")
    op.drop_table("linguistic_versatility_questions")
