#!/usr/bin/env python3
"""Tests for scripts/audit_content.py.

The audit is advisory and reports what no gate blocks: whitespace-only
fields, duplicate card fronts, a free_text answer that is also a
distractor, lessons missing from their set. What the engine gate blocks
(validate_with_engine.mjs) is not repeated here: a malformed cloze, a
multiselect overlap, too few word tiles, a picture choice without exactly
one correct image, a repeated matching left term. One rule, one place
(learn-content-engine's rule ownership).
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import audit_content as ac  # noqa: E402


def _audit_lesson(lesson: dict) -> list[str]:
    findings: list[tuple] = []
    ac.audit_lesson(lesson, "<lesson>", findings)
    return [problem for _label, problem, _fix in findings]


def _audit(exercise: dict, cards: list[dict] | None = None) -> list[str]:
    """Run the audit over a one-exercise lesson; return the problem strings."""
    return _audit_lesson(
        {
            "id": "l1",
            "title": "T",
            "cards": cards or [],
            "steps": [{"id": "s1", "type": "exercise", "exercise": exercise}],
        }
    )


ENGINE_OWNED = {
    "multiselect accept/distractors overlap (E-CLOZE-MS-DISJOINT)": {
        "id": "c1", "type": "cloze", "cloze_mode": "multiselect", "prompt": "Pick.",
        "sentence": "Which are prime?", "accept": ["2", "3"], "distractors": ["3", "4"],
    },
    "multiselect without distractors (E-CLOZE-MS-DISTRACTORS)": {
        "id": "c1", "type": "cloze", "cloze_mode": "multiselect", "prompt": "Pick.",
        "sentence": "Which are prime?", "accept": ["2"], "distractors": [],
    },
    "type cloze without a marker (E-CLOZE-MARKERS)": {
        "id": "c1", "type": "cloze", "cloze_mode": "type", "prompt": "Fill.",
        "sentence": "No gap here.", "blanks": [{"accept": ["x"]}],
    },
    "word_tiles with one tile (E-TILES-MIN)": {
        "id": "w1", "type": "word_tiles", "prompt": "Order.", "tiles": ["one"],
    },
    "picture_choice with two correct images (E-PIC-ONE-CORRECT)": {
        "id": "p1", "type": "picture_choice", "prompt": "Which?",
        "images": [
            {"src": "a.png", "label": "a", "is_correct": "true"},
            {"src": "b.png", "label": "b", "is_correct": "true"},
        ],
    },
    "matching with a repeated left term (E-MATCH-DUP-LEFT)": {
        "id": "m1", "type": "matching", "prompt": "Match.",
        "pairs": [{"left": "a", "right": "1"}, {"left": "A", "right": "2"}, {"left": "b", "right": "3"}],
    },
}


@pytest.mark.parametrize("label", sorted(ENGINE_OWNED))
def test_engine_owned_errors_are_not_repeated(label: str) -> None:
    """The engine gate blocks these; the audit does not report them again."""
    assert _audit(ENGINE_OWNED[label]) == []


def test_whitespace_only_prompt_is_reported() -> None:
    """The schema's minLength lets "  " through; the audit catches it."""
    problems = _audit({"id": "f1", "type": "free_text", "prompt": "   ", "accept": ["a", "b"]})
    assert any("empty prompt" in problem for problem in problems)


def test_duplicate_card_front_is_reported() -> None:
    cards = [{"id": "c1", "front": "Hund", "back": "dog"}, {"id": "c2", "front": "hund", "back": "hound"}]
    problems = _audit({"id": "f1", "type": "free_text", "prompt": "?", "accept": ["a", "b"]}, cards)
    assert any("duplicate card front" in problem for problem in problems)


def test_free_text_answer_that_is_also_a_distractor_is_reported() -> None:
    problems = _audit(
        {"id": "f1", "type": "free_text", "prompt": "?", "accept": ["gracias", "Gracias"], "distractors": ["gracias"]}
    )
    assert any("accept & distractors overlap" in problem for problem in problems)


def test_a_clean_lesson_reports_nothing() -> None:
    cards = [{"id": "c1", "front": "Hund", "back": "dog"}]
    exercise = {"id": "f1", "type": "free_text", "prompt": "Translate.", "accept": ["dog", "Dog"], "distractors": ["cat"]}
    assert _audit(exercise, cards) == []
