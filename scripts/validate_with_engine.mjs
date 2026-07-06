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
 */
import { validateLesson, validateManifest } from "learn-content-engine";
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join, relative } from "node:path";
import { parse as parseYaml } from "yaml";

const repoRoot = process.argv[2] ?? ".";

function* walk(dir) {
  for (const name of readdirSync(dir)) {
    const p = join(dir, name);
    if (statSync(p).isDirectory()) yield* walk(p);
    else yield p;
  }
}

let lessons = 0;
let manifests = 0;
const problems = [];

function report(file, errors) {
  problems.push({ file, errors });
}

// 1. Every lesson JSON under sets/**/lessons/
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
process.exit(problems.length === 0 ? 0 : 1);
