"""Markdown rendering of an evaluation run. Pure: records in, text out."""

import uuid
from collections import Counter
from collections.abc import Mapping, Sequence
from typing import Any

from eval import analysis, gate_rules
from eval.records import MODES, Record
from eval.stats import count_pct, wilson_interval

SPLITS = ("dev", "test")
RRF_KS = (10, 30, 60, 100)
CANDIDATES = (20, 50)
DEFAULT_SETTING = (60, 50)

LIMITATIONS = """\
- n = 40 author-written questions (24 dev / 16 test), written by the same person who built the corpus. Percentages are indicative, not precise; see the Wilson intervals.
- The corpus is synthetic (24 documents, one fictional company). Real tickets are messier.
- Each split has only 4 unanswerable questions, so every false-answer count rests on very few cases; gate results are indicative.
- Vector (cosine) and BM25 scores are not comparable (AR-11); only ranks enter RRF and the gate thresholds only vector cosine.
- HNSW recall is probabilistic (AR-15); vector numbers can differ slightly between builds of the index. Keyword numbers should not.
- Relevance is defined by exact evidence substrings; a chunk that answers the question without containing a listed snippet counts as a miss.
- Identifier tokens are extracted case-sensitively, so a code typed in lowercase gives R2 nothing to match.
- Latency is measured on one developer machine with the real embedding model, one query at a time.\
"""


def _row(cells: Sequence[Any]) -> str:
    return "| " + " | ".join(str(c) for c in cells) + " |"


def _table(header: Sequence[str], rows: Sequence[Sequence[Any]]) -> str:
    sep = _row(["---"] * len(header))
    return "\n".join([_row(header), sep, *(_row(r) for r in rows)])


def _pct(agg_count: int, n: int) -> str:
    return count_pct(agg_count, n)


def metrics_section(records: Sequence[Record]) -> str:
    out = ["## Retrieval metrics (answerable questions)", ""]
    out.append(
        "recall@5 = mean over questions of (distinct relevant chunks in the top 5) / (relevant chunks). "
        "MRR@10 = mean reciprocal rank of the first relevant chunk in the top 10."
    )
    categories = sorted({r.category for r in records if r.answerable})
    for split in SPLITS:
        out += ["", f"### {split}", ""]
        rows: list[list[Any]] = []
        for mode in MODES:
            for label, cat in [("ALL", None), *[(c, c) for c in categories]]:
                a = analysis.aggregate(records, mode, split=split, category=cat)
                if a.n == 0:
                    continue
                rows.append(
                    [
                        mode, label, a.n,
                        _pct(a.hit1, a.n), _pct(a.hit3, a.n), _pct(a.hit5, a.n),
                        f"{a.mrr:.3f}", f"{a.recall5:.3f}",
                    ]
                )  # fmt: skip
        out.append(
            _table(
                [
                    "mode",
                    "category",
                    "n",
                    "hit@1",
                    "hit@3",
                    "hit@5",
                    "MRR@10",
                    "recall@5",
                ],
                rows,
            )
        )
        out += ["", "Overall hit@5, Wilson 95% interval:", ""]
        wrows = []
        for mode in MODES:
            a = analysis.aggregate(records, mode, split=split)
            lo, hi = wilson_interval(a.hit5, a.n)
            wrows.append([mode, _pct(a.hit5, a.n), f"{lo:.0%} to {hi:.0%}"])
        out.append(_table(["mode", "hit@5", "95% interval"], wrows))
    fb = sum(1 for r in records if r.fallback)
    out += ["", f"Vector exact fallback fired for {fb} of {len(records)} questions."]
    return "\n".join(out)


def latency_section(records: Sequence[Record], warmups: int) -> str:
    table = analysis.latency_table(records)
    rows = [[m, n, f"{p50:.0f}", f"{p95:.0f}"] for m, (n, p50, p95) in table.items()]
    return "\n".join(
        [
            "## Latency (ms)",
            "",
            (
                f"{warmups} warm-up queries discarded. vector includes the query embedding; "
                "keyword has none; hybrid includes the embedding plus both branches in "
                "parallel. Real FastEmbed model."
            ),
            "",
            _table(["mode", "n", "p50", "p95"], rows),
        ]
    )


def integrity_section(checks: Mapping[str, list[str]]) -> str:
    rows = [
        [name, "PASS" if not p else "FAIL: " + "; ".join(p[:3])]
        for name, p in checks.items()
    ]
    return "\n".join(["## Integrity checks", "", _table(["check", "result"], rows)])


def _snippet(chunk_id: uuid.UUID, contents: Mapping[uuid.UUID, str]) -> str:
    text = contents[chunk_id][:100].replace("\n", " ").replace("|", "/")
    return f"`{str(chunk_id)[:8]}` {text}"


def failures_section(
    records: Sequence[Record], contents: Mapping[uuid.UUID, str]
) -> str:
    out = ["## Failure list"]
    for split in SPLITS:
        bad = analysis.failures(records, split)
        none = analysis.never_retrieved(records, split)
        out += [
            "",
            f"### {split}: hybrid hit@5 worse than the better single mode ({len(bad)})",
            "",
        ]
        for r in bad:
            out.append(f"- **{r.id}** ({r.category}): {r.question}")
            for mode in MODES:
                tops = "; ".join(_snippet(i, contents) for i in r.modes[mode].ids[:3])
                out.append(f"  - {mode}: {tops}")
        out += [
            "",
            f"### {split}: answerable questions no mode retrieved in the top 5 ({len(none)})",
            "",
        ]
        out += [f"- **{r.id}** ({r.category}): {r.question}" for r in none] or [
            "- none"
        ]
    return "\n".join(out)


def _rt(a: int, b: int) -> str:
    return f"{a}/{b}"


def gate_section(
    records: Sequence[Record], contents: Mapping[uuid.UUID, str]
) -> tuple[str, dict[str, Any]]:
    items = {s: analysis.gate_items(records, contents, s) for s in SPLITS}
    results = {s: gate_rules.sweep(items[s]) for s in SPLITS}
    choice = gate_rules.choose(results["dev"])
    out = [
        "## Gate analysis (closes AR-10)",
        "",
        "R1: answer iff best vector cosine >= T. R2: R1 OR an identifier-like token of the query occurs "
        "(case-insensitively) in a top-5 hybrid hit. False refusal = answerable question refused; "
        "false answer = unanswerable question answered. Counts are over "
        + ", ".join(
            f"{s}: {results[s][0].n_answerable} answerable / {results[s][0].n_unanswerable} unanswerable"
            for s in SPLITS
        )
        + ".",
    ]
    for split in SPLITS:
        out += ["", f"### {split}", ""]
        rows = []
        for g in results[split]:
            cats = " ".join(
                f"{c}:{r}/{a}" for c, (r, a) in g.by_category.items() if r or a
            )
            rows.append(
                [
                    g.rule,
                    f"{g.threshold:.2f}",
                    _rt(g.false_refusals, g.n_answerable),
                    _rt(g.false_answers, g.n_unanswerable),
                    cats or "-",
                ]
            )
        out.append(
            _table(
                [
                    "rule",
                    "T",
                    "false refusals",
                    "false answers",
                    "by category (refusals/answers)",
                ],
                rows,
            )
        )
    rec: dict[str, Any] = {}
    out += ["", "### Recommendation (chosen on dev only)", ""]
    out.append(
        "Rule: minimise dev false refusals subject to at most 1 dev false answer; among tied thresholds take the "
        "middle of the longest contiguous plateau (upper middle when even); equal plateaus prefer R1, then larger T."
    )
    if choice is None:
        out += ["", "No (rule, T) satisfies the constraint on dev."]
    else:
        pick = {
            s: next(
                g
                for g in results[s]
                if g.rule == choice.rule and g.threshold == choice.threshold
            )
            for s in SPLITS
        }
        rec = {
            "rule": choice.rule,
            "threshold": choice.threshold,
            "plateau": [choice.low, choice.high],
        }
        out += [
            "",
            f"**{choice.rule}, T = {choice.threshold:.2f}** (plateau {choice.low:.2f} to {choice.high:.2f}, {choice.plateau_steps} steps).",
            "",
            _table(
                ["split", "false refusals", "false answers"],
                [
                    [
                        s,
                        _rt(pick[s].false_refusals, pick[s].n_answerable),
                        _rt(pick[s].false_answers, pick[s].n_unanswerable),
                    ]
                    for s in SPLITS
                ],
            ),
            "",
            "Test numbers are reported without re-tuning. min_retrieval_score is NOT changed; Day 7 implements the gate.",
        ]
        rec["answered_unanswerable"] = [
            q for s in SPLITS for q in pick[s].wrongly_answered_ids
        ]
    out += ["", "### Identifier-like tokens in near_miss / off_topic questions", ""]
    rows = []
    for r in records:
        if r.category not in ("near_miss", "off_topic"):
            continue
        tokens = gate_rules.identifier_tokens(r.question)
        if not tokens:
            continue
        it = next(i for i in items[r.split] if i.qid == r.id)
        answered = (
            "n/a" if choice is None else gate_rules.answers("R2", choice.threshold, it)
        )
        rows.append(
            [r.id, r.split, r.category, ", ".join(tokens), f"R2 answered: {answered}"]
        )
    out.append(
        _table(["id", "split", "category", "tokens", "R2 at chosen T"], rows)
        if rows
        else "None of them contains an identifier-like token."
    )
    return "\n".join(out), rec


def ablation_section(records: Sequence[Record]) -> tuple[str, tuple[int, int]]:
    dev: dict[analysis.Setting, int] = {}
    test: dict[analysis.Setting, int] = {}
    for k in RRF_KS:
        for c in CANDIDATES:
            dev[(k, c)] = analysis.ablation_hits(records, "dev", k, c)
            test[(k, c)] = analysis.ablation_hits(records, "test", k, c)
    decision = analysis.decide_ablation(dev, test, DEFAULT_SETTING)
    n_dev = analysis.aggregate(records, "hybrid", split="dev").n
    n_test = analysis.aggregate(records, "hybrid", split="test").n
    rows = [
        [k, c, _rt(dev[(k, c)], n_dev), _rt(test[(k, c)], n_test)] for (k, c) in dev
    ]
    verdict = (
        "Keep rrf_k=60, candidates=50 (no setting improves dev hit@5 by at least 2 questions with test not worse)."
        if decision == DEFAULT_SETTING
        else f"Change to rrf_k={decision[0]}, candidates={decision[1]}."
    )
    text = "\n".join(
        [
            "## Ablations (hybrid hit@5, answerable)",
            "",
            (
                "candidates=20 is approximated by truncating the recorded 50-candidate "
                "branch lists to their first 20 and re-fusing. Choices use dev; test is "
                "only the do-not-get-worse check."
            ),
            "",
            _table(
                ["rrf_k", "candidates", "dev hit@5", "test hit@5 (check only)"], rows
            ),
            "",
            f"**Decision:** {verdict}",
        ]
    )
    return text, decision


def env_section(env: Mapping[str, Any]) -> str:
    return "\n".join(["## Environment", "", *(f"- {k}: {v}" for k, v in env.items())])


def counts_section(records: Sequence[Record], n_docs: int, n_chunks: int) -> str:
    cats = sorted({r.category for r in records})
    rows = [
        [
            c,
            *[
                sum(1 for r in records if r.category == c and r.split == s)
                for s in SPLITS
            ],
        ]
        for c in cats
    ]
    rows.append(["total", *[sum(1 for r in records if r.split == s) for s in SPLITS]])
    total_unans = Counter(r.split for r in records if not r.answerable)
    return "\n".join(
        [
            "## Corpus and questions",
            "",
            f"{n_docs} documents, {n_chunks} chunks, {len(records)} questions (unanswerable: dev {total_unans['dev']}, test {total_unans['test']}).",
            "",
            _table(["category", "dev", "test"], rows),
        ]
    )


def render(
    *,
    date: str,
    env: Mapping[str, Any],
    records: Sequence[Record],
    contents: Mapping[uuid.UUID, str],
    n_docs: int,
    checks: Mapping[str, list[str]],
    warmups: int,
    with_ablation: bool,
) -> tuple[str, dict[str, Any]]:
    gate_text, rec = gate_section(records, contents)
    parts = [
        f"# Retrieval evaluation\n\nGenerated {date}. Retrieval only; no LLM is called.",
        env_section(env),
        counts_section(records, n_docs, len(contents)),
        metrics_section(records),
        latency_section(records, warmups),
        integrity_section(checks),
        failures_section(records, contents),
        gate_text,
    ]
    decision: tuple[int, int] | None = None
    if with_ablation:
        text, decision = ablation_section(records)
        parts.append(text)
    parts.append("## Limitations\n\n" + LIMITATIONS)
    extra = {"gate_recommendation": rec, "ablation_decision": decision}
    return "\n\n".join(parts) + "\n", extra
