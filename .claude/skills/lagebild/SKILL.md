---
name: lagebild
description: Lagebild seit dem letzten Blick - neue/geaenderte Intern-Issues, gemergte und offene PRs, Review-Anfragen, Aufraeumbedarf, Vorschlag fuer den naechsten Schritt. Use when jemand nach Updates, Neuigkeiten, gemergten PRs oder "was machen wir als naechstes?" fragt.
---

# Lagebild

`R=davidgoebel75/callers-caddy-intern`, `C=davidgoebel75/callers-caddy`. Nur lesen und berichten; geaendert wird erst auf Wort des Nutzers. Einzige Ausnahme: Schritt 3, wenn er eingeschaltet ist.

## 0. Wer schaut

```bash
gh api user --jq .login                                   # ICH
gh repo view C --json viewerPermission --jq .viewerPermission
```

`ICH` = eigener Login. **Maintainer** = `viewerPermission` ist `ADMIN` oder `MAINTAIN`; sonst **Mitwirkender**. "Andere" = jeder Login ausser `ICH`.

Persoenliche Einstellungen stehen, falls vorhanden, in `CLAUDE.local.md` unter `## Lagebild`:
- `auto-merge: an` schaltet Schritt 3 ein (Standard: aus).
- Weitere Abweichungen dort gehen diesem Skill vor.

## 1. Stichtag

Datei `STANDDATEI` = `$(git rev-parse --git-common-dir)/lagebild_stand` (liegt im Git-Verzeichnis, geht nie in einen Commit, gilt fuer alle Worktrees). Sie enthaelt den Zeitpunkt des letzten Lagebilds (ISO, UTC). Fehlt sie: Stichtag = vor 7 Tagen. `STAND` = dieser Zeitpunkt, `SEIT` = Datum daraus (`YYYY-MM-DD`).

## 2. Einsammeln

```bash
git fetch origin --prune
gh pr list --repo C --state merged --search "merged:>=SEIT" --json number,title,author,mergedAt,headRefName
gh pr list --repo C --state open --json number,title,author,reviewDecision,reviewRequests,updatedAt,headRefName,baseRefName,isDraft,mergeable
gh issue list --repo R --state all --search "updated:>=SEIT" --limit 50 --json number,title,state,labels,assignees,milestone,updatedAt
gh api repos/R/milestones --jq '.[] | "\(.title) open=\(.open_issues) closed=\(.closed_issues)"'
```

**Aktueller Milestone** `MS` = der offene Milestone `Release X.Y` mit der kleinsten Versionsnummer, der noch offene Issues hat (`Release offen` = ungeplant, nie `MS`). Dessen offene Issues holen, sie sind der Vorrat fuer den Vorschlag:
```bash
gh issue list --repo R --milestone "MS" --state open --json number,title,labels,assignees
```

- Jedes geaenderte Issue lesen, nur das Neue seit `STAND` (voller ISO-Zeitpunkt). Body nur bei Issues, die nach dem Stichtag angelegt wurden, sonst nur die neuen Kommentare. Alte Bodies sind schon bekannt und kosten bis zu 40k Zeichen pro Lagebild.
  ```bash
  gh issue view NR --repo R --json title,createdAt,body,comments --jq '.title, (if .createdAt >= "STAND" then .body else "(Body bekannt)" end), (.comments[] | select(.createdAt >= "STAND") | "-- \(.author.login) \(.createdAt)\n\(.body)")'
  ```
  (`--comments` ohne Terminal verschluckt den Body.) Gesucht: Fragen an `ICH`, Entscheidungen anderer, neue Querverweise, Labelwechsel (`blocked`). Einen alten Body erst nachlesen, wenn ein neuer Kommentar ohne ihn unverstaendlich bleibt.
- Offene PRs von `ICH`: `gh pr view NR --repo C --json reviews,comments` — Reviews oder Rueckfragen anderer?
- PRs anderer mit Review-Request an `ICH`: vormerken, nicht selbst reviewen.

**Fertig:** jeder Eintrag aus den drei Listen ist gelesen und einer Rubrik aus Schritt 5 zugeordnet oder als belanglos verworfen.

## 3. Freigegebene eigene PRs mergen (nur mit `auto-merge: an`)

Ausgeschaltet: Kandidaten nur unter "Wartet auf mich" melden ("freigegeben, bereit zum Mergen").

Kandidat = offener PR von `ICH` mit `reviewDecision == APPROVED`. Mergen nur, wenn **alles** zutrifft, sonst nach "Wartet auf mich" mit Grund:

- kein Draft, `mergeable == MERGEABLE` (kein Konflikt);
- kein Review `CHANGES_REQUESTED` und kein Kommentar/Review-Text eines anderen **nach** dem letzten `APPROVED`, der eine Aenderung oder Frage enthaelt (aus Schritt 2; im Zweifel nicht mergen, sondern fragen);
- Checks nicht rot: `gh pr checks NR --repo C` (keine Checks = ok).

Reihenfolge und Ablauf je PR:

1. **Gestapelte PRs:** zuerst die Basis, also der PR mit `baseRefName == develop` vor dem PR, der auf dessen Branch aufsetzt. Vor jedem Merge `gh pr list --repo C --base <headRefName>`; einen Folge-PR erst mit `gh pr edit FOLGE --repo C --base develop` umstellen. Grund: `--delete-branch` per gh loescht die Basis, und GitHub **schliesst** den Folge-PR (nur das Loeschen in der Weboberflaeche stellt um). Ist es doch passiert: Branch aus dem Head-SHA des gemergten PRs wiederherstellen, `gh pr reopen FOLGE`, Basis umstellen, Hilfsbranch loeschen. PR mit anderer Basis als `develop` nie direkt mergen.
2. `gh pr merge NR --repo C --merge --delete-branch` (Merge-Commit, nie Squash/Rebase).
3. Nach jedem Merge `mergeable` der restlichen Kandidaten neu holen; ein jetzt konfliktbehafteter PR wird nicht gemergt, sondern berichtet.

Die hier gemergten PRs zaehlen fuer Schritt 4 und den Bericht als gemergt (Rubrik **Von mir gemergt**).

## 4. Aufraeumbedarf

Fuer jeden gemergten PR (eigene, und andere, deren Branch lokal ausgecheckt war):
- Lokaler Branch mit Markierung `gone` (`git branch -vv`) oder Worktree (`git worktree list`) noch da? Loeschbar, wenn `git rev-list --count origin/develop..<branch>` 0 ist.
- Bei eigenen PRs: zugehoeriges Intern-Issue noch offen?
- Steht der aktuelle Branch auf einem gemergten PR?

**Remote-Branches** auf `origin`, die niemand mehr braucht (`develop` und `main` sind nie dabei):
```bash
git branch -r --merged origin/develop
git branch -r --no-merged origin/develop
gh pr list --repo C --state open --json headRefName,baseRefName
```
- **Loeschbar** = in `develop` gemergt und weder Head noch Basis eines offenen PRs (ein Folge-PR haengt sonst in der Luft, siehe Schritt 3).
- **Nachfragen** = nicht gemergt, kein offener PR, letzter Commit aelter als 30 Tage (`git log -1 --format=%cs origin/<branch>`). Kann verworfene Arbeit sein, kann ein Archiv sein.
- Mitwirkende melden nur eigene Branches (Autor des PRs zu diesem Branch: `gh pr list --repo C --state all --head <branch> --json author`); der Maintainer alle.
- Geloescht wird erst auf Wort des Nutzers, je Branch: `git push origin --delete <branch>`.

## 5. Bericht

Kurz, deutsch, in diesen Rubriken (leere weglassen):

- **Gemergt** — PR-Nummer, Titel, wer.
- **Von mir gemergt** — aus Schritt 3: PR-Nummer, Titel.
- **Wartet auf mich** — Fragen in Issues, Review-Kommentare, Review-Requests an `ICH`, freigegebene eigene PRs, die Schritt 3 nicht gemergt hat (mit Grund).
- **Neu im Backlog** — neue Issues mit Milestone (oder "ohne"), unassigned zuerst.
- **Aufraeumen** — aus Schritt 4: lokal, dann remote (loeschbar / nachfragen getrennt).
- **Vorschlag** — **ein** naechstes Issue mit Begruendung (blockiert etwas anderes, Bug vor Feature, schliesst an gerade Gemergtes an). Kopfzeile nennt `MS` mit Stand offen/geschlossen.
  - Nur Issues aus `MS`; ist dort nichts frei, das sagen und hoechstens ein Issue ohne Milestone vorschlagen, nie eins aus einem spaeteren Milestone.
  - Nur Issues, die `ICH` zugewiesen oder unassigned sind und kein `blocked` tragen; Issues anderer gehoeren denen.
  - Offene Review-Requests an `ICH` gehen dem Issue-Vorschlag vor.
  - Release: Fuer den **Maintainer** ein gueltiger Vorschlag, wenn der kleinste offene Milestone `Release X.Y` keine offenen Issues mehr hat (Ablauf: `docs/18_release.md`). Fuer **Mitwirkende** nie.

## 6. Stichtag fortschreiben

Aktuellen Zeitpunkt (`date -u +%Y-%m-%dT%H:%M:%SZ`) nach `STANDDATEI` schreiben.
