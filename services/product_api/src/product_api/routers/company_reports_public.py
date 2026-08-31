"""Anonymous, read-only SSR endpoints for persisted H1/H2 reports."""
from __future__ import annotations

import re
from secrets import token_urlsafe

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, PlainTextResponse, RedirectResponse, Response
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

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
    PublicDocumentInvalid,
    PublicDocumentKind,
    resolve_public_document,
    scan_public_sitemap,
)
from product_api.company_reports.company_card_v2.public_h2_asset_manifest import PublicH2AssetManifest
from product_api.company_reports.company_card_v2.public_h2_document import (
    public_h2_security_headers, render_public_h2_document, render_public_h2_error_document,
)
from product_api.company_reports.company_card_v2.service import (
    PublicH2Failed,
    PublicH2Invalid,
    PublicH2NotEligible,
    PublicH2NotFound,
    PublicH2Pending,
    resolve_direct_public_h2,
)
from product_api.company_reports.seo import render_sitemap, render_sitemap_index
from product_api.company_reports.company_urls import parse_company_key
from product_api.db.session import get_session
from product_api.settings import get_settings

router = APIRouter(tags=["company-reports-public"])
_PUBLIC_H2_ASSET_MANIFEST: PublicH2AssetManifest | None = None
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


def _direct_plain_redirect(inn: str) -> Response:
    """Move an old canonical H1/H2 URL onto the SPA fallback boundary."""
    return RedirectResponse(
        f"/company/{inn}",
        status_code=302,
        headers=_headers("noindex,follow"),
    )


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
    parsed = parse_company_key(company_key)
    if parsed is None:
        return _not_found()
    try:
        inn = parsed.inn
        current = get_settings()
        direct_h2 = current.company_card_v2_direct_launch_enabled
        if direct_h2:
            dto = await resolve_direct_public_h2(
                session,
                inn=inn,
                rollout_generation=current.company_card_v2_rollout_generation,
            )
            document_kind = PublicDocumentKind.H2
            document_assigned = False
        else:
            document = await resolve_public_document(session, inn=inn)
            dto = document.dto
            document_kind = document.kind
            document_assigned = document.assigned
        if document_kind is PublicDocumentKind.H1 and not document_assigned and dto.projection_scope != "published":
            # Preserve the historical unpublished H1 behaviour.  The plain
            # form is deliberately the only nginx SPA fallback boundary.
            return _not_found()
        if dto.canonical_path != f"/company/{company_key}":
            return RedirectResponse(dto.canonical_path, status_code=301, headers=_headers("noindex,follow"))
        if document_kind is PublicDocumentKind.H1:
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
    except PublicH2NotFound:
        if get_settings().company_card_v2_direct_launch_enabled and parsed.kind != "plain":
            return _direct_plain_redirect(inn)
        return _not_found()
    except (PublicH2Pending, PublicH2Failed, PublicH2NotEligible):
        if get_settings().company_card_v2_direct_launch_enabled:
            if parsed.kind != "plain":
                # Preserve old indexed/bookmarked H1 slugs across the direct
                # switch.  The temporary redirect lands on the one nginx SPA
                # fallback boundary, where the direct H2 lifecycle can start.
                return _direct_plain_redirect(inn)
            if parsed.kind == "plain":
                # The plain path remains the nginx SPA fallback while a direct
                # H2 lifecycle is still pending.  Once ready, the same read
                # resolves the staged saved-result and redirects to its
                # canonical slug.
                return _not_found()
        return _safe_error(409, "Отчёт пока недоступен", "Публичный документ ещё не готов.")
    except PublicH1UnavailableError:
        return PlainTextResponse("Unavailable", status_code=503, headers=_headers("noindex,follow"))
    except (PublicProjectionInvalidError, PublicDocumentInvalid, PublicH2Invalid):
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
        size = get_settings().seo_sitemap_chunk_size
        scan = await scan_public_sitemap(
            session,
            chunk_size=size,
            chunk_number=None,
        )
        base = get_settings().seo_public_base_url.rstrip("/")
        chunks = [
            f"{base}/sitemaps/{number}.xml"
            for number in range(1, (scan.eligible_count + size - 1) // size + 1)
        ]
        return Response(render_sitemap_index(chunks), media_type="application/xml", headers=_headers("noindex,follow"))
    except (SQLAlchemyError, RuntimeError):
        return PlainTextResponse("Unavailable", status_code=503, headers=_headers("noindex,follow"))


@router.get("/sitemaps/{chunk}")
async def sitemap_chunk(chunk: str, request: Request, session: AsyncSession = Depends(get_session)) -> Response:
    if request.query_params or not _CHUNK.fullmatch(chunk):
        return _not_found()
    try:
        number = int(chunk[:-4])
    except ValueError:
        # Python bounds decimal parsing to protect the process from hostile
        # inputs.  An otherwise numeric but overlong chunk remains a stable
        # out-of-range public URL, not an internal error.
        return _not_found()
    try:
        size = get_settings().seo_sitemap_chunk_size
        scan = await scan_public_sitemap(
            session,
            chunk_size=size,
            chunk_number=number,
        )
        if not scan.entries:
            return _not_found()
        base = get_settings().seo_public_base_url.rstrip("/")
        return Response(
            render_sitemap(
                (f"{base}{entry.canonical_path}", entry.published_lastmod)
                for entry in scan.entries
            ),
            media_type="application/xml",
            headers=_headers("noindex,follow"),
        )
    except (SQLAlchemyError, RuntimeError):
        return PlainTextResponse("Unavailable", status_code=503, headers=_headers("noindex,follow"))


__all__ = ["router", "set_public_h2_asset_manifest"]
