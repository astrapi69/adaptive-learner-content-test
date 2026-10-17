#!/usr/bin/env node
/**
 * One lesson through the pinned engine, for Python tooling.
 *
 * Reads a lesson as JSON on stdin and prints one JSON object on stdout:
 * `{ "errors": [{ id, path, message }], "warnings": [...] }`. The errors are
 * the engine's validity errors (`validateLesson`, with this repository's
 * adopted extensions) and, for a lesson that is valid, its quality shortfalls
 * (`validateLessonQuality`: the minimums keyed to the lesson's `purpose`).
 * Exit code 0 whenever it could judge the lesson; 2 on bad input.
 *
 *   node scripts/engine_check.mjs [--source-language <tag>] < lesson.json
 *
 * `--source-language` is the set's source language, for the card-back script
 * lint (`W-CARD-BACK-SCRIPT`); a lesson's own `source_language` wins.
 *
 * The quality minimums, the language rules and the id uniqueness are the
 * engine's (learn-content-engine#185, #190, #202): Python tooling such as
 * generate_exercises.py asks the engine through this script instead of keeping
 * a copy of the rules.
 */
import { validateLesson, validateLessonQuality } from "learn-content-engine";
import { readFileSync } from "node:fs";

import { ADOPTED_EXTENSIONS } from "./adopted-extensions.mjs";

const args = process.argv.slice(2);
const sourceIndex = args.indexOf("--source-language");
const sourceLanguage = sourceIndex >= 0 ? args[sourceIndex + 1] : undefined;

let lesson;
try {
  lesson = JSON.parse(readFileSync(0, "utf8"));
} catch (error) {
  console.error(`engine_check: stdin is not a JSON lesson: ${error.message}`);
  process.exit(2);
}

const brief = (issue) => ({ id: issue.id, path: issue.path, message: issue.message });
const validity = validateLesson(lesson, { extensions: ADOPTED_EXTENSIONS, sourceLanguage });
const quality = validity.valid ? validateLessonQuality(lesson).errors : [];
console.log(
  JSON.stringify({
    errors: [...validity.errors, ...quality].map(brief),
    warnings: validity.warnings.map(brief),
  }),
);
