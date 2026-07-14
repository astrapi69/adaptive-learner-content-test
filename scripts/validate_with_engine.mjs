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
 *
 * `--warnings` also lists the author lints (W-*) that never block. It runs
 * through the SAME extension registry as the error gate, so ext: lessons are
 * validated instead of refused — `make lint-warnings` used to shell out to the
 * bare CLI (no registry) and died on ext content (content-test#71).
 */
import { validateLesson, validateManifest } from "learn-content-engine";
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join, relative } from "node:path";
import { parse as parseYaml } from "yaml";

// --- adopted extension tier (content-test#66) ------------------------------
// The app has ADOPTED these ext: types - a mirror of its SUPPORTED_EXTENSIONS
// (frontend/src/lib/content/validation/lesson-schema-validator.ts). Registering
// them lets a lesson that DECLARES one load through this gate instead of being
// refused (E-EXT-UNSUPPORTED), while any UNADOPTED ext type is still refused -
// exactly the app's load-guard contract, applied at content-CI time.
//
// The validators are permissive on purpose: ext_payload CORRECTNESS is the
// consumer's job (the app's validateGeneratedLesson owns the payload rules).
// Publishing those rules so this gate can reuse them - instead of vendoring a
// drift-prone copy - is the follow-up. Keep this list in sync with the app
// when a new extension is adopted.
const ADOPTED_EXTENSIONS = [
  "ext:al-categorization",
  "ext:al-error-correction",
  "ext:al-reading-comprehension",
  "ext:al-graded-quiz",
].map((type) => ({ type, major: 1, validate: () => [] }));

const withExtensions = { extensions: ADOPTED_EXTENSIONS };

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

/** A base lesson whose exercise is replaced by an ``ext:`` one. */
function extLesson(type, extPayload) {
  const lesson = baseLesson();
  lesson.requires_extensions = [`${type}@1`];
  lesson.steps[1].exercise = {
    id: "e1",
    type,
    prompt: "Ext exercise.",
    card_ids: ["c1"],
    ext_payload: extPayload,
  };
  return lesson;
}

function selfTest() {
  const sane = validateLesson(baseLesson(), withExtensions);
  if (!sane.valid) {
    console.error("SELF-TEST BROKEN: the base lesson must be valid:");
    for (const issue of sane.errors) console.error(`   ${issue.path}: ${issue.message}`);
    return 1;
  }
  let failures = 0;
  for (const testCase of SELF_TEST_CASES) {
    const lesson = baseLesson();
    testCase.mutate(lesson);
    const result = validateLesson(lesson, withExtensions);
    if (result.valid) {
      failures++;
      console.error(`SELF-TEST FAIL: engine did not flag: ${testCase.name}`);
    } else {
      console.log(`self-test OK: ${testCase.name}`);
    }
  }

  // Extension tier (content-test#66): an ADOPTED ext type loads, an UNADOPTED
  // one is still refused loudly.
  const adopted = validateLesson(
    extLesson("ext:al-categorization", {
      categories: [
        { name: "A", items: ["x"] },
        { name: "B", items: ["y"] },
      ],
    }),
    withExtensions,
  );
  if (!adopted.valid) {
    failures++;
    console.error("SELF-TEST FAIL: an adopted extension lesson must load:");
    for (const issue of adopted.errors) console.error(`   ${issue.path}: ${issue.message}`);
  } else {
    console.log("self-test OK: adopted extension ext:al-categorization loads");
  }

  const gradedQuiz = validateLesson(
    extLesson("ext:al-graded-quiz", {
      pass_threshold: 60,
      questions: [
        { prompt: "2+2?", type: "multiple_choice", options: [{ text: "4", correct: true }, { text: "5" }], points: 2 },
      ],
    }),
    withExtensions,
  );
  if (!gradedQuiz.valid) {
    failures++;
    console.error("SELF-TEST FAIL: an adopted ext:al-graded-quiz lesson must load:");
    for (const issue of gradedQuiz.errors) console.error(`   ${issue.path}: ${issue.message}`);
  } else {
    console.log("self-test OK: adopted extension ext:al-graded-quiz loads");
  }

  const unadopted = validateLesson(extLesson("ext:zz-unknown", {}), withExtensions);
  if (unadopted.valid) {
    failures++;
    console.error("SELF-TEST FAIL: an unadopted extension must be refused (E-EXT-UNSUPPORTED)");
  } else {
    console.log("self-test OK: unadopted extension ext:zz-unknown refused");
  }

  // Warning tier (content-test#71): author lints (W-*) are surfaced but never
  // block. Proves the --warnings path is not toothless and that ext lessons
  // reach the warning check instead of erroring out. A lesson with an unused
  // card stays valid AND carries a W-CARD-UNUSED warning.
  const warnLesson = baseLesson();
  warnLesson.cards.push({ id: "c-unused", front: "orphan", back: "never referenced" });
  const warned = validateLesson(warnLesson, withExtensions);
  if (!warned.valid) {
    failures++;
    console.error("SELF-TEST BROKEN: an unused-card lesson must stay valid (warning, not error):");
    for (const issue of warned.errors) console.error(`   ${issue.path}: ${issue.message}`);
  } else if (!warned.warnings.some((issue) => issue.id === "W-CARD-UNUSED")) {
    failures++;
    console.error("SELF-TEST FAIL: expected a surfaced W-CARD-UNUSED warning, got none");
  } else {
    console.log("self-test OK: author-lint warning surfaced (W-CARD-UNUSED)");
  }

  if (failures) return 1;
  console.log(`\nSelf-test passed: the gate rejects all bad-lesson classes, gates the extension tier, and surfaces author warnings.`);
  return 0;
}

// --- full repo run ---------------------------------------------------------
// With `showWarnings`, the author lints (W-*) are ALSO listed. Warnings never
// change the exit code (errors-only), so `make lint-warnings` is a reporter,
// not a gate. Crucially this runs through the SAME extension registry as the
// error gate, so an ext: lesson is validated (not refused with
// E-EXT-UNSUPPORTED) - the bug this replaces used the bare CLI without a
// registry (content-test#71).
function validateAll(repoRoot, { showWarnings = false } = {}) {
  let lessons = 0;
  let manifests = 0;
  const problems = [];
  const warned = [];

  const report = (file, errors) => problems.push({ file, errors });

  // 1. Every lesson JSON under sets/ (+ every per-set manifest).
  for (const file of walk(join(repoRoot, "sets"))) {
    const rel = relative(repoRoot, file);
    if (rel.includes("/lessons/") && rel.endsWith(".json")) {
      lessons += 1;
      const res = validateLesson(JSON.parse(readFileSync(file, "utf8")), withExtensions);
      if (!res.valid) report(rel, res.errors);
      if (showWarnings && res.warnings.length) warned.push({ file: rel, warnings: res.warnings });
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

  const totalWarnings = warned.reduce((sum, w) => sum + w.warnings.length, 0);
  console.log(
    `engine-validate: ${lessons} lesson(s), ${manifests} manifest(s) checked — ` +
      `${problems.length} file(s) with errors` +
      (showWarnings ? `, ${totalWarnings} warning(s)` : ""),
  );
  if (showWarnings) {
    for (const w of warned) {
      console.log(`\nWARN ${w.file}`);
      for (const issue of w.warnings) console.log(`   [${issue.id}] ${issue.path} ${issue.message}`);
    }
  }
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
const showWarnings = args.includes("--warnings");
const repoRoot = args.find((arg) => !arg.startsWith("--")) ?? ".";
process.exit(validateAll(repoRoot, { showWarnings }));
