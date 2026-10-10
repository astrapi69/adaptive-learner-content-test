#!/usr/bin/env python3
"""Read-only set exporter: one set's lessons as a single YAML/JSON file.

Snapshots ONE content set (resolved via the root ``manifest.yaml``) into a
single file so the whole set can be reviewed in one pass, e.g. by an AI
assistant checking syntax, correctness and consistency across lessons.

This is a READ-ONLY snapshot, NOT a re-import format. The exporter never
writes into ``sets/`` and nothing reads the export back. Changes flow only
through the individual schema-validated lesson JSON files (validated by
``scripts/validate_content.py`` and the engine gate in CI).

Usage:

    python3 scripts/export_set.py <set-slug> [--lang de] [--format yaml|json] [--out PATH]
    python3 scripts/export_set.py <set-slug> --split-size N [--lang de] [--format yaml|json]

``--split-size N`` splits a large set into multiple files of at most N
lessons each (e.g. for handing a course to an AI reviewer one digestible
chunk at a time instead of one huge file - a 115-lesson set has no business
being reviewed in one context window). Each part is self-contained: it
carries its own ``review_instructions`` copy plus ``part``/``of`` and
``total_lesson_count`` fields so a reviewer knows where the chunk sits in
the whole set. Incompatible with ``--out`` (a split export always writes
multiple files under ``exports/``, named
``<set-slug>-<lang>-<timestamp>-part<NN>-of-<MM>.<format>``).

``<set-slug>`` matches either a set id from the root manifest (e.g.
``führerschein-übung-from-de``) or the basename of a set path (e.g.
``führerschein-übung`` for ``sets/de/führerschein-übung``). When the
same basename exists under several source-language directories,
``--lang`` (the ``sets/<lang>/`` directory, default ``de``) disambiguates.

Output structure (the embedded review instructions FIRST so the export is
self-contained for a review AI, then the metadata, then the lessons in the
order of the set manifest's ``metadata.lessons`` list):

    review_instructions: |
      <full content of docs/ai-review-prompt-template.md>
    set: führerschein-übung
    language: de
    engine_version: "0.8.1"
    generated_at: "2026-07-11T12:34:56Z"
    lesson_count: 5
    lessons:
      - <full lesson content per file>

``review_instructions`` is read from ``docs/ai-review-prompt-template.md``
at runtime (never hardcoded here, DRY); edit the prompt there and keep the
sibling content repos in sync. A missing template file is a hard error, no
silent export without the field.

Umlauts and every other non-ASCII character are written as real UTF-8
(``allow_unicode=True`` / ``ensure_ascii=False``), never as escapes.

Default output: ``exports/<set-slug>-<lang>-<timestamp>.yaml`` (the
``exports/`` directory is created on demand and gitignored).

Exit code 0 on success; 2 for an unknown/ambiguous slug (the error lists
the available sets), a missing lesson file or a missing review template.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
ROOT_MANIFEST_PATH = REPO_ROOT / "manifest.yaml"
ENGINE_VERSION_PATH = REPO_ROOT / "schema" / "engine-version.txt"
REVIEW_TEMPLATE_PATH = REPO_ROOT / "docs" / "ai-review-prompt-template.md"
EXPORTS_DIR = REPO_ROOT / "exports"
YAML_LINE_WIDTH = 100


class SetResolutionError(Exception):
    """Raised when a set slug cannot be resolved to exactly one manifest set,
    or when a file the export depends on (lesson, review template) is missing."""


class BlockScalarDumper(yaml.SafeDumper):
    """SafeDumper that renders multi-line strings as literal block scalars.

    Keeps the embedded ``review_instructions`` (and multi-line lesson prose)
    human- and AI-readable instead of one escaped single-line string.
    PyYAML falls back to a quoted style automatically for strings a block
    scalar cannot represent, so re-parse equality always holds.
    """


def represent_multiline_string(dumper: yaml.SafeDumper, scalar_text: str):
    scalar_style = "|" if "\n" in scalar_text else None
    return dumper.represent_scalar(
        "tag:yaml.org,2002:str", scalar_text, style=scalar_style
    )


BlockScalarDumper.add_representer(str, represent_multiline_string)


def format_available_sets(set_entries: list[dict]) -> str:
    """Return one line per registered set: ``id (path)``."""
    return "\n".join(
        f"  {set_entry.get('id', '?')} ({set_entry.get('path', '?')})"
        for set_entry in set_entries
    )


def source_language_of(set_entry: dict) -> str:
    """Return the source-language directory of a set path (``sets/de/x`` -> ``de``)."""
    path_parts = PurePosixPath(set_entry.get("path", "")).parts
    return path_parts[1] if len(path_parts) >= 2 else ""


def resolve_set(root_manifest: dict, set_slug: str, lang: str) -> dict:
    """Resolve ``set_slug`` against the root manifest to exactly one set entry.

    Match order: exact set id first, then path basename. Basename matches
    that exist under several ``sets/<lang>/`` directories are disambiguated
    by ``lang``. Raises ``SetResolutionError`` (listing the available sets)
    when nothing or nothing unambiguous matches.
    """
    set_entries = root_manifest.get("sets") or []
    for set_entry in set_entries:
        if set_entry.get("id") == set_slug:
            return set_entry

    basename_matches = [
        set_entry
        for set_entry in set_entries
        if PurePosixPath(set_entry.get("path", "")).name == set_slug
    ]
    if len(basename_matches) == 1:
        return basename_matches[0]
    if basename_matches:
        lang_matches = [
            set_entry
            for set_entry in basename_matches
            if source_language_of(set_entry) == lang
        ]
        if len(lang_matches) == 1:
            return lang_matches[0]
        raise SetResolutionError(
            f"Set slug '{set_slug}' is ambiguous for --lang '{lang}'. "
            f"Candidates:\n{format_available_sets(basename_matches)}\n"
            "Use the full set id instead."
        )

    raise SetResolutionError(
        f"Unknown set slug '{set_slug}'. Available sets:\n"
        f"{format_available_sets(set_entries)}"
    )


def ordered_lesson_paths(set_dir: Path) -> list[Path]:
    """Return the set's lesson files in review order.

    The set manifest's ``metadata.lessons`` list is authoritative; when a
    set manifest carries no such list, fall back to the sorted directory
    listing of ``lessons/*.json``.
    """
    lessons_dir = set_dir / "lessons"
    set_manifest = yaml.safe_load((set_dir / "manifest.yaml").read_text(encoding="utf-8"))
    lesson_filenames = ((set_manifest or {}).get("metadata") or {}).get("lessons")
    if lesson_filenames:
        return [lessons_dir / lesson_filename for lesson_filename in lesson_filenames]
    return sorted(lessons_dir.glob("*.json"))


def load_lessons(set_dir: Path) -> list[dict]:
    """Load all lesson JSONs of a set in review order.

    Raises ``SetResolutionError`` when a manifest-listed lesson file is
    missing, so a stale manifest fails loudly instead of exporting a
    silently incomplete snapshot.
    """
    lesson_documents = []
    for lesson_path in ordered_lesson_paths(set_dir):
        if not lesson_path.is_file():
            raise SetResolutionError(
                f"Lesson file listed in the set manifest is missing: {lesson_path}"
            )
        lesson_documents.append(json.loads(lesson_path.read_text(encoding="utf-8")))
    return lesson_documents


def load_review_instructions() -> str:
    """Return the AI review prompt embedded into every export.

    Read at runtime from ``docs/ai-review-prompt-template.md`` (single
    source, DRY). Raises ``SetResolutionError`` when the template is
    missing: the export must never silently lack the field.
    """
    if not REVIEW_TEMPLATE_PATH.is_file():
        raise SetResolutionError(
            "Review prompt template is missing: "
            f"{REVIEW_TEMPLATE_PATH}\n"
            "The export embeds docs/ai-review-prompt-template.md as its "
            "review_instructions field; restore the file before exporting."
        )
    return REVIEW_TEMPLATE_PATH.read_text(encoding="utf-8")


def build_export(set_slug: str, lang: str) -> dict:
    """Assemble the export payload: review instructions first, then the
    metadata header, then the lessons."""
    root_manifest = yaml.safe_load(ROOT_MANIFEST_PATH.read_text(encoding="utf-8"))
    set_entry = resolve_set(root_manifest, set_slug, lang)
    lesson_documents = load_lessons(REPO_ROOT / set_entry["path"])
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return {
        "review_instructions": load_review_instructions(),
        "set": set_slug,
        "language": lang,
        "engine_version": ENGINE_VERSION_PATH.read_text(encoding="utf-8").strip(),
        "generated_at": generated_at,
        "lesson_count": len(lesson_documents),
        "lessons": lesson_documents,
    }


def chunk_lessons(lesson_documents: list[dict], split_size: int) -> list[list[dict]]:
    """Split ``lesson_documents`` into consecutive chunks of at most
    ``split_size`` lessons each, preserving order. The last chunk may be
    smaller. A ``split_size`` at or above the lesson count yields a single
    chunk. Pure and independent of I/O so it is trivially unit-testable."""
    if split_size < 1:
        raise ValueError(f"split_size must be >= 1, got {split_size}")
    return [
        lesson_documents[start : start + split_size]
        for start in range(0, len(lesson_documents), split_size)
    ] or [[]]


def build_export_parts(set_slug: str, lang: str, split_size: int) -> list[dict]:
    """Assemble one export payload PER CHUNK of at most ``split_size``
    lessons, for AI review sessions that cannot fit an entire large set in
    one context window (e.g. a 115-lesson set). Every part is
    self-contained: it carries its own copy of ``review_instructions`` so
    each file can be handed to a reviewer independently, plus ``part``/``of``
    and ``total_lesson_count`` so the reviewer knows where a chunk sits in
    the whole set. All parts share one ``generated_at`` timestamp (one
    export run)."""
    root_manifest = yaml.safe_load(ROOT_MANIFEST_PATH.read_text(encoding="utf-8"))
    set_entry = resolve_set(root_manifest, set_slug, lang)
    lesson_documents = load_lessons(REPO_ROOT / set_entry["path"])
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    engine_version = ENGINE_VERSION_PATH.read_text(encoding="utf-8").strip()
    review_instructions = load_review_instructions()
    chunks = chunk_lessons(lesson_documents, split_size)
    return [
        {
            "review_instructions": review_instructions,
            "set": set_slug,
            "language": lang,
            "engine_version": engine_version,
            "generated_at": generated_at,
            "part": part_index + 1,
            "of": len(chunks),
            "lesson_count": len(chunk),
            "total_lesson_count": len(lesson_documents),
            "lessons": chunk,
        }
        for part_index, chunk in enumerate(chunks)
    ]


def render_export(export_payload: dict, export_format: str) -> str:
    """Serialize the payload; real UTF-8 in both formats, keys in insert order,
    multi-line strings (notably ``review_instructions``) as YAML block scalars."""
    if export_format == "json":
        return json.dumps(export_payload, ensure_ascii=False, indent=2) + "\n"
    return yaml.dump(
        export_payload,
        Dumper=BlockScalarDumper,
        allow_unicode=True,
        sort_keys=False,
        default_flow_style=False,
        width=YAML_LINE_WIDTH,
    )


def default_output_path(set_slug: str, lang: str, export_format: str) -> Path:
    """Return ``exports/<set-slug>-<lang>-<timestamp>.<format>``."""
    file_timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return EXPORTS_DIR / f"{set_slug}-{lang}-{file_timestamp}.{export_format}"


def default_split_output_path(
    set_slug: str, lang: str, export_format: str, part: int, of: int, file_timestamp: str
) -> Path:
    """Return ``exports/<set-slug>-<lang>-<timestamp>-part<NN>-of-<MM>.<format>``,
    one file per chunk of a ``--split-size`` export. ``file_timestamp`` is
    computed ONCE by the caller and shared across every part of one export
    run, so the parts sort together and are recognisable as one batch."""
    width = max(2, len(str(of)))
    return (
        EXPORTS_DIR
        / f"{set_slug}-{lang}-{file_timestamp}-part{part:0{width}d}-of-{of}.{export_format}"
    )


def parse_arguments(argv: list[str] | None) -> argparse.Namespace:
    argument_parser = argparse.ArgumentParser(
        description=(
            "Export one set's lessons into a single YAML/JSON file for "
            "AI-assisted review (read-only snapshot, NOT a re-import format)."
        )
    )
    argument_parser.add_argument(
        "set_slug",
        help="set id from manifest.yaml or the basename of a set path",
    )
    argument_parser.add_argument(
        "--lang",
        default="de",
        help="source-language directory (sets/<lang>/) used to disambiguate "
        "path-basename slugs (default: de)",
    )
    argument_parser.add_argument(
        "--format",
        dest="export_format",
        choices=("yaml", "json"),
        default="yaml",
        help="output format (default: yaml)",
    )
    argument_parser.add_argument(
        "--out",
        help="output file path (default: exports/<set-slug>-<lang>-<timestamp>.<format>). "
        "Incompatible with --split-size (which writes multiple files).",
    )
    argument_parser.add_argument(
        "--split-size",
        type=int,
        default=None,
        help="split the export into multiple files of at most N lessons each, "
        "e.g. for AI review sessions that cannot fit a large set in one "
        "context window. Each file is self-contained (its own "
        "review_instructions) and carries part/of/total_lesson_count. "
        "Default: one file for the whole set. Incompatible with --out.",
    )
    return argument_parser.parse_args(argv)


def _write_single_export(cli_arguments: argparse.Namespace) -> int:
    try:
        export_payload = build_export(cli_arguments.set_slug, cli_arguments.lang)
    except SetResolutionError as resolution_error:
        print(f"ERROR: {resolution_error}", file=sys.stderr)
        return 2

    output_path = (
        Path(cli_arguments.out)
        if cli_arguments.out
        else default_output_path(
            cli_arguments.set_slug, cli_arguments.lang, cli_arguments.export_format
        )
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        render_export(export_payload, cli_arguments.export_format), encoding="utf-8"
    )
    print(
        f"Exported {export_payload['lesson_count']} lessons of set "
        f"'{export_payload['set']}' to {output_path}"
    )
    return 0


def _write_split_export(cli_arguments: argparse.Namespace) -> int:
    try:
        export_parts = build_export_parts(
            cli_arguments.set_slug, cli_arguments.lang, cli_arguments.split_size
        )
    except (SetResolutionError, ValueError) as build_error:
        print(f"ERROR: {build_error}", file=sys.stderr)
        return 2

    EXPORTS_DIR.mkdir(parents=True, exist_ok=True)
    file_timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    of = len(export_parts)
    for export_payload in export_parts:
        output_path = default_split_output_path(
            cli_arguments.set_slug,
            cli_arguments.lang,
            cli_arguments.export_format,
            export_payload["part"],
            of,
            file_timestamp,
        )
        output_path.write_text(
            render_export(export_payload, cli_arguments.export_format), encoding="utf-8"
        )
        print(
            f"Exported part {export_payload['part']}/{of} "
            f"({export_payload['lesson_count']} of {export_payload['total_lesson_count']} "
            f"lessons) of set '{export_payload['set']}' to {output_path}"
        )
    return 0


def main(argv: list[str] | None = None) -> int:
    cli_arguments = parse_arguments(argv)
    if cli_arguments.split_size is not None and cli_arguments.out:
        print(
            "ERROR: --out cannot be combined with --split-size "
            "(a split export writes multiple files)",
            file=sys.stderr,
        )
        return 2
    if cli_arguments.split_size is not None:
        return _write_split_export(cli_arguments)
    return _write_single_export(cli_arguments)


if __name__ == "__main__":
    sys.exit(main())
