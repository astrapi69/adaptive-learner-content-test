# adaptive-learner-content-test

Starter-Kit fuer eigene Adaptive Learner Lektionen.
Forke dieses Repo und erstelle deine eigenen Inhalte.

Anleitung: [docs/GETTING-STARTED.md](docs/GETTING-STARTED.md)

## Was ist drin

- `docs/` — [GETTING-STARTED.md](docs/GETTING-STARTED.md) und das
  vollstaendige [LESSON-FORMAT.md](docs/LESSON-FORMAT.md).
- `templates/` — Vorlagen je Domaene (language / programming /
  knowledge), plus eine `v1.4-preview/`-Vorschau des
  Mehrdatei-Layouts.
- `examples/` — eine vollstaendige Beispiel-Lektion
  ([Inception-Effekt](examples/inception-effekt/)) zum Nachlesen.
- `sets/de/inception-example/` — dasselbe als lauffaehiges
  Beispiel-Set, im Wurzel-`manifest.yaml` registriert.
- `books.yaml` — Buchempfehlungen je Domaene.
- `scripts/validate_content.py` — lokaler Validator.

## Eigene Inhalte lokal pruefen

```bash
python3 scripts/validate_content.py
```

Exit-Code 0, wenn alle Sets bestehen; sonst 1 mit einem Bericht je
Datei. Der Validator braucht nur Python 3 und PyYAML
(`pip install pyyaml`).
