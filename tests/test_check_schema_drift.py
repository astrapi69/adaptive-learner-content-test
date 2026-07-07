"""Unit tests for the engine-pinned schema-mirror drift gate.

The drift gate compares the vendored mirror under ``schema/`` against the
npm tarball of the PINNED ``learn-content-engine`` release (see
``schema/engine-version.txt``). These tests are fully OFFLINE: they build a
fake npm tarball in ``tmp_path`` and drive the gate's core functions
directly — no registry access, mirroring the repo's rule that everything
except the drift CHECK itself must work without network.

RED/GREEN contract (TDD):
* a mirror byte-identical to the pinned tarball passes (exit 0),
* ANY manipulated mirror byte fails (exit 1, drift listed),
* the pin comes from ``schema/engine-version.txt`` (a deliberate PR bumps it),
* ``--update`` refreshes the mirror from the tarball.
"""
from __future__ import annotations

import io
import json
import sys
import tarfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import check_schema_drift as drift  # noqa: E402


def make_tarball(files: dict[str, bytes]) -> bytes:
    """Build an in-memory npm-style tarball (paths rooted at ``package/``)."""
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for name, data in files.items():
            info = tarfile.TarInfo(name=name)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
    return buf.getvalue()


SCHEMA_BYTES = json.dumps({"$id": "lesson", "x-schema-version": "9.9"}).encode()
MANIFEST_BYTES = json.dumps({"$id": "content-manifest"}).encode()
QUALITY_BYTES = json.dumps({"rules": {"minExercisesPerLesson": 5}}).encode()


def engine_tarball(**overrides: bytes) -> bytes:
    files = {
        "package/schema/lesson.schema.json": SCHEMA_BYTES,
        "package/schema/content-manifest.schema.json": MANIFEST_BYTES,
        "package/schema/quality-rules.json": QUALITY_BYTES,
    }
    files.update(overrides)
    return make_tarball(files)


def write_mirror(
    root: Path,
    lesson: bytes = SCHEMA_BYTES,
    manifest: bytes = MANIFEST_BYTES,
    quality: bytes = QUALITY_BYTES,
) -> None:
    (root / "schema").mkdir(parents=True, exist_ok=True)
    (root / "schema" / "lesson.schema.json").write_bytes(lesson)
    (root / "schema" / "content-manifest.schema.json").write_bytes(manifest)
    (root / "schema" / "quality-rules.json").write_bytes(quality)


def test_pin_is_read_from_engine_version_file() -> None:
    """The pinned engine version comes from schema/engine-version.txt."""
    pin_file = REPO_ROOT / "schema" / "engine-version.txt"
    assert pin_file.is_file(), "pin file schema/engine-version.txt must exist"
    pin = drift.read_pin()
    assert pin == pin_file.read_text(encoding="utf-8").strip()
    assert pin, "pin must be non-empty"
    parts = pin.split(".")
    assert len(parts) == 3 and all(p.isdigit() for p in parts), (
        f"pin must be an exact semver release, got {pin!r}"
    )


def test_tarball_url_targets_the_pinned_release() -> None:
    url = drift.tarball_url("0.3.1")
    assert url == (
        "https://registry.npmjs.org/learn-content-engine/-/learn-content-engine-0.3.1.tgz"
    )


def test_extract_reads_schema_files_from_tarball() -> None:
    tarball = engine_tarball()
    assert drift.extract(tarball, "package/schema/lesson.schema.json") == SCHEMA_BYTES


def test_green_when_mirror_matches_pinned_tarball(tmp_path: Path) -> None:
    write_mirror(tmp_path)
    rc = drift.compare(tmp_path, engine_tarball(), update=False)
    assert rc == 0


def test_red_on_manipulated_mirror(tmp_path: Path) -> None:
    """A single flipped byte in the vendored mirror must trip the gate."""
    write_mirror(tmp_path, lesson=SCHEMA_BYTES + b"\n")
    rc = drift.compare(tmp_path, engine_tarball(), update=False)
    assert rc == 1


def test_red_on_missing_mirror_file(tmp_path: Path) -> None:
    write_mirror(tmp_path)
    (tmp_path / "schema" / "content-manifest.schema.json").unlink()
    rc = drift.compare(tmp_path, engine_tarball(), update=False)
    assert rc == 1


def test_red_on_tampered_quality_rules(tmp_path: Path) -> None:
    """quality-rules.json is engine-mirrored (0.4.0+): tampering trips the gate."""
    write_mirror(tmp_path, quality=QUALITY_BYTES + b"\n// tampered")
    rc = drift.compare(tmp_path, engine_tarball(), update=False)
    assert rc == 1


def test_update_refreshes_mirror_from_tarball(tmp_path: Path) -> None:
    write_mirror(tmp_path, lesson=b"stale", manifest=b"stale", quality=b"stale")
    rc = drift.compare(tmp_path, engine_tarball(), update=True)
    assert rc == 0
    assert (tmp_path / "schema" / "lesson.schema.json").read_bytes() == SCHEMA_BYTES
    assert (
        tmp_path / "schema" / "content-manifest.schema.json"
    ).read_bytes() == MANIFEST_BYTES
    assert (
        tmp_path / "schema" / "quality-rules.json"
    ).read_bytes() == QUALITY_BYTES
    # after the refresh the gate is green
    assert drift.compare(tmp_path, engine_tarball(), update=False) == 0


def test_mirror_declares_no_app_source() -> None:
    """The gate's own docs must declare the ENGINE as the mirror source —
    no reference to the app repo remains in the drift mechanics."""
    text = (SCRIPTS_DIR / "check_schema_drift.py").read_text(encoding="utf-8")
    assert "learn-content-engine" in text
    assert "raw.githubusercontent.com" not in text
    assert "APP_REPO" not in text


def test_repo_mirror_matches_local_engine_tarball_when_available() -> None:
    """Full-loop check against the REAL pinned tarball if it is cached
    locally (env ENGINE_TARBALL) — skipped otherwise, so CI stays offline."""
    import os

    path = os.environ.get("ENGINE_TARBALL")
    if not path or not Path(path).is_file():
        import pytest

        pytest.skip("no local engine tarball (set ENGINE_TARBALL to run)")
    rc = drift.compare(REPO_ROOT, Path(path).read_bytes(), update=False)
    assert rc == 0
