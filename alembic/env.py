import asyncio
import sys
import os
from logging.config import fileConfig
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context

# Add the project root to Python path
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

# Try to import models with better error handling
target_metadata = None

try:
    # Try different import patterns based on your project structure
    try:
        from app.database import Base
        from app.models import user, car, trip, booking
    except ImportError:
        try:
            from database import Base
            from models import user, car, trip, booking
        except ImportError:
            try:
                # Direct import from current directory
                import database
                import models.user
                import models.car
                import models.trip
                import models.booking
                Base = database.Base
            except ImportError:
                print("Warning: Could not import models. Alembic will work but won't auto-detect schema changes.")
                print("You can create migrations manually or fix the import paths.")
                Base = None
    
    if Base is not None:
        target_metadata = Base.metadata
        print("✅ Successfully imported database models")
    
except Exception as e:
    print(f"Warning: Could not import models: {e}")
    print("Alembic will work but won't detect model changes automatically")
    target_metadata = None

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    """Run migrations with database connection."""
    context.configure(
        connection=connection, 
        target_metadata=target_metadata,
        compare_type=True,
        compare_server_default=True,
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """In this scenario we need to create an Engine
    and associate a connection with the context.
    """
    
    # Create async engine configuration
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
