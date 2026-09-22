"""Explicit migrations using the same UTC and timeout policy as the application."""

from alembic import context

from app.config import Settings
from app.db import Database
from app.models import Base

config = context.config


def run_migrations() -> None:
    settings = config.attributes.get("settings") or Settings()
    if context.is_offline_mode():
        context.configure(
            dialect_name="mysql",
            target_metadata=Base.metadata,
            literal_binds=True,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()
        return
    database = Database(settings)
    try:
        with database.engine.connect() as connection:
            version = str(connection.exec_driver_sql("SELECT VERSION()").scalar_one())
            if not version.startswith("8.") or "mariadb" in version.lower():
                raise RuntimeError("Migrations require MySQL 8.x.")
            connection.commit()
            context.configure(
                connection=connection, target_metadata=Base.metadata, compare_type=True
            )
            with context.begin_transaction():
                context.run_migrations()
    finally:
        database.dispose()


run_migrations()
