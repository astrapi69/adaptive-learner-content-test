#!/usr/bin/env python3
"""Coverage ratchet for stable_id (engine#90).

The STABILITY half (does a published id still point at its element?) is not
here: it ships with the pinned engine as ``learn-content-engine
check-stable-ids`` and is called from ``make stable-ids``. Ten vendored
copies would drift; one shipped command does not.

What stays repo-local is the COVERAGE number, because it is a property of
this repository: how many of its sets are FULLY minted (every exercise and
card in every lesson carries a stable_id; half a set is half a promise).
The committed baseline (``schema/stable-id-coverage.txt``) may only be
crossed deliberately: computed < baseline is a regression, computed >
baseline demands a conscious raise. Both are red.

The run prints the checked quantities, and a repo whose manifest lists no
sets fails rather than reporting full coverage over nothing.

    python3 scripts/check_stable_id_coverage.py
    python3 scripts/check_stable_id_coverage.py --self-test
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
BASELINE = REPO_ROOT / "schema" / "stable-id-coverage.txt"


def set_fully_minted(set_dir: Path) -> bool:
    manifest_path = set_dir / "manifest.yaml"
    if not manifest_path.is_file():
        return False
    set_manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
    lesson_names = (set_manifest.get("metadata") or {}).get("lessons") or []
    if not lesson_names:
        return False
    for name in lesson_names:
        lesson_path = set_dir / "lessons" / name
        if not lesson_path.is_file():
            return False
        lesson = json.loads(lesson_path.read_text(encoding="utf-8"))
        for card in lesson.get("cards") or []:
            if not card.get("stable_id"):
                return False
        for step in lesson.get("steps") or []:
            exercise = step.get("exercise")
            if exercise and not exercise.get("stable_id"):
                return False
    return True


def coverage(repo_root: Path) -> tuple[int, int]:
    manifest = yaml.safe_load((repo_root / "manifest.yaml").read_text(encoding="utf-8")) or {}
    root_sets = manifest.get("sets") or []
    covered = sum(
        1 for s in root_sets if s.get("path") and set_fully_minted(repo_root / s["path"])
    )
    return covered, len(root_sets)


def gate(repo_root: Path, baseline_path: Path) -> int:
    covered, total = coverage(repo_root)
    baseline = int(baseline_path.read_text(encoding="utf-8").strip()) if baseline_path.is_file() else 0
    print(f"stable-id coverage: {covered} of {total} set(s) fully minted, baseline {baseline}")
    if total == 0:
        print("FAIL: the root manifest lists no sets; a run over nothing is never fully covered")
        return 1
    if covered < baseline:
        print(f"FAIL: coverage {covered} below baseline {baseline} (regression)")
        return 1
    if covered > baseline:
        print(f"FAIL: coverage {covered} above baseline {baseline}; raise it deliberately in {baseline_path.name}")
        return 1
    print("OK: coverage equals the baseline")
    return 0


def self_test() -> int:
    """Prove the three red paths fire; a ratchet nobody saw trip is decoration."""
    failures = []
    lesson = {
        "id": "l1",
        "title": "L1",
        "cards": [{"id": "c1", "front": "f", "back": "b", "stable_id": "card-selftest01"}],
        "steps": [
            {
                "id": "s1",
                "type": "exercise",
                "exercise": {
                    "id": "e1",
                    "type": "free_text",
                    "prompt": "p",
                    "accept": ["a"],
                    "stable_id": "ex-selftest001",
                },
            }
        ],
    }

    def build(tmp: Path, minted: bool, with_sets: bool = True) -> None:
        (tmp / "schema").mkdir(parents=True, exist_ok=True)
        if not with_sets:
            (tmp / "manifest.yaml").write_text("name: Leer\nsets: []\n", encoding="utf-8")
            return
        lessons = tmp / "sets/de/demo/lessons"
        lessons.mkdir(parents=True, exist_ok=True)
        payload = json.loads(json.dumps(lesson))
        if not minted:
            del payload["cards"][0]["stable_id"]
            del payload["steps"][0]["exercise"]["stable_id"]
        (lessons / "01-demo.json").write_text(json.dumps(payload), encoding="utf-8")
        (tmp / "sets/de/demo/manifest.yaml").write_text(
            "name: Demo\nsets:\n  - id: demo\nmetadata:\n  lessons:\n    - 01-demo.json\n",
            encoding="utf-8",
        )
        (tmp / "manifest.yaml").write_text(
            "name: Demo\nsets:\n  - id: demo\n    path: sets/de/demo\n", encoding="utf-8"
        )

    scenarios = [
        ("regression (minted 0, baseline 1)", False, True, "1", "below baseline"),
        ("undeclared raise (minted 1, baseline 0)", True, True, "0", "above baseline"),
        ("no sets at all", True, False, "0", "lists no sets"),
    ]
    for name, minted, with_sets, baseline_value, marker in scenarios:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            build(tmp_path, minted, with_sets)
            baseline_path = tmp_path / "schema" / "stable-id-coverage.txt"
            baseline_path.write_text(f"{baseline_value}\n", encoding="utf-8")
            import io
            import contextlib

            buffer = io.StringIO()
            with contextlib.redirect_stdout(buffer):
                code = gate(tmp_path, baseline_path)
            if code == 0 or marker not in buffer.getvalue():
                failures.append(f"{name}: did not fire (exit={code})\n{buffer.getvalue()}")
            else:
                print(f"self-test OK: {name}")

    # Positive control: a matching baseline must PASS, or the gate is just
    # always-red and proves nothing.
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        build(tmp_path, True, True)
        baseline_path = tmp_path / "schema" / "stable-id-coverage.txt"
        baseline_path.write_text("1\n", encoding="utf-8")
        if gate(tmp_path, baseline_path) != 0:
            failures.append("positive control: a matching baseline was not accepted")
        else:
            print("self-test OK: positive control (baseline matches)")

    if failures:
        print("SELF-TEST FAIL:")
        for failure in failures:
            print(failure)
        return 1
    print("Self-test passed: every ratchet path fires, and a matching baseline passes.")
    return 0


if __name__ == "__main__":
    sys.exit(self_test() if "--self-test" in sys.argv else gate(REPO_ROOT, BASELINE))
