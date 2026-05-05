"""add live sessions table

Revision ID: 5b86452f9a84
Revises: e7f3a1b2c9d0
Create Date: 2026-05-05 10:32:27.458658

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '5b86452f9a84'
down_revision: Union[str, None] = 'e7f3a1b2c9d0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # pause_sessions drop intentionally removed: table exists in DB but has no entity yet.
    # Alembic autogenerate detected it as removed; keeping it untouched to avoid data loss.
    op.create_table('live_sessions',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('user_id', sa.Uuid(), nullable=False),
    sa.Column('selected_dims', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('analyses', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('overall_score', sa.Numeric(precision=5, scale=2), nullable=True),
    sa.Column('total_errors', sa.Integer(), nullable=False),
    sa.Column('duration_seconds', sa.Integer(), nullable=False),
    sa.Column('stop_reason', sa.String(length=20), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('live_sessions')
