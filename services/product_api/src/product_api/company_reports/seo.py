"""Pure, allowlisted SEO projection and rendering for stored CompanyReports."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from html import escape
import re
from typing import Any, Iterable

from product_api.company_reports.aggregate import CompanyReport, CompanyReportStatus, DatasetReportStatus
from product_api.company_reports.company_urls import legacy_canonical_slug, legacy_h1_binding
from product_api.company_reports.ephemeral_evaluation import evaluate_report_ephemerally
from product_api.company_reports.scoring.models import ScoringLevel

POLICY_VERSION = "publication_sufficiency_v1"
# Stored snapshots intentionally retain some safe provenance fields.  The public
# projection never copies any of these; only raw credential-bearing shapes make
# the source snapshot itself ineligible.
_FORBIDDEN = frozenset({"raw_payload", "headers", "authorization", "api_key"})


class SeoPolicyError(ValueError):
    pass


@dataclass(frozen=True)
class PublicSection:
    name: str
    rows: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class PublicProjection:
    inn: str
    name: str
    status: str | None
    registration_date: str | None
    sections: tuple[PublicSection, ...]
    generated_at: datetime
    warnings: tuple[str, ...]


@dataclass(frozen=True)
class PolicyDecision:
    indexable: bool
    sufficiency_status: str
    projection: PublicProjection | None


def canonical_slug(name: str) -> str:
    try:
        return legacy_canonical_slug(name)
    except ValueError as exc:
        raise SeoPolicyError(str(exc)) from exc


def canonical_path(inn: str, name: str) -> str:
    try:
        return legacy_h1_binding(inn, name).canonical_path
    except ValueError as exc:
        raise SeoPolicyError(str(exc)) from exc


def _contains_forbidden(value: object) -> bool:
    if isinstance(value, dict):
        return any(key in _FORBIDDEN or _contains_forbidden(item) for key, item in value.items())
    if isinstance(value, list):
        return any(_contains_forbidden(item) for item in value)
    return False


def _format_decimal(value: Decimal) -> str:
    return format(value, "f")


def _identity(report: CompanyReport) -> tuple[str, str] | None:
    facts = report.counterparty
    if facts is None or facts.inn != report.target_identifier:
        return None
    name = facts.full_name or facts.short_name
    if not name or not name.strip():
        return None
    return facts.inn, name.strip()


def _finance_section(report: CompanyReport) -> PublicSection | None:
    finance = report.finance
    if finance is None:
        return None
    rows: list[tuple[str, str]] = []
    for period in sorted(finance.periods, key=lambda item: item.year, reverse=True):
        values = [(field, getattr(period, field)) for field in ("revenue", "net_profit", "total_assets")]
        actual = [(field, value) for field, value in values if value is not None]
        if actual:
            label, amount = actual[0]
            titles = {"revenue": "Выручка", "net_profit": "Чистая прибыль", "total_assets": "Активы"}
            rows.append((f"{titles[label]}, {period.year}", f"{_format_decimal(amount)} ({finance.unit})"))
    return PublicSection("Финансовые показатели", tuple(rows)) if rows else None


def _arbitration_section(report: CompanyReport) -> PublicSection | None:
    arbitration = report.arbitration
    if arbitration is None:
        return None
    rows: list[tuple[str, str]] = []
    if arbitration.total_cases is not None:
        rows.append(("Всего дел", str(arbitration.total_cases)))
    for currency, amounts in sorted(arbitration.claim_amounts_by_currency.items()):
        rows.append((f"Требования истца ({currency})", _format_decimal(amounts.plaintiff)))
        rows.append((f"Требования ответчика ({currency})", _format_decimal(amounts.respondent)))
    return PublicSection("Арбитражные сведения", tuple(rows)) if rows else None


def project_report(report: CompanyReport) -> PublicProjection:
    snapshot = report.model_dump(mode="json")
    if _contains_forbidden(snapshot):
        raise SeoPolicyError("snapshot includes forbidden private fields")
    identity = _identity(report)
    if identity is None:
        raise SeoPolicyError("report lacks public identity")
    inn, name = identity
    counterparty = report.counterparty
    sections = tuple(item for item in (_finance_section(report), _arbitration_section(report)) if item)
    warnings = tuple(sorted({warning.code for warning in report.warnings}))
    return PublicProjection(
        inn=inn,
        name=name,
        status=counterparty.status_text if counterparty else None,
        registration_date=counterparty.registration_date.isoformat() if counterparty and counterparty.registration_date else None,
        sections=sections,
        generated_at=report.generated_at.astimezone(timezone.utc),
        warnings=warnings,
    )


def evaluate_publication(report: CompanyReport) -> PolicyDecision:
    if report.status not in {CompanyReportStatus.COMPLETE, CompanyReportStatus.PARTIAL}:
        return PolicyDecision(False, "report_not_finalized", None)
    if not report.usable_for_public_page or not report.usable_for_future_scoring:
        return PolicyDecision(False, "report_not_usable", None)
    try:
        projection = project_report(report)
        _, scoring = evaluate_report_ephemerally(report)
    except (SeoPolicyError, ValueError):
        return PolicyDecision(False, "invalid_or_private_snapshot", None)
    if scoring.level is ScoringLevel.INSUFFICIENT_DATA:
        return PolicyDecision(False, "insufficient_scoring", projection)
    if not projection.sections:
        return PolicyDecision(False, "thin_content", projection)
    if report.status is CompanyReportStatus.PARTIAL:
        counterparty = report.datasets.get("counterparty")
        finance = report.datasets.get("finance")
        arbitration = report.datasets.get("arbitration")
        has_substantive_available = (
            finance is not None and finance.status is DatasetReportStatus.AVAILABLE and _finance_section(report) is not None
        ) or (
            arbitration is not None and arbitration.status is DatasetReportStatus.AVAILABLE and _arbitration_section(report) is not None
        )
        if counterparty is None or counterparty.status is not DatasetReportStatus.AVAILABLE or not has_substantive_available:
            return PolicyDecision(False, "partial_insufficient", projection)
    return PolicyDecision(True, "sufficient", projection)


def metadata(projection: PublicProjection) -> tuple[str, str]:
    sections = {"Финансовые показатели": "финансовые показатели", "Арбитражные сведения": "арбитражные сведения"}
    section_list = ", ".join(sections[section.name] for section in projection.sections)
    return (
        f"{projection.name} — сведения по ИНН {projection.inn} | Pork.su",
        f"Сведения о компании {projection.name}, ИНН {projection.inn}: {section_list}.",
    )


def render_html(projection: PublicProjection, *, base_url: str, robots: str) -> str:
    title, description = metadata(projection)
    canonical = f"{base_url.rstrip('/')}{canonical_path(projection.inn, projection.name)}"
    identity_rows = [("ИНН", projection.inn)]
    if projection.status:
        identity_rows.append(("Статус", projection.status))
    if projection.registration_date:
        identity_rows.append(("Дата регистрации", projection.registration_date))
    sections = (PublicSection("Реквизиты", tuple(identity_rows)), *projection.sections)
    body = "".join(
        "<section><h2>{}</h2><dl>{}</dl></section>".format(
            escape(section.name),
            "".join(f"<dt>{escape(label)}</dt><dd>{escape(value)}</dd>" for label, value in section.rows),
        ) for section in sections
    )
    return "<!doctype html><html lang=\"ru\"><head><meta charset=\"utf-8\"><title>{}</title><meta name=\"description\" content=\"{}\"><meta name=\"robots\" content=\"{}\"><link rel=\"canonical\" href=\"{}\"></head><body><main><h1>{}</h1>{}</main></body></html>".format(escape(title), escape(description, quote=True), escape(robots), escape(canonical, quote=True), escape(projection.name), body)


def render_sitemap(urls: Iterable[tuple[str, datetime]]) -> str:
    entries = "".join(f"<url><loc>{escape(loc)}</loc><lastmod>{lastmod.astimezone(timezone.utc).isoformat().replace('+00:00', 'Z')}</lastmod></url>" for loc, lastmod in urls)
    return f'<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{entries}</urlset>'


def render_sitemap_index(urls: Iterable[str]) -> str:
    entries = "".join(f"<sitemap><loc>{escape(url)}</loc></sitemap>" for url in urls)
    return f'<?xml version="1.0" encoding="UTF-8"?><sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{entries}</sitemapindex>'


__all__ = ["POLICY_VERSION", "PolicyDecision", "PublicProjection", "SeoPolicyError", "canonical_path", "canonical_slug", "evaluate_publication", "metadata", "project_report", "render_html", "render_sitemap", "render_sitemap_index"]
