#!/usr/bin/env node
/**
 * Engine conformance gate: run learn-content-engine's validateLesson() /
 * validateManifest() over the WHOLE repo content — every lesson, the root
 * manifest and every per-set manifest.
 *
 * This is the semantic layer the structural CI (validate_content.py against
 * the vendored JSON Schema) cannot see: cloze blanks == '___' markers,
 * referential integrity of card_ids, multiselect disjointness, picture
 * "exactly one correct". The engine mirrors the app's model_validator rules,
 * so a green run here means the content is valid for EVERY consumer of the
 * pinned engine release — without any reference to the app.
 *
 * Run via CI (.github/workflows/engine-validate.yml) after
 * `npm install learn-content-engine@$(cat schema/engine-version.txt)`.
 * Gate: zero errors.
 *
 * `--self-test` feeds known-bad lessons (one per semantic rule class) to
 * validateLesson and exits non-zero unless EVERY one is rejected — so a
 * silently toothless validator cannot masquerade as a green gate. CI runs
 * it before the real pass.
 */
import { validateLesson, validateManifest } from "learn-content-engine";
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join, relative } from "node:path";
import { parse as parseYaml } from "yaml";

function* walk(dir) {
  for (const name of readdirSync(dir)) {
    const p = join(dir, name);
    if (statSync(p).isDirectory()) yield* walk(p);
    else yield p;
  }
}

// --- self-test -------------------------------------------------------------
// One minimal valid lesson the bad cases are derived from; each bad case
// violates exactly one rule class the engine must flag.
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

// --- full repo run ---------------------------------------------------------
function validateAll(repoRoot) {
  let lessons = 0;
  let manifests = 0;
  const problems = [];

  const report = (file, errors) => problems.push({ file, errors });

  // 1. Every lesson JSON under sets/ (+ every per-set manifest).
  for (const file of walk(join(repoRoot, "sets"))) {
    const rel = relative(repoRoot, file);
    if (rel.includes("/lessons/") && rel.endsWith(".json")) {
      lessons += 1;
      const res = validateLesson(JSON.parse(readFileSync(file, "utf8")));
      if (!res.valid) report(rel, res.errors);
    } else if (rel.endsWith("manifest.yaml")) {
      manifests += 1;
      const res = validateManifest(parseYaml(readFileSync(file, "utf8")));
      if (!res.valid) report(rel, res.errors);
    }
  }

  // 2. The root manifest.
  manifests += 1;
  const rootRes = validateManifest(
    parseYaml(readFileSync(join(repoRoot, "manifest.yaml"), "utf8")),
  );
  if (!rootRes.valid) report("manifest.yaml", rootRes.errors);

  console.log(
    `engine-validate: ${lessons} lesson(s), ${manifests} manifest(s) checked — ` +
      `${problems.length} file(s) with errors`,
  );
  for (const p of problems) {
    console.error(`\n✗ ${p.file}`);
    for (const e of p.errors) console.error(`   ${e.path}: ${e.message}`);
  }
  return problems.length === 0 ? 0 : 1;
}

const args = process.argv.slice(2);
if (args.includes("--self-test")) {
  process.exit(selfTest());
}
process.exit(validateAll(args[0] ?? "."));
