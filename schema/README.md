# Schema (mirror — do not edit here)

`lesson.schema.json` is a **mirror of the
[`learn-content-engine`](https://github.com/astrapi69/learn-content-engine)
npm package, pinned to the version in [`engine-version.txt`](engine-version.txt)**
(source of truth chain: **adaptive-learner Pydantic → engine → this mirror**).

> ⚠️ **Do not hand-edit `lesson.schema.json` in this repo.** It is a
> byte-for-byte copy of the schema the pinned engine release ships. The single
> source of truth is the Pydantic model in
> `adaptive_learner_content_loader.schema` in the
> [adaptive-learner](https://github.com/astrapi69/adaptive-learner) app; the
> engine vendors the generated schema via its documented
> [schema-sync procedure](https://github.com/astrapi69/learn-content-engine#schema-sync-from-adaptive-learner)
> and publishes it with every release — this repo mirrors **the engine
> release**, never the app directly.

## Files in this directory

| File | Owner / origin | Consumed here by |
|------|----------------|------------------|
| `lesson.schema.json` | Mirror of `learn-content-engine@<pin>` `schema/lesson.schema.json` (npm tarball) | `scripts/validate_content.py` (structural validation via `jsonschema`); the `Engine validate` workflow runs the engine's bundled copy of the same bytes |
| `engine-version.txt` | **This repo** — the pinned engine version | `scripts/check_schema_drift.py` (drift gate) and the `Engine validate` workflow (`npm install learn-content-engine@$(cat schema/engine-version.txt)`) |
| `quality-rules.json` | **This repo** — quality minimums for the content quality gate (originally derived from the app's generator, EXP-039; owned here since the engine decoupling) | `scripts/validate_content.py` (quality minimums) |
| `../tests/fixtures/lesson-shape-parity.json` | **This repo** — shape-parity fixture (adopted from the app's #1205 parity contract at the engine decoupling) | `tests/test_shape_parity.py` |

The mirror stays **vendored** (committed) so `validate_content.py` and the
shape-parity test validate fully **offline** — no network, no npm, no app
install. Only the drift gate itself (CI) touches the network, and it can be
pointed at a local tarball (`ENGINE_TARBALL`).

`lesson.schema.json` is a self-contained JSON Schema (Draft 2020-12) — its
`$id`, `$schema` and `x-schema-version` make it usable for IDE autocomplete
(reference it from a lesson `.json` via `"$schema"`) and for `jsonschema`/`ajv`
validation. `quality-rules.json` carries this repo's quality minimums
(`minExercisesPerLesson`, `minExerciseTypes`, `minFreeTextAccepts`,
`minMatchingPairs`, `minTheorySteps`).

## Drift gate (pinned, deterministic)

`scripts/check_schema_drift.py` (run in CI by
`.github/workflows/schema-drift.yml`) downloads the **npm tarball of the
pinned engine version** and compares its bundled `schema/lesson.schema.json`
byte-for-byte against this mirror. The npm tarball was chosen over a git-tag
checkout because published npm versions are **immutable** (a git tag can be
force-moved), the tarball is exactly the artifact consumers install, and the
check is a single unauthenticated HTTPS GET.

Because the comparison target is pinned, the gate only goes red if the mirror
was hand-edited or a pin bump forgot the refresh — an engine release does
**not** break this repo. Adopting a new engine version is a **deliberate PR**:

```bash
# 1. bump the pin
echo "0.4.0" > schema/engine-version.txt
# 2. refresh the mirror from that release
python scripts/check_schema_drift.py --update
# 3. commit both together
git add schema/ && git commit -m "schema: adopt learn-content-engine 0.4.0 mirror"
```

## Engine conformance gate

`.github/workflows/engine-validate.yml` additionally runs the **engine's own
`validateLesson()`** (structural ajv layer **and** the semantic cross-field
rules: cloze markers == blanks, `card_ids` referential integrity, multiselect
disjointness, picture-choice exactly-one-correct) over every lesson in the
repo, at the same pinned version. `scripts/validate_with_engine.mjs
--self-test` first proves the gate rejects each bad-lesson class, then the
full run must report zero errors.
