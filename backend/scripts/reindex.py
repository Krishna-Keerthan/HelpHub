"""Rebuild the Elasticsearch copy from Postgres (runtime role only).

    uv run python scripts/reindex.py --all                 # new versioned index + alias swap
    uv run python scripts/reindex.py --tenant <uuid>       # all READY documents of a tenant
    uv run python scripts/reindex.py --tenant <uuid> --document <uuid>

Idempotent. Backfills documents whose search_index_status is PENDING or FAILED.
"""

import argparse
import asyncio
import sys
import uuid

from app.services import reindex
from app.services.es_client import close_es, get_es


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--all", action="store_true", help="rebuild everything")
    parser.add_argument("--tenant", type=uuid.UUID)
    parser.add_argument("--document", type=uuid.UUID, help="needs --tenant")
    parser.add_argument(
        "--allow-partial",
        action="store_true",
        help="with --all: swap the alias even if some documents failed",
    )
    args = parser.parse_args(argv)
    if args.all == bool(args.tenant) or (args.all and args.document):
        parser.error("use exactly one of --all or --tenant [--document]")
    if args.document and not args.tenant:
        parser.error("--document needs --tenant")
    return args


async def main(args: argparse.Namespace) -> int:
    es = get_es()
    try:
        if args.all:
            summary = await reindex.reindex_all(es, allow_partial=args.allow_partial)
        elif args.document:
            ok = await reindex.reindex_document(es, args.tenant, args.document)
            summary = reindex.ReindexSummary(1, int(ok), int(not ok))
        else:
            summary = await reindex.reindex_tenant(es, args.tenant)
    except reindex.ReindexIncompleteError as exc:
        print(f"aborted, alias not swapped: {exc}", file=sys.stderr)
        return 3
    finally:
        await close_es()
    print(
        f"documents={summary.documents} indexed={summary.indexed} failed={summary.failed}"
    )
    return 1 if summary.failed else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main(parse_args())))
