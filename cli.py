# File: cli.py
import asyncio
import logging
from typing import Optional
import sys # For sys.exit

import typer
from sqlalchemy.exc import SQLAlchemyError

# Assuming these imports are correct based on your project structure
from crud import auth_crud
from database import async_session as async_session_factory # Using your alias
from models import User, UserRole, UserStatus

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Define the Typer app - this will now mostly be for parsing and help text
cli_app_def = typer.Typer(name="cli_runner", add_completion=False, help="Ride Sharing API CLI for administrative tasks.")

# This is your core async logic
async def _create_admin_logic(phone_number: str, full_name: str):
    logger.info(f"Attempting to create or update admin user: {phone_number}, {full_name}")

    if not async_session_factory:
        logger.error("async_session_factory (async_session) is not configured in database.py. Cannot proceed.")
        typer.secho("Error: Database session factory not configured.", fg=typer.colors.RED)
        raise typer.Exit(code=1)

    async with async_session_factory() as session:
        try:
            async with session.begin():
                existing_user = await auth_crud.get_user_by_phone(session=session, phone_number=phone_number)
                action_taken = ""
                user_to_report = None

                if existing_user:
                    logger.info(f"User with phone number {phone_number} already exists. Updating to admin.")
                    if existing_user.role == UserRole.ADMIN and existing_user.status == UserStatus.ACTIVE:
                        msg = f"User {existing_user.phone_number} ({existing_user.full_name}) is already an active admin."
                        logger.info(msg)
                        typer.echo(msg)
                        # For a CLI, exiting here might be okay, or just print and continue if no error.
                        # Let's allow it to "succeed" by just reporting.
                        return # Exit the async logic function

                    existing_user.full_name = full_name
                    existing_user.role = UserRole.ADMIN
                    existing_user.status = UserStatus.ACTIVE
                    session.add(existing_user)
                    await session.flush()
                    await session.refresh(existing_user)
                    user_to_report = existing_user
                    action_taken = "updated to admin"
                else:
                    logger.info(f"Creating new admin user: {phone_number}, {full_name}")
                    new_admin = User(
                        phone_number=phone_number,
                        full_name=full_name,
                        role=UserRole.ADMIN,
                        status=UserStatus.ACTIVE,
                    )
                    session.add(new_admin)
                    await session.flush()
                    await session.refresh(new_admin)
                    user_to_report = new_admin
                    action_taken = "created"
            
            # If session.begin() committed successfully:
            if user_to_report:
                success_message = (
                    f"Admin user {user_to_report.phone_number} ({user_to_report.full_name}) "
                    f"successfully {action_taken}. "
                    f"ID: {user_to_report.id}, Role: {user_to_report.role.value}, Status: {user_to_report.status.value}"
                )
                logger.info(success_message)
                typer.secho(success_message, fg=typer.colors.GREEN)
            # If we returned early due to already being an admin, this part is skipped.

        except SQLAlchemyError as e:
            logger.error(f"Database error occurred: {e}", exc_info=True)
            typer.secho(f"A database error occurred: {e}", fg=typer.colors.RED)
            # No typer.Exit here, let the main block handle exit
            raise # Re-raise to be caught by the outer try-except
        except Exception as e:
            logger.error(f"An unexpected error occurred: {e}", exc_info=True)
            typer.secho(f"An unexpected error occurred: {e}", fg=typer.colors.RED)
            raise # Re-raise to be caught by the outer try-except

# Define the command using the Typer app instance
@cli_app_def.command(name="create-admin") # Explicitly name the command
def create_admin_command(
    phone_number: str = typer.Option(..., "--phone-number", "-p", help="Admin's phone number (e.g., '+998901234567')"),
    full_name: str = typer.Option(..., "--full-name", "-n", help="Admin's full name")
):
    """
    Creates or updates an Admin user. (This is the help text for the command)
    """
    try:
        asyncio.run(_create_admin_logic(phone_number=phone_number, full_name=full_name))
        # If _create_admin_logic returned early, we don't raise Exit here unless an exception was re-raised.
    except Exception:
        # _create_admin_logic already prints specific errors.
        # This ensures script exits with error code if an exception bubbled up.
        sys.exit(1)


# You can add other commands here, e.g.:
# @cli_app_def.command(name="another-task")
# def another_task_command():
#     print("Running another task...")

if __name__ == "__main__":
    cli_app_def() # Call the Typer app instance