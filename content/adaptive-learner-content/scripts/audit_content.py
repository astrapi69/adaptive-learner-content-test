#!/usr/bin/env python3
"""Content quality audit for adaptive-learner-content.

A *reporting* companion to ``validate_content.py``. The validator
enforces the hard quality gate (and fails CI); this audit hunts for the
softer quality problems a schema check can miss and prints them as a
table so they can be fixed:

  * duplicate cards within a lesson (same front, or same front/back pair)
  * empty / whitespace-only fields (card front/back, prompts, theory
    body, titles, matching pair sides): the schema's ``minLength`` lets a
    string of spaces through
  * lessons missing in their set manifest, or set fields missing

Not here, because the engine gate (validate_with_engine.mjs) blocks on them,
and one rule lives in one place: malformed answer sets (cloze markers and
blanks, multiselect accept/distractors, word_tiles with fewer than two tiles,
picture_choice without exactly one correct image, a repeated matching left
term, a free_text answer that is also a distractor (#237, 0.35.0)),
duplicate card, step and exercise ids (learn-content-engine#202), and the
quality minimums such as matching pairs and free_text accepts (#185, keyed to
a lesson's ``purpose``). The distractor requirement on free_text and
picture_choice was dropped by the same decision.

Exit code is always 0 - this is advisory. ``--strict`` makes it exit 1
when any finding is reported (handy in CI once the tree is clean).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]


def is_blank(x) -> bool:
    return not (isinstance(x, str) and x.strip())


def audit_lesson(lesson: dict, label: str, findings: list[tuple]):
    def add(problem, fix):
        findings.append((label, problem, fix))

    cards = lesson.get("cards", []) or []
    # --- duplicate / empty cards -------------------------------------
    seen_front, seen_pair = {}, {}
    card_by_front = {}
    for c in cards:
        cid = c.get("id", "?")
        front = (c.get("front") or "").strip()
        back = (c.get("back") or "").strip()
        if is_blank(c.get("front")) or is_blank(c.get("back")):
            add(f"card '{cid}' has empty front/back", "fill both fields")
        card_by_front[front.lower()] = back
        if front and front.lower() in seen_front:
            add(f"duplicate card front '{front}' (ids {seen_front[front.lower()]}, {cid})",
                "remove/merge the duplicate card")
        seen_front[front.lower()] = cid
        key = (front.lower(), back.lower())
        if front and key in seen_pair:
            add(f"duplicate card front/back pair '{front}'->'{back}'", "remove duplicate")
        seen_pair[key] = cid

    # --- steps: ids, theory, exercises -------------------------------
    steps = lesson.get("steps", []) or []
    for s in steps:
        sid = s.get("id", "?")
        if s.get("type") == "theory":
            if is_blank(s.get("body")):
                add(f"theory step '{sid}' has empty body", "add Markdown body")
            if is_blank(s.get("title")):
                add(f"theory step '{sid}' has empty title", "add a title")

    exercises = [s.get("exercise") for s in steps
                 if s.get("type") == "exercise" and s.get("exercise")]
    for ex in exercises:
        eid = ex.get("id", "?")
        etype = ex.get("type", "?")
        if is_blank(ex.get("prompt")):
            add(f"exercise '{eid}' ({etype}) has empty prompt", "add a prompt")

        if etype == "matching":
            for p in ex.get("pairs") or []:
                if is_blank(p.get("left")) or is_blank(p.get("right")):
                    add(f"matching '{eid}' has an empty pair side", "fill left/right")
                # NB: we deliberately do NOT cross-check the pair's right side
                # against the card gloss - matching exercises legitimately pair
                # a word with its article / gender / category, not its dictionary
                # translation, so such a check is all false positives.


def main() -> int:
    strict = "--strict" in sys.argv
    manifest = yaml.safe_load((REPO_ROOT / "manifest.yaml").read_text(encoding="utf-8"))
    findings: list[tuple] = []
    lessons_scanned = 0
    for cs in manifest.get("sets", []) or []:
        sid = cs.get("id", "?")
        # required set fields
        for field in ("source_language", "target_language", "level"):
            if is_blank(cs.get(field)):
                findings.append((sid, f"set missing '{field}'", f"add {field}"))
        path = cs.get("path")
        if not path:
            continue
        set_manifest = yaml.safe_load((REPO_ROOT / path / "manifest.yaml").read_text(encoding="utf-8"))
        listed = (set_manifest.get("metadata") or {}).get("lessons") or []
        for fn in listed:
            lf = REPO_ROOT / path / "lessons" / fn
            if not lf.is_file():
                findings.append((f"{sid}/{fn}", "listed lesson file missing", "add or delist"))
                continue
            try:
                lesson = json.loads(lf.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                findings.append((f"{sid}/{fn}", f"invalid JSON: {exc}", "fix JSON"))
                continue
            lessons_scanned += 1
            audit_lesson(lesson, f"{sid}/{fn}", findings)

    print(f"Scanned {lessons_scanned} lesson(s) across "
          f"{len(manifest.get('sets', []))} set(s).\n")
    if not findings:
        print("No quality issues found. ✓")
        return 0
    # table
    w0 = max(len(f[0]) for f in findings)
    w1 = max(len(f[1]) for f in findings)
    print(f"{'Set/Lesson'.ljust(w0)} | {'Problem'.ljust(w1)} | Fix")
    print(f"{'-'*w0}-+-{'-'*w1}-+-{'-'*20}")
    for loc, problem, fix in findings:
        print(f"{loc.ljust(w0)} | {problem.ljust(w1)} | {fix}")
    print(f"\n{len(findings)} finding(s).")
    return 1 if strict else 0


if __name__ == "__main__":
    sys.exit(main())
