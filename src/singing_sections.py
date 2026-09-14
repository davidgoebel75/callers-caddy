"""Erkennt die 7 Abschnitte eines Singing Calls im Lyric-Text (BL-161, Stufe B).

GUI-frei und ohne Qt-/main-Abhaengigkeiten, damit eigenstaendig testbar (vgl.
zip_import). Die Anbindung an QTextDocument, Sync-Anker und DB erfolgt in main.py.

Hintergrund
-----------
Ein Singing Call besteht aus 7 gleich langen Teilen (je 64 Beats):

    1 Opener · 2 Figure · 3 Figure · 4 Middle Break · 5 Figure · 6 Figure · 7 Closer

Die ZEITEN der 7 Teile liefert Stufe A (Siebtelung Start..Ende). Dieses Modul
findet die zugehoerigen TEXT-Bloecke (erste/letzte Zeile je Teil) anhand der
Ueberschriften im Lyric ("OPENER", "FIGURE", "MIDDLE BREAK", "CLOSER" ...).

Besonderheiten aus den echten Lyrics (2_Test/lyrics, 447/467 Dateien mit
erkennbaren Ueberschriften):
- Kombinierte Ueberschriften = geteilter Text: "OPENER - MIDDLE BREAK - CLOSER"
  weist denselben Block den Teilen 1, 4 und 7 zu. Trenner: - / , & + : Leerzeichen.
- Figure-Paarung: "FIGURE 1, 4" / "FIGURE 2, 3" — Figuren teilen sich Text nach
  Inhalt, nicht stur 1/2/3/4. Figur-Ordinalzahl -> Teil: {1:2, 2:3, 3:5, 4:6}.
- "Tag" ist ueberladen: der Outro-Abschnitt (ganze Zeile "TAG") vs. Calls wie
  "Tag the Line", "1/2 Tag", "3/4 Tag". Nur die nackte Zeile "TAG" (ohne Ziffern,
  ohne Begleitwoerter) gilt als Outro — alles andere ist ein Call.

Pflegbare Wissensbasis: Standard-Keywords leben im Code (DEFAULT_SECTIONS), eine
optionale User-JSON enthaelt nur das Delta. load_lists()/save_lists() mergen
analog zu zip_import.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from typing import Optional

# ---------------------------------------------------------------------------
# Pflegbare Listen: Standard-Keywords (im Code). User-Overrides in der JSON.
# ---------------------------------------------------------------------------

# Keyword-Gruppe -> Liste von Schluesselwoertern (Grossbuchstaben, wie im Text
# nach Normalisierung). Mehrwort-Keywords ("MIDDLE BREAK") sind erlaubt.
DEFAULT_SECTIONS = {
    "opener": ["OPENER", "OPEN"],                      # -> Teil 1
    # "MIDLE" ist ein Tippfehler, der real auf Cuesheets steht (z.B. RYL 225
    # "OPENER - MIDLE BREAK - CLOSER"). Weil eine Ueberschrift nur zaehlt, wenn
    # ALLE ihre Woerter bekannt sind, kippt ein einziger Typo die ganze Zeile.
    "break":  ["MIDDLE BREAK", "MIDDLE", "MIDLE", "BREAKS", "BREAK"],  # -> Teil 4
    "closer": ["CLOSER", "CLOSING", "CLOSE", "ENDING", "ENDER"],  # -> Teil 7
    "figure": ["FIGURE", "SEQUENCE"],                  # -> Teile 2/3/5/6
    "intro":  ["INTRO"],                               # vor Teil 1 (nur Info)
    "tag":    ["TAG"],                                 # Outro -> extras["tag"]
    # Alternativer Figurentext ausserhalb des 7er-Rasters. Wichtig ist weniger
    # der eigene Block als die Abgrenzung: ohne diese Ueberschrift wandert der
    # Text in den davorstehenden Abschnitt (meist OPENER) und verlaengert ihn
    # faelschlich, weil ein Block bis zur naechsten Ueberschrift reicht.
    "additional": ["ADDITIONAL LYRICS", "ADDITIONAL",
                   "ALTERNATE LYRICS", "ALTERNATE"],   # -> extras["additional"]
}

# Figur-Ordinalzahl (1..4) -> kanonischer Teil im 7er-Schema.
FIGURE_ORDINAL_TO_PART = {1: 2, 2: 3, 3: 5, 4: 6}

# Schnitt-Signale fuer das Figuren-Ende (BL-200). Ein FIGURE-Block endet in vielen
# Cuesheets nicht mit dem letzten Tanz-Call, sondern hat danach 1-2 Zeilen reinen
# Gesangstext (laeuft, waehrend die Taenzer nach Hause promenieren). Die LETZTE
# Zeile mit einem dieser Woerter ist die Heimschick-Zeile ("...and promenade");
# alles danach im Block ist geschuetzter Gesangstext, den Dynamic Lyrics NICHT
# ersetzen soll. Bewusst NICHT Teil von DEFAULT_SECTIONS: diese Woerter duerfen
# die Ueberschriften-Erkennung (classify_heading/_keyword_words) nicht beeinflussen.
# `swing` allein bleibt aussen vor (ist ein Call: "swing thru"). "HOME" ist als
# Signal bewusst NICHT dabei: in einer Batch-Gegenprobe ueber alle echten Lyrics
# (2_Test/lyrics, 403 Figuren-Bloecke) erzeugte "home" nur False-Cuts (es steht
# fast immer im Songtext: "back home in Nashville" o. Kuerzel "Go Home"), waehrend
# "promenade" allein sauberer traf (95,8 % vs. 94,0 %, 0 statt 7 Fehlschnitte).
# Wer "HOME" o. a. dennoch will, ergaenzt es per User-Delta (load_sections-JSON).
DEFAULT_FIGURE_TAIL_CUT = ["PROMENADE"]

# Maximale Zeilenlaenge, ab der eine Zeile sicher KEINE Ueberschrift mehr ist.
MAX_HEADING_LEN = 40

# Geklammertes Praefix-Label am Zeilenanfang: "(Opener): SIDES FACE GRAND SQUARE"
# oder "(Middle Break & Closer): ...". Die STING-Blaetter setzen das Label in
# Klammern an den Zeilenanfang und schreiben den ersten Call auf DIESELBE Zeile —
# damit greift weder die Laengengrenze noch der "alle Woerter sind Keywords"-Test.
# Die Klammern sind hier Pflicht: sie sind das Signal, das ein Label von einer
# Liedzeile trennt. Ohne sie waere "Break: ..." aus einem Songtext ein Fehlalarm.
PAREN_LABEL_RE = re.compile(r"^\(\s*([^()]{1,40}?)\s*\)\s*:")


@dataclass
class SectionResult:
    """Ergebnis der Abschnitts-Erkennung.

    parts:    {teil(1..7): (start_char, end_char)} — Zeichenpositionen der ersten
              bzw. letzten Block-Zeile im uebergebenen Plain-Text.
    detected: Teile, die direkt aus einer Ueberschrift kamen.
    filled:   Teile, die per Fallback aus einem anderen Block ergaenzt wurden.
    extras:   {"tag"|"additional": (start_char, end_char)} — Abschnitte ausserhalb
              des 7er-Rasters. Bewusst NICHT in parts: die Zeiten der 7 Teile
              entstehen durch Siebtelung von Start..Ende, dort haben diese beiden
              keinen Platz. Der Tag liegt zeitlich hinter dem Ende, Additional
              Lyrics laufen ueberhaupt nicht im Raster mit.
    """
    ok: bool
    parts: dict = field(default_factory=dict)
    detected: set = field(default_factory=set)
    filled: set = field(default_factory=set)
    extras: dict = field(default_factory=dict)
    reason: str = ""


def _keyword_words(sections: dict) -> set:
    """Alle Einzelwoerter aller Keywords — fuer den 'saubere Ueberschrift'-Test."""
    words = set()
    for kws in sections.values():
        for kw in kws:
            for w in re.findall(r"[A-Z]+", kw.upper()):
                words.add(w)
    return words


def classify_heading(line: str, sections: dict, kw_words: set) -> Optional[dict]:
    """Prueft, ob `line` eine Abschnitts-Ueberschrift ist, und welche Teile sie
    benennt. Rueckgabe None = keine Ueberschrift.

    Eine Zeile gilt nur dann als Ueberschrift, wenn ALLE ihre Buchstaben-Tokens
    bekannte Keyword-Woerter sind (so fliegen Liedzeilen wie "Return to Sender"
    oder "Tag the line" raus) und mindestens ein Abschnitt erkannt wird.
    """
    raw = line.strip()
    if not raw:
        return None
    U = re.sub(r"\s+", " ", raw.upper())
    m = PAREN_LABEL_RE.match(U)
    if m:
        # Geklammertes Praefix-Label: nur der Klammerinhalt ist das Label, der
        # Rest der Zeile ist bereits Inhalt (Calls) und wird nicht mitgeprueft.
        label = m.group(1).replace(":", " ").strip()
    else:
        # Angehaengte Annotation nach einer groesseren Luecke abtrennen. Viele
        # Blaetter (z.B. ceder.net) setzen hinter die Ueberschrift nach mehreren
        # geschuetzten Leerzeichen das Tanzprogramm bzw. eine Beschreibung:
        # "OPENER - MIDDLE BREAK - CLOSER   Mainstream" oder
        # "FIGURE   Plus, corner progression". Diese Luecke (2+ Whitespace, das
        # \s deckt in Python-Strings auch \xa0/Tabs ab) trennt Label von
        # Annotation — sonst kippt ein einziges Fremdwort (MAINSTREAM, PLUS,
        # CORNER ...) den "alle Woerter sind Keywords"-Test und die ganze Zeile
        # faellt raus. Auf dem Rohtext splitten, da U die Luecke bereits zu
        # einem Leerzeichen zusammengezogen hat.
        raw_label = re.split(r"\s{2,}", raw, maxsplit=1)[0]
        # Beschreibende Zusaetze abtrennen: alles ab der ersten '(' faellt weg
        # ("FIGURE (twice for heads, twice for sides)" -> Label "FIGURE").
        # Doppelpunkte sind mal Trenner ("OPENER: BREAK: CLOSER"), mal
        # Endezeichen ("TAG:") — daher ersetzen statt splitten.
        label = re.sub(r"\s+", " ", raw_label.upper())
        label = label.split("(", 1)[0].replace(":", " ").strip()
        # Laengenpruefung ERST auf dem bereinigten Label. Vorher lief sie auf
        # der Rohzeile und verwarf genau die Faelle, die der Schnitt oben
        # retten sollte: "FIGURE (twice for heads, twice for sides):" ist 42
        # Zeichen lang, das Label danach nur 6.
        if len(label) > MAX_HEADING_LEN:
            return None
    tokens = re.findall(r"[A-Z]+", label)
    if not tokens or any(t not in kw_words for t in tokens):
        return None

    parts: set = set()
    figure = None  # None=keine Figur, 'all'=alle Figuren, sonst set(ordinals)

    def has(group):
        for kw in sections.get(group, []):
            if re.search(r"\b" + re.escape(kw.upper()) + r"\b", label):
                return True
        return False

    if has("opener"):
        parts.add(1)
    if has("break"):
        parts.add(4)
    if has("closer"):
        parts.add(7)
    if has("figure"):
        ordinals = {int(d) for d in re.findall(r"[1-4]", label)}
        figure = ordinals if ordinals else "all"

    # Outro-Tag: nur das nackte Label "TAG" (keine Ziffern, keine Begleitwoerter)
    is_tag = (re.sub(r"[^A-Z]", "", label) == "TAG" and not re.search(r"\d", label)
              and has("tag"))
    # INTRO am Stueckanfang ist faktisch der Opener (Teil 1) — viele Blaetter
    # schreiben "INTRO - MIDDLE BREAK - ENDING" statt "OPENER - ...". Steht spaeter
    # ein echtes OPENER, ueberschreibt dessen Block den Intro-Block (Reihenfolge).
    is_intro = has("intro")
    if is_intro:
        parts.add(1)

    # Additional/Alternate Lyrics: eigener Abschnitt ohne Platz im 7er-Raster.
    # Muss trotzdem als Ueberschrift durchgehen, sonst haengt sein Text am
    # Vorgaenger-Block (siehe Kommentar bei DEFAULT_SECTIONS["additional"]).
    is_additional = has("additional")
    if is_additional:
        # Ein "ALTERNATE/ADDITIONAL ..."-Block liegt AUSSERHALB des 7er-Rasters.
        # Auch wenn die Ueberschrift OPENER/BREAK/CLOSER/FIGURE nennt (z.B.
        # "ALTERNATE OPENER - BREAK - CLOSER"), darf er die echten Abschnitte
        # NICHT beanspruchen/ueberschreiben — sonst springt die App auf den
        # Alternativ-Opener statt auf den echten (Sea Of Heartbreak).
        parts = set()
        figure = None
        is_tag = False
        is_intro = False

    if not parts and figure is None and not is_tag and not is_additional:
        return None
    return {"parts": parts, "figure": figure, "tag": is_tag,
            "intro": is_intro, "additional": is_additional}


def figure_call_end_line(lines: list, start_line: int, end_line: int,
                         tail_cut: Optional[list] = None) -> int:
    """Liefert fuer einen Figuren-INHALTSBEREICH (start_line..end_line, beides
    Inhaltszeilen ohne die FIGURE-Ueberschrift) den Index der letzten Tanz-Call-
    Zeile (BL-200, Option B). Zeilen NACH diesem Index bis `end_line` sind
    angehaengter Gesangstext (laeuft waehrend der Heim-Promenade) und sollen bei
    Dynamic Lyrics erhalten bleiben.

    `lines`      : alle Plain-Text-Zeilen (wie aus _lines_with_offsets / split).
    `start_line` : erste Inhaltszeile des Figuren-Blocks (== Kopfzeile + 1).
    `end_line`   : letzte Inhaltszeile des Figuren-Blocks (inklusive).
    `tail_cut`   : Schnitt-Signale (Default DEFAULT_FIGURE_TAIL_CUT).

    Heuristik (Pareto/80%): vom Blockende RUECKWAERTS die letzte nicht-leere Zeile
    mit einem Schnitt-Signal (Default PROMENADE) suchen. Nur schneiden, wenn
    (a) so eine Zeile existiert, (b) danach noch mind. eine nicht-leere Zeile folgt
    und (c) die Schnittzeile nicht die erste Inhaltszeile ist (sonst waere praktisch
    der ganze Block Gesangstext). Sonst `end_line` zurueckgeben = KEIN Trim; der
    Block bleibt unveraendert (kein Schaden bei atypischen Sheets).

    GUI-frei und einzeln testbar; die Blockgrenzen/Sync-Anker bleiben davon
    unberuehrt — nur der Ersetzungsbereich in _dynamic_build_document wird kuerzer.
    """
    tail_cut = tail_cut if tail_cut is not None else DEFAULT_FIGURE_TAIL_CUT
    if not tail_cut or start_line < 0 or end_line >= len(lines) \
            or start_line > end_line:
        return end_line
    pattern = re.compile(
        r"\b(?:" + "|".join(re.escape(w) for w in tail_cut) + r")\b",
        re.IGNORECASE)
    for idx in range(end_line, start_line - 1, -1):
        if not lines[idx].strip():
            continue  # Leerzeilen sind kein Tail-Signal
        if pattern.search(lines[idx]):
            has_tail = any(lines[k].strip() for k in range(idx + 1, end_line + 1))
            if has_tail and idx > start_line:
                return idx
            return end_line  # Block endet auf Promenade / Promenade ist Zeile 1
    return end_line


def _lines_with_offsets(plain_text: str):
    """Zerlegt Plain-Text in (char_offset, zeilentext). Der char_offset stimmt mit
    der QTextDocument-Position der Zeile ueberein (Block-Grenze == 1 Zeichen)."""
    out = []
    pos = 0
    for raw in plain_text.split("\n"):
        out.append((pos, raw))
        pos += len(raw) + 1
    return out


def parse_sections(plain_text: str, sections: Optional[dict] = None) -> SectionResult:
    """Findet die 7 Teil-Bloecke im Lyric-Plain-Text.

    Liefert je Teil (start_char, end_char) = Zeichenposition der ersten und der
    letzten Inhaltszeile des Blocks. Mehrere Teile koennen denselben Block teilen.
    """
    sections = sections or DEFAULT_SECTIONS
    kw_words = _keyword_words(sections)
    lines = _lines_with_offsets(plain_text)

    line_cls = [classify_heading(raw, sections, kw_words) for (_c, raw) in lines]

    # Aufeinanderfolgende Ueberschriftszeilen zu EINER Gruppe zusammenfassen.
    # Noetig, weil ein Zeilenumbruch eine kombinierte Ueberschrift zerreissen kann
    # ("OPENER - MIDDLE BREAK - CLOSER" -> "OPENER - MIDDLE" + "BREAK - CLOSER").
    # Die Gruppe vereinigt alle Teile/Figuren; ihr Block ist der Text danach.
    groups = []  # (parts:set, figure, hstart_line, hend_line, extras:set)
    i, n = 0, len(lines)
    while i < n:
        if line_cls[i] is None:
            i += 1
            continue
        j = i
        while j + 1 < n and line_cls[j + 1] is not None:
            j += 1
        m_parts, m_fig, m_extra = set(), None, set()
        for k in range(i, j + 1):
            c = line_cls[k]
            m_parts |= c["parts"]
            if c.get("tag"):
                m_extra.add("tag")
            if c.get("additional"):
                m_extra.add("additional")
            if c["figure"] is not None:
                if c["figure"] == "all" or m_fig == "all":
                    m_fig = "all"
                else:
                    m_fig = (m_fig or set()) | c["figure"]
        groups.append((m_parts, m_fig, i, j, m_extra))
        i = j + 1

    if not groups:
        return SectionResult(ok=False, reason="no_headings")

    part_blocks = {}
    detected = set()
    figure_blocks = []
    naked_figure_blocks = []  # #67: nackte "FIGURE"-Bloecke, Zuordnung nach Schleife
    extras = {}

    for gi, (m_parts, m_fig, hstart, hend, m_extra) in enumerate(groups):
        start_line = hend
        end_line = groups[gi + 1][2] if gi + 1 < len(groups) else n
        content = [k for k in range(start_line + 1, end_line) if lines[k][1].strip()]
        if not content:
            continue
        blk = (lines[hstart][0], lines[content[-1]][0])
        # Abschnitte ausserhalb des Rasters. Dass sie ueberhaupt als Gruppe
        # zaehlen, begrenzt schon den Vorgaenger-Block (end_line oben) — auch
        # dann, wenn hier gar nichts eingetragen wird.
        for name in m_extra:
            extras[name] = blk
        # Explizite Teile (Opener/Break/Closer/Intro) — letzte Nennung gewinnt
        for p in m_parts:
            part_blocks[p] = blk
            detected.add(p)
        # Figuren
        if m_fig is not None:
            figure_blocks.append(blk)
            if m_fig == "all":
                # Nackte "FIGURE"-Ueberschrift (ohne Ordinal): Zuordnung erst NACH
                # der Schleife, wenn die Gesamtzahl der Bloecke bekannt ist (#67).
                naked_figure_blocks.append(blk)
            else:
                for o in m_fig:
                    p = FIGURE_ORDINAL_TO_PART.get(o)
                    if p:
                        part_blocks[p] = blk
                        detected.add(p)

    # --- Nackte FIGURE-Bloecke zuordnen (#67) ---
    # Ein zweiter nackter "FIGURE"-Block blieb bisher unzugeordnet (der erste
    # deckte via setdefault alle vier Slots). Neue Regel:
    #  - GENAU 4 Figure-Bloecke, alle nackt -> Medley: 1:1 auf die Teile 2/3/5/6
    #    (Block 1->2, 2->3, 3->5, 4->6). Jeder Block behaelt seinen eigenen
    #    Extent, sodass die Tail-Erkennung (BL-200) je Block greift.
    #  - sonst (1/2/3 nackte Bloecke) -> wie bisher: der erste deckt alle vier.
    # Explizit nummerierte Figuren ("FIGURE 1, 4") sind oben schon gesetzt und
    # bleiben unangetastet; nackte Bloecke fuellen per setdefault nur Luecken.
    if naked_figure_blocks:
        if len(figure_blocks) == 4 and len(naked_figure_blocks) == 4:
            for blk_f, p in zip(naked_figure_blocks, (2, 3, 5, 6)):
                part_blocks[p] = blk_f
                detected.add(p)
        else:
            first_fig = naked_figure_blocks[0]
            for p in (2, 3, 5, 6):
                part_blocks.setdefault(p, first_fig)
                detected.add(p)

    # --- Auffuellen NUR innerhalb der Figuren ---
    # Eine erkannte Figur wird im Singing Call 4x getanzt. Sind nicht alle vier
    # Figur-Teile direkt benannt (z.B. nur "FIGURE 1, 4"), fuellen wir die
    # restlichen aus der ersten gefundenen Figur. Es werden KEINE Bloecke aus
    # fremden Abschnitten erfunden: fehlt z.B. die Figur ganz, bleiben 2/3/5/6
    # offen — main.py haelt die Anzeige dann an Ort und Stelle ("kein Sprung"),
    # statt falschen Text einzublenden.
    filled = set()

    # --- Auffuellen der Break-Positionen (Opener 1 / Middle 4 / Closer 7) ---
    # Diese drei teilen sich im Singing Call denselben Break-Text und werden 3x
    # getanzt. Viele Cuesheets labeln nur ein einziges "BREAK" (ohne eigenes
    # OPENER/CLOSER) und meinen damit alle drei. Gibt es also irgendeinen
    # Break-Block, fuellen wir die fehlenden der drei Positionen daraus — analog
    # zur Figur-Fuellung. So wird "BREAK + FIGURE + TAG" korrekt erkannt, statt
    # an der fehlenden Opener-Ueberschrift zu scheitern.
    break_block = next((part_blocks[p] for p in (4, 1, 7) if p in part_blocks),
                       None)
    if break_block is not None:
        for p in (1, 4, 7):
            if p not in part_blocks:
                part_blocks[p] = break_block
                filled.add(p)

    if figure_blocks:
        fig_default = figure_blocks[0]
        for p in (2, 3, 5, 6):
            if p not in part_blocks:
                part_blocks[p] = fig_default
                filled.add(p)

    # Mindestabdeckung: ohne Opener-Block gibt es keinen sinnvollen Startpunkt.
    if 1 not in part_blocks:
        return SectionResult(ok=False, reason="no_opener", parts=part_blocks,
                             detected=detected, filled=filled, extras=extras)

    return SectionResult(ok=True, parts=part_blocks, detected=detected,
                         filled=filled, extras=extras)


# ---------------------------------------------------------------------------
# Pflegbare User-Liste (Delta), analog zip_import.load_lists/save_lists
# ---------------------------------------------------------------------------

def load_sections(path: Optional[str]) -> dict:
    """Defaults + User-Delta aus path. Das Delta darf je Gruppe 'entries'
    (ersetzt die Gruppe) tragen. Fehlt path/Datei -> reine Defaults."""
    merged = {k: list(v) for k, v in DEFAULT_SECTIONS.items()}
    if path and os.path.isfile(path):
        try:
            with open(path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            groups = data.get("sections", {}) if isinstance(data, dict) else {}
            for grp, val in groups.items():
                if isinstance(val, list):
                    merged[grp] = [str(x).upper() for x in val]
        except (OSError, ValueError):
            pass
    return merged


