#!/usr/bin/env node
/**
 * Registry drift gate: our adopted ext: types vs the app's SUPPORTED_EXTENSIONS.
 *
 * scripts/adopted-extensions.mjs decides which ext: lessons this repo's
 * content gate accepts. The app decides which ones it renders. Those two
 * lists have to agree, and for a long time nothing said so out loud: the
 * comment claimed a mirror, the app adopted three more types, and a lesson
 * using one of them was refused here while the app rendered it fine.
 *
 * A copy without a comparison drifts. This is the comparison. It reads the
 * app's list from its published source file (the repository is public, so no
 * token is involved, the same way the schema-drift job reads the upstream
 * search-index schema) and diffs it against ours.
 *
 * It does NOT run in the PR gate. The app's list moves in the app's
 * repository, so a PR here would turn red for something this repo did not do.
 * It runs nightly and reports the difference as an issue - see
 * .github/workflows/registry-drift.yml.
 *
 * Usage:
 *   node scripts/check_adopted_extensions.mjs             # compare
 *   node scripts/check_adopted_extensions.mjs --self-test # prove it bites
 */
import { ADOPTED_EXTENSION_TYPES } from "./adopted-extensions.mjs";

const APP_REF = process.env.APP_REF ?? "develop";
const APP_SOURCE =
  `https://raw.githubusercontent.com/astrapi69/adaptive-learner/${APP_REF}` +
  "/frontend/src/lib/content/validation/lesson-schema-validator.ts";

// The smallest parse that survives ordinary edits: the declaration line, then
// every quoted entry up to the closing bracket.
const LIST_PATTERN = /SUPPORTED_EXTENSIONS[^=]*=\s*\[([^\]]*)\]/;

/** The ext: types named in the app's source text. */
export function parseSupportedExtensions(source) {
  const block = source.match(LIST_PATTERN);
  if (!block) return [];
  return [...block[1].matchAll(/["']([^"']+)["']/g)].map((match) => match[1]);
}

/** What each side has that the other does not. */
export function compareRegistries(ours, theirs) {
  const missing = theirs.filter((type) => !ours.includes(type));
  const extra = ours.filter((type) => !theirs.includes(type));
  return { missing, extra, inSync: missing.length === 0 && extra.length === 0 };
}

function selfTest() {
  const sample = `export const SUPPORTED_EXTENSIONS: readonly string[] = [\n  "ext:al-a",\n  "ext:al-b",\n];`;
  const parsed = parseSupportedExtensions(sample);
  if (parsed.join(",") !== "ext:al-a,ext:al-b") {
    console.error(`self-test FAILED: parsed ${JSON.stringify(parsed)}`);
    return 1;
  }
  if (parseSupportedExtensions("no list here at all").length !== 0) {
    console.error("self-test FAILED: a source without the list parsed as entries");
    return 1;
  }
  const drift = compareRegistries(["ext:al-a"], ["ext:al-a", "ext:al-b"]);
  if (drift.inSync || drift.missing[0] !== "ext:al-b") {
    console.error("self-test FAILED: a missing entry was not reported");
    return 1;
  }
  const extra = compareRegistries(["ext:al-a", "ext:al-c"], ["ext:al-a"]);
  if (extra.inSync || extra.extra[0] !== "ext:al-c") {
    console.error("self-test FAILED: an extra entry was not reported");
    return 1;
  }
  console.log("self-test passed: parser reads a list, ignores a missing one, and both drift directions are reported");
  return 0;
}

async function main(argv) {
  if (argv.includes("--self-test")) return selfTest();

  const response = await fetch(APP_SOURCE);
  if (!response.ok) {
    console.error(`cannot read the app's list: HTTP ${response.status} for ${APP_SOURCE}`);
    return 2;
  }
  const theirs = parseSupportedExtensions(await response.text());
  // A parse that returns nothing means the app's file changed shape. That is a
  // broken check, not an empty registry, and it must not read as "in sync".
  if (theirs.length < 9) {
    console.error(
      `the app's list parsed as ${theirs.length} entries (${JSON.stringify(theirs)}) - the source shape changed, fix the parser`,
    );
    return 2;
  }

  const { missing, extra, inSync } = compareRegistries(ADOPTED_EXTENSION_TYPES, theirs);
  console.log(`app (${APP_REF}): ${theirs.length} adopted, here: ${ADOPTED_EXTENSION_TYPES.length}`);
  if (inSync) {
    console.log("registry in sync");
    return 0;
  }
  if (missing.length) console.log(`missing here (the app renders them, this gate refuses them): ${missing.join(", ")}`);
  if (extra.length) console.log(`extra here (this gate accepts them, the app refuses them): ${extra.join(", ")}`);
  return 1;
}

main(process.argv.slice(2)).then((code) => process.exit(code));
