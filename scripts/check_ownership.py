#!/usr/bin/env python3
"""Ownership check: every copy of an owned file is its owner's bytes.

The content repositories share their tooling, and the sharing ran on copies
nobody compared. The copies drifted three times the same way: the adopted
ext: list, the engine schemas, and the prose gate, which was one version
behind the template a day after all nine repositories had been brought in
line. And the hub, the repository the template was cut from, had grown its
own versions of the template's files, so for the one repository it came from
the template was no longer canonical.

``.github/ownership.json`` settles that per path, and this check reads it. The
file names the owner of every path:

* ``template`` - canonical in the template (author tooling: validation, drift
  checks, prose gate, exports, Makefile). Every content repository carries a
  byte-identical copy.
* ``hub`` - canonical in adaptive-learner-content (search index and
  federation). Every content repository carries a byte-identical copy.
* ``hub-only`` - only the hub carries it (registry, federation docs, AI
  review).
* ``repo`` - each repository's own (its content, manifests, README, and
  tests that pin its own sets). Not compared.
* ``engine`` - the mirror of the pinned engine release under ``schema/``.
  Compared against the pin by ``schema-drift.yml``, not here.

A path pattern (``sets/*``) may only name ``repo`` or ``engine``: an owned
file that other repositories copy has to be listed by name, so the list says
exactly what is copied.

The rules are read from the TEMPLATE's copy of the file, not the local one,
so a repository with a stale ownership file is measured against the current
rules (and its stale copy is itself a finding).

Findings: ``differs from <owner>``, ``missing`` (an owned file this
repository should carry), ``not in <owner>`` (the owner does not carry a
file it owns), ``only the hub carries it``, and ``no owner`` (a tracked file
no row names; a file without a row is not "the repository's", it is
unmentioned).

Usage (the Ownership workflow checks the owners out next to the repository):
    python3 scripts/check_ownership.py --template DIR --hub DIR \\
        --repository OWNER/NAME [--root .]

Exit codes: 0 in line, 1 findings, 2 the check itself cannot run (an owner
checkout or the ownership file is missing or malformed).
"""
from __future__ import annotations

import argparse
import fnmatch
import json
import subprocess
import sys
from pathlib import Path

OWNERSHIP_FILE = ".github/ownership.json"
COMPARED = ("template", "hub")
OWNER_KINDS = COMPARED + ("hub-only", "repo", "engine")
PATTERN_KINDS = ("repo", "engine")


class OwnershipError(ValueError):
    """The ownership file is missing or does not have the documented shape."""


def load_ownership(text: str) -> tuple[dict[str, str], dict[str, str]]:
    """(owners, rules) from the ownership file's text: ``owners`` maps
    ``template`` and ``hub`` to their repositories, ``rules`` maps each path
    or pattern to its owner kind. Raises OwnershipError on a malformed file."""
    try:
        document = json.loads(text)
    except ValueError as error:
        raise OwnershipError(f"not JSON: {error}") from error
    owners = document.get("owners")
    rules = document.get("paths")
    if not isinstance(owners, dict) or any(not isinstance(owners.get(kind), str) for kind in COMPARED):
        raise OwnershipError("'owners' must name the template and the hub repository")
    if not isinstance(rules, dict):
        raise OwnershipError("'paths' must map each path to its owner")
    for path, owner in rules.items():
        if owner not in OWNER_KINDS:
            raise OwnershipError(f"{path}: unknown owner {owner!r} (one of {', '.join(OWNER_KINDS)})")
        if _is_pattern(path) and owner not in PATTERN_KINDS:
            raise OwnershipError(f"{path}: a pattern may only name {' or '.join(PATTERN_KINDS)}; list copied files by name")
    return owners, rules


def _is_pattern(path: str) -> bool:
    return any(character in path for character in "*?[")


def owner_of(path: str, rules: dict[str, str]) -> str | None:
    """The owner kind of ``path``: its exact row if there is one, else the
    first pattern that matches it (``*`` spans directories), else None."""
    if path in rules:
        return rules[path]
    for pattern, owner in rules.items():
        if _is_pattern(pattern) and fnmatch.fnmatchcase(path, pattern):
            return owner
    return None


def role_of(repository: str, owners: dict[str, str]) -> str:
    """``template``, ``hub``, or ``content`` for every other repository."""
    for kind in COMPARED:
        if owners[kind] == repository:
            return kind
    return "content"


def ownership_findings(
    rules: dict[str, str],
    role: str,
    local_files: dict[str, bytes],
    owner_files: dict[str, dict[str, bytes]],
) -> list[tuple[str, str]]:
    """(finding, path) pairs for a repository in ``role`` whose tracked files
    are ``local_files`` (path -> bytes), measured against the owners' copies
    in ``owner_files`` (owner kind -> path -> bytes). Sorted by path."""
    found = []
    for path, owner in rules.items():
        if _is_pattern(path):
            continue
        if owner == "hub-only":
            if role != "hub" and path in local_files:
                found.append(("only the hub carries it", path))
            elif role == "hub" and path not in local_files:
                found.append(("missing", path))
            continue
        if owner not in COMPARED:
            continue
        if path not in local_files:
            found.append(("missing", path))
        elif role != owner:
            canonical = owner_files[owner].get(path)
            if canonical is None:
                found.append((f"not in {owner}", path))
            elif canonical != local_files[path]:
                found.append((f"differs from {owner}", path))
    found.extend(("no owner", path) for path in local_files if owner_of(path, rules) is None)
    return sorted(found, key=lambda finding: (finding[1], finding[0]))


def _tracked(root: Path) -> list[str]:
    listing = subprocess.run(
        ["git", "ls-files", "-z"], cwd=root, capture_output=True, text=True, check=True
    ).stdout
    return [path for path in listing.split("\0") if path]


def _owned_bytes(root: Path, paths: list[str]) -> dict[str, bytes]:
    return {path: (root / path).read_bytes() for path in paths if (root / path).is_file()}


def report(findings: list[tuple[str, str]], repository: str, role: str) -> str:
    """The findings as text, one per line, with a header naming the
    repository and its role."""
    if not findings:
        return f"ownership: {repository} ({role}) is in line with the ownership file"
    width = max(len(kind) for kind, _ in findings)
    lines = [f"ownership: {len(findings)} finding(s) in {repository} ({role})"]
    lines += [f"  {kind:<{width}}  {path}" for kind, path in findings]
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--template", required=True, type=Path, help="checkout of the template")
    parser.add_argument("--hub", required=True, type=Path, help="checkout of the hub")
    parser.add_argument("--repository", required=True, help="OWNER/NAME of the repository checked")
    parser.add_argument("--root", default=Path("."), type=Path, help="checkout of the repository checked")
    arguments = parser.parse_args(argv)

    try:
        text = (arguments.template / OWNERSHIP_FILE).read_text(encoding="utf-8")
        owners, rules = load_ownership(text)
    except (OSError, OwnershipError) as error:
        print(f"ownership: cannot read the template's {OWNERSHIP_FILE}: {error}", file=sys.stderr)
        return 2
    if not arguments.hub.is_dir():
        print(f"ownership: no hub checkout at {arguments.hub}", file=sys.stderr)
        return 2

    owned = [path for path, owner in rules.items() if owner in COMPARED]
    tracked = _tracked(arguments.root)
    local_files = {path: b"" for path in tracked}
    local_files.update(_owned_bytes(arguments.root, [path for path in owned if path in local_files]))
    owner_files = {"template": _owned_bytes(arguments.template, owned), "hub": _owned_bytes(arguments.hub, owned)}
    role = role_of(arguments.repository, owners)

    findings = ownership_findings(rules, role, local_files, owner_files)
    print(report(findings, arguments.repository, role))
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
