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
from .public_h2_models import (
    CompanyPublicH2Response,
    PublicArbitrationSummary,
    PublicH2CoverageItem,
    PublicSafeCaseDetail,
)


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


def _money(value: object | None) -> str:
    if value is None:
        return "—"
    return f'<span title="{escape(value.display_exact)}">{escape(value.display_compact)}</span>'


_F1_ADVISORY = "Срок и вероятность погашения дебиторской задолженности не оцениваются."


def _finance_limitations(dto: CompanyPublicH2Response, block_id: str, *, advisory: bool) -> str:
    coverage = _coverage(dto, block_id)
    codes = list(coverage.limitation_codes)
    known = {item.code: item for item in dto.limitations}
    if (
        advisory
        and "receivables_collection_unassessed" in known
        and "receivables_collection_unassessed" not in codes
    ):
        codes.append("receivables_collection_unassessed")
    if codes:
        limitations = "<ul>" + "".join(
            f'<li data-h2-finance-limitation="{escape(code)}"><a href="#limitation-{escape(code)}">'
            f'{escape(known[code].message)}</a></li>'
            for code in codes
        ) + "</ul>"
    else:
        limitations = "<p>Ограничения для этого представления не указаны.</p>"
    return (
        f'<section aria-label="Ограничения финансового представления" '
        f'data-h2-finance-limitations="{escape(block_id)}"><h4>Ограничения</h4>'
        f"{limitations}</section>"
    )


def _finance_article(
    dto: CompanyPublicH2Response,
    article_id: str,
    block_id: str,
    title: str,
    body: str,
    *,
    advisory: bool = False,
) -> str:
    advisory_html = (
        '<p data-h2-finance-advisory="receivables_collection_unassessed">'
        f"{_F1_ADVISORY}</p>"
        if advisory else ""
    )
    return (
        f'<article id="{article_id}" data-h2-finance-article="{article_id}"><h3>{title}</h3>'
        f'<p data-h2-finance-coverage="{escape(block_id)}">Покрытие представления: '
        f'{escape(_coverage(dto, block_id).state)}.</p>'
        f"{advisory_html}{body}{_finance_limitations(dto, block_id, advisory=advisory)}"
        f'<div class="company-public-h2__finance-enhancement" data-h2-finance-enhancement="{article_id}" aria-hidden="true"></div></article>'
    )


def _finance_facts(dto: CompanyPublicH2Response) -> str:
    """The immutable server surface mirrored exactly by ``FinanceFacts``.

    It is table/dl first: the optional SVG enhancer is intentionally empty in
    SSR so a failed chunk cannot remove report facts.
    """
    f1, f2, f3, f4, f5 = (getattr(dto.blocks, f"finance_f{number}") for number in range(1, 6))
    missing = "<p>Подтверждённые финансовые данные не опубликованы.</p>"
    if f1 is None:
        f1_body = missing
    else:
        rows = (("Денежные средства", f1.cash_1250), ("Финансовые вложения", f1.investments_1240), ("Дебиторская задолженность", f1.receivables_1230), ("Краткосрочные обязательства", f1.short_liabilities_1500), ("Доступно без запасов", f1.available_without_inventory), ("Разница", f1.difference))
        f1_body = f"<p>Период: <time>{f1.year}</time></p><dl>" + "".join(f"<dt>{label}</dt><dd>{_money(value)}</dd>" for label, value in rows) + "</dl>"
    if f2 is None:
        f2_body = missing
    else:
        rows = "".join(f"<tr><th scope=\"row\">{period.year}</th><td>{_money(period.equity_1300)}</td><td>{_money(period.debt)}</td><td>{period.equity_share_decimal + ' %' if period.equity_share_decimal is not None else '—'}</td><td>{period.debt_share_decimal + ' %' if period.debt_share_decimal is not None else '—'}</td></tr>" for period in f2.periods)
        f2_body = '<table><caption>Структура финансирования по годам</caption><thead><tr><th scope="col">Год</th><th scope="col">Собственные средства</th><th scope="col">Долг</th><th scope="col">Доля собственных средств</th><th scope="col">Доля долга</th></tr></thead><tbody>' + rows + '</tbody></table>'
    if f3 is None:
        f3_body = missing
    else:
        def panel(label: str, money_key: str, yoy_key: str, summary: object) -> str:
            rows = "".join(f"<tr><th scope=\"row\">{point.year}</th><td>{_money(getattr(point, money_key))}</td><td>{getattr(point, yoy_key) + ' %' if getattr(point, yoy_key) is not None else '—'}</td></tr>" for point in f3.points)
            multiple = summary.multiple_decimal + " ×" if summary.multiple_decimal is not None else "—"
            return f'<section aria-label="{label}"><h4>{label}</h4><table><caption>{label} по годам</caption><thead><tr><th scope="col">Год</th><th scope="col">Значение</th><th scope="col">Изменение год к году</th></tr></thead><tbody>{rows}</tbody></table><p>Изменение за период: {_money(summary.change)}; мультипликатор: {multiple}</p></section>'
        f3_body = panel("Выручка", "revenue_2110", "revenue_yoy_decimal", f3.revenue_summary) + panel("Активы", "assets_1600", "assets_yoy_decimal", f3.assets_summary)
    if f4 is None:
        f4_body = missing
    else:
        rows = (("Выручка", f4.revenue_per_100_decimal), ("Валовая прибыль", f4.gross_per_100_decimal), ("Прибыль от продаж", f4.operating_per_100_decimal), ("Чистая прибыль", f4.net_per_100_decimal))
        f4_body = f"<p>Период: <time>{f4.year}</time></p><dl>" + "".join(f"<dt>{label}</dt><dd>{value + ' ₽ из 100 ₽' if value is not None else '—'}</dd>" for label, value in rows) + "</dl>"
    if f5 is None:
        f5_body = missing
    else:
        headers = "".join(f'<th scope="col">{year}</th>' for year in f5.years)
        rows = "".join(f'<tr><th scope="row">{row.label}</th>{"".join(f"<td>{_money(cell.value)}</td>" for cell in row.cells)}</tr>' for row in f5.rows)
        f5_body = f'<div class="company-public-h2__finance-table"><table><caption>Финансовые показатели по годам</caption><thead><tr><th scope="col">Показатель</th>{headers}</tr></thead><tbody>{rows}</tbody></table></div>'
    return "".join((
        _finance_article(dto, "finance-f1", "finance_f1", "Ликвидность", f1_body, advisory=f1 is not None),
        _finance_article(dto, "finance-f2", "finance_f2", "Структура финансирования", f2_body),
        _finance_article(dto, "finance-f3", "finance_f3", "Выручка и активы", f3_body),
        _finance_article(dto, "finance-f4", "finance_f4", "Прибыль на 100 рублей выручки", f4_body),
        _finance_article(dto, "finance-f5", "finance_f5", "Финансовые показатели по годам", f5_body),
    ))


_ARBITRATION_BLOCK_IDS = tuple(f"arbitration_a{number}" for number in range(1, 6))
_ARBITRATION_PRE_RESULT_STATES = {
    "operation_gate_closed": "gate_closed",
    "evidence_gate_closed": "gate_closed",
    "privacy_key_unavailable": "failed",
    "provider_error": "failed",
    "provider_binding_invalid": "failed",
}
_ARBITRATION_ROLE_LABELS = {
    "plaintiff": "Истец",
    "respondent": "Ответчик",
    "other": "Иная роль",
    "unattributed": "Роль не определена",
}
_ARBITRATION_OUTCOME_LABELS = {
    "won": "Требования удовлетворены",
    "lost": "В удовлетворении отказано",
    "returned": "Возвращено",
    "unknown": "Результат не определён",
}
_ARBITRATION_ARTICLES = (
    ("arbitration-a1", "arbitration_a1", "Арбитражная активность по годам"),
    ("arbitration-a2", "arbitration_a2", "Роли компании в делах"),
    ("arbitration-a3", "arbitration_a3", "Исходы дел"),
    ("arbitration-a4", "arbitration_a4", "Цена исков в рублях"),
    ("arbitration-a5", "arbitration_a5", "Противоположные стороны"),
)


def _is_policy_v3_arbitration(dto: CompanyPublicH2Response) -> bool:
    """Mirror the public contract's exact bound/source-less discriminator."""
    if dto.report_version != "3" or dto.snapshot_capability != "card_v2":
        return False
    arbitration_sources = tuple(
        item for item in dto.sources if item.dataset == "arbitration"
    )
    if len(arbitration_sources) == 1:
        source = arbitration_sources[0]
        return (
            len(dto.sources) == 3
            and source.effective_at is None
            and source.period is None
            and source.normalization_version
            == "company_card_arbitration_normalization_v2"
            and source.evidence_version == "datanewton_arbitration_registry_v2"
        )
    if arbitration_sources:
        return False
    coverage = tuple(_coverage(dto, block) for block in _ARBITRATION_BLOCK_IDS)
    reasons = {code for item in coverage for code in item.limitation_codes}
    if len(reasons) != 1:
        return False
    reason = next(iter(reasons))
    expected_state = _ARBITRATION_PRE_RESULT_STATES.get(reason)
    if expected_state is None or any(
        item.state != expected_state
        or item.population_scope != "not_applicable"
        or item.total is not None
        or item.returned is not None
        or item.eligible is not None
        or item.limitation_codes != (reason,)
        or getattr(dto.blocks, item.block_id) is not None
        for item in coverage
    ):
        return False
    linked = tuple(item for item in dto.limitations if item.code == reason)
    return (
        len(dto.sources) == 2
        and len(linked) == 1
        and linked[0].block_id is None
        and linked[0].field_id is None
    )


def _arbitration_count(value: int | None) -> str:
    return "—" if value is None else str(value)


def _arbitration_year(value: int | None) -> str:
    return "Год не указан" if value is None else str(value)


def _arbitration_collection_label(value: str) -> str:
    return {
        "complete_collection": "Полная коллекция",
        "returned_slice": "Полученная часть коллекции",
        "not_applicable": "Коллекция недоступна",
    }[value]


def _arbitration_case_label(value: PublicSafeCaseDetail) -> str:
    return value.case_number or value.case_public_id


def _arbitration_summary_scope(summary: PublicArbitrationSummary) -> str:
    population_scope = (
        "complete_collection" if summary.collection_complete else "returned_slice"
    )
    suffix = (
        "; общее число не подтверждено."
        if summary.source_total is None
        else f" из {_arbitration_count(summary.source_total)} дел."
    )
    return (
        f'<p data-h2-arbitration-scope="{population_scope}">Охват коллекции: '
        f'{_arbitration_collection_label(population_scope)}; получено '
        f'{_arbitration_count(summary.rows_observed)}{suffix}</p>'
    )


def _arbitration_case_list(
    cases: tuple[PublicSafeCaseDetail, ...],
    label: str,
) -> str:
    if not cases:
        return ""
    h = escape
    rows: list[str] = []
    for item in cases:
        optional = ""
        if item.amount is not None:
            optional += f"; цена иска: {h(item.amount.display_exact)}"
        if item.start_date is not None:
            optional += f"; дата начала: <time>{h(item.start_date)}</time>"
        if item.update_date is not None:
            optional += f"; дата обновления: <time>{h(item.update_date)}</time>"
        rows.append(
            f'<li data-h2-case-public-id="{h(item.case_public_id)}"><strong>'
            f'{h(_arbitration_case_label(item))}</strong>; публичный идентификатор: '
            f'<code>{h(item.case_public_id)}</code>; год: '
            f'{h(_arbitration_year(item.year))}; роль: '
            f'{h(_ARBITRATION_ROLE_LABELS[item.role])}; исход: '
            f'{h(_ARBITRATION_OUTCOME_LABELS[item.outcome])}{optional}.</li>'
        )
    return (
        '<section class="company-public-h2__arbitration-details" '
        f'aria-label="{h(label)}"><h4>{h(label)}</h4><ul>'
        f'{"".join(rows)}</ul></section>'
    )


def _arbitration_article(
    dto: CompanyPublicH2Response,
    *,
    article_id: str,
    block_id: str,
    title: str,
    body: str,
) -> str:
    h = escape
    coverage = _coverage(dto, block_id)
    known = {item.code: item for item in dto.limitations}
    if coverage.limitation_codes:
        limitations = "<ul>" + "".join(
            f'<li data-h2-arbitration-limitation="{h(code)}"><a '
            f'href="#limitation-{h(code)}">{h(known[code].message)}</a></li>'
            for code in coverage.limitation_codes
        ) + "</ul>"
    else:
        limitations = "<p>Ограничения для этого представления не указаны.</p>"
    returned = (
        ""
        if coverage.returned is None
        else f"; получено {_arbitration_count(coverage.returned)}"
    )
    total = (
        "" if coverage.total is None else f" из {_arbitration_count(coverage.total)}"
    )
    return (
        f'<article id="{article_id}" data-h2-arbitration-article="{article_id}">'
        f'<h3>{title}</h3><p data-h2-arbitration-coverage="{block_id}">'
        f'Покрытие представления: {h(coverage.state)}; '
        f'{h(_arbitration_collection_label(coverage.population_scope))}'
        f'{returned}{total}.</p>{body}<section '
        f'aria-label="Ограничения арбитражного представления" '
        f'data-h2-arbitration-limitations="{block_id}"><h4>Ограничения</h4>'
        f'{limitations}</section><div '
        f'class="company-public-h2__arbitration-enhancement" '
        f'data-h2-arbitration-enhancement="{article_id}" '
        f'aria-hidden="true"></div></article>'
    )


def _arbitration_unavailable_article(
    dto: CompanyPublicH2Response,
    article_id: str,
    block_id: str,
    title: str,
) -> str:
    return _arbitration_article(
        dto,
        article_id=article_id,
        block_id=block_id,
        title=title,
        body=(
            "<p>Подтверждённые арбитражные данные для этого "
            "представления не опубликованы.</p>"
        ),
    )


def _arbitration_a1_body(view: object) -> str:
    h = escape
    rows = "".join(
        f'<tr><th scope="row">{h(_arbitration_year(bucket.year))}</th>'
        f'<td>{_arbitration_count(bucket.plaintiff_count)}</td>'
        f'<td>{_arbitration_count(bucket.respondent_count)}</td>'
        f'<td>{_arbitration_count(bucket.other_count)}</td>'
        f'<td>{_arbitration_count(bucket.unattributed_count)}</td>'
        f'<td>{_arbitration_count(bucket.total_count)}</td></tr>'
        for bucket in view.buckets
    )
    details = "".join(
        f'<div data-h2-arbitration-detail-scope="{h(_arbitration_year(bucket.year))}.{h(detail.role)}">'
        f'<p>{h(_arbitration_year(bucket.year))}, '
        f'{h(_ARBITRATION_ROLE_LABELS[detail.role])}: {h(detail.scope.label)}.</p>'
        f'{_arbitration_case_list(detail.cases, f"{_arbitration_year(bucket.year)} — {_ARBITRATION_ROLE_LABELS[detail.role]}")}'
        f'</div>'
        for bucket in view.buckets
        for detail in bucket.role_details
    )
    empty = (
        "<p>Подтверждённая коллекция не содержит дел.</p>"
        if view.summary.unique_case_count == 0 else ""
    )
    return (
        f'{_arbitration_summary_scope(view.summary)}{empty}'
        '<div class="company-public-h2__arbitration-table"><table>'
        '<caption>Количество дел по наблюдаемым годам и роли компании</caption>'
        '<thead><tr><th scope="col">Год</th><th scope="col">Истец</th>'
        '<th scope="col">Ответчик</th><th scope="col">Иная роль</th>'
        '<th scope="col">Роль не определена</th><th scope="col">Всего</th>'
        f'</tr></thead><tbody>{rows}</tbody></table></div>{details}'
    )


def _arbitration_bar_body(view: object, *, roles: bool, caption: str) -> str:
    h = escape
    labels = _ARBITRATION_ROLE_LABELS if roles else _ARBITRATION_OUTCOME_LABELS
    rows = "".join(
        f'<tr><th scope="row">{h(labels[bar.category_id])}</th>'
        f'<td>{_arbitration_count(bar.count)}</td><td>'
        f'{("—" if bar.percent_decimal is None else h(bar.percent_decimal) + " %")}</td>'
        f'<td>{h(bar.scope.label)}</td></tr>'
        for bar in view.bars
    )
    details = "".join(
        _arbitration_case_list(
            bar.cases,
            f'{"Роль" if roles else "Исход"} — {labels[bar.category_id]}',
        )
        for bar in view.bars
    )
    return (
        f'{_arbitration_summary_scope(view.summary)}<p>Знаменатель: '
        f'{_arbitration_count(view.denominator)} дел.</p><div '
        f'class="company-public-h2__arbitration-table"><table><caption>{caption}</caption>'
        '<thead><tr><th scope="col">Категория</th><th scope="col">Количество</th>'
        '<th scope="col">Доля</th><th scope="col">Детализация</th></tr></thead>'
        f'<tbody>{rows}</tbody></table></div>{details}'
    )


def _arbitration_a4_body(view: object) -> str:
    h = escape
    group = view.currency_groups[0] if view.currency_groups else None
    if group is None:
        table = "<p>Подтверждённые цены исков в рублях отсутствуют.</p>"
    else:
        rows = "".join(
            f'<tr data-h2-case-public-id="{h(item.case_public_id)}"><th scope="row">'
            f'{h(_arbitration_case_label(item))}<br><code>{h(item.case_public_id)}</code>'
            f'</th><td>{h(_arbitration_year(item.year))}</td><td>'
            f'{h(_ARBITRATION_ROLE_LABELS[item.role])}</td><td>'
            f'{h(_ARBITRATION_OUTCOME_LABELS[item.outcome])}</td><td>'
            f'{h(item.amount.display_exact) if item.amount is not None else "—"}</td></tr>'
            for item in group.cases
        )
        table = (
            f'<p>{h(group.scope.label)}.</p><div '
            'class="company-public-h2__arbitration-table"><table>'
            '<caption>Цена иска в рублях по делам</caption><thead><tr>'
            '<th scope="col">Дело</th><th scope="col">Год</th>'
            '<th scope="col">Роль</th><th scope="col">Исход</th>'
            '<th scope="col">Цена иска</th></tr></thead>'
            f'<tbody>{rows}</tbody></table></div>'
        )
    return (
        f'{_arbitration_summary_scope(view.summary)}<p>Без цены иска: '
        f'{_arbitration_count(view.missing_amount_count)}; без обозначения валюты: '
        f'{_arbitration_count(view.missing_currency_count)}.</p>{table}'
    )


def _arbitration_a5_body(view: object) -> str:
    h = escape
    rows = "".join(
        f'<tr data-h2-opponent-public-id="{h(group.opponent_public_id)}">'
        f'<th scope="row">{h(group.display_name)}<br><code>'
        f'{h(group.opponent_public_id)}</code></th><td>'
        f'{_arbitration_count(group.case_count)}</td><td>'
        f'{h(group.case_scope.label)}</td></tr>'
        for group in view.groups
    )
    details = "".join(
        _arbitration_case_list(group.cases, group.display_name)
        for group in view.groups
    )
    return (
        f'{_arbitration_summary_scope(view.summary)}<p>{h(view.scope.label)}. '
        'Одно дело может относиться к нескольким скрытым сторонам; сумма по '
        'группам поэтому может быть больше числа дел.</p><p>Без безопасно '
        f'выделенной противоположной стороны: {_arbitration_count(view.cases_without_safe_opponent)}; '
        f'с несколькими сторонами: {_arbitration_count(view.multi_opponent_case_count)}.</p>'
        '<div class="company-public-h2__arbitration-table"><table>'
        '<caption>Скрытые противоположные стороны по количеству дел</caption>'
        '<thead><tr><th scope="col">Сторона</th><th scope="col">Количество дел</th>'
        f'<th scope="col">Детализация</th></tr></thead><tbody>{rows}</tbody>'
        f'</table></div>{details}'
    )


def _arbitration_facts(dto: CompanyPublicH2Response) -> str:
    views = tuple(getattr(dto.blocks, block_id) for _, block_id, _ in _ARBITRATION_ARTICLES)
    bodies = (
        None if views[0] is None else _arbitration_a1_body(views[0]),
        None if views[1] is None else _arbitration_bar_body(
            views[1], roles=True, caption="Распределение дел по роли компании",
        ),
        None if views[2] is None else _arbitration_bar_body(
            views[2], roles=False,
            caption="Распределение дел по подтверждённому исходу",
        ),
        None if views[3] is None else _arbitration_a4_body(views[3]),
        None if views[4] is None else _arbitration_a5_body(views[4]),
    )
    return "".join(
        _arbitration_unavailable_article(dto, article_id, block_id, title)
        if body is None
        else _arbitration_article(
            dto,
            article_id=article_id,
            block_id=block_id,
            title=title,
            body=body,
        )
        for (article_id, block_id, title), body in zip(
            _ARBITRATION_ARTICLES, bodies, strict=True,
        )
    )


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
    arbitration_surface = (
        _arbitration_facts(dto)
        if _is_policy_v3_arbitration(dto)
        else _block_surface(dto, "arbitration")
    )
    return f'''<main id="company-public-h2-root" class="company-public-h2" data-contract="{h(dto.contract_version)}" data-report-id="{h(dto.report_id)}">
<nav aria-label="Хлебные крошки"><ol><li><a href="{h(dto.breadcrumbs[0].path)}">{h(dto.breadcrumbs[0].label)}</a></li><li aria-current="page">{h(dto.breadcrumbs[1].label)}</li></ol></nav>
<header id="hero-status"><p>Статус отчёта: {h(status.label if status else "Статус не указан в отчёте")}</p>{f'<p>Дата статуса: <time>{h(status.effective_date)}</time></p>' if status and status.effective_date else ''}<h1 data-h2-field="identity.display_name">{h(dto.identity.display_name)}</h1><p>Дата составления отчёта: <time datetime="{h(dto.checked_at)}">{h(dto.checked_date_display)}</time></p><p>Идентификатор отчёта: <code data-h2-field="report_id">{h(dto.report_id)}</code></p></header>
<section id="narrative" aria-labelledby="narrative-title"><h2 id="narrative-title">{narrative_heading}</h2><p data-h2-field="narrative.description">{h(dto.narrative.description)}</p><h3>Покрытие описания</h3><ul>{_coverage_row(_coverage(dto, "narrative"))}</ul></section>
<nav id="in-page-navigation" aria-label="Разделы отчёта"><ol>{nav}</ol></nav>
<section id="requisites"><h2>Реквизиты</h2><dl>{''.join(requisites)}</dl>{f'<h3>Налоговые режимы</h3><ul>{"".join(f"<li>{h(item.label)}</li>" for item in dto.blocks.requisites.tax_modes)}</ul>' if dto.blocks.requisites.tax_modes else ''}{f'<h3>Дополнительные виды деятельности</h3><ul>{activities}</ul>' if activities else ''}{f'<h3>Руководители</h3><ul>{managers}</ul>' if managers else ''}{f'<h3>Владельцы</h3><ul>{owners}</ul>' if owners else ''}{f'<p>Численность: {employees.count} ({h(employees.period)})</p>' if employees else ''}{f'<p>Налоговый орган: {h(tax_authority.label)}</p>' if tax_authority else ''}<h3>Покрытие реквизитов</h3><ul>{_coverage_row(_coverage(dto, "requisites"))}</ul></section>
<section id="finance"><h2>Финансы</h2><h3>Покрытие</h3><ul>{finance_coverage}</ul>{_finance_facts(dto)}</section>
<section id="arbitration"><h2>Арбитраж</h2><h3>Покрытие</h3><ul>{arbitration_coverage}</ul>{arbitration_surface}</section>
<section id="sources-limitations"><h2>Источники и ограничения</h2><h3>Покрытие раздела</h3><ul>{_coverage_row(_coverage(dto, "sources_limitations"))}</ul><h3>Источники</h3><ul>{sources}</ul><h3>Ограничения</h3><ul>{limitations}</ul></section>
<section id="neutral-actions"><h2>Действия</h2><a class="company-public-h2__button company-public-h2__button--accent" href="{h(dto.actions[0].path)}">{h(dto.actions[0].label)}</a><a class="company-public-h2__button company-public-h2__button--accent" href="{h(dto.actions[1].path)}">{h(dto.actions[1].label)}</a></section>
<aside class="company-public-h2__cta" aria-label="Подготовка претензии"><h2>{h(dto.primary_claim_cta.heading)}</h2><p class="company-public-h2__cta-copy">{h(dto.primary_claim_cta.desktop_copy)}</p><a class="company-public-h2__button company-public-h2__button--accent" href="{h(dto.primary_claim_cta.path)}">{h(dto.primary_claim_cta.button_label)}</a></aside>
<div class="company-public-h2__cta-reserver" inert aria-hidden="true"></div><p class="company-public-h2__live" role="status" aria-live="polite"></p></main>'''


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
