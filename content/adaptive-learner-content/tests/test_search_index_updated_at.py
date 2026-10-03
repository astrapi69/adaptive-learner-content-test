"""``updated_at`` is serialized canonically: UTC with a ``Z`` suffix.

``git log -1 --format=%cI`` emits the committer's local offset (e.g.
``+02:00``) while the generator's own fallback emits ``Z`` - consumers
that compare against Z-suffixed timestamps then see identical instants
as different strings and report spurious "stale" diffs across
environments (adaptive-learner-content#129). These tests pin the fix: ONE canonical
serialization at the generation point, regardless of the source.
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import generate_search_index as gsi  # noqa: E402

GENERATED_FALLBACK = "2026-06-15T12:23:01Z"


def updated_at_with_git_stamp(monkeypatch, stamp: str | None) -> str:
    """``build_set_entry``'s updated_at with ``git_updated_at`` forced to ``stamp``."""
    monkeypatch.setattr(gsi, "git_updated_at", lambda set_dir: stamp)
    entry = gsi.build_set_entry(
        {"id": "stamp-probe", "path": "sets/de/stamp-probe"},
        1,
        GENERATED_FALLBACK,
        [],
    )
    return entry["updated_at"]


def test_git_offset_stamp_is_canonicalized_to_utc_z(monkeypatch) -> None:
    """Reproduction (#129): a local-offset git stamp must come out as UTC/Z."""
    assert (
        updated_at_with_git_stamp(monkeypatch, "2026-06-15T14:23:01+02:00")
        == "2026-06-15T12:23:01Z"
    )


def test_git_source_and_fallback_serialize_identically(monkeypatch) -> None:
    """Happy path: the same instant serializes identically from BOTH sources."""
    from_git = updated_at_with_git_stamp(monkeypatch, "2026-06-15T14:23:01+02:00")
    from_fallback = updated_at_with_git_stamp(monkeypatch, None)
    assert from_git == from_fallback == GENERATED_FALLBACK


def test_naive_stamp_is_taken_as_utc() -> None:
    """Edge: a naive ISO stamp (no offset) is treated as already-UTC."""
    assert gsi.canonical_utc("2026-06-15T12:23:01") == "2026-06-15T12:23:01Z"


def test_canonical_stamps_pass_through_unchanged() -> None:
    """Boundary: ``+00:00`` and ``Z`` are the same instant - both yield ``Z``."""
    assert gsi.canonical_utc("2026-06-27T18:57:58+00:00") == "2026-06-27T18:57:58Z"
    assert gsi.canonical_utc("2026-06-27T18:57:58Z") == "2026-06-27T18:57:58Z"
