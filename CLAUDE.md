# ll-rechnungserstellung – Hinweise für Claude

- Fachliche Wahrheit: `rules/rechnungsregeln.md` (immer komplett lesen, bevor eine Rechnung entsteht).
- Ablauf und Chat-Befehle: Skill `rechnung` (`.claude/skills/rechnung/SKILL.md`).
- Betriebsmodus in `config/betrieb.yaml` (`schatten` = n8n führend, nur Vergleich; `produktiv` = echter Lauf).
- Das Finanzsheet (Drive-ID in `config/betrieb.yaml`) wird nur gelesen, nie beschrieben.
- Nummern nur über `invoice/register.py` vergeben – in beiden Modi wie produktiv (sofort reservieren); jede Änderung am Register committen und pushen.
- Nie Mails senden – nur Gmail-Entwürfe. Nie bei Stopp-Befund rendern.
- Zahlungserinnerungen (Regel 15): jeder Lauf prüft überfällige Rechnungen; Entwurf nur nach Gmail-Prüfung, jede Aktion
  sofort in `register/zahlungserinnerungen.csv` protokollieren, committen, pushen.
- Arbeitsdaten (`data/`, `out/`) sind nicht Teil des Repos.
- Sprache gegenüber Josh: Deutsch, knapp, Befunde zuerst.
