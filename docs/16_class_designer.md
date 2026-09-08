# Lastenheft - Class-Designer für Callers Caddy

## Vorläufige Sammlung

### 1. Ausgangsidee

Der **Class-Designer** soll **nicht direkt in Callers Caddy integriert** werden, sondern als **separates Tool** bereitgestellt werden.

Begründung:

* Die Funktion wird nur gelegentlich genutzt.
* Sie soll **keine unnötige Performance im Hauptprogramm Callers Caddy** beanspruchen.
* Der Aufbau soll dem bestehenden separaten Tool **Migration.exe** entsprechen.

### 2. Bereitstellung

* Der Class-Designer soll als **eigene EXE-Datei** ausgeliefert werden.
* Die EXE liegt **im gleichen Ordner wie Callers Caddy**.
* Das Tool wird **separat gestartet**.

### 3. Gestaltung

* Das Design soll sich **am Default-Design von Callers Caddy** orientieren.
* Ziel ist ein **optisch und funktional stimmiger Eindruck** innerhalb der vorhandenen Programmwelt.

### 4. Zweck des Tools

Mit dem Class-Designer soll eine **Class systematisch geplant** werden.

Geplant werden sollen insbesondere:

* neue Figuren, die eingeführt werden
* Figuren, die bewusst wiederholt werden müssen
* sonstige Hinweise oder Planungseinträge ähnlich einer Notizliste

Der Class-Designer soll also eine Art **strukturierte Unterrichts- und Ablaufplanung** für mehrere Class-Abende ermöglichen.

### 5. Bezug zu bestehenden Daten

* Es soll auf die in Callers Caddy bereits vorhandenen **Figurenlisten** zurückgegriffen werden.
* Diese Figuren sind bereits bei den **Sequenzen** hinterlegt.
* Für Programme von **Basic bis mindestens C1/C3** sind dort laut aktueller Annahme die Figuren aus der Teaching Order vorhanden.
* Diese vorhandenen Daten sollen nach Möglichkeit als Grundlage genutzt werden.

#### DB-Zugriff

* Das Tool greift direkt auf die gemeinsame `callers_caddy.db` zu (Read-Only für Figurdaten).
* Ein **gleichzeitiger Betrieb** von Callers Caddy und Class-Designer ist **nicht vorgesehen**.
* Wenn die DB bereits durch Callers Caddy geöffnet/gesperrt ist, erscheint eine **Warnung** mit dem Hinweis, Callers Caddy zuerst zu schließen.
* Erst danach kann der Class-Designer gestartet werden.

### 6. Auswahl des Tanzprogramms

Eine Class bezieht sich immer auf ein bestimmtes Tanzprogramm.

Daher soll es ein erstes Feld geben:

* **Für welches Tanzprogramm soll die Class geplant werden?**

Auswahlbasis:

* dieselben Tanzprogramme, die auch in den Sequenzen vorhanden sind
* z. B. Mainstream, Plus, A1, A2 usw.

### 7. Planungsliste

Es soll eine anfangs leere Liste geben, in der die Inhalte der Class zusammengestellt werden.

Eigenschaften:

* grundsätzlich ähnlich zur Liste in den **Notizen**
* jedoch **ohne Kennzeichnung offen/erledigt**
* Fokus liegt auf **Planung und Reihenfolge**, nicht auf Abarbeitung

### 8. Freie Einträge und Trenner

Neben Figuren sollen auch allgemeine Planungseinträge möglich sein.

Zusätzlich soll es Trenner geben:

* analog zur Notizfunktion
* Eingabe über `---`
* Darstellung als sichtbarer Trenner in der Liste

### 9. Figurenverwaltung pro Figur

Für jede Figur sollen zusätzliche Eigenschaften gepflegt werden können.

#### 9.1 Aufwand

Für jede Figur soll ein Feld für den **Aufwand** vorhanden sein.

Gedanke:

* Der Aufwand soll quantifizieren, wie anspruchsvoll oder umfangreich eine Figur in der Vermittlung ist.
* Als Werte sollen bevorzugt Zahlen aus der **Fibonacci-Reihe** genutzt werden.

Vorgesehene typische Werte:

* 1
* 2
* 3
* 5
* 8

"Aufwand" wird derzeit als passender betrachtet als "Schwierigkeit" oder "Difficulty".

#### 9.1.1 Aufwand für Wiederholungen

* Wiederholungen haben einen **eigenen, separat konfigurierbaren Aufwandswert**.
* Dieser ist typischerweise niedriger als der Ersteinführungs-Aufwand (z. B. 1 oder 2).
* Wiederholungen dienen explizit als **Ausgleichswerkzeug**: Tage mit zu viel Aufwand können durch gezielte Verschiebung von Wiederholungen entlastet werden.

#### 9.2 Abhängigkeiten

Für jede Figur soll festgelegt werden können, von welchen anderen Figuren sie abhängt.

Beispiel:

* Eine spätere Figur baut auf einer oder mehreren vorherigen Figuren auf.

Daher soll möglich sein:

* einer Figur **mehrere Voraussetzungen** zuzuordnen

#### 9.3 Verzögerung bei Abhängigkeiten

Zusätzlich zu Abhängigkeiten soll eine **Verzögerung** definiert werden können.

Bedeutung:

* Eine abhängige Figur darf nicht direkt nach Einführung der Voraussetzung gelehrt werden.
* Stattdessen sollen erst noch eine bestimmte Anzahl von Class-Abenden vergehen.

Beispiel:

* Figur B hängt von Figur A ab
* Figur B darf erst eingeplant werden, wenn nach Figur A noch **2 weitere Abende** vergangen sind

Ziel:

* Vorwissen soll sich erst festigen, bevor darauf aufgebaut wird.

### 10. Dauer der Class

Es soll angegeben werden können, **wie viele Abende** eine Class dauern soll.

Ziel:

* Die geplanten Inhalte sollen auf die vorhandenen Abende verteilt werden können.

### 10.1 Automatische Abendplanung

Wenn alle erforderlichen Informationen vorliegen, soll der Class-Designer **automatisch einen konkreten Plan für die einzelnen Abende erzeugen**.

Beispiel:

* Bei einer Class mit z. B. 20 Abenden soll das Tool die Figuren und Wiederholungen passend auf diese Abende verteilen.

Der automatisch erzeugte Plan soll in einer eigenen Bereichs- oder Ergebnisspalte sichtbar sein.

#### Algorithmus-Ziel: Ausgeglichene Verteilung

* Der Algorithmus soll die Aufwandspunkte **möglichst gleichmäßig** auf alle Abende verteilen.
* Dies entspricht einem **Bin-Packing-Problem** mit Constraints:
  * Abhängigkeiten zwischen Figuren müssen eingehalten werden
  * Verzögerungen (Mindestabstand in Abenden) müssen eingehalten werden
  * Teaching-Order-Reihenfolge soll so weit wie möglich gewahrt bleiben
* **Wiederholungen** sind das flexible Element: Sie können gezielt eingesetzt werden, um Abende mit zu wenig Inhalt aufzufüllen oder Abende mit zu viel Aufwand zu entlasten.
* Eine explizite Aufwands-Obergrenze pro Abend ist zunächst nicht vorgesehen — das Ziel ist Ausgeglichenheit, kein hartes Limit.

#### Wiederholungs-Verteilung

* Wiederholungen werden **auf die Abende nach der Ersteinführung** verteilt.
* Die genaue Platzierung erfolgt durch den Algorithmus als Ausgleichsmechanismus.

#### Prüfen / Optimieren (Zweistufen-Verfahren)

Die Erstbelegung durch den Generator („Plan erzeugen") ist eine einfache Greedy-Heuristik und produziert brauchbare, aber nicht optimale Verteilungen. Deshalb trennen wir **Erzeugung** und **Optimierung** in zwei Schritten — dasselbe Muster, das in der Scheduling-Literatur Standard ist:

1. **Generator** — schnelle Heuristik füllt den Plan grob (List Scheduling mit Prereq-Prioritäten)
2. **Optimieren** — iterative Local Search räumt Verstöße und Ungleichheiten nachträglich auf
3. **Prüfen** — rein diagnostisch: färbt Überlast/Unterlast (Tagesheader) und Abstandregel-Verstöße (orange) ein, ohne etwas zu verändern

##### Einordnung in die Literatur

Das Problem ist ein **RCPSP** (Resource-Constrained Project Scheduling Problem) — klassische OR-Formulierung für Aufgaben mit Abhängigkeiten und begrenzter Kapazität pro Zeiteinheit. Gleiches Muster wie agile Sprint-Planung: Punkte auf Sprints verteilen, Abhängigkeiten respektieren, Kapazitäten einhalten.

Bewährte Ansätze:

* **Serial/Parallel Schedule Generation Schemes (SGS)** — Kolisch (1996), Grundlage heuristischer RCPSP-Löser. Unser Generator folgt diesem Schema.
* **Iterative Local Search / Hill Climbing mit Best-Improvement** — Standard-Repair-Verfahren, wenn eine heuristische Erstbelegung vorliegt. Das ist der Optimierer.
* Alternativen wie Genetische Algorithmen oder Simulated Annealing wären overkill für die typische Problemgröße (10–20 Abende, 30–60 Elemente) und schwerer nachvollziehbar.

##### Gewählter Optimierungs-Algorithmus: Best-Improvement Hill Climbing

**Warum dieser Algorithmus:**

* **Deterministisch** — gleicher Input → gleicher Output, einfach zu debuggen
* **Konvergiert garantiert** — da jeder Schritt Kosten strikt senkt, endet das Verfahren spätestens, wenn kein verbessernder Move mehr existiert (lokales Optimum)
* **Nachvollziehbar** — jede Move-Entscheidung lässt sich im Zweifel als „dieses Element von Tag i auf Tag k, weil Kosten von X auf Y sinken" erklären
* **Respektiert Nutzerarbeit** — arbeitet auf dem *aktuellen* Plan weiter (inkl. manueller Drag-Änderungen), nicht auf neu generiertem Plan
* **Schnell genug** — für realistische Klassengrößen (≤20 Abende, ≤60 Items) konvergiert es in Sekundenbruchteilen

**Zielfunktion (Cost):**

```
cost = violations × 10 000   +   Σ (load_i − ∅)²
        └─ Abstandregeln ─┘    └─ Last-Varianz ─┘
```

* Distanz-Verstöße dominieren hart (Faktor 10 000) — werden *zuerst* aufgelöst, auch wenn die Last dadurch kurz unausgewogener wird
* Last-Varianz (quadratische Abweichung vom Tagesdurchschnitt) darunter glatt und monoton — bevorzugt Moves, die Ausreißer nach oben *und* unten reduzieren

**Pro Iteration:**

1. Alle legalen Einzel-Moves (Element von Tag i → Tag k) enumerieren
2. Kosten für jeden Probe-Move berechnen (Move anwenden → Cost → rückgängig)
3. Den kostensenkendsten Move festhalten, nach der Schleife anwenden
4. Abbruch, sobald keine Iteration mehr eine Verbesserung findet (max. 200 Iterationen als Safety-Net)

**Harte Constraints bei Legalitäts-Check** (`_can_move`):

* Teach-Move: alle Voraussetzungen müssen genug früh liegen (`to_k > teach[prereq] + delay`), alle Nachfolger genug spät (`teach[succ] > to_k + delay`), alle Repeats dieser Figur nach `to_k`
* Repeat-Move: Ziel-Tag muss nach dem Teach liegen, und kein zweiter Repeat derselben Figur darf am selben Tag stehen
* Info-Move: keine Constraints, frei verschiebbar

**Bewusste Beschränkung:**

* Nur **Single-Item-Moves**, keine Swaps oder Ketten-Moves. Single-Moves reichen für die typische Problemgröße und halten den Code klar. Bei komplexeren Fällen (viele Zwangsbedingungen gleichzeitig) kann der Optimierer in lokalen Optima steckenbleiben — dann genügt meist ein manuelles Drag und ein zweiter Optimize-Klick.

##### Visuelles Feedback

| Einfärbung               | Bedeutung                                                          |
|--------------------------|--------------------------------------------------------------------|
| Roter Tagesheader        | Überlast — Tag > 125 % des Durchschnitts                           |
| Blauer Tagesheader       | Unterlast — Tag < 75 % des Durchschnitts                           |
| **Orange** Element-Text  | Abstandregel verletzt (Prereq-Delay nicht eingehalten)             |

Überlast/Unterlast wird automatisch nach jeder Änderung aktualisiert. Abstandregel-Check ebenfalls, aber der „Prüfen"-Button erlaubt explizites Auslösen zur Sicherheit.

### 10.2 Dreispaltiger Aufbau

Der Class-Designer soll nach aktuellem Stand **dreispaltig** aufgebaut sein.

#### Linke Spalte

Enthält die Grundlagen und Ausgangsdaten, insbesondere:

* Auswahl des Tanzprogramms
* Anzahl der Abende
* Liste **aller Figuren** aus der Teaching Order des gewählten Programms (vollständig, als Referenz — nicht als Auswahlliste)
* Figuren bleiben in Spalte 1 sichtbar, auch wenn sie in Spalte 2 übernommen wurden

Zusätzlich soll sich **unten links** eine Funktion zum **Laden** befinden.

Für den Übergang von Spalte 1 nach Spalte 2 soll es eine explizite Funktion geben:

* **Teaching Order kopieren**

Bedeutung:

* Die in Spalte 1 sichtbare Teaching Order bzw. Figurenbasis kann damit gezielt in die mittlere Spalte übernommen werden.
* Dieser Schritt ist ein bewusster Übergang von der Quelle in den Bearbeitungsbereich.

#### Mittlere Spalte

Enthält alle Inhalte, die in die Planung übernommen und anschließend verteilt werden sollen.

Dazu gehören insbesondere:

* ausgewählte Figuren
* zusätzliche freie Elemente, die nicht in der Teaching Order enthalten sind, aber fachlich relevant sind
* weitere Inhalte, die für die Class berücksichtigt werden sollen

Beispiel für zusätzliche freie Elemente:

* Right Shoulder Passing Rule

Wichtig:

* **Trenner gehören nicht in die mittlere Spalte**.
* Die mittlere Spalte dient als **Sammelbereich der zu verteilenden Inhalte und Regeln**.
* Die mittlere Spalte ist zugleich der **zentrale Bearbeitungsbereich** für die Eigenschaften der Planelemente.

In Spalte 2 sollen die Elemente also nicht nur gesammelt, sondern auch direkt bearbeitet werden können.

#### Struktur der mittleren Spalte

Die mittlere Spalte soll **hierarchisch aufgebaut** sein.

Grundstruktur:

* oberste Ebene: Figuren bzw. Info-Elemente
* darunter bei Figuren: zugehörige Vorgängerfiguren mit ihrem jeweiligen Abstand

Beispiel:

* Figur A
  * Vorgängerfigur X, Abstand 2 Abende
  * Vorgängerfigur Y, Abstand 1 Abend

Ziel:

* Abhängigkeiten sollen direkt im Kontext der jeweiligen Figur sichtbar sein.
* Die Struktur soll nicht nur in Dialogen, sondern auch in der Darstellung der Liste nachvollziehbar sein.

Bearbeitbare Inhalte in Spalte 2 sind insbesondere:

* Aufwand einer Figur
* Abhängigkeiten einer Figur
* erforderliche Abstände zu Vorgängerfiguren
* Anzahl bewusster Wiederholungen nach dem Teaching
* Eingabe und Bearbeitung freier Info-Texte
* Aufwand von Info-Elementen

Für die Bearbeitung soll sich vorzugsweise ein **modaler Dialog** öffnen.

Begründung:

* Figuren und Info-Elemente besitzen unterschiedliche Eingabefelder.
* Ein modaler Dialog ermöglicht eine klare und jeweils passende Eingabemaske je Elementtyp.

Daraus folgt:

* Für **Figuren** soll der Dialog andere bzw. umfangreichere Felder anzeigen als für **Info-Elemente**.
* Die Bearbeitungslogik darf also **elementtypabhängig unterschiedlich ausgeprägt** sein.

Für die mittlere Spalte sollen außerdem eigene Funktionen zum **Laden** und **Speichern** vorgesehen werden.

#### Ein- und ausklappbare Hierarchie in Spalte 2

Die hierarchische Darstellung in Spalte 2 soll **ein- und ausklappbar** sein.

Ziel:

* bei vielen Figuren und Abhängigkeiten die Übersicht behalten
* bei Bedarf nur die gerade relevanten Unterpunkte anzeigen

Ziel der Speicherung:

* Die zusammengestellten und konfigurierten Inhalte der mittleren Spalte sollen unabhängig gespeichert und später wieder geladen werden können.

Als Speicherformat ist aktuell **JSON** vorgesehen.

Wichtig:

* Speicherstände der mittleren Spalte dürfen **nicht versehentlich mit Speicherständen der rechten Spalte verwechselt oder kreuzweise geladen** werden.
* Dafür soll eine klare Typisierung bzw. Erkennung des Dateiinhalts vorgesehen werden.

#### Rechte Spalte

Enthält den automatisch erzeugten **Endplan** der gesamten Class.

Darin sollen insbesondere erscheinen:

* neu zu teachende Figuren
* Wiederholungen bereits eingeführter Figuren
* zusätzliche freie Elemente
* Trenner zwischen einzelnen Abenden bzw. Tagen

Wichtig:

* Rechts soll **der komplette Class-Plan** erscheinen, also alles, was später tatsächlich in der Class berücksichtigt wird.
* Der automatisch erzeugte Plan soll **nachträglich manuell anpassbar** sein.
* Die Automatik liefert also einen **Vorschlag**, der vom Nutzer weiter bearbeitet werden kann.

#### Struktur der rechten Spalte

Die rechte Spalte soll ebenfalls **hierarchisch bzw. eingerückt strukturiert** dargestellt werden.

Grundstruktur:

* oberste Ebene: Tage bzw. Class-Abende
* darunter: die zu diesem Tag gehörenden Inhalte

Zu den Inhalten eines Tages gehören insbesondere:

* Figuren
* Wiederholungen
* Infos

Ziel:

* Jeder Abend soll als klar abgegrenzter Block erkennbar sein.
* Die zugehörigen Inhalte sollen sichtbar diesem Abend untergeordnet sein.

#### Manuelle Bearbeitung in der rechten Spalte

Die Inhalte der rechten Spalte sollen manuell verschoben werden können.

Wichtig:

* Verschiebungen sollen **nicht nur innerhalb eines Tages**, sondern auch **über Tagesgrenzen hinweg** möglich sein.

#### Dynamische Aktualisierung des Tagesaufwands

Wenn Inhalte in der rechten Spalte verändert oder zwischen Tagen verschoben werden, soll die **Aufwandssumme des betroffenen Tages automatisch aktualisiert** werden.

Beispiel für die Anzeige:

* `Day 8 (31 Points)`

#### Kennzahlen unter Spalte 3

Unterhalb der rechten Spalte sollen zusammenfassende Kennzahlen angezeigt werden:

* **Gesamtsumme** aller Aufwandspunkte
* **Durchschnitt** der Aufwandspunkte pro Abend
* **Minimum** der Aufwandspunkte eines Abends
* **Maximum** der Aufwandspunkte eines Abends

#### Ein- und ausklappbare Hierarchie in Spalte 3

Auch die hierarchische Darstellung in Spalte 3 soll **ein- und ausklappbar** sein.

Für den Übergang von Spalte 2 nach Spalte 3 soll es eine explizite Funktion geben:

* **Plan erzeugen**

Bedeutung:

* Aus den in Spalte 2 zusammengestellten und konfigurierten Inhalten wird damit der vollständige Class-Plan in Spalte 3 erzeugt.
* Die Planerzeugung erfolgt also nicht permanent automatisch bei jeder Änderung, sondern bewusst auf Anforderung.

Für die rechte Spalte sollen ebenfalls eigene Funktionen zum **Laden** und **Speichern** vorgesehen werden.

Als Speicherformat ist aktuell ebenfalls **JSON** vorgesehen.

### 10.3 Sprache

* Das Tool ist **zweisprachig** (Deutsch / Englisch).
* Es wird auf dieselbe `translations.json` wie Callers Caddy zugegriffen.
* Die Sprachauswahl folgt der bestehenden Logik (INI-Einstellung).

### 10.4 Dateiablage

* Saves der mittleren Spalte (Planungsstand) und rechten Spalte (Endplan) liegen im Unterordner **`class_designer/`** im App-Verzeichnis.
* Der Ordner wird beim ersten Start automatisch angelegt.

### 10.5 Dateitypen und Schutz vor Verwechslung

Beide Spalten speichern als JSON, sind aber klar getrennt:

* Mittlere Spalte: `"type": "class_plan_config"` im JSON-Root
* Rechte Spalte: `"type": "class_plan_result"` im JSON-Root
* Beim Laden wird der Typ geprüft — falsches Format → Fehlermeldung, kein Laden
