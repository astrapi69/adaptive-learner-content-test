#!/usr/bin/env python3
"""Cross-language shape-parity gate (#1208 / Refs #1205 / #1193, #699).

The lesson SHAPE is defined by ``schema/lesson.schema.json`` — a vendored
mirror of the pinned ``learn-content-engine`` release (source of truth chain:
adaptive-learner Pydantic -> engine -> this mirror) — and validated here with
``jsonschema`` exactly as the engine/app validate it with ``ajv``. The
remaining half of the #699 contract is *parity* — every consumer must
accept/reject every input identically.

This test pins the content-repo validator against the shape-parity fixture
under ``tests/fixtures/lesson-shape-parity.json`` (adopted from the app's
#1205 parity contract at the engine decoupling; owned by this repo since).
Each fixture case carries the expected SHAPE verdict; we assert
``lesson_shape_ok`` returns it. The cross-validator parity anchor is the
engine-conformance CI job (``validate_with_engine.mjs``), which runs the
engine's ajv validator over the whole repo at the same pinned version — a
divergence between its verdicts and this validator's is a real bug.

Runs under pytest (parametrized) or standalone (``python tests/test_shape_parity.py``).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"
FIXTURE_PATH = REPO_ROOT / "tests" / "fixtures" / "lesson-shape-parity.json"

# validate_content imports its sibling generate_search_index, so the scripts/
# directory must be importable as a top-level package root.
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import validate_content as vc  # noqa: E402


def load_cases() -> list[dict]:
    data = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    cases = data["cases"]
    assert cases, "parity fixture carries no cases"
    return cases


CASES = load_cases()


try:
    import pytest

    @pytest.mark.parametrize(
        "case", CASES, ids=[c["name"] for c in CASES]
    )
    def test_shape_parity_case(case: dict) -> None:
        """Each shared-fixture input gets the expected SHAPE verdict — the same
        verdict the app-side ajv validator asserts for the identical input."""
        got = vc.lesson_shape_ok(case["lesson"])
        expected = case["expectValid"]
        assert got == expected, (
            f"{case['name']}: expected expectValid={expected} but "
            f"lesson_shape_ok={got} ({case.get('reason', '')}). "
            f"errors={vc.lesson_shape_errors(case['lesson'])}"
        )

    def test_fixture_covers_both_verdicts() -> None:
        """Guard against a fixture that only exercises one side of accept/reject."""
        verdicts = {c["expectValid"] for c in CASES}
        assert verdicts == {True, False}, (
            "parity fixture must contain both valid and invalid lessons"
        )

except ImportError:  # pragma: no cover - standalone fallback when pytest absent
    pytest = None  # type: ignore[assignment]


def _run_standalone() -> int:
    failures: list[str] = []
    for case in CASES:
        got = vc.lesson_shape_ok(case["lesson"])
        expected = case["expectValid"]
        mark = "ok  " if got == expected else "FAIL"
        if got != expected:
            failures.append(case["name"])
        print(f"  [{mark}] {case['name']:<34} expectValid={expected} got={got}")
    if {c["expectValid"] for c in CASES} != {True, False}:
        failures.append("<fixture must cover both verdicts>")
    if failures:
        print(f"\nDIVERGENCE: {len(failures)} case(s) disagree: {failures}")
        return 1
    print(f"\nParity OK — all {len(CASES)} shared-fixture verdicts match.")
    return 0


if __name__ == "__main__":
    sys.exit(_run_standalone())
