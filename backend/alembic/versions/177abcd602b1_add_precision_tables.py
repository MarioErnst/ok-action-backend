"""add_precision_tables

Revision ID: 177abcd602b1
Revises: 5b86452f9a84
Create Date: 2026-05-06 15:38:35.469376

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '177abcd602b1'
down_revision: Union[str, None] = '5b86452f9a84'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'precision_questions',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('text', sa.Text(), nullable=False),
        sa.Column('category', sa.String(length=100), nullable=False),
        sa.Column('difficulty_level', sa.String(length=20), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_table(
        'precision_sessions',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('user_id', sa.Uuid(), nullable=False),
        sa.Column('mode', sa.String(length=20), nullable=False),
        sa.Column('total_rounds', sa.Integer(), nullable=False),
        sa.Column('completed_rounds', sa.Integer(), nullable=False),
        sa.Column('overall_score', sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_table(
        'precision_rounds',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('session_id', sa.Uuid(), nullable=False),
        sa.Column('question_id', sa.Uuid(), nullable=False),
        sa.Column('question_text', sa.Text(), nullable=False),
        sa.Column('audio_duration_secs', sa.Numeric(precision=6, scale=2), nullable=True),
        sa.Column('transcript', sa.Text(), nullable=True),
        sa.Column('relevance_score', sa.Integer(), nullable=True),
        sa.Column('directness_score', sa.Integer(), nullable=True),
        sa.Column('conciseness_score', sa.Integer(), nullable=True),
        sa.Column('overall_score', sa.Integer(), nullable=True),
        sa.Column('feedback', sa.Text(), nullable=True),
        sa.Column('strengths', postgresql.ARRAY(sa.Text()), nullable=True),
        sa.Column('improvement_areas', postgresql.ARRAY(sa.Text()), nullable=True),
        sa.Column('noise_level', sa.String(length=10), nullable=False),
        sa.Column('audio_intelligible', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['session_id'], ['precision_sessions.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['question_id'], ['precision_questions.id']),
        sa.PrimaryKeyConstraint('id'),
    )


def downgrade() -> None:
    op.drop_table('precision_rounds')
    op.drop_table('precision_sessions')
    op.drop_table('precision_questions')
