"""app/core/errors.py: the one SQLSTATE and traceback-frame helper."""

from app.core.errors import sqlstate_of, traceback_frames


class _Driver(Exception):
    sqlstate = "23505"


def test_sqlstate_found_on_the_exception_itself() -> None:
    assert sqlstate_of(_Driver("boom")) == "23505"


def test_sqlstate_found_through_orig_and_cause_chain() -> None:
    wrapper = Exception("wrapper")
    wrapper.orig = Exception("adapter")  # type: ignore[attr-defined]
    wrapper.orig.__cause__ = _Driver("driver")  # type: ignore[attr-defined]
    assert sqlstate_of(wrapper) == "23505"


def test_sqlstate_is_none_without_a_code_and_survives_cause_cycles() -> None:
    a, b = Exception("a"), Exception("b")
    a.__cause__, b.__cause__ = b, a
    assert sqlstate_of(a) is None
    assert sqlstate_of(Exception("plain")) is None


def test_frames_name_file_line_and_function_but_not_the_message() -> None:
    def fail() -> None:
        raise ValueError("secret document text")

    try:
        fail()
    except ValueError as exc:
        frames = traceback_frames(exc)
    assert "test_errors.py:" in frames and " in fail" in frames
    assert "secret" not in frames
