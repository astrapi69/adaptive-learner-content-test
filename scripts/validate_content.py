#!/usr/bin/env python3
"""Content validator for adaptive-learner-content (EXP-039).

This is the SECOND of Adaptive Learner's two validation layers (the app
runs the same checks client-side before a community share). After EXP-039
the **structural** definition of a lesson is App-authoritative: the JSON
Schema under ``schema/lesson.schema.json`` is MIRRORED from the app repo
(generated from its Pydantic model — see ``schema/README.md``) and this
validator FOLLOWS it instead of re-implementing the field rules.

What comes from the mirror (do not duplicate here):
  * **Structure / fields:** validated with the ``jsonschema`` library
    against ``schema/lesson.schema.json`` (required fields, types, enums,
    string lengths, unknown-field rejection via ``additionalProperties``).
  * **Quality minimums:** read from ``schema/quality-rules.json`` so a
    change to that file changes the behaviour (no hardcoded numbers).

What stays here (content-repo specifics the App schema does NOT cover):
  * Language-pair rules (language domain): valid ISO 639-1 ``target`` +
    ``source``, and ``target != source`` for ``domain: language``.
  * Source-language directory structure: a set's ``path`` is
    ``sets/{source_language}/{target}-{level}`` (the ``{target}-{level}``
    folder-name rule is relaxed for non-language domains).
  * Non-Latin source scripts: card backs use that script.
  * Distractor minimums for ``free_text`` / ``picture_choice`` and the
    ``word_tiles`` ``accept_orderings`` permutation check — content-repo
    quality rules that are not expressible in the JSON Schema.

A set's ``domain`` (optional, default ``language``) selects which rules
apply. Non-language sets (e.g. ``domain: psychology``) are material whose
explanation and content share one language, so the language-pair and
``{target}-{level}`` directory rules are relaxed for them.

Exit code 0 when every file passes; 1 with a per-file report otherwise.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator

import generate_search_index

REPO_ROOT = Path(__file__).resolve().parents[1]
SETS_DIR = REPO_ROOT / "sets"
SCHEMA_DIR = REPO_ROOT / "schema"
LESSON_SCHEMA_PATH = SCHEMA_DIR / "lesson.schema.json"
QUALITY_RULES_PATH = SCHEMA_DIR / "quality-rules.json"

ISO_639_1 = re.compile(r"^[a-z]{2}$")

# Scripts we can distinguish from Latin (mirror the TS validator).
SCRIPT_RANGES = {
    "el": re.compile(r"[Ͱ-Ͽἀ-῿]"),
    "ja": re.compile(r"[぀-ヿ一-鿿]"),
    "zh": re.compile(r"[一-鿿]"),
    "ru": re.compile(r"[Ѐ-ӿ]"),
    "ar": re.compile(r"[؀-ۿ]"),
    "ko": re.compile(r"[가-힯]"),
}


def _load_lesson_schema() -> Draft202012Validator:
    if not LESSON_SCHEMA_PATH.is_file():
        raise SystemExit(
            f"FATAL: missing mirrored schema {LESSON_SCHEMA_PATH.relative_to(REPO_ROOT)} "
            "(run scripts/check_schema_drift.py --update)"
        )
    schema = json.loads(LESSON_SCHEMA_PATH.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def _load_quality_rules() -> dict:
    if not QUALITY_RULES_PATH.is_file():
        raise SystemExit(
            f"FATAL: missing mirrored {QUALITY_RULES_PATH.relative_to(REPO_ROOT)} "
            "(run scripts/check_schema_drift.py --update)"
        )
    data = json.loads(QUALITY_RULES_PATH.read_text(encoding="utf-8"))
    return data.get("rules", data)


LESSON_VALIDATOR = _load_lesson_schema()
QUALITY = _load_quality_rules()

# Quality minimums — read from the mirrored quality-rules.json (App-shared).
MIN_EXERCISES = QUALITY["minExercisesPerLesson"]
MIN_TYPES = QUALITY["minExerciseTypes"]
MIN_THEORY = QUALITY["minTheorySteps"]
MIN_FREE_TEXT_ACCEPTS = QUALITY["minFreeTextAccepts"]
MIN_MATCHING_PAIRS = QUALITY["minMatchingPairs"]


def base_lang(code: str) -> str:
    return (code or "").split("-")[0].lower()


def set_domain(content_set: dict) -> str:
    # ``domain`` defaults to "language". Anything else (e.g.
    # "psychology") marks a non-language content set, which relaxes
    # the language-pair and directory-name rules below.
    return (content_set.get("domain") or "language").strip().lower()


def back_looks_like_source(text: str, source: str) -> bool:
    rng = SCRIPT_RANGES.get(base_lang(source))
    if rng is None:
        return True
    return bool(rng.search(text))


def validate_set_meta(content_set: dict, errors: list[str]) -> None:
    sid = content_set.get("id", "?")
    target = base_lang(content_set.get("target_language", ""))
    source = base_lang(content_set.get("source_language", "en"))
    if not target:
        errors.append(f"set {sid}: missing target_language")
    elif not ISO_639_1.match(target):
        errors.append(f"set {sid}: target_language '{target}' is not ISO 639-1")
    if not ISO_639_1.match(source):
        errors.append(f"set {sid}: source_language '{source}' is not ISO 639-1")
    # Non-language sets are material explained in (and written in) the
    # same language, so source == target is expected and allowed.
    if target and source and target == source and set_domain(content_set) == "language":
        errors.append(f"set {sid}: source and target language are identical ('{target}')")
    if not content_set.get("title"):
        errors.append(f"set {sid}: missing title")
    if not content_set.get("title_native"):
        errors.append(f"set {sid}: missing title_native")


def validate_structure(content_set: dict, errors: list[str]) -> None:
    sid = content_set.get("id", "?")
    path = content_set.get("path")
    source = base_lang(content_set.get("source_language", "en"))
    if not path:
        errors.append(f"set {sid}: missing path (source-language tree)")
        return
    parts = path.split("/")
    if len(parts) != 3 or parts[0] != "sets":
        errors.append(f"set {sid}: path '{path}' must be sets/<source>/<target-level>")
        return
    if parts[1] != source:
        errors.append(
            f"set {sid}: path source dir '{parts[1]}' != source_language '{source}'"
        )
    # The target+level directory name must match the metadata, so a
    # set's file location is derivable from (and consistent with) its
    # declared target_language + level. Non-language sets carry a topic
    # folder name (e.g. ``psych-intro``) instead, so this rule is
    # skipped for them.
    target = base_lang(content_set.get("target_language", ""))
    level = (content_set.get("level", "") or "").strip().lower()
    expected_dir = f"{target}-{level}"
    if set_domain(content_set) == "language" and target and level and parts[2] != expected_dir:
        errors.append(
            f"set {sid}: path target dir '{parts[2]}' != expected "
            f"'{expected_dir}' (from target_language '{target}' + level '{level}')"
        )
    if not (REPO_ROOT / path).is_dir():
        errors.append(f"set {sid}: path '{path}' is not a directory")


def validate_lesson_schema(lesson: dict, label: str, errors: list[str]) -> None:
    """Structural validation against the App-authoritative JSON Schema."""
    for err in sorted(LESSON_VALIDATOR.iter_errors(lesson), key=str):
        loc = "/".join(str(p) for p in err.absolute_path) or "<root>"
        errors.append(f"{label}: schema: {loc}: {err.message}")


def lesson_shape_errors(lesson) -> list[str]:
    """Return the structural (schema-shape) errors for one candidate lesson.

    This is the cross-language parity surface for #1208 / #699: the same
    ``schema/lesson.schema.json`` is validated here with ``jsonschema`` and
    on the app side with ``ajv`` (``validateLessonShape``). The shared
    ``tests/fixtures/lesson-shape-parity.json`` pins both validators to the
    SAME accept/reject verdict per input. Empty list == schema-valid shape.
    """
    errors: list[str] = []
    validate_lesson_schema(lesson, "<lesson>", errors)
    return errors


def lesson_shape_ok(lesson) -> bool:
    """True when ``lesson`` matches the App-authoritative lesson SHAPE.

    Parity twin of the app's ``validateLessonShape(lesson).ok``. Only the
    structural schema (fields, types, closed enums, length/range bounds,
    ``additionalProperties: false``) is checked here — the content-repo's
    quality minimums and language-pair rules are a separate, disjoint layer.
    """
    return not lesson_shape_errors(lesson)


def validate_lesson_quality(lesson: dict, source: str, label: str, errors: list[str]) -> None:
    """Quality minimums (from quality-rules.json) + content-repo specifics
    the JSON Schema cannot express."""
    steps = lesson.get("steps", [])
    exercises = [s["exercise"] for s in steps if s.get("type") == "exercise" and s.get("exercise")]
    theory = [s for s in steps if s.get("type") == "theory"]
    types = {e.get("type") for e in exercises}

    if len(exercises) < MIN_EXERCISES:
        errors.append(f"{label}: {len(exercises)} exercises (need >= {MIN_EXERCISES})")
    if len(types) < MIN_TYPES:
        errors.append(f"{label}: {len(types)} exercise type(s) (need >= {MIN_TYPES})")
    if len(theory) < MIN_THEORY:
        errors.append(f"{label}: no theory step")

    # Non-Latin source scripts: card backs must use that script. (Empty
    # front/back is already rejected by the schema's minLength.)
    for card in lesson.get("cards", []):
        back = (card.get("back") or "").strip()
        cid = card.get("id", "?")
        if back and not back_looks_like_source(back, source):
            errors.append(f"{label}: card '{cid}' back is not in {base_lang(source)}")

    for ex in exercises:
        eid = ex.get("id", "?")
        if ex.get("type") == "free_text":
            if len(ex.get("accept") or []) < MIN_FREE_TEXT_ACCEPTS:
                errors.append(f"{label}: free_text '{eid}' needs >= {MIN_FREE_TEXT_ACCEPTS} accepts")
            if not ex.get("distractors"):
                errors.append(f"{label}: free_text '{eid}' needs distractors")
        elif ex.get("type") == "matching":
            if len(ex.get("pairs") or []) < MIN_MATCHING_PAIRS:
                errors.append(f"{label}: matching '{eid}' needs >= {MIN_MATCHING_PAIRS} pairs")
        elif ex.get("type") == "picture_choice":
            if not ex.get("distractors"):
                errors.append(f"{label}: picture_choice '{eid}' needs distractors")
        elif ex.get("type") == "word_tiles":
            # ``accept_orderings`` is OPTIONAL: extra full orderings that
            # are also graded correct (grammatically equivalent
            # rearrangements). The schema types it as number[][]; the
            # PERMUTATION constraint (each tile index exactly once, in
            # range) cannot be expressed in JSON Schema, so it stays here.
            tiles = ex.get("tiles") or []
            orderings = ex.get("accept_orderings")
            if orderings is not None:
                expected = list(range(len(tiles)))
                if not isinstance(orderings, list):
                    errors.append(f"{label}: word_tiles '{eid}' accept_orderings must be a list of index orderings")
                else:
                    for i, order in enumerate(orderings):
                        if (
                            not isinstance(order, list)
                            or not all(isinstance(x, int) and not isinstance(x, bool) for x in order)
                            or sorted(order) != expected
                        ):
                            errors.append(
                                f"{label}: word_tiles '{eid}' accept_orderings[{i}] is not a "
                                f"permutation of tile indices 0..{len(tiles) - 1}"
                            )


def validate_set_dir(content_set: dict, errors: list[str]) -> None:
    sid = content_set.get("id", "?")
    path = content_set.get("path")
    source = content_set.get("source_language", "en")
    if not path:
        return
    set_dir = REPO_ROOT / path
    manifest_path = set_dir / "manifest.yaml"
    if not manifest_path.is_file():
        errors.append(f"set {sid}: missing {path}/manifest.yaml")
        return
    set_manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    lessons = (set_manifest.get("metadata") or {}).get("lessons") or []
    if not lessons:
        errors.append(f"set {sid}: set manifest lists no lessons")
    for filename in lessons:
        lesson_path = set_dir / "lessons" / filename
        if not lesson_path.is_file():
            errors.append(f"set {sid}: lesson file '{filename}' is missing")
            continue
        try:
            lesson = json.loads(lesson_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            errors.append(f"set {sid}: {filename} is invalid JSON: {exc}")
            continue
        label = f"{sid}/{filename}"
        validate_lesson_schema(lesson, label, errors)
        validate_lesson_quality(lesson, source, label, errors)


def validate() -> int:
    root_manifest = REPO_ROOT / "manifest.yaml"
    if not root_manifest.is_file():
        print("FAIL: no root manifest.yaml", file=sys.stderr)
        return 1
    manifest = yaml.safe_load(root_manifest.read_text(encoding="utf-8"))
    sets = manifest.get("sets") or []
    if not sets:
        print("FAIL: root manifest lists no sets", file=sys.stderr)
        return 1

    all_errors: list[str] = []
    for content_set in sets:
        errors: list[str] = []
        validate_set_meta(content_set, errors)
        validate_structure(content_set, errors)
        validate_set_dir(content_set, errors)
        sid = content_set.get("id", "?")
        if errors:
            print(f"FAIL {sid}:")
            for e in errors:
                print(f"  - {e}")
            all_errors.extend(errors)
        else:
            print(f"PASS {sid}")

    if all_errors:
        print(f"\n{len(all_errors)} validation error(s).", file=sys.stderr)
        return 1
    print(f"\nAll {len(sets)} set(s) passed validation.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate the content tree.")
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--generate-index",
        action="store_true",
        help="(re)generate search-index.json via generate_search_index.py",
    )
    group.add_argument(
        "--check-index",
        action="store_true",
        help="verify search-index.json is up to date; exit 1 if stale",
    )
    args = parser.parse_args()

    if args.generate_index:
        return generate_search_index.main([])
    if args.check_index:
        return generate_search_index.main(["--check"])
    return validate()


if __name__ == "__main__":
    sys.exit(main())
