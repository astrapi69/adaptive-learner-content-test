#!/usr/bin/env python3
"""Schema validation of the search index against the mirrored federation
contract (adaptive-learner-content#175).

``schema/search-index.schema.json`` is a mirror of the contract owned by
adaptive-learner-content (the same mirroring relationship the engine
schemas have). ``validate_index`` must validate against it IN ADDITION to
the hand-maintained checks: the hand checks are this variant's floor, the
schema is the contract every writing repo shares. Before this test the
two could disagree silently - a ``lesson_count`` of ``"5"`` (string)
passed the hand check (truthy, not empty) while violating the contract.

Runs under pytest (``python -m pytest tests -q``).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"

if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import generate_search_index as gsi  # noqa: E402


def minimal_index() -> dict:
    """The smallest index that satisfies both the hand checks and the
    mirrored schema."""
    return {
        "repo": "astrapi69/example-repo",
        "generated": "2026-08-05T00:00:00Z",
        "schema_version": "1.0",
        "sets": [
            {
                "id": "example-set",
                "name": "Example",
                "source_language": "de",
                "target_language": "en",
                "level": "A1",
                "domain": "language",
                "lesson_count": 2,
                "card_count": 10,
                "visibility": "visible",
                "review_status": "authored",
            }
        ],
        "total_lessons": 2,
        "total_cards": 10,
    }


def test_mirror_exists_and_is_draft_2020_12() -> None:
    schema_path = REPO_ROOT / "schema" / "search-index.schema.json"
    assert schema_path.is_file(), "search-index.schema.json mirror is missing"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    assert schema.get("$schema") == "https://json-schema.org/draft/2020-12/schema"


def test_conforming_index_passes() -> None:
    assert gsi.validate_index(minimal_index()) == []


def test_schema_catches_what_the_hand_check_cannot() -> None:
    """Discriminating case: an integer ``level`` is truthy and non-empty, so
    the hand-maintained REQUIRED_SET_FIELDS loop is silent - only the
    schema's ``"type": "string"`` on the contract side rejects it."""
    index = minimal_index()
    index["sets"][0]["level"] = 123
    violations = [error for error in gsi.validate_index(index) if error.startswith("schema:")]
    assert violations, "schema violation must be reported"
    assert any("level" in error for error in violations)


def test_schema_catches_a_missing_contract_field() -> None:
    """``domain`` is required by the federation contract."""
    index = minimal_index()
    del index["sets"][0]["domain"]
    violations = [error for error in gsi.validate_index(index) if error.startswith("schema:")]
    assert any("domain" in error for error in violations)
