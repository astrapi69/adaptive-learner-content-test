# Schema v1.4 — multi-file authoring format (PREVIEW / roadmap)

> ⚠️ **Not yet supported.** The files in this folder illustrate a *planned*
> authoring format. They are **not** loaded by the app and are **not** checked
> by `scripts/validate_content.py` today. For lessons you want to ship now, use
> the working **single-JSON** templates one level up (`templates/<domain>/lesson.json`)
> and the reference in [`docs/LESSON-FORMAT.md`](../../docs/LESSON-FORMAT.md).

## Why this exists

Authoring a lesson as one big JSON file works, but it mixes prose, cards and
exercises in a single document. The planned **schema v1.4** splits a lesson into
four human-friendly files and adds a few conveniences:

```
<lesson-folder>/
  lesson.yaml       # metadata + the order of theory/exercise blocks
  theory.md         # the prose, with Markdown anchors (#einleitung, …)
  cards.yaml        # cards + reusable distractor pools
  exercises.yaml    # the exercises, referencing cards by id
```

New v1.4 conveniences shown here:

- **`example_url`** on a theory step — link out to a live example or source.
- **`distractor_pools`** in `cards.yaml` — reusable wrong-answer banks.
- **`exercise_block`** grouping and a **`review`** step in `lesson.yaml`.

## How it maps to today's format

A v1.4 bundle is equivalent to one v1.3 JSON lesson:

| v1.4 (this folder) | v1.3 (works today) |
|---|---|
| `lesson.yaml` metadata | top-level keys of `lesson.json` |
| `theory.md` sections | `steps[].type: theory` (`body`) |
| `cards.yaml` | `cards[]` |
| `exercises.yaml` | `steps[].type: exercise` (`exercise`) |
| `structure[]` order | the order of entries in `steps[]` |
| `example_url` | (no v1.3 equivalent yet) |
| `distractor_pools` | inlined into each exercise's `distractors` |

Until a v1.4 loader/validator lands, convert a bundle to a single JSON lesson
(see the worked example in `examples/inception-effekt/lesson.json`, which is the
JSON form of the bundle the contributor originally wrote in this layout).

## What's in here

- `language/` — a **complete** worked bundle (all four files).
- `knowledge/lesson.yaml` and `programming/lesson.yaml` — show only the
  domain-specific header differences; their `theory.md` / `cards.yaml` /
  `exercises.yaml` follow the same shapes as `language/`.
