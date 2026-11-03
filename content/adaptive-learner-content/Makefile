# Makefile für dein Adaptive-Learner-Content-Repo.
#
# Ein Befehl genügt zum Loslegen:
#
#     make validate        Prüft deine Inhalte (legt beim ersten Mal automatisch
#                          eine lokale Python-Umgebung an, du musst nichts installieren).
#
# Weitere Ziele:
#     make lint            Engine-Gate lokal: installiert die gepinnte Engine
#                          (einmalig, lokal in node_modules/, per .gitignore
#                          ausgeschlossen) und lässt den Selbsttest plus den
#                          vollen Engine-Lauf über alle Lektionen und Manifeste
#                          laufen - dieselben Regel-IDs (E-CARD-REF & Co.) wie
#                          der CI-Workflow "Engine conformance"
#                          (.github/workflows/engine-validate.yml), nur VOR dem
#                          Push statt danach. Braucht Node.js (>= 20) und npm.
#     make lint-warnings   Optional: derselbe Engine-Lauf, zusätzlich mit den
#                          Warnungen (W-*). Nutzt dieselbe Extension-Registry
#                          wie das Gate, ext: Lektionen werden also validiert
#                          statt abgewiesen.
#     make setup           Nur die lokale Umgebung anlegen/aktualisieren.
#     make generate        KI-Aufgaben generieren (braucht einen API-Schlüssel, siehe README).
#     make export          Ein Set für KI-Review exportieren (ARGS="<slug> [--split-size N] ...").
#     make export-anki     Ein Set als Anki-Deck (.apkg) exportieren (ARGS="<slug> [--lang xx] [--out PATH]").
#     make audit           Überblick über deine Inhalte ausgeben.
#     make clean           Die lokale Umgebung entfernen.
#
# Du brauchst nur "make" und "python3". Kein pip, kein venv, kein Poetry von Hand.
# Die lokale Umgebung landet in .venv/ (per .gitignore ausgeschlossen), die
# Paketnamen stehen einmal in requirements.txt.
#
# Kein "make" auf deinem System (z. B. Windows ohne WSL)? Dann committe deine
# Änderungen und lass die GitHub-Actions-CI validieren, sie prüft dasselbe
# (validate / engine-validate / schema-drift).

VENV := .venv
PY := $(VENV)/bin/python
PIP := $(VENV)/bin/pip

ENGINE_PIN := $(shell cat schema/engine-version.txt)
ENGINE_STAMP := node_modules/.engine-$(ENGINE_PIN)

.PHONY: validate lint lint-warnings prose-check setup generate export export-anki audit clean help

help:
	@echo "make validate        - Inhalte prüfen (richtet sich beim ersten Mal selbst ein)"
	@echo "make lint            - Engine-Gate lokal (Selbsttest + alle Lektionen/Manifeste)"
	@echo "make lint-warnings   - derselbe Lauf, zusätzlich mit Warnungen (W-*)"
	@echo "make prose-check      - Em-Dash, unsichtbare Zeichen, fehlende Umlaute in allen Dateien"
	@echo "make setup           - lokale Umgebung anlegen"
	@echo "make generate        - KI-Aufgaben generieren (API-Schlüssel nötig; ARGS=\"--topic ...\")"
	@echo "make export          - Set für KI-Review exportieren (ARGS=\"<slug> [--split-size N] ...\")"
	@echo "make export-anki     - Set als Anki-Deck (.apkg) exportieren (ARGS=\"<slug> [--lang xx] [--out PATH]\")"
	@echo "make audit           - Inhalts-Überblick"
	@echo "make clean           - lokale Umgebung entfernen"

# Die lokale Umgebung. Wird nur angelegt, wenn sie fehlt (Sentinel .venv/.ready).
# Installiert aus requirements.txt, damit die Paketnamen nur an EINER Stelle stehen.
$(VENV)/.ready: requirements.txt
	@echo ">> Lege lokale Python-Umgebung an (einmalig) ..."
	python3 -m venv $(VENV)
	@$(PIP) install --quiet --upgrade pip
	@$(PIP) install --quiet -r requirements.txt
	@touch $(VENV)/.ready
	@echo ">> Fertig. Künftige Läufe nutzen diese Umgebung direkt."

setup: $(VENV)/.ready

validate: $(VENV)/.ready
	@$(PY) scripts/validate_content.py

# Die gepinnte Engine. Wird nur installiert, wenn der Versions-Stempel fehlt
# (idempotent; ein neuer Pin in schema/engine-version.txt erzwingt eine
# Neuinstallation, weil sich der Stempel-Name ändert).
$(ENGINE_STAMP):
	@echo ">> Installiere learn-content-engine@$(ENGINE_PIN) (einmalig, lokal in node_modules/) ..."
	npm install --no-save --no-package-lock --no-audit --no-fund "learn-content-engine@$(ENGINE_PIN)" "yaml@^2.9.0"
	@touch "$(ENGINE_STAMP)"

lint: $(ENGINE_STAMP)
	node scripts/validate_with_engine.mjs --self-test
	node scripts/validate_with_engine.mjs .

# Prosa-Gate: Em-Dash, unsichtbare Zeichen und deutsche Wörter ohne ihre
# Umlaute (ae/oe/ue/ss statt ä/ö/ü/ß) in allen getrackten Dateien.
# Der Selbsttest läuft zuerst - ein Gate, das auf bekannt schlechte Eingabe
# nicht anschlägt, ist kein Gate. Braucht nur Python 3 (keine Engine, kein
# venv).
prose-check:
	@python3 scripts/check_prose.py --self-test
	@python3 scripts/check_prose.py

lint-warnings: $(ENGINE_STAMP)
	node scripts/validate_with_engine.mjs --warnings .

# KI-Aufgaben generieren. Argumente durchreichen, z. B.:
#     make generate ARGS="--topic 'Im Cafe bestellen' --target-lang fr --source-lang de"
# Braucht einen API-Schlüssel in der Umgebung (ANTHROPIC_API_KEY / OPENAI_API_KEY /
# GEMINI_API_KEY), siehe README.
generate: $(VENV)/.ready $(ENGINE_STAMP)
	@$(PY) scripts/generate_exercises.py $(ARGS)

# Ein Set für KI-Review exportieren, z. B.:
#     make export ARGS="<set-slug>"
#     make export ARGS="<set-slug> --split-size 5"
export: $(VENV)/.ready
	@$(PY) scripts/export_set.py $(ARGS)

# Ein Set als Anki-Deck (.apkg) exportieren, z. B.:
#     make export-anki ARGS="<set-slug>"
#     make export-anki ARGS="<set-slug> --lang en --out /tmp/deck.apkg"
export-anki: $(VENV)/.ready
	@$(PY) scripts/export_anki.py $(ARGS)

audit: $(VENV)/.ready
	@$(PY) scripts/audit_content.py

clean:
	rm -rf $(VENV)

stable-ids: $(ENGINE_STAMP) ## Stabilitäts- und Abdeckungs-Gate (beide mitgeliefert)
	npx --no-install learn-content-engine check-stable-ids --base origin/main
	npx --no-install learn-content-engine check-stable-id-coverage
