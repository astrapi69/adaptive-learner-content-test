#!/usr/bin/env python3
"""Tests for scripts/export_quiz_pdf.py.

Focus: the pure page-building logic (no PDF dependency needed). The student
test paper must NOT reveal answers; the teacher answer sheet MUST carry the
correct answers, points, partial-credit note, and pass threshold.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from export_quiz_pdf import (  # noqa: E402
    build_answer_lines,
    build_test_lines,
    find_graded_quiz,
)

FIXTURE = REPO_ROOT / "tests" / "fixtures" / "graded-quiz-sample.json"


def _load() -> tuple[str, dict]:
    lesson = json.loads(FIXTURE.read_text(encoding="utf-8"))
    found = find_graded_quiz(lesson)
    assert found is not None
    return found


def test_find_graded_quiz_returns_none_for_a_core_lesson() -> None:
    core = {
        "id": "x",
        "title": "x",
        "steps": [
            {"id": "s1", "type": "exercise", "exercise": {"id": "e1", "type": "free_text", "prompt": "q", "accept": ["a"]}}
        ],
    }
    assert find_graded_quiz(core) is None


def test_find_graded_quiz_is_vendor_agnostic() -> None:
    prompt, payload = _load()
    assert prompt.startswith("Beantworte")
    assert len(payload["questions"]) == 3


def test_test_paper_hides_the_answers() -> None:
    prompt, payload = _load()
    lines = build_test_lines(prompt, payload)
    joined = "\n".join(lines)
    # blank checkboxes for MC, an answer line for free_text, points shown
    assert "[ ] Paris" in joined
    assert "Antwort: ______" in joined
    assert "(2 P.)" in joined
    assert "Bestehensschwelle: 60%" in joined
    assert "Gesamtpunkte: 9" in joined
    # the free_text accepted answers must NOT appear on the student paper
    assert "rasch" not in joined
    # no correct-answer marker for MC on the student paper
    assert "correct" not in joined


def test_answer_sheet_reveals_correct_answers_and_points() -> None:
    prompt, payload = _load()
    lines = build_answer_lines(prompt, payload)
    joined = "\n".join(lines)
    assert "Lösungsblatt" in joined
    assert "1. Paris  (2 P.)" in joined
    assert "rasch" in joined  # free_text canonical answer
    assert "auch: flink, zügig" in joined  # further accepted answers
    assert "2, 3" in joined  # both correct primes
    assert "[Mehrfachauswahl, Teilpunkte]" in joined  # partial-credit note on Q3
    assert "Bestehensschwelle: 60%" in joined


def test_whole_number_points_have_no_trailing_decimal() -> None:
    _, payload = _load()
    lines = build_test_lines("", payload)
    joined = "\n".join(lines)
    assert "(2 P.)" in joined and "(2.0 P.)" not in joined
