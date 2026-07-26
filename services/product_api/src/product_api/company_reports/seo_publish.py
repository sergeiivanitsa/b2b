"""Manual bounded SEO publication CLI; it never contacts providers or AI."""
from __future__ import annotations

import argparse
import asyncio
from uuid import UUID

from product_api.company_reports.persistence.publications import (
    PublicationStateConflictError,
    create_batch,
    process_batch,
    set_batch_state,
    set_publication_control,
)
from product_api.db.session import AsyncSessionMaker
from product_api.settings import get_settings


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Controlled CompanyReport SEO publication")
    commands = parser.add_subparsers(dest="command", required=True)
    control = commands.add_parser("control")
    control.add_argument("state", choices=("pause", "resume"))
    run = commands.add_parser("run")
    run.add_argument("--limit", type=int, required=True)
    batch = commands.add_parser("batch")
    batch.add_argument("state", choices=("pause", "resume"))
    batch.add_argument("--batch-id", type=UUID, required=True)
    return parser


async def _run(args: argparse.Namespace) -> int:
    settings = get_settings()
    batch_id = None
    async with AsyncSessionMaker() as session:
        try:
            async with session.begin():
                if args.command == "control":
                    await set_publication_control(session, state="active" if args.state == "resume" else "paused", enabled=settings.seo_public_rollout_enabled)
                elif args.command == "batch":
                    batch = await set_batch_state(session, batch_id=args.batch_id, state="running" if args.state == "resume" else "paused", enabled=settings.seo_public_rollout_enabled)
                    if args.state == "resume":
                        batch_id = batch.id
                else:
                    if not settings.seo_public_rollout_enabled:
                        raise PublicationStateConflictError("SEO_PUBLIC_ROLLOUT_ENABLED is required")
                    batch = await create_batch(session, limit=args.limit, max_limit=settings.seo_publish_batch_max_limit)
                    if batch.state == "running":
                        batch_id = batch.id
        except PublicationStateConflictError as exc:
            print(f"blocked: {exc}")
            return 2
    while batch_id is not None:
        async with AsyncSessionMaker() as session:
            async with session.begin():
                batch = await process_batch(session, batch_id=batch_id)
                if batch.state != "running":
                    batch_id = None
    return 0


def main(argv: list[str] | None = None) -> int:
    return asyncio.run(_run(_parser().parse_args(argv)))


if __name__ == "__main__":
    raise SystemExit(main())
