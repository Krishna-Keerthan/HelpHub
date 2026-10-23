"""Gate tuning (eval/gate_tuning.py, scripts/eval_gate.py): sweep, selection, TEST lock, DEV/TEST separation."""

import importlib.util
import json
from fractions import Fraction
from pathlib import Path

import pytest

from eval import gate_tuning as gt

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "eval_gate.py"
spec = importlib.util.spec_from_file_location("eval_gate", SCRIPT)
assert spec and spec.loader
eg = importlib.util.module_from_spec(spec)
spec.loader.exec_module(eg)


def q(
    qid: str, answerable: bool, *hits: tuple[float, float | None], split: str = "dev"
):
    return gt.QuestionFeatures(
        qid, split, answerable, tuple(gt.HitFeatures(c, s) for c, s in hits)
    )


def test_grids_are_the_protocol_grids() -> None:
    assert len(gt.T_GRID) == 31 and gt.T_GRID[0] == 0.50 and gt.T_GRID[-1] == 0.80
    assert len(gt.S_GRID) == 11 and gt.S_GRID[0] == 0.0 and gt.S_GRID[-1] == 0.50


def test_rule_needs_one_hit_to_satisfy_both_conditions() -> None:
    hits = (gt.HitFeatures(0.70, 0.0), gt.HitFeatures(0.50, 0.40))
    # cosine and text_score are on different hits: R1 refuses, R0 answers
    assert gt.answers(gt.Rule("R0", 0.65), hits)
    assert not gt.answers(gt.Rule("R1", 0.65, 0.30), hits)
    assert gt.answers(gt.Rule("R1", 0.50, 0.30), hits)


def test_null_text_score_counts_as_zero_and_s_zero_equals_r0() -> None:
    hits = (gt.HitFeatures(0.70, None),)
    assert gt.answers(gt.Rule("R1", 0.70, 0.0), hits)
    assert not gt.answers(gt.Rule("R1", 0.70, 0.05), hits)
    assert not gt.answers(gt.Rule("R0", 0.71), hits)  # boundary is >=


def test_score_counts_with_denominators() -> None:
    items = [
        q("a1", True, (0.8, 0.1)),
        q("a2", True, (0.55, 0.1)),
        q("u1", False, (0.7, 0.0)),
        q("u2", False, (0.4, 0.0)),
    ]
    s = gt.score(gt.Rule("R0", 0.6), items)
    assert (s.wrongly_refused, s.n_answerable) == (1, 2)
    assert (s.wrongly_answered, s.n_unanswerable) == (1, 2)
    assert s.worst == Fraction(1, 2)


def test_sweep_sizes_and_monotone_r0() -> None:
    r0, r1 = gt.sweep([q("a", True, (0.7, 0.2)), q("u", False, (0.6, 0.0))])
    assert len(r0) == 31 and len(r1) == 31 * 10
    assert all(x.rule.s > 0 for x in r1)
    refusals = [x.wrongly_refused for x in r0]
    assert refusals == sorted(refusals)  # raising t never un-refuses


def test_r0_tie_goes_to_higher_t() -> None:
    # perfect separation for every t in (0.60, 0.70]
    items = [q("a", True, (0.70, 0.0)), q("u", False, (0.60, 0.0))]
    r0, r1 = gt.sweep(items)
    chosen = gt.choose(r0, r1)
    assert chosen.rule == gt.Rule("R0", 0.70)
    assert chosen.worst == 0


def test_r1_chosen_only_if_strictly_better() -> None:
    # R0 cannot separate (the unanswerable has the higher cosine); the text score can
    items = [q("a", True, (0.70, 0.30)), q("u", False, (0.75, 0.0))]
    r0, r1 = gt.sweep(items)
    chosen = gt.choose(r0, r1)
    assert chosen.rule.name == "R1" and chosen.worst == 0
    # t ties go high: 0.70 is the highest t that still answers "a"; then the highest s <= 0.30
    assert (chosen.rule.t, chosen.rule.s) == (0.70, 0.30)


def test_r1_equal_to_r0_keeps_r0() -> None:
    items = [q("a", True, (0.70, 0.40)), q("u", False, (0.60, 0.0))]
    r0, r1 = gt.sweep(items)
    assert gt.choose(r0, r1).rule == gt.Rule("R0", 0.70)


def test_r1_tie_prefers_higher_t_then_higher_s() -> None:
    r0 = [gt.Scored(gt.Rule("R0", 0.6), 1, 2, 1, 2)]
    r1 = [
        gt.Scored(gt.Rule("R1", 0.60, 0.40), 0, 2, 0, 2),
        gt.Scored(gt.Rule("R1", 0.70, 0.10), 0, 2, 0, 2),
        gt.Scored(gt.Rule("R1", 0.70, 0.20), 0, 2, 0, 2),
    ]
    assert gt.choose(r0, r1).rule == gt.Rule("R1", 0.70, 0.20)


def test_compare_uses_exact_fractions() -> None:
    # 1/3 vs 2/6 are equal, not "better" through float noise
    r0 = [gt.Scored(gt.Rule("R0", 0.6), 1, 3, 0, 3)]
    r1 = [gt.Scored(gt.Rule("R1", 0.6, 0.1), 0, 3, 2, 6)]
    assert gt.choose(r0, r1).rule.name == "R0"


# --- runner: DEV/TEST separation and the TEST lock -------------------------------------


def _write_fixture(tmp_path: Path) -> dict[str, Path]:
    rows = []
    for i, split in enumerate(["dev", "dev", "test", "test"]):
        rows.append(
            {
                "id": f"q-{i}",
                "split": split,
                "category": "code",
                "answerable": True,
                "question": f"{split} answerable {i}",
                "evidence": ["x"],
            }
        )
    rows.append(  # an old unanswerable in questions.yaml: excluded
        {
            "id": "old-1",
            "split": "dev",
            "category": "off_topic",
            "answerable": False,
            "question": "dev old unanswerable",
            "evidence": [],
        }
    )
    qy = tmp_path / "questions.yaml"
    qy.write_text(json.dumps(rows))  # JSON is valid YAML
    cand = [
        {"id": "u-1", "split": "dev", "question": "dev kept u", "answerable": False},
        {"id": "u-2", "split": "test", "question": "test kept u", "answerable": False},
        {"id": "u-3", "split": "dev", "question": "dev removed u", "answerable": False},
    ]
    (tmp_path / "cand.json").write_text(json.dumps({"questions": cand}))
    dec = [
        {"id": "u-1", "decision": "stays"},
        {"id": "u-2", "decision": "stays"},
        {"id": "u-3", "decision": "removed"},
    ]
    (tmp_path / "dec.json").write_text(json.dumps({"decisions": dec}))
    return {
        "questions": qy,
        "candidates": tmp_path / "cand.json",
        "decisions": tmp_path / "dec.json",
    }


class Recorder:
    def __init__(self) -> None:
        self.queries: list[str] = []

    async def __call__(self, query: str) -> list[gt.HitFeatures]:
        self.queries.append(query)
        return [gt.HitFeatures(0.7 if "answerable" in query else 0.6, 0.1)]


def test_load_split_keeps_only_that_split_and_kept_unanswerables(
    tmp_path: Path,
) -> None:
    paths = _write_fixture(tmp_path)
    dev = eg.load_split("dev", **paths)
    assert sorted(x.qid for x in dev) == ["q-0", "q-1", "u-1"]
    assert {x.split for x in dev} == {"dev"}
    test = eg.load_split("test", **paths)
    assert sorted(x.qid for x in test) == ["q-2", "q-3", "u-2"]


def test_dev_command_never_sees_or_writes_test(tmp_path: Path) -> None:
    paths = _write_fixture(tmp_path)
    rec = Recorder()
    out = tmp_path / "dev_tuning.json"
    eg.dev_command(rec, out=out, **paths)
    assert sorted(rec.queries) == ["dev answerable 0", "dev answerable 1", "dev kept u"]
    written = out.read_text()
    assert "test" not in written.replace(
        "dev_tuning", ""
    )  # no TEST ids, splits or text
    assert {f["split"] for f in json.loads(written)["features"]} == {"dev"}


def test_test_command_refuses_a_second_run(tmp_path: Path) -> None:
    paths = _write_fixture(tmp_path)
    tuning, result = tmp_path / "dev_tuning.json", tmp_path / "test_result.json"
    eg.dev_command(Recorder(), out=tuning, **paths)
    first = Recorder()
    payload = eg.test_command(first, tuning=tuning, result=result, **paths)
    assert result.exists() and payload["A_test"].endswith("/2")
    assert sorted(first.queries) == [
        "test answerable 2",
        "test answerable 3",
        "test kept u",
    ]
    before = result.read_text()
    second = Recorder()
    with pytest.raises(gt.TestAlreadyRun):
        eg.test_command(second, tuning=tuning, result=result, **paths)
    assert second.queries == [] and result.read_text() == before


def test_lock_is_checked_before_anything_is_read(tmp_path: Path) -> None:
    result = tmp_path / "test_result.json"
    result.write_text("{}")
    with pytest.raises(gt.TestAlreadyRun):  # tuning file does not even exist
        eg.test_command(Recorder(), tuning=tmp_path / "missing.json", result=result)


def test_write_test_result_never_overwrites(tmp_path: Path) -> None:
    result = tmp_path / "test_result.json"
    gt.write_test_result(result, {"a": 1})
    with pytest.raises(FileExistsError):
        gt.write_test_result(result, {"a": 2})
    assert json.loads(result.read_text()) == {"a": 1}


# --- embed uses the app's ingest path -------------------------------------------------


async def test_embed_stores_the_chunk_texts_the_app_chunker_produces(
    make_tenant,
) -> None:
    from sqlalchemy import text

    from app.db.tenant_context import tenant_transaction
    from app.services.chunker import chunk_text
    from app.services.documents import prepare_text
    from app.services.embeddings import FakeEmbeddingProvider

    tenant = await make_tenant()
    corpus = await eg.corpus_texts()
    files = sorted(
        p for p in (eg.EVAL_DIR / "corpus").glob("*.md") if p.name != "INDEX.md"
    )
    assert len(corpus) == len(files) > 0
    assert await eg.ingest_corpus(tenant["id"], FakeEmbeddingProvider()) == 0
    assert (
        await eg.ingest_corpus(tenant["id"], FakeEmbeddingProvider()) == 0
    )  # idempotent

    async with tenant_transaction(tenant["id"]) as session:
        rows = (
            await session.execute(
                text(
                    "SELECT d.title, c.chunk_index, c.text FROM chunks c "
                    "JOIN documents d ON d.id = c.document_id"
                )
            )
        ).all()
    stored: dict[str, dict[int, str]] = {}
    for title, index, content in rows:
        stored.setdefault(title, {})[index] = content
    for path in files:
        raw = path.read_bytes().decode("utf-8-sig")
        assert raw.startswith("# ")  # the title line is part of the ingested text
        expected = {c["index"]: c["text"] for c in chunk_text(prepare_text(raw))}
        assert stored[path.stem] == expected, path.name
