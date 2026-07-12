from __future__ import annotations

import asyncio
from collections.abc import Mapping
from copy import deepcopy
from typing import Any

from company_report_test_helpers import (
    arbitration_result,
    counterparty_result,
    finance_result,
)
from product_api.providers.datanewton import DataNewtonResult


class FakeCompanyReportProvider:
    def __init__(
        self,
        *,
        results: Mapping[str, DataNewtonResult] | None = None,
        errors: Mapping[str, Exception] | None = None,
        delay: float = 0,
    ) -> None:
        self.results = dict(results or {})
        self.errors = dict(errors or {})
        self.delay = delay
        self.calls: list[dict[str, Any]] = []

    async def _run(self, dataset: str, identifier: str, **params: Any) -> DataNewtonResult:
        self.calls.append(
            {"dataset": dataset, "identifier": identifier, **params}
        )
        if self.delay:
            await asyncio.sleep(self.delay)
        error = self.errors.get(dataset)
        if error is not None:
            raise error
        return self.results[dataset]

    async def fetch_counterparty(
        self,
        identifier: str,
        *,
        filters=None,
        kpp=None,
        request_id=None,
    ) -> DataNewtonResult:
        return await self._run(
            "counterparty",
            identifier,
            filters=filters,
            kpp=kpp,
            request_id=request_id,
        )

    async def fetch_finance(self, identifier: str, *, request_id=None) -> DataNewtonResult:
        return await self._run("finance", identifier, request_id=request_id)

    async def fetch_arbitration_cases(
        self,
        identifier: str,
        *,
        offset=0,
        limit=100,
        company_role=None,
        status=None,
        start_date=None,
        end_date=None,
        updated_at_from=None,
        need_document=None,
        request_id=None,
    ) -> DataNewtonResult:
        return await self._run(
            "arbitration",
            identifier,
            offset=offset,
            limit=limit,
            request_id=request_id,
        )


def successful_fake_provider(*, delay: float = 0) -> FakeCompanyReportProvider:
    return FakeCompanyReportProvider(
        results={
            "counterparty": counterparty_result(),
            "finance": finance_result(),
            "arbitration": arbitration_result(),
        },
        delay=delay,
    )
