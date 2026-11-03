#!/usr/bin/env python3
"""Tests for scripts/export_anki.py.

Focus: the pure note-building logic (no genanki needed) - which lesson
elements become which Anki notes, what is skipped and why, and that note
GUIDs are stable across exports (they derive from ``stable_id`` when present,
so a re-import into Anki updates notes instead of duplicating them). One test
writes a real ``.apkg`` and needs genanki, the same way the PDF export's
emission test needs fpdf2.
"""
from __future__ import annotations

import sys
import zipfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from export_anki import (  # noqa: E402
    build_deck_export,
    cloze_text,
    deck_id_for,
    write_package,
)


def _lesson() -> dict:
    return {
        "id": "l1",
        "title": "Lesson one",
        "stable_id": "sl-l1",
        "cards": [
            {"id": "c1", "front": "hola", "back": "hello", "stable_id": "sc-1"},
            {"id": "c2", "front": "adiós", "back": "goodbye"},
        ],
        "steps": [
            {"id": "t1", "type": "theory", "body": "Some theory."},
            {
                "id": "s1",
                "type": "exercise",
                "exercise": {
                    "id": "e-ft",
                    "type": "free_text",
                    "prompt": "Say hello in Spanish",
                    "accept": ["hola", "buenas"],
                    "stable_id": "se-ft",
                },
            },
            {
                "id": "s2",
                "type": "exercise",
                "exercise": {
                    "id": "e-cl",
                    "type": "cloze",
                    "prompt": "Fill the gaps",
                    "sentence": "Yo ___ español y tú ___ inglés.",
                    "blanks": [{"accept": ["hablo"]}, {"accept": ["hablas", "habláis"]}],
                    "explanation": "Verb endings follow the subject.",
                },
            },
            {
                "id": "s3",
                "type": "exercise",
                "exercise": {
                    "id": "e-mc",
                    "type": "multiple_choice",
                    "prompt": "Which is a greeting?",
                    "options": [{"text": "hola", "correct": True}, {"text": "mesa"}, {"text": "libro"}],
                },
            },
            {
                "id": "s4",
                "type": "exercise",
                "exercise": {
                    "id": "e-ma",
                    "type": "matching",
                    "prompt": "Match",
                    "pairs": [{"left": "rojo", "right": "red"}, {"left": "azul", "right": "blue"}],
                },
            },
            {
                "id": "s5",
                "type": "exercise",
                "exercise": {
                    "id": "e-mfc",
                    "type": "matching",
                    "prompt": "Match the cards",
                    "from_cards": True,
                    "card_ids": ["c1", "c2"],
                },
            },
            {
                "id": "s6",
                "type": "exercise",
                "exercise": {
                    "id": "e-wt",
                    "type": "word_tiles",
                    "prompt": "Order the words",
                    "tiles": ["yo", "hablo", "español"],
                },
            },
            {
                "id": "s7",
                "type": "exercise",
                "exercise": {
                    "id": "e-pc",
                    "type": "picture_choice",
                    "prompt": "Pick the cat",
                    "images": [{"src": "a.png", "label": "cat", "is_correct": "true"}, {"src": "b.png", "label": "dog"}],
                },
            },
            {
                "id": "s8",
                "type": "exercise",
                "exercise": {
                    "id": "e-ext",
                    "type": "ext:al-categorization",
                    "prompt": "Sort",
                    "ext_payload": {"categories": []},
                },
            },
        ],
    }


def test_cards_and_mappable_exercises_become_notes_with_the_right_models() -> None:
    export = build_deck_export("es-a1", "Spanish A1", [_lesson()])
    by_model = {}
    for note in export.notes:
        by_model.setdefault(note.model, []).append(note)
    # 2 cards + free_text + multiple_choice + 2 matching pairs + word_tiles = 7 basic notes
    assert len(by_model["basic"]) == 7
    # one cloze note carrying both blanks
    assert len(by_model["cloze"]) == 1
    assert export.deck_name == "Spanish A1"


def test_cloze_text_turns_each_marker_into_a_numbered_cloze_with_the_canonical_answer() -> None:
    text = cloze_text("Yo ___ español y tú ___ inglés.", [{"accept": ["hablo"]}, {"accept": ["hablas", "habláis"]}])
    assert text == "Yo {{c1::hablo}} español y tú {{c2::hablas}} inglés."


def test_cloze_note_carries_the_explanation_as_extra_and_umlauts_intact() -> None:
    export = build_deck_export("es-a1", "Spanish A1", [_lesson()])
    cloze = next(note for note in export.notes if note.model == "cloze")
    assert cloze.fields[0] == "Yo {{c1::hablo}} español y tú {{c2::hablas}} inglés."
    assert cloze.fields[1] == "Verb endings follow the subject."


def test_multiple_choice_lists_lettered_options_on_the_front_and_the_correct_letters_on_the_back() -> None:
    export = build_deck_export("es-a1", "Spanish A1", [_lesson()])
    mc = next(note for note in export.notes if note.guid_key == "exercise:l1/e-mc")
    assert "A) hola" in mc.fields[0] and "C) libro" in mc.fields[0]
    assert "hola" not in mc.fields[0].split("<br>")[0]  # the prompt line does not leak the answer
    assert mc.fields[1] == "A) hola"


def test_matching_pairs_become_one_note_each_and_word_tiles_hide_the_order_on_the_front() -> None:
    export = build_deck_export("es-a1", "Spanish A1", [_lesson()])
    pairs = [note for note in export.notes if note.guid_key.startswith("pair:l1/e-ma/")]
    assert [(n.fields[0], n.fields[1]) for n in pairs] == [("rojo", "red"), ("azul", "blue")]
    tiles = next(note for note in export.notes if note.guid_key == "exercise:l1/e-wt")
    assert "español / hablo / yo" in tiles.fields[0]  # sorted, not authored order
    assert tiles.fields[1] == "yo hablo español"


def test_free_text_puts_the_canonical_answer_first_and_lists_alternatives() -> None:
    export = build_deck_export("es-a1", "Spanish A1", [_lesson()])
    ft = next(note for note in export.notes if note.guid_key == "exercise:se-ft")
    assert ft.fields[0] == "Say hello in Spanish"
    assert ft.fields[1].startswith("hola")
    assert "buenas" in ft.fields[1]


def test_guid_keys_prefer_stable_id_and_fall_back_to_lesson_and_element_ids() -> None:
    export = build_deck_export("es-a1", "Spanish A1", [_lesson()])
    keys = {note.guid_key for note in export.notes}
    assert "card:sc-1" in keys  # stable_id present
    assert "card:l1/c2" in keys  # no stable_id: lesson id + card id
    assert "exercise:se-ft" in keys
    assert "exercise:l1/e-mc" in keys
    assert "pair:l1/e-ma/0" in keys


def test_unmappable_elements_are_skipped_loudly_with_a_reason() -> None:
    export = build_deck_export("es-a1", "Spanish A1", [_lesson()])
    skipped = {(entry.element_id, entry.kind): entry.reason for entry in export.skipped}
    assert ("e-pc", "picture_choice") in skipped
    assert ("e-ext", "ext:al-categorization") in skipped
    assert ("t1", "theory") in skipped
    assert ("e-mfc", "matching") in skipped and "from_cards" in skipped[("e-mfc", "matching")]
    assert len(export.skipped) == 4


def test_tags_carry_the_set_and_lesson_ids() -> None:
    export = build_deck_export("es-a1", "Spanish A1", [_lesson()])
    assert all("es-a1" in note.tags and "l1" in note.tags for note in export.notes)


def test_deck_id_is_stable_and_positive() -> None:
    assert deck_id_for("es-a1") == deck_id_for("es-a1")
    assert deck_id_for("es-a1") != deck_id_for("fr-a1")
    assert 0 < deck_id_for("es-a1") < 2**31


def test_write_package_produces_an_apkg_that_is_an_anki_collection_zip(tmp_path: Path) -> None:
    pytest.importorskip("genanki")
    export = build_deck_export("es-a1", "Spanish A1", [_lesson()])
    out = tmp_path / "es-a1.apkg"
    write_package(export, out)
    assert out.is_file()
    with zipfile.ZipFile(out) as package:
        names = package.namelist()
    assert any(name.startswith("collection.anki2") for name in names)
    assert "media" in names


def test_write_package_is_deterministic_in_guids_across_two_runs(tmp_path: Path) -> None:
    genanki = pytest.importorskip("genanki")
    export = build_deck_export("es-a1", "Spanish A1", [_lesson()])
    first = [genanki.guid_for(note.guid_key) for note in export.notes]
    second = [genanki.guid_for(note.guid_key) for note in build_deck_export("es-a1", "Spanish A1", [_lesson()]).notes]
    assert first == second
