"""Unit tests for the prose gate (scripts/check_prose.py).

The gate's own ``--self-test`` proves it fires on every banned character;
these tests pin the behaviour that a reader would otherwise have to trust:
which characters are banned, which legitimate typography stays untouched,
and that the mirrored schema/ tree is out of scope by construction.
"""
from __future__ import annotations

import json
import importlib.util
import os
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "check_prose", REPO_ROOT / "scripts" / "check_prose.py"
)
check_prose = importlib.util.module_from_spec(SPEC)
sys.modules["check_prose"] = check_prose
SPEC.loader.exec_module(check_prose)
BUILD_SPEC = importlib.util.spec_from_file_location(
    "build_umlaut_stems", REPO_ROOT / "scripts" / "build_umlaut_stems.py"
)
build_umlaut_stems = importlib.util.module_from_spec(BUILD_SPEC)
BUILD_SPEC.loader.exec_module(build_umlaut_stems)


EM_DASH = chr(0x2014)
ZERO_WIDTH_SPACE = chr(0x200B)
ELLIPSIS = chr(0x2026)
EN_DASH = chr(0x2013)
NO_BREAK_SPACE = chr(0x00A0)


def test_flags_an_em_dash():
    findings = check_prose.findings_in(f"a comment {EM_DASH} with an em dash")
    assert [f[1] for f in findings] == [EM_DASH]
    assert findings[0][0] == 1


def test_flags_an_invisible_character():
    assert check_prose.findings_in(f"zero{ZERO_WIDTH_SPACE}width")


def test_leaves_legitimate_typography_alone():
    # Ellipsis, en dash and no-break space are deliberately not banned: a
    # gate that fights legitimate typography gets switched off.
    assert check_prose.findings_in(f"one{ELLIPSIS}twelve, 5{EN_DASH}10, 12{NO_BREAK_SPACE}h") == []


def test_reports_the_line_number():
    findings = check_prose.findings_in(f"clean\nstill clean\nnow {EM_DASH} here")
    assert findings[0][0] == 3


def test_excludes_the_mirrored_schema_tree():
    # schema/ is a byte-identical mirror of the pinned engine release; its
    # typography belongs to the engine, and editing it here would turn the
    # drift gate red.
    assert any(path.startswith("schema/") for path in _all_git_files())
    assert not any(path.startswith("schema/") for path in check_prose.tracked_files())


def test_self_test_passes():
    assert check_prose.self_test() == 0


def _all_git_files() -> list[str]:
    import subprocess

    return subprocess.run(
        ["git", "ls-files"], capture_output=True, text=True, check=True, cwd=REPO_ROOT
    ).stdout.split()

# --- the umlaut half (ASCII-substituted German) ------------------------------
# This file is UMLAUT_EXEMPT, so it may spell the misspellings out.


def test_flags_a_substituted_german_word():
    findings = check_prose.substituted_words("Die Abhaengigkeitsliste laeuft")
    words = [w for w, _ in findings]
    assert words == ["Abhaengigkeitsliste", "laeuft"]


def test_suggests_the_correct_spelling_and_keeps_the_capital():
    [(word, suggestion)] = check_prose.substituted_words("Abhaengigkeit")
    assert word == "Abhaengigkeit"
    assert suggestion == "Abh\u00e4ngigkeit"


def test_leaves_english_and_code_words_alone():
    # The reason this is a stem list and not a pattern on "ue".
    assert check_prose.substituted_words("value true queue Sequence useState defaultValue") == []


def test_leaves_correct_german_alone():
    correct = "Die Abh\u00e4ngigkeit l\u00e4uft \u00fcber Zuverl\u00e4ssigkeit und Quellen, neue Klassen, dass"
    assert check_prose.substituted_words(correct) == []


def test_skips_a_foreign_lookalike():
    # Spanish "fueron"/"fuera" would otherwise be claimed by the stem "fuer".
    assert check_prose.substituted_words("fueron fuera fuerte") == []
    assert check_prose.substituted_words("dafuer") != []


def test_lesson_code_fields_are_out_of_scope():
    lesson = json.dumps(
        {
            "title": "Eine Uebung",
            "steps": [
                {
                    "exercise": {
                        "sentence": "const laeuft = true;",
                        "ext_payload": {"passage": "const zurueck = 1;", "prompt": "Was laeuft hier?"},
                    }
                }
            ],
        },
        ensure_ascii=False,
    )
    scanned = " ".join(segment for _, segment in check_prose.prose_segments("lesson.json", lesson))
    assert "Uebung" in scanned
    assert "Was laeuft hier?" in scanned
    assert "const laeuft" not in scanned
    assert "zurueck" not in scanned


def test_fenced_code_in_a_theory_body_is_out_of_scope():
    body = "Prosa ueber Effekte\n\n```jsx\nconst laeuft = true;\n```\n\nmehr Prosa"
    lesson = json.dumps({"steps": [{"type": "theory", "body": body}]}, ensure_ascii=False)
    scanned = " ".join(segment for _, segment in check_prose.prose_segments("lesson.json", lesson))
    assert "ueber" in scanned
    assert "const laeuft" not in scanned


def test_the_gate_and_its_test_are_exempt_from_the_umlaut_check():
    # A list of misspellings has to contain them. The exemption is narrow and
    # pinned here so it cannot quietly widen.
    assert check_prose.UMLAUT_EXEMPT == (
        "scripts/check_prose.py",
        "tests/test_check_prose.py",
        "scripts/build_umlaut_stems.py",
        "scripts/umlaut_stems.json",
    )
    for path in check_prose.UMLAUT_EXEMPT:
        assert check_prose.substituted_words((REPO_ROOT / path).read_text(encoding="utf-8"))


def test_every_entry_is_itself_a_substitution():
    umlauts = set("\u00e4\u00f6\u00fc\u00df")
    for table in (check_prose.WHOLE_WORDS, check_prose.STEMS):
        for form, correction in table.items():
            assert form == form.lower() and form.isascii(), form
            assert any(pair in form for pair in ("ae", "oe", "ue", "ss")), form
            assert any(c in umlauts for c in correction), (form, correction)


def test_camel_case_is_treated_as_code():
    # A prompt may name the function it asks about; renaming it in prose would
    # point the sentence at something that does not exist.
    assert check_prose.substituted_words("fuegeOptimistischHinzu(text) aufrufen") == []
    assert check_prose.substituted_words("defaultValue useDeferredValue neuerText") == []
    # ... while an ordinary German noun still gets caught.
    assert check_prose.substituted_words("Abhaengigkeitsliste")


def test_an_all_caps_word_is_not_mistaken_for_an_identifier():
    assert check_prose.substituted_words("CSS")[:1] == []
    assert [w for w, _ in check_prose.substituted_words("PRUEFUNG")] == ["PRUEFUNG"]


def test_applies_every_matching_stem_in_one_word():
    # "zurueckfuehren" needs two stems; stopping at the first leaves half a
    # correction behind.
    [(word, suggestion)] = check_prose.substituted_words("zurueckfuehren")
    assert word == "zurueckfuehren"
    assert suggestion == "zur\u00fcckf\u00fchren"
    # "oe" and "ss" of "Groessen" sit next to each other, so no stem can hold
    # one without the other.
    [(_, gr)] = check_prose.substituted_words("Groessenaendern")
    assert gr == "Gr\u00f6\u00dfen\u00e4ndern"


def test_keeps_a_letter_pair_the_correct_word_keeps():
    [(_, suggestion)] = check_prose.substituted_words("Zuverlaessigkeit")
    assert suggestion == "Zuverl\u00e4ssigkeit"
    [(_, farmer)] = check_prose.substituted_words("Baeuerin")
    assert farmer == "B\u00e4uerin"


def test_id_fields_are_out_of_scope():
    # An id is a machine key: the manifest and the app look it up verbatim, so
    # "correcting" it renames the thing. It is also how a slug quietly stops
    # being ASCII.
    lesson = json.dumps(
        {
            "id": "ex-drei-rueckgaben",
            "steps": [
                {
                    "id": "ex-zustaendigkeiten",
                    "theory_ref": "buendelung",
                    "title": "Die Zustaendigkeiten",
                    "exercise": {"id": "ex-zustaendigkeiten", "card_ids": ["karte-rueckfall"]},
                }
            ],
        },
        ensure_ascii=False,
    )
    scanned = " ".join(segment for _, segment in check_prose.prose_segments("lesson.json", lesson))
    assert "Die Zustaendigkeiten" in scanned
    for machine_key in ("ex-drei-rueckgaben", "ex-zustaendigkeiten", "buendelung", "karte-rueckfall"):
        assert machine_key not in scanned


def test_whole_word_substitutions_do_not_claim_innocent_compounds():
    # "weiss" sits inside "Hinweisschilder", so it cannot be a stem.
    assert [s for _, s in check_prose.substituted_words("weiss")] == ["wei\u00df"]
    assert check_prose.substituted_words("Hinweisschilder") == []


def test_card_code_fields_are_out_of_scope():
    # A card can carry a snippet and its expected output; both are code.
    lesson = json.dumps(
        {
            "cards": [
                {
                    "id": "karte",
                    "front": "Die Uebung",
                    "code_snippet": "const laeuft = true;",
                    "code_language": "javascript",
                    "expected_output": "laeuft",
                    "tags": ["uebung"],
                }
            ]
        },
        ensure_ascii=False,
    )
    scanned = " ".join(segment for _, segment in check_prose.prose_segments("lesson.json", lesson))
    assert "Die Uebung" in scanned
    for code in ("const laeuft", "expected", "javascript"):
        assert code not in scanned


def test_an_inline_example_is_code_when_it_declares_a_language():
    prose_example = json.dumps(
        {"examples": [{"content": "Der Hund laeuft weg.", "title": "Beispiel"}]}, ensure_ascii=False
    )
    code_example = json.dumps(
        {"examples": [{"content": "const laeuft = true;", "language": "javascript"}]}, ensure_ascii=False
    )
    prose_scanned = " ".join(s for _, s in check_prose.prose_segments("l.json", prose_example))
    code_scanned = " ".join(s for _, s in check_prose.prose_segments("l.json", code_example))
    assert "laeuft weg" in prose_scanned
    assert "const laeuft" not in code_scanned


# --- machine strings stay ASCII on purpose ------------------------------------


def test_lowercase_technical_tokens_are_not_prose():
    # Slugs, paths, file names, snake_case, URLs, repository names: the repos
    # keep them ASCII deliberately, so the gate must not demand umlauts there.
    for machine_string in (
        "ex-wo-laeuft-was",
        "sets/de/fuehrerschein-uebung",
        "check_fuer_x.py",
        "https://example.org/ueber",
        "alc-die-waehrung-des-geistes",
    ):
        assert check_prose.substituted_words(machine_string) == [], machine_string


def test_a_sentence_final_period_does_not_hide_a_word():
    assert [w for w, _ in check_prose.substituted_words("Das ist fuer.")] == ["fuer"]


def test_a_capitalised_hyphen_compound_is_prose():
    assert [w for w, _ in check_prose.substituted_words("Der Rueckgabe-Wert")] == ["Rueckgabe"]


def test_inline_code_spans_are_not_prose():
    assert check_prose.substituted_words("nutze `onAendern` hier") == []
    assert check_prose.substituted_words("siehe ``zurueck`` bitte") == []
    assert [w for w, _ in check_prose.substituted_words("`x` ist fuer dich")] == ["fuer"]


def test_the_generated_search_index_is_out_of_scope():
    assert "search-index.json" in check_prose.EXCLUDED_FILES


def test_listing_is_nul_separated_so_non_ascii_paths_are_read():
    # Without -z git quotes a non-ASCII path and the quoted string names no
    # file, so the gate would skip it and still report clean.
    import inspect

    source = inspect.getsource(check_prose.tracked_files)
    assert '"-z"' in source


def test_capitals_write_sharp_s_as_ss():
    # "AUSSCHLIESSLICH" is correct German: in capitals the sharp s is SS.
    assert check_prose.substituted_words("AUSSCHLIESSLICH") == []
    assert check_prose.substituted_words("GROSSE") == []
    # ...but a missing umlaut is still missing when shouted
    assert [s for _, s in check_prose.substituted_words("PRUEFUNG")] == ["PR\u00dcFUNG"]
    assert [s for _, s in check_prose.substituted_words("AUSSCHLIESSLICH GEPRUEFT")] == ["GEPR\u00dcFT"]


def test_markdown_findings_carry_their_line_number():
    text = "# Titel\n\nZeile ohne Befund.\n```\nfuer im Code\n```\nHier steht fuer drin.\n"
    segments = check_prose.prose_segments("doc.md", text)
    hits = [(n, w) for n, seg in segments for w, _ in check_prose.substituted_words(seg)]
    assert hits == [(7, "fuer")]


# The umlaut data is generated from dictionaries (scripts/build_umlaut_stems.py)
# and committed. These tests hold the COMMITTED data and the real gate against
# the dictionaries, so a hand edit or a later generator change cannot quietly
# trade precision for recall. They need wngerman, wamerican and wbritish; the
# umlaut-data workflow installs them and sets REQUIRE_DICTIONARIES, which turns
# a missing dictionary into a failure instead of a skip.
DICTIONARY_FILES = {
    "german": ["/usr/share/dict/ngerman"],
    "english": ["/usr/share/dict/american-english", "/usr/share/dict/british-english"],
}
UMLAUT_TO_PAIR = {"\u00e4": "ae", "\u00f6": "oe", "\u00fc": "ue", "\u00df": "ss"}


def _dictionary(language: str) -> list[str]:
    paths = [Path(p) for p in DICTIONARY_FILES[language]]
    missing = [str(p) for p in paths if not p.exists()]
    if missing:
        if os.environ.get("REQUIRE_DICTIONARIES"):
            pytest.fail(f"dictionaries required but missing: {missing}")
        pytest.skip(f"dictionaries not installed: {missing}")
    return [
        line.strip()
        for p in paths
        for line in p.read_text(encoding="utf-8", errors="ignore").splitlines()
        if line.strip().isalpha()
    ]


def _without_umlauts(word: str) -> str:
    return "".join(UMLAUT_TO_PAIR.get(c, c) for c in word)


def test_dictionary_umlaut_words_are_found_and_corrected():
    umlaut_words = [w.lower() for w in _dictionary("german") if any(c in UMLAUT_TO_PAIR for c in w.lower())]
    flagged = corrected = 0
    for word in umlaut_words:
        findings = check_prose.substituted_words(_without_umlauts(word))
        flagged += bool(findings)
        corrected += bool(findings) and findings[0][1] == word
    # Measured 2026-09-23: 98.2 % flagged, 98.1 % corrected completely.
    assert flagged / len(umlaut_words) >= 0.97
    assert corrected / len(umlaut_words) >= 0.97


def test_no_correct_german_word_is_flagged():
    flagged = [w for w in _dictionary("german") if check_prose.substituted_words(w)]
    assert flagged == []


def test_no_english_word_is_flagged_except_the_german_priority_words():
    # "gross" and "weiss" are English (or a name) too, but in a German lesson
    # they are substitutions; the generator lists them on purpose.
    flagged = [
        w for w in _dictionary("english")
        if w.lower() not in build_umlaut_stems.GERMAN_PRIORITY and check_prose.substituted_words(w)
    ]
    assert flagged == []
