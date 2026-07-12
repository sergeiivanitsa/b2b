from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from product_api.providers.datanewton import DataNewtonResult


class CompanyReportProvider(Protocol):
    async def fetch_counterparty(
        self,
        identifier: str,
        *,
        filters: Sequence[str] | None = None,
        kpp: str | None = None,
        request_id: str | None = None,
    ) -> DataNewtonResult: ...

    async def fetch_finance(
        self,
        identifier: str,
        *,
        request_id: str | None = None,
    ) -> DataNewtonResult: ...

    async def fetch_arbitration_cases(
        self,
        identifier: str,
        *,
        offset: int = 0,
        limit: int = 100,
        company_role: str | None = None,
        status: int | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        updated_at_from: str | None = None,
        need_document: bool | None = None,
        request_id: str | None = None,
    ) -> DataNewtonResult: ...
