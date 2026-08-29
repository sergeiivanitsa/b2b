from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import UUID

import pytest
from sqlalchemy.exc import SQLAlchemyError

from product_api.company_reports import public_document_service as service
from product_api.company_reports.persistence.publications import (
    PublicSitemapCandidate,
    PublicSitemapCandidateKey,
)
from product_api.company_reports.public_h1_service import (
    PublicProjectionInvalidError,
)


_LASTMOD = datetime(2026, 8, 24, 12, tzinfo=timezone.utc)


def _h1_candidate(index: int) -> PublicSitemapCandidate:
    subject_id = UUID(int=index + 1)
    inn = f"{index:010d}"
    path = f"/company/{inn}-company"
    subject = SimpleNamespace(id=subject_id, normalized_identifier=inn)
    report = SimpleNamespace(id=f"report-{index}", subject_id=subject_id)
    publication = SimpleNamespace(
        canonical_path=path,
        published_lastmod=_LASTMOD,
        indexable=True,
    )
    return PublicSitemapCandidate(
        subject=subject,
        assignment=None,
        pin=None,
        report=report,
        publication=publication,
        presentation=None,
        narrative_job=None,
        narrative_artifact=None,
        key=PublicSitemapCandidateKey(inn, path, subject_id),
    )


def _install_stream(
    monkeypatch: pytest.MonkeyPatch,
    candidates: tuple[PublicSitemapCandidate, ...],
    *,
    calls: list[int],
) -> None:
    async def begin(_session: object) -> None:
        calls.append(-1)

    async def fetch(
        _session: object, *, after: PublicSitemapCandidateKey | None, limit: int
    ) -> tuple[PublicSitemapCandidate, ...]:
        calls.append(limit)
        start = 0
        if after is not None:
            start = next(
                index + 1
                for index, candidate in enumerate(candidates)
                if candidate.key == after
            )
        return candidates[start : start + limit]

    monkeypatch.setattr(service, "begin_public_sitemap_snapshot", begin)
    monkeypatch.setattr(service, "fetch_public_sitemap_candidate_window", fetch)


@pytest.mark.asyncio
async def test_index_scans_bounded_keyset_windows_and_retains_only_count(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    candidates = tuple(_h1_candidate(index) for index in range(250))
    calls: list[int] = []
    _install_stream(monkeypatch, candidates, calls=calls)

    def validate(page: object) -> object:
        return SimpleNamespace(
            canonical_path=page.publication.canonical_path,
            indexable=True,
        )

    monkeypatch.setattr(service, "validate_active_publication", validate)
    result = await service.scan_public_sitemap(
        object(), chunk_size=25, chunk_number=None
    )

    assert result.eligible_count == 250
    assert result.entries == ()
    assert calls == [-1, 100, 100, 100]


@pytest.mark.asyncio
async def test_validated_chunk_boundaries_have_no_holes_or_duplicates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    candidates = tuple(_h1_candidate(index) for index in range(23))
    invalid = {4, 5, 9, 10, 11, 20}

    def validate(page: object) -> object:
        index = int(page.subject.normalized_identifier)
        if index in invalid:
            raise PublicProjectionInvalidError()
        return SimpleNamespace(
            canonical_path=page.publication.canonical_path,
            indexable=True,
        )

    monkeypatch.setattr(service, "validate_active_publication", validate)
    expected = [
        candidate.publication.canonical_path
        for index, candidate in enumerate(candidates)
        if index not in invalid
    ]
    combined: list[str] = []
    for chunk_number in range(1, 6):
        calls: list[int] = []
        _install_stream(monkeypatch, candidates, calls=calls)
        scan = await service.scan_public_sitemap(
            object(),
            chunk_size=5,
            chunk_number=chunk_number,
            validation_window_size=7,
        )
        assert len(scan.entries) <= 5
        combined.extend(entry.canonical_path for entry in scan.entries)
    assert combined == expected


@pytest.mark.asyncio
async def test_assignment_presence_suppresses_valid_h1_when_exact_tuple_is_corrupt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    base = _h1_candidate(1)
    corrupt = PublicSitemapCandidate(
        subject=base.subject,
        assignment=SimpleNamespace(presentation_contract="company_public_h2_v1"),
        pin=None,
        report=None,
        publication=base.publication,
        presentation=None,
        narrative_job=None,
        narrative_artifact=None,
        key=base.key,
    )
    calls: list[int] = []
    _install_stream(monkeypatch, (corrupt,), calls=calls)

    def forbidden(_page: object) -> object:
        raise AssertionError("assigned corruption must not fall back to H1")

    monkeypatch.setattr(service, "validate_active_publication", forbidden)
    scan = await service.scan_public_sitemap(
        object(), chunk_size=10, chunk_number=1
    )
    assert scan.eligible_count == 0 and scan.entries == ()


@pytest.mark.asyncio
async def test_assigned_noindex_h2_is_fully_validated_then_omitted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    base = _h1_candidate(2)
    pin = SimpleNamespace(
        projection_scope="active_publication",
        published_lastmod=_LASTMOD,
    )
    candidate = PublicSitemapCandidate(
        subject=base.subject,
        assignment=SimpleNamespace(presentation_contract="company_public_h2_v1"),
        pin=pin,
        report=base.report,
        publication=base.publication,
        presentation=object(),
        narrative_job=object(),
        narrative_artifact=object(),
        key=base.key,
    )
    calls: list[int] = []
    _install_stream(monkeypatch, (candidate,), calls=calls)
    validated: list[object] = []

    async def exact(*_args: object, **kwargs: object) -> object:
        validated.append(kwargs["dependencies"])
        return SimpleNamespace(
            canonical_path=base.publication.canonical_path,
            indexable=False,
        )

    monkeypatch.setattr(service, "_resolve_exact_v3", exact)
    scan = await service.scan_public_sitemap(
        object(), chunk_size=10, chunk_number=1
    )
    assert len(validated) == 1
    assert scan.eligible_count == 0 and scan.entries == ()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "terminal_error",
    (service.PublicH2Pending("pending"), service.PublicH2Failed("failed")),
    ids=("pending", "failed"),
)
async def test_nonready_assigned_h2_is_omitted_and_scan_continues_without_h1_fallback(
    monkeypatch: pytest.MonkeyPatch,
    terminal_error: Exception,
) -> None:
    assigned_base = _h1_candidate(3)
    assigned = PublicSitemapCandidate(
        subject=assigned_base.subject,
        assignment=SimpleNamespace(presentation_contract="company_public_h2_v1"),
        pin=SimpleNamespace(
            projection_scope="active_publication",
            published_lastmod=_LASTMOD,
        ),
        report=assigned_base.report,
        publication=assigned_base.publication,
        presentation=object(),
        narrative_job=object(),
        narrative_artifact=object(),
        key=assigned_base.key,
    )
    later_h1 = _h1_candidate(4)
    calls: list[int] = []
    _install_stream(monkeypatch, (assigned, later_h1), calls=calls)
    h1_subjects: list[str] = []

    async def exact(*_args: object, **_kwargs: object) -> object:
        raise terminal_error

    def validate(page: object) -> object:
        h1_subjects.append(page.subject.normalized_identifier)
        return SimpleNamespace(
            canonical_path=page.publication.canonical_path,
            indexable=True,
        )

    monkeypatch.setattr(service, "_resolve_exact_v3", exact)
    monkeypatch.setattr(service, "validate_active_publication", validate)
    scan = await service.scan_public_sitemap(
        object(), chunk_size=10, chunk_number=1
    )

    assert scan.eligible_count == 1
    assert tuple(entry.canonical_path for entry in scan.entries) == (
        later_h1.publication.canonical_path,
    )
    assert h1_subjects == [later_h1.subject.normalized_identifier]


@pytest.mark.asyncio
async def test_assigned_h2_sitemap_storage_error_aborts_scan(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    base = _h1_candidate(5)
    assigned = PublicSitemapCandidate(
        subject=base.subject,
        assignment=SimpleNamespace(presentation_contract="company_public_h2_v1"),
        pin=SimpleNamespace(
            projection_scope="active_publication",
            published_lastmod=_LASTMOD,
        ),
        report=base.report,
        publication=base.publication,
        presentation=object(),
        narrative_job=object(),
        narrative_artifact=object(),
        key=base.key,
    )
    calls: list[int] = []
    _install_stream(monkeypatch, (assigned,), calls=calls)

    async def exact(*_args: object, **_kwargs: object) -> object:
        raise SQLAlchemyError("storage unavailable")

    monkeypatch.setattr(service, "_resolve_exact_v3", exact)
    with pytest.raises(SQLAlchemyError, match="storage unavailable"):
        await service.scan_public_sitemap(
            object(), chunk_size=10, chunk_number=1
        )
