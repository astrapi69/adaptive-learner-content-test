// The ext: types the app has ADOPTED, as one list with one owner.
//
// It used to live inside validate_with_engine.mjs with a comment calling it a
// mirror of the app's SUPPORTED_EXTENSIONS
// (frontend/src/lib/content/validation/lesson-schema-validator.ts). Nothing
// compared the two, and the copy drifted: the app adopted ordering, parsons
// and hotspot, this list stayed at nine entries, and a lesson using one of the
// three was refused here (E-EXT-UNSUPPORTED) although the app renders it.
//
// It is a module now so that check_adopted_extensions.mjs can read the same
// array the gate registers, instead of parsing it back out of the gate's
// source. That check runs nightly against the app's published file and
// reports drift as an issue - see .github/workflows/registry-drift.yml.
export const ADOPTED_EXTENSION_TYPES = [
  "ext:al-categorization",
  "ext:al-error-correction",
  "ext:al-reading-comprehension",
  "ext:al-graded-quiz",
  "ext:al-dictation",
  "ext:al-image-description",
  "ext:al-speak-and-record",
  "ext:al-audio-choice",
  "ext:al-audio-tiles",
  "ext:al-ordering",
  "ext:al-parsons",
  "ext:al-hotspot",
];

// Registry shape the engine expects. The validators stay permissive on
// purpose: ext_payload CORRECTNESS is the consumer's job (the app's
// validateGeneratedLesson owns the payload rules); registering the type is
// what lets a lesson that DECLARES it load through this gate at all.
export const ADOPTED_EXTENSIONS = ADOPTED_EXTENSION_TYPES.map((type) => ({
  type,
  major: 1,
  validate: () => [],
}));
