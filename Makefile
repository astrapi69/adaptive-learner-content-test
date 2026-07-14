# Makefile für das lokale Engine-Gate (dieselben Regeln wie die CI).
#
#     make lint            Installiert die gepinnte Engine (einmalig, lokal in
#                          node_modules/, per .gitignore ausgeschlossen) und
#                          lässt den Selbsttest plus den vollen Engine-Lauf
#                          über alle Lektionen und Manifeste laufen -
#                          dieselben Regel-IDs (E-CARD-REF & Co.) wie der
#                          CI-Workflow "Engine conformance"
#                          (.github/workflows/engine-validate.yml), nur VOR
#                          dem Push statt danach.
#     make lint-warnings   Optional: derselbe Engine-Lauf, zusätzlich mit den
#                          Warnungen (W-*) über alle Lektionen. Nutzt dieselbe
#                          Extension-Registry wie das Gate, ext: Lektionen
#                          werden also validiert statt abgewiesen. Warnungen
#                          brechen den Lauf nicht ab.
#
# Du brauchst Node.js (>= 20) und npm. Kein package.json nötig: die Engine
# wird mit --no-save an der in schema/engine-version.txt gepinnten Version
# installiert, exakt wie in der CI. Kein "make" auf deinem System? Dann
# führe die Befehle aus dem lint-Ziel von Hand aus, oder committe und
# lass die CI prüfen - sie prüft dasselbe.

ENGINE_PIN := $(shell cat schema/engine-version.txt)
ENGINE_STAMP := node_modules/.engine-$(ENGINE_PIN)

.PHONY: lint lint-warnings help

help:
	@echo "make lint            - Engine-Gate lokal (Selbsttest + alle Lektionen/Manifeste)"
	@echo "make lint-warnings   - derselbe Lauf, zusätzlich mit Warnungen (W-*)"

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

lint-warnings: $(ENGINE_STAMP)
	node scripts/validate_with_engine.mjs --warnings .
