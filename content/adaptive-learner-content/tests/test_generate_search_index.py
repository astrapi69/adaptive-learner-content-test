#!/usr/bin/env python3
"""The search index generator runs unchanged in every content repository.

adaptive-learner-content owns ``scripts/generate_search_index.py`` and every
content repository carries a byte-identical copy (``.github/ownership.json``).
So the generator cannot name this repository: it derives the ``owner/repo``
slug from the git remote (the scp-like SSH form, content-test#87, included),
looks the repository's trust level up in ``recommended-repos.json`` by that
slug (only the hub carries the registry; everywhere else the default
applies), and keeps the ``generated`` stamp when nothing of substance
changed, so a local run leaves no diff.

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


# --- the slug from the git remote -------------------------------------------


def test_slug_from_https_url() -> None:
    assert (
        gsi.slug_from_url("https://github.com/astrapi69/adaptive-learner-content-test.git")
        == "astrapi69/adaptive-learner-content-test"
    )


def test_slug_from_ssh_url() -> None:
    # scp-like form: the colon separates host and owner and must not
    # survive into the slug (content-test#87)
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


def test_repo_slug_comes_from_the_origin_remote(monkeypatch) -> None:
    monkeypatch.setattr(gsi, "origin_url", lambda: "git@github.com:astrapi69/alc-books.git")
    assert gsi.repo_slug() == "astrapi69/alc-books"


def test_repo_slug_falls_back_to_the_directory_name(monkeypatch) -> None:
    monkeypatch.setattr(gsi, "origin_url", lambda: "")
    assert gsi.repo_slug() == gsi.REPO_ROOT.name


def test_the_index_names_the_repository_it_was_built_in(monkeypatch) -> None:
    monkeypatch.setattr(gsi, "origin_url", lambda: "https://github.com/astrapi69/alc-books")
    index, _ = gsi.build_index()
    assert index["repo"] == "astrapi69/alc-books"


# --- the trust level from the registry --------------------------------------


def _registry(tmp_path: Path, monkeypatch, repos: list[dict]) -> None:
    registry = tmp_path / "recommended-repos.json"
    registry.write_text(json.dumps({"repos": repos}), encoding="utf-8")
    monkeypatch.setattr(gsi, "RECOMMENDED_REPOS", registry)


def test_trust_level_is_read_by_slug(tmp_path, monkeypatch) -> None:
    _registry(tmp_path, monkeypatch, [
        {"url": "https://github.com/astrapi69/adaptive-learner-content", "trust_level": 3},
        {"url": "https://github.com/astrapi69/alc-books", "trust_level": 1},
    ])
    assert gsi.repo_trust_level("astrapi69/adaptive-learner-content") == 3


def test_trust_level_defaults_when_the_repository_is_not_listed(tmp_path, monkeypatch) -> None:
    _registry(tmp_path, monkeypatch, [
        {"url": "https://github.com/astrapi69/adaptive-learner-content", "trust_level": 3},
    ])
    assert gsi.repo_trust_level("astrapi69/alc-books") == gsi.DEFAULT_TRUST_LEVEL


def test_trust_level_defaults_without_a_registry(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(gsi, "RECOMMENDED_REPOS", tmp_path / "absent.json")
    assert gsi.repo_trust_level("astrapi69/alc-books") == gsi.DEFAULT_TRUST_LEVEL


def test_trust_level_matches_whole_path_segments(tmp_path, monkeypatch) -> None:
    # "astrapi69/ai" must not borrow the level of "xastrapi69/ai"
    _registry(tmp_path, monkeypatch, [
        {"url": "https://github.com/xastrapi69/ai", "trust_level": 3},
    ])
    assert gsi.repo_trust_level("astrapi69/ai") == gsi.DEFAULT_TRUST_LEVEL


# --- a set entry without a path ---------------------------------------------


def test_a_set_without_a_path_is_an_error() -> None:
    errors: list[str] = []
    gsi.build_set_entry({"id": "no-path"}, 1, "2026-09-24T00:00:00Z", errors)
    assert any("no-path" in error and "path" in error for error in errors), errors


# --- the generated stamp -----------------------------------------------------


def _fixed_index(generated: str, lessons: int = 1) -> dict:
    return {
        "repo": "astrapi69/example",
        "generated": generated,
        "schema_version": "1.0",
        "sets": [],
        "total_lessons": lessons,
        "total_cards": 0,
    }


def _run_main(tmp_path, monkeypatch, committed: dict | None, fresh: dict) -> dict:
    index_path = tmp_path / "search-index.json"
    if committed is not None:
        index_path.write_text(gsi.serialize(committed), encoding="utf-8")
    monkeypatch.setattr(gsi, "INDEX_PATH", index_path)
    monkeypatch.setattr(gsi, "build_index", lambda: (fresh, []))
    assert gsi.main([]) == 0
    return json.loads(index_path.read_text(encoding="utf-8"))


def test_an_unchanged_index_keeps_its_generated_stamp(tmp_path, monkeypatch) -> None:
    written = _run_main(
        tmp_path, monkeypatch,
        committed=_fixed_index("2026-01-01T00:00:00Z"),
        fresh=_fixed_index("2026-09-24T06:00:00Z"),
    )
    assert written["generated"] == "2026-01-01T00:00:00Z"


def test_a_changed_index_gets_a_new_generated_stamp(tmp_path, monkeypatch) -> None:
    written = _run_main(
        tmp_path, monkeypatch,
        committed=_fixed_index("2026-01-01T00:00:00Z", lessons=1),
        fresh=_fixed_index("2026-09-24T06:00:00Z", lessons=2),
    )
    assert written["generated"] == "2026-09-24T06:00:00Z"
    assert written["total_lessons"] == 2


def test_a_first_index_is_written(tmp_path, monkeypatch) -> None:
    written = _run_main(tmp_path, monkeypatch, committed=None, fresh=_fixed_index("2026-09-24T06:00:00Z"))
    assert written["generated"] == "2026-09-24T06:00:00Z"


# --- card counting -----------------------------------------------------------


def _lessons(tmp_path: Path, bodies: dict[str, dict]) -> Path:
    (tmp_path / "lessons").mkdir()
    for name, body in bodies.items():
        (tmp_path / "lessons" / name).write_text(json.dumps(body), encoding="utf-8")
    return tmp_path


def test_a_lesson_without_cards_counts_zero(tmp_path) -> None:
    # ``cards`` is optional in the lesson schema (required: id, title,
    # steps); alc-psychology ships case lessons with exercises only.
    set_dir = _lessons(tmp_path, {
        "01.json": {"id": "a", "title": "A", "steps": [], "cards": [{"id": "c1"}, {"id": "c2"}]},
        "02.json": {"id": "b", "title": "B", "steps": []},
    })
    errors: list[str] = []
    assert gsi.count_cards(set_dir, ["01.json", "02.json"], errors, "probe") == 2
    assert errors == []


def test_cards_that_are_not_a_list_are_an_error(tmp_path) -> None:
    set_dir = _lessons(tmp_path, {"01.json": {"id": "a", "title": "A", "steps": [], "cards": {"id": "c1"}}})
    errors: list[str] = []
    gsi.count_cards(set_dir, ["01.json"], errors, "probe")
    assert any("cards" in error for error in errors), errors
