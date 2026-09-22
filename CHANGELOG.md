# Callers Caddy — Changelog

Versionierung: `0.XX` = Prototyp-Phase (XX = Prototyp-Nummer).
Ab offiziellem Launch wird auf `2.0` umgestellt.
Die Versionen 1.xx bleiben für die alte Version offen

---

## (Unreleased — seit 0.159)

### Verbesserungen
- **In der Playlist lassen sich jetzt mehrere Lieder auf einmal markieren und gemeinsam verschieben oder löschen.** Mit Strg- bzw. Umschalt-Klick (oder durch Ziehen) wählt man einen Block aus; die Pfeil-Tasten ▲/▼ schieben die ganze Auswahl nach oben oder unten (auch nicht zusammenhängende Zeilen, die relative Reihenfolge bleibt erhalten), ✕ bzw. die Entf-Taste entfernen alle markierten Lieder in einem Rutsch, und per Ziehen lässt sich der Block an eine neue Stelle setzen. Ein Auswahl-Klick lädt dabei nicht mehr versehentlich jedes angetippte Lied als Audio. Das gilt gleichermaßen für die Playlist im Planner.
- **Der Button „+Notiz" überträgt jetzt alle markierten Lieder in der richtigen Reihenfolge.** Ohne Markierung wird wie bisher nachgefragt, ob die ganze Playlist übernommen werden soll; ist die Playlist leer, gibt es jetzt einen kurzen Hinweis statt eines stillen Abbruchs.
- **Das Umschalten zwischen Pattern (P) und Singing (S) in der Playlist behält die aktuelle Auswahl bei.** Bisher wurde beim Klick auf die P/S-Spalte die Markierung zurückgesetzt.

### Bugfixes
- **Beim Übertragen mehrerer Lieder in die Notizen stimmt die Reihenfolge jetzt – auch aus dem Abendplaner.** Aus dem Abendplaner kamen die Notizen bisher in umgekehrter Reihenfolge heraus; beide Wege (Playlist und Abendplaner) legen die Einträge nun von oben nach unten in der erwarteten Reihenfolge an. Das Übernehmen einer ganzen Liste ist zudem spürbar schneller, weil die Reihenfolge nur noch einmal am Ende gespeichert wird statt nach jedem einzelnen Lied.
- **Der Limit-Filter in den Sequenzen stuft Sequenzen wieder richtig ein.** Gehört ein Call zu mehreren Tanzprogrammen (z. B. „Dosado" in Basic und Mainstream 2026), zählte bisher ein zufällig herausgegriffenes – in der Praxis fast immer das höchste – Programm. Dadurch galt selbst eine reine Basic-Sequenz aus Dosado und Promenade als Mainstream-2026-Sequenz und verschwand aus dem Filter „bis Basic". Jetzt zählt immer das niedrigste Programm, in dem der Call gelehrt wird – dieselbe Regel, nach der auch die Programm-Auswahl und der Figuren-Dialog gehen. Beim ersten Start nach dem Update rechnet die App die Einstufung aller Sequenzen einmalig nach (bei 11.000 Sequenzen etwa eine Fünftelsekunde).
- **Im Call-Mapping stimmt die Spalte „Anzahl" wieder.** Ein Call-Text, dessen Figur zu mehreren Tanzprogrammen gehört, wurde je Programm einmal gezählt – die Häufigkeit war also verdoppelt (oder verdreifacht) und die Sortierung nach Häufigkeit entsprechend verschoben.

---

## 0.159 — Fenster andocken oder frei bewegen (2026-09-15)

### Verbesserungen
- **Jedes Fenster (Widget) lässt sich jetzt wahlweise andocken oder frei wie ein normales Fenster bewegen.** Bisher richteten sich die Fenster immer am Dock-Raster aus. Jetzt schaltet ein Rechtsklick auf die Titelzeile eines angedockten Fensters über „Frei bewegen" das Andocken ab – das Fenster schwebt dann frei und rastet nicht mehr ein. Zusätzlich hat im Ansicht-Menü jede Fensterzeile rechts ein Magnet-Symbol, das zwischen „angedockt" und „frei" umschaltet; darüber holt man ein frei schwebendes Fenster auch wieder zurück ins Raster. Die Farbe des Magneten zeigt den Zustand an: angedockt in der Akzentfarbe des Designs, frei dezent ausgegraut. Fenster, die bewusst immer frei sind (z. B. Abendplaner, Regeln, Pausen-Uhr), bleiben unverändert. Der gewählte Zustand wird je Fenster gemerkt und übersteht einen Neustart.

### Bugfixes
- **Im Call-Mapping öffnet die Taste F2 den Figuren-Auswahldialog jetzt unabhängig von der zuvor angeklickten Spalte.** Hatte man zuerst in die Call-Text-Spalte geklickt und danach F2 gedrückt, blieb der Tastendruck wirkungslos (nur der Doppelklick auf die Figur-Zelle funktionierte). F2 wirkt jetzt in jeder Spalte der Zeile.
- **Im Figuren-Auswahldialog erscheint jede Figur jetzt nur noch einmal.** Seit der Programm-Umstrukturierung stand ein Call, der zu mehreren Tanzprogrammen gehört (z. B. „Recycle" in Mainstream und Mainstream 2026), mehrfach in der Auswahlliste – je einmal pro Programm und mit angehängtem Programm-Namen. Für die Zuordnung ist das Programm unerheblich; die Liste zeigt jede Figur nun genau einmal, ohne Programm-Zusatz. Das galt sowohl im Call-Mapping als auch beim Doppelklick im Sequenz-Editor. Außerdem zeigt die Sequenz-Anzeige das Programm-Kürzel einer Figur jetzt stabil (immer das niedrigste Programm) statt wechselnd.

---

## 0.158 — Fokus-Rahmen, Medley-Auto-Sync & Fenster-Positionen (2026-09-14)

### Verbesserungen
- **Höhere Tanzprogramme haken die darunterliegenden jetzt automatisch mit an.** Wählte man bisher nur ein höheres Programm (z. B. „Plus 2026"), ohne das darunterliegende („Mainstream 2026"), blieb die Sequenzliste leer – es gibt schlicht keine Sequenz ohne die tieferen Calls. Jetzt genügt ein Klick auf das gewünschte Programm: Die tieferen Programme derselben Reihe werden automatisch mitgewählt (z. B. „Plus 2026" → auch „Mainstream 2026"; „A2" und höher greifen auf die 2026er-Programme zu). Die alten Programme (Basic, Mainstream, Plus, A1 ohne „2026") nutzen weiterhin ihre eigene Reihe inklusive der Basics. Nicht Benötigtes lässt sich jederzeit wieder abwählen.
- **Tastenbefehle mit Buchstaben funktionieren jetzt zuverlässig – auch wenn eine Liste, Tabelle oder das Lyrics-Fenster den Fokus hat.** Bisher wurde ein Buchstabe (z. B. „S") in solchen Fenstern für deren eigene Schnellsuche verbraucht, statt die zugewiesene Regel auszulösen. Jetzt löst ein belegter Buchstabe die Regel aus; nur echte Texteingabefelder (z. B. Notizen oder Suchfelder) haben weiterhin Vorrang. Die Erkennung ist zudem unabhängig von der Groß-/Kleinschreibung – „S" wirkt wie „s". Nicht belegte Tasten funktionieren in Listen/Tabellen weiterhin für die Schnellsuche.
- **In Textfeldern ist jetzt klar sichtbar, wo der Cursor steht – und Escape springt sofort zurück in den Tasten-Modus.** Bisher merkte man oft nicht, dass der Fokus noch in einem Eingabefeld hing, und tippte einen Tastenbefehl versehentlich ins Feld. Jetzt umrahmt ein farbiger, zum jeweiligen Design passender Rahmen das aktive Feld. Ein Druck auf Escape gibt den Fokus wieder frei, sodass belegte Buchstabentasten sofort wieder als Befehl wirken.
- **Bei Medley-Liedern mit vier getrennten „FIGURE"-Abschnitten erkennt die automatische Abschnitts-Erkennung jetzt jede Figur einzeln.** Bisher übernahm der erste Figuren-Block alle vier Figuren-Durchgänge – bei einem Medley mit unterschiedlichen Figuren wurde der zweite (und weitere) Text daher nie eingeblendet. Jetzt bekommt bei genau vier Figuren-Abschnitten jeder seinen eigenen Durchgang zugewiesen (1., 2., 3., 4. Figur der Reihe nach). Bei einem oder zwei Blöcken bleibt es bewusst beim bisherigen Verhalten (der erste deckt alle); abweichende Fälle lassen sich weiterhin von Hand anpassen.
- **Fenster (Widgets) lassen sich jetzt wahlweise zentriert oder an ihrer zuletzt genutzten Position öffnen.** Bisher öffneten die Fenster-Buttons (z. B. „Lyrics") ein loses Fenster immer mittig über dem Hauptfenster – eine vorher gewählte Position ging dabei verloren. Die Regelaktion „Widget öffnen" hat jetzt den Schalter „Open position" mit den Werten „centered" (Standard, wie bisher) und „last" (die zuletzt genutzte Position wird gemerkt und wiederhergestellt). Der On-Screen-Button eines Fensters übernimmt automatisch die Einstellung einer passenden „Widget öffnen"-Regel; ohne solche Regel öffnet der Button weiterhin zentriert.

### Bugfixes
- **Sync-Marken auf den letzten Zeilen langer Songs werden wieder angezeigt.** Bei Liedern mit vielen Sync-Punkten (z. B. mehrfach getanzten Figuren) fehlten die Zeit-Marken auf den hintersten Textzeilen, obwohl sie gesetzt waren (der Rechtsklick zeigte sie weiterhin). Sie werden jetzt korrekt an allen Zeilen eingeblendet.
- **Neu angelegte Tasten-Regeln reagieren sofort – ohne Neustart.** Wies man einer Regel eine bisher unbenutzte Taste zu (z. B. „S"), löste sie erst nach einem Neustart der App aus. Der Auslöser wird jetzt direkt beim Speichern aktiv.

---

## 0.157 — Neues Fenster „Pilot Square" & automatische Fensterlisten in Regeln (2026-09-12)

### Neu
- **Neues Fenster „Pilot Square" — Notizen zu den acht Tänzern im Square.** Über „Ansicht → Pilot Square" öffnet sich ein andockbares Feld, das die acht Tänzer räumlich als Square anordnet (Paar 1 unten, Paar 2 rechts, Paar 3 oben, Paar 4 links – jeweils Mann und Frau an ihrer realen Position). In jedes Feld lässt sich frei etwas eintragen: Name, Level oder Hinweise wie „braucht Blickkontakt". Die Schrift passt sich automatisch an die Textlänge an und füllt das Feld optimal aus; der Text steht immer mittig und gut lesbar. Über die Farbpalette in der Mitte kann man jedem Feld eine Farbe geben – erst das Feld anklicken, dann eine Farbe wählen (das erste Feld entfernt die Farbe wieder); die Textfarbe stellt sich automatisch kontrastreich ein. „Leeren" setzt alle Felder zurück, „Schließen" blendet das Fenster aus. Die Notizen gelten für die laufende Sitzung.

### Verbesserungen
- **Die Regel-Aktionen „Dock öffnen/schließen" und die Stream-Deck-Belegung listen jetzt automatisch alle Fenster.** Bisher war die Auswahl eine feste Liste, in der neuere Fenster fehlten. Jetzt erscheinen alle andockbaren Fenster automatisch – darunter „Pilot Square" sowie Notizen, Abendplaner, Sprungmarken und „To Call". Bestehende Regeln bleiben unverändert gültig.

### Bugfixes
- **Einzelne Buchstaben werden beim Tippen in mehrzeiligen Textfeldern nicht mehr als Tastenbefehl abgefangen.** Wer einen Buchstaben (z. B. „L") als Regel-Auslöser eingerichtet hatte, konnte diesen in manchen Textfeldern nicht eintippen – er löste stattdessen die Regel aus. Jetzt haben Texteingaben in solchen Feldern Vorrang.
- **Die Häkchen im Ansicht-Menü stimmen nach dem Start wieder mit den sichtbaren Fenstern überein.** Ein im Layout gespeichertes, sichtbares Fenster (z. B. der Loop Finder) wurde beim Start korrekt angezeigt, im Ansicht-Menü aber ohne Häkchen – das wirkte widersprüchlich. Die Häkchen werden jetzt nach dem Wiederherstellen des Layouts an die tatsächliche Sichtbarkeit angeglichen.

---

## 0.156 — Absturzbehebungen (2026-09-11)

### Bugfixes
- **Absturz beim Bedienen von Auswahllisten behoben.** In bestimmten Situationen (u. a. beim Aufklappen/Anklicken von Auswahlfeldern) konnte die App mit einem internen Typfehler komplett abstürzen. Der app-weite Tasten-/Maus-Filter fängt solche unerwarteten Fälle jetzt ab, statt sich zu beenden.
- **Absturz bei der Audio-Diagnose behoben.** Eine seltene Kollision zwischen dem Audio-Thread und der Diagnose-Anzeige konnte die App beenden. Die Diagnose arbeitet jetzt auf einer Kopie und lässt den Audio-Thread ungestört.

---

## 0.155 — Songdaten als JSON exportieren & behutsam importieren (2026-09-11)

### Verbesserungen
- **Songdaten als JSON exportieren und wieder einspielen.** In der Songliste gibt es jetzt „Exportieren…": schreibt die Datenbank-Daten aller Songs der aktuell gefilterten Liste in eine JSON-Datei. Vorher wählt man die Felder — die Liste umfasst alles aus Song-Info und den erweiterten Daten und wächst automatisch mit künftigen Feldern mit. Der Titel ist als Zuordnungsschlüssel immer dabei; kritische Felder (Dateiname, Pfade, Aufnahmedatum) und erweiterte Datenfelder sind vorsichtshalber abgewählt — wer sie will, hakt sie an. Derselbe Export steht zusätzlich im Tab „Potential → Daten-Export/-Import" bereit, dort über alle Songs.
- **Behutsamer Import unter „Potential → Daten-Import".** Spielt eine solche JSON wieder ein: aktualisiert nur bestehende Songs (legt nie neue an), Zuordnung über den Songnamen. Eine Vorschau zeigt jede Änderung „alt → neu" einzeln zum Anhaken — nichts wird still überschrieben. Nicht gefundene oder gleichnamige (mehrdeutige) Songs werden mit Namen ausgewiesen und übersprungen.
- **Umbenennen beim Re-Import auf derselben Installation.** Bearbeitet man eine hier exportierte JSON und spielt sie auf demselben Gerät wieder ein, lässt sich auch der Songname ändern — die Abspiel-Historie bleibt erhalten. Bei fremden Dateien (Caller-Austausch) bleibt der Name der Zuordnungsschlüssel.

---

## 0.154 — Neue Regel-Bedingung „Songlänge", breitere Auswahllisten & frei skalierbares Rules-Fenster (2026-09-10)

### Verbesserungen
- **Neue Regel-Bedingung „Song Length" — reagiert auf die Gesamtlänge des geladenen Songs.** In den Regeln lässt sich jetzt prüfen, ob ein Song **länger** oder **kürzer** als eine eingestellte Zeit ist (Eingabe als `mm:ss`, z. B. `3:00`). Damit kann man z. B. nur bei kurzen Pattern-Titeln automatisch einen Loop setzen lassen, bevor der Song gestartet wird, längere aber unangetastet lassen. Die Bedingung wählt man über ein Auswahlfeld „above/below"; ist gerade kein Song geladen, gilt sie als nicht erfüllt.
- **Auswahllisten (Comboboxen) klappen jetzt so breit auf wie ihr längster Eintrag.** Auf schmalen Laptop-Auflösungen quetschte das Layout die Auswahlfelder zusammen, sodass beim Aufklappen längere Einträge abgeschnitten und unlesbar waren. Die Aufklappliste öffnet sich nun immer so breit wie nötig (maximal bis zum Bildschirmrand) — das eigentliche Feld bleibt platzsparend. Gilt automatisch für alle Auswahlfelder im Programm.

### Bugfixes
- **Das freischwebende Regeln-Fenster lässt sich nicht mehr schmaler ziehen als sein Inhalt.** Zuletzt konnte man das Rules-Fenster so klein ziehen, dass Felder abgeschnitten wurden und ein horizontaler Scrollbalken erschien. Die sinnvolle Mindestgröße (700 × 400) ist jetzt wiederhergestellt, sodass der Inhalt immer vollständig sichtbar bleibt.

---

## 0.153 — Auto-Scroll startet zuverlässig & Schriftgröße bleibt beim Speichern erhalten (2026-09-09)

### Bugfixes
- **Der Auto-Scroll läuft jetzt schon beim Start eines Songs von selbst.** Bisher blieb der Lyric-Text nach dem Abspielen zunächst stehen, obwohl Auto-Scroll aktiv war — er lief erst los, wenn man am Zoom drehte oder Auto-Scroll kurz aus- und wieder einschaltete. Jetzt scrollt der Text ab dem ersten Moment korrekt mit. (Sehr kurze Texte, die komplett ins Fenster passen, scrollen wie bisher nicht.)
- **Beim Bearbeiten und Speichern von Lyrics wird die Schriftgröße nicht mehr versehentlich verändert.** Wer das Lyric-Fenster im Bearbeiten-Modus verkleinerte (wodurch die Anzeige die Schrift automatisch anpasst) und dann speicherte, hatte danach dauerhaft kleinere Buchstaben in der Datei. Die reine Anzeige-Anpassung landet jetzt nicht mehr in der gespeicherten Datei; die bewusst pro Wort gesetzten Größen bleiben erhalten.

---

## 0.152 — Live-Lautstärke bleibt erhalten, einheitlich grüne Aktiv-Schalter & flüssigerer Abendplaner (2026-09-09)

### Verbesserungen
- **Die Live-Lautstärke bleibt beim Songwechsel jetzt stehen.** Bisher sprang der Live-Regler bei jedem neuen Song zurück auf 100 %, sodass man ihn beim Aufbau der Playlist immer wieder nachregeln musste. Jetzt behält er den eingestellten Wert für die ganze Sitzung. Wer pro Song bewusst einen festen Pegel möchte, kann das über die neue Regel-Aktion „Set Live-Volume" einstellen (z. B. mit dem Auslöser „Song Changed") — Standard bleibt 100 %.
- **Aktive Umschalt-Schaltflächen sind jetzt einheitlich grün.** Schalter, die eine laufende Funktion anzeigen — Auto-Scroll, Auto-Größe, Auto-Breite und Dynamic Lyrics im Lyric-Fenster, Zufall (🎲) in der Sequenz-Ansicht und Shuffle im Abendplaner — leuchten im aktiven Zustand grün, genau wie der Sync-Schalter. Gleiche Bedeutung, gleiche Farbe, auf einen Blick erkennbar. Die Farbe kommt aus dem jeweiligen Design-Theme.
- **Der Abendplaner öffnet sich ohne kurzes leeres Fenster.** Er wird jetzt kurz nach dem Programmstart im Hintergrund vorbereitet, sodass beim ersten Öffnen sofort der fertige Inhalt erscheint statt für einen Moment ein leeres Fenster.

### Bugfixes
- **Die „Shuffle"-Auswahl in der Songliste lässt sich jetzt immer umschalten.** Bisher war sie bei bestimmten Sortierungen (z. B. alphabetisch oder rein zufällig) ausgegraut, was verwirrte. Jetzt ist sie immer bedienbar; sie wirkt weiterhin nur dort, wo ein Zufalls-Ausgleich bei Gleichstand sinnvoll ist (Empfehlung, Qualität, Einfügedatum), und bleibt in den anderen Sortierungen bewusst ohne Wirkung.

---

## 0.151 — Dynamic Lyrics schützt den Gesangstext am Figuren-Ende (mit verschiebbarer Schnittmarke) & Suchfeld im Lokationsdialog (2026-09-08)

### Verbesserungen
- **Beim automatischen Ersetzen des Figurentextes durch die aktuelle Sequenz (Dynamic Lyrics) bleibt der angehängte Gesangstext am Figuren-Ende jetzt erhalten.** In vielen Cuesheets endet ein Figuren-Block nicht mit dem letzten Tanz-Call, sondern mit ein bis zwei Zeilen reinem Gesangstext, die laufen, während die Tänzer nach Hause promenieren. Bisher wurden auch diese Zeilen durch die Sequenz-Calls überschrieben; jetzt endet die Ersetzung an der letzten Heim-Promenade-Zeile, und der Schluss-Gesang bleibt sichtbar stehen. Das Timing bleibt unverändert — die Anzeige ruht während des Schluss-Gesangs weiter an ihrer Stelle. Die Erkennung wurde an allen echten Lyrics geprüft und trifft in rund 96 % der Figuren-Blöcke die richtige Stelle.
- **Neue verschiebbare Schnittmarke im Abschnitts-Streifen (Sync-Modus).** Ein breiter Trenner im Figuren-Balken zeigt jetzt, wo die Tanz-Calls enden und der Gesangstext beginnt. Die Marke wird automatisch gesetzt; liegt sie einmal nicht richtig, lässt sie sich einfach per Ziehen nach oben oder unten verschieben. Die Position wird pro Song gespeichert und steuert direkt, bis wohin Dynamic Lyrics ersetzt.
- **Der Lokationsdialog hat jetzt ein Suchfeld mit Löschen-Schaltfläche.** Damit lassen sich Einträge schnell filtern; ein Klick auf das X leert die Suche wieder.

---

## 0.150 — Text lässt sich während der Wiedergabe von Hand scrollen (2026-09-08)

### Bugfixes
- **Der Lyric-Text lässt sich jetzt auch während der Wiedergabe von Hand scrollen.** Bisher zog der Auto-Scroll die Anzeige bei jedem Takt sofort wieder an die aktuelle Song-Position zurück — man kam damit nicht an eine andere Textzeile, um dort etwa einen Sync-Punkt zu setzen. Sobald man jetzt von Hand scrollt (Mausrad oder Scrollbalken), pausiert der Auto-Scroll für einige Sekunden und läuft danach von selbst wieder an. Wer länger frei blättern möchte, kann den Auto-Scroll weiterhin über die Schaltfläche in der Werkzeugleiste ganz abschalten.

---

## 0.149 — Deutlich schnellerer Programmstart, zuverlässiges Abspielen während Hintergrund-Analysen & aufgeräumte Beat-Snap-Liste (2026-09-07)

### Performance
- **Deutlich schnellerer Programmstart.** Die BPM-Analyse-Bibliothek (mit ihrer umfangreichen Rechen-Grundlage) wurde bisher schon beim Programmstart komplett geladen — obwohl sie direkt nach dem Start praktisch nie gebraucht wird. Sie wird jetzt erst dann geladen, wenn tatsächlich eine BPM-Messung startet (Button in den Song-Infos oder per Regel-Aktion). Die reine Modul-Ladephase beim Start sinkt dadurch von ~1,8 s auf ~0,6 s (rund −1,2 s); der erste BPM-Vorgang danach dauert einmalig einen Sekundenbruchteil länger, was im Live-Betrieb nicht auffällt.
- **Fenster erscheint spürbar früher.** Beim Start musste das Programm bisher erst berechnen, welche Sequenzen zum aktuellen Tanzprogramm passen (ein Durchlauf über zehntausende Figuren-Einträge) — das blockierte das Erscheinen des Fensters um ~0,3 s. Dieses Ergebnis wird jetzt dauerhaft zwischengespeichert und nur noch neu berechnet, wenn sich tatsächlich etwas an den Calls, Bändern, Mappings oder Sequenzen ändert; außerdem lädt die Sequenzliste erst, nachdem das Fenster sichtbar ist. Die Zeit bis zum sichtbaren Fenster sinkt dadurch nochmals um ~0,4 s.

### Bugfixes
- **Musik lässt sich jetzt auch dann sofort abspielen, wenn im Hintergrund gerade eine Sammel-Analyse läuft** (z. B. BPM ermitteln, Beat-Snap, „Verschönern"). Bisher konnte eine solche Hintergrund-Aufgabe die Datenbank kurz sperren; ein Klick auf Play brach dann mit einer Fehlermeldung ab, statt den Song zu starten. Jetzt hat das Abspielen Vorrang: Der Song startet in jedem Fall, das Mitschreiben der Abspiel-Historie wird bei einer belegten Datenbank stillschweigend übersprungen. Zusätzlich warten die Analysen bei kurzzeitiger Sperre aufeinander, statt einzelne Songs zu überspringen.
- **Songs, deren Loop sich nicht sinnvoll auf den Beat legen lässt, tauchen im Beat-Snap-Bereich nicht mehr endlos wieder auf.** Konnte die automatische Beat-Snap-Optimierung keinen Versatz bestimmen — etwa weil die Datei kein normales Audioformat ist, das Signal zu unklar ist oder der Loop bereits exakt auf dem Beat liegt —, blieb der Song in der Liste und wurde bei jedem Durchlauf erneut vorgeschlagen. Solche Songs erhalten jetzt das Genre-Kennzeichen „CHECK: BEATSNAP" und fallen aus der Vorschlagsliste; über dieses Genre lassen sie sich in der Songliste gezielt heraussuchen und bei Bedarf von Hand prüfen. Snappt man einen davon manuell, wird das Kennzeichen automatisch wieder entfernt.
- **Nicht abspielbare Dateien (z. B. MIDI) erzeugen keine irritierende Fehlermeldung mehr.** Lag eine solche Datei in einer Liste (etwa beim automatischen Weiterschalten), tauchte im Protokoll ein langer technischer Fehlerblock auf. Jetzt wird das Format ruhig als „nicht abspielbar" vermerkt und übersprungen; für echte, unerwartete Ladefehler (z. B. eine beschädigte MP3) bleibt die deutliche Warnung erhalten.

### Technische Notiz
- **Großer interner Umbau der Code-Struktur (unsichtbar für den Betrieb, Grundlage für die Zukunft).** Die über die Jahre auf ~29.000 Zeilen gewachsene zentrale Programmdatei wurde in zehn thematische Module aufgeteilt (Player, Songdaten/Liste, Playlist, Sequenzen, Song-Pool, Loop-Finder, Pause/Foto, Reports, Dialoge, Lyrics) — die zentrale Datei schrumpft dadurch auf ~7.300 Zeilen. Das macht künftige Änderungen sicherer und Fehlersuche schneller, ändert aber nichts am Verhalten des Programms. Begleitend wurden nicht mehr genutzter Code und überflüssige Verweise entfernt. Sämtliche Bereiche wurden nach dem Umbau geprüft.

---

## 0.148 — Schnellerer Abbruch beim versehentlichen Zweitstart, „Load Song" gleicht den Songlisten-Filter an & inaktive Regeln verschwinden aus dem Stream Deck (2026-09-05)

### Performance & Start
- **Startet man Callers Caddy versehentlich ein zweites Mal (typischer Doppelklick, weil der Start etwas dauert), bricht die zweite Instanz jetzt deutlich schneller ab.** Bisher lud der zweite Start fast das komplette Programm — inklusive der schweren Audio-/Analyse-Bausteine — bevor er „läuft bereits" meldete; in dieser Zeit bremste er ausgerechnet den ersten, sichtbaren Start aus. Die Mehrfachstart-Sperre greift nun ganz am Anfang: Die zweite Instanz erkennt in Sekundenbruchteilen, dass das Programm schon läuft, zeigt den Hinweis und beendet sich, ohne die erste zu behindern. Die bewährte Erkennung verwaister Sperren nach einem Absturz bleibt vollständig erhalten.

### Verbesserungen
- **Die Regel-Aktion „Load Song" schaltet den Songlisten-Filter jetzt automatisch auf den gewählten Songtyp um.** Stellt man in der Aktion z. B. „Patter" ein, während die Songliste noch auf „Singing" gefiltert war, wurde der vorgeschlagene Song zwar korrekt in den Player geladen, in der Liste aber nicht markiert — der Filter blendete ihn aus, was verwirrend wirkte. Jetzt setzt die Aktion den Listenfilter passend (Singing → Singing, Patter → Patter), sodass der geladene Song sichtbar und selektiert ist. Steht der Filter bereits richtig, passiert nichts (kein überflüssiger Neuaufbau der Liste).

### Bugfixes
- **Der „Aktiv"-Schalter einer Regel wirkt jetzt wieder auf das Stream Deck.** Zuletzt blieb der Stream-Deck-Button einer Regel auch dann bestehen und auslösbar, wenn die Regel deaktiviert war — nur der automatische Auslöser hielt sich an den Schalter. Jetzt gilt der Schalter durchgängig: Wird eine Regel deaktiviert, verschwindet ihr Button sofort aus dem Stream Deck, und ein (versehentlicher) Aufruf einer inaktiven Regel führt keine Aktionen mehr aus. Beim Wieder-Aktivieren taucht der Button unmittelbar wieder auf — ohne Neustart.

### Technische Notiz
- **Erweiterte Start-Zeitmessung** (nur bei aktivem Performance-Log, `debug/performance_logging=true`): Das Perf-Log erfasst jetzt auch die bisher unsichtbaren Phasen *vor* dem Programmfenster — Bootloader/Python-Start und die Import-Phase — sowie die Gesamtzeit vom Prozessstart bis zum sichtbaren Fenster. Grundlage für die weitere Start-Optimierung; ohne Auswirkung für Endnutzer.

---

## 0.147 — Robusterer Sequenz-Import, klareres Evening-Planner-Design & Floating-Fenster merken sich Größe und Position (2026-09-03)

### Sequenz-Import
- **Sequenz-Dateien mit doppelten Zeilenumbrüchen (z. B. SqView-Exporte) werden jetzt korrekt eingelesen.** Solche Dateien schreiben pro Zeile ein zusätzliches Wagenrücklauf-Zeichen; der Freitext-Import erkannte dadurch jede einzelne Call-Zeile als eigene Sequenz. Jetzt werden die Zeilenenden vor dem Einlesen sauber normalisiert — mehrere Leerzeilen trennen die Sequenzen, einzelne Umbrüche gehören zur laufenden Sequenz. Normale Dateien bleiben unverändert.
- **Head-/Side-Kurzschreibweisen werden beim Zuordnen der Calls erkannt.** „HDS", „HD", „SDS" und „SD" gelten jetzt wie „Heads"/„Sides" als Rollen-Präfix und werden beim Abgleich mit der Call-Datenbank korrekt abgetrennt.
- **Neue Auswahl „Schreibweise" im Import-Dialog.** Wählbar: *Wie im Text* (unverändert), *ALLES GROSSBUCHSTABEN* oder *Erster Buchstabe je Wort groß*. Damit lassen sich in Großbuchstaben vorliegende Quelldateien direkt in eine schön lesbare Schreibweise überführen. Die Groß-Kleinschreibung greift auch nach Trennzeichen wie „-", „(", „)" — nur nach Ziffern bleibt der Buchstabe klein (aus „1ST" wird „1st", nicht „1St").

### Verbesserungen
- **Die Tabelle im Evening Planner ist deutlich lesbarer.** Bisher waren alle Zellen flächig in den ERR-Stufenfarben hinterlegt — in dunklen wie hellen Themes ließen sich die Titel dadurch kaum lesen. Jetzt folgt die Tabelle dem normalen Theme (abwechselnde Zeilenfarben, Standard-Textfarbe); die ERR-Farbe steckt nur noch dort, wo sie Bedeutung trägt: in den beiden ERR-Spalten, als satter Badge mit weißer Zahl. Noch nicht bestätigte Songvorschläge werden nur noch kursiv gekennzeichnet statt grau — dadurch bleiben sie in beiden Themes gut lesbar.
- **Auch das Kandidaten-Fenster (Klick auf einen Slot) zeigt den ERR-Wert jetzt als satten Badge** statt als farbigen Text — einheitlich mit der Haupttabelle.
- **Die Balken im Spannungsbogen-Diagramm sind jetzt durchgängig in Vollfarbe** und passen damit zu den ERR-Badges der Tabelle.

### Bugfixes
- **Frei schwebende Fenster merken sich jetzt ihre Größe und Position über einen Neustart hinweg.** Betroffen waren u. a. Evening Planner, Photo, Reports, Statistik und der Zauberstab-Planner: Nach dem Beenden und Neustart öffneten sie wieder in Standardgröße an Standardposition. Ursache war, dass ein geschlossenes schwebendes Fenster seine Geometrie beim Speichern verlor. Die Fenstergröße/-position wird nun zuverlässig gesichert und beim Öffnen wiederhergestellt.
- **„Zu Notizen hinzufügen" im Evening Planner ohne gewählte Lokation zeigte den Hinweis „Bitte zuerst eine Lokation wählen" einmal pro Lied** (bei vielen Tipps wie eine Endlosschleife). Der Hinweis erscheint jetzt genau einmal, danach bricht die Aktion sauber ab.

---

## 0.146 — Songs per Drag & Drop auf den NEU-Button importieren (2026-09-03)

### Neue Features
- **MP3-Dateien, ZIP-Pakete und ganze Ordner lassen sich jetzt direkt auf den NEU-Button ziehen — der Drop startet denselben Import wie ein Klick.** Beim Ziehen zeigt der Button einen gestrichelten Rahmen als Ablegehinweis. Da die Quelle durch den Drop bereits feststeht, entfällt gegenüber dem Klick nur die Datei-/Ordnerauswahl; die gewohnten Nachfragen (Kopieren oder am Ort belassen, Songtyp, bei Ordnern die Genre-Zuweisung) bleiben unverändert.
- **Ordner-Importe finden jetzt auch enthaltene ZIP-Pakete.** Zieht man einen Ordner auf den NEU-Button (oder wählt ihn über „Ordner importieren"), durchsucht Callers Caddy ihn rekursiv nach Audiodateien UND ZIP-Label-Paketen. Bisher wurden ZIPs in einem Ordner ignoriert.
- **Bei gemischtem Inhalt fragt eine transparente Rückfrage nach.** Enthält ein Drop bzw. Ordner sowohl MP3-/Audiodateien als auch ZIP-Pakete, erscheint ein Dialog mit der genauen Anzahl beider Typen und den Optionen **Nur MP3 / Nur ZIPs / Beides**. Danach läuft alles im gewohnten Import-Prozess weiter (ZIPs ins Vorschau-Fenster, Audio mit Kopieren/Typ/Genre).

---

## 0.145 — Aufgeräumtes Songlisten-Highlight & Countdown verschwindet beim Liedstop (2026-09-02)

### Verbesserungen
- **Die Hervorhebung in der Songliste nutzt jetzt die native Zeilen-Auswahl von Qt — genau eine Zeile ist markiert, und sie wandert beim Wechsel sauber in einem Schritt.** Zuvor lag ein eigenes Highlight zusätzlich über der Auswahl. Beide schalteten nicht gleichzeitig um, wodurch beim Songwechsel kurz zwei Farben zu sehen waren und das alte Lied noch einmal aufblaute, bevor die Markierung weitersprang. Das zweite System ist entfallen — weniger Code, ein durchgängiges Verhalten.
- **Beim Überfahren mit der Maus wird die markierte Zeile nicht mehr grau überdeckt.** Eine Hover-Regel im Design färbte die Zelle unter dem Mauszeiger um, sodass es wirkte, als sei nur eine der beiden Spalten (Titel/Gespielt) hervorgehoben. Die Regel wurde entfernt; die Markierung bleibt beim Hovern vollständig erhalten.

### Bugfixes
- **Der Einzähl-Countdown verschwindet jetzt zuverlässig beim Stoppen oder Wechseln des Liedes.** Das Countdown-Overlay liegt bewusst über allen Fenstern; bei aktivem „Feedback am Liedende"-Dialog blieb die Countdown-Zahl daher sichtbar vor dem Dialog stehen, wenn man mitten im Einzählen das Lied wechselte. Der Countdown wird nun direkt beim Liedstop ausgeblendet — noch bevor der Feedback-Dialog erscheint.

---

## 0.144 — Doppelklick startet den Song & durchgängiges Now-Playing-Highlight (2026-09-02)

### Neue Features
- **Doppelklick in der Songliste startet den Song sofort.** Ein Doppelklick auf einen Song in der Songliste lädt ihn nicht nur, sondern **spielt ihn direkt ab** — ein Schritt weniger im Live-Betrieb. Der Einfachklick bleibt wie gewohnt: Er selektiert und lädt den Song, ohne die Wiedergabe zu starten.

### Verbesserungen
- **Der aktuell spielende Song wird durchgängig hervorgehoben — in Songliste UND Playlist.** Bisher war die Markierung uneinheitlich (mal sichtbar, mal nicht), weil sie an der Zeilen-Auswahl hing. Jetzt folgt ein eigenes Hintergrund-Highlight dem **tatsächlich laufenden Song** — egal, ob er per Klick, Doppelklick, aus der Playlist oder über eine Regel gestartet wurde. Das Highlight bleibt auch nach Filtern/Sortieren der Songliste an der richtigen Zeile.

---

## 0.143 — Neue Regel-Aktion „Create Jump Marker" & Fixes für den Neuaufbau aus dem Quellcode (2026-09-02)

### Neue Features
- **Neue Regel-Aktion „Create Jump Marker".** Setzt per Regel bzw. Stream-Deck-/Tastenknopf eine eigene Sprungmarke an der aktuellen Abspielposition des laufenden Liedes. Anders als der manuelle „Marker setzen"-Knopf fragt diese Aktion **nicht** nach einer Beschriftung, sondern nimmt automatisch die aktuelle Position als **mm:ss** als Beschriftung — ideal, um während des Callens im Vorbeigehen (z. B. per Fernbedienungs- oder Stream-Deck-Taste) eine Stelle zu markieren, ohne den Ablauf zu unterbrechen. Die Aktion wird nur bei **laufender Wiedergabe** ausgeführt; liegt bereits eine Marke sehr nah (unter 1 Sekunde) an der Position, wird keine zweite gesetzt. Zu finden im Rule-Editor in der Gruppe „Transport".

### Bugfixes
- **Erster Start gegen eine leere Datenbank brach ab (`no such column: origin`).** Die Spalte `origin` der Tabelle `dance_programs` stand nur als nachträgliche Migration (`ALTER TABLE`), nicht im `CREATE TABLE`. Da beim Erststart die Migration vor dem Anlegen der Tabelle läuft, lief der ALTER ins Leere (Fehler wird verschluckt) und die Tabelle wurde ohne `origin` angelegt — worauf das Einspielen der Referenzdaten (`reseed_reference_data`) abstürzte. Die Spalte steht jetzt zusätzlich im `CREATE TABLE`; die Migration bleibt für bestehende Datenbanken erhalten. Im ausgelieferten Setup war der Fehler unsichtbar, weil dort die vorbereitete Datenbank mitkommt — er traf nur Neuaufbauten aus dem Quellcode. (Dank an Thomas Franzek für Analyse und Patch.)
- **`pip install -r installer/requirements.txt` schlug fehl.** Der Versions-Pin `access-parser>=0.4` verwies auf eine nicht existierende Version — auf PyPI gibt es die Bibliothek nur in der `0.0.x`-Reihe. Auf `access-parser>=0.0.4` korrigiert (dieselbe gemeinte Untergrenze). Betraf jede Frischinstallation der Abhängigkeiten. (Dank an Thomas Franzek.)

---

## 0.142 — Sprungmarken & To-Call-Liste, relative Positions-Regelaktion, Genre-Löschfix (2026-09-01)

### Neue Features
- **Eigene Sprungmarken mit Beschriftung (BL-185).** Besonders für Caller, die mit Aufnahmen (Recordings) arbeiten: An beliebiger Stelle im Song lassen sich jetzt frei benannte Sprungmarken setzen — z. B. „Beginn 2. Abschnitt" oder „Applaus" — um eine Sequenz gezielt noch einmal anzuspielen. **Setzen:** Song im Player abspielen und im „New Songs"-Bereich auf **„Marker setzen"** klicken (der Platz teilt sich jetzt mit „Beat Snap"); es folgt eine Abfrage der Beschriftung (vorbefüllt mit dem Zeitstempel). **Springen:** In „Song Data" erscheint zwischen „Loop Offset" und „Lyrics file" pro Marke ein Button mit der Beschriftung — ein Klick springt dorthin. **Verwalten:** Rechtsklick auf einen Marker-Button (Beschriftung/Zeit bearbeiten, löschen) oder im Dialog „Erweiterte Daten" im neuen Reiter „Marker". Die Marken liegen platzsparend in den erweiterten Song-Daten (keine leeren Datenbankfelder für Caller, die das nicht nutzen) und sind an die Original-Zeit gebunden, also tempo-/Pitch-unabhängig. Beliebig viele Marken pro Song möglich.
- **Neues Fenster „To Call" — Calls über den Abend abhaken (BL-199).** Viele Caller wollen im Verlauf eines Abends jeden Call eines Programms mindestens einmal einsetzen. Das neue andockbare Fenster zeigt die gewünschten Calls als Kacheln, gleichmäßig übers Feld verteilt (mit dynamischem Umbruch wie beim Sprungmarken-Fenster). Anfangs sind alle kontrastreich; **ein Klick markiert einen Call als erledigt** — die Kachel wechselt Hintergrund und Text auf gedämpfte Theme-Farben (weiterhin gut lesbar) und **wandert ans Ende nach unten**, wo sich die erledigten Calls in halber Größe sammeln. Dadurch rücken die offenen Calls oben nach und bekommen mehr Platz — je weiter der Abend, desto großzügiger stehen die noch offenen Figuren da. Die Schriftgröße passt sich pro Kachel automatisch an (kurze Namen groß, lange kleiner statt abgeschnitten). Nochmal klicken macht „erledigt" rückgängig. **Füllen:** Über den Knopf „Füllen" in der Kopfzeile öffnet sich ein Dialog mit dem aktuellen Tanzprogramm und allen seinen Calls (alle vorausgewählt), samt „Alle an/aus". **Vorab ablegen:** Derselbe Dialog bietet „Zu Notizen hinzufügen" — die Auswahl landet als kompakter Eintrag in den Notizen (bei vollständiger Auswahl nur das Programm; bei kleiner Änderung nur die Ausnahmen; sonst die Call-Liste). Beim Abhaken dieser Notiz wird das To-Call-Fenster automatisch damit gefüllt. So kann man sich die Call-Listen für den Abend vorbereiten. Der Abhak-Status gilt für die laufende Sitzung.
- **Neues Fenster „Sprungmarken".** Ein zusätzliches, andockbares Widget (über Menü „Ansicht" einblendbar) zeigt alle Sprungziele des aktuellen Songs als große Buttons: immer **Start · Loop-Start · Loop-Ende · Ende** und dahinter alle eigenen Marken (nach Zeit sortiert). Die Buttons verteilen sich gleichmäßig über die Fensterfläche und brechen automatisch um, wenn man das Fenster verkleinert — ähnlich dem Stream Deck. Ein Klick springt sofort an die Stelle. Ideal, um während des Callens ohne Umweg über die Song-Daten zwischen den wichtigen Stellen eines Recordings zu wechseln.
- **Neue Regel-Aktion „Shift Position (relative ±)".** Verschiebt die Wiedergabe relativ zur aktuellen Position — z. B. 20 Sekunden zurück. Der Wert wird im Format **mm:ss.cs mit optionalem Vorzeichen** eingegeben (`-0:20` = 20 s zurück, `0:05` = 5 s vor; Dezimaltrenner Punkt oder Komma). Damit lässt sich per Rule ein Button bauen, der beim Ausklingen eines Liedes noch einmal etwas Zeit zum sauberen Beenden schenkt. Die Zielposition wird automatisch auf Songanfang und -ende begrenzt; der Sprung nutzt denselben sanften Crossfade wie „Go To Position". Zu finden im Rule-Editor in der Gruppe „Transport" direkt unter „Go To Position".

### Bugfixes
- **Gelöschte Genres kamen beim Neustart zurück.** Löschte man ein Standard-Genre (z. B. „Blues"), war es zwar sofort weg, tauchte beim nächsten Programmstart aber wieder auf (mit 0 Songs). Ursache: Die Standard-Genre-Liste wurde bei jedem Start neu eingespielt. Jetzt werden die Standard-Genres nur noch **einmalig** bei der Erstbefüllung einer neuen Datenbank angelegt; danach bleiben vom Nutzer gelöschte Genres dauerhaft gelöscht. Ausnahme: Das System-Genre **„NEW"** (Marker für neu importierte Lieder) wird weiterhin immer sichergestellt und lässt sich nicht wegdeletieren.

---

## 0.141 — Call-Mapping-Komfort & -Tempo, Genre-Zuweisung beim Ordner-Import + neue Regel-Aktionen (2026-08-31)

### Neue Features
- **Call-Mapping: Beispiele zu einem Call-Text ansehen.** Im Fenster „Call-Mapping" (Zuordnung der Sequenz-Texte zu den offiziellen Figuren) ist manchmal unklar, was ein aus dem Zusammenhang gerissener Text wie „(Rotated)" eigentlich meint. Ein **Rechtsklick** auf einen Call-Text in der ersten Spalte bietet jetzt **„Beispiel zeigen"**: Es öffnet sich ein Betrachter mit allen Sequenzen, die diesen Text verwenden — zum Durchblättern, wobei der gesuchte Text in jeder Sequenz gelb hervorgehoben ist.
- **Neue Regel-Aktionen für Sequenz-Filter und Tanzprogramm.** Regeln können jetzt die Filter des Sequenzen-Fensters selbst setzen — passend z. B. zum Song-Typ oder Level: „Enthält" (bestimmte Figur), „Limit", „Nur", „Schwierigkeit" und „Tags". Dazu eine Aktion, die das/die aktive(n) **Tanzprogramm(e)** setzt (Mehrfachauswahl per Häkchenliste). So stellt sich beim Start eines Blocks alles von selbst richtig ein. Außerdem neu: **„Fokus Widget + Cursor"** — wie „Fokus Widget", bringt aber zusätzlich den Mauszeiger in die Mitte des Widgets (praktisch beim Lyrics-Fenster, um sofort weiterzuscrollen).
- **Genres direkt beim Ordner-Import vergeben (BL-184).** Wer einen ganzen Ordner importiert, dessen Lieder alle zusammengehören (z. B. „Recordings", „Elvis" oder lauter Singings), kann die passenden Genres jetzt sofort für alle importierten Lieder auf einmal setzen. Nach der Ordnerwahl erscheint ein neuer Dialog mit einer Häkchenliste aller vorhandenen Genres — die angehakten werden jedem Lied des Imports zugewiesen. Ganz unten lässt sich ein neues Genre anlegen; gibt es den Namen schon (unabhängig von Groß-/Kleinschreibung), wird kein Duplikat erzeugt, sondern das vorhandene Genre angehakt. Das automatische „NEW"-Genre ist in der Liste eingeblendet und vorausgewählt — man kann es hier abwählen, wenn die Lieder direkt als „eingearbeitet" gelten sollen. Der reine Datei-Import (einzelne Dateien) bleibt unverändert.

### Verbesserungen
- **Call-Mapping: komfortables Suchfeld für die Figur-Zuordnung.** Die Spalte „Figur (Teaching Order)" nutzt jetzt dieselbe Suche wie die Sequenz-Filter: Tippen findet Treffer auch in der Wortmitte (z. B. „thru" → „Pass Thru") und zeigt sie als Auswahl-Popup, und ein kleines „x" im Feld leert die Eingabe mit einem Klick.

### Performance
- **Call-Mapping „Auswahl bestätigen" von mehreren Sekunden auf Sekundenbruchteile.** Bisher wurde jede bestätigte Zeile einzeln in die Datenbank geschrieben und danach die komplette Liste (~10.000 Zeilen) neu aufgebaut — inklusive einer teuren Vorschlags-Berechnung über alle Zeilen. Jetzt werden alle bestätigten Zeilen in einem Rutsch gespeichert und nur die betroffenen Zeilen aus der Ansicht entfernt.
- **Call-Mapping-Fenster öffnet spürbar schneller.** Die Bedienoberfläche erscheint sofort, der sichtbare Teil der Liste ist gleich farbig, und die Vorschläge für die übrigen Zeilen werden im Hintergrund nachgezogen (beim erneuten Öffnen in derselben Sitzung sofort). Die Vorschlags-Berechnung selbst wurde zusätzlich beschleunigt.

---

## 0.140 — Bugfixes: Sequenz-Programmfilter & Suchfeld-Vervollständigung (2026-08-29)

### Bugfixes
- **Verstümmelte Auto-Vervollständigung in den Sequenz-Suchfeldern.** In den Feldern „Enthält" und „Limit" (sowie Tags) im Sequenzen-Fenster erzeugte die Eingabe eines Wortteils wie „Thru" während des Tippens Murks im Feld (z. B. „Thru thru"); erst mit Enter sprang es auf den richtigen Call („Pass Thru"). Ursache war eine unpassende Vervollständigungs-Betriebsart. Die Felder zeigen die Substring-Treffer jetzt sauber als Auswahl-Popup, und Enter übernimmt den markierten Call direkt.
- **Sequenzen verschwanden bei Programm-Auswahl.** Nach dem Import vieler eigener Sequenzen (z. B. aus SqView) zeigte die Sequenzliste **nur ohne** gewähltes Tanzprogramm etwas an — sobald ein Programm gewählt war, blieb sie leer. Ursache: Bei einem Massenimport wurden die Figuren der importierten Sequenzen nicht automatisch den bekannten Calls zugeordnet, und ohne diese Zuordnung konnte der Programm-Filter keine Sequenz als „tanzbar" erkennen. Behoben an drei Stellen: (1) beim ersten Start der neuen Version werden fehlende Zuordnungen für eindeutige Call-Texte automatisch und einmalig nachgetragen (bestehende Datenbanken heilen sich damit von selbst, ohne Zutun); (2) jeder künftige Massenimport legt die Zuordnungen direkt mit an; (3) der „Remapping"-Knopf im Sequenzen-Fenster ergänzt jetzt ebenfalls fehlende Zuordnungen, statt nur neu zu rechnen. Manuelle Zuordnungen bleiben dabei unangetastet.

---

## 0.139 — Tanzprogramm-Umstellung 2026 (MS50 / Plus / Advanced 1) (2026-08-27)

### Neue Features
- **Unterstützung für die neuen Tanzprogramme ab September 2026.** Das Mainstream-Programm wird auf 50 Calls gestrafft (MS50), und einige Figuren wandern aus Mainstream und Advanced 1 nach Plus. Callers Caddy kennt jetzt beide Welten gleichzeitig: die neuen Programme **Mainstream (2026)**, **Plus (2026)** und **Advanced 1 (2026)** neben den bisherigen Listen **Mainstream**, **Plus** und **Advanced 1**. So bleibt in der Übergangszeit beides tanzbar.
- **Mehrere Tanzprogramme je Lokation.** Eine Lokation kann jetzt mehrere Programme gleichzeitig führen — als Checkbox-Auswahl, sowohl in den Lokations-Einstellungen als auch über den Programm-Button im Player. Das ist nötig, weil eine Figur in mehreren Programmen stehen kann: Wer z. B. Plus tanzt, wählt **Plus (2026)** und **Mainstream (2026)** gemeinsam an (die tieferen Programme gehören bewusst dazu und werden nicht automatisch mitgezogen).
- **Sequenz-Filter nach Programm-Auswahl.** Die Sequenzliste zeigt genau die Sequenzen, deren Figuren alle in den gewählten Programmen der Lokation vorkommen — auch wenn eine Figur durch die Umstrukturierung in mehreren Programmen steht. Der „Nur"-Filter zeigt dabei die Sequenzen, die das **höchste** gewählte Programm wirklich brauchen (nicht schon mit einem tieferen Programm tanzbar sind).
- **Tanzprogramm-Auswahl ist jetzt unabhängig von der Lokation.** Die gewählten Tanzprogramme gelten für die ganze Sitzung und funktionieren auch **ohne** gewählte Lokation — der Programm-Button im Player öffnet die Auswahl direkt. Die zuletzt getroffene Wahl wird gemerkt und beim nächsten Start wieder geladen. Wählt man eine Lokation, übernimmt sie ihre eigenen Programme. Die aktuelle Auswahl steht zusätzlich in **Einstellungen → Sequenzen → Tanzprogramm(e)** und lässt sich dort über einen Button ändern. Für die Ziel-Songdauer gilt das höchste gewählte Programm.
- **Aufgeräumte Tanzprogramm-Liste inkl. Class-Programme.** Die Liste der Tanzprogramme ist jetzt klar nach Level gruppiert — innerhalb jeder Familie in der Reihenfolge *alt → (2026) → (Class)*. Die Class-Programme (Mainstream (Class), Plus (Class) …) bleiben erhalten und nutzen dieselben Figuren wie die jeweilige 2026er-Liste; die Ziel-Songdauer lässt sich pro Programm frei anpassen. Nebenbei behoben: Class-Programme konnten je nach Programmstart mal auftauchen und mal verschwinden.
- **Figuren-Filter im Sequenzen-Fenster folgen den gewählten Programmen.** Die Auswahllisten „Enthält" und „Limit" zeigen jetzt nur noch Figuren der aktuell gewählten Tanzprogramme — und jede Figur an der richtigen Stelle: eine nach Plus gewanderte Figur (z. B. Spin Chain Thru) erscheint bei MS 2026 + Plus 2026 unter Plus, nicht mehr unter Mainstream. Der „Limit"-Filter grenzt die Sequenzen jetzt sauber über die Programm-Bänder ein (statt über einen im Parallelbetrieb unzuverlässig gewordenen Einzelwert).

### Verbesserungen
- **Dynamic Lyrics mit Zufall: auch die erste Sequenz wird gemischt.** Ist im Sequenzen-Detail der Würfel-Modus (Shuffle) aktiv, startet Dynamic Lyrics jetzt schon mit einer zufälligen Sequenz — statt immer mit der ersten der festen Reihenfolge. Das „schon gehabt"-Gedächtnis der Sitzung wird dabei fortgeführt: bereits gezeigte Sequenzen werden übersprungen, bis alle dran waren.

### Performance
- **Sequenzliste bei Programmwechsel drastisch schneller.** Die Auswertung „welche Sequenzen sind mit den gewählten Programmen tanzbar" wird nur noch **einmal** je Programm-Menge berechnet und dann gemerkt (statt bei jedem Wechsel mehrfach). Nach der ersten Wahl eines Programms sind Programmwechsel, Scrollen, Filter und Detail-Ansicht praktisch verzögerungsfrei; die gemerkte Auswertung verwirft sich automatisch, sobald sich Sequenzen, Zuordnungen oder Programme ändern. Auf schwächeren Rechnern verschwindet die bisherige mehrsekündige Wartezeit.

### Umstellung & Datensicherheit
- **Automatische, einmalige Umstellung beim ersten Start.** Bestehende Lokationen werden auf die 2026-Programme gestellt (Standard „neu"). Vorher legt Callers Caddy automatisch ein Backup der Datenbank an. Wer eine Lokation weiterhin nach der alten Liste tanzen möchte, wählt in den Einstellungen einfach die alten Programme wieder an (Basic 1 + 2, Mainstream, Plus, Advanced 1).
- Die Programme **Advanced 2 bis Challenge 3B** bleiben unverändert.

---

## 0.138 — Sequenz-Tags, Detail-Header & Rules-Fenster (2026-08-27)

### Neue Features
- **Neue Regel-Aktion „Custom Size Widget".** Öffnet ein Widget als schwebendes Fenster mit frei wählbarer Größe und Position — Breite, Höhe sowie X-/Y-Position jeweils in Prozent. Die bisherige Aktion „Fullsize Widget" (fest 90 %, zentriert) bleibt unverändert erhalten. X/Y verstehen sich als Platzierung im verfügbaren Rest (0 = bündig links/oben, 50 = zentriert, 100 = bündig rechts/unten), sodass das Fenster bei jeder Größe voll sichtbar bleibt.
- **Sequenz-Detail zeigt Typ & Schwierigkeit im Kopf.** Die Sequenz-Detail-Ansicht hat jetzt oben eine Kopfzeile mit Sequenz-Typ und Schwierigkeit der gerade angezeigten Sequenz — so sieht man auf einen Blick, um welche Art Sequenz es sich handelt, auch ohne aktiven Filter. Die Kopfzeile passt ihre Schriftgröße automatisch an die verfügbare Breite an und bleibt gut lesbar.
- **Frei vergebbare Tags für Sequenzen.** Jede Sequenz kann jetzt zusätzlich zu Typ und Schwierigkeit einen frei wählbaren Tag bekommen — etwa „Once and a half", „Asymmetrische Choreo" oder „One the x Hand". Das Feld steht im Sequenz-Editor unter „Schwierigkeit" und schlägt beim Tippen bereits genutzte Tags vor, damit keine leicht abweichenden Schreibvarianten entstehen. Im Sequenzen-Fenster gibt es dafür einen neuen Filter: Tag auswählen zeigt nur Sequenzen mit genau diesem Tag, ein **x** setzt den Filter wieder zurück.

### Verbesserungen
- **Übersichtlicher Regel-Editor.** Die Parameter einer Aktion stehen jetzt beschriftet untereinander unter der Aktion, statt unbeschriftet in einer immer breiter werdenden Zeile. Das Rules-Fenster bleibt dadurch schmal, auch bei Aktionen mit vielen Einstellungen, und jedes Feld ist klar benannt.
- **Kein versehentliches Verstellen per Mausrad im Rules-Fenster.** Scrollt man durch das Regelfenster, ändern die Auswahl- und Zahlenfelder ihren Wert nicht mehr, nur weil der Mauszeiger darüber schwebt. Klickt man ein Auswahlfeld aktiv an, lässt sich die geöffnete Liste weiterhin per Mausrad durchscrollen. Übrige Fenster (z. B. lange Figuren-Listen) bleiben wie gewohnt scrollbar.
- **Figuren-Suche im Sequenzen-Filter: Tippen statt Scrollen.** Die Felder „Enthält" und „Limit" sind jetzt echte Suchfelder: Man tippt einen Teil eines Figurennamens (z. B. „dodge") und bekommt sofort alle passenden Figuren vorgeschlagen, in denen der Text irgendwo vorkommt — nicht mehr nur am Wortanfang. Die Vorschläge sind nach dem gewählten Tanzprogramm sortiert (Figuren des aktuellen Programms zuerst, höhere Programme danach). Ein kleines **x** im Feld setzt den Filter mit einem Klick zurück, ohne wieder nach oben scrollen zu müssen.

---

## 0.137 — Neues Theme „Winter is Coming" (2026-08-26)

### Neue Features
- **Neues Theme „Winter is Coming" von Thomas Franzek.** Ein dunkles Theme mit tiefem Navy und eisigen Blau-Akzenten (angelehnt an „Game of Thrones"). Auswählbar über **Einstellungen → Anzeige → Skin / Theme**.

---

## 0.136 — Große Sequenz-Bibliothek, längere Sequenzen & schneller Import (2026-08-23)

### Neue Features
- **Alle Sequenz-Typen im Vollpaket.** Die Neuinstallation bringt jetzt die komplette Choreografie-Bibliothek mit rund 10.000 Sequenzen über alle Typen mit (Corner Progression, R-H Lady, Singing Break, Static Set, Zero-Varianten u. v. m.).
- **Referenz-Sequenzen zum Nachimportieren.** Bestandsnutzer finden im Programmordner unter `Sequence-Import` die Datei `sequence-import-v0136.json` mit allen Sequenzen und können sie über „Sequenzen → Sequenzen importieren (JSON)…" einspielen. Der Import überspringt automatisch bereits vorhandene Sequenzen (keine Duplikate).
- **Sequenzen dürfen jetzt mehr als 15 Calls haben.** Die bisherige harte Grenze von 15 Calls pro Sequenz ist aufgehoben — lange Patter-Sequenzen (bis dato abgeschnitten) werden vollständig gespeichert und angezeigt. Ältere Programmversionen können dieselbe Datenbank weiterhin lesen (Abwärtskompatibilität).

### Verbesserungen
- **Deutlich schnellerer Import.** Alle Import-Wege (JSON, CSDS, Freitext, MDB, universeller Import) laufen jetzt gebündelt: ein Import von 10.000 Sequenzen dauert Sekunden statt einer Minute. Während des Imports zeigt der Mauszeiger eine Sanduhr.
- **Saubere Sequenz-Typen.** Doppelte Typ-Bezeichnungen für dieselbe Sache wurden zusammengeführt (z. B. „Singer" und „Singing call" für Corner Progression), Trenner vereinheitlicht (Pfeil statt Bindestrich) und das reine „Complete Dance Routine"-Anhängsel entfernt, das Schein-Kategorien im Filter erzeugte.
- **Auswahl-Felder mit einem Klick.** Editierbare Dropdown-Felder (u. a. „Enthält"-Filter, Typ/Schwierigkeit in den Import- und Editor-Dialogen, Figur-Auswahl im Call-Mapping) öffnen ihre Liste jetzt bei einem Klick irgendwo ins Feld — nicht mehr nur über den schmalen Pfeil. Tippen zum Suchen bleibt möglich.
- **Sichtbarer Dropdown-Pfeil im Theme „win11".** Der Auswahl-Pfeil war dort weiß auf weißem Feld (unsichtbar) und ist jetzt klar erkennbar.
- **Call-Mapping: Suche pro Spalte.** Unter den Spaltenüberschriften gibt es Suchfelder, mit denen sich Call-Text, Figur und Quelle filtern lassen (z. B. alle Figuren mit „& Spread" finden).
- **Call-Mapping öffnet mit Ladeanzeige.** Statt 1–3 Sekunden ohne Rückmeldung zu warten, erscheint das Fenster sofort mit Hinweis „Lädt …" und Sanduhr.

### Bugfixes & Technik
- Der „Enthält"-Filter ist intern auf einen indizierten Nachschlage-Index umgestellt und bleibt dadurch auch bei über 10.000 Sequenzen schnell.
- Typlose Alt-Sequenzen ohne erkennbaren Typ wurden bereinigt.
- **Call-Mapping-Lesbarkeit:** Die farbig hinterlegten Call-Texte hatten im dunklen Theme hellen Text auf hellem Grund — jetzt durchgehend dunkler, gut lesbarer Text.
- **Singing-Call-Abschnitte:** Eine Überschrift wie „ALTERNATE OPENER – BREAK – CLOSER" beanspruchte fälschlich die echten Opener/Break/Closer-Abschnitte, sodass die Dynamic-Lyrics-Anzeige zum Alternativ-Block sprang. Solche „Alternate/Additional"-Blöcke werden jetzt korrekt als Zusatz behandelt (betroffene Songs einmal neu synchronisieren).

## 0.135 — Lokations-Sessions (Termine, Start-Erkennung, geteilte Historie) & Zufallssprung per Regel (2026-08-21)

### Neue Features
- **Termin-Angaben pro Lokation (mehrere Wochentag/Uhrzeit-Slots).** Im Einstellungs-Dialog einer Lokation lässt sich jetzt eine Liste von Terminen hinterlegen — jeder mit eigenem Wochentag und eigener Von-bis-Uhrzeit. So kann dieselbe Lokation z. B. dienstags abends und samstags nachmittags zu unterschiedlichen Zeiten tanzen. Termine lassen sich per „+ Termin" hinzufügen und einzeln entfernen. Grundlage für die neue Start-Erkennung und kommende Session-Funktionen. Ohne Termin gilt die Lokation wie bisher als terminlos.
- **Automatische Lokations-Erkennung beim Programmstart.** Passt der aktuelle Wochentag und die Uhrzeit zu einer hinterlegten Lokation, schlägt Callers Caddy diese beim Start vor („Passend zu heute … Lokation ‚X' starten?") und übernimmt sie auf Bestätigung. Bei mehreren passenden Lokationen erscheint eine Auswahl, bei keiner passenden bleibt alles wie gehabt. Der Vorschlag greift nur, solange noch keine Lokation gewählt ist, und mit einem Toleranzfenster ab 60 Minuten vor Beginn.
- **Geteilte Abspielhistorie zwischen Lokationen.** Im Einstellungs-Dialog einer Lokation lässt sich über „Historie teilen mit …" eine andere Lokation als gemeinsame Historien-Basis wählen. Danach zählen Plays beider Lokationen zusammen — ideal für Clubs, die an mehreren Tagen mit teils denselben Tänzern tanzen: derselbe „neue" Song wird nicht doppelt empfohlen. Bereits vorhandene Einträge werden nach Rückfrage in die gemeinsame Historie übernommen. Notizen, Tanzprogramm, Tempo und Termine bleiben pro Lokation getrennt.
- **Neue Unter-Lokation anlegen.** Ein Klick erzeugt eine Lokation, die alle Einstellungen und Termine der gewählten Lokation übernimmt und ihre Historie automatisch mit ihr teilt — der schnelle Weg, einen zweiten Tanztag desselben Clubs einzurichten.
- **Verknüpfte Lokationen sichtbar & anklickbar.** Der Einstellungs-Dialog zeigt unter den Terminen alle Lokationen mit gemeinsamer Historie; die historienführende Lokation ist fett und unterstrichen hervorgehoben, und per Klick wechselt man direkt in deren Einstellungen. In der Lokationsliste ist eine geteilte Historie mit „→ Zielname" gekennzeichnet.
- **Neue Rule-Aktion „Random Sequence" (Gruppe Sequence View).** Springt in der Sequenz-Detailansicht per Regel zu einer zufällig gewählten anderen Sequenz — unabhängig davon, ob der Würfel-Umschalter aktiv ist. Damit lässt sich der Zufallssprung jetzt auch über das Virtual Stream Deck bzw. eine Fernbedienung auslösen. Es gilt dieselbe Logik wie im Würfel-Modus: Ziehen ohne Zurücklegen pro Sitzung mit stiller Auffüllung, wenn alle passenden Sequenzen einmal dran waren.
- **Auswahl hält sich an die eingestellten Filter.** Der Zufallssprung zieht immer nur aus den Sequenzen, die den aktuell gesetzten Filtern (Enthält, Typ, Schwierigkeit usw.) entsprechen — auch dann, wenn das Detail-Fenster beim Filterwechsel gerade nicht sichtbar war. Der Filterstand wird beim Auslösen frisch übernommen, ohne das Sitzungs-Gedächtnis (schon gezeigte Sequenzen) zu verlieren.

### Verbesserungen
- **Uhrzeit-Felder in allen Themes lesbar.** Die neuen Von-bis-Zeitfelder (und alle künftigen Zeit-Eingaben) werden jetzt vom Skin-System gestylt wie die übrigen Eingabefelder — vorher waren sie im Default-Theme heller Text auf hellem Grund und kaum lesbar.

---

## 0.134 — Zufalls-Modus für die Sequenz-Navigation (2026-08-20)

### Neue Features
- **Würfel-Button in der Sequenz-Detailansicht (Sequence View).** Neben „Weiter" gibt es jetzt einen Würfel-Umschalter. Ist er aktiv, springt „Weiter" (Button, Pfeiltaste rechts und das automatische Durchschalten bei Dynamic Lyrics) nicht mehr zur nächsten Sequenz in der Reihenfolge, sondern zu einer **zufällig** gewählten anderen Sequenz — immer nur aus den Sequenzen, die den aktuell eingestellten Filtern entsprechen.
- **Ziehen ohne Zurücklegen (pro Session).** Callers Caddy merkt sich für die laufende Sitzung, welche Sequenzen im Zufalls-Modus schon dran waren, und wiederholt sie nicht, bis alle passenden Sequenzen einmal gezeigt wurden. Ist der Vorrat erschöpft, füllt er sich **still im Hintergrund** wieder auf (keine Meldung) — so stört im Singing Call nichts, auch nicht bei aktiven Dynamic Lyrics.



### Neue Features
- **Neue Rule-Aktion „Set Sequence Type" (Gruppe Sequence View).** Schaltet den Typ-Filter im Sequenzen-Fenster per Regel auf einen gewählten Wert um — z. B. beim Singing Call auf die Singing-Call-Figuren, beim Patter auf Module und Get-Outs. Der Parameter bietet die tatsächlich in der Datenbank vorhandenen Sequenz-Typen als Auswahl an. Ist der gespeicherte Typ nicht mehr vorhanden, bleibt der Filter unverändert und ein kurzer Hinweis erscheint in der Statuszeile.
- **Neue Rule-Aktion „Load Song" (Gruppe Transport).** Wählt automatisch einen Song nach Typ (Singing oder Patter) und Sortierung aus und lädt ihn startbereit in den Player (ohne automatisches Abspielen). „Empfehlung" liefert dabei immer den besten Song, während Zufalls-Sortierungen wie „Balanced Roulette" (gewichteter Zufall) bei jedem Auslösen einen anderen Song bringen. Die Auswahl nutzt exakt dieselbe Bewertung wie die sichtbare Songliste. Verfügbar sind alle Sortierungen der Songliste (Empfehlung, gewichteter Zufall, Zufall, Qualität, Zuletzt gespielt, Alphabetisch, Hinzugefügt).
- **Neuer Trigger „Virtual Stream Deck (manual only)".** Regeln mit diesem Trigger feuern nicht mehr automatisch bei einem Ereignis, sondern werden ausschließlich über das Virtual Stream Deck (bzw. manuellen Aufruf) ausgelöst. Steht ganz oben in der Trigger-Auswahl. Damit lassen sich reine Knopfdruck-Aktionen anlegen, ohne einen künstlichen Auslöser wählen zu müssen.

### Verbesserungen
- **Automatisches Song-Laden per Regel blockiert nicht mehr.** Die Aktion „Load Song" zeigt beim Laden eines Singing Calls keinen interaktiven Sync-Punkte-Übernehmen-Dialog mehr — dieser Abfrage-Dialog bleibt der manuellen Songauswahl vorbehalten. Vorher konnte im Live-Betrieb ein solcher Dialog (teils hinter dem Fenster) das Laden hängen lassen.
- **Virtual Stream Deck: Anfangsbuchstabe wieder groß und mitwachsend.** Hat eine Regel kein Icon, zeigt der Button ihren Anfangsbuchstaben — dieser war bisher sehr klein und skalierte nicht mit der Kachelgröße. Der Buchstabe füllt die Kachel jetzt ähnlich wie ein Icon und wächst beim Vergrößern/Verkleinern des Decks korrekt mit.

---

## 0.132 — Dynamic Lyrics: Sequenzen live in den Singing Call einblenden (2026-07-29)

### Neue Features
- **Neuer Button „Dynamic Lyrics" im Lyric-Fenster (neben Auto-Scroll).** Ist er aktiv, wird der Text der vier Figuren-Abschnitte eines Singing Calls vorübergehend durch die im Sequence-View gewählten Choreografie-Sequenzen ersetzt. Die Lyric-Datei bleibt dabei komplett unangetastet — nur die Anzeige wird getauscht. Beim Ausschalten erscheint sofort wieder der Originaltext aus dem Dokument.
- **Auto-Scroll läuft weiter.** Die gesetzten SyncPoints bleiben gültig; die Anzeige folgt weiter der Musik, zeigt aber die eingeblendeten Sequenz-Texte statt der Figuren-Zeilen aus der Lyric-Datei. Das Timing der Abschnitte bleibt identisch.
- **Live-Durchschalten der Choreografie.** Beim ersten Aktivieren fragt Callers Caddy einmalig, wie die Sequenzen verteilt werden sollen: entweder dieselbe Sequenz in allen vier Figuren, oder — beginnend bei der aktuell gewählten Sequenz — pro Figuren-Durchgang die jeweils nächste Sequenz. Bei geteiltem FIGURE-Block schaltet die Anzeige genau an jeder Figuren-Teil-Grenze zur nächsten Sequenz weiter (nach dem vierten Durchgang bleibt sie stehen). Die Figuren-Teil-Zeiten werden aus den vorhandenen SyncPoints abgeleitet.
- **Einstellungen werden gemerkt.** Sowohl die getroffene Wahl (Option 1 oder 2) als auch, ob Dynamic Lyrics überhaupt aktiv sein soll, werden gespeichert und beim nächsten Start wiederhergestellt. Beides lässt sich auch in den Einstellungen unter „Lyrics" umschalten („Dynamic Lyrics aktiv" und „Dynamic-Lyrics-Modus") — die neuen Felder sind vollständig übersetzt (DE/EN/JA).
- **Dynamic Lyrics bleibt über Songwechsel aktiv.** Ist der Modus eingeschaltet, greift er beim nächsten Song automatisch wieder und spiegelt dabei die aktuell im Sequence-View gezeigte Sequenz — man muss ihn nicht pro Titel erneut aktivieren. Bei einem Song ohne die nötigen Voraussetzungen pausiert er still und kommt beim nächsten passenden Titel von selbst zurück.
- **Das Sequence-View steuert, das Lyric-Feld spiegelt.** Beim Live-Umblättern (Option 2) blättert Callers Caddy an jeder Figuren-Teil-Grenze im Sequence-View eine Sequenz weiter, und das Lyric-Feld zeigt genau das, was dort gerade steht. Dieselbe Kopplung greift, wenn man im Sequence-View von Hand vor- oder zurückblättert — das Lyric-Feld folgt sofort. So ist die Grundlage gelegt, das Weiterblättern später auch per Fernbedienung dem Nutzer zu überlassen.
- **Eingeblendete Sequenzen ohne Hintergrund-Marker.** Der eingefügte Sequenz-Text übernimmt Schriftart und -farbe der Umgebung, aber keine Hintergrund-/Highlight-Farbe aus der Lyric-Datei mehr — er wird also nicht mehr versehentlich rosa (o. ä.) unterlegt.
- **Sauberes Ausgrauen.** Der Button ist nur verfügbar, wenn alle Voraussetzungen erfüllt sind: Lyric geladen, SyncPoints gesetzt, Figuren-Abschnitte erkannt und mindestens eine Sequenz im Sequence-View gewählt. Fehlt etwas, ist der Button ausgegraut und nennt den Grund im Tooltip. Im Sync- und Bearbeiten-Modus ist Dynamic Lyrics nicht verfügbar.

---

## 0.131 — Update-Erinnerung pausieren, manueller Update-Check & mehr Stream-Deck-Icons (2026-07-26)

### Neue Features
- **Der Update-Hinweis lässt sich jetzt für 7 Tage stummschalten.** Im Fenster „Update verfügbar" gibt es zusätzlich zu „Jetzt herunterladen" und „Später" die Auswahl „Für 7 Tage nicht mehr erinnern". Wer sie anhakt, wird beim nächsten Start eine Woche lang nicht erneut auf dieselbe Version hingewiesen — der tägliche Hinweis beim Öffnen entfällt also, ohne dass man das Update aus den Augen verliert. Nach Ablauf der 7 Tage meldet sich das Programm von selbst wieder. „Später" bleibt wie bisher der Weg für „nur dieses Mal wegklicken".
- **Eine wirklich neuere Version durchbricht die Ruhephase.** Erscheint innerhalb der sieben Tage eine noch höhere Version als die verschobene, wird der Hinweis trotzdem sofort wieder angezeigt — stillgehalten wird nur genau die Version, für die man „Ruhe" gewählt hat.
- **Neuer Menüpunkt „Nach Updates suchen…" im Menü „Info".** Damit lässt sich jederzeit von Hand nach einer neuen Version schauen. Anders als die automatische Prüfung beim Start gibt der manuelle Aufruf immer Rückmeldung: entweder das Update-Fenster, „Callers Caddy ist aktuell" oder ein Hinweis, wenn gerade keine Verbindung besteht. Eine gesetzte 7-Tage-Ruhephase wird dabei bewusst übergangen.
- **Deutlich mehr Symbole für die Stream-Deck-Buttons.** Für praktisch jede Regel-Aktion gibt es jetzt ein passendes Icon (Tempo, Pitch, Live-Lautstärke, BPM, Fenster-Fokus/Vollbild, Dual-View, Auto-Scroll, Sequenz-Ansicht, Foto, Genre, Meldungen, Warnfarbe u. v. m.), dazu Standard-Symbole wie Richtungspfeile in alle acht Richtungen, ein Auge und ein Mauszeiger. Alle neuen Symbole sind im selben Stil gehalten und werden — wie bisher — automatisch in der Theme-Farbe eingefärbt.

---

## 0.130 — Automatische Update-Prüfung beim Programmstart (2026-07-25)

### Neue Features
- **Callers Caddy prüft beim Start automatisch, ob eine neuere Version bereitsteht.** Kurz nach dem Öffnen schaut das Programm im Hintergrund im Online-Download-Bereich nach. Liegt dort eine höhere Version als die installierte, erscheint ein Hinweis „Es ist ein Update (Version xy) verfügbar" mit den Schaltflächen „Jetzt herunterladen" und „Später". Ist alles aktuell, passiert nichts — kein Fenster, keine Verzögerung. Auch wenn gerade keine Internetverbindung besteht, startet das Programm ganz normal weiter.
- **„Jetzt herunterladen" lädt gezielt die richtige Update-Datei.** Statt in einem Ordner voller ZIP-Dateien selbst suchen zu müssen, startet der Knopf direkt den Download der passenden Update-Datei in den Download-Ordner. So kann nicht mehr versehentlich die komplette Neuinstallation geladen werden, die vorhandene Daten überschreiben würde.

---

## 0.129 — Fehlende Lyrics aus einem Ordner auffüllen: „Suche in der Krabbelkiste" (2026-07-24)

### Neue Features
- **Neuer Knopf „Suche in der Krabbelkiste" im Optimierungs-Fenster unter „Ohne Lyrics".** Damit lassen sich fehlende Songtexte für Singing Calls in einem Rutsch aus einem vorhandenen Ordner voller loser Lyric-Dateien auffüllen — etwa dem exportierten Lyrics-Ordner eines anderen Programms. Nach dem Klick erklärt ein kurzer Dialog, was gleich passiert, und lässt die Wahl zwischen „nur dieser Ordner" und „auch Unterordner (rekursiv)". Danach wählt man den Ordner aus, und das Programm durchsucht ihn nach passenden Kandidaten. Betroffen sind ausschließlich Singing Calls ohne hinterlegte Lyrics.
- **Die Zuordnung erkennt passende Dateien an Titel, Label und Plattennummer — nach denselben Prinzipien wie der ZIP-Import und die Cue-Sheet-Suche.** Abweichende Schreibweisen (Slugs, Bindestrich- und Mehrwort-Labels, Modifier-Suffixe, Groß-/Kleinschreibung) werden dynamisch berücksichtigt. Gesucht wird nicht nur im Dateinamen, sondern zusätzlich im Kopf der Datei selbst — so werden auch Dateien mit nichtssagendem Namen gefunden, wenn der Titel im Text steht. Weil Songtexte pro Titel gelten und nicht pro Aufnahme, zählen Label und Plattennummer hier als zusätzliche Bestätigung, verhindern aber keinen guten Titeltreffer (anders als bei der Cue-Sheet-Suche, wo es um eine bestimmte Aufnahme geht).
- **Ein Ergebnis-Dialog stellt Song und gefundene Datei gegenüber und zeigt je Zeile eine Wahrscheinlichkeit.** Die Tabelle zeigt nebeneinander Titel, Label und Nummer des Songs sowie die aus der Datei ermittelten Angaben, dazu die Quelle (Dateiname oder Dateiinhalt) und eine kurze Begründung. Alle Vorschläge sind vorausgewählt — man kann sie also komplett durchwinken oder gezielt einzelne abwählen. Die Tabelle lässt sich nach jeder Spalte sortieren (z. B. nach Wahrscheinlichkeit), sodass jeder selbst entscheidet, wie weit er gehen möchte. Beim Übernehmen werden die gewählten Dateien in den Lyrics-Ordner kopiert und dem jeweiligen Song zugeordnet — der durchsuchte Ordner darf also ruhig ein temporärer Zwischenlager-Ordner sein.

### Verbesserungen
- **Die Suchprinzipien von ZIP-Import und Cue-Sheet-Suche liegen jetzt an einer zentralen Stelle.** Titel-/Label-/Nummer-Zerlegung und Trefferbewertung wurden in eine gemeinsame Basis zusammengeführt, die von der neuen Krabbelkiste-Suche und der ceder.net-Suche geteilt wird. Verbesserungen an der Erkennung wirken damit künftig überall gleichzeitig. Das Verhalten der Cue-Sheet-Suche bleibt dabei unverändert.

### Bugfixes
- **Im Sequenz-Detail-Fenster wird die letzte Zeile nicht mehr abgeschnitten.** Die automatische Schriftanpassung ließ bei großer Schrift und wenigen Zeilen einen kleinen Überlauf zu, wodurch die unterste Call-Zeile halb aus dem Fenster ragte. Die Schrift wird jetzt so weit verkleinert, dass der gesamte Inhalt sicher in die verfügbare Höhe passt — kein Anschnitt mehr, egal wie man das Fenster zieht.
- **Beim Bearbeiten einer Regel gehen Name, Trigger und Aktion nicht mehr verloren, wenn man die Stream-Deck-Felder anfasst.** Bisher wurde beim Setzen der Button-Nummer (bzw. Icon/Tooltip) sofort die ganze Regel gespeichert und neu geladen — noch nicht per „Speichern" bestätigte Eingaben oberhalb gingen dabei verloren, und der „Speichern"-Knopf wurde ausgegraut. Jetzt sind die Stream-Deck-Felder bei eigenen Regeln normale Editor-Felder: Änderungen halten den „Speichern"-Knopf aktiv, und ein Klick auf „Speichern" schreibt alles gemeinsam (Name, Trigger, Aktionen und Deck-Parameter inklusive der lückenlosen Neunummerierung). System-Regeln werden weiterhin sofort aufs Deck übernommen.

---

## 0.128 — Stream Deck: das Regel-System als Klick-Oberfläche (2026-07-23)

### Neue Features
- **Neues, andockbares Fenster „Stream Deck" — das mächtige Regel-System bekommt ein sichtbares Gesicht.** Jede Regel kann eine Buttonnummer, ein Icon und einen Tooltip erhalten; alle Regeln mit einer Nummer größer als 0 erscheinen als quadratische Kacheln im Stream Deck, sortiert nach ihrer Nummer. Ein Klick auf einen Button führt die Regel sofort aus — die Bedingungen werden dabei weiterhin geprüft (z. B. „nur für Singing"), lediglich der Tasten-Auslöser wird übersprungen. Die Buttons nutzen die Fensterfläche optimal aus: sie sind immer quadratisch, brechen bei vielen Buttons in mehrere möglichst gleichmäßig gefüllte Reihen um, und die Button-Matrix sitzt zentriert. Oben rechts öffnet ein dezentes Zahnrad direkt das Regel-Fenster zum Anpassen. Das Fenster lässt sich frei andocken, mit anderen Fenstern tabben oder schweben lassen — die Anordnung bleibt über einen Neustart erhalten.
- **Das Stream Deck ist ab Werk mit den fünf Standard-Steuertasten bestückt.** F5→Play, F6→Pause, F7→Stop, F8→Fade Out und Leertaste→Play/Pause liegen von Anfang an als Buttons im Deck (mit passenden Icons). Es sind System-Regeln, also immer vorhanden — sie funktionieren weiterhin auch über die echten Tasten. Wer einen Button nicht braucht, nimmt ihn einfach aus dem Deck; er kommt nicht ungefragt wieder. Auch bestehende Installationen erhalten diese Erstbestückung beim nächsten Start.
- **Regeln haben jetzt einen Abschnitt „Stream Deck" im Editor.** Dort lassen sich Buttonnummer (= Position), Icon und Tooltip festlegen — mit einer Vorschau des gewählten Icons, dargestellt wie die spätere Kachel (damit die Icons auch auf hellen Themes gut sichtbar sind). Die Nummern werden immer lückenlos vergeben (so viele verschiedene Zahlen wie Buttons), und eine Positionsänderung ist sofort im Deck sichtbar. Der Abschnitt ist bewusst auch für System-Regeln editierbar, sodass sich jede Regel aufs Deck legen lässt.
- **17 neue Symbole für die Buttons.** Play, Stop, Pause, Play/Pause, Fade Out, Lauter, Leiser, Schneller (Hase), Langsamer (Schildkröte), Loop, Notiz abhaken, Nächstes Lied, Pause mit letztem Lied, Pause (Kaffeetasse), Fenster öffnen, Fenster schließen und Choreo (Tanzabdruck). Sie werden — wie alle Icons — automatisch in der Theme-Farbe eingefärbt; reine Titelleisten-Icons stehen in der Auswahl bewusst nicht zur Verfügung.

### Verbesserungen
- **Im Sync-Modus lässt sich der Songstart jetzt direkt per Knopf um eine Sekunde verschieben.** Links neben den Zoom-Knöpfen im Lyric-Fenster gibt es zwei neue Schaltflächen „−1 s" und „+1 s". Ein Klick verschiebt den Beginn des Songs samt aller gesetzten Sync-Punkte und des Endpunkts um eine Sekunde nach vorne bzw. hinten — praktisch, um einen leicht zu früh oder zu spät sitzenden Start nachzujustieren, ohne jeden Punkt einzeln anzufassen. Die Funktion gab es bisher schon, aber versteckt als Rechtsklick-Menü auf einem Sync-Punkt („Alle verschieben"); sie ist jetzt nur besser erreichbar. Beide Wege nutzen dieselbe Logik, und die Knöpfe erscheinen ausschließlich im Sync-Modus.

### Bugfixes
- **Fenster merken sich ihre Anordnung wieder zuverlässig — inklusive des zuletzt vorne liegenden Tabs.** Fenster, die erst spät beim Programmstart erzeugt werden (u. a. die Pausen-Uhr und das neue Stream Deck), kehrten nach einem Neustart an eine Standardposition zurück, statt dorthin, wo man sie zuletzt hatte — sie existierten zum Zeitpunkt der Layout-Wiederherstellung schlicht noch nicht. Jetzt werden alle Docks vor der Wiederherstellung angelegt, und zusätzlich wird pro Tab-Gruppe gemerkt, welcher Tab vorne lag (das vergisst Qt beim Wiederherstellen sonst). Position, Größe, Sichtbarkeit und aktiver Tab kommen damit für jedes Fenster einheitlich zurück — ganz ohne die früheren Einzel-Sonderbehandlungen.

---

## 0.127 — Pausen-Regeln, ceder.net-Filterung, robustere Abschnittserkennung (2026-07-22)

### Neue Features
- **Zwei neue Regel-Aktionen für die Pause.** In der Gruppe „Transport" gibt es jetzt „Start Break" und „Start Break with last Song". Beide öffnen die Pausen-Uhr und starten den Countdown; die zweite spielt zusätzlich den zuletzt gespielten Song als Wartemusik. Die Pausendauer lässt sich als Parameter (Minuten) vorgeben — bei 0 wird automatisch die Standard-Pausendauer der aktuellen Lokation verwendet.
- **Neuer Knopf „✨ Mach alles schön" im Optimierungs-Fenster (Potential).** Ganz unten auf der Übersichtsseite führt er die vorhandenen Heilungsfunktionen auf Wunsch nacheinander aus, statt jede einzeln in ihrem Reiter anzustoßen. Ein Klick öffnet eine Auswahlliste mit allen Aktionen und der jeweils gefundenen Fallzahl — BPM erkennen, Auto-Loop für Patter ohne Loop, BeatSnap, Songanfang und Sync-Punkte erkennen. Die auffüllenden Aktionen sind vorausgewählt; die beiden löschenden Aufräum-Aktionen (leere Lokationen, verwaiste Historie) sind bewusst nicht angehakt und müssen einzeln aktiviert werden. Aktionen ohne Fälle sind ausgegraut. Der Lauf zeigt eine ToDo-Fortschrittsliste mit hervorgehobenem aktuellem Schritt, lässt sich jederzeit abbrechen (bereits gemachte Änderungen bleiben erhalten) und meldet am Ende pro Aktion, wie viele Songs bearbeitet und wie viele übersprungen wurden. Nur die jeweils offenen Fälle werden angepackt — die „ALLE neu durchrechnen"-Varianten der Reiter bleiben unberührt.

### Bugfixes
- **Die Tanzprogramme und ihre Figuren-Limits werden jetzt auch bei bestehenden Installationen nachgetragen.** Wer Callers Caddy über ein Update aktualisiert hat (bei dem die Datenbank absichtlich erhalten bleibt), hatte die Tanzprogramme teils gar nicht oder ohne hinterlegtes Sequenz-Limit. Dadurch bewirkte der Programmwechsel keine Filterung im Sequenzen-Fenster. Beim nächsten Start werden fehlende Programme angelegt und fehlende Figuren-Limits einmalig ergänzt (Mainstream, Plus, A1, A2, C1, C2, C3A samt Class-Varianten). Selbst angepasste Programme, eigene Ziel-Patternlängen und ein bewusst auf „kein Limit" gesetztes Programm bleiben dabei unangetastet.
- **Der Zähler „Loop ohne BeatSnap" sinkt jetzt nach einem BeatSnap-Lauf.** Bisher blieb die Zahl unverändert, obwohl der Stapel-BeatSnap gelaufen war: Die Prüfung wertet einen Loop erst dann als optimiert, wenn ein Loop-Offset gesetzt ist — der Stapel-Lauf hatte aber nur die Loop-Marken auf den Beat geschnappt und den Offset nie gemessen. Jetzt misst der Stapel-BeatSnap zusätzlich den Loop-Offset (Tiefpass-Kreuzkorrelation im Bassbereich), genau wie der Einzel-Song-BeatSnap. Dadurch werden die Loops nicht nur beat-genau, sondern auch sauber überblendbar, und die bearbeiteten Songs verschwinden aus der Liste. Das gilt auch für den bestehenden „Alle optimieren"-Knopf im BeatSnap-Reiter.

### Verbesserungen
- **Das Feld „Kontaktadresse für Serveranfragen" in den Einstellungen wurde entfernt.** Es war eine reine Höflichkeits-Angabe für den ceder.net-Zugriff, blieb aber fast immer leer und stiftete nur Verwirrung. Bei Anfragen an ceder.net wird weiterhin ein sprechender Kennungstext mitgeschickt (Programmname + Homepage), aber keine persönliche E-Mail-Adresse mehr.
- **Der Netzwerk-Abschnitt in den Einstellungen ist jetzt übersetzt.** Der Abschnitt „Netzwerk" samt „Cue-Sheet-Suche auf ceder.net" (inkl. Tooltip) wurde bisher in der englischen und japanischen Oberfläche noch auf Deutsch angezeigt. Die fehlenden Übersetzungen sind ergänzt.
- **Die Einstellung „Patter-Füllung im Planner" ist jetzt übersetzt.** Feldname und Erklärungs-Tooltip erschienen in der englischen und japanischen Oberfläche bisher noch auf Deutsch. Die fehlenden Übersetzungen sind ergänzt.
- **Der ceder.net-Trefferdialog ist jetzt vollständig übersetzt.** Die Spalten „Sicherheit" (sicher / wahrscheinlich / unsicher) und „Begründung" (etwa „Titel identisch", „Titel ähnlich (85 %)", „Label stimmt", „Plattennummer stimmt", „kein Cue Sheet") kamen bisher hartkodiert auf Deutsch aus der Suchlogik und blieben in der englischen und japanischen Oberfläche unübersetzt. Sie laufen jetzt über die zentrale Übersetzungstabelle (Deutsch, Englisch, Japanisch).
- **Beim Holen eines Cue Sheets von ceder.net werden Navigationselemente jetzt weggefiltert.** Der „two columns"-Umschalter oben rechts und die Datenbank-Links im Footer („Data page", „Cue sheet", „Lyrics") landeten bisher mit im lokalen Lyric, obwohl sie dort nichts nützen. Sie werden jetzt vor dem Speichern entfernt. Der Herkunftsnachweis bleibt als HTML-Kommentar in der Datei erhalten.
- **Die Abschnittserkennung für den Auto-Sync verkraftet jetzt an die Überschrift angehängte Zusätze.** Viele Cuesheets (u. a. von ceder.net) schreiben hinter die Überschrift nach einer größeren Lücke noch das Tanzprogramm oder eine Beschreibung — etwa „OPENER - MIDDLE BREAK - CLOSER   Mainstream" oder „FIGURE   Plus, corner progression". Bisher verwarf die Erkennung solche Zeilen komplett (ein einziges Fremdwort ließ die ganze Überschrift durchfallen), sodass der Auto-Sync mit „keine passenden Texte" abbrach. Der Zusatz hinter der Lücke wird jetzt abgetrennt; der Schutz gegen Fehlalarme aus normalen Liedzeilen bleibt bestehen.

---

## 0.126 — Patter auf Ziellänge füllen, Sequenz-Limit beim Programmwechsel (2026-07-20)

### Neue Features
- **Neu in den Planner aufgenommene Patter können automatisch auf die Ziellänge gebracht werden.** In den Einstellungen gibt es im Bereich Planer das neue Feld „Patter-Füllung" mit zwei Optionen. Bei „Endlos" bleibt alles wie bisher: ein neu hinzugefügter Patter läuft ohne feste Länge (∞), bis man ihn von Hand beendet oder pro Song eine Länge einstellt. Bei „Auf Ziellänge optimieren" wird für jeden neu aufgenommenen Patter — egal ob per Knopf, Doppelklick, Ziehen oder über den Zauberstab — automatisch die passende Loop-Anzahl gesetzt, sodass er die Ziellänge des aktiven Tanzprogramms möglichst genau trifft. Liegt keine ganze Loop-Anzahl nah genug an der Zielzeit, wird zusätzlich die feine Kürzung (ganze Phrasen) angewandt, die bis auf rund 20 Sekunden herankommt — dieselbe Rechnung wie im Loop-Dialog von Hand. Songs ohne gültige Loop-Marken bleiben unverändert endlos. Voreingestellt ist „Endlos", sodass sich für bestehende Abläufe nichts ändert, solange man es nicht umstellt.

### Bugfixes
- **Ein von Hand gesetztes Limit im Sequenzen-Fenster bleibt beim Wechsel des Tanzprogramms erhalten.** Bisher wurde der Limit-Filter beim Programmwechsel auf „Alle" zurückgesetzt, sobald das neu gewählte Tanzprogramm kein eigenes Sequenz-Limit hinterlegt hatte — das von Hand gewählte Limit ging dabei jedes Mal verloren. Jetzt wird der Filter nur noch angepasst, wenn das Zielprogramm ein Sequenz-Limit vorgibt; andernfalls bleibt die aktuelle Auswahl stehen. Für Programme mit hinterlegtem Sequenz-Limit ändert sich nichts.
- **Der gespeicherte Zoom im Lyric-Fenster gilt jetzt sofort beim Start.** Wer die Lyric-Schriftgröße von Hand eingestellt hatte, sah nach dem Programmstart zunächst die kleine Standardgröße — erst ein Druck auf einen Zoom-Knopf stellte den gemerkten Wert wieder her. Ursache war, dass die gespeicherte Größe nur auf das noch leere Lyric-Fenster angewendet wurde und beim Laden des ersten Textes verloren ging. Jetzt wird sie direkt auf den geladenen Text übernommen.

---

## 0.125 — Farbige Lyric-Abschnitte, persönliche Voreinstellungen (2026-07-20)

### Neue Features
- **Die Lieblings-Sortierung lässt sich jetzt fest hinterlegen.** Wer immer nach „Zuletzt gespielt" oder „Empfehlung" arbeitet, musste die Sortierung bisher nach jedem Programmstart neu umstellen. In den Einstellungen gibt es dafür den neuen Bereich „Sortierung" mit dem Feld „Lieblings-Sortierung" — alle sieben Sortierungen stehen zur Auswahl. Beim nächsten Start sind Songliste und Planner bereits so sortiert. Im Planner wurde die Sortierung bisher bei jedem Öffnen des Fensters fest auf „Empfehlung" beziehungsweise „Qualität" gestellt — ist eine Lieblings-Sortierung hinterlegt, hat diese jetzt Vorrang, und auch eine von Hand geänderte Sortierung bleibt beim Wiederöffnen erhalten. Ohne hinterlegte Lieblings-Sortierung bleibt es beim bisherigen Verhalten.
- **Der „Nur"-Filter im Sequenzen-Fenster kann voreingestellt werden.** Wer grundsätzlich nur die Sequenzen des gewählten Programms sehen will, setzt die neue Einstellung „‚Nur'-Filter beim Start aktiv" im Bereich Sequenzen. Die Checkbox im Sequenzen-Fenster ist dann von Anfang an gesetzt, lässt sich im laufenden Betrieb aber wie gewohnt umschalten.
- **Die Abschnitte eines Singing Calls werden im Lyric-Fenster farbig angezeigt.** Im Sync-Modus erscheint rechts neben dem Text eine eigene Spalte, die Opener, die vier Figuren, Middle Break, Closer, Tag und Additional Lyrics als farbige Balken zeigt — in denselben Farben wie die Abschnittsleiste am Player. Teilen sich mehrere Abschnitte denselben Text, was auf vielen Cuesheets der Normalfall ist, stehen sie als schmale Spalten nebeneinander statt übereinander.
- **Die Abschnittsgrenzen lassen sich mit der Maus verschieben.** Ober- und Unterkante jedes Balkens sind einzeln greifbar, der Mauszeiger zeigt es an. Die Grenze rastet auf Textzeilen ein, und der Anfang kann das Ende nicht überholen. Gespeichert wird beim Loslassen. Weil die Spalte neben dem Text liegt und nicht darüber, kann ein Klick auf eine Kante keinen versehentlichen Sync-Punkt mehr auslösen.
- **Jeder Abschnitt bleibt einzeln verschiebbar, auch wenn mehrere auf demselben Text starten.** Liegen Opener, Middle Break und Closer nach der Auto-Analyse auf einem gemeinsamen Block, lässt sich trotzdem nur einer davon herausziehen — etwa um den Middle Break nachträglich bis in die Alternativen Lyrics zu verlängern. Überlappen sich Abschnitte danach nur noch teilweise, rücken sie automatisch in nebeneinanderliegende Spuren, statt sich zu verdecken. Wer sich mit niemandem überlappt, nutzt die volle Breite.
- **Die erkannten Abschnitte werden dauerhaft am Song gespeichert** und stehen damit auch nach einem Neustart zur Verfügung, statt bei jedem Auto-Sync neu berechnet zu werden. Das gilt für beide Wege: den Auto-Sync im Lyric-Fenster und den Sammellauf „Sync-Punkte setzen" im Hintergrund. Der Sammellauf hat die Abschnitte ohnehin schon berechnet, bisher aber nur die Sprungmarken daraus gespeichert und die Analyse danach verworfen.
- **„Additional Lyrics" und „Alternate Lyrics" werden als eigener Abschnitt erkannt.** Das behebt einen Fehler mit sichtbarer Wirkung: Weil ein Abschnitt bis zur nächsten erkannten Überschrift reicht, wanderte der alternative Figurentext bisher in den davorstehenden Block und verlängerte etwa den Opener um ein Vielfaches. In 29 der vorhandenen Lyric-Dateien wird dadurch jetzt ein Block korrekt begrenzt.
- **Der Tag bekommt einen eigenen Sprungpunkt** am Ende des Closers. Bisher wurde er beim Auto-Sync übersprungen.
- **Neuer Knopf „ALLE Lieder mit Lyrics neu berechnen" im Tab „Ohne SyncPunkte".** Er läuft über den gesamten Bestand, also auch über Songs, die schon Sync-Punkte haben und deshalb gar nicht in der Liste stehen. Gedacht für den Fall, dass sich die Erkennung verbessert hat und man alles einmal frisch durchrechnen will. Weil dabei bestehende Sprungmarken gelöscht und neu gesetzt werden, zählt die Rückfrage vorher genau, wie viele Songs betroffen sind und wie viele davon bereits Marken haben.

### Verbesserungen
- **Der Knopf „Alle Lieder ergänzen" heißt jetzt „Alle Lieder der Liste ergänzen".** Er hat schon immer nur die Songs der angezeigten Liste bearbeitet, also die ohne Sync-Punkte — der alte Name legte einen Komplettlauf über alle Lieder nahe.
- **Ein wiederholter Sammellauf hinterlässt keine Reste mehr.** Bisher wurden die Sprungmarken über die vorhandenen geschrieben. Hatte ein Song vorher mehr Marken als der neue Lauf erzeugt, blieben die überzähligen aus der alten Synchronisation stehen und vermischten sich mit den neuen. Jetzt werden die alten Marken des Slots erst entfernt. Songs, deren Analyse fehlschlägt, bleiben dabei unangetastet.
- **Überschriften mit erklärendem Zusatz in Klammern werden wieder erkannt.** Eine Zeile wie „FIGURE (twice for heads, twice for sides):" wurde bisher verworfen, weil die Längenprüfung vor dem Abschneiden des Klammerzusatzes lief — die Zeile ist 42 Zeichen lang, die eigentliche Überschrift nur 6. In 14 Lyric-Dateien werden dadurch jetzt sämtliche Figur-Abschnitte erkannt, die vorher komplett fehlten. Das wirkt sich auch auf den Auto-Sync aus: diese Songs bekamen bisher falsch gesetzte Sprungmarken.
- **Wird ein Song beim Sammellauf übersprungen, sagt die Meldung jetzt, wo es weitergeht.** Statt nur „kein Songanfang" steht dort der Hinweis auf den Tab „Ohne Songpunkte", in dem sich der fehlende Wert setzen lässt. Der Grund war zwar schon immer korrekt benannt, führte aber leicht auf die falsche Fährte — bei tadellosen Lyrics sucht man den Fehler zuerst dort.
- **Beide Einstellungen sind in allen drei Sprachen beschriftet** und im Einstellungen-Fenster als neustartpflichtig gekennzeichnet — sie greifen beim nächsten Programmstart.
- **Der Zufalls-Tiebreaker ist beim Start korrekt bedienbar.** Bisher war das Kästchen nach dem Start immer ausgegraut, weil die Anwendung fest von „Alphabetisch" ausging. Jetzt richtet es sich nach der tatsächlich eingestellten Startsortierung.
- **Neue Einstellungen erscheinen auch bei einer frischen Installation.** Bislang zeigte das Einstellungen-Fenster nur Bereiche an, die bereits in der INI-Datei standen — bei einer Neuinstallation blieben noch nie benutzte Bereiche unsichtbar.

---

## 0.124 — Ziel-BPM pro Lokation, „Nur"-Filter für Sequenzen, ZIP-Import (2026-07-19)

### Neue Features
- **Die Sequenzliste kann jetzt gezielt nur die Sequenzen des gewählten Programms anzeigen.** Neben dem Limit-Auswahlfeld sitzt die neue Checkbox „Nur". Hintergrund: Wer beim Limit zum Beispiel A1 wählt, bekam bisher auch sämtliche Sequenzen der tieferen Programme angezeigt — Plus, Mainstream und Basic. Tanzbar sind die für A1-Tänzer zwar alle, aber wer zu einem A1-Abend gekommen ist, will A1 tanzen. Mit gesetzter Checkbox bleiben nur die Sequenzen übrig, deren schwerster Call im Programm des Limits liegt — also garantiert mindestens ein A1-Call pro Sequenz.
- **Das funktioniert auch mit einem Limit mitten im Programm.** Wer als Limit einen einzelnen Call wählt (etwa den Lernstand einer Class), bekommt mit der Checkbox genau die Sequenzen, die mindestens einen Call des angefangenen Programms enthalten, aber keinen über dem gewählten Call — passend zum Unterrichten.
- **Der Filter wirkt überall dort, wo die gefilterte Liste weiterverwendet wird:** beim Durchblättern im Detail-Fenster, bei den Regel-Aktionen auf der gefilterten Auswahl und beim Übernehmen in die Notizen. Ohne gewähltes Limit hat die Checkbox keine Wirkung; der erklärende Tooltip liegt in allen drei Sprachen vor.
- **Jede Lokation kann jetzt ein Ziel-Tempo in BPM vorgeben.** In den Lokations-Einstellungen steht neben dem bekannten prozentualen Tempo ein zweites Feld „Ziel-BPM". Ist es aktiv, wird bei jedem Songwechsel das heutige Tempo automatisch so berechnet, dass der Song genau mit der eingestellten BPM-Zahl läuft — unabhängig davon, wie schnell die Aufnahme von Hause aus ist. Damit laufen alle Songs eines Abends hörbar im selben Tempo. Grundlage der Rechnung ist die tatsächliche Song-Geschwindigkeit, also Basis-BPM mal Song-Tempo.
- **Umgeschaltet wird per Auswahlknopf, nicht durch Löschen.** Vor beiden Feldern sitzt je ein Auswahlknopf, der bestimmt, welcher Wert gilt. Beide Zahlen bleiben dabei gespeichert — wer zwischen „103 %" und „128 BPM" wechselt, muss nichts neu eintippen. Bestehende Lokationen laufen unverändert im Prozent-Modus weiter.
- **Manuelles Abweichen bleibt möglich.** Das heutige Tempo lässt sich nach dem automatischen Setzen wie gewohnt von Hand verstellen — etwa schneller für einen Hot Hash oder langsamer im Workshop. Die Abweichung gilt für den laufenden Song; beim nächsten Songwechsel rechnet die Automatik wieder auf die Ziel-BPM.
- **Schutz vor Tippfehlern.** Beim erstmaligen Aktivieren ist das Feld mit 128 BPM vorbelegt, dem üblichen Square-Dance-Tempo. Liegt der eingetragene Wert außerhalb von 100–150 BPM, fragt der Dialog vor dem Speichern nach — eine vertippte „13" würde sonst jeden Song unbemerkt ans Tempo-Limit fahren.

### Verbesserungen
- **Der ZIP-Import erkennt jetzt deutlich mehr Dateinamen-Schemata der Label.** Als Vorlage diente eine Analyse des Open-Source-Programms SquareDesk, dessen Namenserkennung über die Jahre mit vielen realen Musikdateien gewachsen ist. Neu erkannt werden: Labels mit Bindestrich im Namen wie „4-Bar-B 123 - Chicken Plucker" (bisher wurde der Labelname am Bindestrich zerschnitten), mehrwortige Labels wie „New Beat 203a" oder „Blue Star 1790", Labelkürzel mit Ziffer wie „OGRMP3 04", reine Nummern-Labels wie „123 - Chicken Plucker" — auch mit Punkt statt Bindestrich („123.Chicken Plucker") — sowie die Schreibweise mit Bindestrich zwischen Label und Nummer wie „Paper Doll - Windsor-4936B".
- **Download-Dateinamen mit Unterstrichen werden automatisch aufgeräumt.** Aus einem Shop-Dateinamen wie „ego_112_-_go_tell_aunt_rhody" macht der Import jetzt Titel „Go Tell Aunt Rhody" und Label „ego 112". Komplett klein- oder großgeschriebene Titel werden dabei in normale Groß-/Kleinschreibung gebracht; gemischte Schreibweisen bleiben unangetastet.
- **Vocal-Dateien werden zuverlässiger als Variante erkannt.** Neben den bekannten Kürzeln zählt jetzt auch das ausgeschriebene Wort „vocal" im Dateinamen sowie die Klammer-Zusätze „(Vocal)" und „(Inst)". Solche Dateien werden nicht mehr versehentlich als Haupt-Titel vorgeschlagen.
- **Die Labels mit Bindestrich und die mehrwortigen Labels stehen in der pflegbaren Label-Liste.** Wer ein weiteres Label mit ungewöhnlichem Namen nutzt, trägt es einfach im Import-Dialog nach — ab dann wird es korrekt erkannt.
- **Beigepackte Bilder (Cover) und XML-Dateien werden im Vollständigkeitsbericht mit klarem Grund ausgewiesen** statt nur als „unbekannter Dateityp".
- **Kompakte Dateinamen im SqView-Stil werden erkannt.** Bei Dateien wie „A1005m"/„A1005v" (Labelnummer plus angehängter Kennbuchstabe, ohne Titel) wird die Labelnummer als Label übernommen und das Paar korrekt zu Haupt-MP3 plus Vocal-Variante gebündelt. Im Praxistest mit der vorhandenen Bibliothek (755 Dateien) stieg die Label-Erkennung damit von 15 % auf 52 % der Dateien — der Rest sind normale Musiktitel ohne Label, die bewusst keines bekommen.
- **Der Zauberstab im Planner würfelt bei den Zufalls-Sortierungen vor jedem Befüllen neu.** Wer als Sortierung „Zufall" oder „Gewichteter Zufall" eingestellt hatte und die Playlist zweimal hintereinander automatisch befüllen ließ, bekam bisher beide Male exakt dieselbe Songauswahl — ein zweiter Versuch für einen anderen Vorschlag war damit zwecklos. Hintergrund: Die gezogenen Zufallszahlen werden absichtlich zwischengespeichert, damit sich die Songliste nicht bei jedem Tastendruck im Suchfeld neu sortiert. Der Zauberstab mischt sie jetzt vorher gezielt neu. Beim gewichteten Zufall bleibt die Gewichtung dabei erhalten: gut bewertete und lange nicht gespielte Songs kommen weiterhin bevorzugt dran, nur eben nicht mehr in immer derselben Reihenfolge. Bei allen anderen Sortierungen ändert sich nichts.

### Bugfixes
- **Namensgleiche Dateien aus verschiedenen ZIPs überschreiben sich nicht mehr gegenseitig.** Enthielten zwei ZIP-Pakete eine Varianten- oder Lyrics-Datei mit identischem Dateinamen (etwa „vocal.mp3"), verwies der zweite Import bisher stillschweigend auf die Datei des ersten. Jetzt wird der Inhalt verglichen und bei Abweichung ein eindeutiger Name mit Zusatz „_1" vergeben; echte Doppel-Importe derselben Datei bleiben wie gehabt ohne Duplikat.

### Hinweise
- Kann ein Song die Ziel-BPM nicht erreichen (Stellbereich 50–150 %), wird so nah wie möglich herangefahren und die BPM-Anzeige im Player erscheint in Warnfarbe; der Tooltip nennt den Grund. Songs ohne hinterlegte BPM laufen unverändert mit 100 % — die Anzeige zeigt dann „—". Das Potential-Fenster listet Songs ohne BPM-Wert bereits auf.
- Da das heutige Tempo nur ganze Prozent kennt, kann die tatsächliche BPM-Zahl um bis zu einen halben Schlag pro Minute vom Ziel abweichen.

---

## 0.123 — Zoomen mit STRG + Mausrad, Zufallssortierungen (2026-07-18)

### Neue Features
- **STRG + Mausrad zoomt jetzt überall dort, wo es bisher nur die Plus-/Minus-Knöpfe gab.** Betroffen sind die Sequenzliste, das Lyrics-Fenster, das Notizen-Widget, der Class Designer, die Kurve im Abendplaner und die beiden Wellenformen im Beat-Snap-Dialog. Der Mauszeiger muss dabei über dem jeweiligen Inhalt stehen. Gezoomt wird in denselben Schritten und innerhalb derselben Grenzen wie über die Knöpfe — die Prozentanzeige läuft mit, und der beim Beenden gespeicherte Zoomstand verhält sich unverändert. Bei feinauflösenden Mausrädern und Touchpads werden Teilschritte aufaddiert, sodass eine gefühlte Rasterstufe auch genau einem Zoomschritt entspricht.
- **Zwei neue Sortierungen: „Reiner Zufall" und „Gewichteter Zufall".** Beide stehen im Sortier-Auswahlfeld von Songliste und Playlist-Manager und wirken damit auch beim automatischen Befüllen über den Magischen Button — ist eine der beiden ausgewählt, übernimmt sie dort die Reihenfolge. „Reiner Zufall" mischt gleichverteilt. „Gewichteter Zufall" zieht nach dem Empfehlungs-Score, also Qualität mal Tage seit dem letzten Spielen: gut bewertete und lange nicht gespielte Songs kommen deutlich wahrscheinlicher nach vorn, schwach bewertete behalten aber eine echte Restchance und verschwinden nicht dauerhaft aus dem Programm. Gemessen an einer Bibliothek mit 526 Songs landet ein Titel mit Qualität 10 in rund 12 % der Ziehungen in den ersten zwanzig, einer mit Qualität 1 in rund 1 %.
- **Songs ohne Bewertung werden beim gewichteten Zufall wie mittelmäßige behandelt.** Eine fehlende Bewertung ist in der Datenbank eine Null, und eine Null im Score hätte bedeutet: dieser Song kommt nie dran — und kann deshalb auch nie bewertet werden. Beim gewichteten Zufall zählt eine fehlende Bewertung darum als neutrale 5, sodass der unbewertete Altbestand nach und nach ins Programm rutscht. Die normale Empfehlungs-Sortierung rechnet unverändert mit dem echten Wert.
- **Ein heute bereits gespielter Song bleibt hinten.** Null Tage seit dem letzten Spielen ergeben auch beim gewichteten Zufall das kleinstmögliche Gewicht — am selben Abend soll derselbe Titel nicht erneut vorgeschlagen werden.

### Hinweise
- Die gewürfelte Reihenfolge bleibt stabil, solange nur gefiltert wird — beim Tippen im Suchfeld oder einem Genre-Wechsel springt die Liste also nicht. Neu gemischt wird beim Programmstart und jedes Mal, wenn im Auswahlfeld erneut auf eine der beiden Zufallssortierungen umgeschaltet wird.
- Ohne gedrückte STRG-Taste bleibt das Mausrad wie bisher das Scrollrad — das Zoomen greift ausschließlich mit Modifikator.

---

## 0.122 — Sortierung nach Einfügedatum, mehr Cuesheets beim Auto-Sync erkannt (2026-07-17)

### Neue Features
- **Sortierung nach Einfügedatum.** Das Sortier-Auswahlfeld in Songliste und Planner hat einen neuen Eintrag „Einfügedatum" — die zuletzt aufgenommenen Songs stehen oben. Songs ohne gespeichertes Einfügedatum (der bei der Migration übernommene Altbestand) erben das Datum der Erstaufnahme aus der Konfiguration und bilden damit einen gemeinsamen Block hinter allen späteren Zugängen. Der Zufalls-Tiebreaker wirkt auch hier und mischt Songs mit gleichem Datum bei jedem Programmstart neu durch.
- **Die Datumsspalte wandert mit der Sortierung mit.** Wird nach Einfügedatum sortiert, zeigt die Spalte „Gespielt" in Songliste und Planner das Einfügedatum und heißt „Hinzugefügt"; wird nach Empfehlung sortiert, zeigt dieselbe Spalte den Empfehlungs-Score und heißt „Score" — bei jeder anderen Sortierung steht dort wie bisher das Datum, an dem der Song zuletzt in dieser Gruppe gespielt wurde. So steht immer die Zahl in der Tabelle, nach der gerade sortiert wird. Geerbte Daten des Altbestands erscheinen grau und kursiv mit einem erklärenden Tooltip, damit sie nicht mit einem echten Einfügedatum verwechselt werden.
- **Score-Spalte bei der Empfehlung.** Beim Sortieren nach „Empfehlung" zeigt die zweite Spalte den zugrunde liegenden Score als Ganzzahl — das Produkt aus Qualität und Tagen seit dem letzten Spielen. Damit ist direkt ablesbar, warum ein Song oben steht. Die angezeigte Zahl stammt aus genau derselben Berechnung wie die Sortierung selbst, kann also nicht davon abweichen.

### Verbesserungen
- **Abschnitts-Labels in Klammern am Zeilenanfang werden erkannt.** Manche Cuesheets schreiben das Label geklammert vor den ersten Call derselben Zeile — etwa `(Figure): HEADS SQUARE THRU and go - four hands and go`. Solche Zeilen wurden bisher komplett übersehen, der Auto-Sync fand in diesen Blättern gar keine Abschnitte und brach ab. Jetzt gilt der Klammerinhalt als Label und der Rest der Zeile als Inhalt. Kombinierte Labels wie `(Middle Break & Closer):` sind dabei eingeschlossen. Ohne Klammern bleibt es bei der bisherigen strengen Prüfung, damit eine Liedzeile nicht versehentlich als Überschrift gilt.
- **Zusätzliche Schreibweisen in der Schlüsselwort-Liste:** `OPEN`, `CLOSE`, `BREAKS` sowie die auf Blättern real vorkommende Falschschreibung `MIDLE`. Eine Überschrift zählt nur, wenn alle ihre Wörter bekannt sind — ein einziges unbekanntes Wort ließ bisher die ganze Zeile mitsamt Opener und Closer durchfallen.

### Bugfixes
- **Songliste: nie gespielte Songs wurden bei der Sortierung als „heute gespielt" behandelt.** In der Songliste fehlte die Datumsgrenze aus der Konfiguration, die der Planner längst nutzt. Dadurch galt ein nie gespielter Song beim Sortieren nach „Zuletzt gespielt" bzw. „Empfehlung" als 0 Tage her und landete am Ende statt am Anfang — genau umgekehrt zur Absicht. Jetzt wird auch in der Songliste ab der gesetzten Datumsgrenze gerechnet, sodass lange nicht gespielte und nie gespielte Songs korrekt nach oben kommen. Der Planner war nie betroffen.
- **Getrennter Opener und Break wurden zu einem Block verschmolzen.** Enthielt ein Blatt unter dem Opener eine zweite Überschrift mit einem bis dahin unbekannten Wort (z. B. `BREAK & CLOSE`), fiel diese Überschrift durch und der Opener-Block wurde stillschweigend über beide Abschnitte gezogen und für Opener, Middle Break und Closer gleichermaßen verwendet. Die drei Teile zeigen jetzt auf ihre jeweils eigenen Textblöcke.

### Hinweise
- Gemessen an der Testbibliothek (218 Cuesheets) steigt die Erkennung von 199 auf 204 Blätter. Alle bereits funktionierenden Blätter liefern unveränderte Positionen. Von den verbleibenden Fehlschlägen sind die meisten reine Songtexte ohne Abschnitts-Überschriften — dort gibt es nichts zu teilen, sie werden weiterhin bewusst abgelehnt statt geraten.

---

## 0.121 — Sync-Punkte im Massenlauf setzen (2026-07-15)

### Neue Features
- **Sync-Punkte für viele Songs auf einmal setzen.** Der Reiter „Ohne SyncPunkte" im Potential-Fenster hat jetzt zwei Schaltflächen unter der Liste: „Selektierte Lieder ergänzen" (Mehrfachauswahl in der Liste ist neu möglich) und „Alle Lieder ergänzen" für die komplette Liste. Gerechnet wird exakt wie beim manuellen Sync im Lyric-Fenster: der Song-Body wird in 7 gleiche Abschnitte geteilt, die Abschnitts-Überschriften im Cuesheet gesucht und daraus bis zu 14 Anker gesetzt. Alle Lyric-Formate werden unterstützt (HTML, RTF, DOCX, PDF, TXT) — die Lyric-Dateien selbst werden dabei nicht verändert, die Punkte liegen wie bisher in der Datenbank.
- **Zeitschätzung vor dem großen Lauf.** Ab 15 Songs laufen zuerst 5 als Probelauf, deren Dauer gemessen und die Gesamtlaufzeit hochgerechnet wird — mit Rückfrage, ob der Rest laufen soll. Die 5 Probe-Songs sind dabei bereits fertig eingetragen und werden nicht erneut berechnet. Gleiches Muster wie beim Songanfang-Reiter.

### Hinweise
- **Voraussetzungen je Song:** BPM und Songanfang müssen gesetzt sein, die Lyric-Datei muss auffindbar sein. Ist ein Song-Ende gespeichert, wird es verwendet, sonst aus 448 Beats und der BPM abgeleitet.
- **Übersprungene Songs werden namentlich mit Grund gemeldet** — entweder weil eine Voraussetzung fehlt oder weil sich im Cuesheet keine Abschnitte erkennen ließen. Nichts wird stillschweigend ausgelassen.

### Bugfixes
- **Auslieferungs-Datenbank enthielt Daten aus der Entwicklungsumgebung.** Die mitgelieferte Datenbank im Vollpaket wird aus der Entwicklungs-Datenbank erzeugt und dabei geleert — bislang blieben die Tabellen `notes` und `song_properties` jedoch gefüllt zurück, obwohl die zugehörigen Songs und Lokationen längst gelöscht waren. Beide werden jetzt mitgeleert, ebenso `photos` und `potential_ignored`. Betraf alle Versionen bis einschließlich 0.120; das Update-ZIP war nie betroffen, da es keine Datenbank enthält.
- **Der Build bricht jetzt ab, wenn Benutzerdaten in der Auslieferungs-Datenbank übrig bleiben** — inklusive Warnung bei neuen, noch nicht eingeordneten Tabellen. Vorher wurden die Zahlen nur ausgegeben und nicht geprüft.

## 0.120 — Sync-Punkte gemeinsam verschieben & Songstart daran gekoppelt (2026-07-14)

### Neue Features
- **Alle Sync-Punkte auf einmal um eine Sekunde verschieben.** Im Sync-Modus des Lyric-Fensters gibt es beim Rechtsklick jetzt das Untermenü „Alle Sync-Punkte verschieben" mit den Einträgen „1 Sek. früher (−1 s)" und „1 Sek. später (+1 s)". Damit lässt sich ein durchgehender Versatz korrigieren, wenn der Text insgesamt konstant zu früh oder zu spät mitläuft, ohne jeden Punkt einzeln nachziehen zu müssen. Kein Sync-Punkt rutscht dabei vor den Songanfang (bei 0:00 wird abgeschnitten). Das Menü ist verfügbar, sobald überhaupt Sync-Punkte gesetzt sind — auch bei Rechtsklick auf eine leere Textstelle.
- **Songstart bleibt an den frühesten Sync-Punkt gekoppelt.** Der gespeicherte Musik-Startpunkt eines Songs folgt jetzt automatisch dem frühesten Sync-Punkt (dem Beginn des Openers). Egal ob per „Alle verschieben", Einzel-Verschieben, Löschen oder direktem Zeit-Edit — sobald sich der früheste Sync-Punkt bewegt, wird der Songstart parallel auf dieselbe Zeit gesetzt. So sind Opener-Beginn und Songstart immer verschränkt, was besonders für Singing Calls korrekt ist. Der Start-Countdown zieht sofort mit und zählt zur neuen Startzeit. Bei „Alle verschieben (±1 s)" wandert zusätzlich der Song-Endpunkt um denselben Betrag mit, sodass die Body-Länge unverändert bleibt. Songs ohne gesetzten Startpunkt (z. B. Patter ohne Body) bleiben unberührt — es wird kein Startpunkt erfunden.

## 0.119 — Potential-Dashboard neu strukturiert: Übersichts-Reiter, Workflow-Reihenfolge & Lesbarkeits-Fixes (2026-07-08)

### Neue Features
- **Neuer Start-Reiter „Übersicht" im Potential-Dashboard.** Beim Öffnen des Fensters landet man jetzt zuerst auf einer Übersicht mit Schaltflächen zu allen Reitern, gruppiert nach dem sinnvollen Arbeitsablauf. Jeder Button springt zum passenden Reiter und trägt ein Badge mit der Anzahl offener Punkte: eine Zahl bei den schnellen Prüfungen, ein Haken „✓" wenn nichts mehr offen ist, und „[ ? ]" bei den aufwändigen Datei-Prüfungen (Ohne MP3 / Inkompatibles Format) — die ermitteln ihre echte Zahl erst, wenn man den Reiter tatsächlich öffnet, damit die Übersicht schnell bleibt. Die Buttons brechen bei schmalem Fenster automatisch in die nächste Zeile um.
- **Zwei Abhängigkeitsketten sind mit Pfeilen sichtbar gemacht.** Auf der Übersicht zeigen große Pfeile die Reihenfolge an, in der Schritte aufeinander aufbauen: die **Patter-Kette** „Ohne Loop → Ohne BeatSnap → Loop optimieren" und die **Singing-Kette** „Ohne Lyrics → Ohne Liedpunkte → Ohne Songanfang → Ohne SyncPunkte". So ist auf einen Blick erkennbar, dass z. B. SyncPunkte einen gesetzten Songanfang voraussetzen.
- **Sticky „⌂"-Button links in der Reiterleiste.** Ein kleiner Haus-Button ganz vorne bleibt immer sichtbar — auch wenn man weit nach rechts durch die Reiter gescrollt hat — und bringt per Klick sofort zurück zur Übersicht.

### Verbesserungen
- **Alle Potential-Reiter in eine logische Reihenfolge gebracht.** Statt einer gewachsenen Liste sind die Reiter jetzt in vier Gruppen sortiert: **Basis** (gilt für jeden Song: Ohne MP3, Inkompatibles Format, Ohne BPM, Ohne Genre, Ohne Qualität, Ohne ERR, Quality + ERR füllen, Metadaten füllen), **Patter-Kette**, **Singing-Kette** und **Wartung** (Leere Lokationen, Verwaiste Historie, Massen-Löschen). „Ohne BPM" sitzt bewusst in der Basis-Gruppe, weil es sowohl Patter als auch Singings betrifft.
- **Die Scroll-Pfeile der Reiterleiste sind wieder brauchbar.** Weil so viele Reiter nicht mehr nebeneinander passen, blendet Qt Scroll-Pfeile (‹ ›) ein. Diese waren im Windows-11-Theme zu einem winzigen, kaum klickbaren Bereich zusammengequetscht — sie haben jetzt genügend Platz und sind normal bedienbar.

### Bugfixes
- **Windows-11-Theme: Menü- und Reiter-Texte beim Überfahren waren kaum lesbar.** Beim Hovern (und bei selektierten Menüeinträgen) lag dunkler Text auf dunkelblauem Hintergrund. Menüleiste, Kontext-/Aufklapp-Menüs und alle Reiterleisten zeigen den Text in diesem Zustand jetzt in Weiß — gut lesbar. Betrifft die ganze App, nicht nur das Potential-Fenster.

## 0.118 — Neuer „Ohne Songanfang"-Reiter mit CHECK-Prüf-Marker · Warte-Overlay · „Ohne BPM" schlanker (2026-07-07)

### Neue Features
- **Neuer Reiter „Ohne Songanfang" im Potential-Dashboard.** Er listet alle Singing Calls, für die noch kein Musik-Startpunkt gesetzt ist — bewusst auch solche ohne hinterlegte Lyrics, denn die automatische Erkennung (aus 0.117) arbeitet rein auf der Audiospur und braucht keine Lyrics. Darunter drei Schaltflächen: „Selektierte analysieren" (nur die in der Tabelle markierten), „Offene analysieren" (alle noch offenen Kandidaten der Liste) und „ALLE analysieren". Der letzte Button läuft über sämtliche Singing Calls — auch über solche mit bereits gesetztem Startpunkt — und überschreibt bestehende Werte; deshalb kommt hier vorab eine deutliche Sicherheitsabfrage. Für jeden erkannten Song werden Anfang **und** Ende gesetzt (das Ende ergibt sich starr aus Anfang + 448 Beats). Ab 15 zu bearbeitenden Liedern wird — wie beim „Ohne BPM"-Reiter — zunächst anhand einer Stichprobe von fünf Songs die voraussichtliche Gesamtdauer geschätzt und zur Bestätigung angezeigt; diese fünf werden dabei gleich mitgespeichert, nicht verworfen. Die Analyse läuft im Hintergrund, damit die Wiedergabe nicht stockt.
- **„CHECK: START": unsichere Erkennungen landen automatisch auf einer prüfbaren To-Do-Liste.** Bei der Stapel-Analyse ist niemand dabei, der jeden Vorschlag einzeln bestätigen könnte. Damit trotzdem jeder Singing Call ausgestattet wird und die Wackelkandidaten nicht untergehen, verfährt Callers Caddy so: Der Start-/Endpunkt wird für **alle** erkannten Songs gesetzt — die Erkennung meldet aber je Song, ob sie sicher oder mehrdeutig war. Songs mit mehrdeutigem Ergebnis erhalten zusätzlich das neue Genre **„CHECK: START"**. Der Caller kann die Songliste nach diesem Genre filtern und gezielt genau die Lieder nachhören, bei denen die Automatik unsicher war — eine automatisch gepflegte Prüf-Liste, ganz analog zum bekannten „NEW"-Genre bei neu importierten Songs.

  Der Marker räumt sich selbst wieder ab: Sobald der Caller den Anfang eines solchen Songs im Sync-Modus neu setzt (egal ob er den Auto-Vorschlag übernimmt oder von Hand klickt), verschwindet „CHECK: START" bei diesem Song automatisch — die To-Do-Liste leert sich also von selbst, während man sie abarbeitet. Ebenso entfernt eine erneute Stapel-Analyse den Marker, wenn ein Song diesmal sicher erkannt wird. Der manuelle Weg über den Sync-Button vergibt selbst nie einen Marker (dort sieht der Caller die „Mehrdeutig"-Warnung ja direkt und entscheidet sofort). „CHECK: START" ist das erste einer wiederverwendbaren „CHECK: <Thema>"-Reihe solcher Prüf-Marker.

### Verbesserungen
- **Während die automatische Start-/Ende-Erkennung läuft, erscheint jetzt ein „Bitte warten"-Overlay** (wie beim Loop-Finder). Bisher gab es nur einen kleinen Statustext, sodass der Eindruck entstehen konnte, man könne bereits weiterarbeiten, während die Audio-Analyse für die Sync-Punkte noch rechnete. Das Overlay verschwindet automatisch, sobald das Ergebnis vorliegt (bzw. der Bestätigungsdialog erscheint) oder die Analyse fehlschlägt.
- **„Ohne BPM": Probelauf nur noch ab 15 Liedern — und ohne doppelte Arbeit.** Die vorgeschaltete Zeitschätzung (Probelauf mit 5 Songs) wird jetzt erst ab 15 zu bearbeitenden Liedern angeboten; darunter läuft die BPM-Ermittlung ohne Umweg direkt durch. Zusätzlich werden die 5 Songs des Probelaufs nicht mehr verworfen, sondern gleich ermittelt und eingetragen — der eigentliche Lauf verarbeitet danach nur noch die restlichen Lieder. Das spart die doppelte Analysezeit für die Stichprobe.

## 0.117 — Automatische Singing-Erkennung · Stream-Schutz bei Play-Regeln · Neuer „Ohne BPM"-Reiter (2026-07-06)

### Neue Features
- **Automatische Erkennung von Anfang und Ende eines Singing Calls.** Im Sync-Modus gibt es neben „Anfang & Ende selbst setzen" jetzt die Option „Automatisch erkennen": Callers Caddy analysiert die Musik und schlägt Start- und Endpunkt des Singing-Call-Bodys vor, aus denen anschließend die sieben Abschnitte (starr 7 × 64 = 448 Beats) und die Sync-Punkte abgeleitet werden — das erspart das manuelle Setzen bei hunderten Liedern.

  So arbeitet die Erkennung: Zunächst wird ein **Beat-Raster** berechnet und an der in der Datenbank gespeicherten **BPM verankert** — dieser Tempo-Anker verhindert, dass das Raster auf einer Subharmonischen (halbes/doppeltes Tempo) einrastet und dadurch unmögliche Grids erzeugt. Pro Beat werden ein **beat-synchrones log-Mel-Timbre** (Spektralform), die Energie und ein **Kick-Transient** bestimmt. Über das Timbre findet eine **Foote-Checkerboard-Novelty** die **Arrangement-Kanten** (Besetzungswechsel), denn Intro und Outro brechen klanglich mit dem Body, auch wenn die Melodie durchläuft. Ein **8-Zinken-Kamm** bewertet gezielt die Position, an der gleichzeitig an allen acht Sektionsgrenzen (c, c+64, …, c+448) eine Kante liegt — das ist typisch für den Body und hebt ihn von zufälligen Einzelkanten ab. Anschließend rasten ein **Downbeat-Snap** (Kick-Akzent modulo 8) auf die Phrasen-„1" und ein **Chroma-Figuren-Paar-Tiebreak** gegen den häufigen **±32-Beat-Halbsektions-Alias** ein; eine kleine **Kalibrierung (+2 Beats)** gleicht die systematische Klick-Latenz aus.

  Das Ergebnis kommt stets als **Vorschlag mit Confidence-Wert** (der Kamm-Margin, also der Abstand der besten zur zweitbesten Position) — nie als stilles Überschreiben. Der Nutzer sieht Anfang und Ende und wählt „Übernehmen", „Selbst setzen" oder „Abbrechen"; liegt die Confidence unter der aus der Validierung bestimmten Schwelle, erscheint zusätzlich ein Prüf-Hinweis. Die Analyse läuft in einem Hintergrund-Thread, damit die Wiedergabe nicht stockt. Bewusst als **Vorschlag** ausgelegt: Je nach Musik kann er ein, zwei Beats danebenliegen und wird dann kurz von Hand nachgezogen — die Zeitersparnis über die Masse bleibt.
- **Neuer Reiter „Ohne BPM" im Potential-Dashboard.** Er listet alle Songs, für die keine BPM gesetzt ist oder deren Wert unplausibel außerhalb des Square-Dance-Bereichs liegt (kleiner 100 oder größer 150) — allesamt Kandidaten für die automatische BPM-Ermittlung. Darunter drei Schaltflächen: „Selektierte ermitteln" (nur die in der Tabelle markierten), „Alle leeren ermitteln" (alle ganz ohne BPM) und „ALLE ermitteln". Der letzte Button lässt den BPM-Finder über die komplette Bibliothek laufen und überschreibt dabei auch bereits gute Werte — deshalb kommt hier vorab eine deutliche Sicherheitsabfrage. Bei mehr als fünf Songs wird zunächst anhand einer Stichprobe von fünf Liedern die voraussichtliche Gesamtdauer geschätzt und zur Bestätigung angezeigt (gleiches Verfahren wie beim Stapel-Loop-Finder). Die BPM-Erkennung läuft im Hintergrund, damit die Wiedergabe nicht stockt.
- **Existenz-Prüfung nach dem BPM-Lauf.** Songs, deren Audiodatei in keinem Musikordner mehr auffindbar ist, werden nun am Ende namentlich aufgelistet, statt stillschweigend übersprungen zu werden und unerklärt als Kandidat stehenzubleiben. Der Hinweis verweist auf den Reiter „Ohne MP3", der zum Aufräumen solcher verwaisten Einträge gedacht ist.

### Verbesserungen
- **Der Auto-Loop-Finder hält den Song jetzt zurück, bis er fertig ist.** Wird per Regel beim Abspielstart automatisch ein Loop gesucht, startet der Song erst hörbar, wenn die Analyse abgeschlossen ist — der Loop ist damit garantiert schon gesetzt, wenn die Musik läuft.
- **BPM-Erkennung präziser: Suchband auf 100–150 BPM eingegrenzt.** Der Auto-BPM-Detektor (Onset-Strength-Envelope + Comb-Filter-Bank) suchte bisher in einem weiten Tempobereich und rastete gelegentlich auf einer Subharmonischen ein (halbes/doppeltes Tempo — z. B. „Waltzing Matilda" fälschlich als 90-BPM-Walzer). Das engere Band deckt den für Square Dance typischen Bereich ab (weniger als eine Oktave, 150/100 = 1,5) und beseitigt diese Oktavfehler zuverlässig. Davon profitieren die Auto-BPM-Erkennung, die neue Body-Erkennung (als Tempo-Anker) und der Reiter „Ohne BPM" gleichermaßen.

### Bugfixes
- **Kein Ruckeln mehr beim Abspielstart, wenn eine Regel gleichzeitig das Layout umbaut.** Regeln, die beim Starten oder Fortsetzen eines Songs sofort einen Layout-Wechsel auslösen (z. B. Dual-View mit Lyrics und Sequenzen einblenden), ließen den gerade startenden Audio-Stream hörbar stocken — auf leistungsschwächeren Rechnern besonders deutlich. Solche stream-gefährdenden Aktionen laufen jetzt zuerst zu Ende (während noch Stille herrscht), und erst danach setzt die Wiedergabe hörbar ein. Regeln ohne Layout-Wechsel starten wie bisher ohne jede Verzögerung.
- **Auto-Loop-Regel: leeres Preset-Feld.** Beim Einrichten der Regel „Auto-Set Best Loop" blieb das Feld für das Loop-Preset leer, solange der Loop-Finder-Reiter zuvor noch nie geöffnet worden war. Die Auswahl ist jetzt unabhängig davon immer gefüllt; zusätzlich zeigt sie den seit einiger Zeit umbenannten Standardwert wieder korrekt an (bestehende Regeln mit dem alten Namen funktionieren unverändert weiter).

## 0.116 — Evening Planner: Feinschliff & Shuffle · Loop-Finder: neue Strategie · Statistik: Mehrfachauswahl (2026-07-05)

### Neue Features
- **Evening Planner: Shuffle-Modus für Songvorschläge.** Ein neuer Umschalt-Button in der oberen Leiste steuert den Zufalls-Tiebreaker: Haben mehrere Songs denselben Score, wird bei aktivem Shuffle zufällig statt immer alphabetisch der oberste gewählt (innerhalb einer Sitzung stabil, springt also nicht bei jedem Neuaufbau). Der Schalter teilt sich dieselbe Einstellung wie der Tiebreaker in Songliste und Planner und merkt sich seinen Zustand über Neustarts hinweg.
- **Tiebreaker-Einstellung wird jetzt dauerhaft gemerkt.** Der Zufalls-Tiebreaker in Songliste und Planner stand nach jedem Programmstart wieder auf „an" — sein Zustand wird nun gespeichert und beim nächsten Start wiederhergestellt.
- **Auto-Loop-Finder: neue Strategie „Bestes Vielfaches von 8 Beats"** – Ergänzung zur bisherigen „Bestes Vielfaches von 64 Beats". Sinnvoll für Musik außerhalb des klassischen Square-Dance-Rasters, bei der eine feste 64-Beat-Phrasenlänge nicht passt, aber trotzdem noch ein sauberer, taktgenauer Loop-Punkt gewünscht ist.
- **Statistik-Widget: Mehrfachauswahl in allen 3 Spalten** (TOP/FLOP/Nie gespielt) per Shift-/Strg-Klick. „Zur Playlist hinzufügen" und „Zu Notizen" wirken jetzt auf die gesamte Auswahl; Quality/ERR ±1 sind bei Mehrfachauswahl bewusst ausgegraut, da es dafür keine einheitliche Basis gibt.

### Verbesserungen
- **Evening Planner ist jetzt ein freies Fenster** und dockt nicht mehr ungewollt an anderen Bereichen an, wenn man ihn verschiebt.
- **Redundanter Übernehmen-Button (grüner Haken) im Evening Planner entfernt.** Seine Aufgabe – bestätigte Songs in die Playliste zu übertragen – übernimmt vollständig der Button „Übernehmen zur Playliste" in der unteren Leiste (inkl. Sicherheitsabfrage bei noch nicht bestätigten Songs).

### Bugfixes
- **Evening Planner: Songs mit beiden Typ-Markierungen (Patter *und* Singing) landen jetzt mit dem korrekten Typ in der Playliste.** Bisher wurde ein solcher Song, der in einem Singing-Slot geplant war, beim Übertragen fälschlich als Patter (P) eingetragen. Nun behält er die Rolle seines Slots (S bzw. P). Der Weg „Zu Notizen" war davon nicht betroffen.

## 0.115 — Regeln: Mehrfachauswahl für Export, Duplizieren & Löschen (2026-07-02)

### Neue Features
- **Regelliste unterstützt jetzt Mehrfachauswahl** (Shift/Strg-Klick wie gewohnt).
- **Export exportiert nur die Auswahl**, sofern etwas markiert ist — ohne Auswahl wird wie bisher alles exportiert.
- **Duplizieren dupliziert alle markierten Regeln** auf einmal (System- und User-Regeln als neue User-Regel-Kopien).
- **Löschen löscht alle markierten User-Regeln auf einmal**, weiterhin mit Sicherheitsabfrage (jetzt mit Anzahl bei mehreren Regeln). System-Regeln in der Auswahl werden dabei ignoriert, da sie sich nie löschen lassen.

## 0.114 — Sync-Punkte: Statusfarbe & robust gegen Text-Edits (2026-07-02)

### Neue Features
- **Sync-Button zeigt jetzt den Fortschritt per Farbe:** Rot, solange für die aktuelle Musik-/Lyric-Variante noch kein einziger Sync-Punkt gesetzt ist; normal (Theme-Standard), während der Sync-Modus aktiv ist (Punkte werden gerade erfasst); grün, sobald Start, Ende und mindestens ein Sync-Punkt vorhanden sind — Zeichen dafür, dass hier nichts mehr zu tun ist.

### Bugfixes
- **Sync-Punkte überleben jetzt das Bearbeiten des Lyric-Texts:** Bisher wurden Sync-Punkte (Zeichenpositionen im Text) nach dem Löschen/Ändern von Zeilen im Editor beim nächsten Rendern stillschweigend übersprungen, sobald ihre Position hinter das (kürzere) Textende rutschte — sichtbar wirkte das wie ein kompletter Datenverlust, obwohl die Werte noch in der Datenbank standen. Callers Caddy vergleicht beim Speichern eines In-App-Edits jetzt den Text vor und nach der Änderung per Diff: Sync-Punkte in unverändert gebliebenen Abschnitten bleiben exakt erhalten und werden automatisch nachgeführt, nur Punkte auf tatsächlich gelöschten/geänderten Zeilen entfallen (müssen dort neu gesetzt werden).

## 0.113 — Robustere Lyrics-Anzeige & Countdown-Feinschliff (2026-07-01)

### Bugfixes
- **Zeilenumbruch bricht bei defektem Lyrics-HTML nicht mehr grossflächig ab:** Manche aus Word exportierten Cuesheets enthalten nicht geschlossene Formatierungs-Tags (z. B. ein verwaistes `<nobr>`). Das ließ bisher den kompletten restlichen Song ohne automatischen Zeilenumbruch anzeigen — der Text lief über den Rand hinaus statt umzubrechen. Callers Caddy erkennt das jetzt beim Laden, warnt und bietet an, die Datei dauerhaft zu reparieren. Bei RTF/DOCX (dort ist das HTML nur eine abgeleitete Darstellung, keine eigene Nutzerdatei) wird still automatisch bereinigt, ohne Rückfrage.

### Verbesserungen
- **Start-Countdown-Overlay: unnötigen Overhead entfernt.** Das Overlay hat bisher bei jedem 50ms-UI-Tick die Fenstergeometrie neu gesetzt und sich in den Vordergrund geholt — das passiert jetzt nur noch beim erstmaligen Erscheinen bzw. wenn sich die Hauptfenster-Position tatsächlich geändert hat. Die Zahlenanzeige bleibt unverändert flüssig (läuft weiter über den eigenen Puls-Timer).

## 0.112 — Potential-Fenster: Tabs für fehlende Lied- und Sync-Punkte (2026-06-30)

### Neue Features
- **Zwei neue Reiter im Potential-Fenster** – direkt hinter „Ohne Lyrics":
  - **„Ohne Liedpunkte":** listet alle Singing Calls (mit Lyrics), bei denen **Liedstart und -ende** noch nicht beide gesetzt sind.
  - **„Ohne SyncPunkte":** listet alle Singing Calls (mit Lyrics), die noch **keine Sync-Punkte** haben.
  - Per **Doppelklick** springt man direkt ins Lyrics-Fenster, und **Maus + Fokus liegen sofort auf dem Sync-Button** – der nächste Arbeitsschritt ist ohne Suchen griffbereit.
  - Wie bei „Ohne Lyrics" mit Anzahl-Badge im Reiter und „Ignorieren"-Funktion. Gelistet werden bewusst nur Songs mit Lyrics, da sich die Punkte sonst gar nicht setzen lassen (Songs ohne Lyrics stehen weiterhin unter „Ohne Lyrics").

### Bugfixes
- **Win11-Theme: Plus/Minus-Knöpfe der Zahlenfelder immer sichtbar.** Die Auf/Ab-Schaltflächen in Eingabefeldern (z. B. Tempo) waren vorher nur beim Drüberfahren mit der Maus zu sehen. Jetzt sind sie dauerhaft sichtbar und werden beim Hover dezent dunkler.

## 0.111 — ZIP-Import: mehr Varianten erkannt, bessere Titel & gemerkter Ordner (2026-06-30)

### Verbesserungen
- **ZIP-Import erkennt mehr Tonart- und Stimm-Varianten:** Pakete im Rhythm-Records-Schema (z. B. „Jolene", RR 409) werden jetzt korrekt aufgeschlüsselt — **Female Vocal**, **Male Vocal** und **Harmony 1/2/3** landen als benannte Varianten statt mehrfach als „Instrumental". Auch Labels mit Tonart- oder Index-Kürzel wie `RR 409F` oder `RR 409h1` werden zuverlässig als Label erkannt.
- **Saubere Songtitel aus dem Paket statt aus dem ZIP-Dateinamen:** Bei Paketen mit kryptischem Download-Namen (z. B. `ego_112_-_go_tell_it_on_the_mountain`, `GP509MP3_…_0e76qf`) oder reinem Label-Namen (`STING 22209`) übernimmt CC Titel und Label jetzt aus der enthaltenen Haupt-MP3. Vorbelegt wird damit z. B. **„Go Tell It On The Mountain / EGO 112"** oder **„I Think We're Alone Now / STING 22209"** statt des rohen Dateinamens.

### Bugfixes
- **ZIP-Import merkt sich den zuletzt genutzten Ordner:** Der Dateidialog beim ZIP-Import öffnet wieder dort, wo zuletzt importiert wurde. Bisher wurde der Pfad nur beim Datei-/Ordner-Import gespeichert, beim ZIP-Import nicht — der Dialog sprang dadurch jedes Mal an die falsche Stelle.

## 0.110 — Start-Countdown, Liedrahmen im Player & Sync-Feinschliff (2026-06-27)

### Neue Features
- **Start-Countdown vor dem Liedeinsatz:** Ein großes, halbtransparentes Vollbild-Overlay zählt vor dem Gesangsstart die Beats herunter — im Takt der Musik und mit kurzem Aufleuchten bei jedem Beat. So weiß man genau, wann der erste Call kommt, ohne auf die Uhr zu schauen. Die letzten zwei Beats bleiben bewusst still (kein Overlay), damit der Blick frei ist, wenn es losgeht.
  - Rein visuell — der Countdown greift **nicht** in die Audiowiedergabe ein und erscheint auch über freischwebenden Fenstern.
  - Benötigt eine hinterlegte **BPM** und einen gespeicherten **Liedstart** (aus dem Auto-Sync, siehe unten). Folgt automatisch dem Tempo-Regler.
  - Ein-/ausschaltbar über **Einstellungen → Anzeige → „Start-Countdown anzeigen"** (standardmäßig an). Vollständig übersetzt (DE/EN/JA).
- **Liedrahmen im Statusleisten-Player:** Die sieben Abschnittsstreifen im Mini-Player der Statusleiste liegen jetzt exakt zwischen gespeichertem **Liedstart und -ende** — der Balken zeigt damit den tatsächlich gesungenen Bereich statt einer pauschalen Aufteilung. Sind keine Zeiten gespeichert, bleibt die bisherige Darstellung erhalten.
- **Auto-Sync nutzt gespeicherte Start-/Endzeiten (BL-161):** Sind für einen Song bereits Start und Ende hinterlegt, bietet der erste Sync drei Wege an: **„Jetzt berechnen"** (die sieben Abschnitte sofort aus den gespeicherten Zeiten ableiten — ganz ohne Mitlaufen), **„Neu messen"** oder **„Manuell"** setzen.

### Verbesserungen
- **Synchron scrollende Lyrics: aktuelle Zeile zentriert:** Die gerade gesungene Zeile rastet jetzt in der **Mitte** des Lyrics-Fensters ein (vorher im oberen Viertel) — gleich viel Vorschau nach unten wie Kontext nach oben.

### Bugfixes
- **Kein Zittern mehr beim Auto-Scroll:** Kleine Rückwärts-Sprünge durch Mess-Ungenauigkeit der Wiedergabeposition werden jetzt unterdrückt, sodass der Text ruhig läuft. Echte Rücksprünge (z. B. wiederholte Sequenz oder Loop) werden weiterhin sauber nachvollzogen.
- **Stabilere Sync-Marker:** Marker, die rechnerisch außerhalb des Textes liegen würden, werden übersprungen statt falsch platziert; ein zusätzliches Sicherheitsnetz entfernt eventuell zurückgebliebene Marker-Zeichen restlos.
- **Genauere automatische Abschnittsberechnung:** Ein Figur-Abschnitt beginnt jetzt an seiner Überschriftszeile (statt erst an der ersten Inhaltszeile), und der End-Anker sitzt knapp vor dem Abschnittsende — so sitzen die berechneten Sync-Punkte präziser.
- **Saubere Statusleiste bei wechselnden Buttons:** Ausgeblendete Schaltflächen (z. B. die Sync-Buttons im Auto-Sync-Modus) belegen keinen Platz mehr — keine Lücken oder Überlappungen mehr beim Ein-/Ausblenden.

## 0.109 — Lyrics-Sync-Punkte, Theme „Fire" & mehr Stabilität (2026-06-25)

### Neue Features
- **Synchron scrollende Cuesheets über Sync-Punkte (BL-160):** Automatisch scrollende Lyrics/Cuesheets bleiben jetzt zuverlässig im Takt der Musik. Im neuen **Sync-Modus** koppelst du einzelne Textzeilen fest an eine Liedposition (Anker). Zwischen zwei Ankern interpoliert der Auto-Scroll, an jedem Anker fängt er sich wieder ein — so läuft die Anzeige über den ganzen Song synchron.
  - Gesetzte Anker werden direkt im Text **gelb markiert**.
  - Bei **Rückwärtssprüngen** (z. B. wiederholte Sequenz) bleibt die Anzeige kurz stehen, statt zurückzuspringen.
  - Im Sync-Modus sind **Regeln und History-Logging pausiert**, damit das Setzen der Punkte nichts ungewollt auslöst.
- **Sync in 2 Klicks automatisch erfassen (BL-161):** Beim ersten Synchronisieren eines Songs fragt Callers Caddy, ob die Abschnitte **automatisch** berechnet werden sollen. In der Automatik markierst du nur **Beginn des 1. Teils** und **Ende des 7. Teils** — CC verteilt daraus die sieben Abschnitte selbst. Wo die Ankerzeile im Fenster einrastet, lässt sich bei Bedarf per INI (`lyric_sync/viewport_frac`) feinjustieren.
- **Neues Theme „Fire":** dunkles Theme mit leuchtend feuer-orangem Akzent. Auswählbar über **Einstellungen → Anzeige → Skin / Theme**.
- **Crash-Hinweis: „Ordner öffnen":** Der beim Start angezeigte Hinweis auf ein Absturz-Protokoll bietet jetzt zusätzlich **„Ordner öffnen"**, um direkt zum Log-Verzeichnis (`logs/crashes`) zu springen.

### Bugfixes
- **Absturz beim schnellen Durchsteppen mit Auto-Loop behoben (TIC-0029):** Mit aktiver Regel „bester Loop automatisch setzen" konnte schnelles Wechseln durch mehrere Songs die App mit „QThread: Destroyed while thread is still running" abstürzen lassen. Der Lebenszyklus des Loop-Finder-Threads ist jetzt sauber abgesichert.
- **Kein Absturz mehr beim Beenden (TIC-0026):** Beim Schließen konnte ein zuletzt bearbeitetes Eingabefeld noch ein Auto-Speichern auslösen, nachdem die Datenbank bereits geschlossen war (`AttributeError`). Auto-Speichern und Lautstärke-Speichern prüfen jetzt, ob die Datenbank noch offen ist.

### Übersetzungen
- Englische und japanische Texte für drei zuletzt ergänzte Einstellungen nachgezogen: **Hinweis-Sound (Timer-Überzug)**, **Lautstärke Hinweis-Sound** und **„Filter automatisch auf Tanzprogramm setzen"** (Sequenzen).

## 0.108 — Sicherer ZIP-Import & neue Songs automatisch markiert (2026-06-24)

### Neue Features
- **ZIP-Label-Import: Vollständigkeitscheck + lernende Erkennung (BL-157):** Der Import von Label-Paketen geht jetzt sicher mit allem im ZIP um — und wird durch pflegbare Listen mit jedem Eintrag besser.
  - **Alles bleibt sichtbar:** Alle Musikdateien landen in der Song-Area, alle Lyrics in der Lyric-Area, alles Übrige (z. B. Word-Beiwerk) mit Begründung in einer **„Sonstige"-Liste**. Oben zeigt eine **Bilanz**, dass jede Datei berücksichtigt ist. So fällt ein Paket nicht mehr in mehrere „Songs" auseinander, nur weil eine Originalspur oder Variante anders heißt.
  - **Vier pflegbare Listen in einem Dialog** (Varianten-Abkürzungen, Label-Verzeichnis, Beiwerk-Muster, Rollen-Wörter): Über **„Listen bearbeiten…"** pflegst du, woran CC Songs erkennt. Deine Einträge bleiben bei Updates erhalten, neue mitgelieferte Standards kommen automatisch dazu (nichts wird überschrieben). Per **„Liste importieren…"** kannst du die Sammlung eines Kollegen additiv übernehmen.
  - **Varianten besser erkannt:** Ein Varianten-Kürzel wird jetzt in Klammern `(V)`, direkt an der Labelnummer (`WM 002v`) **und** als freies Wort am Dateinamen-Ende (`… VJ`) erkannt — sofern es in deiner Liste steht. Flip-Side-Nummern wie `509a` bleiben dabei unangetastet.
  - **Standard-Songtyp** im Vorschau-Fenster ist jetzt **Singing** (Label-Pakete sind meist Singing Calls).
  - Hinweis: Lyrics im alten `.doc`-Format kann CC weiterhin nicht anzeigen (nur `.docx`); solche Dateien erscheinen sichtbar unter „Sonstige".
- **Genre „NEW" für frisch hinzugekommene Songs (BL-040):** Jeder Song, der neu in die Datenbank kommt – per Import, ZIP-Label-Import, „Neu"-Button oder durch das Laden einer noch unbekannten MP3 in den Player – erhält **automatisch das Genre „NEW"**. So sieht man auf einen Blick, was zuletzt dazugekommen ist: einfach in der Songliste (oder im Planner) auf das Genre **„NEW"** filtern.
  - Der Caller entscheidet selbst, wann ein Song „eingearbeitet" ist, und entfernt das „NEW"-Tag dann wie gewohnt über den Genre-Dialog im Song-Datensatz.
  - „NEW" verhält sich wie jedes andere Genre (filtern, umbenennen, im Genre-Manager verwalten).
  - Beim Import automatisch erkannte Genre-Vorschläge (aus dem Dateinamen) kommen **zusätzlich** zum „NEW"-Tag dazu – sie überschreiben es nicht mehr.
  - **Migrierter Altbestand** (aus der alten Version / SqView) bekommt bewusst **kein** „NEW", da es sich dabei nicht um Neuzugänge handelt.

### Bugfixes
- **ZIP-Import-Vorschau: Mausrad verstellt keine Auswahlfelder mehr:** Beim Hoch- und Runterscrollen durch das Vorschau-Fenster sprang bisher der Wert eines Auswahlfeldes (z. B. Songtyp) um, sobald der Mauszeiger darüber lag. Das Mausrad ist für die Auswahlfelder (Songtyp & Co.) im Fenster jetzt deaktiviert — wie in den übrigen Dialogen — und scrollt stattdessen den Fensterinhalt.

## 0.107 — ZIP-Label-Import, zuverlässigeres Lyrics-Matching & Audio-Standard-Fix (2026-06-23)

### Neue Features
- **ZIP-Import für Label-Lieferungen (BL-157):** Im Import-Dialog gibt es jetzt die Quelle **„ZIP-Paket (Label-Lieferung)…"**. Callers Caddy entpackt das/die ZIP(s), erkennt automatisch zusammengehörige Songs und zeigt vor dem Übernehmen ein **Vorschau-Fenster** zum Prüfen und Anpassen.
  - **Haupt-MP3 + Varianten:** Die Instrumental-Version (ohne Modifier im Dateinamen) wird als Hauptlied vorgeschlagen; zusätzliche Spuren (z. B. „(V)" = Vocal, „(NL)" = No Lead) werden als **Varianten** angeboten. Die Reihenfolge lässt sich **per Drag & Drop** ändern (oberste = Hauptlied).
  - **Lyrics in mehreren Formaten:** Mitgelieferte Lyrics (HTML, PDF, DOCX, RTF, TXT) werden gefunden; man wählt an/ab, bestimmt die primäre Datei und kann jede **Bezeichnung editieren**.
  - **Editierbare Abkürzungs-Tabelle:** Über „Abkürzungen bearbeiten…" lassen sich die Kürzel (V→Vocal, NL→No Lead Instrument, NB→No Backup Vocals, NBL→No Backup Vocals/No Lead, …) selbst pflegen. Daraus werden die vorbelegten Varianten-Bezeichnungen abgeleitet; Unbekanntes wird roh übernommen und ist überschreibbar.
  - **Probehören im Preview:** Jede Musikspur hat in der Liste eine Probe-Spalte (▶/⏸) — so kann man Instrumental und Varianten direkt anspielen und vergleichen, bevor man importiert. Das Probehören ist „still": es löst — wie das Vorhören im Loop Finder — **weder Regeln noch History-Tracking** aus.
  - Beim Übernehmen landen Haupt-MP3 + primäre Lyrics in den Stammdaten, alle weiteren Dateien als **Varianten (Extended Data)** am Song.
  - Erkennt beide gängigen Label-Namensschemata: Modifier am Ende (`Titel - LABEL (V)`) und vor dem Label (`Titel (V) - LABEL`).

### Bugfixes
- **Lyrics-Dateien kamen beim Song-Import nicht mit, wenn der Dateiname nicht exakt zur MP3 passte – behoben:** Bisher wurde beim Import nur dann eine Lyrics-Datei automatisch verknüpft, wenn ihr Name **exakt** mit dem der MP3 übereinstimmte. Gerade Label-Pakete (z.B. als Word-/DOCX-Datei) benennen die Lyrics aber oft anders als die Musikdatei – sie wurden dadurch übersehen. Der Import vergleicht Namen jetzt **tolerant** (wie schon die Migration aus der alten Version):
  - Label am Ende wird erkannt und ignoriert – auch ohne umgebende Leerzeichen (z.B. MP3 `Achy Breaky Heart-RYL 555`, Lyrics `Achy Breaky Heart.docx`).
  - Funktioniert in **beide Richtungen**: egal ob das Label an der MP3 oder an der Lyrics-Datei hängt.
  - Unterschiede in Schreibweise/Sonderzeichen werden über einen normalisierten Vergleich abgefangen.
  - Liegen mehrere passende Dateien vor, gewinnt das hochwertigere Format (RTF vor HTML vor Text vor DOCX vor PDF). Ein exakter Namenstreffer hat immer Vorrang vor einem nur „label-bereinigten".
- **Kein stummer Start mehr auf dem falschen Ausgang:** Beim allerersten Start wählte Callers Caddy das Ausgabegerät nach Backend-Priorität (WDM-KS vor WASAPI vor MME) — und erwischte dabei oft den **digitalen SPDIF-Ausgang**, sodass nichts zu hören war. Jetzt startet die App mit dem **Windows-Standardwiedergabegerät** („System-Standard"), das praktisch immer hörbar ist. Wer geringere Latenz will, wählt in der Statusleiste gezielt ein spezifischeres Gerät (WDM-KS/WASAPI, optional Exclusive). *(Bereits gespeicherte Geräteauswahlen bleiben unverändert — ggf. einmalig „System-Standard" wählen.)*

### Geändert
- **Import-Dialog umgestellt:** Zuerst wird die **Quelle** gewählt (Datei / Ordner / ZIP). Bei Datei/Ordner kommen Kopieren und **Songtyp erst danach** (Typ ganz am Ende). ZIP-Pakete springen direkt ins Preview — kein unnötiger Vorab-Dialog mehr. (Behebt auch, dass eine vorab gewählte Typ-Einstellung nicht zum ZIP-Preview passte.)

### Technik
- Neuer GUI-freier Analyzer `zip_import.py` (eigenständig testbar) + Vorschau-Dialog `zip_import_dialog.py`. Entpacken/Analysieren laufen im **Hintergrund-Thread** (Audio-Priorität bleibt gewahrt), mit **Performance-Messmarken** für Entpacken, Scan und Commit. Der bestehende Import wurde dafür in einen wiederverwendbaren Kern (`_import_single_audio`) refaktoriert; das normale Import-Verhalten bleibt unverändert. Vollständig übersetzt (DE/EN/JA).
- Lyrics-Matching beim Import: neuer Helfer `_build_lyrics_map()` und überarbeitetes `_find_and_import_lyrics()` — nutzt den bewährten 4-stufigen Matcher der SqView-Migration (`SqViewReader.match_lyrics`) plus die Label-Erkennung `_parse_filename()`; die Migration selbst bleibt unverändert.

## 0.106 — Zentrale Icons, Farben aus dem Theme (2026-06-18)

### Neue Features / Verbesserungen
- **Einheitliches Icon-Konzept für alle Themes:** Alle Icons liegen jetzt zentral in einem gemeinsamen `images/`-Ordner statt in jedem Theme dupliziert. Geometrie und Design werden einmal zentral gepflegt; die **Farbe kommt ausschließlich aus den Theme-Werten**.
  - Neuer Theme-Farb-Key **`icon_color`** (zusätzlich zum bestehenden `title_icon`). Iconfarben lassen sich damit pro Theme rein über `skin.json` steuern — ganz ohne eigene Bilddateien. Eigene Themes zu gestalten wird dadurch deutlich einfacher.
  - Alle Themes nutzen dasselbe Icon-Set (modern, Outline-Stil); bisher abweichende Designs (win11, elegant) wurden angeglichen.
  - Semantische Akzentfarben bleiben fest (Highlight-Gelb, Text-Color-Rot).

### Bugfixes (Theme-Feinschliff)
- **Spinbox-/Combobox-Pfeile** waren in hellen Themes (light/win11) dunkel auf blauem Button-Grund (schlecht lesbar) — sie folgen jetzt `icon_color` und sind dort weiß.
- **Splitter-Trennlinie** (z.B. Planner zwischen Pool und Playlist) war ungestylt und erschien fast weiß — sie nutzt jetzt die Theme-Trennfarbe wie die Dock-Trenner.
- **„…"-Buttons für Datei-Dialoge** zeigten die drei Punkte nicht (Button-Padding schnitt den Text bei fester schmaler Breite ab) — eigene schmale Button-Variante, Punkte wieder sichtbar.
- Notes-Widget: Zoom-Icons werden wieder angezeigt (nutzen nun den zentralen Icon-Cache).

### Technik
- `SkinManager` färbt die zentralen Template-SVGs beim Theme-Laden mit den Theme-Farben ein (Temp-Cache); QSS referenziert Icons über `{{icon_path}}`, Code über `skin_mgr.icon_dir`. Dokumentation: `1_Source/docs/17_theming_icons.md` und `1_Source/src/images/README.md`.

## 0.105 — Japanisch als dritte Sprache (2026-06-18)

### Neue Features
- **Japanische Programmsprache (日本語):** Callers Caddy lässt sich jetzt komplett auf Japanisch umstellen. Die gesamte Oberfläche (Menüs, Dialoge, Tooltips, Meldungen, Tutorials, Migration und Class Designer — rund 1.460 Texte) wurde übersetzt.
  - Auswahl beim Erststart (dritter Button „日本語で開始") sowie jederzeit über **Einstellungen → Sprache** bzw. das Sprach-Menü.
  - **Square-Dance-Fachbegriffe bleiben bewusst englisch** (z.B. Patter, Singing Call, Tip, Loop, BPM, Pitch, Beat Snap) — so wie international und auch von japanischen Callern üblich.
  - Deutsch und Englisch sind unverändert: Die japanische Übersetzung wurde rein additiv ergänzt, bestehende Sprachen wurden an keiner Stelle angetastet.

### Verbesserungen
- **Lyrics-Toolbar bricht bei schmalem Dock um:** Die Buttons oben im Lyrics-Fenster (Auto-Scroll, Auto-Size, Auto-Width, Zoom, Bearbeiten) leiten ihre Breite aus ihrem Inhalt ab und brechen in die nächste Zeile um, wenn das Widget schmaler wird als die Buttonzeile verträgt — statt abgeschnitten zu werden oder eine Mindestbreite zu erzwingen. Gleiches Umbruch-Verhalten wie bereits bei Songliste und Playlist.

### Technik
- **Logfiles bleiben sprachneutral lesbar:** Diagnose-/Support-Logs (Crash-Logs, rules.log, perf_log.txt, System-Report) waren und bleiben unabhängig von der UI-Sprache (technisch/englisch). Das **Migrations-Detaillog** wird ab jetzt bewusst immer auf Englisch geschrieben (samt Live-Anzeige während der Migration), damit es für den Support unabhängig von der gewählten Sprache lesbar bleibt — die übrige Oberfläche des Migrationstools bleibt in der Nutzersprache.

## 0.104 — Massen-Löschen großer Songmengen (2026-06-17)

### Neue Features
- **Neuer Reiter „Massen-Löschen“ im Potential-Fenster (BL-148):** Entfernt eine große Menge Songs in einem Rutsch aus der Datenbank — gedacht für den Fall, dass versehentlich zu viele Songs geladen wurden (z.B. ein falscher Ordner beim Import).
  - **Mehrfach sortierbare Liste** mit den Spalten Typ (P/S/PS), Hinzugefügt (Datum), Titel, Label, Genre, ERR und Qualität — jede Spalte per Klick auf den Kopf sortierbar, um den falschen Schwung schnell zu isolieren.
  - **Komfortable Mehrfachauswahl:** Shift+Klick markiert einen zusammenhängenden Bereich, Strg+Klick einzelne Zeilen, Strg+A alles in der Ansicht.
  - **Eine einzige Sicherheitsabfrage** für den ganzen Vorgang (keine Rückfrage pro Song), danach wird ohne weitere Unterbrechung gelöscht.
  - **Historiendaten:** Liegen zu den ausgewählten Songs Abspielverläufe vor, wird einmal gefragt, ob diese mitgelöscht werden sollen (Standard: Nein — die Historie kann später über „Verwaiste Historie“ bereinigt werden).
  - Die Musikdateien auf der Festplatte werden dabei nicht angetastet.

### Technik / Performance
- Die Songliste des Reiters wird **erst beim Öffnen** geladen (kein Start-Overhead) und das Löschen läuft im Hintergrund-Thread, damit ein laufender Song nie unterbrochen wird. Bei aktivem Performance-Log werden Messpunkte (DB-Abfrage, Genre-Zuordnung, Tabellenaufbau, Löschvorgang) protokolliert.

## 0.103 — Lyrics: Word- (DOCX) und PDF-Dateien anzeigen (2026-06-16)

### Neue Features
- **Lyrics als Word-Dokument (.docx) anzeigen:** Lyrics und Cuesheets, die als Word-Datei vorliegen, lassen sich jetzt direkt mit einem Song verknüpfen und im Lyrics-Fenster anzeigen – inklusive Schriftgrößen, großem zentriertem Titel, Einrückungen, Fett/Kursiv/Unterstrichen sowie farbigen Text- und Hintergrund-Markierungen (z.B. die typischen gelben/farbigen Tag-Markierungen). Es ist keine zusätzliche Software (kein Word) nötig.
- **Lyrics als PDF anzeigen:** PDF-Dateien können ebenfalls als Lyrics verknüpft und angezeigt werden – als schnelle Text-Leseansicht des Call-Texts. Hinweis: PDF wird bewusst nur als Text dargestellt; farbige Markierungen und das exakte Layout aus dem PDF werden dabei nicht übernommen. Wer die volle Formatierung mit Markierungen braucht, verwendet dafür Word, RTF oder HTML.
- **Bearbeiten von Word-/PDF-Lyrics:** Word und PDF sind reine Anzeigeformate. Wer ein solches Lyric bearbeiten möchte, dem bietet Callers Caddy an, daraus eine bearbeitbare HTML-Kopie anzulegen (genau wie bisher bei RTF und Text). Die Originaldatei bleibt dabei unverändert.

### Verbesserungen
- Datei-Auswahl, automatischer Lyrics-Import beim Hinzufügen von Songs und die Migration aus der alten Version erkennen jetzt auch `.docx`- und `.pdf`-Dateien.

## 0.102 — Startprobleme behoben: „läuft bereits", Audio auf ARM-Windows, Theme-Wechsel (2026-06-16)

### Bugfixes
- **„Callers Caddy läuft bereits" trotz geschlossenem Programm – behoben:** Bei einer Installation in geschützten Ordnern (z.B. `C:\Programme\…`) ließ sich Callers Caddy nicht starten – es kam die Meldung, das Programm laufe bereits, obwohl es geschlossen war. Behelfen konnte man sich nur mit „Als Administrator ausführen". Ursache war die interne Sperrdatei, die im Programmordner abgelegt wurde, wo normale Benutzer nicht schreiben dürfen. Sie liegt jetzt in einem immer beschreibbaren, benutzereigenen temporären Ordner – der Admin-Trick ist nicht mehr nötig. Mehrere getrennte Installationen blockieren sich dabei nicht gegenseitig.
- **Absturz beim Start auf Windows-on-ARM (z.B. Apple-Mac mit Parallels) – behoben:** Lief Callers Caddy unter einem Windows auf ARM-Basis (etwa Windows 11 in Parallels auf einem MacBook), stürzte es direkt beim Start mit `error 0x7e` ab, weil das Audio-System fälschlich eine ARM-Variante der Audio-Bibliothek suchte, die nicht mitgeliefert wird. Callers Caddy nutzt jetzt korrekt die mitgelieferte 64-bit-Bibliothek (über die Windows-Emulation) und startet auch in dieser Umgebung. Zusätzlich reißt ein nicht ladbares Audio-System den Start an dieser Stelle nicht mehr roh ab, sondern wird sauber abgefangen.

### Verbesserungen
- **Theme/Skin wechselt jetzt sofort:** Eine Änderung von „Skin / Theme" in den Einstellungen wird unmittelbar übernommen – ein Neustart ist nicht mehr erforderlich.

## 0.101 — Verständliche Meldung statt Absturz, wenn das Audio-System blockiert ist (2026-06-15)

### Bugfixes
- **Kein roher Absturz mehr beim Start, wenn die Audio-Komponente nicht geladen werden kann:** Auf manchen Rechnern brach Callers Caddy direkt beim Start mit einem unverständlichen Python-Fehlerfenster ab (`PortAudio library not found`, `error 0x7e`). Ursache ist fast immer der Rechner, nicht das Programm — meist ein Virenscanner, der die Audio-Datei `libportaudio64bit.dll` blockiert oder in die Quarantäne verschiebt, oder eine heruntergeladene ZIP-Datei, die vor dem Entpacken nicht „zugelassen" wurde (Windows-Sperre). Bisher passierte dieser Fehler so früh, dass kein Hinweisfenster möglich war.
- **Klartext-Hinweis mit Lösungsweg:** Lässt sich das Audio-System nicht laden, erscheint jetzt ein verständliches Fenster, das die wahrscheinliche Ursache nennt und Schritt für Schritt erklärt, wie man sie behebt (Virenscanner-Ausnahme bzw. ZIP vor dem Entpacken freigeben).

### Verbesserungen (Diagnose)
- **Crash-Protokollierung greift jetzt von der allerersten Sekunde an:** Der Absturz-Logger wird nun ganz früh aktiviert — noch bevor die Audio-Komponenten geladen werden. Dadurch werden ab sofort auch Abstürze *beim Programmstart* in eine Logdatei geschrieben (`logs\crashes`), die bisher spurlos blieben.
- **Gezielte Audio-Diagnose:** Schlägt das Laden des Audio-Systems fehl, schreibt Callers Caddy automatisch eine Diagnosedatei. Sie prüft unter anderem, ob die Audio-Datei überhaupt noch vorhanden ist und lesbar ist — so lässt sich unterscheiden, ob der Virenscanner sie *gelöscht/in Quarantäne* verschoben hat oder ob sie *vorhanden, aber blockiert* ist (was der Windows-Fehlercode allein nicht verrät). Der Hinweisdialog nennt den Speicherort der Datei für eine Rückfrage beim Support.
- **Erkennung von Sonderzeichen im Installationspfad:** Die Diagnose prüft jetzt auch, ob der Programmpfad Sonderzeichen enthält (z.B. Umlaute oder Diakritika im Benutzernamen wie `C:\Users\Café\…`). Solche Pfade sind eine bekannte, regionsabhängige Ursache dafür, dass die Audio-Bibliothek unter Windows nicht geladen werden kann — die Diagnose weist dann direkt darauf hin (Abhilfe: in einen Pfad ohne Sonderzeichen installieren, z.B. `C:\Callers_Caddy`).

## 0.100 — Relative Musikpfade: verstreute Bibliotheken über mehrere Ordner (2026-06-15)

### Neue Funktionen
- **Songs dürfen jetzt in beliebig tiefen Unterordnern liegen:** Bisher merkte sich Callers Caddy zu jedem Song nur den reinen Dateinamen und suchte ihn direkt in den (bis zu vier) Musikpfaden. Wer seine Musik in viele Unterordner sortiert hat, stieß damit an Grenzen. Jetzt wird zu jedem Song der **relative Pfad innerhalb seines Musikpfads** gespeichert (z.B. `Singing Calls/Country/song.mp3`). So genügen weiterhin die vier Musikpfade als Wurzeln — die Unterordner-Struktur darunter kann beliebig groß sein.
- **Bis zu vier Wurzelpfade, auch auf verschiedenen Laufwerken:** Die vier Musikpfade gelten als eigenständige Wurzeln und dürfen auf unterschiedlichen Laufwerken liegen (z.B. C:, D:, E:, F:). Ein Song wird relativ zu seinem Musikpfad gespeichert; beim Abspielen werden die Pfade der Reihe nach durchprobiert.
- **Neues Werkzeug „Musikbibliothek re-indexieren" (Menü Pfade):** Durchsucht alle konfigurierten Musikpfade rekursiv und hebt bestehende Songs, deren Datei in einem Unterordner liegt, automatisch auf den passenden relativen Pfad — so werden bisher nicht auffindbare Songs wieder abspielbar. Läuft im Hintergrund, ohne einen laufenden Song zu stören. Am Ende erscheint ein Bericht (aktualisiert / mehrdeutig / weiterhin fehlend). Dateien gleichen Namens in mehreren Ordnern werden bewusst nicht geraten, sondern zur manuellen Zuordnung gemeldet.
- **Import behält die Ordnerstruktur:** Beim Import „am Ort belassen" wird der gewählte Wurzelordner als Musikpfad eingetragen und jeder Song relativ dazu gespeichert — inklusive Unterordner.

### Verbesserungen
- **Einheitliche, portable Pfadspeicherung:** Relative Pfade werden überall einheitlich mit Schrägstrich `/` gespeichert (statt gemischter Schrägstriche). Eine einmalige Datenbank-Migration räumt ältere Einträge automatisch auf. Das macht die Datenbank robuster beim Verschieben auf andere Rechner oder USB-Sticks.
- **Datei-Auswahl an allen Stellen vereinheitlicht:** Der Datei-Button im Song-Datensatz, die Varianten-Verwaltung und die Lyrics-Auswahl ermitteln den relativen Pfad jetzt gegen alle Musikpfade einheitlich.

### Migrations-Tool
- **Kopieren oder Verknüpfen wählbar:** Wie beim normalen Import fragt die Migration jetzt, ob die Musikdateien ins Ziel kopiert oder an ihrem Ort belassen und nur verknüpft werden sollen. Verknüpfen spart Speicherplatz und ist ideal für große, verstreute Bibliotheken — die Quellordner werden dabei automatisch als Musikpfade in die Ziel-Konfiguration eingetragen.
- **Wurzelverzeichnis der Musikbibliothek:** Die Migration fragt das Wurzelverzeichnis ab und speichert jeden Song relativ dazu — die Unterordner-Struktur bleibt erhalten.
- **Unterordner werden vollständig durchsucht (CC1):** Die Callers-Caddy-1.0-Migration durchsucht die Musikordner jetzt rekursiv inklusive aller Unterordner (vorher nur die oberste Ebene).
- **Keine verlorenen Dateien mehr bei gleichen Namen (SqView):** Gleichnamige Dateien in verschiedenen Ordnern gingen bisher verloren. Jetzt bleiben beide erhalten; bei mehreren Treffern wird anhand des ursprünglichen Pfads die passende Datei gewählt.

## 0.99 — Migrations-Detaillog und robustere SqView-Übernahme (2026-06-14)

### Bugfixes
- **App startet nach einem Absturz wieder zuverlässig:** Stürzte Callers Caddy ab, blieb eine interne Sperrdatei zurück, die jeden weiteren Start mit der Meldung „Callers Caddy läuft bereits" blockierte — auch ein Rechner-Neustart half nicht, da die Datei auf der Festplatte verblieb. Die App prüft jetzt beim Start, ob die als Sperr-Besitzer eingetragene Programm-Instanz überhaupt noch läuft, und entfernt verwaiste Sperren automatisch. Läuft tatsächlich noch eine Instanz, erscheint die Hinweismeldung wie bisher.

### Migrationstool
- **Detailliertes Migrationslog:** Bei jeder Migration (SqView wie auch Callers Caddy 1.0) wird jetzt im Zielordner eine Logdatei abgelegt (`migration_log_<Datum>_<Uhrzeit>.txt`). Sie protokolliert Schritt für Schritt, was pro Song getan wurde — Datensatz übernommen, Sprungmarken übernommen, Lyrics gefunden und eingetragen, MP3 gefunden und verknüpft — und ist auch nach der Migration jederzeit nachlesbar. Die Datei wird laufend geschrieben, sodass auch bei einem Abbruch alles bis dahin erhalten bleibt.
- **Drei Meldungsstufen:** Jeder Schritt wird als `DONE`, `WARNING` oder `ERROR` eingestuft. Am Ende des Logs steht eine Zusammenfassung, summiert nach Kategorien — auf einen Blick erkennbar, was gelungen ist und was nicht.
- **Suchbarer Doppel-Schlüssel (Schweregrad + Thema):** Jede Logzeile beginnt mit einem sprachunabhängigen Schlüssel aus Schweregrad und Thema, z.B. `ERROR MUSIC`, `DONE LYRIC`, `WARNING LYRIC`, `DONE LOOP`. So lassen sich einzelne Themen im Log gezielt per Volltextsuche finden, unabhängig von der Sprache der Beschreibung.
- **Aufgeräumte Live-Anzeige:** Während der Migration zeigt das Fenster nur noch den Phasen-Fortschritt, alle Warnungen/Fehler und die Schluss-Zusammenfassung. Die vollständige Schritt-für-Schritt-Liste landet im Detaillog. Ein neuer Button „Detaillog öffnen" öffnet die Logdatei direkt — auch nach einem Fehlerabbruch.
- **Fehlende Dateien werden als Fehler erkannt:** Ist eine Datei laut Quellsystem vorhanden, wird sie beim Import aber nicht gefunden (MP3 oder Lyrics), erscheint das jetzt als `ERROR` statt unbemerkt zu bleiben. Der bewusste Blind-Import ohne Musik-Ordner bleibt eine Warnung.
- **Lyrics-Zuordnungen aus SqView werden bevorzugt:** Explizite Song-zu-Lyrics-Verknüpfungen aus SqView (marry-Tabelle) werden jetzt zuerst ausgewertet, bevor auf die namensbasierte Suche zurückgegriffen wird. Damit bleiben manuell gepflegte Zuordnungen erhalten.
- **Logsprache folgt der gewählten Sprache:** Das Detaillog wird in Deutsch oder Englisch geschrieben — je nach gewählter Sprache. Die Stufen-Kennungen `DONE`/`WARNING`/`ERROR` bleiben sprachunabhängig, damit das Log durchsuchbar bleibt.

### SqView-Import: vollständigere und korrekte Übernahme
- **Gesamte Song-Bibliothek wird übernommen:** Bisher kamen nur Songs aus den aktuellen Listen und der Abspielhistorie an (~1000). Jetzt wird die komplette Song-Bibliothek der Quelle gehoben — inklusive aller Songs mit gesetzten Loop-Markern, die in keiner aktuellen Liste mehr standen. Songs, deren Audiodatei nicht mehr auffindbar ist, werden als Blind-Eintrag mit Fehler-Hinweis protokolliert und lassen sich später per Datei-Import aktivieren.
- **Korrekte Patter/Singing-Einstufung:** Die Einstufung als Patter, Singing oder beides hing vorher allein am Ordnernamen — dabei wurden ganze Ordner (z.B. „Singing Calls") falsch als Patter erkannt. Neue Regel: Sind Loop-Marker gesetzt, ist es ein Patter; ist ein Lyric vorhanden, wird der Singing-Marker gesetzt; der Ordnerpfad zählt nur noch als Indiz. Songs, die beides erfüllen, zählen automatisch zu Patter UND Singing. Ohne jedes Signal wird ein Song als Singing eingestuft.
- **Apostrophe in Titeln werden bereinigt:** Songtitel mit Apostroph (z.B. „Ain't Misbehaving") wurden aus der Quelle mit einem Platzhalter-Sonderzeichen übernommen. Diese werden beim Import jetzt automatisch in einen normalen Apostroph zurückgewandelt. Das Auffinden der zugehörigen Audio- und Lyrics-Dateien funktioniert unabhängig von der Schreibweise.
- **Lyrics-Zuordnung aus der Quelle bevorzugt:** Explizite Song-zu-Lyrics-Verknüpfungen der Quelle werden zuerst genutzt; nur wenn keine vorliegt, greift die namensbasierte Suche.

## 0.98 — Lyrics direkt in der App bearbeiten (2026-06-08)

### Neue Funktionen
- **Lyrics-Editor im Lyrics-Dock:** Die Lyrics können jetzt direkt in Callers Caddy bearbeitet werden — keine externe Word- oder Editor-Sitzung mehr nötig. Ein neuer Stift-Button (✎) rechts in der Lyrics-Toolbar schaltet zwischen Anzeige- und Bearbeitungsmodus um. Alternativ aktiviert ein Doppelklick auf den Lyric-Text den Bearbeitungsmodus.
- **Volle Rich-Text-Bearbeitung:** Im Edit-Modus erscheint eine zweite Toolbar mit allen wichtigen Formatierungen — Absatz-Format (Normal / Überschrift 1–3), Schriftgröße (6–96 pt), Fett, Kursiv, Unterstrichen, Schriftfarbe und Hintergrundfarbe (Markierung). Damit lassen sich Tag-, Break- und Closer-Zeilen so hervorheben wie man es im Live-Betrieb sehen möchte.
- **HTML als einheitliches Zielformat:** Beim Speichern wird die Datei immer als HTML abgelegt. HTML deckt alle Anforderungen (Überschriften, Auszeichnungen, Schriftgrößen, Farben, Hintergrundfarben) verlustfrei ab und ist von jedem Browser oder Editor weiter bearbeitbar.
- **Original-Dateien bleiben unangetastet:** RTF- und TXT-Lyrics werden beim Bearbeiten NIE überschrieben. Stattdessen legt Callers Caddy eine neue `.html`-Datei neben das Original und zieht den `lyrics_file`-Eintrag des Songs auf die neue Datei um. Das Original bleibt als Sicherung im Lyrics-Ordner liegen. Eine kurze Info-Meldung weist nach dem ersten Speichern darauf hin.
- **HTML-Originale werden mit Backup überschrieben:** Beim ersten Speichern einer HTML-Lyrics-Datei wird automatisch eine `.bak`-Sicherung der Originaldatei daneben angelegt — falls man die alte Fassung später noch braucht.
- **Tastatur-Shortcuts:** `Strg+S` speichert und verlässt den Edit-Modus, `Esc` verwirft die Änderungen (mit Rückfrage, falls etwas geändert wurde).
- **Sicherheit beim Songwechsel:** Wer den Song wechselt während Lyrics noch ungespeichert bearbeitet werden, bekommt eine Rückfrage „Änderungen verwerfen?" — versehentlicher Verlust wird damit ausgeschlossen.
- **Schriftgröße wirkt sofort sichtbar:** Wer im Edit-Modus die Schriftgröße über das Spinbox-Feld ändert (Pfeiltasten oder Eingabe), sieht die Änderung live im Text. Ohne Selektion wirkt die neue Größe auf das ganze Dokument, mit Selektion nur auf den markierten Bereich.
- **Per-Wort-Schriftgrößen bleiben in der Anzeige erhalten:** Ein bewusst größer gesetztes Wort (z.B. eine besonders zu betonende Stelle im Lyric) bleibt nach dem Speichern auch in der Lyrics-Anzeige sichtbar größer. Vorher wurden Schriftgrößen-Angaben beim Anzeigen vereinheitlicht — jetzt nicht mehr.
- **Zoom und Auto-Width skalieren das ganze Dokument proportional:** Auch wenn einzelne Wörter unterschiedliche Schriftgrößen haben, skalieren Zoom-Buttons und Auto-Width das gesamte Dokument verhältnistreu — der Größenunterschied zwischen markierten und normalen Stellen bleibt bei jeder Anzeige-Größe erhalten.
- **Auto-Modi sinnvoll im Edit-Mode:** Auto-Scroll und Auto-Size sind während des Bearbeitens deaktiviert (würden den Cursor verschieben bzw. die Schrift beim Tippen springen lassen). Auto-Width und manueller Zoom bleiben verfügbar — sie ändern nur die Anzeige, nicht die gespeicherten Größen. Nach dem Speichern werden alle Modi wieder aktiv.
- **Icons in allen Skins:** Die neuen Toolbar-Buttons (Stift, Speichern, B/I/U, Schrift-/Hintergrundfarbe, Verwerfen) liegen als SVG-Icons in jedem der vier mitgelieferten Skins (Default, Elegant, Light, Win11). Die Icons folgen dem etablierten Skin-Pattern und passen sich an das gewählte Theme an.

### Datenschutz und Build-Hygiene
- **Source-Code-ZIP ohne interne Doku:** Der `docs/`-Ordner aus `1_Source/` wird nicht mehr in das Source-Code-ZIP gepackt. Dort lagen unter anderem Performance-Logs mit Hostnamen und lokalen Pfaden — die haben in einem öffentlich verteilten Archiv nichts zu suchen.

## 0.97 — Pitch-Wechsel ohne Leiern, eigener Timer-Sound und Label im Player (2026-06-03)

### Neue Funktionen
- **Eigener Sound bei Timer-Überzug (BL-137):** Statt des System-Pieps kann beim Überschreiten der Pattern-/Singing-Zeit jetzt eine MP3 oder WAV abgespielt werden — z.B. das berühmte Esel-Geräusch eines Caller-Kollegen. Der Sound wird in den laufenden Audio-Stream eingemischt (gleicher Output, gleiches Gerät, kein zweiter Stream) und stört die Musik nicht. Konfiguriert über Einstellungen → Audio: „Hinweis-Sound (Timer-Überzug)" mit Datei-Picker und eigenem Lautstärke-Schieberegler. Wenn kein Pfad gesetzt ist, bleibt der bisherige Doppel-Beep aktiv. Alternativ kann der Sound auch pro Rule individuell mitgegeben werden (Parameter `sound` in der `system_ping`-Aktion) — damit lassen sich Pattern und Singing mit unterschiedlichen Tönen unterscheiden.
- **Neue Rule-Aktion „Sound abspielen":** Im Rule-Editor erscheint in der Gruppe „Info & Warnings" direkt über „System Ping (Beep)" die neue Aktion. Über einen Datei-Picker wählt man eine Audiodatei, die Lautstärke ist pro Rule einstellbar. Die Datei wird in den laufenden Stream eingemischt — kein zweiter Kanal, kein Aussetzer im Hauptsong.
- **Plattenlabel im Player (BL-138):** Das Plattenlabel des aktuell gespielten Songs (z.B. „DGR 014") wird jetzt rechts oben im Player direkt über dem Status angezeigt — gleiche Schrift, kein Zusatzabstand. Wird ausgeblendet wenn kein Label gepflegt ist.
- **Rules im Loop-Finder-Vorhören pausiert:** Während des Vorhörens im Loop-Finder (Audition) werden alle Rules komplett deaktiviert. Damit springt Auto-Advance oder andere song_stopped-Rules beim Ende der Audition nicht mehr an. Nach dem Beenden der Audition laufen Rules wieder normal. Technisch über eine zentrale suspend/resume-Mechanik in der Rule-Engine gelöst — wiederverwendbar für zukünftige Vorhör-Funktionen.

### Verbesserungen für den Live-Betrieb
- **Pitch-Slider reagiert jetzt sofort:** Wer den Pitch-Slider während der Wiedergabe verschoben hat, hörte die neue Tonhöhe bisher erst nach mehreren Sekunden — und in der Übergangsphase „leierte" das Tempo hörbar (ca. 20 % Schwankung über 4 Sekunden). Die Audio-Engine setzt das Resampling jetzt hinter den WSOLA-Stretcher (SoundTouch-Architektur für rate > 1), womit Pitch-Änderungen binnen weniger Millisekunden am Lautsprecher hörbar sind und das Tempo durch den Wechsel praktisch nicht mehr aus dem Tritt kommt. Tempo-Slider (`set_today_tempo`, `set_tempo`) bleibt unverändert nach AR-021-Pattern. Messtechnisch: Träger-Einschwingzeit von >3000 ms auf 6 ms, RMS-Abweichung von 188 Hz auf 0,77 Hz.

### Unter der Haube
- **PitchShifter komplett überarbeitet:** Statt blockweisem FFT-Resampling jetzt ein stateful Cubic-Hermite-Interpolator (Catmull-Rom, 4-Punkt-Kernel) mit fraktionaler Lese-Position und 3-Sample-Tail über Aufrufe hinweg. Pitch-Wechsel zur Laufzeit erfolgen ohne Reset/Flush, nur der Ratio-Parameter wird gewechselt — analog zu SoundTouch's RateTransposer.
- **Pipeline-Reihenfolge:** Stretcher bekommt jetzt Original-Audio (vorher: pre-resampletes Audio im 5-Sekunden-Puffer, das beim Pitch-Wechsel mit dem neuen Tempo-Parameter kollidierte). Resampling läuft im Audio-Callback hinter `stretcher.retrieve`, mit Carry-Buffer für variable Output-Längen.
- **Diagnose-Capture:** Neue Engine-Methoden `start_output_capture` / `stop_output_capture` für Diagnose-Tools. Im Normalbetrieb ein einziger `is None`-Check pro Callback, keine Performance-Auswirkung. Test-Tools in `1_Source/src/tools/pitch_transition_test.py` und `pitch_transition_analyze.py` für AM-modulierte Sinus-Messungen (Träger zeigt Pitch, Hüllkurve zeigt Tempo via Nulldurchgang-Analyse).
- **Rule-Engine Suspend/Resume:** Neue API `rule_engine.suspend(reason)` / `rule_engine.resume(reason)` und Kontext-Manager `with rule_engine.suspended("xy"):`. Counter-basiert, verschachtelbar — mehrere gleichzeitige Suspend-Aufrufe heben sich erst dann auf wenn alle resume() gerufen wurden. Während des Suspends werden alle Trigger (außer `play_timer`) im rules.log als `SUSPENDED` protokolliert.
- **Einstellungen-Dialog (BL-129): neue Felder erscheinen automatisch.** Der Dialog enumeriert jetzt nicht nur vorhandene INI-Keys, sondern auch alle Keys aus `SETTINGS_META` — auch wenn sie noch nie geschrieben wurden. Neuer Widget-Typ `file` für Datei-Picker (mit konfigurierbarem Audio-Filter).

---

## 0.96 — Sequenzen verwalten und vereinheitlichter Import (2026-06-01)

### Neue Funktionen
- **Universeller Sequenz-Import (BL-098):** Ein neuer Menüpunkt „Sequenzen → Sequenzen importieren..." ersetzt die vier bisherigen Import-Wege (MDB, JSON, CSDS, Freitext). Du wählst einfach die Datei, der Dialog erkennt das Format automatisch (Datei-Endung + Inhalts-Stichprobe), zeigt eine Live-Vorschau der ersten drei Sequenzen und meldet, wie viele Sätze erkannt wurden. Format kann bei Bedarf manuell überschrieben werden. Multi-Datei-Auswahl funktioniert für JSON, CSDS und Freitext — alle Dateien werden in einem Rutsch verarbeitet. Die alten Einzeleinträge sind aus dem Menü verschwunden; die zugrunde liegenden Routinen bleiben bis 1.8.2026 als Sicherheitsnetz erhalten (BL-135).
- **Freitext-Format mit drei Schreibweisen:** Der Freitext-Parser versteht jetzt (1) eine Sequenz pro Zeile mit Komma-getrennten Calls, (2) ein Call pro Zeile mit Leerzeile als Trenner zwischen Sequenzen, (3) wie 2 aber mit `,` oder `;` am Zeilenende. Zusätzlich werden Ceder-Webseiten-Header (`... ID=<nummer> Print`) als Sequenz-Trenner erkannt — du kannst die Choreo-Datenbank-Sammlungen also direkt copy-pasten und importieren.
- **Bulk-Werte oder aus der Datei (Typ + Schwierigkeit):** Bei JSON- und CSDS-Importen, die Typ und Schwierigkeit pro Sequenz mitliefern, kannst du pro Feld wählen: entweder der im Dialog gesetzte Bulk-Wert für alle Sequenzen, oder die Werte aus der Datei (mit Bulk als Fallback wenn die Datei für eine einzelne Sequenz nichts mitbringt).
- **Duplikat-Erkennung beim Import:** Vor dem Schreiben prüft der Importer per 15-Feld-Vergleich, ob die Sequenz schon in der Datenbank steht oder zweimal in den ausgewählten Dateien vorkommt. Default-mäßig aktiviert; die Status-Zeile meldet „X erkannt — Y neu, Z Duplikate". Spart das nachträgliche Aufräumen über den Deduplikat-Dialog.
- **Sequenzen löschen (BL-136):** Rechtsklick auf eine Sequenz in der Sequenz-Liste → „Löschen". Mehrere markieren (Strg-/Shift-Klick) und gemeinsam löschen geht ebenfalls — entweder per Rechtsklick-Menü oder über den neuen „Löschen"-Button unter der Tabelle. Im Detail-Fenster (SequenzView) gibt es zusätzlich einen Löschen-Button in der Navigations-Leiste; nach dem Löschen rückt automatisch die nächste Sequenz aus der gefilterten Liste nach. Jede Löschung fragt vor dem Vollzug nach, mit Singular- oder Plural-Text je nach Auswahl.

### Verbesserungen für den Live-Betrieb
- **Lyrics passen sich nach Songwechsel automatisch an:** Wer „Auto-Größe" oder „Auto-Breite" im Lyrics-Fenster aktiv hat, sah bisher beim Songwechsel die neue Datei nur in Basis-Schriftgröße — der Refit fand schlicht nicht statt. Beide Modi sind jetzt persistente Schalter, die sich gegenseitig ausschließen, und werden bei jedem neuen Song erneut ausgelöst. Der Refit-Zeitpunkt hängt ab sofort am tatsächlichen Layout-Ende des Textbrowsers (statt an einer festen 50-ms-Verzögerung), damit auch langsam ladende HTML- oder RTF-Dateien sauber skaliert werden.
- **Shift-/Strg-Klick öffnet den SequenzView nicht mehr:** Wer in der Sequenz-Liste mit Mehrfach-Klick eine Auswahl aufbaut, bekam bei jedem Klick die Detail-Ansicht neu aufgerufen — störte beim Markieren. Jetzt: nur der einfache Klick (ohne Modifier) wechselt das Detail-Fenster.

---

## 0.95 — Bessere Diagnose bei Audio-Problemen (2026-06-01)

### Verbesserungen
- **Geladene Songs im Perf-Log:** Bei jedem Song-Wechsel wird jetzt eine Diagnose-Zeile mit Dateinamen, vollem Pfad, Samplerate, Kanälen und Dauer geschrieben. Damit lässt sich im Problemfall (Aussetzer, Klangstörung, Stream-Reopen) sofort nachvollziehen, welche Datei genau in dem Moment lief — vorher musste man das umständlich aus der Spielhistorie rekonstruieren. Für den Live-Betrieb komplett unsichtbar; spürbar nur bei späterer Fehlersuche.

---

## 0.94 — Tempo- und Pitch-Wechsel ohne Ruckler (2026-05-31)

### Verbesserungen für den Live-Betrieb
- **Tempo-Wechsel klingen jetzt sauber durch (AR-021).** Wer am Tempo- oder Pitch-Regler dreht, hört keinen kurzen Aussetzer mehr und das Lied bleibt exakt an der Stelle, an der es gerade war. Besonders relevant für „HotHash"-Situationen, in denen das Tempo schrittweise erhöht wird — jeder einzelne Klick führt jetzt zu einem nahtlosen Übergang statt zu einem hörbaren Sprung. Gilt für alle drei Eingabewege: Song-Tempo (das in der DB gespeichert wird), Heutiges Tempo (Session-Faktor) und Pitch.
- **Etwas Reaktions-Latenz beim Tempo-Wechsel:** Bis das neue Tempo hörbar einsetzt, läuft noch bis zu eine knappe Sekunde im alten Tempo weiter. Das ist der Audio-Vorrats-Puffer, der seit v0.93 für die generelle Aussetzer-Freiheit zuständig ist — wir lassen ihn bewusst in Ruhe, weil jeder Eingriff genau die Ruckler erzeugen würde, die wir vermeiden wollen. In der Praxis heißt das: zwischen zwei Tempo-Klicks lieber ein kleines bisschen Pause lassen, dann hört man jeden Schritt sauber.

---

## 0.93 — WSOLA-Stretcher entkoppelt: Knistern bei niedriger Latenz behoben (2026-05-31)

### Performance / Bugfixes
- **WSOLA-Passthrough bei Tempo 1.0 (AR-020 Fix A):** Bisher lief die teure Coarse-to-Fine-Kreuzkorrelation in `time_stretcher.py` **auch** wenn der Tempo-Regler auf 1.0 stand. Bei COLA-konformen Hann-Fenstern mit 50 % Overlap und ana_hop == syn_hop ist die nominale Position aber mathematisch bereits exakt — die Korrelation liefert sowieso nur das nominale Ergebnis zurück. Auf einem Celeron N3450 kostete diese unnötige Suche bis zu 15 ms Lock-Hold pro Hop und wurde unter WDM-KS bei 11 ms Hardware-Latenz als Knistern hörbar. Jetzt: bei Tempo == 1.0 wird die Korrelation komplett übersprungen.
- **PREPROCESS_OUTPUT_SECONDS 0.25 → 1.0 (AR-020 Fix B):** Der Stretcher-Output-Buffer wird jetzt auf 1 s statt 250 ms Soll-Stand gehalten. Damit werden auch maximale Hop-Berechnungs-Spitzen (z. B. bei Tempo-Drag) absorbiert, bevor sie den Hardware-Buffer treffen können. Vorher: Buffer pendelte 232–325 ms mit periodischem Dip auf 209 ms → 23 ms Reserve unter WDM-KS. Nachher: Buffer pendelt 998–1091 ms → ~1 s Reserve über alle Hostapis.
- **Stretcher mit zwei Locks (AR-020 Fix C):** `time_stretcher.py` hatte einen einzigen Lock, den `preprocess()` während der gesamten teuren Hop-Berechnung gehalten hat. Der Audio-Callback wartete im `retrieve()` auf denselben Lock — selbst wenn er nur Output-Frames lesen wollte. Jetzt schützt ein zweiter, schmaler `_out_lock` ausschließlich den Output-Buffer; `retrieve()` wartet höchstens auf das kurze Append eines fertigen Hops, nicht mehr auf die WSOLA-Berechnung selbst.

### Diagnose
- **Stretcher-Stats-Zeile alle 5 s:** Neue `[Diag] Stretcher-Stats`-Zeile direkt unter jedem `[AudioBuf]`-Eintrag im Perf-Log. Format: `hops=N passthrough=N (X%) correlation=N lock_hold_ms avg=X.XX max=X.XX`. Zeigt damit auf einen Blick: ob Fix A greift (Passthrough-Anteil), wie teuer die Hop-Berechnung tatsächlich ist (Lock-Hold-Zeiten), und wann der User am Tempo war (Correlation > 0).
- **Lock-Hold-Messung:** Jeder Hop wird in `time_stretcher.preprocess()` via `time.monotonic_ns()` umrahmt — die Statistik liefert Avg + Max pro 5-s-Fenster.

### Hintergrund
- der v0.92-Trace eines Users 2026-05-31 (perf_24–27) zeigte: WDM-KS messtechnisch perfekt (0 XRuns, hw_default=44100 Hz, distinct=1 im Frame-Histogramm), aber hörbares Knistern wie Kabelbruch. AR-020 Mechanismus (a) und (c) damit definitiv widerlegt. Code-Review im Stretcher: `min10s=209 ms` exakt konstant entspricht ~2 Callback-Blocks unter dem 250-ms-Soll → der Feeder konnte einzelne Ticks nicht rechtzeitig liefern, weil der einzige Lock von der teuren Hop-Berechnung gehalten wurde. Die drei Fixes adressieren genau diese Engstelle.

---

## 0.92 — Audio-Diagnose: Sample-Rate-Mismatch und Callback-Frame-Histogramm (2026-05-30)

### Logs & Diagnose
- **Hardware-Sample-Rate im Stream-Diag-Log (AR-020 T1):** Sowohl `[Diag] Stream-Init Versuch` als auch `[Diag] Stream gestartet` zeigen jetzt zusätzlich `hw_default=XHz` — die native Sample-Rate des Audio-Devices. Wenn das nicht zu unserer angeforderten Rate (44100 Hz) passt, übernimmt der Treiber Resampling — auf manchen Hostapi/Codec-Kombinationen (WDM-KS + Realtek HD ist bekannt) ist die Qualität schlecht und als „komischer Klang"/„Geschwindigkeitsfluktuation" hörbar, ohne dass es zu Buffer-Underruns kommt. Wenn `hw_default ≠ angeforderte SR`, erscheint zusätzlich ein deutlicher `⚠ SR-MISMATCH (wir fordern NHz)`-Marker direkt in der Versuchs-Zeile.
- **Callback-Frame-Count-Histogramm (AR-020 T1):** Pro Stream werden die ersten 200 Aufrufe des PortAudio-Callbacks gezählt und einmalig als kompaktes Histogramm geloggt: `[Diag] Callback-frames-Histogramm (erste 200): min=1024 max=1024 distinct=1 | top: 1024×200 (100%)`. Liefert der Treiber konstante Block-Größen, steht `distinct=1` — schwankt er (Verdacht WDM-KS), sieht man die Verteilung sofort. Das Sampling ist ein billiger `list.append` pro Callback, kein Lock, kein I/O.
- **Hintergrund:** der Test eines Users 2026-05-30 (perf_log_22, T-Lap, WDM-KS) zeigte 4 min `xRuns=0` bei perfektem Buffer — trotzdem hörbare Pitch-Wackler und Vinyl-artige Störgeräusche. Der direkt anschließende MME-Test (perf_log_23) klang sauber. Die neuen zwei Diag-Zeilen klären in einem einzigen Trace, ob Sample-Rate-Mismatch (Mechanismus a) oder Frame-Count-Schwankung (Mechanismus c) die Ursache ist.

---

## 0.91 — Fade-Out-Stottern behoben, neuer logs/-Ordner (2026-05-30)

### Performance / Bugfixes
- **Fade-Out vektorisiert (AR-018):** Der Fade-Out-Block im PortAudio-Callback (`audio_engine.py`) enthielt eine Python-`for`-Schleife über 1024 Samples pro Audio-Block. Auf schwacher Hardware (der Celeron N3450 eines Users) verursachte das hörbares Stottern beim Fade-Out, weil ~4–10 % der Block-Zeit nur für die Fade-Logik draufgingen und der GIL die ganze Schleife lang gehalten wurde. Ersetzt durch NumPy-Array-Multiplikation (1 Aufruf statt 1024 Iterationen). Faktor 100–500× Speedup, Fade-Out läuft jetzt glatt auch auf schwacher CPU.

### Logs & Diagnose
- **Diagnose-Center (Hilfe → Diagnose-Center…):** Neues Fenster mit eingebauten Tests, das dem Entwickler bei Aussetzer-Problemen die nötigen Daten liefert — ohne dass du externe Tools installieren musst. Jeder Test erklärt vorher in Klartext was er misst und was du tun sollst. Verfügbare Tests:
  - **A — System-Snapshot:** Eckdaten Windows/CPU/RAM/Audio-Geräte/Backends, Callers-Caddy-Version, INI-Inhalt.
  - **D — QTimer-Inventur:** listet alle aktiven Timer im Programm — hilft beim Aufspüren periodischer Aussetzer.
  - **F — Externe-Last-Sampling (60 s):** prüft welche anderen Programme während der Wiedergabe CPU brauchen (Antivirus, Cloud-Sync, Treiber-Services).
  - **G — Stall-Sentinel:** zeigt Stand der dauerhaften Hintergrund-Überwachung von Main-Thread-Blockaden während der Wiedergabe.
  - **H — Bundle „Senden an Entwickler":** packt die letzten Logs in eine ZIP zum Mailen.
  - **B/C/E — Audio-Tests (in Vorbereitung):** Stille-Wiedergabe, Hostapi-Vergleich, Fade-Out-Stress kommen mit v0.92.
- **Zentraler logs/-Ordner:** Alle Logs landen jetzt in `<app_dir>/logs/`. Damit bleibt das Hauptverzeichnis aufgeräumt, und Diagnose-Daten sind an *einer* Stelle:
  - `logs/perf/perf_YYYY-MM-DD_HH-MM-SS.txt` — Perflog mit Zeitstempel pro Sitzung (vorher fester Name `perf_log.txt`, jeder Start überschrieb den letzten). Automatische Rotation: nur die jüngsten 20 Sitzungen werden behalten.
  - `logs/crashes/crash_*.log` — Crash-Logs (vorher im Root)
  - `logs/rules.log` — Rules-Engine-Log (vorher unter `rules/`, dort liegen jetzt nur noch die User-Rules-JSONs)
  - `logs/system_report.txt` — Systembericht (vorher im Root)
- **Automatische Migration beim ersten Start v0.91:** Vorhandene `perf_log.txt`, `crash_*.log`, `rules/rules.log` und `system_report.txt` werden einmalig in die neue Struktur verschoben.

---

## 0.90 — Sequenz-Editor & Sequenz-Limit pro Tanzprogramm (2026-05-27)

### Neue Features
- **Sequenz-Editor (BL-015):** Neues Fenster „Sequenzen → Sequenz-Editor…" zum Erstellen und Bearbeiten von Sequenzen. Kopfbereich mit Typ (Pflichtfeld) und Schwierigkeit (vorbefüllte, editierbare Dropdowns), darunter ein Eingabefeld mit **einem Call pro Zeile**. Buttons: „+ Neu", „Speichern", „Auf Duplikate prüfen" (warnt, wenn die Eingabe bereits existiert) und „Schließen". Limit von 15 Calls wird live angezeigt und beim Speichern erzwungen. Bekannte Calls werden **grün** markiert (gemappt oder exakter Treffer); ein **Doppelklick** auf eine nicht-grüne Zeile öffnet einen schlanken Zuordnungs-Dialog mit durchsuchbarer Call-Auswahl (Matcher-Vorschlag vorausgewählt). Exakte Treffer werden beim Speichern automatisch gemappt, damit das Level berechnet wird. Aus dem SequenzView führt ein ✎-Button direkt zum Bearbeiten der angezeigten Sequenz. Nach dem Speichern wird die neue Sequenz garantiert sichtbar (Filter-Reset + Auswahl).
- **Sequenz-Limit pro Tanzprogramm (BL-132):** Im Tanzprogramm-Manager kann pro Programm ein „Sequenz-Limit" hinterlegt werden — ein beliebiger Call aus der Teaching Order (inkl. Programm-Separatoren wie „-- Mainstream --"). Beim Programmwechsel (Lokation laden oder manuell im Player) setzt der Sequenzen-Filter automatisch auf diesen Call. Jeder Caller definiert die Grenze einmalig selbst — wer auf MS wechselt, sieht nur MS-Sequenzen, wer auf A2 wechselt nur A2. Opt-out in Einstellungen → Sequenzen → „Filter automatisch auf Tanzprogramm setzen".

---

## 0.89 — Mausrad-Schutz, Feedback-Suppress, Call-Mapping Bulk-Confirm, Quality/ERR per Kontextmenue (2026-05-27)

### Neue Features
- **Kontextmenue Quality/ERR ±1 (BL-127):** Songliste, Playlist und Statistik-Dock (TOP/FLOP/Nie) zeigen im Rechtsklick-Menue vier neue Eintraege: Qualitaet +1/−1 und ERR +1/−1. Jeder Eintrag zeigt den alten und neuen Wert in der Form `[5>6]`. Am Wertebereichs-Rand (Quality 0/10, ERR 0/4) wird die jeweilige Aktion deaktiviert. Aenderungen werden sofort in die DB geschrieben; das Song-Daten-Dock synchronisiert sich live, wenn es denselben Song zeigt.
- **Feedback-Dialog: Session-Suppression:** Neue Checkbox „In dieser Sitzung nicht mehr fragen" zwischen Notiz-Feld und Buttons. Bei Haken wird das Auto-Feedback-Fenster fuer den Rest der Sitzung unterdrueckt — unabhaengig davon, ob „Uebernehmen" oder „Abbrechen" gedrueckt wird. Wirkt sowohl beim manuellen Feedback-Aufruf als auch beim automatischen Popup nach Songende. INI-Standard bleibt unangetastet und greift beim naechsten App-Start wieder.
- **Call-Mapping: Bulk-Confirm:** Im Call-Mapping-Dialog koennen jetzt mehrere Zeilen markiert (Ctrl/Shift+Klick, Ctrl+A) und per Button „Auswahl bestaetigen" gemeinsam in die DB geschrieben werden. Quelle wird auf `manual` gesetzt, Tabelle wird automatisch aus der DB neu geladen.

### Verbesserungen
- **Mausrad-Schutz fluechendeckend:** Im Song-Daten-Dock, Player (inkl. Volume- und Position-Slider) und im Einstellungen-Dialog ignorieren SpinBoxes, ComboBoxes, DateEdits und Slider Mausrad-Events. Versehentliches Scrollen ueber Feldern aendert keine Werte mehr. Im Einstellungs-Dialog gilt der Schutz fenster-weit — auch zukuenftig hinzugefuegte Felder sind automatisch geschuetzt.
- **Menue „Allgemeine Einstellungen":** Der Einstellungen-Dialog-Aufruf liegt jetzt im Menue „Einstellungen" (bisher unter „App") und heisst „Allgemeine Einstellungen…". Shortcut `Strg+,` bleibt erhalten. Das App-Menue enthaelt nur noch „Beenden".

### Bugfixes / Diagnose
- **Stall-Detektor schweigt im Leerlauf:** Der Main-Thread-Stall-Detektor (AR-F) meldet jetzt nur noch Blockaden waehrend ein Song laeuft. Bei Title-Bar-Drag oder Fenster-Resize entstehen durch Windows' modale Move-Loop scheinbare „Blockaden", die mit Audio-Aussetzern nichts zu tun haben — diese False Positives erscheinen jetzt nicht mehr im Perf-Log.

### Aufgeraeumt
- Toten Translation-Key `menu_settings` entfernt (durch `menu_general_settings` ersetzt)
- Drei NoScroll-Subklassen im Settings-Dialog entfernt (durch fenster-weiten Event-Filter ersetzt)

---

## 0.88 — Audition-Kanal + Einstellungen-Fenster + Anti-Ruckler (2026-05-26)

### Neues Feature: Audition-Kanal (BL-074)
- **Audition-Button** im Player: schmaler Button rechts neben Play, liegt optisch über Fade Out
- Song startet beim Drücken von Audition von vorne auf dem **sekundären Ausgang** (exklusiv — kein zweiter Stream)
- Kein History-Eintrag bei Audition; Rules werden nicht gefeuert
- Stop / Play / Song-Ende beenden Audition und stellen automatisch den Primärkanal wieder her
- **Primärer / Sekundärer Ausgang** jetzt getrennte INI-Keys (`audio/primary_device`, `audio/secondary_device`) mit eigener Lautstärke (`audio/secondary_volume`, Default 80 %)
- Beide Geräte-Dropdowns erscheinen im Einstellungen-Dialog (Audio-Sektion)
- **Migration:** `audio/output_device` → `audio/primary_device` läuft einmalig automatisch
- **Bugfix:** WASAPI-Fallback-Cache in `AudioEngine` — wenn ein Gerät beim Start auf System-Default zurückfällt, wird bei jedem Kanal-Wechsel (Audition → Primär) der Cache-Eintrag genutzt statt WASAPI erneut zu versuchen

### Neues Feature: Einstellungen-Fenster (BL-129)
- Neues Fenster „Einstellungen…" im App-Menü (Shortcut `Strg+,`)
- Liest alle relevanten INI-Sektionen generisch aus und stellt sie in Tabs dar
- Automatische Widget-Auswahl je nach Wert-Typ: Checkbox, SpinBox, DoubleSpinBox, Pfad-Button, ComboBox, DateEdit, LineEdit
- `SETTINGS_META`-Registrierungstabelle für bekannte Keys mit Labels, Tooltips, Wertebereichen und ComboBox-Optionen (Skin-Liste, Sprachen)
- Tabs: Anzeige, Pfade, Audio, Loop, Player, Playlist, Feedback, Sequenzen, Notizen, Lyrics, Debug, Rules (System)
- Buttons: OK / Abbrechen / Übernehmen
- Hinweis-Dialog wenn neustart-pflichtige Keys geändert wurden (Skin, Sprache, Debug, Audio-Flags)
- Live-Apply wo möglich: Zoom (Sequenzen/Lyrics/Notizen), Mindest-Lautstärke, Loop-Crossfade, Statusleisten-Player, Musikpfade
- Ausgeschlossen: `[General]`, `[Tutorials]`, `[custom-filter]`, alle `*_dock`-Sektionen
- Neue `settings_dialog.py` — standalone, kein Aufblähen von main.py

### Anti-Ruckler: Hostapi-Heuristik + Header-Latenz + Playlist-Refresh-Storm (AR-015 / AR-002)
- **L1 — WDM-KS-first Heuristik:** Beim Erststart (kein gespeichertes Gerät) wählt die App automatisch das beste verfügbare Audio-Backend: WDM-KS > WASAPI Shared > MME — DirectSound nie als Default. Hintergrund: der Hostapi-Matrix-Test eines Users 2026-05-26 (10 Sessions auf Celeron N3450) zeigt WDM-KS = 0 Ruckler, MME = 7–10, DirectSound = 15–25 pro 30-s-Session. Heuristik läuft in `_setup_audio_device_combo()`, speichert das gewählte Gerät sofort in INI und loggt `[Diag] Auto-Device-Heuristik (AR-015 L1)`.
- **L2 — Perf-Header beide Latenzen:** `[Sys]`-Header zeigt jetzt `Audio-Output (System-Default)` UND `Audio-Output (konfiguriert)` (wenn verschieden). `generate_compact_header(configured_device_index=...)` nimmt den gespeicherten Device-Index aus INI entgegen. Verhindert die Verwechslung: MME-Default-Latenz 90 ms vs. tatsächlich aktive WDM-KS-Latenz 11 ms (Befund 5 aus Hostapi-Matrix).
- **G — Playlist-Refresh-Storm behoben (AR-002):** Neue Methode `PlaylistWidget.add_entries_bulk(entries)` hängt alle Einträge intern an und ruft `refresh_display()` + `_notify_changed()` exakt einmal auf — egal wie viele Songs. Auto-Fill nutzt jetzt Bulk-Add statt N× `add_entry()`. Vorher: 24× `refresh_display` + 24× `_refresh_playlist_mirror`; nachher: 1× je.

---

## 0.87 — Dock-Open-Instrumentierung + Stall-Detektor 100 ms + Audio-Device-Routing-Diagnose (2026-05-25)

Erweitert die Diagnose-Werkzeuge aus 0.86 um zwei gezielte Messpunkte für Audio-Aussetzer-Ursachen, die wir in den User-Logs (Desktop + Laptop) gesehen aber nicht eingrenzen konnten. Hintergrund und Verdachtsfälle dokumentiert in `1_Source/docs/anti_ruckler_backlog.md` (Aufgaben J, N).

### Perf-Log: Dock-Toggle-Schritte einzeln gestempelt
- `_toggle_dock(...)` (zentraler Handler für alle Dock-Buttons in der Statusleiste, u. a. Planner, Lyrics, SongData) stempelt jetzt jeden Qt-Schritt einzeln: `setFloating(True)`, `show()`, `move()`, `raise_()`, `setFocus()`, `hide()`. Plus eine `TOTAL`-Zeile.
- Label enthält den Dock-Namen, damit Planner/Lyrics/etc. unterscheidbar sind.
- `_on_manager_button_clicked` (Planner-Button) bekommt zusätzlich Stempel um den `setCurrentIndex(sort)`-Trigger (löst `_apply_filter` aus).
- Zielt auf die Beobachtung vom Laptop eines Users (Celeron N3450): Underflow-Burst direkt nach Planner-Klick, mit Main-Thread-Stall von ~950 ms — bisher ohne sichtbare Ursache im Log. Die bekannte Qt-Falle `setFloating(True) ~90 ms` (siehe CLAUDE.md) skaliert auf schwacher CPU stark.

### Stall-Detektor-Schwelle gesenkt: 150 ms → 100 ms
- In den Logs eines Users vom Vormittag traten Underflows teilweise auf, ohne dass der Stall-Detektor (aus 0.86) etwas meldete — vermutlich weil Blocks zwischen 100–150 ms unter dem alten Cutoff lagen.
- Neue Schwelle 100 ms liegt sicher über dem normalen Scheduling-Jitter (~80–100 ms), fängt aber die Blocks zuverlässig, die den Python-PortAudio-Callback am GIL-Greifen hindern.

### Diagnostische Konsequenz für AR-014
- Die Underflows in den neuesten Logs eines Users (Desktop perf_log_8, Laptop perf_log_14) zeigen alle `BUFFER GEFUELLT` (255–325 ms Vorrat). Der Feeder ist nicht das Problem — der Python-Callback ist es, weil er bei jedem Aufruf den GIL braucht. Diese Version macht den Beleg dafür präziser, indem sie auch kleinere Stalls + Dock-Schritt-Kosten messbar macht.

### Audio-Device-Routing — Versuch / Fallback / Endergebnis (Nachzug am Abend)
Hintergrund: in einem Nachmittags-Test zeigte das `[Diag] Stream gestartet` immer noch `hostapi=MME`, obwohl ein User laut Video im Combo zweifelsfrei einen WASAPI-Eintrag gewählt hatte. Vermutet: stiller Fallback in `_ensure_stream`, weil die `try/except`-Kette dort bisher die Ursache verschluckt hat.

Drei neue `[Diag]`-Zeilen rund um den Stream-Start machen den Weg vom Combo bis zum aktiven Stream nachvollziehbar:
1. **Versuch (UI-seitig)** — `_on_audio_device_changed` loggt jeden Combo-Wechsel:
   `[Diag] Audio-Device Wechsel angefordert: idx=…, combo_label='…'`
2. **Versuch (Engine-seitig)** — `_ensure_stream` loggt vor dem ersten Stream-Open:
   `[Diag] Stream-Init Versuch: device=…, name='…', hostapi=…, exclusive=…`
3. **Fallback-Pfade** — wenn das Open mit dem User-Device scheitert:
   - `[Diag] Stream-Init fehlgeschlagen mit device=… (…) — Fallback 1 auf gleiches Device ohne extra_settings`
   - `[Diag] Stream-Init Fallback 1 ebenfalls fehlgeschlagen (…) — Fallback 2 auf System-Standard (…). User-Auswahl device=… wird IGNORIERT!`

Das bestehende `[Diag] Stream gestartet`-Event zeigt weiterhin das *tatsächlich* aktive Device + Hostapi (also nach Fallback). Reine Diagnose, keine Verhaltensänderung am Audio.

---

## 0.86 — Anti-Ruckler-Diagnose + MMCSS-Priorität für Audio-Feeder (2026-05-24)

Erweitert die Ursachensuche für Audio-Aussetzer (TIC-0025-Komplex) durch zwei neue Diagnose-Werkzeuge im `perf_log.txt` und einen ersten Lösungsversuch auf System-Ebene. Hintergrund und Verdachtsfälle dokumentiert in `1_Source/docs/anti_ruckler_backlog.md`, User-Anleitung in `1_Source/docs/diagnose_ruckler_user.md`.

### Audio-Feeder läuft mit MMCSS "Pro Audio" Priorität (Lösungsversuch)
- Der dedizierte `AudioFeeder`-Thread (seit 0.80) lief bisher mit normaler Windows-Thread-Priorität. PortAudio gibt seinem eigenen Callback-Thread bereits MMCSS, unser Python-Feeder hatte das nicht — der Windows-Scheduler konnte ihn dadurch hinter UI-Threads zurückstellen, selbst wenn der GIL frei war.
- Neu: Als allererste Aktion im Feeder-Run-Loop wird `AvSetMmThreadCharacteristicsW("Pro Audio")` via ctypes aufgerufen. Damit steht der Feeder im Scheduler über allen UI-Anwendungen.
- Per INI abschaltbar: `audio/mmcss_priority=false` falls Probleme auftreten.

### Perf-Log: Wallclock-Zeitstempel auf allen Zeilen
- Jede Zeile im `perf_log.txt` (außer `[Sys]`-Header) bekommt jetzt einen `HH:MM:SS.mmm`-Stempel vorangestellt. Damit lassen sich Ruckler-Beobachtungen mit Uhrzeit oder einer Video-Aufnahme exakt mit Log-Events korrelieren.

### Perf-Log: System-Header beim Start
- Beim ersten Öffnen des Perf-Logs wird ein `[Sys]`-Block geschrieben mit: Callers-Caddy-Version, Python/PySide6/Qt-Versionen, OS, CPU, RAM, PortAudio-Version, Default-Audio-Output, **aktiver Hostapi** (MME/DirectSound/WASAPI/WDM-KS), verfügbare Hostapis, Audio-Engine-Konstanten (`FEED_AHEAD`, `PREPROCESS`, `BLOCK`). Macht Logs verschiedener Sitzungen und User vergleichbar.
- Kosten: ~90 ms beim Start (nur wenn `debug/performance_logging=true`); ohne Subprocess-Calls.

### Perf-Log: PortAudio-Underflow-Events mit Buffer-Snapshot
- Bisher wurden Underflows nur als Zähler erfasst (`xRuns=N`). Jetzt schreibt jeder Underflow eine eigene `[Diag]`-Zeile mit Zeitstempel, Buffer-Stand und Diagnose-Hinweis:
  - `BUFFER LEER → Feeder/GIL-Verdacht` (unser Code konnte nicht nachfüllen)
  - `BUFFER GEFUELLT → Treiber/Hostapi/DPC-Verdacht` (PortAudio meldet trotz voller Daten — z. B. WASAPI-Shared-Glitch oder Treiber-DPC-Stall)
- Events werden im Callback in eine Deque gepusht (kein I/O im Callback selbst) und vom Feeder-Loop ins Log geschrieben.
- Beim Stream-Start zusätzlich `[Diag] Stream gestartet: '<Device>' hostapi=<...> sr=... blocksize=... latency=...`.
- Per INI abschaltbar: `audio/log_underflows=false`.

### Neue User-Doku
- `1_Source/docs/diagnose_ruckler_user.md` beschreibt für betroffene User in drei Schritten, wie sie Logs sammeln (Perflog aktivieren, LatencyMon, optional Video-Sync). Kann direkt an User mit Ruckler-Berichten weitergeleitet werden.

### WASAPI Exclusive Mode als Opt-in (AR-008)
- Die [Recherche](docs/anti_ruckler_backlog.md) hatte einen dokumentierten Glitch in Windows WASAPI Shared Mode (PortAudio Issue #303) als wahrscheinlichste Ursache für scheinbar zufällige Mini-Aussetzer identifiziert. Diese Version erlaubt User, WASAPI im Exclusive Mode zu nutzen — das umgeht den Bug komplett.
- Im Audio-Device-Selector wird jetzt der **Hostapi pro Gerät** angezeigt (`"Speakers (WASAPI)"`, `"UR22 mkII (ASIO)"`). Damit sieht der User direkt, welches Backend Windows nutzt.
- Neue **Checkbox "Exclusive"** in der Statusleiste neben dem Device-Combo. Aktiviert WASAPI Exclusive Mode für das gewählte Gerät; bei Init-Fehler automatisch Fallback auf Shared. Wirkt nur bei WASAPI-Geräten — andere Hostapis (MME, DirectSound, ASIO) ignorieren das Flag.
- Tooltip warnt: Exclusive Mode blockiert andere Audio-Programme systemweit (kein YouTube/Spotify nebenbei).
- INI-Schlüssel: `audio/wasapi_exclusive=true/false` (Default off).
- Wer ein ASIO-Interface besitzt (z. B. Steinberg UR22 mkII): einfach das ASIO-Gerät aus der Liste wählen — PortAudio routet automatisch über den ASIO-Hostapi, ohne zusätzliche Schalter.

### Hauptthread-Stall-Detektor im Perf-Log
- Der bestehende 50 ms `_update_all`-Timer misst jetzt die Lücke zwischen seinen Ticks. Ist die Lücke größer als 150 ms, war der UI-Thread blockiert — z. B. durch eine schwere Python-Operation, die den GIL belegt.
- Geloggt als `[Diag] Main-Thread blockiert: NNNms (erwartet 50ms) (letzter [Perf]-Event vor XXXms: ...)`. Über den Wallclock-Stempel direkt korrelierbar mit Underflow-Events: war kurz vor einem `[Diag] PortAudio output_underflow` ein Main-Thread-Stall, ist GIL-Contention die wahrscheinliche Ursache.
- Der angehängte "letzter [Perf]-Event"-Hinweis nennt die zuletzt instrumentierte Operation, die vor dem Stall lief — gibt sofort den Verdächtigen, ohne im Log scrollen zu müssen.
- Reines Logging, keine Verhaltensänderung.

### Verbesserte AudioBuf-Klassifikation
- Im ersten Live-Test zeigte sich, dass das bisherige `⚠ KRITISCH` häufig falsch alarmierte: `min10s=0` tritt bei jedem Tempo/Pitch-Change auf, weil der Stretcher dabei kurz geflusht wird — der 5 s Pre-Roll fängt das aber ab, sodass PortAudio keinen Underflow meldet und nichts hörbar wird.
- Neue Label-Stufen in der `[AudioBuf]`-Zeile:
  - `⚠ XRUN (+N echter Aussetzer)` — der PortAudio-xRun-Counter ist seit dem letzten Sample gestiegen, das ist ein hörbarer Aussetzer auf Treiber-Ebene
  - `△ Buffer-Dip (vermutl. Stretcher-Flush, harmlos)` — `min10s` war kurz auf 0, aber kein neuer xRun (typisch bei Tempo/Pitch-Wechsel)
  - `△ niedrig` — `min10s` 50–120 ms (Vorwarnung)
- Beim Sichten eines Logs reicht damit Suche nach `⚠ XRUN` und `[Diag] output_underflow` — der Rest ist Rauschen.

### Hinweis
Diese Version enthält ausschließlich Diagnose-Verbesserungen plus den MMCSS-Fix-Versuch. Die in der Recherche gefundenen weiteren Hebel (WASAPI-Exclusive/ASIO-Wahl, Stall-Detektor, Numba/CFFI) sind im Anti-Ruckler-Backlog erfasst und werden je nach Ergebnis der ersten Test-Runde priorisiert.

---

## 0.85 — Filter-Header + Kritischer Bugfix Loop-Datenverlust (2026-05-23)

### Bugfix: Loop-Werte wurden beim Songliste-Klick fremdüberschrieben
- **Symptom**: 33 Songs hatten identische `loop_in=0.34` Werte mit unterschiedlichen `loop_out` (geclustert nach Quell-Song). Original-Loops waren verloren.
- **Ursache**: `_save_current_song` lief in `_on_file_loaded` mit dem **neuen** `_current_song`, aber dem Engine-Loop-Snapshot des **alten** Songs. Beim Durchklicken durch die Songliste hat jeder neue Song die Loop-Werte des vorherigen geerbt.
- **Fix (Variante C+ — Direkt-Persistierung + Dirty-Flags)**:
  - Jede Loop-Änderung (Set Loop In/Out, Beat Snap, Clear Loop) schreibt **sofort** in die DB — kein Sammel-Save beim Song-Wechsel mehr.
  - Tempo und Pitch nutzen ein Dirty-Flag und werden beim Verlassen des Feldes (Enter / Fokus-Wechsel) oder vor dem nächsten Song-Wechsel persistiert. Während eines Slider-Drags **kein** DB-Write — schützt den Audio-Buffer.
  - Snapshot-Mechanismus (`_snapshot_loop_values`, `_saved_loop_in/out`, `on_before_load`) komplett entfernt.
  - Neue Helper-Methode `_flush_player_values()` wird an allen Song-Wechsel-Punkten aufgerufen (Songliste, Playlist, Vorhören, Drag&Drop, closeEvent).
- **DB-Cleanup**: 33 betroffene Songs auf `loop_in=0, loop_out=0` zurückgesetzt (Loops müssen neu eingerichtet werden).
- **Backups**: DB unter `2_Test/callers_caddy.db.backup_20260522_225318`, Source unter `1_Source/src/_fallback/*.bak_loop_fix_20260522_231059`.
- **Testplan**: `5_Tickets/loop_data_loss_testplan.md`
- **Folge-Ticket**: [TIC-0027](5_Tickets/TIC-0027_audio_buffer_underrun_tempo_drag/ticket.md) — Audio-Buffer-Underrun beim Tempo-Drag (eigenständiges Performance-Thema)

### Feature: SongFilterBar — einheitlicher Filter-/Sortierbereich (BL-101 + BL-121)
- **Neue gemeinsame Komponente `SongFilterBar`** ersetzt die bisherigen separaten Filter-Bereiche in Songliste und Planner.
- **Songliste** hat jetzt vollständige Parität mit dem Planner:
  - **Typ-Filter**: RadioButtons Alle / Patter / Singing
  - **Genre-Filter**: ComboBox mit allen verfügbaren Genres
  - **Sortierung**: Alphabetisch / Qualität / Zuletzt gespielt / **Empfehlung** (neu)
  - **Custom-Filter**: Button zum Laden gespeicherter Playlisten als Vorauswahl (BL-097)
  - **Suchfeld**: Live-Filter über Titel, Label, Dateiname
- **Planner** bleibt unverändert — nutzt jetzt ebenfalls `SongFilterBar` intern.
- Kein doppelter Code mehr: Filterlogik, Custom-Filter-Dialog, Persistenz und Sortierung leben an einer einzigen Stelle.

### Feature: Zufälliger Tiebreaker bei Gleichstand (BL-113)
- Bei **Sortierung nach Qualität** und **Sortierung nach Empfehlung** werden Songs mit identischem Score nicht mehr immer in DB-Reihenfolge angezeigt, sondern innerhalb der Gleichstands-Gruppe zufällig gereiht.
- Neue **„Zufall"-Checkbox** neben dem Sort-Dropdown zum Ein-/Ausschalten — bei Alphabetisch und Zuletzt gespielt automatisch ausgegraut.
- Die Reihenfolge ist **stabil innerhalb einer Session** — kein Neugemischt bei jedem Tastendruck oder Filter-Wechsel.
- Alphabetische Sortierung und Zuletzt-gespielt-Sortierung bleiben unverändert deterministisch.
- Wirkt überall wo `SongFilterBar` verwendet wird: Songliste, Planner-Pool, Auto-Fill.

### Feature: Statusleiste — Miniatur-Abspielfortschritt (BL-128)
- **Neues Widget `_StatusBarPlayerBar`** in der Statusleiste zeigt dauerhaft den Wiedergabefortschritt:
  - Fortschritts-Füllung (semi-transparent, Akzentfarbe aus Skin)
  - Loop-In / Loop-Out als vertikale Linien (wie im Hauptplayer-Slider)
  - 7 gleichbreite Sektionsstreifen (Singing-Call-Farben O/1/2/M/3/4/C) am unteren Rand
- Das Widget ist **skin-bewusst** — Farben wechseln bei Skin-Wechsel automatisch.
- Ein-/ausschaltbar per INI: `display/statusbar_player = true` (Standard) / `false`
- Kein Performance-Overhead: Update nur wenn sich Werte tatsächlich ändern (`update_state` mit Dirty-Check).

### Refactoring: Entwicklungsrichtlinie dokumentiert
- Neue **Refactoring-Vollständigkeitsregel** in `1_Source/docs/12_erfahrungen.md`:
  - Zweiphasen-Vorgehen: erst Aufbau (neues erstellen), dann nach Test Abbau (Altes entfernen)
  - Pflicht-Checkliste: Aufbau-Liste + Abbau-Liste vor dem Coden
- `CLAUDE.md` verweist jetzt mit Tabelle auf alle Subdokumente (wann welches lesen)

---

## 0.84 — Evening Planner Transfer-Dialog + Audio-Device-Selector + Crash-Fix (2026-05-22)

### Feature: Evening Planner — Transfer-Dialog mit Bestätigung
- **„Zur Playliste" und „Zu Notizen"** zeigen jetzt immer einen Bestätigungs-Dialog — auch wenn keine Songs bestätigt sind.
- Der Dialog informiert über die Anzahl bestätigter und unbestätigter Songs und bietet drei Optionen: **Alle übertragen / Nur bestätigte / Abbrechen**.
- Sind alle Songs bereits bestätigt, entfällt die Auswahlmöglichkeit und der Transfer läuft direkt durch.
- Nach dem Transfer erscheint eine Rückmeldung mit der Anzahl übertragener Songs.
- **Bugfix:** Wenn nichts bestätigt war, passierte beim Klick auf die Transfer-Buttons schlicht nichts — kein Dialog, keine Meldung. Behoben.

### Bugfix: Evening Planner — falsche Reihenfolge beim Notizen-Export
- Songs erschienen nach dem Export in die Notizen in umgekehrter Reihenfolge.
- Ursache: das Notes-Widget fügt neue Einträge immer oben ein (`index=0`), wodurch beim sequenziellen Einfügen der letzte Song oben landete.
- Fix: Die Export-Liste wird vor dem Einfügen umgekehrt, sodass die Reihenfolge aus dem Evening Planner erhalten bleibt.

### Feature: P/S-Markierung in Notizen-Shortcodes
- Beim Export in die Notizen werden Songs jetzt als **P** (Patter) oder **S** (Singing Call) markiert: `[load_song title="..." mode="P"]`.
- Verhindert Verwechslungen bei Songs, die für beide Typen registriert sind.
- Rückwärtskompatibel: Songs ohne Typ-Zuordnung verwenden weiterhin das alte Format `[load_song "..."]`.

### Feature: Audio-Ausgabegerät wählen (BL-126)
- **Neue ComboBox** dauerhaft in der rechten Statusleiste zum Wählen des Audio-Ausgabegeräts.
- Zeigt alle verfügbaren Ausgabegeräte des Systems (gefiltert auf Ausgabe-fähige Geräte).
- Erster Eintrag: **System-Standard** (bisheriges Verhalten).
- Gerätewechsel funktioniert auch während laufender Wiedergabe — der Stream wird sofort auf das neue Gerät umgeschaltet.
- Auswahl wird in der INI gespeichert und beim nächsten Start automatisch wiederhergestellt.
- Fallback: Ist das gespeicherte Gerät nicht verfügbar (z. B. USB-Soundkarte nicht angeschlossen), startet die App automatisch mit dem System-Standard.

### Bugfix: Crash nach Audio-Device-Disconnect (TIC-0026)
- **Crash „Cannot operate on a closed database"** trat auf wenn ein Audio-Gerät getrennt wurde: Der Feeder stoppte die Wiedergabe, ein bereits eingereihter Timer-Callback versuchte danach noch auf die bereits geschlossene Datenbank zuzugreifen.
- Fix: `timer.stop()` wird jetzt als allererste Aktion in `closeEvent` ausgeführt. Zusätzliche `is_open()`-Guards in `_do_auto_advance` und `_get_current_target_duration` verhindern Zugriffe auf eine geschlossene DB.
- **Audio-Recovery:** Wird ein Gerät während der Wiedergabe getrennt (USB, HDMI), läuft die Wiedergabe nach einem kurzen Ausfall automatisch auf dem nächsten verfügbaren Gerät (i. d. R. interner Lautsprecher) weiter. Der Stream wird alle 2 Sekunden auf Aktivität geprüft und bei Bedarf neu gestartet.

---

## 0.83 — Feedback-Notizen + Lokations-Tipps + KI-Metadaten für Quality/ERR (2026-05-21)

### Feature: Notizfeld im Feedback-Dialog
- **Neues Textfeld „Notizen für die Zukunft"** im Feedback-Dialog (nach den Quality- und ERR-Buttons), 3-zeilig.
- Wenn eine Lokation gewählt ist: Eintrag wird beim OK direkt als neue Notiz **ans Ende der Notizliste** der aktuellen Lokation angefügt — ideal als Gedächtnisstütze für den nächsten Abend.
- Wenn keine Lokation gewählt: Feld deaktiviert mit erklärendem Hinweistext im Platzhalter („Zuerst eine Lokation wählen").
- Speicherung direkt in die DB (robust gegen lazy-init des Notes-Docks) + anschließender Refresh des NotesWidget.

### Feature: Geplante Anzahl Tips pro Lokation
- **Neues Einstellungsfeld** im Lokations-Settings-Dialog (unter dem Tempo-Spinner): Anzahl der geplanten Tips pro Abend.
- SpinBox 0–40, 0 = keine Vorgabe (wird als „– (keine Vorgabe)" angezeigt).
- Beim Lokationswechsel wird der Wert automatisch an zwei Stellen übernommen:
  - **Autofill-Dialog** (Zauberstab im Planner): `spin_tipps` startet mit dem Lokations-Wert statt fest verdrahtetem Standardwert 8.
  - **Evening Planner**: `_spin_tips` wird auf den Lokations-Wert gesetzt.
- DB-Migration: neue Spalte `planned_tips INTEGER` in der `locations`-Tabelle.

### Feature: KI-Metadaten-Export für Quality und ERR (Potential-Widget)
- **Quality und ERR** sind jetzt wählbare Felder im „Lücken exportieren"-Dialog.
  - „Fehlend" bedeutet: `quality = 0` bzw. `err = 0`.
- **KI-Prompt** erklärt Quality und ERR mit vollständigen Anweisungen:
  - Quality: Caller-Eigeneinschätzung (KI kann das nicht beurteilen) → KI setzt immer 6, Caller korrigiert selbst.
  - ERR: Tänzer-Reaktion (1 = Höhepunkt bis 4 = Beruhigung) → KI schätzt anhand Bekanntheit, Mitgrölfaktor, emotionaler Wirkung. Feld ist Pflicht, nie auslassen.
- **Import** verarbeitet quality und ERR als Integer-Felder (`update_song_simple_field`). Wert 0 wird beim Import übersprungen.
- **Buttons im FlowWidget**: alle Buttons liegen jetzt nebeneinander und umbrechen automatisch in die nächste Zeile wenn der Platz nicht reicht — wiederverwendbare `_FlowWidget`-Klasse für die gesamte App.

---

## 0.82 — Feedback-Dialog + Musik- und Lyric-Varianten + Pattern→Patter (2026-05-20)

### Feature: Song-Feedback nach dem Abspielen (BL-119 + BL-035)
- **Neuer modaler Feedback-Dialog** erscheint nach jedem Songende (natürliches Ende, Fadeout, manueller Stop), wenn `feedback/enabled = true` in der INI gesetzt ist (Standard: aus).
- **Quality-Buttons 0–10** mit Farbgradient von Weiß (0 = nicht bewertet) über Hellgrün bis Waldgrün (10 = exzellent). Aktuell eingestellter Wert ist hervorgehoben.
- **ERR-Buttons 0/4/3/2/1** in der Reihenfolge schwächste → stärkste Tänzer-Reaktion, eingefärbt mit den Evening-Planner-Farben (Grau/Blau/Grün/Amber/Rot). Tooltips erklären die Bedeutung beim Hover.
- **Adaptive Textfarbe:** Dunkler Text auf hellen Buttons, weißer Text auf dunklen — automatisch via Leuchtdichte-Formel.
- Esc oder „Abbrechen" schließt ohne Speichern. Nur geänderte Felder werden in die DB geschrieben.
- **Auto-Advance wartet** automatisch bis der Dialog geschlossen ist (modaler Dialog blockiert den Main-Thread).
- **Manueller Aufruf** jederzeit über den neuen „Feedback"-Button im Song-Daten-Dock (neben „Erweiterte Daten" und „Song löschen").

### Feature: Mehrere Musik- und Lyric-Dateien pro Song (BL-XXX)
- **Varianten-Verwaltung** im Dialog „Erweiterte Song-Daten" (neuer Tab „Varianten").
- Über **+ Musik-Variante** bzw. **+ Lyric-Variante** können beliebig viele Alternativdateien pro Song eingetragen werden — mit sprechendem Namen (z.B. „Live-Version") und Dateiauswahl-Dialog.
- Varianten werden in der `song_properties`-Tabelle gespeichert (`music_2_name`, `music_2_file`, etc.), keine Schema-Änderung nötig.
- Löschen einer Variante mit ✕-Button; verbleibende Varianten werden automatisch neu nummeriert.
- Sind Varianten vorhanden, erscheinen im **Song-Daten-Dock** direkt unterhalb des Dateinamens bzw. der Lyrics-Zeile **Auswahl-Buttons**: „Default" / „Standard" ist immer die erste und vorausgewählte Option.
- Klick auf eine Musik-Variante lädt sie sofort im Player (PathManager sucht wie bei Hauptdateien in allen konfigurierten Music-Slots).
- Klick auf eine Lyric-Variante zeigt sie sofort im Lyrics-Widget.
- Die aktive Lyric-Variante bleibt beim Bearbeiten von Songfeldern (Autosave) und Skin-Wechsel erhalten. Beim Wechsel auf einen anderen Song wird immer auf „Standard" zurückgesetzt.
- Datei-Dialoge starten standardmäßig im jeweiligen Music- bzw. Lyrics-Ordner; portabler Dateiname wird relativ gespeichert.
- **Bugfix:** Varianten-Buttons sprangen nach jeder Player-Rückmeldung auf „Standard" zurück. Aktive Variante wird jetzt im Widget gemerkt und beim Button-Rebuild korrekt wiederhergestellt.

### Umbenennung: „Pattern" → „Patter"
- Auf Empfehlung eines amerikanischen Callers: Die gesamte UI verwendet jetzt den korrekten Begriff „Patter" statt „Pattern" — in allen deutschen und englischen Texten (Checkbox, RadioButton, Import-Dialog, Evening-Planner, Statistik, Spaltenüberschriften, Tooltips, Tutorial-Texte).
- Interne Code-Variablen und DB-Felder (`is_pattern` etc.) bleiben unverändert.

---

## 0.81 — Bugfix: Slider-Anzeige bei Tempo-Änderung und Loop-Audition (2026-05-18)

### Bugfix: Zeitanzeige inkonsistent bei verändertem Tempo
- **`label_time_current` zeigte Original-Sekunden**, `label_time_total` hingegen Echtzeit-Dauer — unterschiedliche Einheiten. Beispiel bei 3-Min-Song, Tempo 1,5×, nach 1 Minute: Labels zeigten „1:30 / 2:00" (impliziert 75 %), Slider stand korrekt bei 50 %. Jetzt zeigt auch die laufende Zeit Echtzeit: `pos × dur / orig_dur`. Labels und Slider stimmen wieder überein.

### Bugfix: Slider friert bei Loop-Audition ein
- **Slider blieb während der 5-Sekunden-Vorhörphase** (vor dem ersten Loop-Sprung) auf der `loop_in`-Position stehen. Ursache: `_estimate_playback_pos()` klemmte die Position auf `max(loop_in, ...)`, sobald der Feed-Pointer nach dem Feed-Ahead-Wrap bereits hinter `loop_in` lag — obwohl der Audio-Callback noch im Pre-Loop-Segment spielte. Fix: Bei `pos < loop_in` wird jetzt `_playback_sample` als Näherung verwendet (exakt bei Tempo 1,0; leichte Abweichung bei anderen Tempos).

---

## 0.80 — Audio-Architektur: Dedizierter Feeder-Thread (2026-05-15)

### Audio-Aussetzer endgültig behoben (TIC-0025)
- **Dedizierter Audio-Feeder-Thread** in der `AudioEngine`. Bisher wurde der WSOLA-Stretcher vom UI-Main-Thread aus gefüllt (alle 50 ms via QTimer aus `PlayerWidget.update_display`). Damit war das Audio-Feeding vollständig vom UI-Thread abhängig: jede GIL-Blockade > 500 ms (Loop-Finder-Completion, DB-Operationen, restoreState) führte zu hörbaren Aussetzern. **Jetzt läuft ein eigener Daemon-Thread (`AudioFeeder`)**, der den Stretcher unabhängig vom Main-Thread alle 20 ms nachfüllt.
- **`FEED_AHEAD_SECONDS`: 0.5 s → 5.0 s.** Der Stretcher puffert ab sofort 5 Sekunden Audio vor. Selbst wenn der Main-Thread mehrere Sekunden blockiert, hat der Audio-Callback genug Daten zum Abspielen.
- **Thread-sichere Zustands-Updates** via `threading.Lock`: `load()`, `seek()`, `play()` und `_flush_and_refeed()` halten den Lock, während sie `_feed_pos`, `audio_data` oder den `stretcher` ändern. Keine Race-Conditions zwischen Feeder-Thread und Main-Thread möglich.
- **Ergebnis:** Ein aktiver AudioStream hat ab jetzt absolute Priorität — er wird nicht mehr von UI-Operationen ausgehungert.

### Weitere Rule-Aktionen entkoppelt
- **`dual_view_toggle` deferred** via `QTimer.singleShot(0, ...)` — gleiches Muster wie `layout_load` in v0.79. Die Toggle-Pfade mit `restoreState`/`restoreGeometry` blockierten bis zu 105 ms.
- **`system_ping` asynchron** im Daemon-Thread — `winsound.Beep` blockierte den Main-Thread synchron für die volle Tondauer (~300 ms). Trigger ist jetzt sofort durch, der Beep spielt parallel.

### Bugfix: Ruckeln ohne UI-Interaktion (Nachbessserung, 2026-05-16)
- **WSOLA-Processing aus dem Audio-Callback herausgelöst.** Bisher rief `StreamingTimeStretcher.retrieve()` im Audio-Callback `_process_one_hop()` auf — also Kreuzkorrelations-Berechnung mit variabler Laufzeit direkt im Echtzeit-Thread. Bei GIL-Contention oder CPU-Lastspitzen überschritt das gelegentlich das Callback-Budget (~23 ms bei 1024 Frames/44100 Hz), was zu ~180 ms Buffer-Underruns führte. Analyse via isolierter Audioaufnahme: ein Beat mit regulärem 0,47 s-Abstand erschien 0,18 s verspätet — klassisches Underrun-Muster.
- **Neue `preprocess()`-Methode** im `StreamingTimeStretcher`: befüllt den Output-Buffer im Feeder-Thread vor. `retrieve()` liest seitdem nur noch aus dem fertigen Buffer (O(1) Array-Slice) — keine Berechnung mehr im Callback.
- **`PREPROCESS_OUTPUT_SECONDS = 0.25 s`**: Der Feeder hält 250 ms vorverarbeitetes Audio bereit. Nach `play()`, `seek()` und `_flush_and_refeed()` wird der Output-Buffer sofort neu befüllt.
- **Audio-Buffer-Diagnostik** (aktiv bei `performance_logging = true`): alle 5 s werden aktueller Buffer-Stand und Rolling-Minimum der letzten 10 s in `perf_log.txt` geschrieben. Verifiziert auf Desktop und Laptop: `min10s ≥ 186 ms`, `xRuns = 0`.

---

## 0.79 — Performance: layout_load deferred (2026-05-15)

### Bugfix: Audio-Aussetzer bei Layout-Wechsel durch Rules (TIC-0025)
- **`layout_load`-Aktion deferred** — `restoreState`/`restoreGeometry` blockierten ~75 ms synchron auf dem Main-Thread (GIL), genau beim `song_started`-Trigger. Mit `QTimer.singleShot(0, ...)` wird der Layout-Wechsel in den nächsten Event-Loop-Tick verschoben, sodass der Audio-Callback zuerst läuft. Identisches Muster wie die bereits deferred `play`-Aktion.

---

## 0.78 — Performance: Audio-Aussetzer (2026-05-15)

### Bugfix: Song-Aussetzer im Livebetrieb (TIC-0025)
- **Songliste: `set_last_played_map` optimiert** — bisher wurden beim Song-Start alle 2401 Tabellenzeilen neu geschrieben (144 ms GIL-Block auf dem UI-Thread). Jetzt werden nur noch die tatsächlich geänderten Zeilen aktualisiert (typisch: 1 Zeile, ~0 ms). Behebt die Hauptursache für Audio-Aussetzer auf schwächeren Rechnern.
- **`_apply_filter` baut `_row_by_id`-Dict** auf (song_id → Zeilenindex) für direkten Zugriff ohne lineare Suche.

### Rule Engine: Aktions-Timing im Log
- Jede Rule-Aktion protokolliert jetzt ihre Ausführungszeit in `rules/rules.log` (z.B. `song_list_refresh({}) [2.1ms]`). Erleichtert die Diagnose von Performance-Problemen im Livebetrieb.

---

## 0.77 — Permanent Custom-Filter (2026-05-14)

### Planner — Permanente Custom-Filter-Slots
- **„Permanent"-Toggle-Button** in jeder der 4 Custom-Filter-Slot-Zeilen (hinter dem Entfernen-Button)
- Ist der Button gedrückt, wird der Dateipfad der geladenen Playlist in der INI (Sektion `custom-filter`) gespeichert
- Beim Entfernen eines Slots wird der Permanent-Status automatisch zurückgesetzt
- Beim ersten Öffnen des Planners in einer Session werden permanente Einträge aus der INI gelesen und die Playlisten automatisch als Custom-Filter geladen

---

## 0.76 — Planner Custom-Filter (BL-097) (2026-05-12)

### Planner — Custom-Playlist-Filter
- **„Custom"-Button** in der Filter-Zeile (nach Alle/Pattern/Singing, vor Genre): öffnet den neuen Custom-Filter-Dialog
- **Custom-Filter-Dialog**: bis zu 4 feste Slots, je mit [Laden]- und [Entfernen]-Button; lädt gespeicherte Playlist-TXT-Dateien (aktuelles und altes Format)
- **Vorschau-Tabelle** im Dialog zeigt die Schnittmenge aller geladenen Slots in Echtzeit
- **Anzeigename** per Doppelklick auf den Slot-Namen änderbar (Playlist-Daten bleiben unverändert)
- **Extra-Zeile im Planner** erscheint nach dem Übernehmen mit Checkboxen pro geladenem Slot — nur sichtbar wenn mindestens eine Playlist geladen ist
- Checkboxen an/aus filtert den Song-Pool sofort auf die Schnittmenge der aktiven Playlisten
- Alle anderen Filter (Suche, Sortierung, Typ, Genre) bleiben weiterhin wirksam
- Filter ist session-only (kein Persist beim App-Ende)

---

## 0.75 — Quality + ERR Füllen, Evening Planner Fixes (2026-05-11)

### Neues Tab im Potential-Widget: Quality + ERR Füllen
- **Einzel-Datensatz-Durchlauf**: Songs mit fehlender Quality oder ERR-Bewertung werden einzeln angezeigt — kein Listenspringen mehr
- **Song-Info**: Titel (fett), darunter Typ (Pattern / Singing / Pattern + Singing), Label, aktueller Quality- und ERR-Wert
- **Quality-Buttons** (1–10): nur sichtbar wenn Quality nicht gesetzt; aktueller Wert hervorgehoben
- **ERR-Buttons** (1–4): in ERR-Farben (Rot / Orange / Grün / Blau); nur sichtbar wenn ERR nicht gesetzt
- **Auto-Advance**: Sobald beide Werte gesetzt sind, springt die Anzeige automatisch zum nächsten Song
- **„▶ Vorhören" / „⏹ Stopp"** Button neben dem Titel: lädt den Song in den Player und startet die Wiedergabe; zweiter Klick stoppt
- Navigation mit „◀ Zurück" / „Weiter ▶" (gut lesbar) + Zähler „Song X von Y"
- Badge-Count im Tab-Titel

### Evening Planner Fixes
- **ERR-Balken erschienen nie**: Songs mit `err=0` (nicht bewertet) lieferten `patter_err=0` → `_draw_bar` zeichnete nichts. Fix: Songs mit `err=0` aber vorhandenem Slot bekommen einen **grauen Balken** auf Ziel-ERR-Höhe (konsistent mit Tabellen-Verhalten)
- **Dock nicht dockbar**: Evening Planner Dock ist jetzt nur noch schließbar (kein Movable/Floatable) — bleibt auch nach `restoreState()` fest

### Weitere Fixes
- **KI-Prompt** im Metadaten-Tab ist jetzt immer auf Englisch
- **Statistik-Texte** nach Export/Import/CSV-Abgleich vollständig übersetzt (keine hardcodierten deutschen Strings mehr)

---

## 0.74 — Metadaten-Werkzeuge: Song-Properties, CSV-Abgleich, Metadaten-Export/Import (2026-05-11)

### Neue Funktion: Erweiterte Song-Daten (BL-094)
- **Generische `song_properties`-Tabelle**: Speichert beliebige Schlüssel-Wert-Paare pro Song (initial: `original_artist`, `release_year`)
- **Button „Erweiterte Daten"** im Song-Datensatz öffnet einen generischen Editor mit bearbeitbarer Key-Value-Tabelle
- **Label-Feld** umbenannt zu „Label + Nr." mit Beispiel-Platzhalter „z.B. SQR 123"

### Neues Widget-Layout im Potential-Widget
- **Umbau zu QTabWidget**: Jede der 10 Prüfungen bekommt einen eigenen Tab (Badge-Count im Tab-Titel)
- Erster Tab wird beim Öffnen automatisch geladen
- Tab-Scroll-Buttons verbreitert (24 px Mindestbreite)
- **Neuer Tab „Metadaten füllen"** (BL-114) mit drei Werkzeugen:

### Metadaten-Werkzeuge (BL-114)

#### Abgleichen mit Music CSV
- **CSV-Abgleich-Button** (an erster Stelle): Gleicht fehlende Song-Metadaten automatisch mit einer mitgelieferten CSV-Datenbank ab
- Dreistufiges Matching: 1) exakter Titel, 2) Label-Code + Nummer, 3) Fuzzy (difflib, Schwelle 0.80)
- **Preview-Tabelle** mit Checkbox pro Song, „Alle / Keine" Auswahl
- Grüne Zellen = eindeutiger Treffer, gelbe Zellen = mehrdeutig → Doppelklick öffnet Auswahllist
- Unterstützte Felder: Interpret, Label/Nr., Genre, Original Artist, Erscheinungsjahr
- `music-extended-data/music_extended_data.csv` wird bei jedem Release automatisch mitgeliefert

#### Lücken exportieren (JSON)
- Feld-Auswahl-Dialog (welche leeren Felder exportieren?)
- Exportiert Songs mit fehlenden Daten als JSON mit `genres_available`-Liste
- Statistik nach Export (Anzahl Songs, fehlende Felder)

#### KI-Prompt anzeigen
- Kopierfertige Anleitung für KI-Assistenten, **immer auf Englisch**
- Enthält alle im System vorhandenen Genres als erlaubte Werte

#### Daten importieren (JSON)
- Lädt angereicherte JSON zurück, zeigt Preview-Tabelle mit Checkbox-Auswahl
- Unbekannte Genres werden markiert und übersprungen
- Alle Statistik-Texte vollständig übersetzt (keine hardcodierten deutschen Strings mehr)

### Playlist-Kompatibilität
- **V1-Playlisten** (nur Titel, altes Format) werden wieder korrekt geladen
- Neue Playlisten werden mit Titel statt Dateiname gespeichert (Format V3: Typ + Loop-Count + Titel)
- Loader erkennt alle drei Formate automatisch (V1/V2/V3)

---

## 0.73 — Abendplanung: Evening Planner Widget (2026-05-10)

### Potential-Widget: Neue Prüfer
- **Ohne ERR** (BL-115): Listet Songs auf, bei denen der ERR-Wert noch nicht gesetzt ist (`err = 0`). Doppelklick navigiert direkt zum Song.
- **Ohne Genre** (BL-116): Listet Songs ohne Genre-Zuweisung auf. Doppelklick navigiert direkt zum Song.
- **Inkompatibles Format** (BL-117): Prüft ob Audiodateien vom internen Decoder (soundfile/libsndfile) gelesen werden können. Erkennt MP3s mit nicht-standardkonformen Frames, die nur ffmpeg-basierte Player lesen können. Läuft wie BPM- und Loop-Check mit Zeitschätzung (5 Sample-Dateien → Hochrechnung → Bestätigung → vollständiger Check im Hintergrundthread). Doppelklick navigiert zum betroffenen Song; Ignorieren-Funktion vorhanden.

### Bugfix
- **Import neuer Songs schlägt fehl** (`You did not supply a value for binding parameter :err`): `err` fehlte im `insert()`-Dict — die Spalte war beim Hinzufügen von BL-111 im SQL ergänzt worden, aber nicht im Python-Dict. Neue Songs werden immer mit `err = 0` (nicht gesetzt) importiert. `insert()` und `update()` verwenden jetzt `dataclasses.asdict()` statt manueller Dicts — neue Felder im Song-Modell werden künftig automatisch berücksichtigt.
- **Crash beim Songimport behoben** (`TypeError: '>' not supported between instances of 'str' and 'int'`): `quality`-Werte die als Text oder Kommazahl in der DB lagen (z.B. aus älteren Migrationen) konnten die App beim Start komplett blockieren. `_row_to_song` konvertiert `quality` jetzt robust zu `int`; eine automatische DB-Migration bereinigt bestehende Altdaten beim ersten Start der neuen Version.

### Neues Feature: Evening Planner (Abendplanung)
- **Neuer Dock „Abendplanung"** parallel zum bestehenden Planner (Ansicht-Menü)
- **Emotionaler Spannungsbogen**: Bezier-Kurve mit Catmull-Rom-Interpolation als visuelles Ziel
- **Sägezahn-Blöcke**: CurveEngine segmentiert N Tipps automatisch in Blöcke (konfigurierbares Min/Max, Standard 3–5 Tipps), jeder Block mit ERR-Muster 3→4→2→1
- **ERR-Balken**: Patter (satte Farbe) und Singer (helle Farbe) als separate Balken pro Tipp; Höhe = emotionale Intensität
- **Drag-Handles**: ERR-Ziele per Maus verschieben; Griff-Abstand konfigurierbar (pro Tipp / 30 / 45 / 60 / 90 min)
- **Pausen-Unterstützung**: Pausen als graue Blöcke im Zeitstrahl, proportional zur Dauer dargestellt; harte Block-Grenzen
- **Songvorschläge**: SongScorer bewertet nach `quality × days_since_last_played × err_match`; bester Vorschlag automatisch grau vorbelegt
- **Ausgleichsregel**: Singer-ERR komplementär zu Patter-ERR (Summe ≈ 5)
- **4 Strategien**: Pattern+Singing abwechselnd, Singings nur Anfang/Ende, Nur Pattern, Nur Singings
- **Detail-Liste (PlannerTable)**: Tabellarische Ansicht aller Tipps mit Zeit, Songtitel, Label, ERR; Pausen per Drag & Drop verschiebbar
- **Zoom & Pan**: Zoom-in/out/fit-Buttons, QScrollArea für horizontales Panning
- **Lokation-Integration**: Automatische Aktualisierung der Vorschläge bei Lokationswechsel
- `song_db.py`: Neue Methode `get_planner_candidates()` für ERR-gefiltertes Kandidaten-Query
- **Kandidaten-Dialog**: Doppelklick auf einen Tipp-Slot öffnet einen Dialog mit allen passenden Kandidaten (Score, ERR, Label, Dateiname); beim Pattern-Slot optionale Bonus-Spalten für Genre-Match und Label-Match; Doppelklick oder OK bestätigt den Song für diesen Slot
- **Genre-Filter**: Checkbox + Button schränkt Song-Kandidaten auf ausgewählte Genres ein (gilt für Auto-Fill und Kandidaten-Dialog); Button zeigt kompakte Zusammenfassung der gewählten Genres
- **Planungsregeln-Dialog**: Konfigurierbare Regeln für die Vorschlagsberechnung
  - **Balance**: Patter-ERR komplementär zu Singing-ERR (Summe ≈ 5)
  - **Same-Genre-Boost** / **Same-Label-Boost**: multiplikativer Score-Bonus (Faktor konfigurierbar) wenn Patter und Singer aus gleichem Genre / Label
  - **First-Tip-Soft**: Erster Tipp bevorzugt Baseline/Beruhigung
  - **Last-Tip-Strong**: Letzter Tipp bevorzugt Höhepunkt oder Vorbereitung
- **Export-Button** (grüner Haken): Überträgt alle bestätigten Slots als neue Playlist (nur bestätigte, keine grauen Vorschläge)
- **Zwei Fill-Algorithmen**: `_fill_optimal` (globale Optimierung, minimiert Wiederholungen) und `_fill_greedy` (schneller, greedy je Slot)

---

## 0.72 — Potential: Ohne MP3 / Ohne Qualität, Crash-Handler Qt-Erweiterung (2026-05-07)

### Potential-Widget: Zwei neue Datenqualitäts-Checks (BL-027)
- **Ohne MP3**: Zeigt Songs, deren MP3-Datei in keinem konfigurierten Musikordner gefunden wird
  - Lazy Load: Dateicheck startet erst beim Klick auf den Button, nicht beim App-Start
  - Fortschritts-Dialog während der Prüfung ("Prüfe MP3-Dateien... x/n")
  - Läuft im Hintergrund-Thread (QThread), UI bleibt bedienbar, abbrechbar
  - Doppelklick navigiert zum Song in der Songliste; Ignorieren-Funktion vorhanden
- **Ohne Qualität**: Zeigt Songs mit `quality = 0` (Standardwert = noch nie bewertet)
  - Doppelklick navigiert zum Song; Ignorieren-Funktion vorhanden

### Crash-Handler: Qt-Message-Handler (BL-103)
- `qInstallMessageHandler` registriert: Qt-eigene Critical- und Fatal-Meldungen werden jetzt abgefangen
- Bei `QtCriticalMsg` und `QtFatalMsg`: sofortiges Schreiben eines Crash-Logfiles (inkl. Ring-Buffer)
- Schützt vor einer Klasse von Qt-internen Fehlern, die `sys.excepthook` nicht erreichen

---

## 0.71 — ERR-Feld, Planner-Suche, Auto-Fill, Button-Wrap (2026-05-07)

### ERR-Feld: Emotional Response Rate (BL-111)
- Neues Feld `err` in der Songdatenbank (INTEGER, 0–4): bewertet die emotionale Wirkung eines Songs im Tanzabend
- Werte: 0 = nicht bewertet, 1 = Höhepunkt, 2 = Vorbereitung, 3 = Baseline, 4 = Beruhigung
- ComboBox im Song-Daten-Widget; gespeichert wird nur die Zahl, keine Texte
- DB-Migration: neues Feld wird bestehenden Datenbanken automatisch hinzugefügt

### Auto-Fill im Planner (BL-112)
- Neuer Zauberstab-Button (3. Position in der Mittelleiste) füllt die Playlist automatisch
- Dialog: Anzahl Tipps wählbar + eine von 4 Strategien:
  1. **Pattern + Singing abwechselnd** — je ein Pattern und ein Singing pro Tipp
  2. **Singings nur am Anfang und Ende** — erstes und letztes Tipp-Paar je P+S, dazwischen nur Pattern
  3. **Nur Pattern** — ausschließlich Pattern-Songs
  4. **Nur Singings** — ausschließlich Singing-Songs
- Dual-Typ-Songs (Pattern + Singing) erhalten korrekt den jeweils gewählten Modus
- Gesamtdauer der Playlist berücksichtigt bei Loop=∞ die voreingestellte Pattern-Dauer des Programms/Clubs

### Planner-Suche (BL-106)
- Suchfeld oben im Pool (linke Spalte des Planners): filtert gleichzeitig nach Titel, Label und Dateiname
- Mit X-Button zum Leeren; Suche wirkt zusammen mit den übrigen Filtern (Genre, Typ usw.)

### Button-Leiste mit Zeilenumbruch
- Neue Hilfsklasse `_WrapButtonBar`: Buttons reihen sich nebeneinander, umbrechen aber bei zu schmalen Dock-Fenstern automatisch in eine zweite Zeile
- Songliste und Playlist nutzen jetzt diese Leiste — keine abgeschnittenen Beschriftungen mehr
- Alle Buttons einer Zeile werden auf einheitliche Höhe gebracht (Zeilen-Maximum)
- Button-Texte kompakter: „→ Notiz" → „+Notiz", „→ Playlist" → „+Playlist"

### Sonstiges
- Standard-Tanzprogramm beim Start: Button zeigt „MS" (Mainstream) statt „—"

---

## 0.70 — Potential-Widget: Bulk-Aktionen; UI-Bugfixes (2026-05-05)

### Potential-Widget: Bulk-Aktionen (Erweiterung BL-027)
- **Auto-Loop für alle**: Neuer Button im "Ohne Loop"-Check — setzt automatisch einen Loop für alle betroffenen Pattern per Loop-Finder. Bei mehr als 5 Songs wird vorab eine Zeitschätzung anhand von 5 Stichproben gemessen und dem Nutzer angezeigt, bevor er bestätigt.
- **Beat-Snap für alle**: Neuer Button im "Ohne BeatSnap"-Check — snappt Loop-In und Loop-Out aller betroffenen Songs auf den nächstgelegenen Beat. Gleiches Timing-Prinzip: bei > 5 Songs Vorab-Schätzung, sonst direkt loslegen.
- **Leere Lokationen löschen**: Neuer Button im "Leere Lokationen"-Check — entfernt alle Lokationen ohne Abspielhistorie nach Bestätigung.
- Alle Bulk-Operationen laufen im Hintergrundthread (kein UI-Freeze), mit abbrechbarem Fortschrittsdialog ("Abbrechen"-Button).
- SQLite-Thread-Safety: Worker öffnen eine eigene DB-Verbindung über `db_path`, statt die Verbindung des Main-Threads zu teilen.

### Bugfixes
- **Loop Finder Widget**: Segmentleiste (7 Singing-Call-Abschnitte) wurde nach dem Player-Redesign unten abgeschnitten — Höhe von 14 px auf 28 px korrigiert.
- **Loop-Widget Buttons**: Unterlängen (p, g) in zweizeiligen Buttons ("Loop\nFinder", "Beat\nSnap" etc.) wurden abgeschnitten — QPushButton-Padding in allen Themes von 10 px auf 5 px vertikal reduziert.

---

## 0.69 — Rules: BPM-Bedingungen + Auto-Detect-Aktion; zentrale Pfadauflösung (2026-05-03)

### Rules — neue Bedingungen
- **BPM Set**: prüft ob der aktuelle Song einen BPM-Wert gesetzt hat (`base_bpm > 0`)
- **BPM Not Set**: Gegenstück — Song hat noch keinen BPM-Wert

### Rules — neue Aktion
- **Auto-Detect BPM** (Gruppe "Audio"): Startet die automatische BPM-Erkennung für den aktuell geladenen Song im Hintergrund — identisch zum "Auto BPM"-Button im Song-Daten-Widget, aber als Regel-Aktion auslösbar (z. B. via Trigger "Song Changed" mit Bedingung "BPM Not Set")
- Ergebnis wird in DB gespeichert und das BPM-Feld im Song-Daten-Widget sofort aktualisiert
- Läuft idempotent: zweiter Aufruf während laufender Erkennung wird ignoriert
- "BPM wird ermittelt …"-Overlay während der Erkennung (analog zum Auto-Loop-Overlay)

### Zentrale Pfadauflösung (BL-104)
- `PathManager.find_lyric_file(filename)` neu — sucht Lyrik-Datei im konfigurierten Lyrics-Ordner (Pendant zu `find_song_file()`)
- `SongDataWidget._on_auto_bpm()`: nutzt jetzt `find_song_file()` statt direktem `music_dir`-Join — findet Songs in allen 4 Musik-Slots
- `LyricsWidget._load_lyrics_file()`: nutzt jetzt `find_lyric_file()` statt direktem `lyrics_dir`-Join

### Bugfixes
- **TIC-0016**: Auto-BPM-Button reagierte nicht auf Klick — Ursache war `music_dir`-Join der nur Slot 1 durchsuchte; behoben durch `find_song_file()` (Teil der zentralen Pfadauflösung)
- **TIC-0023**: Funktionen ignorierten alternative Musik-/Lyrik-Pfade (Slots 2–4) — behoben durch zentrale Pfadauflösung (BL-104)
- **TIC-0007 / TIC-0022**: Abstürze ohne Details nicht mehr analysierbar — strukturell behoben durch Crash-Handler (BL-103): automatisches Logfile bei jedem unbehandelten Absturz

---

## 0.68 — Player-Widget Redesign (2026-05-02)

### Player-Widget: Neues Layout

- **Info-Streifen** (oberste Zeile): 4 gleich breite Spalten mit Beschriftung oben und Wert darunter — Dauer / BPM / Loops / Programm
- **BPM-Anzeige**: zeigt nur noch den Zahlenwert, „BPM" steht als Spaltentitel darüber
- **Loop-Count**: zeigt nur noch „3/8" bzw. „∞", Spaltentitel lautet „Loops"
- **Songtitel + Status** in einer gemeinsamen Zeile: Titel linksbündig, Status rechtsbündig
- **Songtitel dynamisch skalierend**: nutzt allen freien vertikalen Platz der Player-Karte, Schrift wächst von der Theme-Basisgröße bis +13 px — mit Zeilenumbruch bei Platzmangel
- **Status-Text** bleibt dauerhaft in kleiner fester Schriftgröße (font_size − 2), skaliert nicht mit dem Titel

### Sektionsleiste neu

- 7 QPushButton-Segmente statt custom paintEvent
- Gestalt-basierte Farbgebung: O/M/C (strukturelle Marker) in Rot, 1/3 in hellem Grau, 2/4 in dunklem Grau — Muster des Singing Calls wird sofort visuell erkennbar
- Farben über neue Skin-Keys `sec_o`, `sec_1`, `sec_2`, `sec_m`, `sec_3`, `sec_4`, `sec_c` — in allen 4 Skins hinterlegt (default, light, win11, elegant)

### Transport-Buttons: SVG-Icons

- Play, Pause, Stop und Fade-Out erhalten SVG-Vektorsymbole
- Farbe der Icons folgt dynamisch der Theme-Einstellung `button_text` — keine separaten SVG-Dateien pro Theme nötig
- Fade-Out-Pfeil zeigt nach rechts (→)
- Play-Button: volle Breite, Mindesthöhe 44 px, Akzentfarbe aus dem Theme

### Theme-relative Schriftgrößen im Info-Streifen

- Alle Schriftgrößen relativ zur `font_size`-Einstellung des Skins
- Beschriftungs-Labels: `font_size − 2` px
- Wert-Labels (BPM, Loops): `font_size + 1` px
- Dauer-Timer: `font_size + 2` px, monospace fett

### Platzsparende Anpassungen (Laptop-Optimierung)

- **Loop-Widget**: Button-Höhen von 52 px auf 38 px reduziert, NEU-Button von 38 auf 32 px, Spacing von 6 auf 4 px, `addStretch()` am unteren Rand entfernt, Bottom-Margin auf 4 px gekürzt — spart ~100–120 px Gesamthöhe
- **Programm-Button** im Info-Streifen: Höhe auf max. 24 px begrenzt, internes Padding reduziert
- **Songtitel-Bereich**: maximale Höhe auf 52 px gedeckelt (verhindert übermäßigen Leerraum zwischen Titel und Spielzeit)
- **Mindesthöhe Player-Widget**: 380 px (zuvor 420 px)

### Weitere Verbesserungen

- Loop-Checkbox-Beschriftung: „Loop aktiv" → „Loop" (Übersetzungsschlüssel bleibt erhalten)
- Player-Design-Vorschau: neues Sandbox-Fenster im Ansicht-Menü zum Testen von Layout und Theme-Wechsel ohne echten Betrieb

---

## 0.67 — Crash-Handler, Media-Tasten, Bugfixes (2026-05-01)

### Neu: Crash-Handler (BL-103)
- Neues Modul `crash_handler.py`: fängt unbehandelte Python-Exceptions automatisch ab
- Bei jedem Absturz wird `crash_YYYYMMDD_HHMMSS.log` im App-Verzeichnis gespeichert
- Log enthält: Zeitstempel, Song, Lokation, vollständiger Stacktrace, die letzten 25 Benutzeraktionen (Ring-Buffer)
- Beim nächsten App-Start erscheint ein Hinweis-Dialog mit „Protokoll anzeigen"-Button (öffnet Texteditor)
- Geloggte Aktionen: Song aus Liste geladen, Song aus Playlist geladen, Play gestartet, Lokation gewechselt, Planner Confirm

### Media- und Fn-Tasten als Rule-Trigger
- Volume+, Volume−, Mute, Media Play/Pause, Media Stop, Media Next, Media Previous, Brightness+, Brightness− sind jetzt als Trigger in der Rule Engine verfügbar
- Abfang per App-weitem EventFilter (analog zu F13–F24) — funktioniert wenn das OS die Tasten nicht systemweit schluckt
- Neues Diagnoseskript `2_Test/key_monitor.py` (+ `.bat`): zeigt für jede gedrückte Taste Key-Code, Trigger-Name und ob Callers Caddy sie verarbeiten würde — hilfreich beim Einrichten von Stream Deck / Funk-Fernbedienungen

### Statistik-Dock: Kontextmenü (BL-102)
- Rechtsklick auf einen Song in den Listen TOP / FLOP / Nie gespielt öffnet ein Kontextmenü
- **„Zur Playlist hinzufügen"** → Song landet direkt in der aktuellen Playlist
- **„Zu Notizen hinzufügen"** → fügt einen `[load_song "Titel"]`-Shortcode als neue Notiz ein

### Bugfixes
- **TIC-0019** Planner: Loop-Daten wurden nach Rule-Ausführung nicht aktualisiert — Loop-Anzahl-Dialog liest Daten jetzt frisch aus der DB
- **TIC-0020** Tanzprogramme verwalten: Spaltenheader „Ziel-Dauer (min)" wurde abgeschnitten — Spalte passt sich jetzt automatisch an den Header-Text an
- **TIC-0021** Statistik-Dock: alternierende Zeilenfarben hatten zu wenig Kontrast — `alternate-background-color` jetzt für alle 4 Skins definiert
- Statistik-Dock → „Zu Notizen hinzufügen" crashte wenn das Notizen-Dock noch nie geöffnet war (`notes_widget` noch nicht lazy-initialisiert) — Fix: synchrone Init vor dem Zugriff (vom Crash-Handler in der eigenen Sitzung gefunden)

---

## 0.66 — Bugfixes (TIC-0015, TIC-0017, TIC-0018) (2026-04-30)

### Bugfixes
- **TIC-0015** Lyrics-Zoom-Stufe wird jetzt beim App-Start korrekt wiederhergestellt — Zoom-Wert und Auto-Size-Zustand werden in der INI gespeichert und beim nächsten Start sofort angewendet
- **TIC-0017** Loop-Count-Dialog im Planner findet Songs jetzt auch in Musikordnern Slot 2–4 — Funktion `show_loop_count_dialog` nutzt jetzt `find_song_file()` statt nur Slot 1
- **TIC-0018** Rule-Aktion „Load Layout": Dropdown zeigt jetzt alle gespeicherten Layouts aus dem `skins/`-Ordner — `layout_names_provider` angebunden, TODO-Stub ersetzt

---

## 0.65 — Statistik-Dock (BL-019) (2026-04-29)

### Neues Dock: Statistik
- Neues andockbares, lazy geladenes Fenster „Statistik" im Ansicht-Menü (tabbiert mit Reports)
- **Filter** (oben): Lokation (Alle oder einzelne), Typ (Beide / Pattern / Singing), Zeitraum (Alle Zeit / 5 Jahre / 1 Jahr / 3 Monate / 1 Monat)
- **Drei Spalten** (scrollbar, alle Songs ohne Limit):
  - **TOP** — alle gespielten Songs, meistgespielt zuerst, mit Abspielanzahl
  - **FLOP** — alle gespielten Songs, wenigstgespielt zuerst, mit Abspielanzahl
  - **Nie gespielt** — alle Songs ohne Play in den aktuellen Filtern, alphabetisch
- **Doppelklick** auf einen Song springt direkt zur Songliste
- **Histogramm** (volle Breite): Verteilung aller Songs nach Abspielanzahl
  - Bin 0 ist immer fest für „nie gespielt", danach 9 logarithmisch verteilte Bins
  - Farbgradient von Blau (kalt = selten) bis Orange-Rot (heiß = oft gespielt), unabhängig vom Skin
  - Tooltip auf jedem Balken zeigt Bin-Bereich, Anzahl Songs und bis zu 5 Beispiel-Titel
- Übersetzungen DE + EN vollständig vorhanden

---

## 0.64 — First-Steps-Paket, Tutorial-Überholung, Playlist-Verbesserungen (2026-04-28)

### Beispielprojekt für Neueinsteiger (first-steps/)
- **first-steps/-Ordner** wird in jeder Neuinstallation mitgeliefert
- Enthält „YRR 049 - Electro Blues.mp3" von Jon Hansell Nilsson (freundlicherweise zur Verfügung gestellt) und das passende Lyricsheet „YRR 049 - Electro Blues.htm"
- Das Lyricsheet thematisiert auf witzige Weise die Funktionen von Callers Caddy
- `build.py`: Schritt 3 kopiert `1_Source/first-steps/` automatisch in den App-Ordner

### Tutorial: New Songs Tour (komplett überarbeitet)
- **Umbenannt** von „Loop-Tour" zu „New Songs Tour"
- **Menüreihenfolge**: New Songs Tour jetzt direkt nach Player-Tour (Prio 97), Loop Finder direkt darunter (Prio 96), Beat Snap danach
- **Step 1** (Import-Button): Expliziter Handlungsaufruf mit Schritt-für-Schritt-Anleitung durch die drei Import-Dialoge — Songtyp „Beides", Kopieren, Einzeldateien aus first-steps/
- **Step 2** (Auto-Loop): Loop Finder als zweiter Schritt statt manuellem In/Out-Setzen — manuelle Buttons und Beat Snap aus dem Tutorial entfernt
- **Song-Daten-Tutorial** um Step 4 erweitert: „Lyricsheet verknüpfen" mit Hinweis auf first-steps-HTM

### Songliste: Song zur Playlist hinzufügen
- **→ Playlist-Button** unterhalb der Songliste (neben „Liste aktualisieren" und „→ Notiz")
- **Rechtsklick-Kontextmenü** der Songliste: neuer Eintrag „Zur Playlist hinzufügen"
- „→ Notiz"-Button von der Suchzeile nach unten in die Button-Leiste verschoben

### Playlist: Songs entfernen
- **✕-Button** neben den Pfeiltasten ▲ ▼ entfernt den markierten Song sofort
- **Rechtsklick-Kontextmenü**: „Aus Playlist entfernen" ganz oben (vor Separator)
- **Entf-Taste**: QShortcut mit `WidgetWithChildrenShortcut`-Kontext — funktioniert unabhängig davon, welches Kind-Widget Fokus hat

---

## 0.63 — LoopFinder Lazy Init, Mapping Export/Import, Sequenzen Export (2026-04-27)

### LoopFinder: Lazy Initialisierung
- `LoopFinderWidget` wird nicht mehr beim Start erstellt, sondern erst beim ersten Öffnen des Fensters
- Spart ~100ms Startzeit auf schwacher Hardware (Notebook: addDockWidget war 106ms)
- Waveform + Sprungbereiche werden beim Öffnen sofort angezeigt (kein manuelles „Analysieren" nötig für die Vorschau)
- Song-Info wird nachgereicht falls beim Öffnen bereits ein Song geladen ist
- `setFloating` und `restoreGeometry` des Dock-Fensters ebenfalls per `QTimer.singleShot` nach `show()` verschoben

### Mapping Export/Import (Sequenzen-Menü)
- **Mapping exportieren…**: Speichert alle `call_text_mappings` als JSON-Datei (`call_text`, `entity_id`, `mapped_by`)
- **Mapping importieren…**: Liest JSON, fügt neue Einträge ein (`INSERT OR IGNORE`), überspringt bereits vorhandene
- Rückmeldung: „X neue Mappings importiert, Y bereits vorhanden (übersprungen)"
- Bei neuen Einträgen wird automatisch Remapping angestoßen

### Sequenzen exportieren (JSON)
- Neuer Menüpunkt **Sequenzen exportieren (JSON)…** nach den drei Import-Punkten
- Exportiert alle Sequenzen im exakt gleichen Format wie der JSON-Import erwartet (`id`, `calls`, `level`, `seq_type`, `difficulty`)
- Exportierte Datei kann direkt wieder per „Sequenzen importieren (JSON)" eingelesen werden

### UI-Detail
- Pfeil-Buttons (◀ ▶) und Note-Button im Sequence-Detail-Fenster haben jetzt einheitliche Höhe (40px) — bessere Treffsicherheit am Laptop

### Projektdokumentation
- `CLAUDE.md`: `setFloating(True)` auf Windows kostet ~90ms (einmalig pro Floating-Dock-Kontext) — wandert nur zwischen Buckets wenn man es defer't, spart keine Gesamtzeit

## 0.62 — CallMatcher & Sequenz-UI-Verbesserungen (2026-04-27)

### Call-Mapping: Intelligenter Auto-Vorschlag (CallMatcher)
- Drei-Stufen-Matching vollständig in `sequence_mapper.py` ausgelagert — keine API-Kosten, läuft lokal in Millisekunden
- **Stufe 1**: Exakter Vergleich nach Normalisierung (Präfixe/Suffixe entfernt) → Score 1.0
- **Stufe 2**: Bidirektionaler Token-Overlap (geometrisches Mittel aus Precision × Recall) → Score bis 0.92
- **Stufe 3**: `difflib.SequenceMatcher` als Fallback (nur wenn Token-Score ≥ 0.30) → Score bis 0.85
- **Farbcodierung** der Call-Text-Zeilen im Mapping-Dialog:
  - 🟢 Grün (Score ≥ 0.85): sicherer Vorschlag
  - 🟡 Gelb (Score 0.50–0.84): unsicherer Vorschlag, manuelle Prüfung empfohlen
  - 🔴 Rot (Score < 0.50): kein brauchbarer Vorschlag
  - Grün auch für bereits gemappte Einträge
- Altes `_normalize_call_text`/`_norm_index`-System in `main.py` durch `CallMatcher`-Import ersetzt

### Sequenz-Tabelle: UX-Verbesserungen
- Level-, Type- und Difficulty-Spalten **ausgeblendet** (`setColumnHidden`) — Sequenz füllt die volle Tabellenbreite
- Type-Filter-Dropdown startet mit **„Singer (Corner progression)"** als Standardwert (häufigster Typ)
- Bugfix: `ResizeToContents` bei Type-Spalte ließ die Sequenz-Spalte schrumpfen wenn viele Zeilen denselben langen Typ hatten

### Performance-Logging
- Neue Messpunkte: `SequencesWidget` und `SequenceViewWidget` getrennt gemessen
- Neuer Messpunkt: `_build_menu` (war bisher in `song_list.refresh` versteckt)
- Neuer Messpunkt: `_init_sequences` intern aufgeteilt (`load_sequences` + `sequence_view prefill`)
- Bugfix: LoopFinder-Split zeigte fälschlicherweise Notizen-Zeit mit an (`_td10` → `_td10b`)

### Sonstiges
- `CLAUDE.md` um Debugging-Zusammenarbeits-Regel erweitert: Screenshot/Rückfrage vor langer Code-Analyse

## 0.61 — Ceder-Sequenzen Import & Call-Mapping (2026-04-26)

### Ceder-Choreo-Scraping (externes Projekt)
- Neues Scraper-Projekt `Ceder-Choreo-Scraping`: lädt alle Singing-Call-Sequenzen von ceder.net herunter
- Paginierung über `Page=N`-Parameter (200 Einträge/Seite), Resume-Support via `_done.txt`
- Alle Level (SSD bis C4) × alle Special-Filter werden abgedeckt
- Ausgabe als JSON pro Level + kombinierte CSV
- Import-Skript `import_to_db.py` fügt Sequenzen direkt in die Callers-Caddy-Testdatenbank ein

### Sequenz-Tabelle erweitert
- Neue Spalten `type` und `difficulty` in der `sequences`-Tabelle (Migration idempotent)
- `insert_sequence()` nimmt jetzt `seq_type` und `difficulty` entgegen
- Neue DB-Methoden: `get_sequence_type_values()`, `get_sequence_difficulty_values()`

### Sequenz-UI erweitert
- Tabelle: von 3 auf 4 Spalten — **Sequenz** (Stretch, sofort sichtbar), Level, Typ, Schwierigkeit
- Zweite Filter-Zeile mit **Typ**- und **Schwierigkeit**-Dropdown
- Alle Filter (Contains, Limit, Typ, Difficulty) greifen konsistent in Tabelle, Navigation und Shortcodes

### Neue Import-Formate im Menü „Sequenzen"
- **JSON-Import** (`import_from_json`): lädt eine oder mehrere Ceder-JSON-Dateien, hängt Sequenzen an
- **CSDS-Import** (`import_from_csds`): lädt Vic Ceder's `.in`/`.csds`-Exportformat; parst `#EASY#`/`#REC=`/`#SEQTYPE=`-Metadaten und bereinigt `<C ALT="...">text</C>`-Markup automatisch
- Deduplizierung über Ceder-Record-ID beim Mehrfach-Import
- Letztes Import-Verzeichnis wird in den Settings gemerkt

### Call-Mapping-Dialog
- Neuer Menüpunkt **„Call-Mapping…"** im Sequenzen-Menü
- Tabelle aller ungemappten Call-Texte, sortiert nach **Häufigkeit** (häufigste zuerst — ein Eintrag kann viele Sequenzen auf einmal heilen)
- Rechte Spalte: editierbare ComboBox mit Contains-Autocomplete — öffnet sich erst beim Klick (Delegate, kein Voraus-Rendering)
- **Lazy Loading**: nur 20 Zeilen initial, weitere beim Scrollen ans Ende
- Gelbe Markierung für Texte ohne Auto-Vorschlag
- **Auto-Vorschlag** durch normalisierten Textvergleich: Präfixe (Heads/Sides/Centers/Boys/Girls…) und Suffixe (Zahlen, Brüche, Klammern) werden abgeschnitten
- Sonderoption **„→ An Komma aufteilen"**: Calls wie `"Flutter Wheel, Sweep 1/4"` werden direkt in den Sequenzen gesplittet — nachfolgende Felder rücken automatisch nach rechts
- Sondereintrag **„Filler Words"** (TO=0.001) für Füllphrosen die kein echtes Level haben — verhindert NULL bei der Levelberechnung ohne das Ergebnis zu verfälschen
- Nach dem Speichern wird automatisch `recompute_sequence_max_to()` angestoßen

## 0.60 — F13–F24 Tasten-Trigger (2026-04-25)

### Erweiterte F-Tasten-Unterstützung
- **F13–F24** sind jetzt vollwertige Rule-Trigger — erscheinen im Trigger-Dropdown des Rule-Editors
- Capture-Dialog erkennt F13–F24 beim Drücken korrekt und zeigt sie als „F13" etc. an
- Abfang über den App-weiten EventFilter (zuverlässiger als QKeySequence-Strings, die Qt für F13+ nicht parst)
- Nützlich für USB-Fernbedienungen und Makro-Pads, die erweiterte F-Tasten senden

## 0.59 — Shortcodes in Notizen & Rule-Editor Gruppen (2026-04-24)

### Shortcodes in Notizen (BL-093)
- **Shortcode-Syntax** in Notizen: `[load_song "Titel"]` lädt ein Lied; `[sequence_view id=42]` / `[sequence_view contains="Swing Thru" limit="MS"]` öffnet die Sequenzansicht mit optionalem Filter
- Shortcodes werden ausgelöst beim **manuellen Abhaken** einer Notiz sowie via `notes_tick_top`-Regel
- Neues Modul `shortcode_parser.py` mit robustem Regex-Parser (positionale und benannte Parameter, Integer-Erkennung)
- **→ Notiz Button** in Songliste, Playlist, Sequenz-Übersicht und Sequenz-Detail: fügt den aktuellen Eintrag als Shortcode in die Notizliste ein
- **→ Filter Button** in Sequenz-Übersicht: fügt die aktiven Contains/Limit-Filter als `[sequence_view]`-Shortcode ein
- **Rechtsklick-Menü** (Context-Menu) in Songliste, Playlist und Sequenz-Tabelle: „Zu Notizen hinzufügen"
- Warnung wenn keine Lokation gewählt und Notiz eingefügt werden soll
- Songtitel wird ohne Anzeige-Suffixe (Typ, Label, Qualität) in den Shortcode übernommen

### Rule-Editor: Aktionen gruppiert
- Die 43 Regelaktionen sind jetzt in **10 Kategorien** gegliedert: Transport · Audio · Layout & Docks · Lyrics & Scroll · Sequence View · Notes · Workflow · Photo · Genre · Info & Warnings
- Nicht-auswählbare Gruppenheader im Aktions-Dropdown für bessere Übersicht
- Reihenfolge der Aktionen innerhalb der Gruppen logisch sortiert
- Bestehende Rules bleiben vollständig kompatibel — nur die Anzeige ändert sich

## 0.58 — Sequence Detail als echtes Dock (2026-04-24)

### Sequence Detail als QDockWidget (BL-092)
- **`dock_sequence_view`** ist jetzt ein vollwertiges Dock-Widget — kein temporärer Popup-Dialog mehr
- Kann wie alle anderen Docks behandelt werden: `dock_open`, `dock_close`, `dock_fullsize`, `dock_focus`, `dual_view`, Layout-Save/Restore
- Klick auf eine Zeile in der Sequenzübersicht aktualisiert das Detail-Dock und bringt es in den Vordergrund
- Im Regel-Editor unter dem Kurzname **`sequence_view`** verfügbar (z.B. `dual_view` mit `dock_left=sequences` + `dock_right=sequence_view`)
- `sequenceview_maximize` öffnet das Dock als schwebendes 90 %-Fenster — kein Konflikt mehr mit dem Dual-View
- Navigation (◀/▶, Tastatur ← →) bleibt erhalten; `sequenceview_prev`/`sequenceview_next`-Regelaktionen steuern das Dock direkt
- Alle Regel-Aktionsnamen durchgehend Englisch: `sequenceview_*` (statt `sequenzview_*`)
- **Filter-Sync**: Ändert der Nutzer den Contains- oder Limit-Filter in der Sequenzübersicht, springt das Detail-Dock automatisch auf die erste Sequenz der neuen Ergebnisliste (nur wenn das Dock sichtbar ist)
- **Startup-Vorbefüllung**: Beim App-Start wird das Detail-Dock sofort mit Sequenz 1 gefüllt — kein leeres Fenster beim ersten Öffnen

## 0.57 — SequenzView Navigation & Vollbild (2026-04-24)

### SequenzView — Navigation ohne Dialog zu schließen (BL-089)
- **‹ / › Buttons** in der Sequenzansicht: blättert durch die aktuell gefilterte Liste
- **Positions-Anzeige** „3 / 12" zwischen den Buttons — Caller sieht sofort wo er in der Liste steht
- **Tastatur-Support**: ← / → Pfeiltasten navigieren ebenfalls (ideal für freihandigen Betrieb)
- Buttons werden am Anfang bzw. Ende der Liste automatisch deaktiviert
- Navigation bezieht sich immer auf die vollständige gefilterte Liste (nicht nur geladene Zeilen)
- Neue DB-Methode `get_filtered_sequence_ids()` liefert alle passenden IDs für die Navigation

### SequenzView — Auto-Zoom & freie Fenstergröße (BL-090)
- **Frei vergrößerbar**: Dock kann beliebig groß gezogen werden
- **Mitwachsende Schrift**: Schriftgröße der Calls passt sich automatisch an die verfügbare Fensterhöhe an — Sequenz füllt das Fenster optimal aus
- **◀ / ▶ Buttons** in einheitlicher Größe (font-size 16px)
- **Position-Label** „X / N" verwendet die Schriftfarbe des aktiven Themes

### SequenzView — Rule-Aktionen (BL-091)
- **`sequenzview_open`**: zeigt das Detail-Dock mit der aktuellen Tabellenauswahl
- **`sequenzview_close`**: versteckt das Detail-Dock
- **`sequenzview_prev` / `sequenzview_next`**: blättert per Rule/Tastenkürzel zur vorherigen/nächsten Sequenz
- **`sequenzview_focus`**: bringt das Detail-Dock in den Vordergrund
- **`sequenzview_maximize`**: macht das Detail-Dock als schwebendes 90%-Fenster
- **Auto-Zoom bidirektional**: Schriftgröße wird auch nach oben korrigiert wenn der erste Schätzwert zu konservativ war

---

## 0.56 — Dual-View & Songlisten-Schnellnavigation (2026-04-23)

### Dual-View: zwei Widgets nebeneinander (BL-077)
- **Neue Regel-Aktion `dual_view`**: Öffnet zwei beliebige Docks als schwebende Fenster nebeneinander — zusammen 90 % Bildschirmbreite und -höhe, zentriert mit 4 px Abstand
- **Flexibles Breitenverhältnis**: Auswahl aus `50:50`, `33:67` oder `67:33` direkt im Regel-Editor
- **Neue Aktion `dual_view_close`**: Schließt beide Dual-View-Fenster und dockt sie zurück
- **Neue Aktion `dual_view_toggle`**: Ein Tastendruck öffnet den Dual-View (Layout wird automatisch gesichert), ein zweiter Tastendruck stellt das ursprüngliche Layout exakt wieder her — ideal als Keyboard-Shortcut
- Alle drei Aktionen erscheinen mit englischen Display-Namen im Regel-Editor; Parameter `dock_left`, `dock_right` und `split` als gewohnte Dropdowns
- Häufigste Kombination: Lyrics links + Sequenzen rechts, 50:50

---

## 0.55 — Planner-Loop-Dialog & Doppelklick-Fix (2026-04-22)

### Planner: Loop-Dialog mit Ziel-Patternlänge vorbelegt (BL-085)
- **Loop-Count-Dialog** im Planner und im Playlist-Widget übernimmt jetzt automatisch die Ziel-Patternlänge des aktiven Tanzprogramms als Voreinstellung (statt fest 7 min)
- Ist kein Tanzprogramm gesetzt, bleibt der Standardwert 7 min

### Playlist-Widget: Doppelklick auf Loops-Spalte (BL-085)
- **Doppelklick auf die Loops-Spalte** im Playlist-Dock öffnet jetzt denselben Loop-Count-Dialog wie im Planner — Anzahl und Zeitvorgabe direkt editierbar
- Zuverlässige Auslösung über `mouseDoubleClickEvent`-Override in `_PlaylistTable`, der einen bekannten Qt-6-Timing-Konflikt zwischen DragDrop-Modus und `cellDoubleClicked`-Signal umgeht

---

## 0.54 — Tanzprogramm-System & Lokations-Erweiterungen (2026-04-22)

### Tanzprogramm-Anzeige im Player (BL-083)
- **Neuer Button `btn_program`** in der Player-Info-Zeile (neben BPM): zeigt das aktuell eingestellte Tanzprogramm-Kürzel an (z.B. `MS`, `A1 Class`)
- **Schnellauswahl-Dialog**: Klick auf den Button öffnet ein Grid aller konfigurierten Programme als Schaltflächen — Button-Breite passt sich automatisch an den längsten Text an
- **14 Default-Programme**: MS, MS Class, PL, PL Class, A1, A1 Class, A2, A2 Class, C1, C1 Class, C2, C2 Class, C3A, C3A Class — je mit konfigurierbarer Ziel-Patternlänge (Standard 7 min)
- **Verwaltungsdialog** über Menü *Datenbank → Tanzprogramme verwalten*: Programme anlegen, umbenennen, Reihenfolge und Ziel-Patternlänge anpassen, löschen
- Neue DB-Tabelle `dance_programs`; bestehende Installationen erhalten die Default-Programme automatisch beim nächsten Start (INSERT OR IGNORE)

### Lokations-Einstellungen: Tanzprogramm & temporäres Tempo (BL-084 + BL-086)
- **Neuer „Einstellungen"-Button** im Lokations-Dialog: öffnet einen Einstellungs-Dialog für die gewählte Lokation
- **Tanzprogramm-Zuweisung pro Lokation**: Beim Wählen einer Lokation wird das gespeicherte Tanzprogramm automatisch im Player eingestellt
- **Temporäres Tempo pro Lokation**: SpinBox (50–150 %, Standard 100 % = kein Einfluss). Bei Lokationswechsel wird der gespeicherte Wert automatisch in das Feld „Temporäres Tempo" übernommen — praktisch für Classes und Anfänger-Gruppen mit fester Tempobremse
- Neue DB-Spalten `dance_program_id` und `temp_tempo` in der `locations`-Tabelle (Migration für Bestandsinstallationen)

---



## 0.53 — Class Designer: Prüfen & Optimieren, Notizen-Feinschliff (2026-04-20)

### Class Designer — Prüfen & Optimieren (neu)
- **„Prüfen"-Button** in Spalte 3: löst explizit Überlast/Unterlast-Färbung der Tagesheader und Abstandregel-Check aus
- **Orange Markierung** für Teaches, die Prereq-Delay-Regeln verletzen (vorher rot) — klar abgegrenzt vom roten Überlast-Tagesheader
- **„Optimieren"-Button**: iterative Local Search (Best-Improvement Hill Climbing) auf dem bestehenden Plan — ersetzt keine Generator-Neubelegung, sondern räumt Verstöße und Lastungleichheiten nachträglich auf
  - Zielfunktion: `Verstöße × 10 000 + Σ(Last − Ø)²` — Constraint-Verstöße dominieren hart, Lastvarianz wird darunter feinabgestimmt
  - Respektiert manuelle Drag-Änderungen in Spalte 3
  - Harte Constraints werden pro Move geprüft: Prereq-Delay, Nachfolger-Delay, Repeat nach Teach, keine doppelten Repeats am selben Tag
  - Konvergiert deterministisch (max. 200 Iterationen); typisch deutlich schneller
- Algorithmus-Einordnung (RCPSP / Sprint-Rebalancing) dokumentiert in `docs/16_class_designer.md`

### Class Designer — UX-Verbesserungen
- **Effort-Felder als Button-Reihe** statt ComboBox: alle Fibonacci-Werte (1, 2, 3, 5, 8, 13 bzw. 0–13 bei Info) als Toggle-Buttons direkt sichtbar — ein Klick statt Dropdown öffnen
- **Neue Einträge hinter markiertem Element**: Bei „+ Call" und „+ Info" wird das neue Element hinter dem aktuell selektierten eingefügt (statt ans Ende) und automatisch markiert — kettenweises Einfügen fließt natürlich
- **Effort-Filter in Spalte 2**: Toggle-Button-Reihe `0 | 1 | 2 | 3 | 5 | 8 | 13` zwischen Toolbar und Planungstabelle. Standardmäßig alle aktiv — ermöglicht auf einen Blick zu prüfen, ob Calls mit gleichem Aufwand auch ähnlich aufwendig sind
- `n_evenings` wird im Col3-Widget gespeichert, damit Optimieren auch nach manuellen Änderungen mit dem richtigen Rahmen arbeitet

### Notizen-Widget — Darstellung & Bearbeitung
- **Oberste offene Notiz 4× vergrößert** (BL-079): Die aktuell wichtigste Notiz wird prominent als große, fette Überschrift angezeigt — Vergrößerungsfaktor in INI konfigurierbar (`notes/first_note_factor`, Default 4.0)
- **Kompakter Zeilenabstand** bei langem Mehrzeilen-Text: Das Label rendert Wort-Umbrüche jetzt selbst (statt über Qt's Standard-Lineheight) und nutzt ca. 90 % der Schriftgröße als Zeilenvorschub — spart bei der großen ersten Zeile erheblich Platz, ohne Descender abzuschneiden
- **Wortumbruch** für sehr lange Notizen: Text umbricht sauber innerhalb der Zeile, Zeilenhöhe wächst mit
- **Doppelklick zum Bearbeiten**: Linker Doppelklick auf eine Notizzeile öffnet einen Edit-Dialog mit mehrzeiligem Textfeld — Theme-konform gestylt, Sprache folgt UI-Einstellung (DE/EN), `Ctrl+Enter` bestätigt
- **Zoom-Buttons +/−** weiterhin aktiv — die neue Rendering-Logik respektiert die Zoom-Stufe
- Neue DB-Methode `update_note_text(note_id, text)` in `song_db`

### Regel-System
- **Neue Aktion `notes_tick_top`** (BL-080): Hakt die oberste offene Notiz der aktiven Lokation ab — nützlich z.B. für Keyboard-Shortcuts oder Timer-Events. Bei leerer Liste stumm ignoriert (keine Fehlermeldung)

### Interne Aufräumarbeiten
- Neues Helper-Widget `_ValueButtonRow` für exklusive Wert-Auswahl (wiederverwendbar für weitere diskrete Auswahlen)
- Helper `_insert_after_selected()` in Col2 — zentralisiert Einfüge-Logik
- Neue QLabel-Subklasse `_TightLabel` mit eigenem `paintEvent` + manuellem Wortumbruch für präzise Zeilenabstandskontrolle
- Neuer modaler Dialog `_NoteEditDialog`

---

## 0.52 — Class Designer (Prototyp) & Tracking-Fix (2026-04-17)

### Class Designer — Erster Prototyp
- **Hinweis**: Dies ist der **erste Prototyp** des Class Designers — weiterer Feinschliff ist definitiv nötig
- **Gleichmäßigere Punkteverteilung pro Tag**: Umstellung auf Greedy-Bin-Filling. Jeder Tag wird bis zum Zielbudget (Gesamt-Punkte / Anzahl Tage) aufgefüllt, bevor der nächste Tag befüllt wird
- **Repeat-Constraints respektiert**: Wiederholungen derselben Figur halten weiterhin mind. 1 Tag Abstand; Prereq-Delays bleiben erhalten
- **Unterfüllte Tage vermieden**: Wenn ein Repeat wegen `earliest`-Constraint vorspringt, bleibt der Tag-Zeiger zurück — nachfolgende Teaches füllen den freigebliebenen Tag auf, statt ihn leer zu lassen

### Loop Finder — Zeit-Anzeige unter Suchbereichen
- **Spielzeiten unter den Prozent-Feldern**: Unter jedem der 4 Prozent-Felder (Loop-In Start/Ende, Loop-Out Start/Ende) wird jetzt die konkrete Spielzeit des geladenen Songs im Format `m:ss` angezeigt (z.B. `0:53`). So sieht der Caller auf einen Blick, wo im Song der Suchbereich liegt
- Anzeige aktualisiert sich live bei Eingabe der Prozentwerte und beim Ziehen der Waveform-Handles
- Einheitliche Zeilenhöhe: Preset-ComboBox und Load/Save-Buttons nutzen jetzt dieselbe Höhe wie die Prozent-SpinBoxen

### Bugfix — Abspielhistorie
- **Tracking nur bei echtem Play**: Bisher wurde die "Zuletzt gespielt"-Spalte bereits beim reinen Selektieren/Laden einer Datei aktualisiert. Jetzt wird der Zeitstempel ausschließlich beim tatsächlichen Drücken von Play gesetzt. Der Song muss nicht vollständig durchlaufen
- Der DB-Eintrag in `play_history` war bereits korrekt, nur die UI-Spalte lief voraus

---

## 0.51 — Notizen-Widget Verbesserungen (2026-04-15)

### Notizen-Widget — Überarbeitung & neue Features
- **Export-Ordner `notes/`**: Neuer Unterordner wird automatisch angelegt; ist Default-Ort für Laden/Speichern von JSON-Dateien
- **Hintergrundfarbe**: "Erledigt"-Liste hat jetzt dieselbe Hintergrundfarbe wie "Offen"-Liste — einheitliches Erscheinungsbild
- **Export-Markierung**: Auswahl-Checkbox ersetzt durch `_SelectToggle` (○ / ✓) — kein Qt-QSS-Problem mehr mit unsichtbarem Haken
- **Drag-Highlight**: Gezogene Zeile erhält während des Verschiebens farbigen Hintergrund + linken Rand (Akzentfarbe)
- **Alle markieren / Alle abwählen**: Zwei neue Buttons `Alle ✓` und `Alle ○` für schnelle Export-Selektion
- **Zoom-Controls**: `−` / `100%` / `+` oben rechts — ändert nur die Schriftgröße der Listeneinträge; Icons aus dem aktiven Skin
- **Zoom-Persistenz**: Zoom-Einstellung wird in INI gespeichert (`notes/zoom_pct`) und beim nächsten Start wiederhergestellt
- **Zeitstempel bei Erledigt**: Abschluss-Zeitpunkt wird im Format `[TT.MM.JJ HH:MM]` hinter dem Text angezeigt
- **Import-Reihenfolge**: Aus JSON geladene Notizen werden in korrekter Reihenfolge oben eingefügt
- **Done-Toggle**: ☐ (offen) / ☑ (erledigt) — Stift-Experiment rückgängig gemacht

### Loop Active Checkbox — Barrierefreiheit
- **Sichtbarer Haken**: Alle 4 Skin-QSS-Dateien erweitert — `QCheckBox::indicator:checked` zeigt jetzt weißes Häkchen (check.svg) auf farbigem Hintergrund

### Sequenzen-Widget
- **Zoom-Persistenz**: Zoom-Einstellung wird in INI gespeichert (`sequences/zoom_pct`) und beim Start wiederhergestellt

### Performance
- **Notizen-Dock lazy**: Widget wird erst beim ersten Öffnen erstellt (wie Reports, Potential, Photo) — kein Startup-Overhead

---

---

## 0.50 — Frei belegbare Tasten-Trigger (2026-04-09)

### Tasten-Trigger selbst erzeugen (BL-064)
- **Neuer Button „+ Taste"** im Rules-Dialog neben der Trigger-Auswahl
- Klick öffnet Mini-Dialog: User drückt eine beliebige Taste — der Trigger-Name wird automatisch ermittelt
- Unterstützte Tasten: A–Z, 0–9, F1–F12, Space, Return, Delete, Tab, Escape, Insert, Backspace, Home, End, PageUp, PageDown
- Nach dem Erstellen taucht der neue Trigger sofort in der Trigger-Liste auf und kann einer Rule zugewiesen werden
- **Persistierung**: Neue Trigger werden automatisch beim App-Start wiederhergestellt, sofern mindestens eine Rule damit verknüpft ist
- **Fokus-Sicherheit**: Tasten-Trigger feuern nicht, wenn ein Textfeld oder eine Suche aktiv ist — diese haben immer Priorität. Gilt automatisch für alle zukünftigen Trigger.
- **Dynamischer eventFilter**: Nicht mehr hardcodiert — alle registrierten `key_*`-Trigger werden automatisch erkannt und weitergeleitet

---

## 0.49 — Label-Erkennung (bidirektional), Lyrics-Co-Import (2026-04-08)

### Label-Erkennung — bidirektionale Dateibenennung
- **Format 1 (Titel-Label)**: `Ring Of Fire-RYL818.mp3` → Titel: "Ring Of Fire", Label: "RYL818"
- **Format 2 (Label-Titel)**: `RYL818-Ring Of Fire.mp3` → Titel: "Ring Of Fire", Label: "RYL818"
- **Mit Leerzeichen im Label**: `YRR 043a-Dunderklumpen.mp3` oder `Dunderklumpen-YRR 043a.mp3`
- Regex-Pattern: Buchstaben + optionales Leerzeichen + Ziffern + optionaler Suffix (a/b/+)
- Unterstützte Label-Formate: `BVR113`, `RYL818+`, `YRR 043a`, `RBS 1326`

### Lyrics-Co-Import
- Beim MP3-Import wird automatisch eine gleichnamige Lyrics-Datei gesucht (ohne Extension-Suffix)
- **Quellordner (Import-Ordner)**: RTF/HTML/TXT-Datei wird in `lyrics/`-Ordner kopiert
- **Lyrics-Ordner**: Bereits vorhanden → wird direkt verknüpft
- Unterstützte Lyrik-Formate: `.rtf`, `.htm`, `.html`, `.txt`
- Log-Ausgabe: `[Import] Lyrics verknüpft: <dateiname>` bei erfolgreicher Zuordnung

---

## 0.48 — SqView-Migration, Blind-Import, Theme-Fix (2026-04-08)

### SqView-Migration (BL-011)
- **Ordner-Auswahl**: User wählt den SqView-Ordner direkt per Explorer — `sqview.db`, `MP3/` und `text/` werden automatisch erkannt
- **Blind-Import**: Songs werden auch ohne vorhandene MP3-Dateien vollständig in die DB eingetragen (Dateiname als Platzhalter). MP3s können später per normalem Datei-Import nachgeliefert werden — bestehende Einträge werden automatisch aktiviert statt als Duplikat übersprungen
- **Vollständige Song-Erkennung**: Liest alle ~200 Songs aus `markext1/2/3` + `track`-Tabelle (nicht nur die ~10 mit expliziten Einstellungen in der `music`-Tabelle)
- **Rekursiver MP3-Index**: Durchsucht alle Unterordner (`patter/`, `singer/`, `Karaoke/` etc.)
- **Lyrics-Matching**: 4-stufige Regex-Strategie — exakter Titel, Label-Strip (` - RBS 1234`), Normalisierung (alphanumerisch), Kombination
- **Loop- und Pitch-Übernahme**: Werte aus der SqView-`music`-Tabelle werden übernommen
- **Abspielhistorie**: Aus `track`-Tabelle mit Datum/Zeit und Lokations-Zuordnung
- Musik-Ordner ist optional (Blind-Import läuft auch ohne)
- MP3-Zählung in der Statusanzeige jetzt rekursiv

### Blind-Import aktivieren (Datei-Import)
- Beim normalen MP3-Import: Existiert bereits ein DB-Eintrag zum Dateinamen, aber die Datei fehlt noch im `music/`-Ordner → Datei wird kopiert und der Song aktiviert (statt als Duplikat übersprungen)

### Bugfix: Song Data — heller Hintergrund im Default-Theme
- `QScrollArea`-Viewport und dessen Inhalt erhielten keinen dunklen Hintergrund (Qt-Stylesheet-Vererbung greift nicht durch Viewport-Grenzen)
- Fix in allen 4 Themes (default, win11, elegant, light)

---

## 0.47 — Loop Finder Presets, CrossFade Beat Snap (2026-04-07)

### Loop Finder: Parameter-Presets (BL-046)
- **Preset-ComboBox** ersetzt den alten Reset-Button: zeigt alle gespeicherten Presets, "Standard" ist nicht überschreibbar
- **Laden**-Button: Wendet das gewählte Preset auf Suchbereiche, Vergleichsfenster und Strategie an
- **Speichern**-Button: Immer aktiv — bei "Standard" erscheint Eingabedialog für neuen Namen, bei User-Presets direktes Überschreiben
- Presets als JSON-Dateien im Ordner `loop_presets/` — portabel und editierbar
- **Strategie-ComboBox** in der Analyse-Zeile: zeigt alle verfügbaren Auswahlstrategien (aktuell: *"Bestes Vielfaches von 64 Beats"*), wird mit dem Preset gespeichert und geladen; weitere Strategien jederzeit nachrüstbar
- **Rules-Aktion "Auto-Set Best Loop"** hat jetzt Parameter `preset` (Dropdown aller gespeicherten Presets)
  - Lädt Suchbereiche, Vergleichsfenster und Strategie vollständig aus dem gewählten Preset
  - Neuer `preset_choice`-Parametertyp in rule_widget.py mit `preset_names_provider`

### CrossFade im Beat Snap (BL-067)
- Neuer Toggle-Button **CrossFade** zwischen Snap und Vorhören
- Wenn aktiv: Vorhören des Loop-Sprungs mit demselben Crossfade wie im Normalbetrieb
- Wird bei jedem Laden und jeder Waveform-Änderung automatisch deaktiviert

### Taskleisten-Icon Laptop-Fix
- `cc-logo.png` wird beim Build ins App-Root kopiert (war bisher nur auf Build-Rechner vorhanden)

---

## 0.46 — Live-Volume (BL-070), UI-Gleichraster Player (2026-04-07)

### Live-Volume / Mindest-Lautstärke (BL-070)
- Neuer **Live-Vol-Slider** im Player (4. Spalte neben Heutiges Tempo / Song-Tempo / Pitch)
- Artefaktfreie Lautstärkeänderung via Windows WASAPI (pycaw) — außerhalb des Audio-Streams, keine Knackser bei schnellen Bewegungen
- Reset auf 100% bei jedem Song-Wechsel (nicht persistent)
- INI-Einstellung `audio/min_volume` (Default `0.0`): Slider kann nicht unter diesen Wert gesenkt werden
- Wird beim App-Start automatisch in INI geschrieben falls fehlend
- Graceful Degradation: ohne pycaw (kein Windows-Gerät) bleibt Funktion stumm, App läuft normal weiter

### Rules-Aktion: Live-Volume ändern
- Neue Aktion **"Change Live-Volume (±)"** mit einstellbarem `delta` in Prozentpunkten (−100 bis +100, Default −10)
- Respektiert automatisch die `min_volume`-Grenze aus der INI

### UI: Player-Zeilen im gleichmäßigen 4er-Raster
- Zeile "Heutiges Tempo / Song-Tempo / Pitch / Live-Vol": `QGridLayout` mit `columnStretch=1` + `QSizePolicy.Ignored` → exakt gleichbreite Spalten
- Zeile "Lokation / Planner / Lyrics / Loop aktiv": ebenfalls ins 4er-Raster überführt, bündig mit Zeile darüber
- Labels mit `setWordWrap(True)` — kein Text bläht seine Spalte auf

---

## 0.45 — Genre-System, Rules Drag&Drop, Bugfixes (2026-04-06)

### Bugfix: Reports und Potential Dock-Absturz beim ersten Öffnen
- `setFloating(True)` im `visibilityChanged`-Handler loeste re-entranten Signal-Aufruf aus → Absturz
- Fix: Signal sofort trennen + Initialisierung per `QTimer.singleShot(0, ...)` zurueckstellen
- Betrifft `_on_reports_visibility` und `_on_potential_visibility`

### Genre / Tags (BL-063)
- Songs koennen mehrere Genres/Tags erhalten (Many-to-Many)
- **65 Default-Genres** aus Square Dance Labels + musicforcallers.com (Dekaden, Stile, Kuenstler, Themen, Square Dance spezifisch, NEW)
- `seed_default_genres()` ist idempotent — fuegt nur fehlende Genres ein, bestehende bleiben erhalten
- **Genre-Verwaltung** (Menue Datenbank → "Genres verwalten..."):
  - Liste aller Genres mit Song-Zaehler
  - Anlegen, Umbenennen, Loeschen
  - Beim Loeschen mit zugeordneten Songs: Wahlmoeglichkeit "Auf anderes Genre umbiegen" oder "Einfach entfernen"
- **Song-Datensatz**: Genre-Tags als klickbare Anzeige + "..."-Button oeffnet Checkbox-Dialog
  - Neues Genre direkt im Dialog anlegen moeglich
  - Aenderungen werden sofort gespeichert
- **Import-Keyword-Matching**: Beim Import werden Genres automatisch aus dem Dateinamen vorgeschlagen (z.B. "Christmas" aus "Xmas Song.mp3")
- **Rules-Aktionen**: "Add Genre to Song" und "Remove Genre from Song"
  - Parameter als Dropdown aller vorhandenen Genres (kein Freitext → keine Duplikate)
  - Neuer `genre_choice`-Parametertyp in rule_widget.py mit `genre_names_provider`

### Rules: Aktionen per Drag&Drop umordnen
- Jede Aktion-Zeile hat links ein **≡**-Handle (Cursor ↕)
- Ziehen verschiebt die Zeile live an die neue Position
- Reihenfolge der Aktionen ist sofort gespeichert
- Bugfix: `_on_action_type_changed` hatte falschen Index nach Handle-Einfuegung (combo wurde statt Params entfernt)

---

## 0.44 — Multi-Musikpfade, Import Kopieren/Belassen (2026-04-05)

### Mehrere Musik-Verzeichnisse (bis zu 4)
- Bis zu 4 Musikpfade konfigurierbar (Slot 1 = Hauptordner, Slots 2–4 optional)
- `find_song_file()` sucht in Reihenfolge Slot 1 → 2 → 3 → 4, gibt ersten Treffer zurueck
- Neuer Dialog "Musikpfade verwalten" (Menue Pfade) mit Browse + Leeren pro Slot
- Menuetext: "Musik-Verzeichnis aendern" → "Musikpfade verwalten"
- Migration: Alter INI-Key `paths/music_dir` wird automatisch nach `paths/music_dir_1` uebertragen
- Gut fuer Caller mit Programmdaten auf einem und Musikdateien auf einem anderen Laufwerk

### Import: Kopieren oder am Ort belassen
- Neuer Zwischendialog nach Songtyp-Auswahl: "Dateien kopieren?" oder "Am Ort belassen"
- Kopieren: bisheriges Verhalten — Dateien gehen ins music/-Hauptverzeichnis
- Belassen: Dateien bleiben wo sie sind, nur DB-Eintrag wird angelegt
- Bei Belassen: wenn Quellordner noch nicht als Musikpfad eingetragen, Nachfrage ob er als freier Slot ergaenzt werden soll
- Wenn alle 4 Slots belegt: Hinweismeldung mit Verweis auf den Verwaltungs-Dialog

### Single-Instance-Lock robuster (Race Condition bei Doppelklick)
- Ersetzt QLocalServer/QLocalSocket durch atomaren QLockFile
- Doppelklick auf run_test.bat oder EXE startet keine zweite Instanz mehr

### Mindestbreite Player- und Loop-Dock
- Player-Dock: min. 340px — verhindert unleshares Zusammenquetschen
- Loop-Dock: min. 400px — alle 4 Buttons bleiben nebeneinander lesbar

### Performance-Optimierung Startup (−22% auf Laptop)
- Reports-Dock: `setFloating(True)` wird nicht mehr beim Start gesetzt, sondern erst beim ersten Oeffnen (lazy) → −318ms auf Laptop
- Potential-Dock: gleiche Optimierung → −137ms auf Laptop
- Gesamtersparnis Laptop: ~526ms (2415ms → 1889ms)
- **Hinweis fuer Kunden**: Beim ersten Start nach einem Update kann die App einige Sekunden laenger brauchen — Windows Defender scannt die neuen Dateien. Ab dem zweiten Start ist alles normal.

---

## 0.43 — UI-Mindesthoehen, Song-Data-Scroll, Erststart-Sprachabfrage, Quickwin-Bundle (2026-04-04)

### Neue Rule-Aktion: Song-Tempo aendern (persistent)
- `song_tempo_change` ergaenzt zur bisherigen `tempo_change`
- **tempo_change** (umbenannt zu "Change Today's Tempo (±%)"): heutiges Tempo, nicht persistent
- **song_tempo_change** ("Change Song Tempo (±%, persistent)"): aendert das Song-Tempo und speichert den Wert ueber die bestehende Auto-Save-Kette am Song in der Datenbank
- Parameter: `delta` als Integer-Prozent, Clamp 50-150%

### Import/Migration fehlertolerant (BL-065)
- Manueller Import: Pro-Datei-try/except — defekte/unlesbare Dateien werden uebersprungen, Session laeuft weiter
- CC1-Migration: `shutil.copy2` pro MP3 gekapselt, Fehler protokolliert, Report am Ende
- SqView-Migration: gleiche Fehlerresilienz
- Auch `player._load_file()` am Ende des Imports fehlertolerant — eine defekte letzte Datei bricht die Summary nicht mehr ab

### Ordner-Import mit Unterordnern (BL-032)
- Neuer Zwischendialog "Importquelle": Einzelne Dateien oder Ordner (inkl. Unterordner)
- Bei Ordner-Auswahl wird rekursiv nach .mp3/.wav/.flac/.ogg/.aiff/.aif gesucht
- der Langzeit-Feature-Request eines Users erfuellt

### Aktiver Tab besser erkennbar (BL-060)
- `QTabBar::tab:selected` in allen Themes mit `font-weight: bold`
- Win11: Border von 2px auf 3px, expliziter `widget_bg`-Hintergrund
- Default: zusaetzliche 2px Top-Border in Selection-Farbe
- Light: Bold ergaenzt, elegant war bereits bold

### Import-Hinweis: wo die Songs landen (BL-062)
- Nach erfolgreichem Import wird das Song-List-Dock automatisch in den Vordergrund geholt
- Import-Zusammenfassung enthaelt neuen Hinweis: "Die neuen Songs wurden der Songliste hinzugefuegt."

### TIC-0014: Player-Mindesthoehe beim App-Resize
- `MainWindow.setMinimumSize()` von (1100, 650) auf (1100, 720) erhoeht
- Summe aus Player (350) + Loop (240) + Titelleisten + Menu + Statusbar passt jetzt in die Mindesthoehe
- Untere Button-Zeile (Lokation, Planner, Lyrics) wird beim Verkleinern des Hauptfensters nicht mehr abgeschnitten

### Erststart-Sprachabfrage (BL-058)
- Beim allerersten Start (keine Sprache in INI) erscheint ein Dialog: "Start in English" / "In Deutsch starten"
- Sprache wird danach in der INI gespeichert, Dialog erscheint nur einmal

### UI: Mindesthoehen gegen Quetschen (TIC-0008, TIC-0013)
- Player-Buttons (Play, Pause, Stop, Fade Out, Lokation, Planner, Lyrics): Mindesthoehe 34px
- Player-SpinBoxen (Tempo, Pitch): Mindesthoehe 24px mit Labels 16px
- Player-Widget gesamt: Mindesthoehe 350px, wird nach Layout-Restore erneut erzwungen
- Loop-Widget ("New Songs"): Mindesthoehe 240px, Buttons 52px, festes Spacing 6px
- Verhindert unleserliche UI auf kleinen Bildschirmen oder bei hoher DPI-Skalierung (z.B. 1.8x)

### Song Data: ScrollArea (TIC-0012)
- Song-Data-Widget hat jetzt eine vertikale Scrollleiste statt Quetschen bei kleinem Dock
- Alle Felder bleiben lesbar unabhaengig von der Widget-Hoehe

### Bugfix: "Titel"-Spalte nicht uebersetzt (TIC-0009)
- Spalte "Titel" in Playlist und Planner wird jetzt korrekt ueber das Uebersetzungssystem ausgegeben ("Title" auf Englisch)

### Bugfix: Show/Hide-Buttons sind jetzt echtes Toggle (TIC-0010, TIC-0011)
- `_toggle_dock()` war bisher nur Show + raise — zweiter Klick blendete nicht aus
- Planner- und Lyrics-Button blenden das jeweilige Dock jetzt beim zweiten Klick wieder aus
- Sonderfall hinterer Tab im Stapel: Dock wird nur nach vorne geholt, nicht versteckt
- Sortier-Preselect im Planner laeuft nur noch beim Oeffnen, nicht beim Schliessen

### Abgelehnt
- **BL-059** (Tabs oben statt unten): Wird bewusst nicht umgesetzt — die untere Tab-Position ist bereits im alten CC 1.x so und ist Designentscheidung zur Konsistenz mit Bestandsnutzern.

---

## 0.42 — Rules-Erweiterungen, Planner-Loeschen, App-Menu & Song-Anzeige ohne Datei (2026-03-28)

### Neue Rule-Aktionen
- **Go To Position** (BL-044): Springt zu Start, Loop-In, Loop-Out oder Ende des Songs. Position ueber Dropdown waehlbar, nutzt Crossfade-Parameter fuer sanften Uebergang
- **Toggle Loop Active** (BL-045): Schaltet die Loop-Checkbox an/aus — per Tastenkuerzel oder Regel steuerbar

### Planner: Playlist komplett loeschen (BL-049)
- Neuer roter ✖-Button ueber dem Bestaetigungs-Button im Planner
- Loescht die gesamte Playlist nach Rueckfrage-Dialog

### Song-Daten ohne Audiodatei (BL-051)
- Song-Daten und Lyrics werden jetzt auch angezeigt, wenn keine MP3/Audio-Datei vorhanden ist
- Dateiname-Feld wird rot hinterlegt als visueller Hinweis
- Warnung nur noch in der Statusbar (kein blockierendes Popup mehr)
- Ermoeglicht manuelles Verlinken einer Datei oder Einsicht in Migrationsdaten

### App-Menu (BL-052)
- Neuer erster Menueeintrag "App" mit "Beenden" — sauberes Schliessen ueber das Menu statt nur ueber das X

### Rules-Widget
- Neuer Parametertyp "choice" fuer Dropdown-Auswahl in Rule-Aktionen (z.B. GoTo-Position)

---

## 0.41 — Song-Verwaltung, Foto-Widget, RTF-Bereinigung & MDB-Erweiterungstabellen (2026-03-27)

### Song loeschen (BL-039)
- Songs koennen einzeln aus der Datenbank geloescht werden
- Sicherheitsabfrage mit Option, Historiendaten (play_history, song_location_stats) mitzuloeschen
- Auch per Entf-Taste in der Songliste aufrufbar

### Multi-File-Import mit Typ-Auswahl
- Beim Importieren neuer Songs wird vorher der Songtyp abgefragt (Pattern / Singing / Beides)
- Mehrere Dateien gleichzeitig auswaehlbar (Multi-File-Dialog)
- Gewaehlter Typ wird auf alle importierten Songs angewendet

### Foto-Widget (BL-041)
- Neues Dock-Widget mit Kamera-Vorschau (QtMultimedia: QCamera + QMediaCaptureSession)
- RAM-only: Fotos werden nur im Speicher gehalten, kein Dateisystem, keine DB
- Lazy-Init: Kamera wird erst bei erster Sichtbarkeit des Docks initialisiert
- QStackedWidget fuer Umschaltung zwischen Kamera-Preview und aufgenommenem Foto
- Rules-Aktionen: photo_capture (Kamera starten + Timer) und photo_show (90% Screen)

### RTF-Bereinigung (BL-043)
- Lyrics-Import: Word-Muell aus RTF-Dateien wird automatisch entfernt (datastore, themedata, colorschememapping, xmlnstbl, latentstyles etc.)
- Whitelist-Ansatz: Nur bekannte RTF-Gruppen (fonttbl, colortbl, stylesheet) werden behalten
- Bei betroffenen Dateien bis zu 48% Dateigroesse eingespart

### MDB-Migration: Erweiterte Tabellen (BL-047)
- access-parser Monkey-Patches fuer erweiterte CC1-Tabellen (Off-by-One, Row-Count, Primary-Key)
- History-Based Reconstruction: Wenn normale Song-Felder unlesbar, werden Songs aus der Historie rekonstruiert
- Case-insensitiver Fallback fuer Tabellen- und Spaltennamen (access-parser liefert inkonsistente Gross-/Kleinschreibung)
- Windows-Console: Unicode-sichere Log-Ausgaben (ASCII statt Sonderzeichen)

### Bugfixes
- SqView-Migration bereit fuer groessere Testdaten

---

## 0.40 — Loop-Anzahl, Performance-Optimierung & Mehrfachstart-Schutz (2026-03-26)

### Loop-Anzahl / Zeitgesteuerter Loop (BL-042)
- Neue Funktion: Caller legt gewuenschte Pattern-Dauer fest, Callers Caddy berechnet die noetige Anzahl Loops
- Zwei Optionen (ein Loop mehr / ein Loop weniger) mit resultierender Gesamtdauer
- Loop-Anzahl wird im Player angezeigt (Loop X/N bzw. Loop unendlich)
- Singing Calls zeigen "1" statt Unendlich-Zeichen in der Loops-Spalte
- Loop-Anzahl pro Playlist-Eintrag (nicht pro Song), persistiert in Playlist-Dateien
- Rueckwaertskompatibles Playlist-Format: Erkennt altes und neues Format automatisch
- Doppelklick auf Loops-Spalte oeffnet Loop-Anzahl-Dialog (Playlist + Planner)

### Player-Verbesserungen
- Song-Titel in eigener Zeile (16px fett), Info-Zeile darunter mit Timer + Loop-Count + BPM
- Loop-Marken (Loop-In / Loop-Out) werden als vertikale Linien auf dem Position-Slider angezeigt

### Playlist + Planner
- Neue Spalte "Dauer" mit berechneter Laufzeit pro Song (beruecksichtigt Loop-Anzahl)
- Gesamtdauer-Summe unter der Playlist — Caller kann den ganzen Abend verplanen
- Planner: Linker und rechter Bereich per QSplitter in der Groesse verschiebbar

### Performance-Optimierung (Startup −55%)
- App-Start: 1724ms → 780ms durch Lazy-Init von Reports, Potential und Planner
- Songliste: set_last_played_map aktualisiert nur noch Datumsspalte statt Table-Rebuild
- Playlist-Dauer: Negative Cache + Inline-Summe (250 Songs: 367ms → 5ms)
- Performance-Logging-System: `perf_start()` / `perf_log()` / `perf_split()`
- Aktivierbar via INI-Schalter `debug/performance_logging = true`

### Mehrfachstart-Schutz
- Doppelter App-Start wird verhindert (QLocalServer/QLocalSocket)
- Fehlermeldung wenn Callers Caddy bereits laeuft
- Wait-Cursor (Sanduhr) waehrend des App-Starts

### Uebersetzungen
- Neue Schluessel: header_duration, playlist_total, loop_count_per_loop, loop_count_before, loop_count_after, already_running

---

## 0.39 — SqView-Migration, Song-Volume & Verbesserungen (2026-03-26)

### SqView-Migration (Beta)
- Neuer Migrations-Pfad: SqView → Callers Caddy 2.0
- Liest sqview.db: Songs (Tempo, Pitch, Volume, Loops), Abspielhistorie, Lyrics-Zuordnungen
- Auto-Detect: Musik- und Lyrics-Ordner werden aus SqView-INI erkannt
- Ausfuehrliches Log pro Song: MP3-Status, Lyrics, Loop-Punkte, Pitch, Volume
- Nacharbeit-Bericht am Ende: fehlende MP3s und Lyrics aufgelistet
- Beta-Warnung: "Noch im Test-Stadium. Benutzung auf eigene Gefahr!"
- Dateiname-Parsing: "Title-Label.mp3" wird automatisch in Titel + Label zerlegt

### Song-Volume
- Volume-Feld in Song-Daten wird jetzt auf die Audio-Engine angewandt (multiplikativ)
- Smooth-Rampe bei Volume-Aenderung (~50ms), kein Knistern oder Knacksen
- Debounced DB-Save: nur Volume-Spalte, kein Lyrics-Reload bei Aenderung
- Range begrenzt auf 0.0–1.0 (0%–100%)

### Rules-Aktionen
- Neue Aktion: "Change Pitch" (±Halbtoene, konfigurierbare Schrittweite)
- Neue Aktion: "Change Volume" (±Faktor, konfigurierbare Schrittweite)

### Tutorial-Menu
- Neuer Menuepunkt "Alle Tutorials beenden" (Gegenstueck zu "Alle zuruecksetzen")
- Beendet laufendes Tutorial und markiert alle als abgeschlossen

### Potential-Widget
- FlowLayout fuer Check-Buttons: Buttons haben volle Textbreite, umbrechen automatisch bei schmalem Dock
- Doppelklick auf "Leere Lokation" oeffnet Lokation-Dialog mit der betroffenen Lokation vorselektiert

### Bugfix
- Tasten P und L funktionieren jetzt in Songliste/Playlist fuer Type-to-Search
  (wurden vorher vom app-weiten EventFilter geschluckt, auch bei deaktivierten Regeln)
- Tempo/Pitch-Aenderung verursacht kein Audio-Knistern mehr (Debounced Save ohne Lyrics-Reload)

---

## 0.38 — Lyrics-Redesign, Tutorials & Bugfixes (2026-03-25)

### Lyrics-Widget: As-Is-Rendering (Architektur-Vereinfachung)
- Lyrics werden jetzt 1:1 original dargestellt — wie im Browser oder Word
- Weisser Hintergrund, unabhaengig vom gewaehlten Theme
- Alle Farben (Textfarbe, Hintergrundfarbe, Highlights) bleiben original erhalten
- Sanitizer radikal vereinfacht: nur noch CSS-Link-Aufloesung + font-size-Entfernung
- Externe CSS-Dateien (z.B. cuesheet2.css) werden automatisch inlined
- RTF-Konverter: Unterstuetzung fuer \highlight (Hintergrundfarben)
- RTF-Konverter: Korrekte Behandlung von \*\background und weiteren Header-Gruppen
- Neuer Button "Auto-Breite": Skaliert Schrift so, dass Text in die Fensterbreite passt
- Auto-Breite auch als Rules-Aktion verfuegbar ("Lyrics Auto-Width")

### Tutorials
- Neues Tutorial: Loop Finder (6 Schritte: Wellenform, Suchbereich, Suchfenster, Analyse, Ergebnisse, Uebernehmen)
- Neues Tutorial: Rules (7 Schritte: Regelliste, Neue Regel, Name/Aktiv/Once, Trigger, Bedingungen, Aktionen, Import/Export)

### Song-Restart
- Play-Button bei laufendem Song = Neustart von vorne (seek 0)
- Kein Stop+Start mehr noetig, auch per F5-Rule nutzbar

### Bugfixes
- HTML-Lyrics mit externem CSS werden jetzt korrekt dargestellt (TIC-0001)
- RTF-Lyrics mit Farben und Highlights werden originalgetreu angezeigt (TIC-0002)
- App-Icon in Titelleiste und Windows-Taskleiste (TIC-0004)
- CP1252-Encoding-Fallback beim Laden von Playlists (der utf-8 Fehler eines Users)

### Ticket-System
- Neues Ticket-System unter 5_Tickets/ fuer Fehlermeldungen und Fragen
- TICKETS.md als Uebersicht, ein Ordner pro Ticket mit Anhaengen

---

## 0.37 — Regel-Engine & Automatisierung (2026-03-24)

### Regel-Engine (neues System)
- Komplett neues Automatisierungssystem: Trigger → Bedingungen → Aktionen
- **26 Trigger**: App-Lifecycle (Start, Song gestartet/pausiert/gestoppt/resumed/gewechselt), periodischer Timer, Tastatur (F1–F12, Space, L, P), Manager geschlossen
- **9 Bedingungen**: Songtyp (Singing/Patter), Lyrics vorhanden/nicht, Loop gesetzt/nicht, Location gewaehlt/nicht, Spielzeit ueber Schwellwert
- **25 Aktionen**: Dock oeffnen/schliessen/Vollbild/Fokus, Layout laden, Play/Pause/Stop/Fade-Out/Toggle, Auto-Advance, Auto-Scroll Start/Stop, Tempo aendern, Statusbar-Nachricht, Log-Nachricht, System-Ping, Warn-Hintergrund (Ampel), Location-Dialog, Manager-Toggle, Auto-Loop-Finder
- Bedingungslogik: Flexible UND/ODER-Gruppen (z.B. „Singing UND Lyrics vorhanden ODER Patter UND Loop gesetzt")
- „Einmal pro Song"-Option: Regel feuert maximal einmal pro Song

### Regel-Editor (neues Widget)
- Dockbares Editor-Widget mit zweigeteiltem Layout (Regelliste links, Editor rechts)
- Suchfeld zum Filtern nach Name oder Trigger
- Sortierbare Tabelle: Aktiv-Checkbox, Name, Trigger, Quelle (System/User)
- Dynamische Parameter-Eingabefelder je nach Aktions-/Bedingungstyp
- Buttons: Hinzufuegen, Duplizieren, Loeschen, Hoch/Runter, Export, Import

### System- vs. User-Regeln
- **13 vorinstallierte System-Regeln** (nur Aktiv-Toggle aenderbar, nicht editierbar):
  - Singing Call → Lyrics Vollbild mit Auto-Scroll (Start + Resume)
  - Singing Call Stop/Pause → Default Layout zurueck
  - Song Stop → Auto-Advance
  - Manager geschlossen → Playlist fokussieren
  - Tastatur-Shortcuts: F5=Play, F6=Pause, F7=Stop, F8=Fade-Out, Space=Play/Pause, L=Location, P=Manager
- **User-Regeln**: Voll editierbar, Import/Export als JSON, frei sortierbar

### Regel-Logging
- Eigene Log-Datei `rules/rules.log` mit Kategorien: TRIGGER, MATCH, NO_MATCH, ACTION, ERROR, BLOCKED
- Automatische Rotation bei 1 MB (behält 500 Zeilen)
- Hilft bei Diagnose, warum Regeln feuern oder nicht

### Auto-Loop-Finder (Regel-Aktion)
- Neue Aktion `auto_set_best_loop`: Analysiert den Song automatisch und setzt den besten 64-Beat-Loop
- Bevorzugt 64-Beat-Loops, Fallback auf hoechsten Score
- "Bitte warten"-Overlay waehrend der Analyse (halbtransparent, verschwindet automatisch)
- Kann per Regel z.B. bei Song-Start automatisch ausgeloest werden

### Performance-Optimierung
- **Lazy Waveform**: Loop-Finder-Waveform wird erst bei Sichtbarkeit geladen (spart ~100-400ms beim Songwechsel)
- **Gezieltes Song-Update**: Nach Abspielen wird nur die Last-Played-Spalte aktualisiert statt die gesamte Songliste neu aufgebaut (~4-22ms statt ~400-1200ms)

### Loop-Widget: Neues Button-Layout
- Alle 4 Buttons (Set In, Clear, Set Out, Test Loop) in einer flachen Zeile
- Buttons schrumpfen bei Platzmangel mit automatischem Textumbruch
- Player-Spalte laesst sich jetzt deutlich schmaler ziehen

### Dock-Widget-Verbesserungen
- **Features-Persistenz**: Dock-Faehigkeiten (Verschieben/Andocken/Schliessen) bleiben nach Layout-Wiederherstellung erhalten (Qt-Bug behoben)
- **Kleinere Fenstergroessen**: Docks lassen sich jetzt auch andocken, wenn die App nicht im Vollbild laeuft (minimumSize-Fix)

### Bugfixes
- **Loop-Guard**: Snapshot-Werte von 0.0 werden korrekt als ungueltig erkannt — verhindert Ueberschreiben guter Loop-Werte beim Schliessen
- **Audition/Beat Snap**: Abspielen im Loop Finder und Beat Snap wird nicht mehr in der Play-Historie geloggt
- **Loop Finder schliessen**: Stoppt laufende Wiedergabe automatisch
- **Resume-Regel**: Funktioniert wieder zuverlaessig nach Layout-Wechsel (Focus-Restore nach restoreState)

---

## 0.36 — Loop Finder & UI-Reorganisation (2026-03-21)

### Loop Finder (neues Widget)
- Neues dockbares Fenster "Loop Finder" — sucht automatisch passende Loop-Punkte
- Aehnlichkeitsbasierte Analyse: Vergleicht Phrasen im vorderen und hinteren Songbereich
- 8-Beat-Nummerierung: Alle Beats werden 1-8 durchgezaehlt, Spruenge nur zwischen gleichen Beat-Positionen
- Downbeat-Erkennung: Bevorzugt Kandidaten auf geschaetztem Beat 1 (Kick-Energie-Heuristik)
- Chroma-basierter Harmonie-Score (FFT → 12 Halbtoene, rein mit scipy/numpy)
- Einstellbares Vergleichsfenster: 4, 8, 16, 32 oder 64 Beats per ComboBox
- Einstellbare Suchbereiche: 4 Prozentfelder (Default 7%/21%/64%/79%) mit Reset-Button
- Waveform-Uebersicht mit farbigen Suchbereichen (gruen = Loop-In, orange = Loop-Out)
- 4 verschiebbare Handles (beide Seiten pro Region per Maus anpassbar)
- 7 Singing-Call-Segmente ueber der Waveform (Opener, 1-4, Middle Break, Closer)
- Weisse gestrichelte Marken zeigen den selektierten Vorschlag in der Waveform
- Sortierbare Ergebnistabelle: Klick auf Spaltenueberschrift sortiert nach Score, Beat, Zeit
- Audition-Funktion: Startet 5 Sekunden vor Loop-Out, springt, stoppt 2 Sekunden nach Loop-In
- Apply-Button: Uebernimmt den Vorschlag als Loop-In/Loop-Out in den Player
- Analyse laeuft in QThread (nicht blockierend)
- Keine neuen Abhaengigkeiten — alles mit scipy + numpy

### UI-Reorganisation (Loop-Widget)
- **Loop Active → Player**: Checkbox aus dem Loop-Widget in die Player-Toolbar verschoben (rechts neben Lyrics)
- **3-Spalten-Layout**: Loop-In-Zeit und Loop-Out-Zeit stehen zentriert ueber ihren Buttons
- **Button-Reihe**: Set Loop-In | Set Loop-Out | Test Loop nebeneinander
- **Neue Button-Reihe**: Loop Finder | Beat Snap nebeneinander
- Fixe Zeilenhoehe im 3-Spalten-Grid (dehnt sich nicht bei groesserem Widget)

### Loop Finder Dock
- Eigenes Dock-Widget, darf nicht mit anderen Widgets andocken (Qt.NoDockWidgetArea)
- Oeffnet sich ueber den neuen "Loop Finder"-Button im Loop-Widget

## 0.35 — Guided Tutorials & Verbesserter Loop-Guard (2026-03-20)

### Tutorial-System (13 Tutorials)
- Neues geführtes Tutorial-System mit Tooltip-Overlays und Highlight-Rahmen
- 11 Widget-Tutorials: Player, Layout, Songliste, Song-Daten, Planner, Playlist, Loop, Lyrics, Sequenzen, Reports, Potential
- 2 Dialog-Tutorials: Lokationen, Beat Snap
- Prioritaetsbasierte Reihenfolge: Player → Lokationen → Layout → Songliste → ... → Potential
- Automatisches Chaining: Nach Abschluss eines Tutorials wird das naechste angeboten
- Tutorial-Angebot ablehnbar: "Nicht jetzt" pausiert Tutorials fuer die Sitzung
- Schritt-Navigation: Weiter, Zurueck, Ueberspringen + Schritt-Anzeige (z.B. "3 / 5")
- Enter = Weiter, Escape = Ueberspringen

### Tutorial-Menu
- Neues Untermenu "Tutorials" mit allen Tutorials in Prioritaetsreihenfolge
- Haekchen (✓) vor bereits abgeschlossenen Tutorials
- "Alle Tutorials zuruecksetzen" setzt den Fortschritt komplett zurueck
- Menu-Auswahl hat Vorrang ueber automatisches "naechstes Tutorial"
- Einzelne Tutorials koennen jederzeit ueber das Menu neu gestartet werden

### Tutorial-Architektur
- Drei-Komponenten-System: Transparentes Overlay (Klick-Faenger) + Highlight-Rahmen + Tooltip-Popup
- Highlight und Tooltip als eigenstaendige Tool-Fenster (liegen ueber QDockWidgets)
- Multi-Element-Highlighting: Mehrere Elemente gleichzeitig rahmen (z.B. BPM-Feld + Auto-Button)
- Dialog-Tutorials: Eigene leichtgewichtige Engine fuer modale Dialoge (LocationDialog, BeatSnapDialog)
- Spezial-Pfade: `_menu_bar`, `_dock_XXX_title` fuer Menu und Dock-Titelleisten
- Floating-Dock-Management: Lose Docks werden waehrend Tutorials versteckt und danach wiederhergestellt
- Tooltip-Box mit eigenem paintEvent (opaker Hintergrund trotz transparentem Overlay)
- Dedizierte Skin-Farben: `tutorial_box_bg`, `tutorial_box_text`, `tutorial_highlight` in allen 4 Themes

### Beat Snap: "Adjust" → "Snap"
- Button-Beschriftung von "Adjust" zu "Snap" umbenannt (inklusive Tooltip und Status-Text)

### Verbesserter Loop-Guard (Datenbank)
- Erweiterter Schutz gegen versehentliches Ueberschreiben von Loop-Werten
- Neuer Guard 2: Erkennt das Engine-Reset-Muster (loop_in=0 + loop_out=Songdauer) und schuetzt gespeicherte Werte
- Bisheriger Guard schuetzte nur gegen 0.0, nicht gegen die Songdauer als loop_out

### Win11 Theme
- Zoom-SVG-Icons: Strichfarbe von dunkel (#1b1b1b) auf weiss (#ffffff) geaendert (bessere Sichtbarkeit auf blauem Hintergrund)

## 0.34 — Keyboard-Shortcuts & Elegant Gold Theme (2026-03-19)

### Keyboard-Shortcuts (App-weit)
- **L-Taste**: Oeffnet Lokations-Auswahl-Dialog (mit Fokus auf Lokationsliste)
- **P-Taste**: Oeffnet/schliesst Planner (mit Fokus auf Pool-Tabelle)
- App-weiter EventFilter statt QShortcut (funktioniert auch bei fokussierten Tabellen/Listen)
- Modale Dialoge blockieren Shortcuts automatisch
- Textfelder/SpinBoxen werden erkannt und nicht abgefangen
- Planner-Sortierung wird automatisch vorausgewaehlt (Empfehlung bei Lokation, Qualitaet sonst)

### Elegant Gold Theme
- Neues Theme "Elegant Gold": Anthrazit-Basis mit strahlendem Gold (#d4a017)
- Goldene Titelleisten, Buttons, aktive Tabs, Header-Trennlinien und Tooltips
- Deaktivierte Elemente in mittlerem Goldton (#7a6a2e)
- Eingabefelder und Listenbereiche mit leichtem Goldfarbton (#2e2a1f)
- SVG-Icons: Pfeile und Dock-Buttons schwarz (#000000), Lupen/Zahnrad dunkelbraun (#2a2518)
- Section-Bar-Segmente (Singing Call 1/2/3/5) in mittlerem Goldton

### Fokus-Management
- Startup-Fokus auf Songliste (verhindert Shortcut-Blockade durch SpinBox)
- Floating-Dock-Aktivierung: `activateWindow()` vor `setFocus()` fuer Keyboard-Input
- Lokations-Dialog: Fokus auf Liste bei vorhandenen Eintraegen, auf Hinzufuegen-Button bei leerer Liste

### Tooltip-Verbesserungen
- Lokations- und Planner-Buttons zeigen Shortcut-Hinweis im Tooltip (L) / (P)

## 0.33 — Potential-Widget & Menu-Umbau (2026-03-18)

### Potential-Widget (Datenqualitaet)
- Neues dockbares Fenster "Potential" — zeigt Optimierungspotential in der Songdatenbank
- 5 Checks mit Badge-Counter auf den Buttons:
  - Singing Calls ohne Lyrics
  - Pattern ohne Loop-Marken
  - Loops ohne BeatSnap-Optimierung
  - Lokationen ohne Abspielhistorie
  - Verwaiste Historieneintraege (geloeschte Lokationen)
- Doppelklick navigiert zum betroffenen Objekt (Song-Daten, Beat Snap, Lokation)
- "Ignorieren"-Button: Einzelne Eintraege als bewusst akzeptiert markieren
- "Alle bereinigen": Verwaiste History-Eintraege per Batch loeschen
- Lazy Loading: Daten werden erst beim Einblenden geladen
- DB: Neue Tabelle `potential_ignored` (check_type + entity_id)

### Lokation loeschen
- Loesch-Funktion funktioniert jetzt korrekt (vorher durch Foreign Key blockiert)
- Checkbox "Historiendaten ebenfalls loeschen" im Bestaetigungsdialog
- Ohne Checkbox: Historie bleibt als verwaiste Eintraege erhalten (im Potential sichtbar)
- Mit Checkbox: Historie und Stats werden komplett geloescht

### Menu-Umbau
- "Design" umbenannt zu "Einstellungen" / "Settings"
- Datumsformat-Einstellung von Ansicht nach Einstellungen verschoben
- Sprach-Einstellung von Info nach Einstellungen verschoben
- "Skin" umbenannt zu "Theme" (Menue, Dialoge)
- Datumsformat-Label: "DE" geaendert zu "EU" (europaweit gueltig)

### Default-Layout (3-spaltig)
- Neues 3-Spalten-Layout als Standard bei Erstinstallation und Layout-Reset
- Spalte 1: Player oben, Loop/Neu unten
- Spalte 2: Songliste und Playlist als Tabs (Songliste aktiv)
- Spalte 3: Lyrics, Song-Daten und Sequenzen als Tabs (Lyrics aktiv)
- Planner, Reports, Potential versteckt (ueber Menu oeffenbar)

### Technisch
- Layout-Version 3 (neues Dock erfordert Layout-Reset)
- Dock-Aufbau-Reihenfolge: Zuerst 3 Spalten horizontal, dann Spalte 1 vertikal teilen
  (verhindert dass Player ueber volle Breite spannt)

## 0.32 — Keyboard, Datei-Auswahl & Loop-Verbesserungen (2026-03-18)

### Keyboard & Datei-Auswahl
- ENTER-Taste: Song in Songliste laden, Song im Planner-Pool zur Playlist hinzufuegen, Song in Playlist entfernen
- F-Tasten (F5-F8, Space) funktionieren jetzt auch bei abgedockten Fenstern (ApplicationShortcut)
- Datei-Auswahl-Button ("...") in Song-Daten: Audio-Datei nachtraeglich aendern
- Bei bereits vergebener Datei: Kopie-Dialog mit automatischer Kopie-Erstellung
- Erweiterte Audio-Format-Unterstuetzung: WAV, FLAC, OGG, AIFF neben MP3
- Audio-Format-Filter auch im Import-Dialog erweitert
- Neue DB-Methode `update_filename()` mit UNIQUE-Constraint-Pruefung

### Loop-Crossfade
- Nahtloser Loop-Uebergang durch Crossfade statt hartem Schnitt
- Crossfade-Dauer konfigurierbar via INI `loop/crossfade_ms` (Default 46ms)
- Eliminiert WSOLA-Einschwing-Artefakte am Loop-Punkt (kein flush/warmup noetig)
- Budget-basierter Loop-Mechanismus: Callback zaehlt Output-Samples, kein Stretcher-Zugriff aus UI-Thread
- Fallback-Sicherung: Feed-Level Loop-Back falls UI-Timer den Seek verpasst

### Loop-Offset (pro Song)
- Automatische Offset-Messung via FFT-basierter Kreuzkorrelation (Tiefpass <200Hz)
- Findet optimalen Versatz zwischen Loop-Ende und Loop-Anfang im Bass-Bereich
- Suchbereich ±2 Sekunden, waehlt den kleinsten Offset mit guter Korrelation (>= 0.1)
- Offset wird pro Song in der DB gespeichert (`loop_offset_ms`)
- Manuelle Feinkorrektur ueber SpinBox in Song-Daten (±3000ms, 0.5ms Schritte)
- Auto-Messung bei Beat Snap und Loop-Test, Ergebnis in DB + SpinBox
- DB-Migration: Neue Spalte `loop_offset_ms` wird automatisch angelegt

### Bugfixes
- Playposition-Anzeige (Uhrzeit + Slider) klemmt nicht mehr bei Pattern-Start mit Loop
- Loop-Marken werden beim Dateiwechsel nicht mehr auf 0 zurueckgesetzt

## 0.31 — Beat Snap Audition (2026-03-16)

- Beat Snap Dialog: Vorhoeren des Loop-Sprungs mit Waveform-Visualisierung
- Doppelte Waveform-Anzeige (Loop-Out oben, Loop-In unten) mit Cursor-Synchronisation
- Playback-Sample-Counter (`_playback_sample`) in Audio-Engine fuer praezise Positionsbestimmung
- Engine-Loop wird waehrend Audition deaktiviert (verhindert Doppel-Sprung durch Feed-Ahead)
- Layout-Versionierung: `_LAYOUT_VERSION` verhindert korrupte Dock-States bei Aenderungen
- Versioned `saveState()`/`restoreState()` — alter State wird automatisch verworfen
- Bugfix: Dock-Widgets liessen sich nicht mehr einrasten nach P30→P31 Dock-Aenderung

## 0.30 — BPM-Detection, Reports, Lyrics-Kontrast (2026-03-14)

- Auto-BPM-Erkennung via Comb-Filter-Bank (scipy/numpy, keine neuen Pakete)
- Sub-Harmonik-Korrektur: Integer-Vielfache pruefen, hoehere Tempi bevorzugen
- BPM-Detection laeuft in QThread (nicht blockierend)
- Reports-Widget: Setlist/Musikfolgeliste fuer GEMA mit TXT-Export
- Bidirektionale ComboBox-Filterung (Lokation ↔ Datum)
- Lyrics-Kontrast: WCAG-basierte Farberkennung fuer Word-HTML (bgcolor, background, color)
- Sanitizer entfernt Block-Hintergruende, behaelt Inline-Highlights, ersetzt schlechte Textfarben
- Default-Stylesheet wird bei jedem Skin-Wechsel und setHtml() aktualisiert

## 0.29 — Release-Vorbereitung (2026-03-12)

- Internationalisierung: i18n-Modul mit JSON-Translations (Deutsch/Englisch)
- 5-Stufen-Ordnerstruktur: 1_Source, 2_Test, 3_Build, 4_Release, _archive
- Build-Pipeline: PyInstaller-Spec + build.py (Vollpaket, Update, Source-ZIP)
- Clean-DB-Skript: Entfernt User-Daten, behaelt Referenzdaten (Sequenzen, Teaching Order)
- Migration-EXE: Separater Access-Import-Prozess
- Portable Pfade: App-Verzeichnis neben EXE statt Prototypen-Ordner

## 0.28 — Sequenzen-Fenster + Design-Menu + Audio-Fix (2026-03-11)

- Neues dockbares Fenster "Sequenzen" (Dock 9, getabbt mit Lyrics)
- Import von 885 Singing-Call-Sequenzen aus Access-MDB (caller.mdb)
- Cached Live-Mapping gegen Burleson-Vocabulary (Teaching Order)
- Contains-Filter: Autocomplete-Suche nach enthaltenen Calls
- Limit-Filter: Nur Sequenzen bis zu einem bestimmten Programm-Level
- Lazy Loading (50er-Bloecke) fuer schnelles Scrollen
- Detail-Dialog mit allen Calls und Programm-Tags
- Remapping-Button (Zahnrad) fuer Teaching-Order-Neuberechnung
- Zoom [-/+] mit Prozentanzeige (wie Lyrics-Widget)
- Neues Modul: sequence_mapper.py (Burleson-Mapping-Logik)
- DB-Erweiterung: sequences + sequence_calls Tabellen mit Indizes
- Design-Menu: Layout laden/speichern/wiederherstellen + Skin-Wechsel zur Laufzeit
- Benannte Layouts: Caller koennen "Live.ini", "Workshop.ini" etc. speichern
- Playlist-Manager umbenannt zu "Planner" (kuerzer, ueberall umbenannt)
- Caller-Workflow-Guidance: Lokation → Planner-Button rot → Planner bestaetigt → Playlist fokus
- Audio-Fix: Persistenter Stream (kein Knacken/Brummen bei Song-Start)
- WSOLA-Warmup: 200ms Einschwingphase wird als Stille ausgegeben

## 0.27 — Performance-Optimierung (2026-03-11)

- Performance-Messframework mit Phase A (Baseline) und Phase B (Stresstest mit 10k Songs)
- Testmethodik: 10 Wiederholungen, Statistik (Mean/StdDev/Min/Max), CSV-Export
- Pool-Tabelle im Playlist-Manager: **40% schneller** durch optimiertes Tabellen-Pattern
- Songliste: **7% schneller** durch gleiche Optimierung
- Erkenntnis: QTableWidget-Rebuild ist der Flaschenhals, nicht DB oder Sortierung
- Optimiertes Pattern: `setRowCount(0)` + `setRowCount(n)` + `setItem()` statt `insertRow()`

## 0.26 — Lyrics-Anzeige (2026-03)

- Lyrics-Widget als dockbares Fenster (getabbt mit Song-Daten)
- Unterstuetzte Formate: HTML/HTM, RTF, TXT
- Auto-Fit: Schriftgroesse wird automatisch angepasst wenn Text auf eine Seite passt
- Auto-Scroll: Proportional zum Song-Fortschritt
- Smarte Farb-Bereinigung: Hintergruende entfernt, Sektionsfarben beibehalten
- Toolbar mit Auto-Scroll/Auto-Size Toggle und Zoom +/-
- Light Blue Skin: Zweites Farbschema (helle Oberflaeche, blaue Akzente)
- Muted- und Indicator-Farben fuer besseren Kontrast in beiden Skins
- Loop-Save-Bugfix: Snapshot-Mechanismus sichert Loop-Werte vor Song-Wechsel
- Gemeinsame Datenordner (music/, lyrics/, playlists/) sparen Plattenplatz

## 0.21 — Playlist und Playlist-Manager (2026-03)

- PlaylistWidget: Schlank, getabbt neben Songliste, Laden/Speichern als .txt
- PlaylistManagerWidget: Zwei-Panel-Ansicht mit Song-Pool und Playlist-Spiegel
- Song-Transfer: Doppelklick, Pfeil-Buttons, Drag & Drop
- 4 Sortierungen: Alphabetisch, Qualitaet, Zuletzt gespielt, Empfehlung
- Filter: Alle / nur Pattern / nur Singing
- Auto-Advance: Naechster Song bei Song-Ende, Stop oder Fade-Out
- Fade-Out: Konfigurierbarer linearer Volume-Ramp (Default 3s)
- Empfehlungssystem integriert (urspr. P25)
- Playlist-Builder integriert (urspr. P24)

## 0.20 — Abspielhistorie (2026-03)

- Drei-Schichten-Architektur: play_history, song_location_stats, On-the-Fly-Berechnung
- "Zuletzt gespielt"-Spalte in der Songliste
- Lokations-bezogene Statistik (wann wurde welcher Song wo gespielt)
- Umbenennung: "Club" wird zu "Lokation" (generalisiert fuer Club + Special)
- INI-Setting fuer Datumsformat (deutsch/amerikanisch)

## 0.19 — Lokationen (2026-03)

- Club- und Special-Verwaltung als auswaehlbare Kontexte
- Lokationsauswahl beeinflusst Songempfehlung und Historie

## 0.18 — Pattern/Singing-Modus (2026-03)

- Songs als Pattern, Singing oder beides markierbar
- Typ-Kuerzel (P/S/PS) in Songliste und Pool-Anzeige
- Filter im Playlist-Manager nach Modus

## 0.17 — Heutiges Tempo (2026-03)

- Gespeichertes Tempo pro Song fuer den heutigen Abend
- Tempo wird beim Laden eines Songs automatisch wiederhergestellt

## 0.16 — Songliste mit Suche (2026-03)

- Songliste als QTableWidget mit Echtzeit-Suchfilter
- Suche ueber Titel, Label und Dateiname

## 0.15 — Portable Pfade (2026-03)

- Relative Pfade fuer Songs und Daten
- Anwendung kann auf USB-Stick oder zwischen Rechnern verschoben werden

## 0.14 — Auto-Save (2026-03)

- Automatisches Speichern aller Aenderungen (Song-Daten, Einstellungen)

## 0.13 — Song-Datenmodell (2026-03)

- SQLite-Datenbank fuer Songs, Lokationen, Historie
- Song-Felder: Titel, Dateiname, Label, Qualitaet, Pattern/Singing, Tempo

## 0.07 — Dock-Fenstersystem (2026-03)

- QDockWidget-basiertes Fenstersystem mit freier Anordnung
- Fenster verschieben, andocken, stapeln, Groesse aendern
- Layout wird gespeichert und beim Neustart wiederhergestellt
- Resize-Regeln pro Fenstertyp
- Integriert: P8 (Ein-/Ausblenden), P9 (Verschieben), P10 (Resize-Regeln), P11 (Docking), P12 (Layout-Persistenz)

## 0.06 — Loop mit Tempoanpassung (2026-03)

- Loop-Region bleibt bei Tempowechsel stabil
- Eigener Streaming-WSOLA-Algorithmus (kein Rubber Band/SoundTouch)

## 0.05 — Loop-In / Loop-Out (2026-03)

- Markierbare Loop-Region mit Start- und Endpunkt
- Nahtloser Loop waehrend der Wiedergabe

## 0.04 — Tempo und Pitch gleichzeitig (2026-03)

- Unabhaengige gleichzeitige Tempo- und Pitch-Steuerung

## 0.03 — Pitch-Steuerung (2026-03)

- Tonhoehe stufenlos aendern, unabhaengig vom Tempo

## 0.02 — Tempo-Steuerung (2026-03)

- Wiedergabegeschwindigkeit stufenlos aendern

## 0.01 — MP3-Wiedergabe (2026-03)

- MP3-Dateien laden und stabil abspielen
- Grundlegende Transportsteuerung (Play, Pause, Stop)
- Positionsanzeige und Seek-Slider
