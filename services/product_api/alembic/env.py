from __future__ import annotations

import asyncio
import os
import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from alembic.script import ScriptDirectory
from sqlalchemy import (
    Column,
    MetaData,
    PrimaryKeyConstraint,
    String,
    Table,
    inspect,
    pool,
)
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

BASE_DIR = Path(__file__).resolve().parents[1]
SOURCE_ROOT = BASE_DIR / "src"
if SOURCE_ROOT.is_dir():
    sys.path.append(str(SOURCE_ROOT))

SHARED_ROOT = next(
    (
        candidate
        for candidate in (BASE_DIR, *BASE_DIR.parents)
        if (candidate / "shared" / "__init__.py").is_file()
    ),
    None,
)
if SHARED_ROOT is None:
    raise RuntimeError("unable to locate shared package root")
sys.path.append(str(SHARED_ROOT))

from product_api.db.base import Base  # noqa: E402
from product_api import models  # noqa: F401,E402
from product_api.company_reports.persistence import models as company_report_models  # noqa: F401,E402

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

_VERSION_TABLE_NAME = "alembic_version"
_VERSION_NUM_COLUMN_NAME = "version_num"
_MIN_VERSION_NUM_LENGTH = 64
_VERSION_NUM_LENGTH_MARGIN = 16
_VERSION_NUM_LENGTH_GRANULARITY = 16


def _get_url() -> str:
    return os.getenv("DATABASE_URL", config.get_main_option("sqlalchemy.url"))


def _required_version_num_length() -> int:
    script_directory = ScriptDirectory.from_config(config)
    longest_revision = max(
        (
            len(revision.revision)
            for revision in script_directory.walk_revisions()
        ),
        default=0,
    )
    padded_length = longest_revision + _VERSION_NUM_LENGTH_MARGIN
    rounded_length = (
        (
            padded_length
            + _VERSION_NUM_LENGTH_GRANULARITY
            - 1
        )
        // _VERSION_NUM_LENGTH_GRANULARITY
        * _VERSION_NUM_LENGTH_GRANULARITY
    )
    return max(_MIN_VERSION_NUM_LENGTH, rounded_length)


def _bootstrap_version_table(connection: Connection) -> None:
    if connection.dialect.name != "postgresql":
        raise RuntimeError(
            "Alembic online migrations require a PostgreSQL connection"
        )

    required_length = _required_version_num_length()
    version_table = Table(
        _VERSION_TABLE_NAME,
        MetaData(),
        Column(
            _VERSION_NUM_COLUMN_NAME,
            String(required_length),
            nullable=False,
        ),
        PrimaryKeyConstraint(
            _VERSION_NUM_COLUMN_NAME,
            name=f"{_VERSION_TABLE_NAME}_pkc",
        ),
    )
    version_table.create(connection, checkfirst=True)

    columns = {
        column["name"]: column
        for column in inspect(connection).get_columns(_VERSION_TABLE_NAME)
    }
    version_column = columns.get(_VERSION_NUM_COLUMN_NAME)
    if version_column is None:
        raise RuntimeError(
            "alembic_version exists without a version_num column"
        )

    column_type = version_column["type"]
    if not isinstance(column_type, String):
        raise RuntimeError(
            "alembic_version.version_num must use a string type"
        )

    current_length = column_type.length
    if current_length is None or current_length >= required_length:
        return

    connection.exec_driver_sql(
        "ALTER TABLE alembic_version "
        "ALTER COLUMN version_num "
        f"TYPE VARCHAR({required_length})"
    )


def run_migrations_offline() -> None:
    url = _get_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    with connection.begin():
        _bootstrap_version_table(connection)

    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        version_table=_VERSION_TABLE_NAME,
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    config.set_main_option("sqlalchemy.url", _get_url())
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
