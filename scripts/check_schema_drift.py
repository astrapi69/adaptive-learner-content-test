#!/usr/bin/env python3
"""Schema-mirror drift gate — pinned to the learn-content-engine release.

The JSON Schema under ``schema/lesson.schema.json`` is a MIRROR of the
`learn-content-engine <https://github.com/astrapi69/learn-content-engine>`_
package (source-of-truth chain: **adaptive-learner Pydantic -> engine ->
this mirror**). The engine vendors the app-generated schema via its
documented schema-sync procedure and ships it in every npm release; this
repo keeps a byte-for-byte copy plus this gate so an engine schema bump
has a visible consequence here (CI goes red until the mirror + pin are
refreshed) instead of silently drifting apart.

The comparison target is the **npm tarball of the pinned engine version**
(``schema/engine-version.txt``), i.e. exactly the artifact consumers
install — chosen over a git-tag checkout because published npm versions
are immutable (a git tag can be force-moved), need no git/auth/API on the
runner, and are a single HTTPS GET. Bumping the pin is a deliberate PR
that edits ``schema/engine-version.txt`` and refreshes the mirror —
never a floating branch.

The mirror itself stays VENDORED so ``validate_content.py`` and the
shape-parity test keep working fully offline; only this gate needs the
network (CI), and even it can be pointed at a local tarball.

Usage::

    python scripts/check_schema_drift.py            # CI gate: exit 1 on drift
    python scripts/check_schema_drift.py --update    # refresh the local mirror

Configurable via env:

    ENGINE_VERSION   overrides the pin from schema/engine-version.txt
    ENGINE_TARBALL   path or URL of a tarball to compare against
                     (used by the offline tests; bypasses the registry)

Stdlib only (urllib + tarfile) so the gate needs no extra install.
"""
from __future__ import annotations

import argparse
import io
import os
import sys
import tarfile
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
PIN_FILE = REPO_ROOT / "schema" / "engine-version.txt"

REGISTRY_BASE = "https://registry.npmjs.org/learn-content-engine/-"

# Local mirror path (relative to the repo root) -> member path inside the
# engine npm tarball. Only the engine-shipped artifacts are drift-checked;
# ``schema/quality-rules.json`` and the shape-parity fixture are owned by
# this repo (see schema/README.md) and are deliberately NOT listed here.
MIRRORED = {
    "schema/lesson.schema.json": "package/schema/lesson.schema.json",
}


def read_pin(pin_file: Path = PIN_FILE) -> str:
    """Return the pinned engine version from the version file."""
    return pin_file.read_text(encoding="utf-8").strip()


def tarball_url(version: str) -> str:
    """Registry URL of the engine tarball for ``version`` (immutable)."""
    return f"{REGISTRY_BASE}/learn-content-engine-{version}.tgz"


def load_tarball(source: str) -> bytes:
    """Fetch the tarball bytes from a URL or a local path."""
    if source.startswith(("http://", "https://")):
        req = urllib.request.Request(
            source, headers={"User-Agent": "schema-drift-check"}
        )
        with urllib.request.urlopen(req, timeout=60) as resp:  # noqa: S310
            if resp.status != 200:
                raise RuntimeError(f"GET {source} -> HTTP {resp.status}")
            return resp.read()
    return Path(source).read_bytes()


def extract_member(tar_bytes: bytes, member: str) -> bytes:
    """Return one file's bytes out of the (gzipped) tarball."""
    with tarfile.open(fileobj=io.BytesIO(tar_bytes), mode="r:gz") as tar:
        fileobj = tar.extractfile(member)
        if fileobj is None:
            raise RuntimeError(f"{member}: not found in engine tarball")
        return fileobj.read()


def run_check(
    tarball_source: str | None = None,
    repo_root: Path = REPO_ROOT,
    update: bool = False,
) -> int:
    """Compare (or, with ``update=True``, refresh) the mirror.

    Returns 0 on parity / successful update, 1 on drift, 2 on
    fetch/extract errors.
    """
    if tarball_source is None:
        version = os.environ.get("ENGINE_VERSION") or read_pin()
        tarball_source = os.environ.get("ENGINE_TARBALL") or tarball_url(version)
        print(f"Comparing schema mirror against learn-content-engine {version}")
    print(f"Tarball: {tarball_source}\n")

    try:
        tar_bytes = load_tarball(tarball_source)
    except Exception as exc:  # network / 404 / bad path
        print(f"ERROR: could not fetch engine tarball: {exc}", file=sys.stderr)
        return 2

    drift: list[str] = []
    for local_name, member in MIRRORED.items():
        local_file = repo_root / local_name
        try:
            canonical = extract_member(tar_bytes, member)
        except Exception as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 2

        if update:
            local_file.parent.mkdir(parents=True, exist_ok=True)
            local_file.write_bytes(canonical)
            print(f"UPDATED  {local_name}  ({len(canonical)} bytes)")
            continue

        if not local_file.is_file():
            drift.append(f"{local_name}: missing from the mirror")
            continue
        current = local_file.read_bytes()
        if current == canonical:
            print(f"OK       {local_name}")
        else:
            drift.append(
                f"{local_name}: differs from the engine tarball's {member} "
                f"(mirror {len(current)} bytes vs engine {len(canonical)} bytes)"
            )

    if update:
        print(
            "\nMirror refreshed from the engine tarball. Review and commit "
            "schema/ (and bump schema/engine-version.txt in the same PR if "
            "you pinned a new engine version)."
        )
        return 0

    if drift:
        print(
            "\nSCHEMA DRIFT detected — mirror != pinned engine release:",
            file=sys.stderr,
        )
        for d in drift:
            print(f"  - {d}", file=sys.stderr)
        print(
            "\nThe engine release is the mirror source. Refresh with:\n"
            "    python scripts/check_schema_drift.py --update\n"
            "then commit schema/. To move to a NEW engine version, edit\n"
            "schema/engine-version.txt in the same (deliberate) PR.",
            file=sys.stderr,
        )
        return 1

    print("\nSchema mirror is in sync with the pinned engine release.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--update",
        action="store_true",
        help="overwrite the local mirror with the pinned engine artifacts",
    )
    args = parser.parse_args()
    return run_check(update=args.update)


if __name__ == "__main__":
    sys.exit(main())
