#!/usr/bin/env python3
"""Export one set as an Anki deck (``.apkg``).

Anki is the largest spaced-repetition ecosystem there is; this tool lets a
set travel there without leaving this repository's format behind. It is a
CONSUMER tool, not part of the engine (the same "one source, many outputs"
boundary as ``export_set.py`` and ``export_quiz_pdf.py``): the engine
validates the lesson JSON, this script renders one presentation of it.

What becomes a note:

* every card (``front`` / ``back``)                -> Basic note
* ``free_text``                                    -> Basic (prompt / canonical answer, alternatives listed)
* ``cloze`` (``type`` and ``select`` modes)        -> Cloze note, one ``{{cN::...}}`` per blank
* ``cloze`` ``multiselect``                        -> Basic (question stem / accepted answers)
* ``multiple_choice``                              -> Basic (prompt plus lettered options / the correct letters)
* ``matching`` with explicit ``pairs``             -> one Basic note PER PAIR (left / right)
* ``word_tiles``                                   -> Basic (prompt plus the tiles in alphabetical order / the sentence)

What is skipped, and said so in the report (never silently): theory steps
(no card to make), ``picture_choice`` (assets are not exported),
``matching`` with ``from_cards`` (its pairs ARE the cards, exported once
already), and every ``ext:`` type (opaque payload).

Note identity: each note's GUID derives from the element's ``stable_id``
when present, else from the lesson id plus the element id. Anki matches
notes on GUID, so re-importing a newer export UPDATES notes and keeps the
learner's scheduling instead of creating duplicates - the same identity
promise ``stable_id`` makes inside this ecosystem, carried across.

The note-building logic is pure (``build_deck_export``) and unit-tested;
only ``write_package`` imports ``genanki``, lazily, so the logic is testable
without the dependency (``make setup`` installs it from requirements.txt).

Usage:

    python3 scripts/export_anki.py <set-slug> [--lang de] [--out PATH]

Default output: ``exports/<set-slug>-<lang>-<timestamp>.apkg``. Exit code 0
on success; 2 for an unknown/ambiguous slug, a missing lesson file, or a
missing ``genanki``.
"""
from __future__ import annotations

import argparse
import html
import sys
import zlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import yaml

from export_set import (
    EXPORTS_DIR,
    REPO_ROOT,
    ROOT_MANIFEST_PATH,
    SetResolutionError,
    load_lessons,
    resolve_set,
)

CLOZE_MARKER = "___"
LINE_BREAK = "<br>"
OPTION_LETTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"


class DependencyMissingError(Exception):
    """Raised when ``genanki`` is not installed in the environment."""


@dataclass
class AnkiNote:
    """One note to create: ``model`` is ``basic`` (Front / Back) or ``cloze``
    (Text / Back Extra); ``guid_key`` is the stable identity the GUID derives from."""

    model: str
    fields: list[str]
    guid_key: str
    tags: list[str]


@dataclass
class SkippedElement:
    lesson_id: str
    element_id: str
    kind: str
    reason: str


@dataclass
class DeckExport:
    set_slug: str
    deck_name: str
    notes: list[AnkiNote] = field(default_factory=list)
    skipped: list[SkippedElement] = field(default_factory=list)


def deck_id_for(set_slug: str) -> int:
    """A stable, positive 31-bit deck id derived from the set slug, so two
    exports of the same set land in the same Anki deck."""
    return (zlib.crc32(set_slug.encode("utf-8")) & 0x7FFFFFFF) or 1


def _text(value: str) -> str:
    """Escape for an Anki field (fields are HTML); umlauts stay verbatim."""
    return html.escape(value, quote=False)


def _identity(lesson: dict, element: dict, fallback_id: str) -> str:
    stable_id = element.get("stable_id")
    return stable_id if isinstance(stable_id, str) and stable_id else f"{lesson.get('id', '?')}/{fallback_id}"


def cloze_text(sentence: str, blanks: list[dict]) -> str:
    """Turn ``Yo ___ español`` plus its blanks into ``Yo {{c1::hablo}} español``,
    one numbered cloze per marker, the canonical (first) accepted answer as
    the cloze text. Raises ``ValueError`` when markers and blanks disagree."""
    segments = sentence.split(CLOZE_MARKER)
    if len(segments) - 1 != len(blanks):
        raise ValueError(
            f"{len(segments) - 1} marker(s) but {len(blanks)} blank(s); the validator rejects this shape"
        )
    rendered = _text(segments[0])
    for index, (blank, segment) in enumerate(zip(blanks, segments[1:]), start=1):
        answer = (blank.get("accept") or [""])[0]
        rendered += f"{{{{c{index}::{_text(answer)}}}}}{_text(segment)}"
    return rendered


def _card_notes(lesson: dict, tags: list[str]) -> list[AnkiNote]:
    return [
        AnkiNote(
            model="basic",
            fields=[_text(card.get("front", "")), _text(card.get("back", ""))],
            guid_key=f"card:{_identity(lesson, card, card.get('id', '?'))}",
            tags=tags,
        )
        for card in lesson.get("cards") or []
    ]


def _free_text_note(lesson: dict, exercise: dict, tags: list[str]) -> AnkiNote:
    accept = exercise.get("accept") or []
    back = _text(accept[0]) if accept else ""
    if len(accept) > 1:
        back += f"{LINE_BREAK}also: {_text(', '.join(accept[1:]))}"
    return AnkiNote("basic", [_text(exercise.get("prompt", "")), back], f"exercise:{_identity(lesson, exercise, exercise['id'])}", tags)


def _cloze_note(lesson: dict, exercise: dict, tags: list[str]) -> AnkiNote:
    text = cloze_text(exercise.get("sentence", ""), exercise.get("blanks") or [])
    extra = _text(exercise.get("explanation") or "")
    return AnkiNote("cloze", [text, extra], f"exercise:{_identity(lesson, exercise, exercise['id'])}", tags)


def _multiselect_note(lesson: dict, exercise: dict, tags: list[str]) -> AnkiNote:
    back = _text(", ".join(exercise.get("accept") or []))
    return AnkiNote("basic", [_text(exercise.get("sentence", "")), back], f"exercise:{_identity(lesson, exercise, exercise['id'])}", tags)


def _multiple_choice_note(lesson: dict, exercise: dict, tags: list[str]) -> AnkiNote:
    options = exercise.get("options") or []
    lettered = [f"{OPTION_LETTERS[index]}) {_text(option.get('text', ''))}" for index, option in enumerate(options)]
    correct = [line for line, option in zip(lettered, options) if option.get("correct") is True]
    front = LINE_BREAK.join([_text(exercise.get("prompt", "")), *lettered])
    return AnkiNote("basic", [front, LINE_BREAK.join(correct)], f"exercise:{_identity(lesson, exercise, exercise['id'])}", tags)


def _pair_notes(lesson: dict, exercise: dict, tags: list[str]) -> list[AnkiNote]:
    base = _identity(lesson, exercise, exercise["id"])
    notes = []
    for index, pair in enumerate(exercise.get("pairs") or []):
        pair_stable = pair.get("stable_id")
        key = f"pair:{pair_stable}" if isinstance(pair_stable, str) and pair_stable else f"pair:{base}/{index}"
        notes.append(AnkiNote("basic", [_text(pair.get("left", "")), _text(pair.get("right", ""))], key, tags))
    return notes


def _word_tiles_note(lesson: dict, exercise: dict, tags: list[str]) -> AnkiNote:
    tiles = [str(tile) for tile in exercise.get("tiles") or []]
    front = LINE_BREAK.join([_text(exercise.get("prompt", "")), _text(" / ".join(sorted(tiles)))])
    return AnkiNote("basic", [front, _text(" ".join(tiles))], f"exercise:{_identity(lesson, exercise, exercise['id'])}", tags)


def _exercise_notes(lesson: dict, exercise: dict, tags: list[str]) -> tuple[list[AnkiNote], SkippedElement | None]:
    kind = exercise.get("type", "?")
    exercise_id = exercise.get("id", "?")
    lesson_id = lesson.get("id", "?")
    if kind.startswith("ext:"):
        return [], SkippedElement(lesson_id, exercise_id, kind, "extension payload is opaque to this exporter")
    if kind == "picture_choice":
        return [], SkippedElement(lesson_id, exercise_id, kind, "image assets are not exported")
    if kind == "matching":
        if exercise.get("from_cards") is True:
            return [], SkippedElement(lesson_id, exercise_id, kind, "from_cards pairs are the cards, exported once already")
        return _pair_notes(lesson, exercise, tags), None
    if kind == "free_text":
        return [_free_text_note(lesson, exercise, tags)], None
    if kind == "multiple_choice":
        return [_multiple_choice_note(lesson, exercise, tags)], None
    if kind == "word_tiles":
        return [_word_tiles_note(lesson, exercise, tags)], None
    if kind == "cloze":
        if exercise.get("cloze_mode") == "multiselect":
            return [_multiselect_note(lesson, exercise, tags)], None
        try:
            return [_cloze_note(lesson, exercise, tags)], None
        except ValueError as shape_error:
            return [], SkippedElement(lesson_id, exercise_id, kind, str(shape_error))
    return [], SkippedElement(lesson_id, exercise_id, kind, "no Anki mapping for this exercise type")


def build_deck_export(set_slug: str, deck_name: str, lesson_documents: list[dict]) -> DeckExport:
    """Pure: lesson documents to the notes an Anki deck will carry, plus the
    elements skipped and why. No I/O, no genanki."""
    export = DeckExport(set_slug=set_slug, deck_name=deck_name)
    for lesson in lesson_documents:
        lesson_id = lesson.get("id", "?")
        tags = [set_slug, lesson_id]
        export.notes.extend(_card_notes(lesson, tags))
        for step in lesson.get("steps") or []:
            if step.get("type") == "theory":
                export.skipped.append(SkippedElement(lesson_id, step.get("id", "?"), "theory", "theory step has no card to make"))
                continue
            exercise = step.get("exercise")
            if not exercise:
                continue
            notes, skipped = _exercise_notes(lesson, exercise, tags)
            export.notes.extend(notes)
            if skipped:
                export.skipped.append(skipped)
    return export


def write_package(export: DeckExport, out_path: Path) -> None:
    """Emit the ``.apkg``. Imports genanki lazily so the note logic stays
    testable without it; raises ``DependencyMissingError`` when absent."""
    try:
        import genanki  # noqa: PLC0415 (lazy on purpose, see module docstring)
    except ImportError as import_error:
        raise DependencyMissingError(
            "genanki is not installed; run `make setup` (it installs requirements.txt)"
        ) from import_error

    deck = genanki.Deck(deck_id_for(export.set_slug), export.deck_name)
    for note in export.notes:
        model = genanki.CLOZE_MODEL if note.model == "cloze" else genanki.BASIC_MODEL
        deck.add_note(genanki.Note(model=model, fields=note.fields, guid=genanki.guid_for(note.guid_key), tags=note.tags))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    genanki.Package(deck).write_to_file(str(out_path))


def default_output_path(set_slug: str, lang: str) -> Path:
    file_timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return EXPORTS_DIR / f"{set_slug}-{lang}-{file_timestamp}.apkg"


def format_report(export: DeckExport, out_path: Path) -> str:
    counts = {model: sum(1 for note in export.notes if note.model == model) for model in ("basic", "cloze")}
    lines = [
        f"Exported {len(export.notes)} notes (basic: {counts['basic']}, cloze: {counts['cloze']}) "
        f"of set '{export.set_slug}' as deck '{export.deck_name}' to {out_path}"
    ]
    if export.skipped:
        lines.append(f"Skipped {len(export.skipped)} element(s):")
        lines.extend(
            f"  - {entry.lesson_id}/{entry.element_id} ({entry.kind}): {entry.reason}" for entry in export.skipped
        )
    return "\n".join(lines)


def parse_arguments(argv: list[str] | None) -> argparse.Namespace:
    argument_parser = argparse.ArgumentParser(description="Export one set as an Anki deck (.apkg).")
    argument_parser.add_argument("set_slug", help="set id from manifest.yaml or the basename of a set path")
    argument_parser.add_argument(
        "--lang",
        default="de",
        help="source-language directory (sets/<lang>/) used to disambiguate path-basename slugs (default: de)",
    )
    argument_parser.add_argument("--out", help="output file path (default: exports/<set-slug>-<lang>-<timestamp>.apkg)")
    return argument_parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    cli_arguments = parse_arguments(argv)
    try:
        root_manifest = yaml.safe_load(ROOT_MANIFEST_PATH.read_text(encoding="utf-8"))
        set_entry = resolve_set(root_manifest, cli_arguments.set_slug, cli_arguments.lang)
        lesson_documents = load_lessons(REPO_ROOT / set_entry["path"])
    except SetResolutionError as resolution_error:
        print(f"ERROR: {resolution_error}", file=sys.stderr)
        return 2

    deck_name = set_entry.get("title") or cli_arguments.set_slug
    export = build_deck_export(cli_arguments.set_slug, deck_name, lesson_documents)
    out_path = Path(cli_arguments.out) if cli_arguments.out else default_output_path(cli_arguments.set_slug, cli_arguments.lang)
    try:
        write_package(export, out_path)
    except DependencyMissingError as dependency_error:
        print(f"ERROR: {dependency_error}", file=sys.stderr)
        return 2
    print(format_report(export, out_path))
    return 0


if __name__ == "__main__":
    sys.exit(main())
