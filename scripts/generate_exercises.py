#!/usr/bin/env python3
"""Draft-then-validate AI exercise generator for the starter kit.

Generates a complete lesson (theory + exercises) from a topic with a
BYOK AI model, then gates every candidate through this repo's own
validator (``validate_content.py``) before writing it to a ``generated/``
staging folder. Nothing is ever written into a shipped ``sets/`` tree:
the staging folder is the mechanical form of "draft, then validate".

Design (see issue #25 / the "Build Your Own Lessons" blog post):

* **Provider-agnostic (BYOK).** A thin ``call_model`` dispatches to
  Anthropic / OpenAI / Gemini over plain HTTPS (stdlib ``urllib``, no
  SDK). The API key is read from the environment only, never from the
  repo. Choose the provider with ``--provider`` / ``AL_GEN_PROVIDER``.
* **The prompt pins the exact lesson-schema JSON shape** and embeds a
  worked example, so the model returns final-schema JSON, not an ad-hoc
  shape. The semantic constraints (cloze blanks == ``___`` markers,
  disjoint multiselect sets, deliberate distractors, hint rules) are
  spelled out in the prompt.
* **The validator is a hard gate, in a retry loop.** Each candidate is
  run through ``lesson_shape_errors`` + ``validate_lesson_quality``; on
  failure the error text is fed back to the model and it retries
  (bounded). A candidate that never validates is discarded, not written.

The heavy AI generation pipeline that ships INSIDE the app (EXP-036,
``frontend/src/lib/ai/generation/``) is browser-embedded TypeScript that
operates on the app's data model; it cannot be run against a forked
content repo. This script is the standalone-repo equivalent and reuses
that pipeline's prompt design (rules, type-selection, deliberate
distractors, validator-feedback retry).

Run ``python3 scripts/generate_exercises.py --help`` for usage.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPTS_DIR.parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import validate_content as vc  # noqa: E402  (sibling script, path set above)

DEFAULT_PROVIDER = "anthropic"

# Provider defaults: (env var(s) for the key, default model, API base).
PROVIDERS: dict[str, dict[str, object]] = {
    "anthropic": {
        "key_env": ("ANTHROPIC_API_KEY",),
        "model": "claude-sonnet-4-5",
        "url": "https://api.anthropic.com/v1/messages",
    },
    "openai": {
        "key_env": ("OPENAI_API_KEY",),
        "model": "gpt-4o",
        "url": "https://api.openai.com/v1/chat/completions",
    },
    "gemini": {
        "key_env": ("GEMINI_API_KEY", "GOOGLE_API_KEY"),
        "model": "gemini-2.5-flash",
        "url": "https://generativelanguage.googleapis.com/v1beta/models",
    },
}

DEFAULT_MAX_RETRIES = 3
DEFAULT_TIMEOUT = 120


# --------------------------------------------------------------------------
# Prompt building
# --------------------------------------------------------------------------


@dataclass
class GenerationParams:
    """What to generate. All fields are author-supplied, none from the model."""

    topic: str
    target_language: str
    source_language: str
    level: str = "A1"
    count: int = 6
    set_id: str = "generated-set"


def build_generation_prompt(params: GenerationParams, feedback: str | None = None) -> str:
    """Build the generation prompt that pins the final lesson-schema shape.

    The semantic invariants the engine enforces (blanks == markers,
    disjoint multiselect sets, referential integrity) are stated as rules
    so the model emits valid content; the validator still gates the result.

    Args:
        params: The author's generation request.
        feedback: On a retry, the validator's error text from the previous
            attempt, so the model corrects rather than repeats.

    Returns:
        A single prompt string for the user message.
    """
    lines = [
        "You are an instructional designer creating a language lesson for the",
        "Adaptive Learner content format. Produce ONE complete lesson as JSON.",
        "",
        f"TOPIC: {params.topic}",
        f"TARGET LANGUAGE (what the learner studies): {params.target_language}",
        f"SOURCE LANGUAGE (the explanation language): {params.source_language}",
        f"CEFR LEVEL: {params.level}",
        f"Create at least {max(5, params.count)} exercises.",
        "",
        "RULES",
        "- Return JSON ONLY. No prose, no Markdown code fences, no comments.",
        "- Write cards and exercises in the correct languages: card 'front' in",
        f"  the target language ({params.target_language}), card 'back' and all",
        f"  theory in the source language ({params.source_language}).",
        "- At least one theory step and at least two DIFFERENT exercise types",
        "  (an all-cloze set is allowed only if every cloze is select/multiselect).",
        "- Allowed exercise types: cloze, free_text, matching, word_tiles.",
        "  Do NOT use picture_choice (it needs image asset files this flow",
        "  cannot create).",
        "- Every distractor is a deliberate, plausible mistake a real learner",
        "  would make (a confusable form, a classic misconception), never an",
        "  obviously-wrong throwaway.",
        "- A hint must never reveal or state the length of the answer.",
        "- Exercises may reference cards via card_ids; every id used MUST be",
        "  the id of a card you include in 'cards'.",
        "",
        "EXERCISE FIELDS (final schema)",
        "- cloze/type: cloze_mode 'type'; 'sentence' with one ___ per blank;",
        "  'blanks': [{accept:[...]}]; number of ___ MUST equal blanks length.",
        "- cloze/select: as type, plus a non-empty 'distractors'; blank accept[0]",
        "  is the correct option.",
        "- cloze/multiselect: 'sentence' is the question (NO ___), no 'blanks';",
        "  'accept' lists every correct option, 'distractors' the wrong ones;",
        "  both non-empty and disjoint.",
        "- free_text: 'accept' (>= 2 acceptable answers) and 'distractors'.",
        "- matching: 'pairs' (>= 3 of {left, right}).",
        "- word_tiles: 'tiles' (>= 2); use ONLY for a sentence with one fixed",
        "  word order, never for open definitions.",
        "",
        "OUTPUT SHAPE (return exactly this shape, filled with your content):",
        _example_lesson_json(params),
    ]
    if feedback:
        lines += [
            "",
            "CORRECTION",
            "Your previous JSON failed validation with these errors:",
            feedback,
            "Return a corrected lesson as JSON only, fixing every error above.",
        ]
    return "\n".join(lines)


def _example_lesson_json(params: GenerationParams) -> str:
    """A compact, schema-correct worked example embedded in the prompt."""
    example = {
        "id": "01-example",
        "title": "Example lesson title",
        "description": "One-sentence summary.",
        "target_language": params.target_language,
        "source_language": params.source_language,
        "domain": "language",
        "estimated_minutes": 8,
        "cards": [
            {"id": "card-a", "front": "<target word>", "back": "<source translation>"}
        ],
        "steps": [
            {
                "id": "intro",
                "type": "theory",
                "title": "Theory",
                "body": "Explain the concept in **Markdown**, in the source language.",
            },
            {
                "id": "ex-cloze",
                "type": "exercise",
                "exercise": {
                    "id": "ex-cloze",
                    "type": "cloze",
                    "cloze_mode": "select",
                    "prompt": "Choose the correct word.",
                    "sentence": "<sentence with one ___ blank>",
                    "blanks": [{"accept": ["<correct>"]}],
                    "distractors": ["<plausible wrong>", "<plausible wrong>"],
                },
            },
            {
                "id": "ex-free",
                "type": "exercise",
                "exercise": {
                    "id": "ex-free",
                    "type": "free_text",
                    "prompt": "Answer in the target language.",
                    "accept": ["<answer>", "<accepted variant>"],
                    "distractors": ["<deliberate mistake>"],
                },
            },
        ],
    }
    return json.dumps(example, ensure_ascii=False, indent=2)


# --------------------------------------------------------------------------
# Defensive JSON extraction
# --------------------------------------------------------------------------


def extract_json(text: str) -> dict:
    """Parse a lesson object out of a model reply, tolerating stray wrapping.

    Tries a direct parse first, then strips Markdown fences, then falls back
    to the outermost balanced ``{...}`` span. Raises ``ValueError`` when no
    JSON object can be recovered.
    """
    candidate = text.strip()
    for attempt in (candidate, _strip_fences(candidate), _outermost_object(candidate)):
        if not attempt:
            continue
        try:
            parsed = json.loads(attempt)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed
    raise ValueError("no JSON object found in model reply")


def _strip_fences(text: str) -> str:
    """Remove a leading/trailing Markdown code fence if present."""
    fenced = re.match(r"^```(?:json)?\s*(.*?)\s*```$", text, re.DOTALL)
    return fenced.group(1) if fenced else ""


def _outermost_object(text: str) -> str:
    """Return the substring from the first ``{`` to the last ``}`` inclusive."""
    start = text.find("{")
    end = text.rfind("}")
    return text[start : end + 1] if 0 <= start < end else ""


# --------------------------------------------------------------------------
# Provider layer (BYOK, stdlib HTTPS, no SDK)
# --------------------------------------------------------------------------


@dataclass
class ModelConfig:
    """Resolved provider settings for one run."""

    provider: str = DEFAULT_PROVIDER
    model: str = ""
    api_key: str = ""
    timeout: int = DEFAULT_TIMEOUT
    max_tokens: int = 4096


def resolve_api_key(provider: str) -> str:
    """Read the provider's API key from the environment (BYOK).

    Raises:
        RuntimeError: when no key env var is set for the provider.
    """
    for env_name in PROVIDERS[provider]["key_env"]:  # type: ignore[index]
        value = os.environ.get(env_name)
        if value:
            return value
    names = " / ".join(PROVIDERS[provider]["key_env"])  # type: ignore[arg-type]
    raise RuntimeError(f"No API key for {provider}: set {names} in the environment.")


def _http_post_json(url: str, headers: dict[str, str], payload: dict, timeout: int) -> dict:
    """POST a JSON payload and return the parsed JSON response.

    Isolated so tests can patch it instead of hitting a real API.

    Raises:
        RuntimeError: on an HTTP or transport error, with the provider's
            response body when available (actionable in a bug report).
    """
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")
        raise RuntimeError(f"HTTP {exc.code} from provider: {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"network error calling provider: {exc.reason}") from exc


def _call_anthropic(prompt: str, config: ModelConfig) -> str:
    headers = {
        "content-type": "application/json",
        "x-api-key": config.api_key,
        "anthropic-version": "2023-06-01",
    }
    payload = {
        "model": config.model,
        "max_tokens": config.max_tokens,
        "messages": [{"role": "user", "content": prompt}],
    }
    data = _http_post_json(PROVIDERS["anthropic"]["url"], headers, payload, config.timeout)  # type: ignore[arg-type]
    return "".join(block.get("text", "") for block in data.get("content", []))


def _call_openai(prompt: str, config: ModelConfig) -> str:
    headers = {
        "content-type": "application/json",
        "authorization": f"Bearer {config.api_key}",
    }
    payload = {
        "model": config.model,
        "max_tokens": config.max_tokens,
        "messages": [{"role": "user", "content": prompt}],
    }
    data = _http_post_json(PROVIDERS["openai"]["url"], headers, payload, config.timeout)  # type: ignore[arg-type]
    return data["choices"][0]["message"]["content"]


def _call_gemini(prompt: str, config: ModelConfig) -> str:
    base = PROVIDERS["gemini"]["url"]
    url = f"{base}/{config.model}:generateContent?key={config.api_key}"
    headers = {"content-type": "application/json"}
    payload = {"contents": [{"parts": [{"text": prompt}]}]}
    data = _http_post_json(url, headers, payload, config.timeout)
    parts = data["candidates"][0]["content"]["parts"]
    return "".join(part.get("text", "") for part in parts)


_DISPATCH = {"anthropic": _call_anthropic, "openai": _call_openai, "gemini": _call_gemini}


def call_model(prompt: str, config: ModelConfig) -> str:
    """Send ``prompt`` to the configured provider and return the raw reply text."""
    return _DISPATCH[config.provider](prompt, config)


# --------------------------------------------------------------------------
# Validation gate
# --------------------------------------------------------------------------


def validate_candidate(lesson: dict, source_language: str) -> list[str]:
    """Gate a candidate lesson through this repo's own validator.

    Runs the structural schema check first (``lesson_shape_errors``); only
    when the shape is valid does the quality layer run (it indexes fields
    the schema guarantees). Returns an empty list when the lesson passes.

    Note: the cross-field SEMANTIC rules (cloze blanks == ``___`` markers,
    multiselect disjointness, card_ids referential integrity, picture
    exactly-one-correct) live in the engine layer (``validate_with_engine``
    / the engine's ``validateLesson``), not in ``validate_content.py``. Use
    :func:`engine_check` when the engine is installed, and rely on the
    repo's engine CI gate before shipping.
    """
    errors = vc.lesson_shape_errors(lesson)
    if errors:
        return errors
    vc.validate_lesson_quality(lesson, source_language, "<candidate>", errors)
    return errors


def engine_check(lesson_path: Path) -> list[str] | None:
    """Best-effort semantic gate via the installed engine.

    Runs the engine's ``validateLesson`` on a single file when Node and the
    pinned ``learn-content-engine`` are both available in the repo. Returns
    the list of semantic errors (empty == valid), or ``None`` when the
    engine is not installed (the caller then warns and defers to CI).
    """
    node = _which("node")
    engine_dir = REPO_ROOT / "node_modules" / "learn-content-engine"
    if not node or not engine_dir.is_dir():
        return None
    script = (
        "import{validateLesson} from 'learn-content-engine';"
        "import{readFileSync} from 'node:fs';"
        "const l=JSON.parse(readFileSync(process.argv[1],'utf8'));"
        "const r=validateLesson(l);"
        "if(r&&r.ok===false){console.log(JSON.stringify(r.errors||[r.error||'invalid']));"
        "process.exit(3);}"
    )
    result = subprocess.run(  # noqa: S603  (fixed args, no shell)
        [node, "--input-type=module", "-e", script, str(lesson_path)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        return []
    try:
        return list(json.loads(result.stdout.strip()))
    except (json.JSONDecodeError, ValueError):
        return [result.stdout.strip() or result.stderr.strip() or "engine rejected the lesson"]


def _which(binary: str) -> str | None:
    """Return the path to ``binary`` on PATH, or ``None``."""
    from shutil import which

    return which(binary)


# --------------------------------------------------------------------------
# Generation loop
# --------------------------------------------------------------------------


@dataclass
class GenerationResult:
    """Outcome of one generation attempt sequence."""

    lesson: dict | None = None
    attempts: int = 0
    errors: list[str] = field(default_factory=list)


def generate_lesson(
    config: ModelConfig,
    params: GenerationParams,
    *,
    call=call_model,
    max_retries: int = DEFAULT_MAX_RETRIES,
) -> GenerationResult:
    """Generate one validated lesson, retrying on validation failure.

    The model is called with the generation prompt; the reply is parsed and
    gated through :func:`validate_candidate`. On failure the validator's
    errors are fed back into the prompt and the model retries, up to
    ``max_retries`` times. A candidate that never validates is discarded.

    Args:
        config: Resolved provider settings.
        params: The author's generation request.
        call: The model-call function (injected for testing).
        max_retries: Extra attempts after the first (total = max_retries + 1).

    Returns:
        A :class:`GenerationResult`; ``lesson`` is ``None`` when every
        attempt failed, with the last attempt's ``errors`` populated.
    """
    feedback: str | None = None
    result = GenerationResult()
    for attempt in range(max_retries + 1):
        result.attempts = attempt + 1
        prompt = build_generation_prompt(params, feedback=feedback)
        try:
            lesson = extract_json(call(prompt, config))
        except ValueError as exc:
            result.errors = [f"could not parse model reply as JSON: {exc}"]
            feedback = "Your reply was not valid JSON. Return a single JSON object only."
            continue
        errors = validate_candidate(lesson, params.source_language)
        if not errors:
            result.lesson = lesson
            result.errors = []
            return result
        result.errors = errors
        feedback = "\n".join(f"- {e}" for e in errors)
    return result


# --------------------------------------------------------------------------
# Staging output
# --------------------------------------------------------------------------


def slugify(text: str, fallback: str = "lesson") -> str:
    """Turn free text into a kebab-case, filename-safe slug."""
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug or fallback


def stage_lesson(lesson: dict, out_dir: Path, set_id: str) -> Path:
    """Write a validated lesson into the ``generated/`` staging area.

    The lesson is NEVER written into a shipped ``sets/`` tree: staging is
    the mechanical enforcement of draft-then-validate. The author reviews
    the file, then moves it into a set and re-runs the full validator + CI.
    """
    target_dir = out_dir / slugify(set_id, "generated-set")
    target_dir.mkdir(parents=True, exist_ok=True)
    name = slugify(str(lesson.get("id") or lesson.get("title") or "lesson"))
    path = target_dir / f"{name}.json"
    path.write_text(json.dumps(lesson, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def build_config(args: argparse.Namespace) -> ModelConfig:
    """Assemble the :class:`ModelConfig` from CLI args + environment."""
    provider = args.provider or os.environ.get("AL_GEN_PROVIDER") or DEFAULT_PROVIDER
    if provider not in PROVIDERS:
        raise RuntimeError(f"Unknown provider '{provider}' (choose: {', '.join(PROVIDERS)}).")
    model = args.model or str(PROVIDERS[provider]["model"])
    return ModelConfig(provider=provider, model=model, api_key=resolve_api_key(provider))


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate a validated lesson from a topic with a BYOK AI model."
    )
    parser.add_argument("--topic", required=True, help="What the lesson is about.")
    parser.add_argument("--target-lang", required=True, help="Language the learner studies (BCP-47).")
    parser.add_argument("--source-lang", required=True, help="Explanation language (BCP-47).")
    parser.add_argument("--level", default="A1", help="CEFR level (default A1).")
    parser.add_argument("--count", type=int, default=6, help="Exercises to request (min 5).")
    parser.add_argument("--set-id", default="generated-set", help="Target set id (staging subfolder).")
    parser.add_argument("--provider", default="", help="anthropic | openai | gemini (default anthropic).")
    parser.add_argument("--model", default="", help="Override the provider's default model.")
    parser.add_argument("--retries", type=int, default=DEFAULT_MAX_RETRIES, help="Retries on validation failure.")
    parser.add_argument("--out", default="generated", help="Staging directory (default generated/).")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """CLI entry point. Returns a process exit code."""
    args = _parse_args(argv)
    try:
        config = build_config(args)
    except RuntimeError as exc:
        print(f"FATAL: {exc}", file=sys.stderr)
        return 2

    params = GenerationParams(
        topic=args.topic,
        target_language=args.target_lang,
        source_language=args.source_lang,
        level=args.level,
        count=args.count,
        set_id=args.set_id,
    )
    print(f"Generating with {config.provider} ({config.model}) ...", file=sys.stderr)
    try:
        result = generate_lesson(config, params, max_retries=args.retries)
    except RuntimeError as exc:
        # Provider / transport error (auth, rate limit, network). Retrying
        # would not fix it and would burn calls, so abort cleanly.
        print(f"FATAL: {exc}", file=sys.stderr)
        return 2
    if result.lesson is None:
        print(
            f"DISCARDED after {result.attempts} attempt(s): no candidate validated.",
            file=sys.stderr,
        )
        for err in result.errors:
            print(f"  - {err}", file=sys.stderr)
        return 1

    path = stage_lesson(result.lesson, REPO_ROOT / args.out, args.set_id)
    print(f"OK: staged {_display_path(path)} (passed structure + quality gate).")
    _report_next_steps(path)
    return 0


def _display_path(path: Path) -> str:
    """Show the path relative to the repo root when it lives inside it."""
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def _report_next_steps(path: Path) -> None:
    """Print the remaining, non-automatable gates the author still owes."""
    semantic = engine_check(path)
    if semantic is None:
        print(
            "NOTE: semantic engine gate skipped (learn-content-engine not installed). "
            "The structure + quality gate passed, but cloze blanks==markers, "
            "card_ids integrity and multiselect disjointness are only verified by "
            "the engine gate. Run the engine gate / open a PR so CI checks them.",
            file=sys.stderr,
        )
    elif semantic:
        print("WARNING: the engine's semantic gate rejected this lesson:", file=sys.stderr)
        for err in semantic:
            print(f"  - {err}", file=sys.stderr)
    else:
        print("Semantic engine gate: passed.", file=sys.stderr)
    print(
        "REVIEW BEFORE SHIPPING: read the lesson, and for a language you do not "
        "speak natively, get a native-speaker review — no validator catches an "
        "unnatural phrasing or a wrong romanization.",
        file=sys.stderr,
    )


if __name__ == "__main__":
    raise SystemExit(main())
