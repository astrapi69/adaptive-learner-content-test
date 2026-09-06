# generated/: Staging-Bereich für KI-Entwürfe

`scripts/generate_exercises.py` schreibt jede generierte Lektion HIERHER,
niemals direkt in einen ausgelieferten `sets/`-Baum. Das ist die
mechanische Form von "erst Entwurf, dann validieren": Ein KI-Entwurf ist
so lange nur ein Entwurf, bis ein Mensch ihn gesichtet hat.

Ablauf:

1. Generieren: `python3 scripts/generate_exercises.py --topic ... ` legt
   `generated/<set-id>/<lektion>.json` an (nur nachdem der Entwurf den
   Struktur- + Qualitäts-Gate von `validate_content.py` bestanden hat).
2. Sichten: Lies die Lektion. Für eine Sprache, die du nicht muttersprachlich
   sprichst, hol ein Muttersprachler-Review ein: kein Validator erkennt
   eine unnatürliche Formulierung oder eine falsche Umschrift.
3. Einsortieren: Verschiebe die Datei in dein Set unter
   `sets/<quellsprache>/<set-id>/lessons/`, trage sie im Set-Manifest ein
   und lass `python3 scripts/validate_content.py` (plus die Engine-CI) noch
   einmal über den vollständigen Baum laufen.

Die generierten JSON-Dateien sind in `.gitignore` ausgeschlossen (nur
diese README bleibt versioniert), damit ungesichtete Entwürfe nicht aus
Versehen committet werden.
