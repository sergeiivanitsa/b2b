from __future__ import annotations

import asyncio
from uuid import UUID

import pytest
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from product_api.company_reports import public_document_service
from product_api.company_reports.company_card_v2.public_h2_asset_manifest import (
    load_public_h2_asset_manifest,
)
from product_api.company_reports.company_card_v2.rollout import run_rollout_mutation
from product_api.company_reports.persistence.models import (
    CompanyCardNarrativeArtifact,
)
from product_api.company_reports.public_document_service import scan_public_sitemap
from product_api.routers.company_reports_public import set_public_h2_asset_manifest
from tests_support.iteration25_rollout import (
    RELEASE_SHA,
    build_activation_decision,
    load_acceptance_seeder,
    prepare_unassigned_acceptance_seed,
    with_database_url,
)


@pytest.mark.asyncio
async def test_iteration25_seeded_postgres_rows_resolve_through_real_product_http(
    engine,
    db_url: str,
    async_client,
) -> None:
    seeder = load_acceptance_seeder()
    profiles = seeder.load_profile_registry()
    counts = await seeder.seed_database(db_url, profiles, release_sha=RELEASE_SHA)
    manifest = seeder.build_e2e_manifest(profiles, release_sha=RELEASE_SHA)
    set_public_h2_asset_manifest(load_public_h2_asset_manifest())

    assert counts == {
        "subjects": 5,
        "reports": 10,
        "pins": 20,
        "assignments": 5,
        "journal": 5,
        "decisions": 1,
    }
    assert [profile["profile_id"] for profile in manifest["profiles"]] == list(
        seeder.PROFILE_IDS
    )
    for profile in profiles:
        response = await async_client.get(profile["canonical_path"])
        assert response.status_code == 200
        assert response.headers["x-robots-tag"] == "noindex,follow"
        assert profile["h2_report_id"] in response.text
        for expected in profile["expected_visible_text"]:
            assert expected in response.text
        for forbidden in profile["forbidden_visible_text"]:
            assert forbidden not in response.text

        head = await async_client.head(profile["canonical_path"])
        assert head.status_code == 200
        assert head.headers["x-robots-tag"] == "noindex,follow"
        assert head.content == b""

        wrong_slug = await async_client.get(profile["wrong_slug_path"])
        assert wrong_slug.status_code == 301
        assert wrong_slug.headers["location"] == profile["canonical_path"]
        assert wrong_slug.headers["x-robots-tag"] == "noindex,follow"

    sitemap_index = await async_client.get(manifest["routes"]["sitemap_index_path"])
    assert sitemap_index.status_code == 200
    assert "/sitemaps/1.xml" not in sitemap_index.text
    sitemap_chunk = await async_client.get("/sitemaps/1.xml")
    assert sitemap_chunk.status_code == 404
    assert sitemap_chunk.headers["x-robots-tag"] == "noindex,follow"


@pytest.mark.asyncio
async def test_sitemap_real_postgres_repeatable_read_then_excludes_late_corruption(
    engine,
    db_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    profiles = await prepare_unassigned_acceptance_seed(engine, db_url)
    selected = profiles[:2]
    activation, config = await build_activation_decision(
        engine,
        selected,
        decision_id="25000000-0000-4000-8000-000000000201",
        indexable=True,
    )
    applied = await run_rollout_mutation(
        activation,
        with_database_url(config, db_url),
        mode="apply",
        confirm_digest=activation.decision_digest,
    )
    assert [result.code for result in applied.results] == ["applied", "applied"]

    original_fetch = public_document_service.fetch_public_sitemap_candidate_window
    first_window_loaded = asyncio.Event()
    release_reader = asyncio.Event()
    fetches = 0

    async def blocked_after_first_window(session, *, after, limit):
        nonlocal fetches
        rows = await original_fetch(session, after=after, limit=limit)
        fetches += 1
        if fetches == 1:
            first_window_loaded.set()
            await release_reader.wait()
        return rows

    monkeypatch.setattr(
        public_document_service,
        "fetch_public_sitemap_candidate_window",
        blocked_after_first_window,
    )

    async def read_before_view():
        async with AsyncSession(bind=engine, expire_on_commit=False) as session:
            return await scan_public_sitemap(
                session,
                chunk_size=10,
                chunk_number=1,
                validation_window_size=1,
            )

    reader = asyncio.create_task(read_before_view())
    try:
        await asyncio.wait_for(first_window_loaded.wait(), timeout=5)
        async with AsyncSession(bind=engine, expire_on_commit=False) as writer:
            async with writer.begin():
                await writer.execute(
                    update(CompanyCardNarrativeArtifact)
                    .where(
                        CompanyCardNarrativeArtifact.report_id
                        == UUID(selected[1]["h2_report_id"])
                    )
                    .values(rendered_output_bytes_sha256="0" * 64)
                )
        release_reader.set()
        before = await asyncio.wait_for(reader, timeout=10)
    finally:
        release_reader.set()
        if not reader.done():
            reader.cancel()
            with pytest.raises(asyncio.CancelledError):
                await reader

    assert before.eligible_count == 2
    assert [entry.canonical_path for entry in before.entries] == [
        profile["canonical_path"] for profile in selected
    ]

    async with AsyncSession(bind=engine, expire_on_commit=False) as session:
        after = await scan_public_sitemap(
            session,
            chunk_size=10,
            chunk_number=1,
            validation_window_size=1,
        )
    assert after.eligible_count == 1
    assert [entry.canonical_path for entry in after.entries] == [
        selected[0]["canonical_path"]
    ]
