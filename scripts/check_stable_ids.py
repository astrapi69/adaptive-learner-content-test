#!/usr/bin/env python3
"""Stability gate for stable_id (engine#90) plus the coverage ratchet.

The schema can demand presence, format and per-document uniqueness; it can
NEVER see whether an id stayed the same across versions, because that needs
the previous state. This gate closes that half of the promise:

1. STABILITY against the last published state (the merge base with
   ``origin/main``; main IS the published state - the official repo is
   branch-tracked in the registry, and every alc pin points at a main
   commit, so a promise over main history carries to the pins):
   - V1: a stable_id present in the base disappeared from the head.
     Deliberate retirement via ``retired_ids`` stays LOCKED until
     adaptive-learner#2188 lands (the engine validator rejects the list,
     E-RETIRED-IDS-LOCKED), so today every disappearance is a violation.
   - V2: a stable_id is used more than once set-wide in the head.
   - V3: a stable_id moved to a different KIND or exercise type
     (id-reuse smell: an exercise became a card, a matching became cloze).
   - V4: a lesson file present in the base is gone from the head while its
     set survives (the filename IS the lesson identity for progress/SRS).
2. COVERAGE RATCHET: n of m sets are FULLY covered (every exercise and
   card in every lesson carries a stable_id; half a set is half a
   promise). The committed baseline (``schema/stable-id-coverage.txt``)
   may only be crossed deliberately: computed < baseline is a regression,
   computed > baseline demands a conscious baseline raise. Both are red.

Test contract: the run prints the checked quantities (sets, base ids,
head ids) and FAILS when the base lists sets but yields zero ids while
claiming coverage, so a run over nothing never passes. ``--self-test``
seeds one violation per class in a temp tree and proves every detector
fires (a green run of a blind gate is worthless).

Usage:
    python3 scripts/check_stable_ids.py               # gate against merge-base with origin/main
    python3 scripts/check_stable_ids.py --self-test   # seeded negative controls
    BASE_REF=<ref> overrides the comparison base (CI uses the PR base).
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
COVERAGE_BASELINE = REPO_ROOT / "schema" / "stable-id-coverage.txt"


def git(*args: str, cwd: Path | None = None) -> str:
    # cwd resolves at CALL time: --gate-cwd rebinds REPO_ROOT after import,
    # and a definition-time default would keep pointing at the old root.
    return subprocess.check_output(["git", *args], cwd=cwd or REPO_ROOT, text=True)


def base_ref() -> str:
    override = os.environ.get("BASE_REF")
    if override:
        return override
    try:
        return git("merge-base", "HEAD", "origin/main").strip()
    except subprocess.CalledProcessError:
        return git("merge-base", "HEAD", "main").strip()


def lesson_files_of_tree(ref: str | None) -> list[str]:
    """Repo-relative lesson JSON paths at ``ref`` (None = working tree)."""
    if ref is None:
        out = git("ls-files", "--cached", "--others", "--exclude-standard", "sets/*/*/lessons/*.json")
        # ls-files lists the INDEX; a deleted-but-unstaged lesson would still
        # appear and explode the reader. Filter to what exists: the deletion
        # itself surfaces as V4 via the base/head comparison.
        return [
            line
            for line in out.split()
            if line.endswith(".json") and "/lessons/" in line and (REPO_ROOT / line).is_file()
        ]
    out = git("ls-tree", "-r", "--name-only", ref, "sets/")
    return [line for line in out.split() if line.endswith(".json") and "/lessons/" in line]


def read_at(ref: str | None, rel_path: str) -> str:
    if ref is None:
        return (REPO_ROOT / rel_path).read_text(encoding="utf-8")
    return git("show", f"{ref}:{rel_path}")


def set_of(rel_path: str) -> str:
    # sets/<lang>/<set>/lessons/<file>.json -> sets/<lang>/<set>
    return "/".join(rel_path.split("/")[:3])


def inventory(ref: str | None) -> dict[str, dict[str, tuple[str, str, str]]]:
    """Per set: stable_id -> (kind, type, lesson filename)."""
    sets: dict[str, dict[str, tuple[str, str, str]]] = {}
    for rel_path in lesson_files_of_tree(ref):
        lesson = json.loads(read_at(ref, rel_path))
        set_key = set_of(rel_path)
        bucket = sets.setdefault(set_key, {})
        filename = rel_path.split("/")[-1]
        for card in lesson.get("cards") or []:
            sid = card.get("stable_id")
            if sid:
                bucket.setdefault(sid, ("card", "card", filename))
        for step in lesson.get("steps") or []:
            exercise = step.get("exercise")
            if exercise and exercise.get("stable_id"):
                bucket.setdefault(
                    exercise["stable_id"],
                    ("exercise", exercise.get("type", "?"), filename),
                )
    return sets


def duplicates_in_head() -> list[str]:
    """V2: set-wide duplicates in the working tree (first-write-wins above
    hides them, so count directly)."""
    problems: list[str] = []
    per_set: dict[str, dict[str, list[str]]] = {}
    for rel_path in lesson_files_of_tree(None):
        lesson = json.loads(read_at(None, rel_path))
        seen = per_set.setdefault(set_of(rel_path), {})
        for card in lesson.get("cards") or []:
            if card.get("stable_id"):
                seen.setdefault(card["stable_id"], []).append(f"{rel_path} card {card.get('id')}")
        for step in lesson.get("steps") or []:
            exercise = step.get("exercise")
            if exercise and exercise.get("stable_id"):
                seen.setdefault(exercise["stable_id"], []).append(
                    f"{rel_path} exercise {exercise.get('id')}"
                )
    for set_key, seen in per_set.items():
        for sid, places in seen.items():
            if len(places) > 1:
                problems.append(f"V2 {set_key}: stable_id '{sid}' mehrfach: {'; '.join(places)}")
    return problems


def coverage_of_head() -> tuple[int, int]:
    """(fully covered sets, total sets listed in the root manifest)."""
    manifest = yaml.safe_load((REPO_ROOT / "manifest.yaml").read_text(encoding="utf-8")) or {}
    root_sets = manifest.get("sets") or []
    covered = 0
    for root_set in root_sets:
        set_dir = REPO_ROOT / (root_set.get("path") or "")
        set_manifest_path = set_dir / "manifest.yaml"
        if not set_manifest_path.is_file():
            continue
        set_manifest = yaml.safe_load(set_manifest_path.read_text(encoding="utf-8")) or {}
        lesson_names = (set_manifest.get("metadata") or {}).get("lessons") or []
        if not lesson_names:
            continue
        full = True
        for name in lesson_names:
            lesson_path = set_dir / "lessons" / name
            if not lesson_path.is_file():
                full = False
                break
            lesson = json.loads(lesson_path.read_text(encoding="utf-8"))
            for card in lesson.get("cards") or []:
                if not card.get("stable_id"):
                    full = False
            for step in lesson.get("steps") or []:
                exercise = step.get("exercise")
                if exercise and not exercise.get("stable_id"):
                    full = False
        if full:
            covered += 1
    return covered, len(root_sets)


def run_gate() -> int:
    ref = base_ref()
    base = inventory(ref)
    head = inventory(None)
    problems: list[str] = []

    base_ids = sum(len(bucket) for bucket in base.values())
    head_ids = sum(len(bucket) for bucket in head.values())

    for set_key, base_bucket in base.items():
        head_bucket = head.get(set_key, {})
        for sid, (kind, ex_type, filename) in base_bucket.items():
            if sid not in head_bucket:
                problems.append(
                    f"V1 {set_key}: stable_id '{sid}' ({kind} in {filename}) ist verschwunden; "
                    "Ausmusterung ist bis adaptive-learner#2188 gesperrt"
                )
            else:
                head_kind, head_type, _ = head_bucket[sid]
                if head_kind != kind or head_type != ex_type:
                    problems.append(
                        f"V3 {set_key}: stable_id '{sid}' wechselte {kind}/{ex_type} -> "
                        f"{head_kind}/{head_type} (Wiederverwendungs-Verdacht)"
                    )

    problems.extend(duplicates_in_head())

    base_lessons = {(set_of(p), p.split("/")[-1]) for p in lesson_files_of_tree(ref)}
    head_lessons = {(set_of(p), p.split("/")[-1]) for p in lesson_files_of_tree(None)}
    head_sets = {set_key for set_key, _ in head_lessons}
    for set_key, filename in sorted(base_lessons - head_lessons):
        if set_key in head_sets:
            problems.append(
                f"V4 {set_key}: Lektionsdatei '{filename}' fehlt im Head; der Dateiname ist die "
                "Lektions-Identitaet fuer Fortschritt/SRS"
            )

    covered, total_sets = coverage_of_head()
    baseline = int(COVERAGE_BASELINE.read_text(encoding="utf-8").strip()) if COVERAGE_BASELINE.is_file() else 0

    print(
        f"stable-id gate: Basis {ref[:7] if len(ref) >= 7 else ref}, Sets Basis/Head "
        f"{len(base)}/{len(head)}, Ids Basis/Head {base_ids}/{head_ids}"
    )
    print(f"Abdeckung: {covered} von {total_sets} Sets voll abgedeckt, Baseline {baseline}")

    if total_sets == 0:
        print("FAIL: 0 Sets im Root-Manifest; ein Lauf ueber nichts besteht nie")
        return 1
    if covered > 0 and head_ids == 0:
        print("FAIL: Abdeckung behauptet, aber 0 Ids gezaehlt (blinder Zaehler?)")
        return 1
    if covered < baseline:
        problems.append(f"RATCHET {covered} < Baseline {baseline}: Rueckschritt")
    if covered > baseline:
        problems.append(
            f"RATCHET {covered} > Baseline {baseline}: Baseline bewusst anheben "
            f"({COVERAGE_BASELINE.relative_to(REPO_ROOT)})"
        )

    if problems:
        print(f"FAIL ({len(problems)} Verstoss/Verstoesse):")
        for problem in problems:
            print(f"  {problem}")
        return 1
    print("OK: Stabilitaet gehalten, Abdeckung == Baseline")
    return 0


def self_test() -> int:
    """Seed one violation per class in a temp repo and prove each detector
    fires. A gate whose detectors were never seen firing is a blind gate."""
    failures: list[str] = []

    def scenario(name: str, mutate, expect_marker: str) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            subprocess.run(["git", "init", "-q", "-b", "main", tmp], check=True)
            lessons = tmp_path / "sets/de/demo/lessons"
            lessons.mkdir(parents=True)
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
            (lessons / "01-demo.json").write_text(json.dumps(lesson), encoding="utf-8")
            (tmp_path / "sets/de/demo/manifest.yaml").write_text(
                "schema_version: '1.3'\nname: Demo\nsets:\n  - id: demo\n"
                "metadata:\n  lessons:\n    - 01-demo.json\n",
                encoding="utf-8",
            )
            (tmp_path / "manifest.yaml").write_text(
                "schema_version: '1.2'\nname: Demo\nsets:\n  - id: demo\n    path: sets/de/demo\n",
                encoding="utf-8",
            )
            (tmp_path / "schema").mkdir()
            (tmp_path / "schema/stable-id-coverage.txt").write_text("1\n", encoding="utf-8")
            subprocess.run(["git", "-C", tmp, "add", "-A"], check=True)
            subprocess.run(
                ["git", "-C", tmp, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "base"],
                check=True,
            )
            mutate(tmp_path, lesson, lessons)
            env = dict(os.environ, BASE_REF="main")
            proc = subprocess.run(
                [sys.executable, str(Path(__file__).resolve()), "--gate-cwd", tmp],
                capture_output=True,
                text=True,
                env=env,
            )
            if proc.returncode == 0 or expect_marker not in proc.stdout:
                failures.append(
                    f"{name}: Detektor feuerte NICHT (exit={proc.returncode})\n"
                    f"stdout: {proc.stdout}\nstderr: {proc.stderr[-400:]}"
                )
            else:
                print(f"self-test OK: {name}")

    def v1(tmp_path: Path, lesson: dict, lessons: Path) -> None:
        lesson["steps"] = []
        (lessons / "01-demo.json").write_text(json.dumps(lesson), encoding="utf-8")

    def v2(tmp_path: Path, lesson: dict, lessons: Path) -> None:
        lesson["cards"][0]["stable_id"] = "ex-selftest001"
        (lessons / "01-demo.json").write_text(json.dumps(lesson), encoding="utf-8")

    def v3(tmp_path: Path, lesson: dict, lessons: Path) -> None:
        lesson["steps"][0]["exercise"]["type"] = "cloze"
        lesson["steps"][0]["exercise"]["sentence"] = "a ___"
        lesson["steps"][0]["exercise"]["blanks"] = [{"accept": ["a"]}]
        (lessons / "01-demo.json").write_text(json.dumps(lesson), encoding="utf-8")

    def v4(tmp_path: Path, lesson: dict, lessons: Path) -> None:
        (lessons / "01-demo.json").unlink()
        (lessons / "02-neu.json").write_text(json.dumps(lesson), encoding="utf-8")

    def ratchet_down(tmp_path: Path, lesson: dict, lessons: Path) -> None:
        del lesson["cards"][0]["stable_id"]
        (lessons / "01-demo.json").write_text(json.dumps(lesson), encoding="utf-8")

    scenario("V1 verschwundene Id", v1, "V1 ")
    scenario("V2 Duplikat set-weit", v2, "V2 ")
    scenario("V3 Typwechsel", v3, "V3 ")
    scenario("V4 Datei-Umbenennung", v4, "V4 ")
    scenario("RATCHET Rueckschritt", ratchet_down, "RATCHET")

    if failures:
        print("SELF-TEST FAIL:")
        for failure in failures:
            print(failure)
        return 1
    print("Self-test passed: alle 5 Detektoren feuern auf geseedete Verstoesse.")
    return 0


if __name__ == "__main__":
    if "--gate-cwd" in sys.argv:
        REPO_ROOT = Path(sys.argv[sys.argv.index("--gate-cwd") + 1]).resolve()
        COVERAGE_BASELINE = REPO_ROOT / "schema" / "stable-id-coverage.txt"
        sys.exit(run_gate())
    if "--self-test" in sys.argv:
        sys.exit(self_test())
    sys.exit(run_gate())
