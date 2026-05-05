"""add_muletillas_tables

Revision ID: e7f3a1b2c9d0
Revises: 428244644432
Create Date: 2026-04-30 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'e7f3a1b2c9d0'
down_revision: Union[str, None] = '428244644432'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'muletillas_sessions',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('user_id', sa.UUID(), nullable=False),
        sa.Column('question_text', sa.Text(), nullable=False),
        sa.Column('overall_score', sa.Numeric(precision=4, scale=2), nullable=False),
        sa.Column('fluency_score', sa.Numeric(precision=4, scale=2), nullable=False),
        sa.Column('muletillas_score', sa.Numeric(precision=4, scale=2), nullable=False),
        sa.Column('total_muletillas_count', sa.Integer(), nullable=False),
        sa.Column('muletillas_per_minute', sa.Numeric(precision=5, scale=2), nullable=False),
        sa.Column('feedback', sa.Text(), nullable=False),
        sa.Column('strengths', sa.Text(), nullable=False),
        sa.Column('improvement_areas', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_table(
        'phrase_muletillas',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('session_id', sa.UUID(), nullable=False),
        sa.Column('word', sa.String(length=100), nullable=False),
        sa.Column('count', sa.Integer(), nullable=False),
        sa.Column('severity', sa.String(length=10), nullable=False),
        sa.Column('suggestion', sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(['session_id'], ['muletillas_sessions.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )


def downgrade() -> None:
    op.drop_table('phrase_muletillas')
    op.drop_table('muletillas_sessions')
