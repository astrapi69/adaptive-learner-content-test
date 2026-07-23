#!/usr/bin/env python3
"""Set-entry ``visibility`` in the search index (engine#83).

``visibility`` is a consumer-display hint on the manifest set entry
(learn-content-engine 0.14.0, schema 1.8, additive): ``hidden`` asks a
consumer app not to surface the set to learners. The generator mirrors
the engine's ``asContentSetEntry`` projection: absent or out-of-enum
values normalize to ``"visible"``, so every index entry carries a
concrete value consumers can filter on without their own defaulting.

Runs under pytest (``python -m pytest tests -q``).
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"

if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import generate_search_index as gsi  # noqa: E402


def test_slug_from_https_url() -> None:
    assert (
        gsi.slug_from_url("https://github.com/astrapi69/adaptive-learner-content-test.git")
        == "astrapi69/adaptive-learner-content-test"
    )


def test_slug_from_ssh_url() -> None:
    """Regression guard for #87: the scp-like SSH form separates host and
    owner with a colon; the slug must not keep the git@host: prefix."""
    assert (
        gsi.slug_from_url("git@github.com:astrapi69/adaptive-learner-content-test.git")
        == "astrapi69/adaptive-learner-content-test"
    )


def test_slug_from_ssh_scheme_url() -> None:
    assert (
        gsi.slug_from_url("ssh://git@github.com/astrapi69/adaptive-learner-content-test")
        == "astrapi69/adaptive-learner-content-test"
    )


def test_slug_from_url_without_git_suffix_and_trailing_slash() -> None:
    assert (
        gsi.slug_from_url("https://github.com/astrapi69/adaptive-learner-content-test/")
        == "astrapi69/adaptive-learner-content-test"
    )


def test_slug_from_unusable_url_is_none() -> None:
    assert gsi.slug_from_url("") is None
    assert gsi.slug_from_url("just-a-name") is None


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


def test_graded_quiz_demo_stays_hidden() -> None:
    """Regression guard for adaptive-learner#1707: the graded-quiz demo is
    a conformance fixture (the deliberate E-EXT-UNSUPPORTED negative case),
    not learner content. It must stay in the repo for engine validation
    but must never surface in a consumer app, so its index entry carries
    visibility "hidden"."""
    index, build_errors = gsi.build_index()
    assert not build_errors
    demo_entry = next(
        entry for entry in index["sets"] if entry["id"] == "graded-quiz-demo-from-de"
    )
    assert demo_entry["visibility"] == "hidden"
