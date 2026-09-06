#!/usr/bin/env python3
"""Tests for the AI exercise generator (scripts/generate_exercises.py).

No real API call is ever made: the model-call function is injected, and the
one provider-transport test patches the HTTP helper. The point of these
tests is the parts that carry the value — defensive JSON extraction, the
validator gate, and the validate-retry-discard loop — not the network.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import generate_exercises as gen  # noqa: E402
import validate_content as vc  # noqa: E402


# --------------------------------------------------------------------------
# Fixtures
# --------------------------------------------------------------------------


def valid_lesson() -> dict:
    """A lesson that passes BOTH the structural and the quality gate."""
    return {
        "id": "01-greetings",
        "title": "Greetings",
        "description": "Say hello.",
        "target_language": "fr",
        "source_language": "en",
        "domain": "language",
        "cards": [{"id": "bonjour", "front": "bonjour", "back": "hello"}],
        "steps": [
            {"id": "intro", "type": "theory", "title": "Theory", "body": "Bonjour = hello."},
            _cloze("c1"),
            _cloze("c2"),
            _cloze("c3"),
            {
                "id": "f1",
                "type": "exercise",
                "exercise": {
                    "id": "f1",
                    "type": "free_text",
                    "prompt": "How do you say hello?",
                    "accept": ["bonjour", "Bonjour"],
                    "distractors": ["bonsoir"],
                },
            },
            {
                "id": "m1",
                "type": "exercise",
                "exercise": {
                    "id": "m1",
                    "type": "matching",
                    "prompt": "Match the pairs.",
                    "pairs": [
                        {"left": "bonjour", "right": "hello"},
                        {"left": "merci", "right": "thanks"},
                        {"left": "oui", "right": "yes"},
                    ],
                },
            },
        ],
    }


def _cloze(eid: str) -> dict:
    return {
        "id": eid,
        "type": "exercise",
        "exercise": {
            "id": eid,
            "type": "cloze",
            "cloze_mode": "type",
            "prompt": "Fill the blank.",
            "sentence": "On dit ___ le matin.",
            "blanks": [{"accept": ["bonjour"]}],
        },
    }


# --------------------------------------------------------------------------
# The fixture itself must actually pass the real validator
# --------------------------------------------------------------------------


def test_valid_lesson_fixture_passes_the_real_gate():
    assert gen.validate_candidate(valid_lesson(), "en") == []


# --------------------------------------------------------------------------
# extract_json — defensive parsing
# --------------------------------------------------------------------------


def test_extract_json_direct():
    assert gen.extract_json('{"id": "x"}') == {"id": "x"}


def test_extract_json_strips_markdown_fences():
    reply = "```json\n{\"id\": \"x\", \"n\": 1}\n```"
    assert gen.extract_json(reply) == {"id": "x", "n": 1}


def test_extract_json_recovers_outermost_object_from_prose():
    reply = 'Sure! Here is the lesson:\n{"id": "x"}\nHope that helps.'
    assert gen.extract_json(reply) == {"id": "x"}


def test_extract_json_raises_when_no_object():
    with pytest.raises(ValueError):
        gen.extract_json("no json here at all")


# --------------------------------------------------------------------------
# Prompt building
# --------------------------------------------------------------------------


def test_prompt_pins_json_only_and_forbids_picture_choice():
    params = gen.GenerationParams(topic="Food", target_language="fr", source_language="en")
    prompt = gen.build_generation_prompt(params)
    assert "JSON ONLY" in prompt
    assert "Do NOT use picture_choice" in prompt
    assert "deliberate, plausible mistake" in prompt


def test_prompt_includes_validator_feedback_on_retry():
    params = gen.GenerationParams(topic="Food", target_language="fr", source_language="en")
    prompt = gen.build_generation_prompt(params, feedback="- <candidate>: 2 exercises (need >= 5)")
    assert "CORRECTION" in prompt
    assert "need >= 5" in prompt


# --------------------------------------------------------------------------
# Validation gate
# --------------------------------------------------------------------------


def test_gate_rejects_structural_error():
    broken = valid_lesson()
    del broken["title"]  # required field
    errors = gen.validate_candidate(broken, "en")
    assert errors and any("title" in e for e in errors)


def test_gate_rejects_quality_error_too_few_exercises():
    thin = valid_lesson()
    thin["steps"] = thin["steps"][:2]  # theory + one exercise only
    errors = gen.validate_candidate(thin, "en")
    assert errors and any("exercises" in e for e in errors)


# --------------------------------------------------------------------------
# The generate-validate-retry-discard loop (model injected)
# --------------------------------------------------------------------------


def _config() -> gen.ModelConfig:
    return gen.ModelConfig(provider="anthropic", model="test-model", api_key="test-key")


def test_loop_succeeds_on_first_valid_reply():
    calls = []

    def fake_call(prompt, config):
        calls.append(prompt)
        return json.dumps(valid_lesson())

    result = gen.generate_lesson(_config(), _params(), call=fake_call)
    assert result.lesson is not None
    assert result.attempts == 1
    assert len(calls) == 1


def test_loop_retries_with_feedback_then_succeeds():
    replies = iter([json.dumps(_too_thin()), json.dumps(valid_lesson())])
    seen_prompts = []

    def fake_call(prompt, config):
        seen_prompts.append(prompt)
        return next(replies)

    result = gen.generate_lesson(_config(), _params(), call=fake_call, max_retries=2)
    assert result.lesson is not None
    assert result.attempts == 2
    # The second prompt must carry the first attempt's validator errors.
    assert "CORRECTION" in seen_prompts[1]


def test_loop_discards_when_never_valid():
    def fake_call(prompt, config):
        return json.dumps(_too_thin())

    result = gen.generate_lesson(_config(), _params(), call=fake_call, max_retries=2)
    assert result.lesson is None
    assert result.attempts == 3  # first + 2 retries
    assert result.errors


def test_loop_handles_unparseable_reply():
    def fake_call(prompt, config):
        return "I cannot help with that."

    result = gen.generate_lesson(_config(), _params(), call=fake_call, max_retries=1)
    assert result.lesson is None
    assert any("JSON" in e for e in result.errors)


def _params() -> gen.GenerationParams:
    return gen.GenerationParams(
        topic="Greetings", target_language="fr", source_language="en", set_id="fr-a1"
    )


def _too_thin() -> dict:
    lesson = valid_lesson()
    lesson["steps"] = lesson["steps"][:2]
    return lesson


# --------------------------------------------------------------------------
# Staging output — never touches sets/, lands in generated/
# --------------------------------------------------------------------------


def test_stage_lesson_writes_into_generated_subfolder(tmp_path):
    path = gen.stage_lesson(valid_lesson(), tmp_path, "fr-a1")
    assert path.parent == tmp_path / "fr-a1"
    assert path.name == "01-greetings.json"
    written = json.loads(path.read_text(encoding="utf-8"))
    assert written["id"] == "01-greetings"


def test_slugify():
    assert gen.slugify("Ordering Food!!") == "ordering-food"
    assert gen.slugify("") == "lesson"


# --------------------------------------------------------------------------
# API key resolution (BYOK, env only)
# --------------------------------------------------------------------------


def test_resolve_api_key_reads_env(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    assert gen.resolve_api_key("anthropic") == "sk-test"


def test_resolve_api_key_gemini_falls_back_to_google_key(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setenv("GOOGLE_API_KEY", "g-test")
    assert gen.resolve_api_key("gemini") == "g-test"


def test_resolve_api_key_raises_when_missing(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(RuntimeError):
        gen.resolve_api_key("openai")


# --------------------------------------------------------------------------
# Provider transport (HTTP helper patched — still no real network)
# --------------------------------------------------------------------------


def test_call_model_anthropic_shapes_request_and_reads_text(monkeypatch):
    captured = {}

    def fake_post(url, headers, payload, timeout):
        captured["url"] = url
        captured["headers"] = headers
        captured["payload"] = payload
        return {"content": [{"type": "text", "text": '{"id": "x"}'}]}

    monkeypatch.setattr(gen, "_http_post_json", fake_post)
    config = gen.ModelConfig(provider="anthropic", model="claude-x", api_key="sk-1")
    text = gen.call_model("hello prompt", config)
    assert text == '{"id": "x"}'
    assert captured["headers"]["x-api-key"] == "sk-1"
    assert captured["payload"]["messages"][0]["content"] == "hello prompt"


def test_call_model_openai_reads_choice(monkeypatch):
    def fake_post(url, headers, payload, timeout):
        return {"choices": [{"message": {"content": '{"ok": true}'}}]}

    monkeypatch.setattr(gen, "_http_post_json", fake_post)
    config = gen.ModelConfig(provider="openai", model="gpt-x", api_key="sk-2")
    assert gen.call_model("p", config) == '{"ok": true}'


def test_call_model_gemini_reads_parts(monkeypatch):
    def fake_post(url, headers, payload, timeout):
        assert "gemini-x:generateContent" in url
        return {"candidates": [{"content": {"parts": [{"text": "{}"}]}}]}

    monkeypatch.setattr(gen, "_http_post_json", fake_post)
    config = gen.ModelConfig(provider="gemini", model="gemini-x", api_key="g-1")
    assert gen.call_model("p", config) == "{}"


# --------------------------------------------------------------------------
# main() end to end — HTTP helper patched (no real network), real gate + staging
# --------------------------------------------------------------------------


def test_main_stages_validated_lesson(monkeypatch, tmp_path):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    monkeypatch.setattr(
        gen,
        "_http_post_json",
        lambda url, headers, payload, timeout: {
            "content": [{"type": "text", "text": json.dumps(valid_lesson())}]
        },
    )
    rc = gen.main(
        [
            "--topic", "Greetings",
            "--target-lang", "fr",
            "--source-lang", "en",
            "--set-id", "fr-a1",
            "--out", str(tmp_path),
        ]
    )
    assert rc == 0
    assert (tmp_path / "fr-a1" / "01-greetings.json").is_file()


def test_main_reports_provider_error_cleanly(monkeypatch, tmp_path):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")

    def boom(url, headers, payload, timeout):
        raise RuntimeError("HTTP 401 from provider: invalid x-api-key")

    monkeypatch.setattr(gen, "_http_post_json", boom)
    rc = gen.main(
        ["--topic", "X", "--target-lang", "fr", "--source-lang", "en", "--out", str(tmp_path)]
    )
    assert rc == 2  # clean abort, not a traceback


def test_main_missing_key_returns_2(monkeypatch, tmp_path):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("AL_GEN_PROVIDER", raising=False)
    rc = gen.main(
        ["--topic", "X", "--target-lang", "fr", "--source-lang", "en", "--out", str(tmp_path)]
    )
    assert rc == 2
