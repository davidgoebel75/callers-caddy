# Player Redesign — Designanalyse & Notizen

Referenz-Mockup: Favorit aus Claude Design Session (gespeichert als `player_redesign_mockup.png` in `1_Source/docs/`)

---

## Was das Mockup zeigt

### 1. Player-Karte (obere Sektion)
- Abgerundete dunkle Karte (fast schwarz, leicht blau-grau) als Container
- **"No file loaded"** als Subtitle oben links in der Karte
- **Zeitanzeige**: Große, monospace-artige Schrift `01:42.18 / 03:18.00`
  - Position links, dominant — das Herzstück der Karte
  - Aktuelle Zeit **weiß/hell + fett**, Gesamtzeit **gedimmt/grau**
- **Fortschrittsbalken**: Schmal, mit rundem Thumb-Slider (hell, weiß)
  - Volle Breite der Karte
- **7 Sektionsbuttons** (Singing-Call-Segmente):
  - Labels: `0 · 1 · 2 · M · 3 · 4 · C`
  - Jeder Button eine eigene Farbe (pastellig, gedämpft):
    - 0: blau-grau
    - 1: türkis/teal
    - 2: orange/amber (im Mockup aktiv/selected)
    - M: grün
    - 3: hellblau/lavendel
    - 4: lachs/rosa
    - C: koralle/rot
  - Aktiver Button: kräftiger/gesättigter, leicht hervorgehoben
  - Buttons gleichmäßig über die volle Breite verteilt, abgerundet (pill-shape)

### 2. Transport-Buttons (unter der Karte)
- **Play**: Großer violetter/lila Balken-Button (volle Breite), Icon `▶ Play`
  - Dominante Call-to-Action, abgerundet
  - Hintergrundfarbe: kräftiges Lila/Violett (#7C5CBF-Bereich)
- **Pause / Stop / Fade**: Drei gleichbreite Buttons in einer Zeile darunter
  - Dunkler Hintergrund, hellgrauer Text
  - Icons davor: `⏸ Pause`, `■ Stop`, `◄ Fade`
  - Gleiche Größe, abgerundet

### 3. MIX-Sektion (unterer Bereich — optional)
- Label "MIX" als Sektions-Überschrift (der User findet dieses Label entbehrlich)
- Spin-Boxen für Today's Tempo / Song Tempo / Pitch
- Slider für Live Vol
- → **Kann so bleiben wie bisher oder minimaler gestaltet werden**

---

## Was dem User gefällt (Prioritätsliste)

1. **Sektionsbuttons**: Farbcodierung der 7 Segmente (0,1,2,M,3,4,C), jede Sektion eigene Farbe, pill-förmig, aktiver Button hebt sich ab
2. **Zeitanzeige**: Groß, dominant, zweiteilig (aktuelle/gesamt) mit Kontrast zwischen hell und gedimmt
3. **Play-Button**: Breiter, farbiger (lila) Balken — klar als Haupt-CTA erkennbar
4. **Fortschrittsbalken**: Schmal, mit sauberem Thumb
5. **Gesamte Player-Karte**: Einheitlicher dunkler Container

---

## Was NICHT übernommen werden muss

- Label "MIX" ist optional / entbehrlich
- 3 "Modes" im Mockup sind nicht Teil von Callers Caddy
- Exakte Farben müssen nicht 1:1 stimmen — Stil/Feeling zählt

---

## Offene Entscheidungen / Fragen

- Sektionsfarben: Feste Palette vorbelegen oder konfigurierbar?
- Play-Button-Farbe: Lila beibehalten oder an Theme anpassen?
- Karte vs. flat: Klare abgerundete Karte (wie Mockup) oder flaches Layout?
- Dark-Mode only oder auch hell?

---

## Technische Umsetzungshinweise (PySide6)

- Sektionsbuttons: `QPushButton` mit `setStyleSheet`, Farbliste als Konstante definieren
- Aktiv-Markierung: `setChecked` + checked-State in Stylesheet
- Play-Button: Volle Breite via `setSizePolicy(Expanding, Fixed)`, feste Mindesthöhe (~48px)
- Fortschrittsbalken: `QSlider` mit custom Stylesheet (Groove + Handle)
- Karte: `QFrame` mit `border-radius` und dunklem Hintergrund
- Zeitanzeige: `QLabel` mit HTML-Formatierung oder zwei Labels (aktuelle Zeit / Gesamtzeit)
