"""Server-rendered, no-network Company Card v2 document.

The factual document intentionally has a small, stable DOM surface. The client
enhancement replaces only the contents of the root with the same ordered
semantic surface; it never fetches factual data.
"""
from __future__ import annotations

from html import escape
from secrets import token_urlsafe

from .canonical_json import script_safe_json_bytes
from .public_h2_asset_manifest import PublicH2AssetManifest, asset_integrity_attribute
from .public_h2_models import CompanyPublicH2Response, PublicH2CoverageItem


def public_h2_security_headers(nonce: str, robots: str) -> dict[str, str]:
    return {
        "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff",
        "Referrer-Policy": "no-referrer",
        "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
        "X-Robots-Tag": robots,
        "Content-Security-Policy": (
            "default-src 'none'; base-uri 'none'; object-src 'none'; frame-ancestors 'none'; "
            "form-action 'self'; img-src 'self' data:; font-src 'self'; style-src 'self'; "
            f"script-src 'self' 'nonce-{nonce}'; connect-src 'self'; manifest-src 'self'"
        ),
    }


def _asset(manifest: PublicH2AssetManifest, path: str):
    return next(asset for asset in manifest.assets if asset.path == path)


def _coverage(dto: CompanyPublicH2Response, block: str) -> PublicH2CoverageItem:
    return next(value for value in dto.coverage if value.block_id == block)


def _coverage_row(item: PublicH2CoverageItem) -> str:
    h = escape
    counts = "".join(
        f'<span data-h2-coverage="{h(item.block_id)}.{name}">{name}: {value}</span>'
        for name, value in (("total", item.total), ("returned", item.returned), ("eligible", item.eligible))
        if value is not None
    )
    limitations = "".join(
        f'<a href="#limitation-{h(code)}">Ограничение: {h(code)}</a>'
        for code in item.limitation_codes
    )
    return (
        f'<li data-h2-coverage="{h(item.block_id)}">'
        f'<strong>{h(item.block_id)}</strong>: {h(item.state)}; '
        f'охват: {h(item.population_scope)}{("; " + counts) if counts else ""}'
        f'{("; " + limitations) if limitations else ""}</li>'
    )


def _block_surface(dto: CompanyPublicH2Response, prefix: str) -> str:
    """Render bounded factual availability without chart artwork or conclusions."""
    h = escape
    suffixes = ("f1", "f2", "f3", "f4", "f5") if prefix == "finance" else ("a1", "a2", "a3", "a4", "a5")
    rows: list[str] = []
    for suffix in suffixes:
        block_id = f"{prefix}_{suffix}"
        value = getattr(dto.blocks, block_id)
        label = block_id.replace("_", " ").upper()
        fact = f": подтверждённые данные {h(value.view_id)}" if value is not None else ": данные не опубликованы"
        rows.append(f'<li data-h2-block="{h(block_id)}"><strong>{h(label)}</strong>{fact}</li>')
    return "<ul>" + "".join(rows) + "</ul>"


def render_public_h2_body(dto: CompanyPublicH2Response) -> str:
    """Render factual shell only; charts and computed conclusions are absent."""
    h = escape
    limitations = "".join(
        f'<li id="limitation-{h(item.code)}" data-h2-limitation="{h(item.code)}" '
        f'data-h2-limitation-block="{h(item.block_id or "")}" '
        f'data-h2-limitation-field="{h(item.field_id or "")}">{h(item.message)}</li>'
        for item in dto.limitations
    )
    sources = "".join(
        f'<li data-h2-field="sources.{h(item.dataset)}">{h(item.dataset)} — {h(item.received_at)}'
        f'{("; дата актуальности: " + h(item.effective_at)) if item.effective_at else ""}'
        f'{("; период: " + h(item.period)) if item.period else ""}</li>' for item in dto.sources
    )
    nav = "".join(
        f'<li><a href="#{anchor}">{label}</a></li>'
        for anchor, label in (("requisites", "Реквизиты"), ("finance", "Финансы"), ("arbitration", "Арбитраж"))
    )
    requisites: list[str] = [
        f"<dt>Полное наименование</dt><dd>{h(dto.identity.legal_full_name)}</dd>",
        f'<dt>ИНН</dt><dd data-h2-field="identity.inn">{h(dto.identity.inn)}</dd>',
    ]
    optional_identity = (("Краткое наименование", dto.identity.short_name), ("ОГРН", dto.identity.ogrn), ("КПП", dto.identity.kpp), ("Дата регистрации", dto.identity.registration_date), ("Дата прекращения деятельности", dto.identity.dissolution_date))
    requisites.extend(f"<dt>{label}</dt><dd>{h(value)}</dd>" for label, value in optional_identity if value)
    if dto.blocks.requisites.address:
        requisites.append(f"<dt>Адрес</dt><dd>{h(dto.blocks.requisites.address.display)}</dd>")
    if dto.blocks.requisites.legal_form:
        requisites.append(f"<dt>Организационно-правовая форма</dt><dd>{h(dto.blocks.requisites.legal_form.label)}</dd>")
    if dto.blocks.requisites.primary_activity:
        requisites.append(f"<dt>Основной вид деятельности</dt><dd>{h(dto.blocks.requisites.primary_activity.label)}</dd>")
    if dto.blocks.requisites.charter_capital:
        requisites.append(f"<dt>Уставный капитал</dt><dd>{h(dto.blocks.requisites.charter_capital.display_exact)}</dd>")
    activities = "".join(f"<li>{h(item.label)}</li>" for item in dto.blocks.requisites.additional_activities)
    managers = "".join(f"<li>{h(item.name)} — {h(item.role)}</li>" for item in dto.blocks.requisites.managers)
    owners = "".join(f"<li>{h(item.display_name)}</li>" for item in dto.blocks.requisites.owners)
    employees = dto.blocks.requisites.employees
    tax_authority = dto.blocks.requisites.tax_authority
    status = dto.identity.status
    narrative_heading = "Описание деятельности" if dto.narrative.mode == "artifact" else "Описание деятельности — подтверждённый шаблон"
    finance_coverage = "".join(_coverage_row(_coverage(dto, block)) for block in ("finance_f1", "finance_f2", "finance_f3", "finance_f4", "finance_f5"))
    arbitration_coverage = "".join(_coverage_row(_coverage(dto, block)) for block in ("arbitration_a1", "arbitration_a2", "arbitration_a3", "arbitration_a4", "arbitration_a5"))
    return f'''<main id="company-public-h2-root" class="company-public-h2" data-contract="{h(dto.contract_version)}" data-report-id="{h(dto.report_id)}">
<nav aria-label="Хлебные крошки"><ol><li><a href="{h(dto.breadcrumbs[0].path)}">{h(dto.breadcrumbs[0].label)}</a></li><li aria-current="page">{h(dto.breadcrumbs[1].label)}</li></ol></nav>
<header id="hero-status"><p>Статус отчёта: {h(status.label if status else "Статус не указан в отчёте")}</p>{f'<p>Дата статуса: <time>{h(status.effective_date)}</time></p>' if status and status.effective_date else ''}<h1 data-h2-field="identity.display_name">{h(dto.identity.display_name)}</h1><p>Дата составления отчёта: <time datetime="{h(dto.checked_at)}">{h(dto.checked_date_display)}</time></p><p>Идентификатор отчёта: <code data-h2-field="report_id">{h(dto.report_id)}</code></p></header>
<section id="narrative" aria-labelledby="narrative-title"><h2 id="narrative-title">{narrative_heading}</h2><p data-h2-field="narrative.description">{h(dto.narrative.description)}</p><h3>Покрытие описания</h3><ul>{_coverage_row(_coverage(dto, "narrative"))}</ul></section>
<nav id="in-page-navigation" aria-label="Разделы отчёта"><ol>{nav}</ol></nav>
<section id="requisites"><h2>Реквизиты</h2><dl>{''.join(requisites)}</dl>{f'<h3>Налоговые режимы</h3><ul>{"".join(f"<li>{h(item.label)}</li>" for item in dto.blocks.requisites.tax_modes)}</ul>' if dto.blocks.requisites.tax_modes else ''}{f'<h3>Дополнительные виды деятельности</h3><ul>{activities}</ul>' if activities else ''}{f'<h3>Руководители</h3><ul>{managers}</ul>' if managers else ''}{f'<h3>Владельцы</h3><ul>{owners}</ul>' if owners else ''}{f'<p>Численность: {employees.count} ({h(employees.period)})</p>' if employees else ''}{f'<p>Налоговый орган: {h(tax_authority.label)}</p>' if tax_authority else ''}<h3>Покрытие реквизитов</h3><ul>{_coverage_row(_coverage(dto, "requisites"))}</ul></section>
<section id="finance"><h2>Финансы</h2><h3>Покрытие</h3><ul>{finance_coverage}</ul>{_block_surface(dto, "finance")}</section>
<section id="arbitration"><h2>Арбитраж</h2><h3>Покрытие</h3><ul>{arbitration_coverage}</ul>{_block_surface(dto, "arbitration")}</section>
<section id="sources-limitations"><h2>Источники и ограничения</h2><h3>Покрытие раздела</h3><ul>{_coverage_row(_coverage(dto, "sources_limitations"))}</ul><h3>Источники</h3><ul>{sources}</ul><h3>Ограничения</h3><ul>{limitations}</ul></section>
<section id="neutral-actions"><h2>Действия</h2><a class="company-public-h2__button company-public-h2__button--accent" href="{h(dto.actions[0].path)}">{h(dto.actions[0].label)}</a><a class="company-public-h2__button company-public-h2__button--accent" href="{h(dto.actions[1].path)}">{h(dto.actions[1].label)}</a></section>
<aside class="company-public-h2__cta" aria-label="Подготовка претензии"><h2>{h(dto.primary_claim_cta.heading)}</h2><p class="company-public-h2__cta-copy">{h(dto.primary_claim_cta.desktop_copy)}</p><a class="company-public-h2__button company-public-h2__button--accent" href="{h(dto.primary_claim_cta.path)}">{h(dto.primary_claim_cta.button_label)}</a></aside>
<div class="company-public-h2__cta-reserver" inert aria-hidden="true"></div><p class="company-public-h2__live" aria-live="polite"></p></main>'''


def render_public_h2_document(dto: CompanyPublicH2Response, manifest: PublicH2AssetManifest, nonce: str | None = None, robots: str = "noindex,follow") -> str:
    nonce = nonce or token_urlsafe(18)
    state = script_safe_json_bytes(dto.model_dump(mode="json"))
    if len(state) > 786432:
        raise ValueError("public projection exceeds embedded state cap")
    js, css = _asset(manifest, manifest.entry_js_path), _asset(manifest, manifest.entry_css_path)
    title = f"{dto.identity.display_name} — проверка компании"
    description = "Публичный отчёт о компании: реквизиты, источники и ограничения данных."
    return f'''<!doctype html><html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>{escape(title)}</title><meta name="description" content="{escape(description)}"><meta name="robots" content="{escape(robots)}"><link rel="canonical" href="{escape(dto.canonical_path)}"><link rel="stylesheet" href="{escape(css.path)}" integrity="{asset_integrity_attribute(css)}" crossorigin="anonymous"></head><body>{render_public_h2_body(dto)}<script id="company-public-h2-state" type="application/json" nonce="{escape(nonce)}">{state.decode('utf-8')}</script><script type="module" src="{escape(js.path)}" integrity="{asset_integrity_attribute(js)}" crossorigin="anonymous" nonce="{escape(nonce)}"></script></body></html>''' + "\n"


def render_public_h2_error_document(title: str, message: str) -> str:
    return f'<!doctype html><html lang="ru"><head><meta charset="utf-8"><meta name="robots" content="noindex,follow"><title>{escape(title)}</title></head><body><main><h1>{escape(title)}</h1><p>{escape(message)}</p></main></body></html>'


__all__ = ["render_public_h2_body", "render_public_h2_document", "render_public_h2_error_document", "public_h2_security_headers"]
