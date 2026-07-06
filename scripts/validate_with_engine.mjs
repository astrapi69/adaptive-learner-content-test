#!/usr/bin/env node
/**
 * Engine conformance gate: run learn-content-engine's validateLesson()
 * (structural ajv layer AND the semantic cross-field rules — cloze
 * markers == blanks, referential card_ids integrity, multiselect
 * disjointness, picture-choice exactly-one-correct, ...) over EVERY
 * lesson in this repo. Gate: zero errors.
 *
 * Rationale: the structural CI (validate_content.py against the
 * mirrored JSON Schema) cannot see cross-field semantics; a real
 * conformance run found two semantic bugs in the official content repo
 * that the structural gate had passed. This job closes that hole with
 * the engine's own validator — the same one third-party consumers run.
 *
 * The engine version comes from schema/engine-version.txt (the same pin
 * the schema-mirror drift gate uses); CI installs it with
 * `npm install --no-save learn-content-engine@$(cat schema/engine-version.txt)`.
 *
 * Usage:
 *   node scripts/validate_with_engine.mjs               # validate sets/
 *   node scripts/validate_with_engine.mjs --self-test   # prove the gate bites
 *
 * --self-test feeds known-bad lessons (one per semantic rule class) to
 * validateLesson and exits non-zero unless EVERY one is rejected — so a
 * silently toothless validator cannot masquerade as a green gate.
 */
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { validateLesson } from "learn-content-engine";

const repoRoot = fileURLToPath(new URL("..", import.meta.url));
const setsDir = join(repoRoot, "sets");

function collectLessonFiles(dir) {
  const files = [];
  for (const entry of readdirSync(dir)) {
    const full = join(dir, entry);
    if (statSync(full).isDirectory()) files.push(...collectLessonFiles(full));
    else if (entry.endsWith(".json")) files.push(full);
  }
  return files.sort();
}

// One minimal valid lesson the bad cases are derived from; each bad case
// violates exactly one semantic rule the engine must flag.
const baseLesson = () => ({
  id: "self-test",
  title: "Self test",
  cards: [{ id: "c1", front: "a", back: "b" }],
  steps: [
    { id: "t1", type: "theory", title: "T", body: "Theory." },
    {
      id: "e1",
      type: "exercise",
      theory_ref: "t1",
      title: "E",
      exercise: {
        id: "e1",
        type: "cloze",
        prompt: "Fill in.",
        card_ids: ["c1"],
        sentence: "One ___ here.",
        blanks: [{ accept: ["blank"] }],
        cloze_mode: "type",
      },
    },
  ],
});

const SELF_TEST_CASES = [
  {
    name: "cloze marker/blank count mismatch",
    mutate(lesson) {
      lesson.steps[1].exercise.sentence = "Two ___ markers ___ here.";
    },
  },
  {
    name: "card_ids referential integrity",
    mutate(lesson) {
      lesson.steps[1].exercise.card_ids = ["no-such-card"];
    },
  },
  {
    name: "multiselect accept/distractors disjointness",
    mutate(lesson) {
      lesson.steps[1].exercise = {
        id: "e1",
        type: "cloze",
        prompt: "Pick all.",
        card_ids: ["c1"],
        sentence: "Pick ___ now.",
        cloze_mode: "multiselect",
        accept: ["same"],
        distractors: ["same", "other"],
      };
    },
  },
  {
    name: "picture_choice exactly-one-correct",
    mutate(lesson) {
      lesson.steps[1].exercise = {
        id: "e1",
        type: "picture_choice",
        prompt: "Which one?",
        card_ids: ["c1"],
        images: [
          { src: "a.png", alt: "a", is_correct: "true" },
          { src: "b.png", alt: "b", is_correct: "true" },
        ],
      };
    },
  },
  {
    name: "structural: unknown field rejected",
    mutate(lesson) {
      lesson.totally_unknown_field = true;
    },
  },
];

function selfTest() {
  const sane = validateLesson(baseLesson());
  if (!sane.valid) {
    console.error("SELF-TEST BROKEN: the base lesson must be valid:");
    for (const issue of sane.errors) console.error(`   ${issue.path}: ${issue.message}`);
    return 1;
  }
  let failures = 0;
  for (const testCase of SELF_TEST_CASES) {
    const lesson = baseLesson();
    testCase.mutate(lesson);
    const result = validateLesson(lesson);
    if (result.valid) {
      failures++;
      console.error(`SELF-TEST FAIL: engine did not flag: ${testCase.name}`);
    } else {
      console.log(`self-test OK: ${testCase.name}`);
    }
  }
  if (failures) return 1;
  console.log(`\nSelf-test passed: the gate rejects all ${SELF_TEST_CASES.length} bad-lesson classes.`);
  return 0;
}

function validateAll() {
  const files = collectLessonFiles(setsDir);
  let invalid = 0;
  for (const file of files) {
    let lesson;
    try {
      lesson = JSON.parse(readFileSync(file, "utf8"));
    } catch (error) {
      invalid++;
      console.error(`PARSE ERROR ${file}: ${error.message}`);
      continue;
    }
    const result = validateLesson(lesson);
    if (!result.valid) {
      invalid++;
      console.error(`INVALID ${file.slice(repoRoot.length)}`);
      for (const issue of result.errors) console.error(`   ${issue.path}: ${issue.message}`);
    }
  }
  console.log(`\n${files.length} lesson(s) checked with the engine validator, ${invalid} invalid.`);
  return invalid ? 1 : 0;
}

process.exit(process.argv.includes("--self-test") ? selfTest() : validateAll());
