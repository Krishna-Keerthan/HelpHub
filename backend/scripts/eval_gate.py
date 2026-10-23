"""Retrieval-gate evaluation (docs/eval/protocol.md): embed, dev, test.

  embed  Load the eval corpus into the dedicated eval tenant with the production
         embedding provider (EMBEDDING_PROVIDER=cloudflare). Idempotent; counts only.
  dev    Features and the R0/R1 sweep on DEV questions only; writes
         docs/eval/dev_tuning.json with the chosen rule. Never touches TEST.
  test   Applies the chosen rule once to TEST; writes docs/eval/test_result.json.
         Refuses if that file exists (it is the lock).

Run from backend/:  EMBEDDING_PROVIDER=cloudflare uv run python scripts/eval_gate.py dev
Never prints keys or document text.
"""

import argparse
import asyncio
import json
import secrets
import sys
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:  # run as a script: make `eval` importable
    sys.path.insert(0, str(BACKEND))

from eval import gate_tuning as gt
from eval.validate import EVAL_DIR, load_questions

DOCS_EVAL = BACKEND.parent / "docs" / "eval"
DEV_TUNING = DOCS_EVAL / "dev_tuning.json"
TEST_RESULT = DOCS_EVAL / "test_result.json"
QUESTIONS = EVAL_DIR / "questions.yaml"
CANDIDATES = EVAL_DIR / "unanswerable_candidates.json"
DECISIONS = EVAL_DIR / "unanswerable_decisions.json"
EVAL_SLUG = "eval-cloudflare"
EXPECTED_MODEL = "@cf/baai/bge-small-en-v1.5"
TOP_K = 5

Searcher = Callable[[str], Awaitable[list[gt.HitFeatures]]]


@dataclass(frozen=True)
class Question:
    qid: str
    split: str
    answerable: bool
    text: str


def load_split(
    split: str,
    questions: Path = QUESTIONS,
    candidates: Path = CANDIDATES,
    decisions: Path = DECISIONS,
) -> list[Question]:
    """The answerable questions of ``split`` plus the kept unanswerables of ``split``.

    The 8 older unanswerables in questions.yaml are excluded (Amendment 1). Rows of
    the other split are dropped here, so callers never hold them.
    """
    out = [
        Question(r["id"], r["split"], True, r["question"])
        for r in load_questions(questions)
        if r["answerable"] and r["split"] == split
    ]
    stays = {
        d["id"]
        for d in json.loads(decisions.read_text())["decisions"]
        if d["decision"] == "stays"
    }
    cand = json.loads(candidates.read_text())["questions"]
    out += [
        Question(c["id"], c["split"], False, c["question"])
        for c in cand
        if c["id"] in stays and c["split"] == split
    ]
    return out


async def compute_features(
    questions: Sequence[Question], searcher: Searcher
) -> list[gt.QuestionFeatures]:
    return [
        gt.QuestionFeatures(q.qid, q.split, q.answerable, tuple(await searcher(q.text)))
        for q in questions
    ]


def _cell(s: gt.Scored) -> str:
    return f"A={s.wrongly_refused}/{s.n_answerable} U={s.wrongly_answered}/{s.n_unanswerable}"


def render_table(r0: Sequence[gt.Scored], r1: Sequence[gt.Scored]) -> str:
    lines = ["R0 (t): A_dev, U_dev"]
    lines += [f"  t={x.rule.t:.2f}  {_cell(x)}" for x in r0]
    lines.append("R1 (best s per t; full grid in dev_tuning.json): A_dev, U_dev")
    for t in gt.T_GRID:
        row = [x for x in r1 if x.rule.t == t]
        best = min(row, key=lambda x: (x.worst, -x.rule.s))
        lines.append(f"  t={t:.2f} s={best.rule.s:.2f}  {_cell(best)}")
    return "\n".join(lines)


def dev_command(
    searcher: Searcher,
    *,
    out: Path = DEV_TUNING,
    questions: Path = QUESTIONS,
    candidates: Path = CANDIDATES,
    decisions: Path = DECISIONS,
    model: str = EXPECTED_MODEL,
) -> gt.Scored:
    dev = load_split("dev", questions, candidates, decisions)
    items = asyncio.run(compute_features(dev, searcher))
    r0, r1 = gt.sweep(items)
    chosen = gt.choose(r0, r1)
    print(render_table(r0, r1))
    print(f"chosen: {gt.to_json(chosen)}")
    out.write_text(
        json.dumps(
            {
                "embedding_model": model,
                "chosen": gt.to_json(chosen),
                "r0": [gt.to_json(x) for x in r0],
                "r1": [gt.to_json(x) for x in r1],
                "features": gt.features_to_json(items),
            },
            indent=2,
        )
        + "\n"
    )
    return chosen


def test_command(
    searcher: Searcher,
    *,
    tuning: Path = DEV_TUNING,
    result: Path = TEST_RESULT,
    questions: Path = QUESTIONS,
    candidates: Path = CANDIDATES,
    decisions: Path = DECISIONS,
    model: str = EXPECTED_MODEL,
) -> dict[str, Any]:
    gt.refuse_if_test_done(result)  # before anything is loaded or embedded
    tuned = json.loads(tuning.read_text())
    if tuned["embedding_model"] != model:
        raise SystemExit(
            "dev_tuning.json was produced with a different embedding model"
        )
    rule = gt.rule_from_json(tuned["chosen"])
    test = load_split("test", questions, candidates, decisions)
    items = asyncio.run(compute_features(test, searcher))
    scored = gt.score(rule, items)
    payload = {
        "embedding_model": model,
        "rule": gt.to_json(scored),
        "A_test": f"{scored.wrongly_refused}/{scored.n_answerable}",
        "U_test": f"{scored.wrongly_answered}/{scored.n_unanswerable}",
        "passes": scored.a <= gt.Fraction(15, 100) and scored.u <= gt.Fraction(15, 100),
        "features": gt.features_to_json(items),
    }
    gt.write_test_result(result, payload)
    return payload


# --- database-backed pieces (not used by the unit tests) --------------------------------


async def _eval_tenant_id() -> Any:
    from app.services import auth

    tenant_id = await auth.tenant_id_for_slug(EVAL_SLUG)
    if tenant_id is None:
        raise SystemExit("eval tenant missing: run the embed command first")
    return tenant_id


def real_searcher() -> Searcher:
    from app.core.config import settings
    from app.services.embeddings import default_provider
    from app.services.search import search

    if settings.embedding_provider != "cloudflare":
        raise SystemExit("EMBEDDING_PROVIDER must be cloudflare for the measurement")
    provider = default_provider()
    if provider.model_name != EXPECTED_MODEL:
        raise SystemExit("unexpected embedding model")
    tenant: list[Any] = []

    async def searcher(query: str) -> list[gt.HitFeatures]:
        if not tenant:
            tenant.append(await _eval_tenant_id())
        titled = await search(tenant[0], query, TOP_K, provider, "hybrid")
        return [
            gt.HitFeatures(
                t.hit.score if t.hit.score is not None else float("-inf"),
                t.hit.text_score,
            )
            for t in titled
        ]

    return searcher


async def corpus_texts() -> list[tuple[str, str]]:
    """(title, text) per corpus file, as scripts/load_demo_corpus.py and the app see it.

    Whole file through the app's own extraction (title = file stem); nothing is
    stripped, so the ``# Title`` line stays.
    """
    from app.services import extraction

    files = sorted(
        p for p in (EVAL_DIR / "corpus").glob("*.md") if p.name != "INDEX.md"
    )
    return [
        (p.stem, await extraction.extract_text(p.name, p.read_bytes())) for p in files
    ]


async def ingest_corpus(tenant_id: Any, provider: Any) -> int:
    """Idempotent: ingest every corpus file through the app's service path and
    delete documents in the tenant that are not a corpus file. Returns the stale count."""
    from app.services import documents

    corpus = await corpus_texts()
    wanted = {documents.content_hash(documents.prepare_text(t)) for _, t in corpus}
    stale = 0
    for doc in await documents.list_documents(tenant_id, limit=200):
        if doc.content_hash not in wanted:
            await documents.delete_document(tenant_id, doc.id)
            stale += 1
    for title, content in corpus:
        document, _ = await documents.create_or_get(tenant_id, None, title, content)  # type: ignore[arg-type]
        await documents.ingest_document(tenant_id, document.id, provider)
    return stale


async def embed_corpus() -> dict[str, int]:
    from sqlalchemy import text

    from app.core.config import settings
    from app.db.session import engine
    from app.db.tenant_context import tenant_transaction
    from app.schemas.auth import RegisterRequest
    from app.services import auth
    from app.services.embeddings import default_provider

    if settings.embedding_provider != "cloudflare":
        raise SystemExit("EMBEDDING_PROVIDER must be cloudflare")
    provider = default_provider()
    tenant_id = await auth.tenant_id_for_slug(EVAL_SLUG)
    created = tenant_id is None
    if tenant_id is None:
        user = await auth.create_tenant_with_admin(
            RegisterRequest(
                tenant_name="Eval (cloudflare)",
                tenant_slug=EVAL_SLUG,
                email="eval@example.com",
                password=secrets.token_urlsafe(24),
            ),
            reserved_ok=True,
        )
        tenant_id = user.tenant_id
    stale = await ingest_corpus(tenant_id, provider)
    async with tenant_transaction(tenant_id) as session:
        rows = (
            await session.execute(
                text(
                    "SELECT embedding_model, count(*), count(DISTINCT document_id) "
                    "FROM chunks GROUP BY 1"
                )
            )
        ).all()
    await engine.dispose()
    return (
        {"tenant_created": int(created), "stale_documents_deleted": stale}
        | {f"{m}: chunks": c for m, c, _ in rows}
        | {f"{m}: documents": d for m, _, d in rows}
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("command", choices=["embed", "dev", "test"])
    args = parser.parse_args(argv)
    if args.command == "embed":
        print(asyncio.run(embed_corpus()))
    elif args.command == "dev":
        dev_command(real_searcher())
    else:
        gt.refuse_if_test_done(TEST_RESULT)
        print(test_command(real_searcher()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
