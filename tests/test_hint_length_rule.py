#!/usr/bin/env python3
"""Quality rule: no answer-length statements in exercise/blank hints (#100).

The app shows the answer's length automatically (the system hint), so an
authored hint stating a letter/character count ("Vier Buchstaben.") is
redundant at best — and drifts into visible contradiction when the content
changes (the DSGVO cloze said "Vier Buchstaben." for a five-letter answer).

Scope: the rule covers ``exercise.hint`` and ``exercise.blanks[].hint`` —
the surfaces the app pairs with its automatic length hint. Card hints are
deliberately NOT covered: a character count there can be legitimate teaching
content (e.g. the python-basics slicing card explains that ``s[0:3]``
yields 3 characters).
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"

# validate_content imports its sibling generate_search_index, so the scripts/
# directory must be importable as a top-level package root.
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import validate_content as vc  # noqa: E402


def quality_errors(lesson: dict) -> list[str]:
    errors: list[str] = []
    vc.validate_lesson_quality(lesson, "de", "<lesson>", errors)
    return [e for e in errors if "length" in e or "Länge" in e or "count" in e]


def lesson_with_exercise(exercise: dict, cards: list | None = None) -> dict:
    return {
        "id": "l1",
        "title": "T",
        "cards": cards or [],
        "steps": [
            {"id": "s1", "type": "theory", "title": "Th", "body": "b"},
            {"id": "s2", "type": "exercise", "title": "Ex", "exercise": exercise},
        ],
    }


def cloze(hint: str | None = None, blanks: list | None = None) -> dict:
    return {
        "id": "e1",
        "type": "cloze",
        "prompt": "p",
        "card_ids": [],
        "sentence": "a ___ b",
        "blanks": blanks if blanks is not None else [{"accept": ["x"]}],
        "cloze_mode": "type",
        **({"hint": hint} if hint is not None else {}),
    }


# --- 1. Reproduction (the DSGVO shape: a bare letter-count hint) -----------


def test_letter_count_hint_is_flagged() -> None:
    errors = quality_errors(lesson_with_exercise(cloze(hint="Vier Buchstaben.")))
    assert errors, "a letter-count hint must be reported as a quality error"


def test_character_count_hint_is_flagged() -> None:
    errors = quality_errors(
        lesson_with_exercise(cloze(hint="Zwei Zeichen, das zweite klein."))
    )
    assert errors


# --- 2. Happy path: content hints pass --------------------------------------


def test_content_hint_passes() -> None:
    errors = quality_errors(
        lesson_with_exercise(
            cloze(hint="Abkürzung für die Datenschutz-Grundverordnung.")
        )
    )
    assert errors == []


def test_absent_hint_passes() -> None:
    assert quality_errors(lesson_with_exercise(cloze())) == []


# --- 3. Edge cases: rule scope ----------------------------------------------


def test_blank_level_hint_is_flagged() -> None:
    exercise = cloze(
        blanks=[{"accept": ["x"], "hint": "Genau drei Buchstaben tippen."}]
    )
    errors = quality_errors(lesson_with_exercise(exercise))
    assert errors


def test_card_hint_with_character_count_is_not_flagged() -> None:
    """Card hints may talk about character counts (teaching content)."""
    cards = [
        {
            "id": "c1",
            "front": "String-Slicing",
            "back": "Teilstring",
            "hint": "Der stop-Index ist ausschließend — s[0:3] liefert 3 Zeichen, nicht 4.",
        }
    ]
    errors = quality_errors(lesson_with_exercise(cloze(), cards=cards))
    assert errors == []


def test_free_text_hint_is_flagged_too() -> None:
    """The rule covers every exercise type, not just cloze."""
    exercise = {
        "id": "e1",
        "type": "free_text",
        "prompt": "p",
        "card_ids": [],
        "accept": ["Hola", "hola"],
        "distractors": ["Adios"],
        "hint": "Vier Buchstaben, das H ist stumm.",
    }
    errors = quality_errors(lesson_with_exercise(exercise))
    assert errors


# --- 4. Boundary: digit form, article form, and compound-word non-matches ---


def test_digit_count_is_flagged() -> None:
    errors = quality_errors(lesson_with_exercise(cloze(hint="Nur 8 Zeichen lang.")))
    assert errors


def test_article_count_form_is_flagged() -> None:
    errors = quality_errors(
        lesson_with_exercise(cloze(hint="Eine Kurzform mit einem Buchstaben."))
    )
    assert errors


def test_compound_leerzeichen_is_not_flagged() -> None:
    """"vier Leerzeichen" is indentation advice, not an answer length."""
    errors = quality_errors(
        lesson_with_exercise(cloze(hint="Einrückung: vier Leerzeichen pro Ebene."))
    )
    assert errors == []
