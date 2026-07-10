#!/usr/bin/env python3
"""Schema-mirror drift gate — pinned to a learn-content-engine release.

The JSON-Schema artefacts under ``schema/`` are a **mirror of
learn-content-engine ``schema/``** at the version pinned in
``schema/engine-version.txt`` (source-of-truth chain: learn-content-engine
(canonical) → this mirror). The engine is the canonical schema source; this
repo mirrors it, so content authors and third-party validators never
need the app.

The mirror stays VENDORED so everything except this drift CHECK works
offline (``validate_content.py`` and the shape-parity test read only the
committed files). This gate gives an engine-side schema change a visible
consequence here: CI goes red until the mirror is refreshed against a new,
deliberately bumped pin — no floating branch is ever compared against.

Mechanism: download the npm tarball of the PINNED engine release at CI
time and compare its ``package/schema/*.json`` byte-for-byte with the
committed mirror. The npm tarball (not a git tag) is the comparison
source because a published npm version is immutable (the registry refuses
re-publishing the same version, while git tags can be moved or deleted),
it is exactly the artefact validator consumers install via
``npm ci learn-content-engine@<pin>``, and it needs just one anonymous
HTTPS GET — no GitHub token, no git, still Python-stdlib-only.

Usage::

    python scripts/check_schema_drift.py            # CI gate: exit 1 on drift
    python scripts/check_schema_drift.py --update    # refresh the local mirror

Updating the pin is a deliberate PR: bump ``schema/engine-version.txt``,
run ``--update``, commit both together.

Env overrides (offline runs / tests):

    ENGINE_TARBALL   path to a local .tgz to use instead of the registry
    NPM_REGISTRY     registry base URL (default: https://registry.npmjs.org)

Stdlib only (urllib + tarfile) so the content repo needs no extra install.
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

ENGINE_PACKAGE = "learn-content-engine"
NPM_REGISTRY = os.environ.get("NPM_REGISTRY", "https://registry.npmjs.org")

# Local mirror path (relative to the repo root) -> member path inside the
# engine's npm tarball. The engine bundles its whole schema/ directory; the
# mirror carries the same set.
MIRRORED = {
    "schema/lesson.schema.json": "package/schema/lesson.schema.json",
    "schema/content-manifest.schema.json": (
        "package/schema/content-manifest.schema.json"
    ),
    "schema/quality-rules.json": "package/schema/quality-rules.json",
}


def read_pin() -> str:
    """The engine version this mirror is pinned to (schema/engine-version.txt)."""
    return PIN_FILE.read_text(encoding="utf-8").strip()


def tarball_url(pin: str) -> str:
    return f"{NPM_REGISTRY}/{ENGINE_PACKAGE}/-/{ENGINE_PACKAGE}-{pin}.tgz"


def fetch_tarball(pin: str) -> bytes:
    """The pinned release tarball: local override (ENGINE_TARBALL) or registry."""
    local = os.environ.get("ENGINE_TARBALL")
    if local:
        return Path(local).read_bytes()
    url = tarball_url(pin)
    req = urllib.request.Request(url, headers={"User-Agent": "schema-drift-check"})
    with urllib.request.urlopen(req, timeout=60) as resp:  # noqa: S310 (registry)
        if resp.status != 200:
            raise RuntimeError(f"GET {url} -> HTTP {resp.status}")
        return resp.read()


def extract(tarball: bytes, member: str) -> bytes:
    with tarfile.open(fileobj=io.BytesIO(tarball), mode="r:gz") as tar:
        fh = tar.extractfile(member)
        if fh is None:
            raise RuntimeError(f"{member}: not a regular file in the engine tarball")
        return fh.read()


def compare(mirror_root: Path, tarball: bytes, *, update: bool) -> int:
    """Core gate: byte-compare (or, with ``update``, refresh) the mirror.

    Pure function over explicit inputs so the offline unit tests can drive
    it against a temp directory and an in-memory tarball.
    """
    drift: list[str] = []
    for local_name, member in MIRRORED.items():
        canonical = extract(tarball, member)
        local_file = mirror_root / local_name

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
                f"{local_name}: differs from the pinned engine tarball "
                f"({member}: mirror {len(current)} bytes vs engine "
                f"{len(canonical)} bytes)"
            )

    if update:
        print("\nMirror refreshed. Review and commit schema/.")
        return 0

    if drift:
        print("\nSCHEMA DRIFT detected — the mirror is out of date:", file=sys.stderr)
        for d in drift:
            print(f"  - {d}", file=sys.stderr)
        print(
            "\nThe pinned learn-content-engine release is the mirror source."
            "\nRefresh the mirror with:\n"
            "    python scripts/check_schema_drift.py --update\n"
            "then commit schema/. To move to a NEW engine version, bump\n"
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
        help="overwrite the local mirror with the pinned engine schemas (refresh)",
    )
    args = parser.parse_args()

    pin = read_pin()
    print(f"Comparing schema mirror against {ENGINE_PACKAGE}@{pin} (npm tarball)\n")
    try:
        tarball = fetch_tarball(pin)
    except Exception as exc:  # network / 404 / etc.
        print(
            f"ERROR: could not fetch {ENGINE_PACKAGE}@{pin}: {exc}", file=sys.stderr
        )
        return 2
    return compare(REPO_ROOT, tarball, update=args.update)


if __name__ == "__main__":
    sys.exit(main())
