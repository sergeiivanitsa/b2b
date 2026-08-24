from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from product_api.company_reports.persistence.models import CompanyCardNarrativeOutbox
from product_api.company_reports.persistence.narrative_outbox import (
    NarrativeOutboxOwnershipError,
    claim_narrative_outbox,
    heartbeat_narrative_outbox,
    outbox_lease,
)


NOW = datetime(2026, 8, 24, 12, tzinfo=UTC)


def _row(**overrides: object) -> CompanyCardNarrativeOutbox:
    values: dict[str, object] = {
        "id": uuid4(),
        "report_id": uuid4(),
        "snapshot_hash": "a" * 64,
        "event_kind": "initialize_narrative_v1",
        "state": "leased",
        "available_at": NOW,
        "attempt_count": 1,
        "lease_token": uuid4(),
        "lease_expires_at": NOW + timedelta(minutes=1),
        "fence_generation": 3,
    }
    values.update(overrides)
    return CompanyCardNarrativeOutbox(**values)


def test_outbox_lease_copies_the_exact_immutable_ownership_tuple() -> None:
    row = _row()
    lease = outbox_lease(row)

    assert lease.outbox_id == row.id
    assert lease.report_id == row.report_id
    assert lease.snapshot_hash == row.snapshot_hash
    assert lease.lease_token == row.lease_token
    assert lease.fence_generation == row.fence_generation
    assert lease.lease_expires_at == row.lease_expires_at
    with pytest.raises(FrozenInstanceError):
        lease.fence_generation = 4  # type: ignore[misc]


@pytest.mark.parametrize(
    "overrides",
    [
        {"state": "pending"},
        {"lease_token": None},
        {"lease_expires_at": None},
    ],
)
def test_outbox_lease_rejects_incomplete_or_unleased_rows(overrides: dict[str, object]) -> None:
    with pytest.raises(NarrativeOutboxOwnershipError, match="not leased"):
        outbox_lease(_row(**overrides))


class _NoDatabase:
    def __getattr__(self, name: str):
        raise AssertionError(f"database must not be reached: {name}")


@pytest.mark.asyncio
async def test_outbox_claim_rejects_invalid_clock_and_lease_before_database_access() -> None:
    with pytest.raises(ValueError, match="positive"):
        await claim_narrative_outbox(_NoDatabase(), now=NOW, lease_seconds=0)
    with pytest.raises(ValueError, match="timezone-aware"):
        await claim_narrative_outbox(_NoDatabase(), now=NOW.replace(tzinfo=None))


@pytest.mark.asyncio
async def test_outbox_heartbeat_rejects_invalid_lease_before_database_access() -> None:
    with pytest.raises(ValueError, match="positive"):
        await heartbeat_narrative_outbox(
            _NoDatabase(),
            lease=outbox_lease(_row()),
            now=NOW,
            lease_seconds=0,
        )
