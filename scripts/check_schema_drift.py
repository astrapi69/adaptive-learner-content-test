#!/usr/bin/env python3
"""Schema-mirror drift gate (EXP-039).

The JSON-Schema artefacts under ``schema/`` AND the shared shape-parity
fixture under ``tests/fixtures/`` are MIRRORED from the app repository
``astrapi69/adaptive-learner`` — the app is the single source of truth (the
schema is generated from its Pydantic model; the fixture is the #1205 parity
contract). This repo keeps a byte-for-byte copy plus this gate so that an
app-side schema or fixture change has a visible consequence here (CI goes red
until the mirror is refreshed) instead of silently drifting apart. Refreshing
after an app schema change therefore pulls the mirror AND the fixture together,
so the cross-language parity (#699 / #1208) cannot silently rot.

Mechanism: pull the canonical artefacts from the app repo at CI time and
compare them byte-for-byte with the committed mirror.

Usage::

    python scripts/check_schema_drift.py            # CI gate: exit 1 on drift
    python scripts/check_schema_drift.py --update    # refresh the local mirror

Configurable via env (defaults target the app repo's default branch):

    APP_REPO   owner/name of the app repo   (default: astrapi69/adaptive-learner)
    APP_REF    git ref to compare against    (default: master)

Stdlib only (urllib) so the content repo needs no extra install for the gate.
"""
from __future__ import annotations

import argparse
import os
import sys
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_DIR = REPO_ROOT / "schema"

APP_REPO = os.environ.get("APP_REPO", "astrapi69/adaptive-learner")
APP_REF = os.environ.get("APP_REF", "master")
RAW_BASE = "https://raw.githubusercontent.com"

# Local mirror path (relative to the repo root) -> path of the original inside
# the app repo. The schema artefacts live under ``schema/`` on both sides; the
# shared shape-parity fixture lives next to its app-side test, so the mapping is
# kept explicit per file rather than assuming a shared directory.
MIRRORED = {
    "schema/lesson.schema.json": "schema/lesson.schema.json",
    "schema/quality-rules.json": "schema/quality-rules.json",
    "tests/fixtures/lesson-shape-parity.json": (
        "frontend/src/lib/content/__fixtures__/lesson-shape-parity.json"
    ),
}


def fetch(app_path: str) -> bytes:
    url = f"{RAW_BASE}/{APP_REPO}/{APP_REF}/{app_path}"
    req = urllib.request.Request(url, headers={"User-Agent": "schema-drift-check"})
    with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310 (trusted host)
        if resp.status != 200:
            raise RuntimeError(f"GET {url} -> HTTP {resp.status}")
        return resp.read()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--update",
        action="store_true",
        help="overwrite the local mirror with the app originals (refresh)",
    )
    args = parser.parse_args()

    print(f"Comparing schema mirror against {APP_REPO}@{APP_REF}\n")
    drift: list[str] = []
    errors: list[str] = []

    for local_name, app_path in MIRRORED.items():
        local_file = REPO_ROOT / local_name
        try:
            canonical = fetch(app_path)
        except Exception as exc:  # network / 404 / etc.
            errors.append(f"{local_name}: could not fetch {app_path}: {exc}")
            continue

        if args.update:
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
                f"{local_name}: differs from {APP_REPO}@{APP_REF}:{app_path} "
                f"(mirror {len(current)} bytes vs origin {len(canonical)} bytes)"
            )

    if errors:
        print("\nERROR: could not reach the app repo:", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        return 2

    if args.update:
        print("\nMirror refreshed. Review and commit schema/ and tests/fixtures/.")
        return 0

    if drift:
        print("\nSCHEMA DRIFT detected — the mirror is out of date:", file=sys.stderr)
        for d in drift:
            print(f"  - {d}", file=sys.stderr)
        print(
            "\nThe app is the source of truth. Refresh the mirror with:\n"
            "    python scripts/check_schema_drift.py --update\n"
            "then commit schema/ and tests/fixtures/.",
            file=sys.stderr,
        )
        return 1

    print("\nSchema mirror is in sync with the app.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
