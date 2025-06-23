"""Add timezone aware datetime columns

Revision ID: a8f804421577
Revises: f91ff15824da
Create Date: 2025-06-23 16:42:27.427739

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a8f804421577'
down_revision: Union[str, None] = 'f91ff15824da'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade():
    """Add timezone-aware columns alongside existing ones"""
    from sqlalchemy.dialects import postgresql
    
    # Add new timezone-aware columns to admin_mfa_tokens
    op.add_column('admin_mfa_tokens', 
        sa.Column('expires_at_tz', postgresql.TIMESTAMP(timezone=True), nullable=True)
    )
    op.add_column('admin_mfa_tokens', 
        sa.Column('created_at_tz', postgresql.TIMESTAMP(timezone=True), nullable=True)
    )
    
    # Add new timezone-aware columns to users table
    op.add_column('users', 
        sa.Column('created_at_tz', postgresql.TIMESTAMP(timezone=True), nullable=True)
    )
    op.add_column('users', 
        sa.Column('updated_at_tz', postgresql.TIMESTAMP(timezone=True), nullable=True)
    )
    op.add_column('users', 
        sa.Column('last_admin_login_tz', postgresql.TIMESTAMP(timezone=True), nullable=True)
    )
    op.add_column('users', 
        sa.Column('password_changed_at_tz', postgresql.TIMESTAMP(timezone=True), nullable=True)
    )


def downgrade():
    """Remove timezone-aware columns if rollback is needed"""
    
    # Remove the new columns
    op.drop_column('admin_mfa_tokens', 'expires_at_tz')
    op.drop_column('admin_mfa_tokens', 'created_at_tz')
    
    op.drop_column('users', 'created_at_tz')
    op.drop_column('users', 'updated_at_tz')
    op.drop_column('users', 'last_admin_login_tz')
    op.drop_column('users', 'password_changed_at_tz')