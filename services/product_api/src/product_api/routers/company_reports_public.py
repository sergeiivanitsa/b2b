"""Anonymous, read-only SSR endpoints for explicitly published reports."""
from __future__ import annotations

import re

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, PlainTextResponse, RedirectResponse, Response
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from product_api.company_reports.persistence.publications import get_public_page, list_indexable_publications
from product_api.company_reports.persistence.serialization import calculate_company_report_snapshot_hash, company_report_from_snapshot
from product_api.company_reports.seo import canonical_path, evaluate_publication, render_html, render_sitemap, render_sitemap_index
from product_api.db.session import get_session
from product_api.settings import get_settings

router = APIRouter(tags=["company-reports-public"])
_KEY = re.compile(r"(?P<inn>[0-9]{10}(?:[0-9]{2})?)-(?P<slug>[a-z0-9]+(?:-[a-z0-9]+)*)$")
_CHUNK = re.compile(r"[1-9][0-9]*\.xml$")


def _headers(robots: str) -> dict[str, str]:
    return {"X-Robots-Tag": robots, "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"}


def _not_found() -> Response:
    return PlainTextResponse("Not found", status_code=404, headers=_headers("noindex,follow"))


def _current_public_projection(page):
    """Return the current policy result only when registry and snapshot agree."""
    if page.publication.status != "active" or not page.publication.indexable:
        return None
    if page.report.lifecycle_status not in {"complete", "partial"} or not page.report.normalized_snapshot or not page.report.snapshot_hash:
        return None
    try:
        snapshot_hash = calculate_company_report_snapshot_hash(page.report.normalized_snapshot)
        if snapshot_hash != page.report.snapshot_hash or snapshot_hash != page.publication.snapshot_hash:
            return None
        decision = evaluate_publication(company_report_from_snapshot(page.report.normalized_snapshot))
        if not decision.indexable or decision.projection is None:
            return None
        if canonical_path(decision.projection.inn, decision.projection.name) != page.publication.canonical_path:
            return None
    except Exception:
        return None
    return decision.projection


@router.get("/company/{company_key}", response_class=HTMLResponse)
async def public_company_page(company_key: str, request: Request, session: AsyncSession = Depends(get_session)) -> Response:
    if request.query_params:
        return _not_found()
    match = _KEY.fullmatch(company_key)
    if match is None:
        return _not_found()
    try:
        page = await get_public_page(session, inn=match.group("inn"))
        if page is None or page.publication.status != "active":
            return _not_found()
        if page.report.lifecycle_status not in {"complete", "partial"} or not page.report.normalized_snapshot or not page.report.snapshot_hash:
            return _not_found()
        if calculate_company_report_snapshot_hash(page.report.normalized_snapshot) != page.publication.snapshot_hash or page.report.snapshot_hash != page.publication.snapshot_hash:
            return PlainTextResponse("Internal error", status_code=500, headers=_headers("noindex,follow"))
        report = company_report_from_snapshot(page.report.normalized_snapshot)
        decision = evaluate_publication(report)
        if decision.projection is None:
            return PlainTextResponse("Internal error", status_code=500, headers=_headers("noindex,follow"))
        expected = canonical_path(decision.projection.inn, decision.projection.name)
        if match.group("slug") != page.publication.canonical_slug:
            return RedirectResponse(expected, status_code=301, headers=_headers("noindex,follow"))
        robots = "index,follow" if page.publication.indexable and decision.indexable and page.publication.canonical_path == expected else "noindex,follow"
        return HTMLResponse(render_html(decision.projection, base_url=get_settings().seo_public_base_url, robots=robots), headers=_headers(robots))
    except SQLAlchemyError:
        return PlainTextResponse("Unavailable", status_code=503, headers=_headers("noindex,follow"))
    except Exception:
        return PlainTextResponse("Internal error", status_code=500, headers=_headers("noindex,follow"))


@router.get("/robots.txt")
async def robots(request: Request) -> Response:
    if request.query_params:
        return _not_found()
    base = get_settings().seo_public_base_url.rstrip("/")
    return PlainTextResponse(f"User-agent: *\nAllow: /\nSitemap: {base}/sitemaps/index.xml\n", headers=_headers("noindex,follow"))


@router.get("/sitemaps/index.xml")
async def sitemap_index(request: Request, session: AsyncSession = Depends(get_session)) -> Response:
    if request.query_params:
        return _not_found()
    try:
        pages = [page for page in await list_indexable_publications(session) if _current_public_projection(page) is not None]
        size = get_settings().seo_sitemap_chunk_size
        base = get_settings().seo_public_base_url.rstrip("/")
        chunks = [f"{base}/sitemaps/{number}.xml" for number in range(1, (len(pages) + size - 1) // size + 1)]
        return Response(render_sitemap_index(chunks), media_type="application/xml", headers=_headers("noindex,follow"))
    except SQLAlchemyError:
        return PlainTextResponse("Unavailable", status_code=503, headers=_headers("noindex,follow"))


@router.get("/sitemaps/{chunk}")
async def sitemap_chunk(chunk: str, request: Request, session: AsyncSession = Depends(get_session)) -> Response:
    if request.query_params or not _CHUNK.fullmatch(chunk):
        return _not_found()
    try:
        pages = [page for page in await list_indexable_publications(session) if _current_public_projection(page) is not None]
        size, number = get_settings().seo_sitemap_chunk_size, int(chunk[:-4])
        selected = pages[(number - 1) * size:number * size]
        if not selected:
            return _not_found()
        base = get_settings().seo_public_base_url.rstrip("/")
        return Response(render_sitemap(((f"{base}{page.publication.canonical_path}", page.publication.published_lastmod) for page in selected if page.publication.published_lastmod)), media_type="application/xml", headers=_headers("noindex,follow"))
    except SQLAlchemyError:
        return PlainTextResponse("Unavailable", status_code=503, headers=_headers("noindex,follow"))


__all__ = ["router"]
