# File: cli_admin.py (NEW FILE - CLI commands for admin management)

import asyncio
import getpass
from typing import Optional

import typer
from sqlalchemy.ext.asyncio import AsyncSession

from database import async_session
from crud.admin_auth_crud import create_bootstrap_admin, get_admin_count, validate_password_strength
from schemas import BootstrapAdminRequest

app = typer.Typer(name="admin", help="Admin management commands")

async def create_first_admin_interactive():
    """Interactive admin creation"""
    print("🔐 Creating Bootstrap Admin Account")
    print("=" * 40)
    
    # Get admin details
    email = typer.prompt("Admin email")
    full_name = typer.prompt("Full name")
    
    # Get password securely
    password = getpass.getpass("Password (min 12 chars, uppercase, lowercase, number, special): ")
    confirm_password = getpass.getpass("Confirm password: ")
    
    if password != confirm_password:
        typer.echo("❌ Passwords do not match!", err=True)
        raise typer.Exit(1)
    
    try:
        # Validate password strength
        validate_password_strength(password, {"email": email, "name": full_name})
    except Exception as e:
        typer.echo(f"❌ Password validation failed: {str(e)}", err=True)
        raise typer.Exit(1)
    
    return BootstrapAdminRequest(
        email=email,
        full_name=full_name,
        password=password,
        confirm_password=confirm_password
    )

@app.command("create-first")
def create_first_admin(
    email: Optional[str] = typer.Option(None, help="Admin email"),
    name: Optional[str] = typer.Option(None, help="Admin full name"),
    password: Optional[str] = typer.Option(None, help="Admin password"),
):
    """Create the first admin account"""
    
    async def run_create_admin():
        async with async_session() as session:
            try:
                # Check if admin already exists
                admin_count = await get_admin_count(session)
                if admin_count > 0:
                    typer.echo("❌ Admin already exists! Use the invite system to create additional admins.", err=True)
                    raise typer.Exit(1)
                
                # Get admin data
                if not all([email, name, password]):
                    bootstrap_data = await create_first_admin_interactive()
                else:
                    bootstrap_data = BootstrapAdminRequest(
                        email=email,
                        full_name=name,
                        password=password,
                        confirm_password=password
                    )
                
                # Create admin
                admin = await create_bootstrap_admin(session, bootstrap_data)
                await session.commit()
                
                typer.echo("✅ Bootstrap admin created successfully!")
                typer.echo(f"📧 Email: {admin.email}")
                typer.echo(f"👤 Name: {admin.full_name}")
                typer.echo(f"🔑 Role: {admin.role.value}")
                typer.echo(f"🆔 ID: {admin.id}")
                typer.echo("\n🚀 You can now log in to the admin console!")
                
            except Exception as e:
                await session.rollback()
                typer.echo(f"❌ Error creating admin: {str(e)}", err=True)
                raise typer.Exit(1)
    
    asyncio.run(run_create_admin())

@app.command("check")
def check_admin_status():
    """Check admin account status"""
    
    async def run_check():
        async with async_session() as session:
            try:
                admin_count = await get_admin_count(session)
                
                if admin_count == 0:
                    typer.echo("❌ No admin accounts found!")
                    typer.echo("💡 Run 'python cli_admin.py create-first' to create the first admin")
                else:
                    typer.echo(f"✅ Found {admin_count} admin account(s)")
                    
                    if admin_count == 1:
                        typer.echo("💡 This is your bootstrap admin. You can invite more admins via the API.")
                
            except Exception as e:
                typer.echo(f"❌ Error checking admin status: {str(e)}", err=True)
                raise typer.Exit(1)
    
    asyncio.run(run_check())

@app.command("list-endpoints")
def list_admin_endpoints():
    """List all admin API endpoints"""
    
    endpoints = [
        ("POST", "/api/v1/auth/admin/bootstrap", "Create first admin (disable after use)"),
        ("POST", "/api/v1/auth/admin/login", "Admin login with email/password"),
        ("POST", "/api/v1/auth/admin/verify-mfa", "Verify MFA code"),
        ("POST", "/api/v1/auth/admin/invite", "Invite new admin (super admin only)"),
        ("POST", "/api/v1/auth/admin/accept-invite", "Accept admin invitation"),
        ("GET", "/api/v1/auth/admin/me", "Get current admin profile"),
        ("GET", "/api/v1/admin/verifications/drivers/pending", "List pending driver verifications"),
        ("GET", "/api/v1/admin/verifications/cars/pending", "List pending car verifications"),
        ("POST", "/api/v1/admin/verifications/drivers/{driver_id}/approve", "Approve driver"),
        ("POST", "/api/v1/admin/verifications/drivers/{driver_id}/reject", "Reject driver"),
        ("POST", "/api/v1/admin/verifications/cars/{car_id}/approve", "Approve car"),
        ("POST", "/api/v1/admin/verifications/cars/{car_id}/reject", "Reject car"),
    ]
    
    typer.echo("🔗 Admin API Endpoints")
    typer.echo("=" * 50)
    
    for method, endpoint, description in endpoints:
        typer.echo(f"{method:6} {endpoint:45} - {description}")
    
    typer.echo("\n📖 Documentation: https://your-api-url/docs")

if __name__ == "__main__":
    app()

# Usage examples:
# python cli_admin.py create-first
# python cli_admin.py create-first --email admin@autoport.uz --name "Admin User" --password SecurePass123!
# python cli_admin.py check
# python cli_admin.py list-endpoints