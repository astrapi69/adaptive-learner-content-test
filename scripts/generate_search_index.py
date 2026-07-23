#!/usr/bin/env python3
"""Generate ``search-index.json`` from the repo's content manifests.

The search index is a flat, machine-readable catalogue of every content
set in the repo. It is consumed by Adaptive Learner's *multi-repo
discovery*: the app loads the index from each recommended repo in
parallel and searches across all of them, without having to clone or
walk the full content tree.

The index is **always generated, never hand-edited** (see CI workflow
``.github/workflows/generate-index.yml``). Run it after changing any
manifest or lesson:

    python3 scripts/generate_search_index.py            # (re)write index
    python3 scripts/generate_search_index.py --check    # exit 1 if stale

It is intentionally self-contained (stdlib + PyYAML) and repo-agnostic,
so the same script drops into the official content repo and this
test/starter repo unchanged. Per set it derives:

  * ``id``/``name``/``description`` from the root + set manifest
  * ``source_language`` / ``target_language`` / ``level`` / ``domain``
  * ``lesson_count`` — lessons listed in the set manifest
  * ``card_count`` — EXACT sum of ``cards[]`` over every lesson file
  * ``tags``        — from the manifest, else ``[]``
  * ``visibility``  — consumer-display hint (engine schema 1.8);
    absent or out-of-enum normalizes to ``"visible"``
  * ``ai_validated``— ``true`` if the set/lesson carries an
    ``ai_validation`` block
  * ``trust_level`` — from ``recommended-repos.json``, else ``1``
  * ``book``        — from the manifest, else ``null``
  * ``updated_at``  — ``git log -1 --format=%cI`` for the set directory
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
INDEX_PATH = REPO_ROOT / "search-index.json"
SCHEMA_VERSION = "1.0"
DEFAULT_TRUST_LEVEL = 1
VISIBILITY_VALUES = ("visible", "hidden")


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def slug_from_url(url: str) -> str | None:
    """Return ``owner/repo`` from a git remote URL, or ``None``.

    Handles the https form, the scp-like SSH form
    (``git@host:owner/repo``, #87: the colon separates host and owner
    and must not survive into the slug) and the ``ssh://`` form, each
    with or without a ``.git`` suffix or trailing slash.
    """
    slug = url.strip().rstrip("/")
    if slug.endswith(".git"):
        slug = slug[: -len(".git")]
    if "://" not in slug and ":" in slug:
        slug = slug.replace(":", "/", 1)
    parts = [p for p in slug.split("/") if p]
    if len(parts) >= 2:
        return f"{parts[-2]}/{parts[-1]}"
    return None


def repo_slug() -> str:
    """Return ``owner/repo`` derived from the git remote (fallback: dir)."""
    try:
        url = subprocess.check_output(
            ["git", "-C", str(REPO_ROOT), "config", "--get", "remote.origin.url"],
            text=True,
        ).strip()
    except (subprocess.CalledProcessError, OSError):
        url = ""
    if not url:
        return REPO_ROOT.name
    return slug_from_url(url) or REPO_ROOT.name


def git_updated_at(path: Path) -> str | None:
    """ISO-8601 commit date of the last change touching ``path``."""
    try:
        out = subprocess.check_output(
            ["git", "-C", str(REPO_ROOT), "log", "-1", "--format=%cI", "--", str(path)],
            text=True,
        ).strip()
    except (subprocess.CalledProcessError, OSError):
        return None
    return out or None


def load_yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def load_recommended_trust() -> dict[str, int]:
    """Map ``owner/repo`` -> trust_level from ``recommended-repos.json``.

    The file is optional; absent it, every repo defaults to
    ``DEFAULT_TRUST_LEVEL``. Both a top-level list and a ``{"repos": [...]}``
    wrapper are accepted, and a repo entry may key its slug under
    ``repo``, ``slug``, ``name`` or ``full_name``.
    """
    path = REPO_ROOT / "recommended-repos.json"
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    entries = data.get("repos") if isinstance(data, dict) else data
    trust: dict[str, int] = {}
    for entry in entries or []:
        if not isinstance(entry, dict):
            continue
        slug = entry.get("repo") or entry.get("slug") or entry.get("name") or entry.get("full_name")
        level = entry.get("trust_level", entry.get("trust"))
        if slug and level is not None:
            trust[str(slug)] = int(level)
    return trust


def normalize_visibility(raw_visibility: object) -> str:
    """Engine-parity projection of the manifest ``visibility`` flag.

    Mirrors ``asContentSetEntry`` in learn-content-engine 0.14.0: absent
    or out-of-enum values fold back to ``"visible"``, so consumers can
    filter on the field without their own defaulting.
    """
    return raw_visibility if raw_visibility in VISIBILITY_VALUES else "visible"


def has_ai_validation(set_manifest: dict, lessons: list[dict]) -> bool:
    if set_manifest.get("ai_validation"):
        return True
    if isinstance(set_manifest.get("metadata"), dict) and set_manifest["metadata"].get("ai_validation"):
        return True
    return any(isinstance(l, dict) and l.get("ai_validation") for l in lessons)


# --------------------------------------------------------------------------- #
# Index building
# --------------------------------------------------------------------------- #
def build_set_entry(root_set: dict) -> tuple[dict, list[str]]:
    """Return ``(entry, errors)`` for one root-manifest set."""
    errors: list[str] = []
    sid = root_set.get("id", "?")
    path = root_set.get("path")
    if not path:
        return {}, [f"set {sid}: missing path"]

    set_dir = REPO_ROOT / path
    set_manifest_path = set_dir / "manifest.yaml"
    set_manifest: dict = {}
    if set_manifest_path.is_file():
        set_manifest = load_yaml(set_manifest_path)
    else:
        errors.append(f"set {sid}: missing {path}/manifest.yaml")

    # Prefer the richer set-manifest entry, fall back to the root entry.
    inner_sets = set_manifest.get("sets") or []
    inner = next((s for s in inner_sets if s.get("id") == sid), inner_sets[0] if inner_sets else {})
    merged = {**root_set, **{k: v for k, v in inner.items() if v is not None}}

    # Lessons: the set manifest's metadata.lessons is the source of truth.
    lesson_files = (set_manifest.get("metadata") or {}).get("lessons") or []
    lesson_count = len(lesson_files) if lesson_files else int(merged.get("lesson_count", 0) or 0)

    # card_count: open every lesson and count cards[] EXACTLY.
    card_count = 0
    lessons: list[dict] = []
    for filename in lesson_files:
        lesson_path = set_dir / "lessons" / filename
        if not lesson_path.is_file():
            errors.append(f"set {sid}: lesson file '{filename}' is missing")
            continue
        try:
            lesson = json.loads(lesson_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            errors.append(f"set {sid}: {filename} is invalid JSON: {exc}")
            continue
        lessons.append(lesson)
        card_count += len(lesson.get("cards") or [])

    name = merged.get("title") or merged.get("name") or sid
    description = (merged.get("description") or "").strip()
    level = (merged.get("level") or "").strip().lower()
    domain = (merged.get("domain") or "language").strip().lower()

    entry = {
        "id": sid,
        "name": name,
        "description": description,
        "source_language": merged.get("source_language"),
        "target_language": merged.get("target_language"),
        "level": level,
        "domain": domain,
        "lesson_count": lesson_count,
        "card_count": card_count,
        "tags": merged.get("tags") or [],
        "visibility": normalize_visibility(merged.get("visibility")),
        "ai_validated": has_ai_validation(set_manifest, lessons),
        "trust_level": None,  # filled in by caller (repo-level)
        "book": merged.get("book"),
        "updated_at": git_updated_at(set_dir),
    }
    return entry, errors


def build_index() -> tuple[dict, list[str]]:
    errors: list[str] = []
    root_manifest_path = REPO_ROOT / "manifest.yaml"
    if not root_manifest_path.is_file():
        return {}, ["no root manifest.yaml"]
    root_manifest = load_yaml(root_manifest_path)
    root_sets = root_manifest.get("sets") or []
    if not root_sets:
        return {}, ["root manifest lists no sets"]

    slug = repo_slug()
    trust_map = load_recommended_trust()
    trust_level = trust_map.get(slug, DEFAULT_TRUST_LEVEL)

    entries: list[dict] = []
    total_lessons = 0
    total_cards = 0
    for root_set in root_sets:
        entry, set_errors = build_set_entry(root_set)
        errors.extend(set_errors)
        if not entry:
            continue
        entry["trust_level"] = trust_level
        entries.append(entry)
        total_lessons += entry["lesson_count"]
        total_cards += entry["card_count"]

    index = {
        "repo": slug,
        "generated": _now_iso(),
        "schema_version": SCHEMA_VERSION,
        "sets": entries,
        "total_lessons": total_lessons,
        "total_cards": total_cards,
    }
    return index, errors


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# --------------------------------------------------------------------------- #
# Validation
# --------------------------------------------------------------------------- #
REQUIRED_SET_FIELDS = (
    "id",
    "name",
    "source_language",
    "target_language",
    "level",
    "domain",
    "lesson_count",
    "card_count",
    "visibility",
)


def validate_index(index: dict) -> list[str]:
    errors: list[str] = []
    for key in ("repo", "generated", "schema_version", "sets", "total_lessons", "total_cards"):
        if key not in index:
            errors.append(f"index missing top-level field '{key}'")
    for entry in index.get("sets", []):
        sid = entry.get("id", "?")
        for field in REQUIRED_SET_FIELDS:
            value = entry.get(field)
            if value is None or value == "":
                errors.append(f"set {sid}: empty required field '{field}'")
    # Totals must add up.
    if sum(e.get("lesson_count", 0) for e in index.get("sets", [])) != index.get("total_lessons"):
        errors.append("total_lessons does not match sum of set lesson_count")
    if sum(e.get("card_count", 0) for e in index.get("sets", [])) != index.get("total_cards"):
        errors.append("total_cards does not match sum of set card_count")
    return errors


def _comparable(index: dict) -> dict:
    """Strip the volatile ``generated`` timestamp for staleness checks."""
    clean = dict(index)
    clean.pop("generated", None)
    return clean


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate search-index.json")
    parser.add_argument(
        "--check",
        action="store_true",
        help="Verify the on-disk index is current; exit 1 if stale.",
    )
    args = parser.parse_args(argv)

    index, build_errors = build_index()
    if build_errors:
        print("Errors while building the index:", file=sys.stderr)
        for e in build_errors:
            print(f"  - {e}", file=sys.stderr)
        return 1

    schema_errors = validate_index(index)
    if schema_errors:
        print("Index failed validation:", file=sys.stderr)
        for e in schema_errors:
            print(f"  - {e}", file=sys.stderr)
        return 1

    existing: dict | None = None
    if INDEX_PATH.is_file():
        try:
            existing = json.loads(INDEX_PATH.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            existing = None

    # Preserve the old timestamp when nothing of substance changed, so the
    # generator is idempotent (no spurious diffs / CI commits).
    unchanged = existing is not None and _comparable(existing) == _comparable(index)
    if unchanged:
        index["generated"] = existing["generated"]

    if args.check:
        if existing is None:
            print("search-index.json is missing — run generate_search_index.py", file=sys.stderr)
            return 1
        if not unchanged:
            print("search-index.json is stale — run generate_search_index.py", file=sys.stderr)
            return 1
        print("search-index.json is up to date.")
        return 0

    if unchanged and existing == index:
        print(f"search-index.json already current ({index['total_cards']} cards across "
              f"{len(index['sets'])} set(s)).")
        return 0

    INDEX_PATH.write_text(json.dumps(index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {INDEX_PATH.relative_to(REPO_ROOT)}: {len(index['sets'])} set(s), "
          f"{index['total_lessons']} lesson(s), {index['total_cards']} card(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
