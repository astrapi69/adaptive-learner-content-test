#!/usr/bin/env python3
"""minMatchingPairs gate counts derived pairs for ``from_cards`` matching.

A schema-1.6 ``matching`` with ``from_cards: true`` (engine 0.7.0+) has
no explicit ``pairs`` - the pairs are derived from ``card_ids``. Before
this fix the gate counted only explicit ``pairs``, so a perfectly valid
from_cards matching was falsely blocked with "needs >= 3 pairs" even
though the engine validator in CI accepts it. The gate now mirrors the
engine semantics: with ``from_cards`` the derived pair count is
``len(card_ids)``.
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import validate_content as vc  # noqa: E402


def pairs_errors(lesson: dict) -> list[str]:
    errors: list[str] = []
    vc.validate_lesson_quality(lesson, "de", "<lesson>", errors)
    return [e for e in errors if "pairs" in e]


def matching_from_cards(card_ids: list[str]) -> dict:
    return {
        "id": "s-m1",
        "type": "exercise",
        "exercise": {
            "id": "m1",
            "type": "matching",
            "prompt": "Ordne zu.",
            "from_cards": True,
            "card_ids": card_ids,
        },
    }


def matching_explicit(pair_count: int) -> dict:
    return {
        "id": "s-m1",
        "type": "exercise",
        "exercise": {
            "id": "m1",
            "type": "matching",
            "prompt": "Ordne zu.",
            "pairs": [
                {"left": f"links {i}", "right": f"rechts {i}"}
                for i in range(pair_count)
            ],
        },
    }


def lesson(matching_step: dict, card_ids: list[str]) -> dict:
    return {
        "id": "l1",
        "title": "T",
        "cards": [
            {"id": cid, "front": f"Vorderseite {cid}", "back": f"Rückseite {cid}"}
            for cid in card_ids
        ],
        "steps": [
            {"id": "t1", "type": "theory", "body": "Theorie."},
            matching_step,
        ],
    }


def test_from_cards_with_enough_card_ids_passes() -> None:
    card_ids = ["k1", "k2", "k3"]
    built = lesson(matching_from_cards(card_ids), card_ids)
    assert pairs_errors(built) == []


def test_from_cards_below_minimum_still_blocked() -> None:
    card_ids = ["k1", "k2"]
    built = lesson(matching_from_cards(card_ids), card_ids)
    assert pairs_errors(built) != []


def test_explicit_pairs_below_minimum_still_blocked() -> None:
    built = lesson(matching_explicit(2), [])
    assert pairs_errors(built) != []


def test_explicit_pairs_at_minimum_passes() -> None:
    built = lesson(matching_explicit(3), [])
    assert pairs_errors(built) == []
