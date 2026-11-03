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
    findings = quality_state.parse_findings(WARNINGS_OUTPUT)
    assert [(f.path, f.rule, f.pointer) for f in findings] == [
        ("sets/de/x/lessons/01-a.json", "W-CLOZE-NO-CARRIER", "/steps/1/exercise/sentence"),
        ("sets/de/x/lessons/01-a.json", "W-CARD-UNUSED", "/cards"),
    ]


def test_a_finding_on_an_exercise_is_identified_by_its_stable_id(tmp_path):
    root = _lesson(tmp_path)
    finding = quality_state.parse_findings(WARNINGS_OUTPUT)[0]
    assert quality_state.element_key(finding, root) == "ex-abc"


def test_a_finding_without_an_exercise_falls_back_to_file_and_pointer(tmp_path):
    root = _lesson(tmp_path)
    finding = quality_state.parse_findings(WARNINGS_OUTPUT)[1]
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


# --- a rule raised to an error (template#101) ---------------------------------
# Raising a rule renames it: the tier is the prefix of its ID, so 0.38.0 turned
# W-MANIFEST-ENTRY-MISMATCH into E-MANIFEST-ENTRY-MISMATCH (engine#256). The
# runner prints the engine's rename table (RENAMED_RULE_IDS, followed with
# currentRuleId) and the errors with their IDs, so a record kept under the old
# name is still recognized. This output is the example in the template README.

RAISED_OUTPUT = """engine-validate: 1 lesson(s), 2 manifest(s) checked - 1 file(s) with errors, 0 warning(s)
RENAMED W-MANIFEST-ENTRY-MISMATCH -> E-MANIFEST-ENTRY-MISMATCH

✗ sets/de/x/manifest.yaml
   [E-MANIFEST-ENTRY-MISMATCH] /sets/0/description set 'x': 'description' is "Root text" in the root manifest but "Set text" in the set manifest; the two must be identical
"""

RAISED_RECORD = {
    "rule": "W-MANIFEST-ENTRY-MISMATCH",
    "since": "2026-09-23",
    "reason": "the root text is shorter on purpose",
    "ids": ["sets/de/x/manifest.yaml#/sets/0/description"],
}


def test_errors_are_parsed_with_their_rule_ids():
    [finding] = quality_state.parse_findings(RAISED_OUTPUT)
    assert (finding.path, finding.rule, finding.pointer) == (
        "sets/de/x/manifest.yaml",
        "E-MANIFEST-ENTRY-MISMATCH",
        "/sets/0/description",
    )


def test_the_renames_are_read_from_the_runner_output():
    assert quality_state.parse_renames(RAISED_OUTPUT) == {"W-MANIFEST-ENTRY-MISMATCH": "E-MANIFEST-ENTRY-MISMATCH"}


def test_without_a_rename_table_there_are_no_renames():
    # An older runner prints no table: nothing is renamed, nothing is guessed
    # from a shared suffix.
    assert quality_state.parse_renames(WARNINGS_OUTPUT) == {}


def test_an_accepted_warning_raised_to_an_error_is_not_reported_as_resolved(tmp_path):
    # The reproduction: the record names the old ID, the findings carry the new
    # one. Compared under the old ID, every recorded element looked resolved.
    report = quality_state.warnings_report(RAISED_OUTPUT, {"accepted_warnings": [RAISED_RECORD]}, tmp_path)
    assert "resolved" not in report
    assert (
        "| `W-MANIFEST-ENTRY-MISMATCH` | 1 | 1 since 2026-09-23 | raised to `E-MANIFEST-ENTRY-MISMATCH`:"
        " an error blocks the gate, the acceptance no longer applies (1 finding) |"
    ) in report


def test_a_raised_rule_without_findings_asks_for_the_record_to_go(tmp_path):
    output = RAISED_OUTPUT.split("\n✗")[0]
    report = quality_state.warnings_report(output, {"accepted_warnings": [RAISED_RECORD]}, tmp_path)
    assert "raised to `E-MANIFEST-ENTRY-MISMATCH`: no findings left, remove the record |" in report


def test_errors_of_rules_nobody_accepted_stay_out_of_the_warnings_table(tmp_path):
    output = RAISED_OUTPUT.replace("E-MANIFEST-ENTRY-MISMATCH]", "E-SCHEMA]")
    report = quality_state.warnings_report(output, {}, tmp_path)
    assert "E-SCHEMA" not in report


def test_an_error_cannot_be_accepted(tmp_path):
    with pytest.raises(ValueError, match="cannot be accepted"):
        quality_state.accept_warnings(
            {}, "E-MANIFEST-ENTRY-MISMATCH", RAISED_OUTPUT, tmp_path, reason="r", since="2026-10-12"
        )


def test_the_old_name_of_a_raised_rule_cannot_be_accepted_either(tmp_path):
    with pytest.raises(ValueError, match="E-MANIFEST-ENTRY-MISMATCH"):
        quality_state.accept_warnings(
            {}, "W-MANIFEST-ENTRY-MISMATCH", RAISED_OUTPUT, tmp_path, reason="r", since="2026-10-12"
        )


def test_the_old_name_of_a_lowered_rule_is_recorded_under_its_new_one(tmp_path):
    # Lowering renames too (E-X becomes W-X); the record carries the ID the
    # findings carry, or it would compare against nothing from the next run on.
    root = _lesson(tmp_path)
    output = "RENAMED E-CLOZE-NO-CARRIER -> W-CLOZE-NO-CARRIER\n" + WARNINGS_OUTPUT
    state = quality_state.accept_warnings({}, "E-CLOZE-NO-CARRIER", output, root, reason="r", since="2026-10-12")
    [entry] = state["accepted_warnings"]
    assert (entry["rule"], entry["ids"]) == ("W-CLOZE-NO-CARRIER", ["ex-abc"])


def test_a_recorded_error_fails_loudly(tmp_path):
    path = tmp_path / "state.json"
    path.write_text(json.dumps({"accepted_warnings": [{**RAISED_RECORD, "rule": "E-MANIFEST-ENTRY-MISMATCH"}]}))
    with pytest.raises(ValueError, match="cannot be accepted"):
        quality_state.load_state(path)
