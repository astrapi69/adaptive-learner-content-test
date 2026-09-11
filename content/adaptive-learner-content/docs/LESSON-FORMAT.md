# Lesson format: local summary

> **The canonical, test-validated format reference is the engine's**
> **[`docs/lesson-format.md`](https://github.com/astrapi69/learn-content-engine/blob/main/docs/lesson-format.md)**
> (every JSON example there is validated by the engine's test suite, so it
> cannot rot). This page is a convenience summary for people forking this
> starter kit; on any conflict the engine reference wins, and this page must
> not diverge from it. The bundled, pinned schema lives in
> [`../schema/`](../schema/) (version in
> [`../schema/engine-version.txt`](../schema/engine-version.txt)).

This is a field-by-field summary of the lesson format used by this repository.
Lessons that follow it pass `scripts/validate_content.py` and load in the
Adaptive Learner app.

The lesson format is **one JSON file per lesson**: this is what the app loads
and the validator checks. It is summarised below.

New to this? Start with [GETTING-STARTED.md](GETTING-STARTED.md) and copy a
[template](../templates/).

---

## Where files live

```
sets/<source_language>/<set-folder>/
  manifest.yaml          # the set: id, title, version, lesson_count, lesson list
  lessons/
    01-....json          # one JSON file per lesson
manifest.yaml            # root: lists every set
```

- **Language sets** live at `sets/<source>/<target>-<level>/`
  (e.g. `sets/en/es-a1/`: Spanish for English speakers, level A1).
- **Non-language sets** (e.g. psychology, programming) use a topic folder name
  (e.g. `sets/de/psych-intro/`), because material and explanation share one
  language.

## A lesson file (top level)

```jsonc
{
  "id": "01-greetings",            // kebab-case; match the filename (without .json)
  "title": "Greetings",            // shown in the app
  "description": "…",              // one or two sentences
  "target_language": "es",         // ISO 639-1 — the language being LEARNED
  "source_language": "en",         // ISO 639-1 — the explanation language
  "domain": "language",            // "language" (default) | "psychology" | "programming" | …
  "estimated_minutes": 10,         // integer
  "cards": [ … ],                  // see below
  "steps": [ … ]                   // theory + exercises, in display order
}
```

Rules:

- For **`domain: language`**, `target_language` **must differ** from
  `source_language`.
- For **non-language domains**, `source_language == target_language` is expected
  and allowed.
- Write accents and umlauts as **real UTF-8 characters** (`á é í ó ú ñ ü ä ö ß`),
  not ASCII substitutes (`ae`, `ss`, …).

## Cards

A card is one fact (a word, a term, a Q/A, a code snippet).

```jsonc
{
  "id": "gracias",                 // unique, kebab-case; exercises reference it
  "front": "gracias",              // language: TARGET word | knowledge: term/question
  "back": "thank you",             // language: SOURCE gloss | knowledge: definition/answer
  "notes": "Optional note (Markdown), in the source language.",
  "media_type": "text",            // "text" (default) | "code" | "formula" | "diagram"
  "difficulty": 1,                 // optional, 1–5
  "tags": ["greetings"],           // optional
  "hint": "Optional hint."         // optional
}
```

**Code cards** (schema v1.3) add:

```jsonc
{
  "id": "py-print",
  "front": "print()",
  "back": "Prints text to the console.",
  "media_type": "code",
  "code_snippet": "print('Hello')",
  "code_language": "python",
  "expected_output": "Hello"
}
```

Don't leave `front` or `back` empty.

## Steps: theory and exercises

`steps` is a flat, ordered list. Two kinds:

### Theory

```jsonc
{ "id": "intro", "type": "theory", "title": "…", "body": "# Markdown here\n…" }
```

`body` is Markdown (headings, lists, tables, blockquotes). At least **one**
theory step is required per lesson.

### Exercise (wrapper)

```jsonc
{
  "id": "ex-match",
  "type": "exercise",
  "title": "…",
  "exercise": { "id": "ex-match", "type": "matching", … }   // inner id repeats the wrapper id
}
```

The inner `exercise` object's `type` picks one of the six exercise types below.
Most carry `card_ids` (the cards they draw on) and a `direction`.

**`direction`** (productive vs receptive):
- `source_to_target`: learner produces the target language (harder).
- `target_to_source`: learner recognises/translates into the source (easier).

## The six exercise types

Since schema 1.7 the engine additionally defines an opt-in `ext:` namespace
for extension exercise types (see `docs/extensions.md` in the engine repo);
this content repo uses core types only.

### matching
```jsonc
{ "type": "matching", "prompt": "…", "card_ids": [ … ],
  "pairs": [ {"left": "hola", "right": "hello"}, … ],   // >= 3 pairs
  "direction": "target_to_source" }
```

**`from_cards`** (schema v1.5): set `"from_cards": true` and **omit** `pairs`
to avoid repeating definitions that already live in the cards. The engine
derives the pairs from the referenced `card_ids` (left = card `front`,
right = card `back`). Requires non-empty `card_ids` and forbids an explicit
`pairs` list; the >= 3 minimum then applies to the derived pairs, i.e. the
`card_ids`.

```jsonc
{ "type": "matching", "prompt": "…",
  "card_ids": ["hola", "gracias", "adios"],   // >= 3, pairs are derived from these cards
  "from_cards": true,
  "direction": "target_to_source" }
```

### free_text
```jsonc
{ "type": "free_text", "prompt": "Translate: thank you", "card_ids": [ … ],
  "accept": ["gracias", "Gracias"],        // >= 2 accepted answers
  "hint": "…",
  "distractors": ["hola", "por favor"],    // REQUIRED: >= 1 plausible wrong answer
  "direction": "source_to_target" }
```

### cloze
```jsonc
{ "type": "cloze", "prompt": "…", "card_ids": [ … ],
  "sentence": "Un café, ___ .",            // ___ marks the gap
  "blanks": [ {"accept": ["por favor"]} ],
  "cloze_mode": "type",
  "hint": "…" }
```

### word_tiles
```jsonc
{ "type": "word_tiles", "prompt": "Build: Hello, thank you", "card_ids": [ … ],
  "tiles": ["Hola", "gracias"],            // the correct sequence (the app shuffles)
  "hint": "…",
  "direction": "source_to_target" }
```

### picture_choice
```jsonc
{ "type": "picture_choice", "prompt": "Which word means 'goodbye'?", "card_ids": [ … ],
  "images": [
    {"src": "assets/img/adios.png", "label": "adiós", "is_correct": "true"},  // exactly one correct
    {"src": "assets/img/hola.png",  "label": "hola"},
    … ],
  "hint": "…",
  "distractors": ["hola", "gracias"],      // REQUIRED
  "direction": "target_to_source" }
```

`is_correct` is the string `"true"` on exactly one image. Image files are
optional in practice (the label text is what's shown); use `assets/img/<name>.png`
paths as elsewhere in the repo.

### multiple_choice
```jsonc
{ "type": "multiple_choice", "prompt": "Which number is prime?",
  "options": [
    {"text": "7", "correct": true},          // exactly one correct (single mode)
    {"text": "8"},
    {"text": "9"}
  ],
  "card_ids": [ … ],
  "hint": "…" }
```

First-class text multiple choice (schema v1.6). `options` is a list of
`{text, correct?}`; at least two options, option texts must be unique (the
text IS the option). `multiple` picks the mode:

- **`multiple: false`** (default): single choice, exactly **one** option
  carries `"correct": true` and the learner picks one.
- **`multiple: true`**: "select all that apply", at least **one** option is
  correct; graded by exact-set match, no partial credit (the same contract
  as `cloze` `multiselect`).

Correctness is a per-option flag, so there are no separate accept/distractor
lists. `multiple_choice` **coexists** with the legacy `cloze`
`select`/`multiselect` vehicle; existing cloze-based multiple choice stays
valid.

## Validation rules (the quality gate)

`scripts/validate_content.py` (plus the engine gate in CI for the rules
marked *engine*) enforces, per lesson:

| Rule | Minimum |
|---|---|
| exercises | ≥ 5 |
| distinct exercise types | ≥ 2 |
| theory steps | ≥ 1 |
| `free_text` accepts | ≥ 2 **and** `distractors` present |
| `matching` pairs | ≥ 3 (explicit or derived via `from_cards`) |
| `picture_choice` | `distractors` present |
| `multiple_choice` options | ≥ 2, no duplicate option texts (*engine*) |
| `multiple_choice` correct count | exactly 1 (single) / ≥ 1 (`multiple: true`) (*engine*) |
| cards | no empty `front`/`back` |

…and, per set: a valid ISO 639-1 language pair, the correct `path` for the
domain, and every lesson listed in the set manifest's `metadata.lessons`.

## Registering a set

`sets/<…>/manifest.yaml`:

```yaml
schema_version: '1.7'
name: My Set
sets:
  - id: my-set-from-en
    title: My Set
    target_language: es
    source_language: en
    level: A1
    path: sets/en/my-set
    version: '1.0.0'
    lesson_count: 1
    domain: language
    description: >-
      …
metadata:
  author: your-handle
  license: CC-BY-SA-4.0
  lessons:
    - 01-greetings.json
```

Then add the same set block to the **root** `manifest.yaml` under `sets:`, and
add a row to the README table (keeping the totals line in sync).

Run `python scripts/validate_content.py` until it prints
`All N set(s) passed validation.`
