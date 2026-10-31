"""Guard: ``ai_validation`` never lives inside a strict set entry.

``ai_validation`` is a content-repo-local provenance block (which AI
reviewed the set, when, with what result). The canonical manifest format
(engine ``content-manifest.schema.json``, strict
``additionalProperties: false``) does not know it, so it must live in the
set manifest's free-form top-level ``metadata`` block, NOT in the strict
set entry. This guard runs in every content repository (the file is owned
by adaptive-learner-content and copied everywhere); the positive index pin
(metadata block -> ``ai_validated`` flag) belongs to alc-ai and its
ki-einsteiger set (``tests/test_ki_einsteiger_ai_validated.py`` there,
adaptive-learner-content#144).
"""
from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_ai_validation_not_in_strict_set_entries() -> None:
    """No set manifest may carry ``ai_validation`` inside a set ENTRY:
    the canonical (engine) manifest schema rejects unknown fields there."""
    import yaml

    offenders = []
    for manifest_path in sorted(REPO_ROOT.glob("sets/*/*/manifest.yaml")):
        doc = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
        for entry in doc.get("sets") or []:
            if "ai_validation" in entry:
                offenders.append(str(manifest_path.relative_to(REPO_ROOT)))
    assert not offenders, (
        f"ai_validation must live under the manifest's free-form metadata "
        f"block, not the strict set entry: {offenders}"
    )
