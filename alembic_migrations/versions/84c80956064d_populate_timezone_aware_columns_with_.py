"""Populate timezone aware columns with existing data

Revision ID: 84c80956064d
Revises: a8f804421577
Create Date: 2025-06-23 17:02:08.221506

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '84c80956064d'
down_revision: Union[str, None] = 'a8f804421577'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade():
    """Populate timezone-aware columns with existing data (assuming UTC)"""
    
    # Update admin_mfa_tokens - copy existing data assuming it's UTC
    op.execute("""
        UPDATE admin_mfa_tokens 
        SET 
            expires_at_tz = expires_at AT TIME ZONE 'UTC',
            created_at_tz = created_at AT TIME ZONE 'UTC'
        WHERE expires_at IS NOT NULL OR created_at IS NOT NULL;
    """)
    
    # Update users - copy existing data assuming it's UTC
    op.execute("""
        UPDATE users 
        SET 
            created_at_tz = created_at AT TIME ZONE 'UTC',
            updated_at_tz = updated_at AT TIME ZONE 'UTC',
            last_admin_login_tz = CASE 
                WHEN last_admin_login IS NOT NULL 
                THEN last_admin_login AT TIME ZONE 'UTC' 
                ELSE NULL 
            END,
            password_changed_at_tz = CASE 
                WHEN password_changed_at IS NOT NULL 
                THEN password_changed_at AT TIME ZONE 'UTC' 
                ELSE NULL 
            END
        WHERE created_at IS NOT NULL OR updated_at IS NOT NULL;
    """)


def downgrade():
    """Clear the timezone-aware columns (rollback)"""
    
    # Clear the timezone-aware columns
    op.execute("""
        UPDATE admin_mfa_tokens 
        SET expires_at_tz = NULL, created_at_tz = NULL;
    """)
    
    op.execute("""
        UPDATE users 
        SET created_at_tz = NULL, updated_at_tz = NULL, 
            last_admin_login_tz = NULL, password_changed_at_tz = NULL;
    """)
