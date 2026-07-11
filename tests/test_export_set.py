"""Tests for the read-only set exporter (``scripts/export_set.py``).

The exporter snapshots ONE set's lessons into a single YAML/JSON file for
AI-assisted review. It is explicitly NOT a re-import format: changes flow
only through the individual schema-validated lesson JSON files.

Covered behaviours (TDD, RED first):
* a known set exports with the correct ``lesson_count`` and the lesson
  order of the set manifest's ``metadata.lessons`` list,
* umlauts survive as REAL UTF-8 in the written bytes (never ``\\u00fc``
  escapes, never an ae/oe/ue substitution),
* re-parsing the YAML yields content equal to the source lesson JSONs,
* an unknown slug fails with a non-zero exit and lists the available sets,
* ``--format json`` produces valid JSON with the same lesson content,
* the default output path lands under ``exports/`` (created on demand),
* the manifest set id (``fuehrerschein-uebung-from-de``) resolves the same
  set as the path basename slug.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import export_set  # noqa: E402

KNOWN_SLUG = "fuehrerschein-uebung"
KNOWN_SET_DIR = REPO_ROOT / "sets" / "de" / "fuehrerschein-uebung"


def load_source_lessons() -> list[dict]:
    """Load the known set's lesson JSONs in set-manifest order."""
    set_manifest = yaml.safe_load(
        (KNOWN_SET_DIR / "manifest.yaml").read_text(encoding="utf-8")
    )
    lesson_filenames = set_manifest["metadata"]["lessons"]
    return [
        json.loads((KNOWN_SET_DIR / "lessons" / lesson_filename).read_text(encoding="utf-8"))
        for lesson_filename in lesson_filenames
    ]


def run_export(tmp_path: Path, *extra_argv: str) -> Path:
    """Run the exporter for the known set into ``tmp_path`` and return the file."""
    suffix = "json" if "json" in extra_argv else "yaml"
    out_path = tmp_path / f"export.{suffix}"
    exit_code = export_set.main([KNOWN_SLUG, "--out", str(out_path), *extra_argv])
    assert exit_code == 0
    return out_path


def test_known_set_exports_with_count_and_manifest_order(tmp_path: Path) -> None:
    out_path = run_export(tmp_path)
    export_payload = yaml.safe_load(out_path.read_text(encoding="utf-8"))

    source_lessons = load_source_lessons()
    assert export_payload["set"] == KNOWN_SLUG
    assert export_payload["language"] == "de"
    assert export_payload["lesson_count"] == len(source_lessons)
    assert len(export_payload["lessons"]) == len(source_lessons)
    exported_ids = [lesson["id"] for lesson in export_payload["lessons"]]
    source_ids = [lesson["id"] for lesson in source_lessons]
    assert exported_ids == source_ids


def test_metadata_header_fields(tmp_path: Path) -> None:
    out_path = run_export(tmp_path)
    export_payload = yaml.safe_load(out_path.read_text(encoding="utf-8"))

    pinned_version = (REPO_ROOT / "schema" / "engine-version.txt").read_text(
        encoding="utf-8"
    ).strip()
    assert export_payload["engine_version"] == pinned_version
    assert export_payload["set_id"] == "fuehrerschein-uebung-from-de"
    # ISO-8601 UTC, e.g. 2026-07-11T12:34:56Z
    assert export_payload["generated_at"].endswith("Z")
    assert "T" in export_payload["generated_at"]


def test_umlauts_survive_as_real_utf8(tmp_path: Path) -> None:
    out_path = run_export(tmp_path)
    raw_text = out_path.read_bytes().decode("utf-8")

    assert "ü" in raw_text
    assert "ä" in raw_text
    assert "\\u00fc" not in raw_text
    assert "\\u00e4" not in raw_text
    # A known lesson phrase must keep its umlaut, never an ue-substitution.
    # (Plain "gewaehren" DOES occur in the source as the ASCII card id
    # "vorfahrt-gewaehren", so assert on the prose phrase, not the token.)
    assert "Vorfahrt gewähren" in raw_text
    assert "Vorfahrt gewaehren" not in raw_text


def test_yaml_reparse_content_equals_source_lessons(tmp_path: Path) -> None:
    out_path = run_export(tmp_path)
    export_payload = yaml.safe_load(out_path.read_text(encoding="utf-8"))
    assert export_payload["lessons"] == load_source_lessons()


def test_format_json_is_valid_and_content_equal(tmp_path: Path) -> None:
    out_path = run_export(tmp_path, "--format", "json")
    raw_text = out_path.read_text(encoding="utf-8")

    export_payload = json.loads(raw_text)
    assert export_payload["lessons"] == load_source_lessons()
    # ensure_ascii must be off: real umlauts in the JSON bytes too.
    assert "gewähren" in raw_text
    assert "\\u00fc" not in raw_text


def test_unknown_slug_fails_and_lists_available_sets(tmp_path: Path, capsys) -> None:
    exit_code = export_set.main(
        ["definitely-not-a-set", "--out", str(tmp_path / "never-written.yaml")]
    )
    assert exit_code != 0
    captured_stderr = capsys.readouterr().err
    assert "definitely-not-a-set" in captured_stderr
    assert KNOWN_SLUG in captured_stderr
    assert not (tmp_path / "never-written.yaml").exists()


def test_manifest_id_resolves_like_path_basename(tmp_path: Path) -> None:
    out_path = tmp_path / "by-id.yaml"
    exit_code = export_set.main(
        ["fuehrerschein-uebung-from-de", "--out", str(out_path)]
    )
    assert exit_code == 0
    export_payload = yaml.safe_load(out_path.read_text(encoding="utf-8"))
    assert export_payload["set_id"] == "fuehrerschein-uebung-from-de"
    assert export_payload["lessons"] == load_source_lessons()


def test_default_out_path_lands_under_exports_dir() -> None:
    exports_dir = REPO_ROOT / "exports"
    before_export = set(exports_dir.glob("*")) if exports_dir.is_dir() else set()
    exit_code = export_set.main([KNOWN_SLUG])
    assert exit_code == 0
    created_files = set(exports_dir.glob(f"{KNOWN_SLUG}-de-*.yaml")) - before_export
    assert len(created_files) == 1
    created_export = created_files.pop()
    try:
        export_payload = yaml.safe_load(created_export.read_text(encoding="utf-8"))
        assert export_payload["set"] == KNOWN_SLUG
    finally:
        created_export.unlink()
