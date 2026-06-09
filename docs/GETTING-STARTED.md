# Getting started — your first lesson in 10 minutes

This walkthrough takes you from zero to a validated lesson. You'll copy a
template, edit it, register it, and run the validator.

For the full field reference, see [LESSON-FORMAT.md](LESSON-FORMAT.md).

## Before you start

You need:

- **Git** and a **GitHub account**.
- **Python 3** with PyYAML (`pip install pyyaml`) to run the validator.
- A text editor.

### Start your own content repository (recommended)

Fork the starter repository and work in your own copy:

> **Fork** <https://github.com/astrapi69/adaptive-learner-content-test> as the
> starting point for your own content repo, then clone your fork.

The starter is a minimal content repo you can grow. The **templates** and a
**worked example** referenced below live in the official repository
(<https://github.com/astrapi69/adaptive-learner-content>) under
[`templates/`](../templates/) and [`examples/`](../examples/) — copy what you
need from there into your repo.

> An example of a self-contained content repository:
> <https://github.com/astrapi69/adaptive-learner-content-test>

## 1. Copy a template (1 min)

Pick the template for your domain and copy it into a set's `lessons/` folder:

```bash
mkdir -p sets/en/my-set/lessons
cp templates/language/lesson.json sets/en/my-set/lessons/01-greetings.json
```

(There are also `templates/knowledge/` and `templates/programming/` templates.)

## 2. Edit the lesson (5 min)

Open `sets/en/my-set/lessons/01-greetings.json` and change:

- **`id`** → `01-greetings` (match the filename, kebab-case).
- **`title`**, **`description`**, **`target_language`** / **`source_language`**.
- **`cards`** → your words/terms. Keep ids unique and kebab-case.
- **`steps`** → at least one **theory** step and **five** exercises across at
  least two of the five types (matching, free_text, cloze, word_tiles,
  picture_choice).

Keep these or the validator will complain:

- `free_text` needs **≥ 2 accepts** and at least one **distractor**.
- `matching` needs **≥ 3 pairs**.
- `picture_choice` needs **distractors** and exactly one `is_correct: "true"`.

## 3. Register the lesson (2 min)

Create `sets/en/my-set/manifest.yaml`:

```yaml
schema_version: '1.3'
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
      My first set.
metadata:
  author: your-handle
  license: CC-BY-SA-4.0
  lessons:
    - 01-greetings.json
```

Then add the **same set block** to the root `manifest.yaml` under `sets:`.

## 4. Validate (1 min)

```bash
python scripts/validate_content.py
```

You want:

```
All N set(s) passed validation.
```

If it fails, the message names the lesson and the rule (e.g.
`free_text '…' needs distractors`). Fix and re-run.

## 5. Use your lessons

Two ways to publish:

- **In the app:** connect your repository under **Settings → Content**
  (*Einstellungen → Inhalte*). The app reads your root `manifest.yaml`.
- **Contribute back:** open a pull request to
  <https://github.com/astrapi69/adaptive-learner-content>. Keep
  `validate_content.py` green and update the README table + totals.

## Next steps

- Read a real, complete lesson:
  [`examples/inception-effekt/lesson.json`](../examples/inception-effekt/lesson.json).
- Skim [LESSON-FORMAT.md](LESSON-FORMAT.md) for every field and option.
- Curious about the planned 4-file YAML authoring format? See
  [`templates/v1.4-preview/`](../templates/v1.4-preview/).
