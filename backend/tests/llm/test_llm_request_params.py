"""Exact kwargs sent to Groq, and the shipped default model."""

import pytest

from app.core.config import Settings, settings
from app.services.llm import request_params

MESSAGES = [{"role": "user", "content": "q"}]


def test_default_model_is_gpt_oss_120b() -> None:
    assert Settings.model_fields["groq_model"].default == "openai/gpt-oss-120b"


@pytest.mark.parametrize("model", ["openai/gpt-oss-120b", "openai/gpt-oss-20b"])
def test_gpt_oss_models_get_exactly_the_reasoning_kwargs(
    monkeypatch: pytest.MonkeyPatch, model: str
) -> None:
    monkeypatch.setattr(settings, "groq_model", model)
    monkeypatch.setattr(settings, "llm_reasoning_effort", "low")
    params = request_params(MESSAGES, 800)
    assert params == {
        "model": model,
        "messages": MESSAGES,
        "temperature": settings.llm_temperature,
        "stream": True,
        "reasoning_effort": "low",
        "include_reasoning": False,
        "max_completion_tokens": 800 + settings.llm_reasoning_token_headroom,
    }


def test_other_models_get_none_of_the_reasoning_kwargs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "groq_model", "some/plain-model")
    assert request_params(MESSAGES, 800) == {
        "model": "some/plain-model",
        "messages": MESSAGES,
        "temperature": settings.llm_temperature,
        "stream": True,
        "max_completion_tokens": 800,
    }
