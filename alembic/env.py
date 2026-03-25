from __future__ import annotations

import pkgutil
import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.core.database import Base, DATABASE_URL  # noqa: E402
import app.models as models_pkg  # noqa: E402


def _import_all_models() -> None:
    skip = {"__pycache__", "__init__", "base", "_generated_all"}
    for module_info in pkgutil.iter_modules(models_pkg.__path__):
        name = module_info.name
        if name in skip or name.startswith("_"):
            continue
        __import__(f"app.models.{name}")


def _sync_database_url() -> str:
    database_url = DATABASE_URL
    if not database_url:
        raise RuntimeError("DATABASE_URL is required for Alembic")
    return database_url.replace("+asyncpg", "")


config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

_import_all_models()
target_metadata = Base.metadata
config.set_main_option("sqlalchemy.url", _sync_database_url())


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        compare_type=True,
        compare_server_default=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
        future=True,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
