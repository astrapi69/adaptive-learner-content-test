#!/usr/bin/env python3
"""Cross-language shape-parity gate (#1208 / Refs #1205 / #1193, #699).

The lesson SHAPE is canonical: ``schema/lesson.schema.json`` is mirrored from
the pinned learn-content-engine release (source-of-truth chain: engine
(canonical) → this mirror) and validated here with ``jsonschema`` exactly
as ajv-based consumers (the app, the engine) validate it. The remaining half of
the #699 contract is *parity* — every consumer must accept/reject the same
input identically.

This test pins the content-repo validator against the locally-owned fixture
snapshot ``tests/fixtures/lesson-shape-parity.json`` (carried over from the
app at schema v1.5; the cross-repo parity guarantee is closed by the app's
app-vs-engine parity test plus this repo's engine-pinned drift gate). Each
fixture case carries the expected SHAPE verdict; we assert ``lesson_shape_ok``
returns it. A divergence means the mirror drifted or a validator detail
differs, and is a real bug. When a pin bump changes the schema, refresh the
fixture cases in the same PR.

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
        """Each fixture input gets the expected SHAPE verdict — the same
        verdict ajv-based consumers assert for the identical input."""
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
