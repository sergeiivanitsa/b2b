"""Real PostgreSQL acceptance for the production worker-drain aggregate SQL."""
from __future__ import annotations

import asyncio
import importlib.util
import json
import os
from pathlib import Path
import shutil
import sys

import pytest
from sqlalchemy import text


ROOT = Path(__file__).resolve().parents[3]
MODULE = ROOT / "deploy/product_api/worker_drain.py"
SPEC = importlib.util.spec_from_file_location("worker_drain_postgres_acceptance", MODULE)
assert SPEC and SPEC.loader
drain = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = drain
SPEC.loader.exec_module(drain)


@pytest.mark.asyncio
async def test_exact_worker_drain_aggregate_sql_and_psql_adapter_on_migrated_postgres(
    engine,
    db_url: str,
) -> None:
    """The shipped SQL must execute on head, and CI must exercise real psql."""
    async with engine.connect() as connection:
        revision = await connection.scalar(text("SELECT version_num FROM alembic_version"))
        raw = await connection.scalar(text(drain._AGGREGATE_SQL))

    assert revision == "0019_company_card_v2_rollout_control"
    assert isinstance(raw, str)
    direct_snapshot = drain.AggregateSnapshot(**json.loads(raw))
    assert direct_snapshot.safe
    assert all(value == 0 for value in direct_snapshot.stable_key())

    # The Windows developer runner intentionally owns PostgreSQL inside Docker
    # and does not install a host libpq client.  GitHub's PostgreSQL acceptance
    # is the authoritative adapter check and must fail, never skip, if psql is
    # absent there.  The direct exact-SQL assertion above still runs locally.
    if shutil.which("psql") is None:
        if os.environ.get("CI", "").lower() in {"1", "true"}:
            pytest.fail("CI PostgreSQL acceptance requires the real psql client")
        return

    adapter_snapshot = await asyncio.to_thread(
        drain.PsqlAggregateAdapter(db_url).snapshot
    )
    assert adapter_snapshot.safe
    assert adapter_snapshot.stable_key() == direct_snapshot.stable_key()
    assert adapter_snapshot.db_clock
