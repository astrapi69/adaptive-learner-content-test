# adaptive-learner-content-test

Starter-Kit für eigene Adaptive Learner Lektionen.
Forke dieses Repo und erstelle deine eigenen Inhalte.

Anleitung: [docs/GETTING-STARTED.md](docs/GETTING-STARTED.md)

## Was ist drin

- `docs/` — [GETTING-STARTED.md](docs/GETTING-STARTED.md) und
  [LESSON-FORMAT.md](docs/LESSON-FORMAT.md) (lokale Zusammenfassung; die
  kanonische, testvalidierte Format-Referenz ist die
  [learn-content-engine `docs/lesson-format.md`](https://github.com/astrapi69/learn-content-engine/blob/main/docs/lesson-format.md),
  gespiegelt in [`schema/`](schema/)).
- `templates/` — Vorlagen je Domäne (language / programming /
  knowledge) für das Single-JSON-Lektionsformat.
- `examples/` — eine vollständige Beispiel-Lektion
  ([Inception-Effekt](examples/inception-effekt/)) zum Nachlesen.
- `sets/de/inception-example/` — dasselbe als lauffähiges
  Beispiel-Set, im Wurzel-`manifest.yaml` registriert.
- `books.yaml` — Buchempfehlungen je Domäne.
- `scripts/validate_content.py` — lokaler Validator.
- `scripts/generate_exercises.py` — optionaler KI-Aufgaben-Generator
  (siehe unten).

## Eigene Inhalte lokal prüfen

```bash
python3 scripts/validate_content.py
```

Exit-Code 0, wenn alle Sets bestehen; sonst 1 mit einem Bericht je
Datei. Der Validator braucht nur Python 3 und PyYAML
(`pip install pyyaml`).

## Aufgaben mit KI generieren (optional)

`scripts/generate_exercises.py` erzeugt aus einem Thema eine vollständige
Lektion mit einem KI-Modell und lässt jeden Entwurf durch denselben
Validator laufen, bevor er geschrieben wird. Das Prinzip ist **erst
Entwurf, dann validieren**: Nichts landet direkt in `sets/`, sondern
zuerst im Staging-Ordner [`generated/`](generated/).

Setup (BYOK — dein Schlüssel, aus der Umgebung, nie im Repo):

```bash
pip install pyyaml jsonschema           # dieselben Deps wie der Validator
export ANTHROPIC_API_KEY="sk-..."       # oder OPENAI_API_KEY / GEMINI_API_KEY
```

Aufruf:

```bash
python3 scripts/generate_exercises.py \
  --topic "Im Café bestellen" \
  --target-lang fr --source-lang de --level A1 \
  --set-id fr-a1 --count 6
```

Anbieter-agnostisch: `--provider anthropic|openai|gemini` (Default
`anthropic`), Modell per `--model` überschreibbar. Der Ablauf ist ein
Schleifen-Gate: Der Prompt gibt die exakte Lektions-JSON-Form vor, die
Antwort wird geparst und validiert; schlägt die Validierung fehl, gehen
die Fehler zurück ins Modell und es versucht es erneut (begrenzt). Ein
Entwurf, der nie valide wird, wird verworfen, nicht geschrieben.

Zwei Gates bleiben nach der Generierung:

1. **Semantik-Gate der Engine** (cloze `___`-Marker == blanks, `card_ids`-
   Integrität, multiselect-Disjunktheit): läuft, wenn die
   `learn-content-engine` installiert ist, sonst spätestens in der CI —
   die reine Python-Validierung deckt es nicht ab.
2. **Muttersprachler-Review** für Sprachen, die du nicht muttersprachlich
   sprichst. Kein Validator erkennt eine unnatürliche Formulierung oder
   eine falsche Umschrift. Maschinell erzeugt, dann menschlich geprüft —
   das ist die einzig verlässliche Reihenfolge für Sprachinhalte.

Hintergrund + Prompt-Rezepte: der Blogpost "Build Your Own Lessons for
Adaptive Learner".
