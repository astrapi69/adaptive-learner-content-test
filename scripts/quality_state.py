#!/usr/bin/env python3
"""Repository-owned quality decisions, read by the template-owned workflows.

The CI workflows come from the content template and are identical in every
repository, so that a divergence check can hold them. Two decisions are not
identical across repositories, and they live in the repository's own
``.github/quality-state.json`` instead of in a workflow edit:

* ``prose_gate.blocking``: whether a prose finding fails the PR. A repository
  with a backlog from before the gate records ``false`` with a date and a
  reason; its cleanup PR sets it back (or deletes the file). Absent means
  blocking. A broken gate (exit code other than 0 or 1) is never masked.
* ``accepted_warnings``: author warnings a repository has decided to keep, with
  the date, the reason, an optional link to the decision, and the identities
  of the elements it covers. A decision that cannot be read off the state is
  a backlog three months later: the warning summary shows the decision next to
  the number, and compares the recorded elements with the current ones, so
  "still the same 105" is a set comparison, not a count.

Commands (all write Markdown for the job summary to stdout):

    python3 scripts/quality_state.py prose --status N --report FILE
        exit code: what the prose step should exit with
    python3 scripts/quality_state.py warnings FILE
    python3 scripts/quality_state.py accept RULE FILE --reason TEXT [--decision URL] [--since DATE]
        records the current findings of RULE as accepted
"""
from __future__ import annotations

import argparse
import datetime
import json
import re
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

STATE_PATH = Path(".github/quality-state.json")
TABLE_ROWS = 50

FINDING_LINE = re.compile(r"^(?P<path>[^ ].*?):(?P<line>\d+): ")
WARN_FILE = re.compile(r"^WARN (?P<path>\S+)")
WARN_ENTRY = re.compile(r"^\s+\[(?P<rule>W-[A-Z0-9-]+)\] (?P<pointer>\S+)")
STEP_POINTER = re.compile(r"^/steps/(?P<index>\d+)/exercise")


# --- the state file -----------------------------------------------------------


def load_state(path: Path = STATE_PATH) -> dict:
    """The parsed state, ``{}`` when the file is absent. A malformed file raises:
    a quality decision that cannot be read must not silently become a default."""
    if not path.exists():
        return {}
    state = json.loads(path.read_text(encoding="utf-8"))
    gate = state.get("prose_gate")
    if gate is not None:
        if not isinstance(gate.get("blocking"), bool):
            raise ValueError(f"{path}: prose_gate.blocking must be true or false")
        if gate["blocking"] is False and not (gate.get("since") and gate.get("reason")):
            raise ValueError(f"{path}: a non-blocking prose gate needs 'since' and 'reason'")
    for entry in state.get("accepted_warnings", []):
        missing = [key for key in ("rule", "since", "reason", "ids") if key not in entry]
        if missing:
            raise ValueError(f"{path}: accepted warning {entry.get('rule', '?')} needs {', '.join(missing)}")
    return state


# --- the prose gate -----------------------------------------------------------


def prose_exit_code(state: dict, gate_status: int) -> int:
    """What the prose step exits with. Findings (exit 1) block unless the state
    records a backlog; anything else the gate returns passes through."""
    if gate_status != 1:
        return gate_status
    return 1 if state.get("prose_gate", {}).get("blocking", True) else 0


def prose_report(output: str, state: dict, gate_status: int) -> str:
    """Markdown for the job summary: findings per file, the backlog decision
    when there is one, and the gate's totals line last."""
    per_file = Counter(
        match.group("path") for line in output.splitlines() if (match := FINDING_LINE.match(line))
    )
    lines = ["### Prose gate", ""]
    gate = state.get("prose_gate", {})
    if gate_status == 1 and gate.get("blocking") is False:
        lines += [f"**Non-blocking since {gate['since']}:** {gate['reason']}", ""]
    if per_file:
        lines += ["| file | findings |", "|---|---|"]
        ranked = per_file.most_common()
        lines += [f"| `{path}` | {count} |" for path, count in ranked[:TABLE_ROWS]]
        if len(ranked) > TABLE_ROWS:
            lines.append(f"| ... and {len(ranked) - TABLE_ROWS} more file(s) | |")
        lines.append("")
    totals = [line for line in output.splitlines() if line.startswith(("PROSE GATE:", "prose gate:"))]
    if totals:
        lines.append(totals[-1])
    return "\n".join(lines) + "\n"


# --- warnings -----------------------------------------------------------------


@dataclass(frozen=True)
class Finding:
    path: str
    rule: str
    pointer: str


@dataclass
class AcceptedStatus:
    new: list[str] = field(default_factory=list)
    resolved: list[str] = field(default_factory=list)

    @property
    def unchanged(self) -> bool:
        return not self.new and not self.resolved


def parse_warnings(output: str) -> list[Finding]:
    """Every author warning in the engine runner's --warnings output."""
    findings, current = [], None
    for line in output.splitlines():
        if match := WARN_FILE.match(line):
            current = match.group("path")
        elif current and (match := WARN_ENTRY.match(line)):
            findings.append(Finding(current, match.group("rule"), match.group("pointer")))
    return findings


def element_key(finding: Finding, root: Path) -> str:
    """The identity of the element a warning is about: the exercise's
    stable_id (or its id before minting) when the pointer lands on one, else
    file and pointer. A stable_id survives reordering; a pointer does not."""
    fallback = f"{finding.path}#{finding.pointer}"
    match = STEP_POINTER.match(finding.pointer)
    if not match or not finding.path.endswith(".json"):
        return fallback
    try:
        lesson = json.loads((root / finding.path).read_text(encoding="utf-8"))
        exercise = lesson["steps"][int(match.group("index"))]["exercise"]
    except (OSError, ValueError, KeyError, IndexError, TypeError):
        return fallback
    return exercise.get("stable_id") or exercise.get("id") or fallback


def compare_accepted(accepted: dict, current: set[str]) -> AcceptedStatus:
    """What changed since the decision was recorded, as sets of elements."""
    recorded = set(accepted["ids"])
    return AcceptedStatus(new=sorted(current - recorded), resolved=sorted(recorded - current))


def _status_text(status: AcceptedStatus) -> str:
    if status.unchanged:
        return "as accepted"
    parts = []
    if status.new:
        parts.append(f"{len(status.new)} new: {', '.join(status.new[:5])}{' ...' if len(status.new) > 5 else ''}")
    if status.resolved:
        parts.append(f"{len(status.resolved)} resolved, update the record")
    return "; ".join(parts)


def warnings_report(output: str, state: dict, root: Path = Path(".")) -> str:
    """Markdown for the job summary: warnings per rule, each accepted rule with
    its decision next to the number and a set comparison against the record."""
    findings = parse_warnings(output)
    per_rule = Counter(finding.rule for finding in findings)
    accepted = {entry["rule"]: entry for entry in state.get("accepted_warnings", [])}
    lines = ["### Author lints (warnings, non-blocking)", "", "| rule | count | accepted | status |", "|---|---|---|---|"]
    for rule in sorted(set(per_rule) | set(accepted), key=lambda r: (-per_rule[r], r)):
        entry = accepted.get(rule)
        if entry is None:
            lines.append(f"| `{rule}` | {per_rule[rule]} | - | |")
            continue
        current = {element_key(f, root) for f in findings if f.rule == rule}
        status = compare_accepted(entry, current)
        lines.append(f"| `{rule}` | {per_rule[rule]} | {len(entry['ids'])} since {entry['since']} | {_status_text(status)} |")
    if accepted:
        lines += ["", "**Accepted warnings**", ""]
        for rule, entry in sorted(accepted.items()):
            link = f" ([decision]({entry['decision']}))" if entry.get("decision") else ""
            lines.append(f"- `{rule}` since {entry['since']}: {entry['reason']}{link}")
    return "\n".join(lines) + "\n"


def accept_warnings(state: dict, rule: str, output: str, root: Path, reason: str, since: str, decision: str | None = None) -> dict:
    """The state with the current findings of ``rule`` recorded as accepted."""
    ids = sorted({element_key(f, root) for f in parse_warnings(output) if f.rule == rule})
    entry = {"rule": rule, "count": len(ids), "since": since, "reason": reason}
    if decision:
        entry["decision"] = decision
    entry["ids"] = ids
    kept = [e for e in state.get("accepted_warnings", []) if e["rule"] != rule]
    return {**state, "accepted_warnings": kept + [entry]}


# --- command line -------------------------------------------------------------


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    commands = parser.add_subparsers(dest="command", required=True)
    prose = commands.add_parser("prose")
    prose.add_argument("--status", type=int, required=True)
    prose.add_argument("--report", type=Path, required=True)
    warnings = commands.add_parser("warnings")
    warnings.add_argument("output", type=Path)
    accept = commands.add_parser("accept")
    accept.add_argument("rule")
    accept.add_argument("output", type=Path)
    accept.add_argument("--reason", required=True)
    accept.add_argument("--decision")
    accept.add_argument("--since", default=datetime.date.today().isoformat())
    args = parser.parse_args(argv)

    state = load_state()
    if args.command == "prose":
        sys.stdout.write(prose_report(args.report.read_text(encoding="utf-8"), state, args.status))
        return prose_exit_code(state, args.status)
    if args.command == "warnings":
        sys.stdout.write(warnings_report(args.output.read_text(encoding="utf-8"), state))
        return 0
    updated = accept_warnings(state, args.rule, args.output.read_text(encoding="utf-8"), Path("."),
                              reason=args.reason, since=args.since, decision=args.decision)
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(updated, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    entry = next(e for e in updated["accepted_warnings"] if e["rule"] == args.rule)
    print(f"recorded {entry['count']} accepted {args.rule} finding(s) in {STATE_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
