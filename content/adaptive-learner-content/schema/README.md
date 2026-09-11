# Schema (mirror, do not edit here)

**Mirror of the `learn-content-engine` `schema/`**, pinned to the version in
[`engine-version.txt`](engine-version.txt) (source of truth chain:
engine (canonical) → this mirror). The mirror and the pin move
together in one deliberate PR, so the pinned version lives in exactly one place
(`engine-version.txt`) and is not restated as a hardcoded number in this prose.

> ⚠️ **Do not hand-edit these files in this repo.** They are byte-for-byte
> copies of the schemas bundled by the pinned
> [`learn-content-engine`](https://github.com/astrapi69/learn-content-engine)
> npm release. The single source of truth is the `learn-content-engine`
> schema, which this repo mirrors byte-for-byte. Content authors and
> third-party validators never need the app.

## What is mirrored

| File | Origin (engine npm tarball) | Consumed here by |
|------|-----------------------------|------------------|
| `lesson.schema.json` | `package/schema/lesson.schema.json` | `scripts/validate_content.py` (structural validation via `jsonschema`), `tests/test_shape_parity.py` |
| `content-manifest.schema.json` | `package/schema/content-manifest.schema.json` | vendored for IDE autocomplete / third-party manifest validation; CI validates manifests with the engine itself (`engine-validate.yml`) |
| `quality-rules.json` | `package/schema/quality-rules.json` (engine ≥ 0.4.0, locally owned before that) | `scripts/validate_content.py` (quality minimums: `minExercisesPerLesson`, `minExerciseTypes`, `minFreeTextAccepts`, `minMatchingPairs`, `minTheorySteps`) |
| `engine-version.txt` | - (the pin itself) | `scripts/check_schema_drift.py`, `.github/workflows/engine-validate.yml` |

`lesson.schema.json` is a self-contained JSON Schema (Draft 2020-12). Its
`$id`, `$schema` and `x-schema-version` make it usable for IDE autocomplete
(reference it from a lesson `.json` via `"$schema"`) and for `jsonschema`/`ajv`
validation.

## Locally owned (NOT part of the engine mirror)

* `../tests/fixtures/lesson-shape-parity.json`: the shape-parity fixture
  snapshot (see `tests/test_shape_parity.py`). The cross-repo parity
  guarantee is closed by the app's own app-vs-engine parity test plus this
  repo's engine-pinned drift gate, so the fixture no longer needs to be
  synced from the app.

## Drift gate

`scripts/check_schema_drift.py` (run in CI by
`.github/workflows/schema-drift.yml`) downloads the **npm tarball of the
pinned engine release** at CI time and compares it byte-for-byte against
this mirror. The npm tarball (not a git tag) is the comparison source
because a published npm version is immutable (the registry refuses
re-publishing a version, git tags can be moved or deleted), it is exactly
the artefact validator consumers install via
`npm ci learn-content-engine@<pin>`, and it needs a single anonymous HTTPS
GET: no GitHub token, still Python-stdlib-only.

The mirror stays **vendored** so validation works offline: only the drift
CHECK itself needs network.

To move to a new engine version (deliberate PR):

```bash
echo "0.4.0" > schema/engine-version.txt          # bump the pin
python scripts/check_schema_drift.py --update      # refresh the mirror
git add schema/ && git commit -m "schema: bump engine pin to 0.4.0"
```

An `--update` without a pin bump simply re-asserts the current pin (useful
after an accidental hand-edit).

## Engine conformance gate

`.github/workflows/engine-validate.yml` additionally runs the engine's own
`validateLesson()` / `validateManifest()` (at the pinned version) over the
whole repo content: the semantic rules (cloze blanks == markers,
referential integrity, multiselect disjointness, picture exactly-one-correct)
that a JSON Schema cannot express. Gate: zero errors.
