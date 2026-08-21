"""Fail-closed guards shared by public-H1 read-path acceptance tests."""
from __future__ import annotations

import inspect
from collections import Counter
from typing import Any

from sqlalchemy.sql import Select


class SelectOnlySession:
    """Delegate SELECTs while making every ORM/business write observable."""

    def __init__(self, session: Any) -> None:
        self._session = session
        self.select_count = 0
        self.prohibited = Counter[str]()

    async def execute(self, statement: Any, *args: Any, **kwargs: Any) -> Any:
        if not isinstance(statement, Select):
            self.prohibited["sql_non_select"] += 1
            raise AssertionError(
                f"public H1 read path attempted {type(statement).__name__}"
            )
        self.select_count += 1
        return await self._session.execute(statement, *args, **kwargs)

    async def scalar(self, statement: Any, *args: Any, **kwargs: Any) -> Any:
        if not isinstance(statement, Select):
            self.prohibited["sql_non_select"] += 1
            raise AssertionError(
                f"public H1 read path attempted {type(statement).__name__}"
            )
        self.select_count += 1
        return await self._session.scalar(statement, *args, **kwargs)

    def add(self, *_args: Any, **_kwargs: Any) -> None:
        self._reject("orm_add")

    def add_all(self, *_args: Any, **_kwargs: Any) -> None:
        self._reject("orm_add_all")

    async def delete(self, *_args: Any, **_kwargs: Any) -> None:
        self._reject("orm_delete")

    async def merge(self, *_args: Any, **_kwargs: Any) -> None:
        self._reject("orm_merge")

    async def flush(self, *_args: Any, **_kwargs: Any) -> None:
        self._reject("orm_flush")

    async def commit(self, *_args: Any, **_kwargs: Any) -> None:
        self._reject("orm_commit")

    def _reject(self, name: str) -> None:
        self.prohibited[name] += 1
        raise AssertionError(f"public H1 read path attempted {name}")


def install_capability_guards(monkeypatch: Any) -> Counter[str]:
    """Guard definitions and loaded call-site aliases for every write family."""
    from product_api import gateway_client
    from product_api.company_reports import ephemeral_evaluation, seo, service, worker
    from product_api.company_reports import persistence as persistence_package
    from product_api.company_reports import scoring as scoring_package
    from product_api.company_reports import signals as signals_package
    from product_api.company_reports import explanation as explanation_package
    from product_api.company_reports.explanation import service as explanation_service
    from product_api.company_reports.persistence import jobs, publications
    from product_api.company_reports.scoring import evaluation as scoring_evaluation
    from product_api.company_reports.signals import evaluation as signals_evaluation
    from product_api.company_reports import seo_publish
    from product_api.providers.datanewton import DataNewtonClient

    counters = Counter[str]()
    targets: list[tuple[str, Any, str]] = [
        ("publication_policy", seo, "evaluate_publication"),
        ("publication_policy_alias", publications, "evaluate_publication"),
        ("ephemeral_evaluation", ephemeral_evaluation, "evaluate_report_ephemerally"),
        ("ephemeral_evaluation_seo_alias", seo, "evaluate_report_ephemerally"),
        ("ephemeral_evaluation_jobs_alias", jobs, "evaluate_report_ephemerally"),
        ("signals", signals_evaluation, "evaluate_signals"),
        ("signals_package_alias", signals_package, "evaluate_signals"),
        ("signals_ephemeral_alias", ephemeral_evaluation, "evaluate_signals"),
        ("signals_service_alias", service, "evaluate_signals"),
        ("signals_worker_alias", worker, "evaluate_signals"),
        ("scoring", scoring_evaluation, "score_signals"),
        ("scoring_package_alias", scoring_package, "score_signals"),
        ("scoring_ephemeral_alias", ephemeral_evaluation, "score_signals"),
        ("scoring_service_alias", service, "score_signals"),
        ("scoring_worker_alias", worker, "score_signals"),
        ("ai_explanation", explanation_service, "explain_scoring_result"),
        ("ai_explanation_package_alias", explanation_package, "explain_scoring_result"),
        ("ai_explanation_service_alias", service, "explain_scoring_result"),
        ("gateway_chat", gateway_client, "send_chat"),
        ("gateway_chat_explanation_alias", explanation_service, "send_chat"),
        ("gateway_stream_chat", gateway_client, "stream_chat"),
    ]

    job_names = (
        "enqueue_company_report_job",
        "claim_next_job",
        "heartbeat_job",
        "complete_claimed_job",
        "fail_owned_job",
        "reconcile_expired_jobs",
    )
    for name in job_names:
        targets.append((f"job_{name}", jobs, name))
        if hasattr(persistence_package, name):
            targets.append((f"job_{name}_package_alias", persistence_package, name))
        if hasattr(service, name):
            targets.append((f"job_{name}_service_alias", service, name))
        if hasattr(worker, name):
            targets.append((f"job_{name}_worker_alias", worker, name))

    for name in ("run_one_claimed_job", "heartbeat_supervisor", "run_worker"):
        targets.append((f"worker_{name}", worker, name))

    publication_names = (
        "set_publication_control",
        "create_batch",
        "set_batch_state",
        "claim_next_batch_item",
        "relinquish_batch_claim",
        "finalize_batch_claim",
        "process_batch",
    )
    for name in publication_names:
        targets.append((f"publication_{name}", publications, name))
        if hasattr(seo_publish, name):
            targets.append((f"publication_{name}_cli_alias", seo_publish, name))

    for module_name, module, attribute in targets:
        _install_guard(monkeypatch, counters, module_name, module, attribute)

    for name, value in vars(DataNewtonClient).items():
        if name.startswith("fetch_") and callable(value):
            _install_guard(
                monkeypatch,
                counters,
                f"datanewton_{name}",
                DataNewtonClient,
                name,
            )
    return counters


def _install_guard(
    monkeypatch: Any,
    counters: Counter[str],
    label: str,
    owner: Any,
    attribute: str,
) -> None:
    original = getattr(owner, attribute)
    if inspect.iscoroutinefunction(original):
        async def forbidden(*_args: Any, **_kwargs: Any) -> None:
            counters[label] += 1
            raise AssertionError(f"prohibited capability called: {label}")
    else:
        def forbidden(*_args: Any, **_kwargs: Any) -> None:
            counters[label] += 1
            raise AssertionError(f"prohibited capability called: {label}")
    monkeypatch.setattr(owner, attribute, forbidden)


def assert_zero_side_effects(
    session: SelectOnlySession,
    counters: Counter[str],
    *,
    expected_selects: int,
) -> None:
    assert session.select_count == expected_selects
    assert not session.prohibited
    assert not counters


__all__ = [
    "SelectOnlySession",
    "assert_zero_side_effects",
    "install_capability_guards",
]
