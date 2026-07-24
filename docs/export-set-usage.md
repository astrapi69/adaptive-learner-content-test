# Export a set for AI review: usage and best practices

> Deutsche Version: [export-set-usage.de.md](export-set-usage.de.md)

How to use [`scripts/export_set.py`](../scripts/export_set.py) and how
to run an AI-assisted review on the exported file.

## Purpose

`scripts/export_set.py` snapshots ONE content set into a single YAML
(default) or JSON file so that an AI assistant (or a human) can review
the whole set in one pass: syntax, correctness, consistency across
lessons.

The export is a **read-only snapshot, NOT a re-import format**. The
script never writes into `sets/`, and nothing reads the export back.
Changes always flow through the individual schema-validated lesson
JSON files under `sets/`.

## Usage

```bash
python3 scripts/export_set.py <set-slug> [--lang <lang>] [--format yaml|json] [--out PATH]
```

| Argument | Meaning | Default |
| --- | --- | --- |
| `<set-slug>` | Set id from the root `manifest.yaml` (e.g. `graded-quiz-demo-from-de`) or the folder name of the set path (e.g. `graded-quiz-demo` for `sets/de/graded-quiz-demo`) | required |
| `--lang` | Source-language directory (`sets/<lang>/`) that disambiguates a folder-name slug existing under several source languages | `de` |
| `--format` | Output format: `yaml` or `json` | `yaml` |
| `--out` | Output file path | `exports/<set-slug>-<lang>-<timestamp>.<format>` |

Examples:

```bash
# Standard case: YAML export into exports/
python3 scripts/export_set.py graded-quiz-demo
# -> exports/graded-quiz-demo-de-<timestamp>.yaml

# Special case: JSON to a custom path (only when a tool explicitly needs JSON)
python3 scripts/export_set.py graded-quiz-demo --format json --out /tmp/review.json
```

Without `--out`, the file is written to `exports/` following the
pattern `<set-slug>-<lang>-<timestamp>.<format>`. The `exports/`
directory is created on demand and is **gitignored**: export files are
throwaway review artifacts and are never committed.

An unknown or ambiguous slug aborts with exit code 2 and a list of the
available sets. Umlauts and all other non-ASCII characters stay real
UTF-8.

## Workflow: running an AI review

1. **Create the export:**

   ```bash
   python3 scripts/export_set.py graded-quiz-demo
   ```

2. **Open the export file** and find the section "Quellkapitel"
   (source chapter) inside the `review_instructions` block at the top
   of the file.

3. **Paste the source chapter manually** if the exercises were written
   against a textbook chapter or other reference material that does
   not live in this repo. This matters: without the chapter, the AI
   checks factual claims only against its general knowledge, not
   against the actual teaching source (see the priority rule inside
   the `review_instructions` block).

4. **Hand the complete file to an AI** of your choice. The export is
   self-contained: the embedded `review_instructions` field tells the
   AI its role, the checks to run, and the expected output format, so
   no extra prompt is needed.

5. **Walk through the result:** a findings list per lesson, each
   finding with a severity (KRITISCH/MITTEL/GERING) and one concrete
   improvement suggestion.

6. **Apply accepted suggestions MANUALLY** to the individual
   schema-validated lesson JSON files under `sets/`. Never feed the
   export file back: nothing reads it.

7. **Re-run the validators after every content change:**

   ```bash
   python3 scripts/validate_content.py
   node scripts/validate_with_engine.mjs .
   ```

   The AI review is an additional semantic layer; it does not replace
   the technical validators.

## Best practices

- **The export is a snapshot, not a live document.** Re-export after
  every content change; never keep reviewing a stale export.
- **Re-insert the source chapter for every review** when it has
  changed; do not copy it out of an old export.
- **Review large sets in slices** (e.g. 8-10 lessons per pass) when
  the AI you use has a limited context window.
- **Keep YAML as the default**; use JSON only when a tool explicitly
  requires it.
- **No copy-paste of AI suggestions without cross-reading.** The AI
  delivers suggestions, not finished truths, especially for domain
  content reviewed without a source chapter.
- **Never commit export files.** They are throwaway artifacts for the
  review; `exports/` is gitignored for exactly that reason.
- **Weigh findings made without a source chapter accordingly.**
  Factual findings checked only against general knowledge deserve
  lower confidence. The AI marks these itself in its output ("geprüft
  gegen Allgemeinwissen, kein Quellkapitel vorhanden"); keep that in
  mind while cross-reading anyway.
