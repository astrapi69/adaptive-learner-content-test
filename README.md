# adaptive-learner-content-test

Starter-Kit für eigene Adaptive Learner Lektionen.
Forke dieses Repo und erstelle deine eigenen Inhalte.

Anleitung: [docs/GETTING-STARTED.md](docs/GETTING-STARTED.md)

## Was ist drin

- `docs/` — [GETTING-STARTED.md](docs/GETTING-STARTED.md) und das
  vollständige [LESSON-FORMAT.md](docs/LESSON-FORMAT.md).
- `templates/` — Vorlagen je Domäne (language / programming /
  knowledge) für das Single-JSON-Lektionsformat.
- `examples/` — eine vollständige Beispiel-Lektion
  ([Inception-Effekt](examples/inception-effekt/)) zum Nachlesen.
- `sets/de/inception-example/` — dasselbe als lauffähiges
  Beispiel-Set, im Wurzel-`manifest.yaml` registriert.
- `books.yaml` — Buchempfehlungen je Domäne.
- `scripts/validate_content.py` — lokaler Validator.

## Eigene Inhalte lokal prüfen

```bash
python3 scripts/validate_content.py
```

Exit-Code 0, wenn alle Sets bestehen; sonst 1 mit einem Bericht je
Datei. Der Validator braucht nur Python 3 und PyYAML
(`pip install pyyaml`).
