# Replace the content of: alembic_migrations/versions/add_admin_security_tables.py

"""Add admin security tables

Revision ID: admin_security_001
Revises: e100f24d8f70
Create Date: 2024-06-22 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers
revision = 'admin_security_001'
down_revision = 'e100f24d8f70'
branch_labels = None
depends_on = None

def upgrade() -> None:
    # Check if adminrole enum exists, create only if it doesn't
    connection = op.get_bind()
    result = connection.execute(
        sa.text("SELECT 1 FROM pg_type WHERE typname = 'adminrole'")
    ).fetchone()
    
    if not result:
        # Create admin_role enum only if it doesn't exist
        admin_role_enum = postgresql.ENUM('admin', 'super_admin', 'moderator', name='adminrole')
        admin_role_enum.create(op.get_bind())
    
    # Add new admin role enum value to existing userrole enum if it doesn't exist
    connection.execute(sa.text("ALTER TYPE userrole ADD VALUE IF NOT EXISTS 'super_admin'"))
    
    # Add admin-specific columns to users table (only if they don't exist)
    connection = op.get_bind()
    
    # Check and add password_hash column
    result = connection.execute(
        sa.text("SELECT 1 FROM information_schema.columns WHERE table_name='users' AND column_name='password_hash'")
    ).fetchone()
    if not result:
        op.add_column('users', sa.Column('password_hash', sa.String(), nullable=True))
    
    # Check and add failed_login_attempts column
    result = connection.execute(
        sa.text("SELECT 1 FROM information_schema.columns WHERE table_name='users' AND column_name='failed_login_attempts'")
    ).fetchone()
    if not result:
        op.add_column('users', sa.Column('failed_login_attempts', sa.Integer(), nullable=True, default=0))
    
    # Check and add locked_until column
    result = connection.execute(
        sa.text("SELECT 1 FROM information_schema.columns WHERE table_name='users' AND column_name='locked_until'")
    ).fetchone()
    if not result:
        op.add_column('users', sa.Column('locked_until', sa.DateTime(), nullable=True))
    
    # Check and add last_admin_login column
    result = connection.execute(
        sa.text("SELECT 1 FROM information_schema.columns WHERE table_name='users' AND column_name='last_admin_login'")
    ).fetchone()
    if not result:
        op.add_column('users', sa.Column('last_admin_login', sa.DateTime(), nullable=True))
    
    # Check and add password_changed_at column
    result = connection.execute(
        sa.text("SELECT 1 FROM information_schema.columns WHERE table_name='users' AND column_name='password_changed_at'")
    ).fetchone()
    if not result:
        op.add_column('users', sa.Column('password_changed_at', sa.DateTime(), nullable=True))
    
    # Create admin_invitations table (only if it doesn't exist)
    result = connection.execute(
        sa.text("SELECT 1 FROM information_schema.tables WHERE table_name = 'admin_invitations'")
    ).fetchone()
    if not result:
        op.create_table('admin_invitations',
            sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column('email', sa.String(), nullable=False),
            sa.Column('invited_by', postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column('token', sa.String(length=255), nullable=False),
            sa.Column('expires_at', sa.DateTime(), nullable=False),
            sa.Column('used_at', sa.DateTime(), nullable=True),
            sa.Column('is_used', sa.Boolean(), nullable=True, default=False),
            sa.Column('role', postgresql.ENUM('admin', 'super_admin', 'moderator', name='adminrole'), nullable=True, default='admin'),
            sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
            sa.ForeignKeyConstraint(['invited_by'], ['users.id'], ),
            sa.PrimaryKeyConstraint('id')
        )
        op.create_index(op.f('ix_admin_invitations_email'), 'admin_invitations', ['email'], unique=False)
        op.create_index(op.f('ix_admin_invitations_token'), 'admin_invitations', ['token'], unique=True)
    
    # Create admin_mfa_tokens table (only if it doesn't exist)
    result = connection.execute(
        sa.text("SELECT 1 FROM information_schema.tables WHERE table_name = 'admin_mfa_tokens'")
    ).fetchone()
    if not result:
        op.create_table('admin_mfa_tokens',
            sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column('admin_id', postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column('code', sa.String(length=6), nullable=False),
            sa.Column('expires_at', sa.DateTime(), nullable=False),
            sa.Column('is_used', sa.Boolean(), nullable=True, default=False),
            sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
            sa.ForeignKeyConstraint(['admin_id'], ['users.id'], ),
            sa.PrimaryKeyConstraint('id')
        )
    
    # Create admin_audit_logs table (only if it doesn't exist)
    result = connection.execute(
        sa.text("SELECT 1 FROM information_schema.tables WHERE table_name = 'admin_audit_logs'")
    ).fetchone()
    if not result:
        op.create_table('admin_audit_logs',
            sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column('admin_id', postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column('action', sa.String(length=100), nullable=False),
            sa.Column('resource_type', sa.String(length=50), nullable=True),
            sa.Column('resource_id', postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column('details', sa.JSON(), nullable=True),
            sa.Column('ip_address', sa.String(length=45), nullable=True),
            sa.Column('user_agent', sa.String(length=500), nullable=True),
            sa.Column('success', sa.Boolean(), nullable=True, default=True),
            sa.Column('error_message', sa.Text(), nullable=True),
            sa.Column('timestamp', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
            sa.ForeignKeyConstraint(['admin_id'], ['users.id'], ),
            sa.PrimaryKeyConstraint('id')
        )
    
    # Create admin_password_history table (only if it doesn't exist)
    result = connection.execute(
        sa.text("SELECT 1 FROM information_schema.tables WHERE table_name = 'admin_password_history'")
    ).fetchone()
    if not result:
        op.create_table('admin_password_history',
            sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column('admin_id', postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column('password_hash', sa.String(), nullable=False),
            sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
            sa.ForeignKeyConstraint(['admin_id'], ['users.id'], ),
            sa.PrimaryKeyConstraint('id')
        )
    
    # Create indexes for performance (only if they don't exist)
    try:
        op.create_index('ix_admin_audit_logs_admin_id', 'admin_audit_logs', ['admin_id'])
    except:
        pass  # Index already exists
    
    try:
        op.create_index('ix_admin_audit_logs_timestamp', 'admin_audit_logs', ['timestamp'])
    except:
        pass  # Index already exists
    
    try:
        op.create_index('ix_admin_audit_logs_action', 'admin_audit_logs', ['action'])
    except:
        pass  # Index already exists
    
    try:
        op.create_index('ix_admin_password_history_admin_id', 'admin_password_history', ['admin_id'])
    except:
        pass  # Index already exists

def downgrade() -> None:
    # Drop indexes
    try:
        op.drop_index('ix_admin_password_history_admin_id', table_name='admin_password_history')
        op.drop_index('ix_admin_audit_logs_action', table_name='admin_audit_logs')
        op.drop_index('ix_admin_audit_logs_timestamp', table_name='admin_audit_logs')
        op.drop_index('ix_admin_audit_logs_admin_id', table_name='admin_audit_logs')
    except:
        pass
    
    # Drop tables
    op.drop_table('admin_password_history')
    op.drop_table('admin_audit_logs')
    op.drop_table('admin_mfa_tokens')
    
    try:
        op.drop_index(op.f('ix_admin_invitations_token'), table_name='admin_invitations')
        op.drop_index(op.f('ix_admin_invitations_email'), table_name='admin_invitations')
        op.drop_table('admin_invitations')
    except:
        pass
    
    # Drop admin_role enum
    try:
        admin_role_enum = postgresql.ENUM(name='adminrole')
        admin_role_enum.drop(op.get_bind())
    except:
        pass
    
    # Remove admin columns from users table
    try:
        op.drop_column('users', 'password_changed_at')
        op.drop_column('users', 'last_admin_login')
        op.drop_column('users', 'locked_until')
        op.drop_column('users', 'failed_login_attempts')
        op.drop_column('users', 'password_hash')
    except:
        pass