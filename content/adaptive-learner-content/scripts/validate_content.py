#!/usr/bin/env python3
"""Content validator for adaptive-learner-content (EXP-039).

This is the SECOND of Adaptive Learner's two validation layers (the app
runs the same checks client-side before a community share). The
**structural** definition of a lesson is canonical: the JSON Schema under
``schema/lesson.schema.json`` is MIRRORED from the pinned
learn-content-engine release (source-of-truth chain: engine
(canonical) → this mirror - see ``schema/README.md``) and this
validator FOLLOWS it instead of re-implementing the field rules. It reads
only the vendored mirror, so validation works fully offline.

What comes from the mirror (do not duplicate here):
  * **Structure / fields:** validated with the ``jsonschema`` library
    against ``schema/lesson.schema.json`` (required fields, types, enums,
    string lengths, unknown-field rejection via ``additionalProperties``).

What stays here (what the engine cannot see, because it needs the file
system):
  * Source-language directory structure: a set's ``path`` is
    ``sets/{source_language}/{target}-{level}`` (the ``{target}-{level}``
    folder-name rule is relaxed for non-language domains), the set manifest
    exists and lists lesson files that exist and parse.

What the engine owns (``scripts/validate_with_engine.mjs``, the engine gate):
every rule about the content itself. The semantic rules, the quality
minimums keyed to a lesson's ``purpose`` (``validateLessonQuality``,
learn-content-engine#185), the language tags, language pair, ``title_native``
and the script of card backs (#190), unique card, step and exercise ids
(#202), and the ``accept_orderings`` permutation (``E-TILES-ORDERING``). This
validator kept copies of several of them; they moved to the engine, and the
distractor requirement on ``free_text`` / ``picture_choice`` was dropped there
by decision (#185).

A set's ``domain`` (optional, default ``language``) relaxes the
``{target}-{level}`` directory rule for non-language sets (e.g.
``domain: psychology``), whose folder carries a topic name instead.

Exit code 0 when every file passes; 1 with a per-file report otherwise.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml
from lce_schema import build_validator

import generate_search_index

REPO_ROOT = Path(__file__).resolve().parents[1]
SETS_DIR = REPO_ROOT / "sets"
SCHEMA_DIR = REPO_ROOT / "schema"
LESSON_SCHEMA_PATH = SCHEMA_DIR / "lesson.schema.json"


def _load_lesson_schema():
    if not LESSON_SCHEMA_PATH.is_file():
        raise SystemExit(
            f"FATAL: missing mirrored schema {LESSON_SCHEMA_PATH.relative_to(REPO_ROOT)} "
            "(run scripts/check_schema_drift.py --update)"
        )
    schema = json.loads(LESSON_SCHEMA_PATH.read_text(encoding="utf-8"))
    # Built through the engine's shipped helper (scripts/lce_schema.py,
    # mirrored from the pinned release): the slug pattern uses Unicode
    # property escapes that Python's built-in ``re`` cannot compile, so a
    # plain Draft202012Validator dies on the schema itself.
    return build_validator(schema)


LESSON_VALIDATOR = _load_lesson_schema()


def base_lang(code: str) -> str:
    return (code or "").split("-")[0].lower()


def set_domain(content_set: dict) -> str:
    # ``domain`` defaults to "language". Anything else (e.g.
    # "psychology") marks a non-language content set, which relaxes
    # the directory-name rule below.
    return (content_set.get("domain") or "language").strip().lower()


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
    """Structural validation against the canonical (engine-mirrored) JSON Schema."""
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
    """True when ``lesson`` matches the canonical lesson SHAPE.

    Parity twin of the app's ``validateLessonShape(lesson).ok``. Only the
    structural schema (fields, types, closed enums, length/range bounds,
    ``additionalProperties: false``) is checked here - the engine's rules
    (semantic rules, quality minimums, language rules) are a separate layer.
    """
    return not lesson_shape_errors(lesson)


def validate_set_dir(content_set: dict, errors: list[str]) -> None:
    sid = content_set.get("id", "?")
    path = content_set.get("path")
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
