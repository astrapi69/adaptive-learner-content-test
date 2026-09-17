#!/usr/bin/env python3
"""Variety exemption covers ALL multiple-choice forms (native + cloze).

A pure multiple-choice lesson - a valid, intended artifact in this
MC-focused test repo - is exempt from the ``minExerciseTypes`` variety
rule. Since schema v1.6 there are two MC authoring forms: the legacy
``cloze`` ``select``/``multiselect`` vehicle and the native
``multiple_choice`` type (engine 0.8.x, coexistence). The exemption must
treat them alike; before this fix a native-MC-only lesson was blocked
while the equivalent cloze-select-only lesson passed.
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import validate_content as vc  # noqa: E402


def variety_errors(lesson: dict) -> list[str]:
    errors: list[str] = []
    vc.validate_lesson_quality(lesson, "de", "<lesson>", errors)
    return [e for e in errors if "exercise type" in e]


def mc_native(ident: str) -> dict:
    return {
        "id": f"s-{ident}",
        "type": "exercise",
        "exercise": {
            "id": ident,
            "type": "multiple_choice",
            "prompt": "Frage?",
            "options": [
                {"text": f"richtig {ident}", "correct": True},
                {"text": f"falsch {ident}"},
            ],
        },
    }


def mc_cloze_select(ident: str) -> dict:
    return {
        "id": f"s-{ident}",
        "type": "exercise",
        "exercise": {
            "id": ident,
            "type": "cloze",
            "cloze_mode": "select",
            "prompt": "Frage?",
            "sentence": "Antwort: ___.",
            "blanks": [{"accept": ["richtig"]}],
            "distractors": ["falsch"],
        },
    }


def free_text(ident: str) -> dict:
    return {
        "id": f"s-{ident}",
        "type": "exercise",
        "exercise": {
            "id": ident,
            "type": "free_text",
            "prompt": "Frage?",
            "accept": ["antwort"],
        },
    }


def lesson(steps: list[dict]) -> dict:
    return {
        "id": "l1",
        "title": "T",
        "cards": [],
        "steps": [{"id": "t1", "type": "theory", "body": "Theorie."}, *steps],
    }


def test_native_mc_only_lesson_is_exempt() -> None:
    steps = [mc_native(f"mc{i}") for i in range(5)]
    assert variety_errors(lesson(steps)) == []


def test_cloze_select_only_lesson_stays_exempt() -> None:
    steps = [mc_cloze_select(f"c{i}") for i in range(5)]
    assert variety_errors(lesson(steps)) == []


def test_mixed_mc_forms_are_exempt() -> None:
    steps = [mc_native("mc1"), mc_cloze_select("c1"), mc_native("mc2")]
    assert variety_errors(lesson(steps)) == []


def test_single_non_mc_type_still_blocked() -> None:
    steps = [free_text(f"f{i}") for i in range(5)]
    assert variety_errors(lesson(steps)) != []


def test_mc_plus_free_text_counts_as_two_types_no_error() -> None:
    steps = [mc_native("mc1"), free_text("f1")]
    assert variety_errors(lesson(steps)) == []
