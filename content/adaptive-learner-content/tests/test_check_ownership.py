"""Unit tests for the ownership check (scripts/check_ownership.py).

The ownership file names, per path, which side owns it. These tests pin
what the check derives from that: a copy of an owned file that is not the
owner's bytes is reported, so is a file a repository should carry and does
not, a hub-only file outside the hub, and a tracked file nobody owns.
"""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "check_ownership", REPO_ROOT / "scripts" / "check_ownership.py"
)
check_ownership = importlib.util.module_from_spec(SPEC)
sys.modules["check_ownership"] = check_ownership
SPEC.loader.exec_module(check_ownership)

OWNERS = {
    "template": "astrapi69/adaptive-learner-content-template",
    "hub": "astrapi69/adaptive-learner-content",
}
RULES = {
    "scripts/check_prose.py": "template",
    "scripts/generate_search_index.py": "hub",
    "scripts/validate_registry.py": "hub-only",
    "schema/lesson.schema.json": "engine",
    "README.md": "repo",
    "sets/*": "repo",
}
OWNER_FILES = {
    "template": {"scripts/check_prose.py": b"gate v3", "scripts/generate_search_index.py": b"index old"},
    "hub": {
        "scripts/check_prose.py": b"gate v1",
        "scripts/generate_search_index.py": b"index new",
        "scripts/validate_registry.py": b"registry",
    },
}


def findings(role, local_files):
    return check_ownership.ownership_findings(RULES, role, local_files, OWNER_FILES)


def in_line_content_repo(**overrides):
    files = {
        "scripts/check_prose.py": b"gate v3",
        "scripts/generate_search_index.py": b"index new",
        "README.md": b"own words",
        "sets/de/x/lessons/01.json": b"{}",
        "schema/lesson.schema.json": b"engine bytes",
    }
    files.update(overrides)
    return {path: body for path, body in files.items() if body is not None}


def test_a_content_repo_in_line_with_both_owners_has_no_findings():
    assert findings("content", in_line_content_repo()) == []


def test_reports_a_copy_that_differs_from_its_owner():
    stale = in_line_content_repo(**{"scripts/check_prose.py": b"gate v1"})
    assert findings("content", stale) == [("differs from template", "scripts/check_prose.py")]


def test_reports_an_owned_file_the_repository_does_not_carry():
    lacking = in_line_content_repo(**{"scripts/generate_search_index.py": None})
    assert findings("content", lacking) == [("missing", "scripts/generate_search_index.py")]


def test_the_template_carries_hub_files_as_copies_of_the_hub():
    template_files = {"scripts/check_prose.py": b"gate v3", "scripts/generate_search_index.py": b"index old"}
    assert findings("template", template_files) == [
        ("differs from hub", "scripts/generate_search_index.py"),
    ]


def test_the_owner_itself_is_not_compared_but_must_carry_its_files():
    hub_files = {"scripts/check_prose.py": b"gate v1", "scripts/validate_registry.py": b"registry"}
    assert findings("hub", hub_files) == [
        ("differs from template", "scripts/check_prose.py"),
        ("missing", "scripts/generate_search_index.py"),
    ]


def test_a_hub_only_file_outside_the_hub_is_reported():
    carrying = in_line_content_repo(**{"scripts/validate_registry.py": b"registry"})
    assert findings("content", carrying) == [("only the hub carries it", "scripts/validate_registry.py")]


def test_a_tracked_file_without_an_owner_is_reported():
    extra = in_line_content_repo(**{"tests/test_known_domain.py": b"local rule"})
    assert findings("content", extra) == [("no owner", "tests/test_known_domain.py")]


def test_repo_and_engine_files_are_never_compared():
    own = in_line_content_repo(**{"README.md": b"other words", "schema/lesson.schema.json": b"older pin"})
    assert findings("content", own) == []


def test_an_owned_file_the_owner_does_not_carry_is_reported_as_such():
    owner_files = {"template": {}, "hub": OWNER_FILES["hub"]}
    local = in_line_content_repo()
    result = check_ownership.ownership_findings(RULES, "content", local, owner_files)
    assert result == [("not in template", "scripts/check_prose.py")]


def test_owner_of_prefers_an_exact_row_and_matches_patterns_at_any_depth():
    rules = {"sets/*": "repo", "sets/README.md": "template"}
    assert check_ownership.owner_of("sets/README.md", rules) == "template"
    assert check_ownership.owner_of("sets/de/x/lessons/01.json", rules) == "repo"
    assert check_ownership.owner_of("docs/other.md", rules) is None


def test_role_of_names_the_two_owners_and_everything_else_content():
    assert check_ownership.role_of(OWNERS["template"], OWNERS) == "template"
    assert check_ownership.role_of(OWNERS["hub"], OWNERS) == "hub"
    assert check_ownership.role_of("astrapi69/alc-books", OWNERS) == "content"


def _ownership_text(**overrides):
    document = {"owners": OWNERS, "paths": RULES}
    document.update(overrides)
    return json.dumps(document)


def test_load_accepts_the_documented_shape():
    owners, rules = check_ownership.load_ownership(_ownership_text())
    assert owners == OWNERS
    assert rules == RULES


@pytest.mark.parametrize(
    "broken",
    [
        {"owners": {"template": OWNERS["template"]}},
        {"paths": {"scripts/x.py": "nobody"}},
        {"paths": {"scripts/*": "template"}},
        {"paths": []},
    ],
    ids=["hub-owner-missing", "unknown-owner", "pattern-for-a-compared-owner", "paths-not-a-map"],
)
def test_load_rejects_a_malformed_file(broken):
    with pytest.raises(check_ownership.OwnershipError):
        check_ownership.load_ownership(_ownership_text(**broken))


def test_every_tracked_file_of_this_repository_has_an_owner():
    # Runs in every repository that carries this test: a new file without a
    # row turns the PR red where it is added, not a night later.
    text = (REPO_ROOT / ".github" / "ownership.json").read_text(encoding="utf-8")
    _, rules = check_ownership.load_ownership(text)
    tracked = subprocess.run(
        ["git", "ls-files", "-z"], cwd=REPO_ROOT, capture_output=True, text=True, check=True
    ).stdout.split("\0")
    unowned = [path for path in tracked if path and check_ownership.owner_of(path, rules) is None]
    assert unowned == []


def _git_repository(root: Path, files: dict[str, bytes]) -> Path:
    root.mkdir(parents=True)
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    for path, body in files.items():
        target = root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(body)
    subprocess.run(["git", "add", "-A"], cwd=root, check=True)
    return root


def _ownership_bytes() -> bytes:
    rules = {".github/ownership.json": "template", **RULES}
    return json.dumps({"owners": OWNERS, "paths": rules}).encode()


def _run(tmp_path, content_files, capsys):
    ownership = _ownership_bytes()
    template = _git_repository(tmp_path / "template", {".github/ownership.json": ownership, **OWNER_FILES["template"]})
    hub = _git_repository(tmp_path / "hub", {".github/ownership.json": ownership, **OWNER_FILES["hub"]})
    repository = _git_repository(tmp_path / "repo", {".github/ownership.json": ownership, **content_files})
    status = check_ownership.main([
        "--template", str(template), "--hub", str(hub),
        "--repository", "astrapi69/alc-books", "--root", str(repository),
    ])
    return status, capsys.readouterr().out


def test_main_exits_0_when_in_line(tmp_path, capsys):
    status, out = _run(tmp_path, in_line_content_repo(), capsys)
    assert status == 0
    assert "in line" in out


def test_main_exits_1_and_lists_the_findings(tmp_path, capsys):
    status, out = _run(tmp_path, in_line_content_repo(**{"scripts/check_prose.py": b"gate v1"}), capsys)
    assert status == 1
    assert "differs from template" in out and "scripts/check_prose.py" in out


def test_main_exits_2_when_an_owner_checkout_is_missing(tmp_path, capsys):
    repository = _git_repository(tmp_path / "repo", {"README.md": b"x"})
    status = check_ownership.main([
        "--template", str(tmp_path / "nowhere"), "--hub", str(tmp_path / "nowhere"),
        "--repository", "astrapi69/alc-books", "--root", str(repository),
    ])
    assert status == 2
