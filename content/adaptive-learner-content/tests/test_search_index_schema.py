#!/usr/bin/env python3
"""Schema validation of the search index against the owned federation
contract (adaptive-learner-content#175).

adaptive-learner-content owns ``schema/search-index.schema.json`` and the
generator, and every content repository carries byte-identical copies of
both; yet ``validate_index`` once ran only the hand-maintained field list.
It must validate against the schema IN ADDITION to the hand checks, so
owner and copies enforce the same contract. Before this test the two could disagree silently - an
integer ``level`` passed the hand check (truthy) while violating the
contract's ``"type": "string"``.

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
    return {
        "repo": "astrapi69/adaptive-learner-content",
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
                "visibility": "visible",
                "review_status": "authored",
            }
        ],
    }


def root_sets() -> list[dict]:
    return [{"id": "example-set"}]


def test_schema_is_draft_2020_12() -> None:
    schema_path = REPO_ROOT / "schema" / "search-index.schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    assert schema.get("$schema") == "https://json-schema.org/draft/2020-12/schema"


def test_conforming_index_passes() -> None:
    errors: list[str] = []
    gsi.validate_index(minimal_index(), root_sets(), errors)
    assert errors == []


def test_schema_catches_what_the_hand_check_cannot() -> None:
    """Integer ``level`` is truthy, so the hand check is silent - only the
    contract's ``"type": "string"`` rejects it."""
    index = minimal_index()
    index["sets"][0]["level"] = 123
    errors: list[str] = []
    gsi.validate_index(index, root_sets(), errors)
    violations = [error for error in errors if error.startswith("schema:")]
    assert violations, "schema violation must be reported"
    assert any("level" in error for error in violations)


def test_schema_catches_a_missing_contract_field() -> None:
    index = minimal_index()
    del index["sets"][0]["domain"]
    errors: list[str] = []
    gsi.validate_index(index, root_sets(), errors)
    assert any(error.startswith("schema:") and "domain" in error for error in errors)
