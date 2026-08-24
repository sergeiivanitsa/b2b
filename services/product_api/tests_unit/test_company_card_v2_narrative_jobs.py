from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import UTC, datetime
from uuid import UUID

import pytest

from product_api.company_reports.persistence.narratives import (
    NarrativeJobLease,
    narrative_budget_windows,
)


def test_moscow_daily_and_monthly_windows_use_exact_utc_boundaries() -> None:
    daily, monthly = narrative_budget_windows(datetime(2026, 8, 31, 20, 59, 59, tzinfo=UTC))
    assert daily == (
        "2026-08-31",
        datetime(2026, 8, 30, 21, tzinfo=UTC),
        datetime(2026, 8, 31, 21, tzinfo=UTC),
    )
    assert monthly == (
        "2026-08-01",
        datetime(2026, 7, 31, 21, tzinfo=UTC),
        datetime(2026, 8, 31, 21, tzinfo=UTC),
    )


def test_moscow_day_and_month_roll_over_together_at_utc_21() -> None:
    daily, monthly = narrative_budget_windows(datetime(2026, 8, 31, 21, tzinfo=UTC))
    assert daily == (
        "2026-09-01",
        datetime(2026, 8, 31, 21, tzinfo=UTC),
        datetime(2026, 9, 1, 21, tzinfo=UTC),
    )
    assert monthly == (
        "2026-09-01",
        datetime(2026, 8, 31, 21, tzinfo=UTC),
        datetime(2026, 9, 30, 21, tzinfo=UTC),
    )


def test_budget_window_clock_must_be_timezone_aware() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        narrative_budget_windows(datetime(2026, 8, 24, 12))


def test_job_lease_is_an_exact_frozen_fence_tuple() -> None:
    lease = NarrativeJobLease(
        job_id=UUID("00000000-0000-4000-8000-000000000001"),
        report_id=UUID("00000000-0000-4000-8000-000000000002"),
        snapshot_hash="a" * 64,
        generation_key="b" * 64,
        lease_token=UUID("00000000-0000-4000-8000-000000000003"),
        fence_generation=7,
        lease_expires_at=datetime(2026, 8, 24, 12, 1, tzinfo=UTC),
    )
    assert tuple(lease.__dict__) == (
        "job_id",
        "report_id",
        "snapshot_hash",
        "generation_key",
        "lease_token",
        "fence_generation",
        "lease_expires_at",
    )
    with pytest.raises(FrozenInstanceError):
        lease.fence_generation = 8  # type: ignore[misc]
