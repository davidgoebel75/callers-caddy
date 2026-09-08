"""Cue-Sheet-Suche in Vic Ceders Record-Datenbank (ceder.net).

GUI-frei und ohne Qt-/main-Abhaengigkeiten, damit eigenstaendig testbar — wie
zip_import und singing_sections. Die Anbindung an Tabelle, Fortschritt und
Dateiablage erfolgt in main.py.

Rechtlicher Rahmen
------------------
ceder.net ist "Copyright (c) Vic Ceder. All Rights Reserved.", die Cue Sheets
enthalten zusaetzlich Songtexte der Musikverlage. Geholte Sheets gehoeren in den
lokalen Lyrics-Ordner des Nutzers und DUERFEN NICHT weitergegeben werden — weder
in einem Release-ZIP noch sonstwie. build.py schliesst lyrics/ entsprechend aus.

Umgang mit dem fremden Server
-----------------------------
Es gibt keine robots.txt (Stand 2026-07-20) — das ist keine Erlaubnis, sondern
nur das Fehlen einer Ansage. Deshalb bewusst zurueckhaltend:

- MIN_DELAY Sekunden Mindestabstand zwischen zwei Anfragen, modulweit erzwungen
- sprechender User-Agent mit Programmname und Homepage-URL (callerscaddy.com)
- harte Timeouts (ein haengender Socket darf den Aufrufer nie festhalten)
- Label-Liste wird lokal zwischengespeichert, nicht bei jedem Start geholt
- eine Suche + ein Sheet-Abruf pro Song, keine Massenabfragen im Sekundentakt

Ermittelte Endpunkte (2026-07-20)
---------------------------------
Suche      POST recorddb/view.php
           FindTitle, FindLabelId (ID aus Dropdown!), HasCueSheet, Page, SortBy
Cue Sheet  GET  recorddb/ajax_viewsingle_cuesheet.php?RecordId=N
Lyrics     GET  recorddb/ajax_viewsingle_lyrics.php?RecordId=N
Labelliste GET  recorddb/query.php  (SELECT NAME="FindLabelId")
"""

from __future__ import annotations

import difflib
import html as _html
import json
import os
import re
import threading
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Optional

# i18n ist Qt-frei (nur json/os) — Anzeige-Texte (Confidence, „Warum") werden
# uebersetzt, ohne die GUI-Freiheit dieses Moduls zu brechen.
from i18n import _t

# Gemeinsame Match-Basis (Qt-frei). Titel-Aehnlichkeit, Label/Nummer-Split,
# Query-Normalisierung und der Bewertungskern leben zentral in song_match, damit
# jede Optimierung dort auch hier wirkt (und in der Krabbelkiste-Suche).
import song_match

BASE = "https://www.ceder.net/recorddb/"
MIN_DELAY = 2.0      # Sekunden zwischen zwei Anfragen an ceder.net
TIMEOUT = 20.0       # harte Obergrenze je Anfrage

USER_AGENT = ("CallersCaddy/{ver} (square dance cue sheet lookup; "
              "+https://callerscaddy.com)")

# Modulweite Drossel. Auch wenn mehrere Worker laufen, bleibt der Abstand.
_throttle_lock = threading.Lock()
_last_request = [0.0]


class CederError(RuntimeError):
    """Netz-/Serverproblem — vom Aufrufer als Meldung anzeigbar."""


# ---------------------------------------------------------------------------
# Datenklasse
# ---------------------------------------------------------------------------

@dataclass
class Candidate:
    """Ein Treffer aus der Ergebnisliste."""
    record_id: str
    title: str = ""
    label_name: str = ""
    number: str = ""
    artist: str = ""          # Original-Interpret
    sd_artist: str = ""       # Square-Dance-Interpret
    year: str = ""
    has_cuesheet: bool = False
    has_lyrics: bool = False
    score: int = 0
    reasons: list = field(default_factory=list)

    @property
    def label_full(self) -> str:
        return f"{self.label_name} {self.number}".strip()

    @property
    def confidence(self) -> str:
        """sicher / wahrscheinlich / unsicher — fuer die Anzeige (uebersetzt)."""
        if self.score >= 90:
            return _t("ceder_conf_high")
        if self.score >= 60:
            return _t("ceder_conf_medium")
        return _t("ceder_conf_low")


# ---------------------------------------------------------------------------
# HTTP mit Drossel
# ---------------------------------------------------------------------------

def _agent(version: str = "0.0") -> str:
    return USER_AGENT.format(ver=version)


def _request(url: str, data: Optional[dict] = None,
             version: str = "0.0") -> str:
    """Eine Anfrage, inklusive Mindestabstand. Wirft CederError."""
    with _throttle_lock:
        wait = MIN_DELAY - (time.monotonic() - _last_request[0])
        if wait > 0:
            time.sleep(wait)
        _last_request[0] = time.monotonic()
    body = urllib.parse.urlencode(data).encode() if data else None
    req = urllib.request.Request(
        url, data=body, headers={"User-Agent": _agent(version)})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            raw = r.read()
            enc = r.headers.get_content_charset() or "utf-8"
        return raw.decode(enc, errors="replace")
    except Exception as e:
        raise CederError(str(e)) from e


# ---------------------------------------------------------------------------
# Label-Liste (Name -> ID), lokal zwischengespeichert
# ---------------------------------------------------------------------------

def load_labels(cache_path: str, refresh: bool = False,
                version: str = "0.0") -> dict:
    """{Labelname: ID}. Holt die Liste nur, wenn der Cache fehlt oder refresh."""
    if not refresh and cache_path and os.path.exists(cache_path):
        try:
            with open(cache_path, encoding="utf-8") as f:
                data = json.load(f)
            if data:
                return data
        except Exception:
            pass   # kaputter Cache: neu holen statt scheitern
    html_text = _request(BASE + "query.php", version=version)
    labels = parse_labels(html_text)
    if cache_path and labels:
        try:
            os.makedirs(os.path.dirname(cache_path), exist_ok=True)
            with open(cache_path, "w", encoding="utf-8") as f:
                json.dump(labels, f, ensure_ascii=False, indent=1,
                          sort_keys=True)
        except Exception:
            pass   # Cache ist Beschleunigung, kein Muss
    return labels


def parse_labels(html_text: str) -> dict:
    m = re.search(r'<SELECT[^>]*NAME="FindLabelId".*?</SELECT>',
                  html_text, re.I | re.S)
    if not m:
        return {}
    out = {}
    for val, txt in re.findall(r'<OPTION[^>]*VALUE=["\']?(\d+)["\']?[^>]*>([^<]*)',
                               m.group(0), re.I):
        name = _html.unescape(txt).strip()
        if name and val != "0":
            out[name] = val
    return out


def match_label_id(label_name: str, labels: dict) -> tuple:
    """(id, gefundener_name) fuer einen Labelnamen, sonst (None, '').

    Die Ceder-Liste unterscheidet Faelle wie "Desert" und "Desert Gold",
    deshalb erst exakt, dann case-insensitiv, dann aehnlichkeitsbasiert.
    """
    if not label_name or not labels:
        return (None, "")
    if label_name in labels:
        return (labels[label_name], label_name)
    low = {k.lower(): k for k in labels}
    key = label_name.lower().strip()
    if key in low:
        return (labels[low[key]], low[key])
    near = difflib.get_close_matches(key, list(low), n=1, cutoff=0.88)
    if near:
        return (labels[low[near[0]]], low[near[0]])
    return (None, "")


# ---------------------------------------------------------------------------
# Label-Feld der App zerlegen: "Shakedown 302" -> ("Shakedown", "302")
# ---------------------------------------------------------------------------

# songs.label haelt Name + Nummer zusammen ("Shakedown 302"); die Ceder-Suche
# braucht den Namen fuer die ID und die Nummer fuer die Treffersicherheit. Die
# Zerlegung lebt zentral in song_match — hier nur der Re-Export fuer Aufrufer/Tests.
split_label_number = song_match.split_label_number


# ---------------------------------------------------------------------------
# Suche und Ergebnis-Auswertung
# ---------------------------------------------------------------------------

# Apostroph-/Quote-Vereinheitlichung: ceder.net indexiert Titel mit dem geraden
# Apostroph (U+0027) — eine Suche nach "Don’t" (U+2019, wie er aus Tags/Dateinamen
# in songs.title landet) liefert dort NULL Treffer, "Don't" dagegen den Datensatz.
# Empirisch am Titel "I Think We’re Alone Now" bestaetigt. Die Vereinheitlichung
# lebt zentral in song_match; hier nur der Re-Export.
normalize_query = song_match.normalize_query


def search(title: str = "", label_id: Optional[str] = None,
           only_with_cuesheet: bool = True,
           version: str = "0.0") -> list:
    """Sucht Datensaetze. Mindestens Titel ODER Label muss gesetzt sein."""
    if not title and not label_id:
        return []
    form = {"Page": "1", "SortBy": "title"}
    if title:
        form["FindTitle"] = normalize_query(title)
    if label_id:
        form["FindLabelId"] = str(label_id)
    if only_with_cuesheet:
        form["HasCueSheet"] = "1"
    html_text = _request(BASE + "view.php", data=form, version=version)
    return parse_results(html_text)


def parse_results(html_text: str) -> list:
    """Zerlegt die Trefferseite in Candidate-Objekte.

    Ausgewertet werden die CSS-Klassen der Seite, NICHT Textpositionen: der
    Titel steht im viewsingle-Link, Label und Nummer in <SPAN CLASS="reclabel">
    ("Royal 150"), Typ in "rectype", die SD-Interpreten in "recartist". Ein
    frueherer Versuch ueber Wortabstaende las "Jerry Story Royal 325" als Label
    und schnitt Titel falsch ab — die Klassen sind eindeutig und aendern sich
    seltener als das Layout.

    Label und Nummer sind der Schluessel zur Treffersicherheit: derselbe Titel
    kommt beim selben Label mehrfach mit verschiedenen Nummern vor.
    """
    out, seen = [], set()
    for row in re.findall(r"<TR\b.*?</TR>", html_text, re.I | re.S):
        m = re.search(r"viewsingle\.php\?RecordId=(\d+)", row)
        if not m:
            continue
        rid = m.group(1)
        if rid in seen:
            continue
        seen.add(rid)
        cand = Candidate(record_id=rid)

        # Titel: Text des viewsingle-Links
        tm = re.search(r"<A[^>]+viewsingle\.php\?RecordId=" + rid +
                       r"[^>]*>(.*?)</A>", row, re.I | re.S)
        if tm:
            cand.title = _text(tm.group(1))

        cand.label_name, cand.number = split_label_number(
            _span(row, "reclabel"))
        cand.sd_artist = _span(row, "recartist")
        # Original-Interpret: Link auf die Interpretensuche
        am = re.search(r"FindOriginalArtist=[^\"'>]*[\"'][^>]*>(.*?)</A>",
                       row, re.I | re.S)
        if am:
            cand.artist = _text(am.group(1))

        # Vorhandensein von Cue Sheet / Lyrics an den echten Links festmachen
        cand.has_cuesheet = bool(re.search(r"cuesheet\.php\?RecordId=", row, re.I))
        cand.has_lyrics = bool(re.search(r"lyrics\.php\?LyricsId=", row, re.I))

        ym = re.search(r"\b(19\d{2}|20\d{2})\b", _text(row))
        cand.year = ym.group(1) if ym else ""
        out.append(cand)
    return out


def _span(row: str, css_class: str) -> str:
    """Text des ersten <SPAN CLASS="…css_class…"> in der Zeile."""
    m = re.search(rf"<SPAN[^>]*CLASS=[\"'][^\"']*\b{css_class}\b[^\"']*[\"'][^>]*>"
                  r"(.*?)</SPAN>", row, re.I | re.S)
    return _text(m.group(1)) if m else ""


def _text(fragment: str) -> str:
    t = re.sub(r"<[^>]+>", " ", fragment)
    t = _html.unescape(t).replace("\xa0", " ")
    return re.sub(r"\s+", " ", t).strip()


# ---------------------------------------------------------------------------
# Treffersicherheit
# ---------------------------------------------------------------------------

# Titel-Aehnlichkeit lebt zentral in song_match (Re-Export fuer Aufrufer/Tests).
title_similarity = song_match.title_similarity


def score_candidate(cand: Candidate, want_title: str, want_label: str = "",
                    want_number: str = "") -> Candidate:
    """Bewertet einen Treffer 0..100 und begruendet das Ergebnis.

    Der Titel/Label/Nummer-Kern kommt aus song_match.score_match (gemeinsame
    Basis mit der Krabbelkiste-Suche). Ceder-spezifisch bleibt nur der Abzug fuer
    einen Datensatz OHNE Cue Sheet — ohne Sheet nuetzt der beste Treffer nichts.
    """
    score, why = song_match.score_match(
        want_title, want_label, want_number,
        cand.title, cand.label_name, cand.number)
    if not cand.has_cuesheet:
        score -= 25
        why.append(_t("ceder_why_no_cuesheet"))
    cand.score = max(0, min(100, score))
    cand.reasons = why
    return cand


def find_candidates(title: str, label_field: str = "", labels: Optional[dict] = None,
                    version: str = "0.0") -> tuple:
    """Kompletter Weg: Label zerlegen, suchen, bewerten, sortiert zurueckgeben.

    Rueckgabe: (kandidaten, info) — info beschreibt, wonach gesucht wurde,
    damit die Oberflaeche das ehrlich anzeigen kann.
    """
    lname, number = split_label_number(label_field)
    label_id, matched = (None, "")
    if labels:
        label_id, matched = match_label_id(lname, labels)
    cands = search(title=title, label_id=label_id, version=version)
    # Ohne Treffer mit Label: zweiter Versuch nur ueber den Titel. Labelnamen
    # weichen zwischen Dateiname und Ceder-Liste oefter ab als Titel.
    fallback = False
    if not cands and label_id:
        cands = search(title=title, label_id=None, version=version)
        fallback = True
    for c in cands:
        score_candidate(c, title, matched or lname, number)
    cands.sort(key=lambda c: c.score, reverse=True)
    info = {"label_name": lname, "number": number,
            "label_id": label_id, "label_matched": matched,
            "fallback_title_only": fallback, "count": len(cands)}
    return (cands, info)


# ---------------------------------------------------------------------------
# Cue Sheet holen
# ---------------------------------------------------------------------------

def fetch_cuesheet(record_id: str, version: str = "0.0") -> str:
    """Vollstaendige Cue-Sheet-Seite (cuesheet.php) eines Datensatzes.

    Bewusst die Druckansicht statt des ajax_viewsingle-Fragments: das Fragment
    verweist per CLASS auf das Site-Stylesheet und kaeme lokal unformatiert an.
    Die Vollseite bringt ihre Formatregeln (.call fett, .lyrics rosa, .hdr
    braunrot ...) als eingebettete <STYLE>-Bloecke selbst mit — und ist mit
    ~5 KB kaum groesser.
    """
    return _request(f"{BASE}cuesheet.php?RecordId={record_id}",
                    version=version)


# Nur diese CSS-Eigenschaften werden beim Inlinen uebernommen — der Rest
# (position, page-break, columns ...) wird von Qt ohnehin ignoriert und
# wuerde die Datei nur aufblaehen.
_CSS_KEEP = {"font-size", "font-weight", "font-style", "font-family",
             "color", "background-color", "text-decoration",
             "margin-left", "margin-right", "margin-top", "margin-bottom",
             "line-height", "text-align"}


def _strip_media_blocks(css: str) -> str:
    """Entfernt @media-Bloecke mitsamt Inhalt (Klammern balanciert).

    Die Media-Queries der Seite sind Responsive-Weichen fuer den Browser.
    Wuerden ihre inneren Regeln mit eingesammelt, laege z.B. fuer .text sowohl
    die Desktop- (30px) als auch die Mobil-Einrueckung (16px) vor — welche
    gewinnt, hinge von der Reihenfolge ab.
    """
    out, i, n = [], 0, len(css)
    while i < n:
        m = re.search(r"@media[^{]*\{", css[i:])
        if not m:
            out.append(css[i:])
            break
        out.append(css[i:i + m.start()])
        j, depth = i + m.end(), 1
        while j < n and depth:
            if css[j] == "{":
                depth += 1
            elif css[j] == "}":
                depth -= 1
            j += 1
        i = j
    return "".join(out)


def _class_rules(html_text: str) -> dict:
    """{klassenname: css} aus allen <STYLE>-Bloecken der Seite.

    Nur einfache Ein-Klassen-Selektoren (".call", "SPAN.hdr") — mehr nutzt die
    Cue-Sheet-Seite nicht, und mehr kann Qt beim Inlinen auch nicht abbilden.
    """
    rules: dict = {}
    for block in re.findall(r"<STYLE[^>]*>(.*?)</STYLE>", html_text,
                            re.I | re.S):
        block = _strip_media_blocks(re.sub(r"/\*.*?\*/", "", block, flags=re.S))
        for sel, body in re.findall(r"([^{}]+)\{([^{}]*)\}", block):
            props = []
            for part in body.split(";"):
                if ":" not in part:
                    continue
                k, v = part.split(":", 1)
                if k.strip().lower() in _CSS_KEEP:
                    props.append(f"{k.strip()}:{v.strip()}")
            if not props:
                continue
            for one in sel.split(","):
                m = re.fullmatch(r"(?:\w+)?\.([\w-]+)", one.strip())
                if m:
                    cls = m.group(1)
                    rules[cls] = rules.get(cls, "") + ";".join(props) + ";"
    # Die Einrueckungen stehen im Original in @media-Bloecken (oben verworfen)
    # bzw. als position/left, das Qt nicht kennt. Desktop-Wert fest uebernehmen.
    for cls in ("indent30", "text"):
        if cls in rules or cls == "indent30":
            rules[cls] = rules.get(cls, "") + "margin-left:30px;"
    return rules


def _inline_classes(body: str, rules: dict) -> str:
    """Schreibt die Klassenregeln als STYLE-Attribute in die Start-Tags.

    Noetig, weil Qts Rich-Text-Darstellung <STYLE>-Bloecke mit Klassenregeln
    nicht auswertet — im Browser saehe die Datei gut aus, im QTextBrowser der
    App bliebe sie nackt. Ein vorhandenes STYLE-Attribut bleibt erhalten und
    steht hinter den Klassenregeln, gewinnt also wie im echten CSS.
    """
    return re.sub(
        r"(<\w+)([^>]*?)\sCLASS\s*=\s*[\"']([^\"']+)[\"']([^>]*)>",
        lambda m: _one_wrap(m, rules), body, flags=re.I)


def _one_wrap(m, rules):
    head, pre, cls_attr, post = m.group(1), m.group(2), m.group(3), m.group(4)
    css = "".join(rules.get(c, "") for c in cls_attr.split())
    rest = pre + post
    if not css:
        return f"{head}{rest}>"
    sm = re.search(r"\sSTYLE\s*=\s*([\"'])(.*?)\1", rest, re.I | re.S)
    if sm:
        merged = css + sm.group(2)
        rest = rest[:sm.start()] + f' STYLE="{merged}"' + rest[sm.end():]
        return f"{head}{rest}>"
    return f'{head}{rest} STYLE="{css}">'


def _strip_navigation(body: str) -> str:
    """Entfernt Ceder-Navigationselemente, die im lokalen Lyric nichts zu
    suchen haben.

    Zwei Dinge fliegen raus:
    - der "two columns"-Umschalter oben rechts (ein Link mit ``col=2``, der
      die Seite im Browser zweispaltig neu laedt — lokal wirkungslos),
    - die Courier-DIVs im Footer mit den Verweisen zurueck in die Datenbank
      ("Data page", "Cue sheet", "Lyrics").

    Die Herkunft bleibt trotzdem nachvollziehbar: sie steht als HTML-Kommentar
    im <head> (siehe to_lyric_html), unabhaengig von den sichtbaren Links.
    """
    # "two columns": erst die ganze rechts eingeblendete float-Zelle, dann
    # ein evtl. nackt stehen gebliebener col=2-Link.
    body = re.sub(
        r"<DIV\b[^>]*float\s*:\s*right[^>]*>\s*<A\b[^>]*\bcol=2\b.*?</A>\s*</DIV>",
        "", body, flags=re.I | re.S)
    body = re.sub(r"<A\b[^>]*\bcol=2\b[^>]*>.*?</A>", "", body,
                  flags=re.I | re.S)
    # Footer: ceder trennt ihn mit einer Linie (<HR>) vom Inhalt ab. Alles ab
    # der LETZTEN Trennlinie abschneiden, sofern dahinter ein Ruecklink in die
    # Datenbank steht — robust gegen jede Aenderung am Footer-Styling. Die
    # Trennlinie unter dem Titel bleibt unberuehrt, weil sie kein solches
    # Tail-Kriterium erfuellt.
    _db_link = r"ceder\.net/recorddb|(?:viewsingle|cuesheet|lyrics)\.php"
    hrs = list(re.finditer(r"<HR\b[^>]*>", body, re.I))
    if hrs:
        last = hrs[-1]
        if re.search(_db_link, body[last.end():], re.I):
            body = body[:last.start()]
    # Fallback ohne Trennlinie: die Courier-DIVs mit den Datenbank-Links direkt
    # entfernen (enthalten keine verschachtelten DIVs, das erste </DIV> schliesst).
    body = re.sub(
        r"<DIV\b[^>]*font-family\s*:\s*Courier[^>]*>.*?</DIV>",
        "", body, flags=re.I | re.S)
    return body.rstrip()


def to_lyric_html(page: str, title: str, source_url: str = "") -> str:
    """Macht aus der cuesheet.php-Seite eine eigenstaendige Lyric-Datei.

    Skripte, Formulare und externe Verweise fliegen raus, die Formatierung der
    <STYLE>-Bloecke wird in die Tags geschrieben (siehe _inline_classes), und
    die Ceder-Navigation (two-columns-Umschalter, Footer-Datenbanklinks) wird
    weggefiltert (siehe _strip_navigation). Der Herkunftsnachweis bleibt als
    HTML-Kommentar im <head> erhalten.
    """
    rules = _class_rules(page)
    bm = re.search(r"<BODY[^>]*>(.*?)</BODY>", page, re.I | re.S)
    body = bm.group(1) if bm else page
    for tag in ("script", "style", "form", "button", "select", "textarea"):
        body = re.sub(rf"<{tag}\b.*?</{tag}>", "", body, flags=re.I | re.S)
    body = re.sub(r"<(input|link|base|meta)\b[^>]*>", "", body, flags=re.I)
    body = re.sub(r"\son\w+\s*=\s*(\"[^\"]*\"|'[^']*'|[^\s>]+)", "", body,
                  flags=re.I)
    body = _strip_navigation(body)
    body = _inline_classes(body, rules)
    safe_title = _html.escape(title or "Cue Sheet")
    origin = _html.escape(source_url)
    return (
        "<!DOCTYPE html>\n<html><head><meta charset=\"utf-8\">\n"
        f"<title>{safe_title}</title>\n"
        f"<!-- Quelle: {origin} (ceder.net) — nur fuer den persoenlichen "
        "Gebrauch, nicht weitergeben -->\n"
        "</head>\n"
        "<body style=\"font-family:Arial,Helvetica,sans-serif; "
        "font-size:10pt;\">\n"
        f"{body}\n</body></html>\n"
    )
