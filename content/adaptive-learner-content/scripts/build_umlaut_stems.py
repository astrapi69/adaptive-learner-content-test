#!/usr/bin/env python3
"""Build scripts/umlaut_stems.json, the data behind the prose gate's umlaut check.

The check has to find German written with the letter pairs ae/oe/ue/ss instead
of its umlauts, and it has to stay silent on everything else - it blocks PRs,
so a false alarm costs more than a missed word. A hand-written stem list
reached 41 percent of the German dictionary and raised false alarms on English
("blueberry", "shoehorn") and on the Korean and Spanish these repositories
teach. This generator derives the list from dictionaries instead and proves
both properties by construction:

* Targets: every German dictionary word with an umlaut or sharp s, written the
  substituted way ("muessen" for "müssen").
* Forbidden: every window of every CORRECT word - the German dictionary as it
  is spelled (so the legitimate "ss" in "Zuverlässigkeit" counts), the English
  dictionaries, and the foreign-language material of the content repositories
  (for a German-explained set only its target-language fields, because its
  explanations are German and may carry the very substitutions we look for).
* Words whose substituted form is at most six characters are matched as whole
  words ("fuer", "ueber"); longer ones through stems of six to ten characters,
  chosen greedily by coverage. A stem never occurs inside a correct word.
* GERMAN_PRIORITY: a few frequent words that are also rare English or a name
  ("gross", "weiss"). In a German lesson they are substitutions.

Needs /usr/share/dict/{ngerman,american-english,british-english} (Debian:
wngerman, wamerican, wbritish). Run from the template, with the content
repositories as corpus:

    python3 scripts/build_umlaut_stems.py ../adaptive-learner-content ../alc-*

It prints the dictionary coverage it reached. The output is committed; CI does
not regenerate it.
"""
from __future__ import annotations

import collections
import datetime
import heapq
import json
import re
import sys
from pathlib import Path

from check_prose import MACHINE_KEYS

SUBSTITUTION = {"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss"}
LETTER_PAIRS = ("ae", "oe", "ue", "ss")
STEM_MIN, STEM_MAX, WHOLE_WORD_MIN, WHOLE_WORD_MAX = 6, 10, 3, 6
# Short forms that read as something else as often as as German: the letter
# name "ae" and "boe" (Bö, rare, but also an abbreviation).
TOO_AMBIGUOUS = {"ae", "boe"}
MIN_GAIN = 3
DICTIONARIES = {
    "german": "/usr/share/dict/ngerman",
    "english": ["/usr/share/dict/american-english", "/usr/share/dict/british-english"],
}
GERMAN_PRIORITY = {
    "gross": "groß", "grosse": "große", "grossen": "großen", "grosser": "großer",
    "grosses": "großes", "weiss": "weiß", "weisst": "weißt",
}
TARGET_FIELDS = {"front", "accept", "tiles", "distractors", "left", "text", "sentence", "passage", "items"}
WORD = re.compile("[A-Za-zÄÖÜäöüß]+")


def substituted(word: str) -> tuple[str, list[int]]:
    """The word with its umlauts written as letter pairs, and for every output
    character the index of the source character it came from."""
    out, origin = [], []
    for index, character in enumerate(word):
        for replacement in SUBSTITUTION.get(character, character):
            out.append(replacement)
            origin.append(index)
    return "".join(out), origin


def _cuts_a_pair(origin: list[int], start: int, end: int) -> bool:
    """Whether the window [start, end) begins or ends inside the letter pair of
    one umlaut: "euerin" from "baeuerin" has no correction of its own."""
    starts_inside = start > 0 and origin[start - 1] == origin[start]
    ends_inside = end < len(origin) and origin[end - 1] == origin[end]
    return starts_inside or ends_inside


def load_words(path: str) -> list[str]:
    return [w.strip() for w in open(path, encoding="utf-8", errors="ignore") if w.strip().isalpha()]


def _strings(node, wanted, key=None, out=None) -> list[str]:
    """Every string in a lesson whose nearest key ``wanted`` accepts."""
    out = [] if out is None else out
    if isinstance(node, dict):
        for k, v in node.items():
            _strings(v, wanted, k, out)
    elif isinstance(node, list):
        for v in node:
            _strings(v, wanted, key, out)
    elif isinstance(node, str) and wanted(key):
        out.append(node)
    return out


def foreign_words(repositories: list[Path]) -> set[str]:
    """Words of the languages the repositories teach, other than German."""
    words = set()
    for repository in repositories:
        for lesson_path in repository.glob("sets/*/*/lessons/*.json"):
            try:
                lesson = json.loads(lesson_path.read_text(encoding="utf-8"))
            except ValueError:
                continue
            target = (lesson.get("target_language") or "de").split("-")[0]
            source = (lesson.get("source_language") or "de").split("-")[0]
            if target == "de":
                continue
            # A German-explained set contributes only its target-language
            # fields. Any other set contributes all of its words except the
            # machine keys, whose ASCII slugs may spell German the substituted
            # way ("ex-pick-ser-identitaet").
            if source == "de":
                wanted = TARGET_FIELDS.__contains__
            else:
                wanted = lambda key: key not in MACHINE_KEYS
            text = " ".join(_strings(lesson, wanted))
            words |= {w.lower() for w in WORD.findall(text)}
    return {w for w in words if not any(c in w for c in SUBSTITUTION)}


def build(german: list[str], english: list[str], foreign: set[str]) -> tuple[dict, dict, float]:
    correct = {w.lower() for w in german} | {w.lower() for w in english} | foreign
    targets = sorted({w.lower() for w in german if any(c in w.lower() for c in SUBSTITUTION)})

    words: dict[str, str | None] = {}
    for word in targets:
        form, _ = substituted(word)
        if WHOLE_WORD_MIN <= len(form) <= WHOLE_WORD_MAX and form not in correct and form not in TOO_AMBIGUOUS:
            words[form] = word if words.get(form, word) == word else None
    words = {form: word for form, word in words.items() if word}
    words.update(GERMAN_PRIORITY)

    forbidden = set()
    for word in correct:
        if any(pair in word for pair in LETTER_PAIRS):
            for size in range(STEM_MIN, STEM_MAX + 1):
                for start in range(len(word) - size + 1):
                    window = word[start:start + size]
                    if any(pair in window for pair in LETTER_PAIRS):
                        forbidden.add(window)

    # Coverage is per OCCURRENCE, not per word: every letter pair a word gets
    # needs a stem that contains it. A stem may span other pairs of the word
    # ("groess" for "größ"); the gate collects the decision per pair from all
    # stems found in the original word, so the order stems apply in does not
    # matter and "zurueckhaelt" is corrected completely.
    coverage: dict[str, set[tuple[int, int]]] = collections.defaultdict(set)
    corrections: dict[str, str] = {}
    ambiguous: set[str] = set()
    occurrences: list[tuple[int, int]] = []
    for index, word in enumerate(targets):
        form, origin = substituted(word)
        spans = []                          # (first, last) output index of each pair
        for k in range(len(form)):
            if word[origin[k]] in SUBSTITUTION and (k == 0 or origin[k - 1] != origin[k]):
                spans.append((k, k + 1))
        for number, (first, last) in enumerate(spans):
            occurrences.append((index, number))
            for size in range(STEM_MIN, STEM_MAX + 1):
                for start in range(max(0, last - size + 1), min(first, len(form) - size) + 1):
                    end = start + size
                    if _cuts_a_pair(origin, start, end):
                        continue
                    stem = form[start:end]
                    if stem in forbidden or stem in ambiguous:
                        continue
                    correction = word[origin[start]:origin[end - 1] + 1]
                    if corrections.setdefault(stem, correction) != correction:
                        ambiguous.add(stem)
                        continue
                    coverage[stem].add((index, number))
    for stem in ambiguous:
        coverage.pop(stem, None)

    whole = {i for i, w in enumerate(targets) if substituted(w)[0] in words}
    covered = {occ for occ in occurrences if occ[0] in whole}
    chosen = []
    heap = [(-len(ids - covered), len(stem), stem) for stem, ids in coverage.items()]
    heapq.heapify(heap)
    while heap:
        negative_gain, _, stem = heapq.heappop(heap)
        gain = len(coverage[stem] - covered)
        if gain == 0:
            continue
        if gain < -negative_gain:
            heapq.heappush(heap, (-gain, len(stem), stem))
            continue
        if gain < MIN_GAIN:
            break
        chosen.append(stem)
        covered |= coverage[stem]
    per_word = collections.defaultdict(list)
    for occ in occurrences:
        per_word[occ[0]].append(occ in covered)
    fully = sum(1 for flags in per_word.values() if all(flags))
    stems = {stem: corrections[stem] for stem in sorted(chosen)}
    return dict(sorted(words.items())), stems, fully / len(targets)


def main(argv: list[str]) -> int:
    german = load_words(DICTIONARIES["german"])
    english = [w for path in DICTIONARIES["english"] for w in load_words(path)]
    words, stems, recall = build(german, english, foreign_words([Path(p) for p in argv]))
    out = Path(__file__).with_name("umlaut_stems.json")
    out.write_text(json.dumps({
        "generated": datetime.date.today().isoformat(),
        "method": "scripts/build_umlaut_stems.py",
        "dictionary_recall": round(recall, 4),
        "words": words,
        "stems": stems,
    }, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"{len(words)} whole words + {len(stems)} stems correct {100 * recall:.1f} % of the German dictionary's umlaut words completely")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
