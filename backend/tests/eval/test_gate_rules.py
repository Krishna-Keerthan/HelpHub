"""Identifier-like tokens, refusal rules R1/R2, the T sweep and the dev-only chooser."""

import pytest

from eval import gate_rules as gr
from eval.gate_rules import Item


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("What does E-4012 mean?", ["E-4012"]),
        ("Order SKU AB-1234-XL please", ["AB-1234-XL"]),
        ("I keep getting ERR_CONN_RESET on upload", ["ERR_CONN_RESET"]),
        ("Is this fixed in v2.3.1 or v3.0?", ["v2.3.1", "v3.0"]),
        ("The API returns HTTP 429 after a while", ["HTTP 429"]),
        ("E-4012 and ERR_TIMEOUT together", ["E-4012", "ERR_TIMEOUT"]),
    ],
)
def test_identifier_tokens_found(text: str, expected: list[str]) -> None:
    assert gr.identifier_tokens(text) == expected


@pytest.mark.parametrize(
    "text",
    [
        "How do I reset my password?",
        "Since 2024 we have had no outages",
        "Call us on 555-1234 or 020 7946 0958",
        "Our SSO and API docs",
        "version 2 is better than version 1",
        "It costs 8 USD for 100 GB",
        "HTTP is a protocol",
        "",
    ],
)
def test_ordinary_text_has_no_identifier_tokens(text: str) -> None:
    assert gr.identifier_tokens(text) == []


def test_sku_is_not_also_reported_as_an_error_code() -> None:
    assert gr.identifier_tokens("AB-1234-XL") == ["AB-1234-XL"]


def test_code_literal_match_is_case_insensitive_over_contents() -> None:
    assert gr.code_literal_match("what is E-4012", ["error e-4012: assertion"])
    # tokens are extracted case-sensitively: a lowercase query has none
    assert not gr.code_literal_match("what is e-4012", ["Error E-4012"])
    assert not gr.code_literal_match("what is E-4012", ["Error E-4013"])
    assert not gr.code_literal_match("no code here", ["E-4012"])


def _item(
    qid: str,
    *,
    answerable: bool,
    score: float,
    query: str = "q",
    top5: tuple[str, ...] = (),
    category: str = "paraphrase",
) -> Item:
    return Item(qid, category, answerable, score, query, top5)


def test_r1_answers_iff_score_reaches_threshold() -> None:
    assert gr.answers("R1", 0.60, _item("a", answerable=True, score=0.60))
    assert not gr.answers("R1", 0.60, _item("a", answerable=True, score=0.5999))


def test_r2_recovers_a_code_query_that_r1_refuses() -> None:
    code = _item(
        "c",
        answerable=True,
        score=0.40,
        query="what does E-4012 mean",
        top5=("Error E-4012: assertion signature invalid",),
    )
    assert not gr.answers("R1", 0.60, code)
    assert gr.answers("R2", 0.60, code)


def test_r2_still_refuses_when_the_code_is_not_in_the_top_hits() -> None:
    item = _item("c", answerable=False, score=0.40, query="E-9999", top5=("E-4012",))
    assert not gr.answers("R2", 0.60, item)


def test_no_hits_means_refusal() -> None:
    assert not gr.answers("R1", 0.50, _item("a", answerable=True, score=float("-inf")))


ITEMS = [
    _item("a1", answerable=True, score=0.80, category="paraphrase"),
    _item("a2", answerable=True, score=0.55, category="paraphrase"),
    _item(
        "a3",
        answerable=True,
        score=0.40,
        category="code",
        query="E-4012?",
        top5=("e-4012 text",),
    ),
    _item("u1", answerable=False, score=0.62, category="near_miss"),
    _item("u2", answerable=False, score=0.30, category="off_topic"),
]


def test_evaluate_counts_false_refusals_and_false_answers_by_category() -> None:
    r1 = gr.evaluate(ITEMS, "R1", 0.60)
    assert (r1.false_refusals, r1.false_answers) == (2, 1)
    assert r1.n_answerable == 3 and r1.n_unanswerable == 2
    assert r1.by_category["code"] == (1, 0)
    assert r1.by_category["near_miss"] == (0, 1)
    r2 = gr.evaluate(ITEMS, "R2", 0.60)
    assert (r2.false_refusals, r2.false_answers) == (1, 1)  # code query recovered


def test_threshold_boundary_is_inclusive() -> None:
    items = [_item("a", answerable=True, score=0.60)]
    assert gr.evaluate(items, "R1", 0.60).false_refusals == 0
    assert gr.evaluate(items, "R1", 0.62).false_refusals == 1


def test_default_sweep_grid_is_050_to_070_by_002() -> None:
    assert gr.THRESHOLDS[0] == 0.50 and gr.THRESHOLDS[-1] == 0.70
    assert len(gr.THRESHOLDS) == 11
    assert gr.THRESHOLDS[1] == 0.52


def _res(rule: str, t: float, refusals: int, answers: int) -> gr.GateResult:
    return gr.GateResult(rule, t, 10, 4, refusals, answers, {})


def test_choose_single_optimum() -> None:
    results = [_res("R1", 0.50, 5, 3), _res("R1", 0.52, 2, 1), _res("R1", 0.54, 3, 0)]
    choice = gr.choose(results)
    assert choice is not None and (choice.rule, choice.threshold) == ("R1", 0.52)


def test_choose_plateau_takes_the_middle_step() -> None:
    results = [_res("R1", t, 2, 1) for t in (0.54, 0.56, 0.58)] + [
        _res("R1", 0.52, 4, 0),
        _res("R1", 0.60, 4, 0),
    ]
    choice = gr.choose(results)
    assert choice is not None
    assert (choice.threshold, choice.low, choice.high) == (0.56, 0.54, 0.58)


def test_choose_even_plateau_takes_the_upper_middle() -> None:
    results = [_res("R1", t, 1, 1) for t in (0.54, 0.56, 0.58, 0.60)]
    choice = gr.choose(results)
    assert choice is not None and choice.threshold == 0.58


def test_choose_two_disjoint_plateaus_picks_the_longest() -> None:
    results = [
        _res("R1", 0.50, 2, 1),
        _res("R1", 0.52, 2, 1),
        _res("R1", 0.54, 5, 0),
        _res("R1", 0.56, 2, 1),
        _res("R1", 0.58, 2, 1),
        _res("R1", 0.60, 2, 1),
    ]
    choice = gr.choose(results)
    assert choice is not None
    assert (choice.low, choice.high, choice.threshold) == (0.56, 0.60, 0.58)


def test_choose_ties_between_plateaus_prefer_r1_then_larger_t() -> None:
    both = [_res("R1", 0.52, 2, 1), _res("R2", 0.52, 2, 1)]
    choice = gr.choose(both)
    assert choice is not None and choice.rule == "R1"
    two = [_res("R1", 0.50, 2, 1), _res("R1", 0.56, 2, 1)]
    choice = gr.choose(two)
    assert choice is not None and choice.threshold == 0.56


def test_choose_requires_at_most_one_false_answer_and_may_find_none() -> None:
    assert gr.choose([_res("R1", 0.5, 0, 2), _res("R2", 0.5, 0, 3)]) is None
    choice = gr.choose([_res("R1", 0.5, 0, 2), _res("R1", 0.52, 3, 1)])
    assert choice is not None and choice.threshold == 0.52
