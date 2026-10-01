#!/usr/bin/env python3
"""Export a graded-quiz lesson to a printable test PDF + a separate answer sheet.

Teacher-facing tool for the school-test use case (learn-content-engine#46):
it reads a lesson that carries an ``ext:*-graded-quiz`` exercise (a scored
question set - each question with ``points``, optional ``partial_credit`` on
multi-select, an optional percentage ``pass_threshold``) and renders two PDFs:

  * ``<id>-test.pdf``     - the question paper for students (no answers shown,
                            blank checkboxes / answer lines, points per question).
  * ``<id>-lösung.pdf``  - the answer sheet for the teacher (correct answers,
                            points, partial-credit note, pass threshold).

This is a CONSUMER tool, not part of the engine: the engine validates and
produces the canonical lesson, a tool like this renders one presentation of it
(the same "one source, many outputs" boundary that keeps rendering out of the
engine). It is standalone - it does not invoke the engine, so it is independent
of the repo's pinned engine version.

Note: the content gate (``make lint``) accepts adopted ``ext:`` types since
adaptive-learner-content-test#66/#67, so graded-quiz content can now live under
``sets/`` (adaptive-learner-content-test#69 ships a reference set there). This
tool reads any graded-quiz lesson JSON - one under ``sets/`` or a lesson kept
elsewhere (e.g. ``tests/fixtures/``).

The page-building logic is pure (``build_test_lines`` / ``build_answer_lines``)
and unit-tested; the PDF emission is a thin wrapper that imports ``fpdf2``
lazily, so the logic is testable without the PDF dependency.

Usage:
    python scripts/export_quiz_pdf.py path/to/graded-quiz.json [--out-dir DIR]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


def find_graded_quiz(lesson: dict[str, Any]) -> tuple[str, dict[str, Any]] | None:
    """Return ``(exercise_prompt, ext_payload)`` of the first graded-quiz
    exercise in ``lesson``, or ``None``. A graded-quiz is recognised by its
    payload shape - an ``ext_payload`` whose ``questions`` is a list of objects
    each carrying numeric ``points`` - so the tool is vendor-agnostic
    (``ext:ref-graded-quiz``, ``ext:al-graded-quiz``, ...)."""
    for step in lesson.get("steps", []):
        exercise = step.get("exercise")
        if not isinstance(exercise, dict):
            continue
        payload = exercise.get("ext_payload")
        if not isinstance(payload, dict):
            continue
        questions = payload.get("questions")
        if (
            isinstance(questions, list)
            and questions
            and all(isinstance(q, dict) and isinstance(q.get("points"), (int, float)) for q in questions)
        ):
            return str(exercise.get("prompt", "")), payload
    return None


def _threshold_line(payload: dict[str, Any]) -> list[str]:
    threshold = payload.get("pass_threshold")
    return [f"Bestehensschwelle: {threshold}%"] if isinstance(threshold, (int, float)) else []


def _canonical_answer(question: dict[str, Any]) -> str:
    """The correct answer(s) of one question, for the answer sheet."""
    if question.get("type") == "multiple_choice":
        correct = [o.get("text", "") for o in question.get("options", []) if o.get("correct") is True]
        return ", ".join(correct)
    if question.get("type") == "free_text":
        accept = [a for a in question.get("accept", []) if str(a).strip()]
        if not accept:
            return ""
        head, *rest = accept
        return head + (f"  (auch: {', '.join(rest)})" if rest else "")
    return ""


def build_test_lines(prompt: str, payload: dict[str, Any]) -> list[str]:
    """The student question paper: prompts, points, blank answer affordances -
    NO correct answers."""
    total = sum(float(q.get("points", 0)) for q in payload.get("questions", []))
    lines: list[str] = ["TEST"]
    if prompt.strip():
        lines.append(prompt.strip())
    lines += _threshold_line(payload)
    lines.append(f"Gesamtpunkte: {_fmt_points(total)}")
    lines.append("")
    for index, question in enumerate(payload.get("questions", []), start=1):
        lines.append(f"{index}. {question.get('prompt', '')}  ({_fmt_points(question.get('points', 0))} P.)")
        if question.get("type") == "multiple_choice":
            for option in question.get("options", []):
                lines.append(f"    [ ] {option.get('text', '')}")
        else:
            lines.append("    Antwort: ______________________________")
        lines.append("")
    return lines


def build_answer_lines(prompt: str, payload: dict[str, Any]) -> list[str]:
    """The teacher answer sheet: correct answers, points, partial-credit note,
    pass threshold."""
    total = sum(float(q.get("points", 0)) for q in payload.get("questions", []))
    lines: list[str] = ["Lösungsblatt"]
    if prompt.strip():
        lines.append(prompt.strip())
    lines += _threshold_line(payload)
    lines.append(f"Gesamtpunkte: {_fmt_points(total)}")
    lines.append("")
    for index, question in enumerate(payload.get("questions", []), start=1):
        note = "  [Mehrfachauswahl, Teilpunkte]" if question.get("partial_credit") is True else ""
        lines.append(
            f"{index}. {_canonical_answer(question)}  ({_fmt_points(question.get('points', 0))} P.){note}"
        )
    return lines


def _fmt_points(value: Any) -> str:
    """Format points without a trailing ``.0`` on whole numbers."""
    number = float(value)
    return str(int(number)) if number == int(number) else str(number)


def _write_pdf(lines: list[str], title: str, out_path: Path) -> None:
    """Render ``lines`` to ``out_path`` as a simple PDF. Imports fpdf2 lazily so
    the pure page logic stays testable without the dependency."""
    try:
        from fpdf import FPDF
        from fpdf.enums import XPos, YPos
    except ImportError as error:  # pragma: no cover - exercised only without the dep
        raise SystemExit(
            "This step needs fpdf2. Install it with 'pip install fpdf2' "
            "(it is listed in requirements.txt)."
        ) from error

    pdf = FPDF()
    pdf.set_title(title)
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    for line in lines:
        if line == "":
            pdf.ln(5)
            continue
        style = "B" if line in ("TEST", "Lösungsblatt") else ""
        pdf.set_font("Helvetica", style=style, size=14 if style else 12)
        # Core fonts are latin-1; keep the demo robust for other scripts. Return
        # the cursor to the left margin after each line so the next line has the
        # full page width (fpdf2 otherwise leaves x at the right).
        pdf.multi_cell(
            0,
            8,
            line.encode("latin-1", "replace").decode("latin-1"),
            new_x=XPos.LMARGIN,
            new_y=YPos.NEXT,
        )
    pdf.output(str(out_path))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Export a graded-quiz lesson to test + answer-sheet PDFs.")
    parser.add_argument("lesson", type=Path, help="Path to a graded-quiz lesson JSON.")
    parser.add_argument("--out-dir", type=Path, default=Path("."), help="Output directory (default: current).")
    args = parser.parse_args(argv)

    lesson = json.loads(args.lesson.read_text(encoding="utf-8"))
    found = find_graded_quiz(lesson)
    if found is None:
        print(f"error: {args.lesson} has no graded-quiz exercise (ext_payload.questions with points).", file=sys.stderr)
        return 1
    prompt, payload = found

    args.out_dir.mkdir(parents=True, exist_ok=True)
    stem = str(lesson.get("id", args.lesson.stem))
    test_path = args.out_dir / f"{stem}-test.pdf"
    answer_path = args.out_dir / f"{stem}-lösung.pdf"
    _write_pdf(build_test_lines(prompt, payload), f"{stem} - Test", test_path)
    _write_pdf(build_answer_lines(prompt, payload), f"{stem} - Lösung", answer_path)
    print(f"wrote {test_path}")
    print(f"wrote {answer_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
