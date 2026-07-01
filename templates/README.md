# Lesson templates

Copy-and-edit starting points for new lessons, one per content **domain**.

A lesson is a **single JSON file** — that is the lesson format. Pick the
template for your domain and copy it.

| Template | Domain | Use it for |
|---|---|---|
| [`language/lesson.json`](language/lesson.json) | `language` | Learning a language (target ≠ source), CEFR level |
| [`knowledge/lesson.json`](knowledge/lesson.json) | non-language (e.g. `psychology`) | Subject knowledge; material and explanation share one language |
| [`programming/lesson.json`](programming/lesson.json) | `programming` | Code lessons with `code_snippet` / `expected_output` cards |

## How to use a template

1. **Copy** the JSON template for your domain into your set's `lessons/` folder.
2. **Rename** the file to a kebab-case slug and set the lesson `id` to match
   (e.g. `01-greetings.json` → `"id": "01-greetings"`).
3. **Replace** the placeholder cards, theory and exercises with your content.
4. **Register** the file in your set's `manifest.yaml` (`metadata.lessons`) and
   make sure the set is listed in the root `manifest.yaml`.
5. **Validate**: `python scripts/validate_content.py` — it must print
   `All N set(s) passed validation.`

> JSON has no comments, so the field-by-field explanations live in
> [`../docs/LESSON-FORMAT.md`](../docs/LESSON-FORMAT.md).

## What each template already satisfies

Every JSON template is a **valid lesson** (checked with the validator's
lesson rules): ≥ 1 theory step, ≥ 5 exercises across ≥ 2 types, free-text with
≥ 2 accepts **and** distractors, matching with ≥ 3 pairs, and a picture-choice
with distractors. Keep those minimums when you edit.

## Domain differences at a glance

- **language**: `domain: language`, `target_language` **and** `source_language`
  differ, `level` is a CEFR band (A1–C2). Matching/free-text use a
  translation context (target ↔ source).
- **knowledge**: `domain: psychology` (or another non-language domain),
  `source_language == target_language`, no separate target. Matching/free-text
  use a term ↔ definition context.
- **programming**: `domain: programming`, `source_language == target_language`,
  code cards add `code_snippet`, `code_language`, `expected_output` and
  `media_type: "code"`.
