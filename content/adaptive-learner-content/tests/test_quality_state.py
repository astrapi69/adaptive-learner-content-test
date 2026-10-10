"""Unit tests for scripts/quality_state.py.

The workflows are owned by the template and identical in every repository;
two decisions are not, and they live in the repository's own
.github/quality-state.json: whether the prose gate blocks yet, and which
author warnings the repository has decided to keep. These tests pin how the
workflows read that file.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("quality_state", REPO_ROOT / "scripts" / "quality_state.py")
quality_state = importlib.util.module_from_spec(SPEC)
sys.modules["quality_state"] = quality_state
SPEC.loader.exec_module(quality_state)


# --- the state file -----------------------------------------------------------


def test_a_missing_state_file_means_the_defaults(tmp_path):
    assert quality_state.load_state(tmp_path / "missing.json") == {}


def test_a_malformed_blocking_flag_fails_loudly(tmp_path):
    path = tmp_path / "state.json"
    path.write_text(json.dumps({"prose_gate": {"blocking": "no"}}))
    with pytest.raises(ValueError, match="blocking"):
        quality_state.load_state(path)


def test_an_accepted_warning_needs_a_reason_and_a_date(tmp_path):
    path = tmp_path / "state.json"
    path.write_text(json.dumps({"accepted_warnings": [{"rule": "W-X", "ids": []}]}))
    with pytest.raises(ValueError, match="reason"):
        quality_state.load_state(path)


# --- the prose gate -----------------------------------------------------------


def test_a_clean_prose_run_passes():
    assert quality_state.prose_exit_code({}, 0) == 0


def test_findings_block_by_default():
    assert quality_state.prose_exit_code({}, 1) == 1


def test_a_recorded_backlog_turns_findings_non_blocking():
    state = {"prose_gate": {"blocking": False, "since": "2026-09-23", "reason": "backlog"}}
    assert quality_state.prose_exit_code(state, 1) == 0


def test_a_broken_gate_is_never_masked():
    # Exit 2 means the gate itself failed (for example no tracked files); a
    # recorded backlog must not turn a broken check into a green one.
    state = {"prose_gate": {"blocking": False, "since": "2026-09-23", "reason": "backlog"}}
    assert quality_state.prose_exit_code(state, 2) == 2


def test_the_prose_report_ends_with_the_totals_and_names_the_backlog():
    output = (
        "docs/a.md:3: wort - German written without its umlaut, correct is wört\n"
        "docs/a.md:9: U+2014 EM DASH - EM DASH (write a hyphen or a comma)\n"
        "sets/b.json:1: U+2014 EM DASH - EM DASH (write a hyphen or a comma)\n"
        "\nPROSE GATE: 2 banned character(s) and 1 substituted German word(s) in 5 tracked file(s).\n"
    )
    state = {"prose_gate": {"blocking": False, "since": "2026-09-23", "reason": "cleanup follows"}}
    report = quality_state.prose_report(output, state, 1)
    assert "| `docs/a.md` | 2 |" in report
    assert "Non-blocking since 2026-09-23" in report
    assert "cleanup follows" in report
    assert report.rstrip().endswith("tracked file(s).")


def test_the_prose_report_never_caps_in_silence():
    output = "".join(f"f{i}.md:1: wort - German written without its umlaut\n" for i in range(55))
    report = quality_state.prose_report(output, {}, 1)
    assert "and 5 more file(s)" in report


# --- warnings -----------------------------------------------------------------

WARNINGS_OUTPUT = """engine-validate: 1 lesson(s) checked

WARN sets/de/x/lessons/01-a.json
   [W-CLOZE-NO-CARRIER] /steps/1/exercise/sentence the sentence carries nothing but its blanks
   [W-CARD-UNUSED] /cards 1 card is defined but never referenced
"""


def _lesson(tmp_path):
    lesson = tmp_path / "sets/de/x/lessons/01-a.json"
    lesson.parent.mkdir(parents=True)
    lesson.write_text(
        json.dumps(
            {
                "steps": [
                    {"id": "intro", "type": "theory"},
                    {"id": "ex-1", "type": "exercise", "exercise": {"id": "ex-1", "stable_id": "ex-abc"}},
                ]
            }
        )
    )
    return tmp_path


def test_warnings_are_parsed_per_file(tmp_path):
    findings = quality_state.parse_warnings(WARNINGS_OUTPUT)
    assert [(f.path, f.rule, f.pointer) for f in findings] == [
        ("sets/de/x/lessons/01-a.json", "W-CLOZE-NO-CARRIER", "/steps/1/exercise/sentence"),
        ("sets/de/x/lessons/01-a.json", "W-CARD-UNUSED", "/cards"),
    ]


def test_a_finding_on_an_exercise_is_identified_by_its_stable_id(tmp_path):
    root = _lesson(tmp_path)
    finding = quality_state.parse_warnings(WARNINGS_OUTPUT)[0]
    assert quality_state.element_key(finding, root) == "ex-abc"


def test_a_finding_without_an_exercise_falls_back_to_file_and_pointer(tmp_path):
    root = _lesson(tmp_path)
    finding = quality_state.parse_warnings(WARNINGS_OUTPUT)[1]
    assert quality_state.element_key(finding, root) == "sets/de/x/lessons/01-a.json#/cards"


def test_accepted_warnings_are_compared_as_sets_not_counts(tmp_path):
    # Same count, different elements: one resolved, one new. A count alone
    # would call this "as accepted".
    accepted = {"rule": "W-CLOZE-NO-CARRIER", "since": "2026-09-23", "reason": "r", "ids": ["ex-old", "ex-abc"]}
    status = quality_state.compare_accepted(accepted, {"ex-abc", "ex-new"})
    assert status.new == ["ex-new"]
    assert status.resolved == ["ex-old"]
    assert not status.unchanged


def test_the_warnings_report_shows_the_decision_next_to_the_number(tmp_path):
    root = _lesson(tmp_path)
    state = {
        "accepted_warnings": [
            {
                "rule": "W-CLOZE-NO-CARRIER",
                "since": "2026-09-23",
                "reason": "legacy modelling, renders correctly",
                "decision": "https://example.org/decision",
                "ids": ["ex-abc"],
            }
        ]
    }
    report = quality_state.warnings_report(WARNINGS_OUTPUT, state, root)
    assert "| `W-CLOZE-NO-CARRIER` | 1 | 1 since 2026-09-23 | as accepted |" in report
    assert "| `W-CARD-UNUSED` | 1 | - | |" in report
    assert "legacy modelling, renders correctly" in report
    assert "https://example.org/decision" in report


def test_accepting_records_the_ids_count_date_and_reason(tmp_path):
    root = _lesson(tmp_path)
    state = quality_state.accept_warnings(
        {}, "W-CLOZE-NO-CARRIER", WARNINGS_OUTPUT, root, reason="kept on purpose", since="2026-09-23"
    )
    [entry] = state["accepted_warnings"]
    assert entry == {
        "rule": "W-CLOZE-NO-CARRIER",
        "count": 1,
        "since": "2026-09-23",
        "reason": "kept on purpose",
        "ids": ["ex-abc"],
    }
