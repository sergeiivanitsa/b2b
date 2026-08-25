"""Anonymous, read-only SSR endpoints for explicitly published H1 reports.

The saved-result-only H2 resolver introduced in iteration 21 is deliberately
not routed here: iteration 22 owns the public H2 page shell and SSR wiring.
"""
from __future__ import annotations

import re
from secrets import token_urlsafe

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, PlainTextResponse, RedirectResponse, Response
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from product_api.company_reports.persistence.publications import list_indexable_publications
from product_api.company_reports.public_h1 import render_public_h1_html
from product_api.company_reports.public_h1_service import (
    PublicH1FailedError,
    PublicH1NotEligibleError,
    PublicH1NotFoundError,
    PublicH1PendingError,
    PublicH1UnavailableError,
    PublicProjectionInvalidError,
    resolve_public_h1,
    validate_active_publication,
)
from product_api.company_reports.public_document_service import (
    PublicDocumentInvalid, PublicDocumentKind, resolve_public_document,
)
from product_api.company_reports.company_card_v2.public_h2_asset_manifest import PublicH2AssetManifest
from product_api.company_reports.company_card_v2.public_h2_document import (
    public_h2_security_headers, render_public_h2_document, render_public_h2_error_document,
)
from product_api.company_reports.company_card_v2.service import PublicH2Failed, PublicH2NotEligible, PublicH2Pending
from product_api.company_reports.seo import render_sitemap, render_sitemap_index
from product_api.db.session import get_session
from product_api.settings import get_settings

router = APIRouter(tags=["company-reports-public"])
_PUBLIC_H2_ASSET_MANIFEST: PublicH2AssetManifest | None = None
_KEY = re.compile(r"(?P<inn>[0-9]{10}(?:[0-9]{2})?)-(?P<slug>[a-z0-9]+(?:-[a-z0-9]+)*)$")
_PLAIN = re.compile(r"(?P<inn>[0-9]{10}(?:[0-9]{2})?)$")
_CHUNK = re.compile(r"[1-9][0-9]*\.xml$")


def _headers(robots: str) -> dict[str, str]:
    return {"X-Robots-Tag": robots, "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"}


def set_public_h2_asset_manifest(manifest: PublicH2AssetManifest) -> None:
    """Inject the startup-validated immutable package manifest once."""
    global _PUBLIC_H2_ASSET_MANIFEST
    _PUBLIC_H2_ASSET_MANIFEST = manifest


def _public_h2_asset_manifest() -> PublicH2AssetManifest:
    if _PUBLIC_H2_ASSET_MANIFEST is None:
        raise RuntimeError("public H2 asset manifest is not initialized")
    return _PUBLIC_H2_ASSET_MANIFEST


def _not_found() -> Response:
    return PlainTextResponse("Not found", status_code=404, headers=_headers("noindex,follow"))


def _current_public_projection(page):
    """The same pure complete pin predicate used by API/SSR resolution."""
    try:
        dto = validate_active_publication(page)
        return dto if dto.indexable else None
    except (PublicProjectionInvalidError, ValueError):
        return None


def _safe_error(status_code: int, title: str, message: str) -> Response:
    return HTMLResponse(
        render_public_h2_error_document(title, message), status_code=status_code,
        headers=_headers("noindex,follow"),
    )


@router.api_route("/company/{company_key}", methods=["GET", "HEAD"], response_class=HTMLResponse)
async def public_company_page(company_key: str, request: Request, session: AsyncSession = Depends(get_session)) -> Response:
    if request.query_params:
        return _safe_error(422, "Некорректный запрос", "Параметры запроса не поддерживаются.")
    match = _KEY.fullmatch(company_key)
    plain = _PLAIN.fullmatch(company_key)
    if match is None and plain is None:
        return _not_found()
    try:
        inn = (match or plain).group("inn")
        document = await resolve_public_document(session, inn=inn)
        dto = document.dto
        if document.kind is PublicDocumentKind.H1 and not document.assigned and dto.projection_scope != "published":
            # Preserve the historical unpublished H1 behaviour.  The plain
            # form is deliberately the only nginx SPA fallback boundary.
            return _not_found()
        if dto.canonical_path != f"/company/{company_key}":
            return RedirectResponse(dto.canonical_path, status_code=301, headers=_headers("noindex,follow"))
        if document.kind is PublicDocumentKind.H1:
            robots = "index,follow" if dto.indexable else "noindex,follow"
            return HTMLResponse(render_public_h1_html(dto), headers=_headers(robots))
        nonce = token_urlsafe(18)
        robots = "index,follow" if dto.indexable else "noindex,follow"
        return HTMLResponse(
            render_public_h2_document(dto, _public_h2_asset_manifest(), nonce, robots),
            headers=public_h2_security_headers(nonce, robots),
        )
    except (PublicH1NotFoundError, PublicH1PendingError, PublicH1FailedError, PublicH1NotEligibleError):
        return _not_found()
    except (PublicH2Pending, PublicH2Failed, PublicH2NotEligible):
        return _safe_error(409, "Отчёт пока недоступен", "Публичный документ ещё не готов.")
    except PublicH1UnavailableError:
        return PlainTextResponse("Unavailable", status_code=503, headers=_headers("noindex,follow"))
    except (PublicProjectionInvalidError, PublicDocumentInvalid):
        return _safe_error(500, "Внутренняя ошибка", "Документ отчёта недоступен.")
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


__all__ = ["router", "set_public_h2_asset_manifest"]
