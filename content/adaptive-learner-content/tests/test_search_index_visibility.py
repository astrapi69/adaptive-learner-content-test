"""Set-entry ``visibility`` in the search index (engine#83).

``visibility`` is a consumer-display hint on the manifest set entry
(learn-content-engine 0.14.0, schema 1.8, additive): ``hidden`` asks a
consumer app not to surface the set to learners. This repo's generator
mirrors the engine's ``asContentSetEntry`` projection: absent or
out-of-enum values normalize to ``"visible"``, so every index entry
carries a concrete value consumers can filter on without their own
defaulting.
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"

if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import generate_search_index as gsi  # noqa: E402


def test_absent_visibility_defaults_to_visible() -> None:
    """Absent flag means visible - every pre-1.8 manifest keeps its shape."""
    assert gsi.normalize_visibility(None) == "visible"


def test_hidden_passes_through() -> None:
    assert gsi.normalize_visibility("hidden") == "hidden"


def test_visible_passes_through() -> None:
    assert gsi.normalize_visibility("visible") == "visible"


def test_out_of_enum_normalizes_to_visible() -> None:
    """Engine parity: asContentSetEntry folds unknown values back to visible."""
    assert gsi.normalize_visibility("internal") == "visible"


def test_every_index_entry_carries_visibility() -> None:
    """The generator emits a concrete visibility on every set entry."""
    index, build_errors = gsi.build_index()
    assert not build_errors
    assert index["sets"], "index carries no sets"
    for entry in index["sets"]:
        assert entry["visibility"] in ("visible", "hidden")
