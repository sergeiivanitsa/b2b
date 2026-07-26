"""Focused PostgreSQL schema checks for the Claims handoff migration."""

import pytest
from sqlalchemy import text


pytestmark = pytest.mark.asyncio


async def test_claim_handoff_columns_and_constraints_exist(engine):
    async with engine.connect() as connection:
        column_rows = await connection.execute(
            text(
                "SELECT column_name, is_nullable FROM information_schema.columns "
                "WHERE table_name = 'claims' AND column_name IN "
                "('source_company_report_id', 'handoff_idempotency_key_hash')"
            )
        )
        columns = dict(column_rows.all())
        assert columns == {
            "source_company_report_id": "YES",
            "handoff_idempotency_key_hash": "YES",
        }
        constraints = (
            await connection.execute(
                text(
                    "SELECT conname FROM pg_constraint WHERE conrelid = 'claims'::regclass"
                )
            )
        ).scalars().all()
        assert "uq_claims_handoff_idempotency_key_hash" in constraints
        delete_action = await connection.scalar(
            text(
                "SELECT confdeltype FROM pg_constraint "
                "WHERE conrelid = 'claims'::regclass "
                "AND confrelid = 'company_reports'::regclass "
                "AND contype = 'f'"
            )
        )
        assert delete_action in {"n", b"n"}
        index_exists = await connection.scalar(
            text(
                "SELECT to_regclass('ix_claims_source_company_report_id')"
            )
        )
        assert index_exists == "ix_claims_source_company_report_id"
