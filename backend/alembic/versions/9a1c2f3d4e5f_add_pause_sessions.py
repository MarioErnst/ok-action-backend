"""add_pause_sessions

Revision ID: 9a1c2f3d4e5f
Revises: e3f4a5b6c7d8
Create Date: 2026-04-26 20:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '9a1c2f3d4e5f'
down_revision: Union[str, None] = 'e3f4a5b6c7d8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'pause_sessions',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('user_id', sa.Uuid(), nullable=False),
        sa.Column('prompt_text', sa.String(length=500), nullable=False),
        sa.Column('duration_ms', sa.Integer(), nullable=False),
        sa.Column('total_pauses', sa.Integer(), nullable=False),
        sa.Column('total_pause_duration_ms', sa.Integer(), nullable=False),
        sa.Column('average_pause_ms', sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column('longest_pause_ms', sa.Integer(), nullable=False),
        sa.Column('silence_ratio', sa.Numeric(precision=6, scale=4), nullable=False),
        sa.Column('classification', sa.String(length=50), nullable=False),
        sa.Column('pauses', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('pause_sessions')
