"""Gemeinsame Match-Basis: Rohname/Song -> Titel/Label/Nummer + Bewertung.

Kapselt die Suchprinzipien, die bisher verteilt lagen:
- Dateiname zerlegen (Titel/Label/Nummer)  -> war nur in zip_import
- Treffer bewerten (Titel/Label/Nummer)     -> war nur in ceder_lookup

Ein Ort fuer beides, damit jede Optimierung ueberall wirkt: die Krabbelkiste-
Suche (lokale Lyric-Dateien), die Ceder-Cue-Sheet-Suche und perspektivisch der
ZIP-Import schauen auf dieselbe Logik.

GUI-frei und ohne Qt-/main-Abhaengigkeiten (wie zip_import/ceder_lookup), damit
das Modul eigenstaendig testbar bleibt. Nur i18n wird importiert (selbst Qt-frei),
damit die Begruendungen uebersetzt sind.

Der Datei-Parser wird bewusst NICHT nachgebaut, sondern aus zip_import
wiederverwendet (`split_title_label`, `strip_label_suffix_modifier`) — dort steckt
die praxiserprobte Behandlung von Slugs, Bindestrich-/Mehrwort-Labels,
Kompakt-Token und Modifier-Suffixen.
"""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass, field
from typing import Optional

import zip_import
from i18n import _t

# Ab diesem Score gilt ein Treffer ueberhaupt als vorzeigbar. Darunter ist die
# Titel-Aehnlichkeit so gering, dass es reines Rauschen waere. Der Aufrufer darf
# schaerfer filtern; hier nur die Untergrenze, unter der wir gar nicht listen.
MIN_SCORE = 40

# Apostroph-/Anfuehrungsvarianten -> gerades ASCII. Aus ceder_lookup uebernommen
# und hier zentralisiert, damit beide Suchen dieselbe Vereinheitlichung nutzen.
_APOSTROPHE_VARIANTS = {
    "’": "'", "‘": "'", "ʼ": "'", "′": "'",
    "`": "'", "´": "'", "“": '"', "”": '"',
}


def normalize_query(text: str) -> str:
    """Vereinheitlicht Sonderzeichen (Apostrophe/Quotes) fuer die Suche."""
    if not text:
        return text
    for src, dst in _APOSTROPHE_VARIANTS.items():
        text = text.replace(src, dst)
    return text


# Labeltext der App in (Name, Nummer) trennen: "Shakedown 302" -> ("Shakedown",
# "302"). songs.label haelt beides zusammen; die Bewertung braucht den Namen und
# die Nummer getrennt (die Plattennummer identifiziert eine Aufnahme eindeutig).
_NUM_TAIL = re.compile(r"^(.*?)[\s\-_]*([0-9]{1,5}[A-Za-z]?)\s*$")


def split_label_number(label_field: str) -> tuple:
    """Trennt einen Labeltext in (Name, Nummer). Ohne Nummer: (Name, '')."""
    s = (label_field or "").strip()
    if not s:
        return ("", "")
    m = _NUM_TAIL.match(s)
    if not m or not m.group(1).strip():
        return (s, "")
    return (m.group(1).strip(" -_"), m.group(2).strip())


def _norm(s: str) -> str:
    """Normalisiert einen Titel fuer den Vergleich: klein, ohne Artikel, alnum."""
    s = (s or "").lower()
    s = re.sub(r"[‘’“”`]", "'", s)
    s = re.sub(r"\b(a|an|the)\b", " ", s)
    s = re.sub(r"[^a-z0-9 ]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def title_similarity(a: str, b: str) -> float:
    """0..1 Aehnlichkeit zweier Titel (normalisiert, dann SequenceMatcher)."""
    na, nb = _norm(a), _norm(b)
    if not na or not nb:
        return 0.0
    if na == nb:
        return 1.0
    return difflib.SequenceMatcher(None, na, nb).ratio()


# ---------------------------------------------------------------------------
# Rohname -> (Titel, Labelname, Nummer)
# ---------------------------------------------------------------------------

@dataclass
class ParsedName:
    """Ergebnis von parse_name: die drei Vergleichskriterien."""
    title: str = ""
    label_name: str = ""
    number: str = ""

    @property
    def label_full(self) -> str:
        return f"{self.label_name} {self.number}".strip()


def _maps(lists: Optional["zip_import.ImportLists"]) -> tuple:
    """Effektive (labelmap, modmap) aus den gepflegten Import-Listen."""
    if lists is None:
        lists = zip_import.ImportLists.defaults()
    return (lists.labels.effective(), lists.modifiers.effective())


def parse_name(raw: str, lists: Optional["zip_import.ImportLists"] = None) -> ParsedName:
    """Zerlegt einen Rohnamen in Titel/Labelname/Nummer.

    `raw` ist ein Dateiname OHNE Endung oder eine einzelne Textzeile (z.B. der
    Kopf eines Cue Sheets). Nutzt den zip_import-Parser fuer Titel/Label und
    spaltet danach die Nummer ab.
    """
    labelmap, modmap = _maps(lists)
    title, label = zip_import.split_title_label(raw or "", labelmap)
    clean_label, _mod = zip_import.strip_label_suffix_modifier(label, modmap)
    lname, number = split_label_number(clean_label or label)
    return ParsedName(title=title.strip(), label_name=lname.strip(),
                      number=number.strip())


# ---------------------------------------------------------------------------
# Bewertung: wie gut passt ein Kandidat zum gesuchten Song?
# ---------------------------------------------------------------------------

# Zwei Bewertungsprofile fuer denselben Vergleich — je nachdem, was gesucht wird:
#
# 'record' (Ceder-Cue-Sheet-Suche): Es geht um EINE bestimmte Aufnahme. Die
#   Plattennummer identifiziert sie eindeutig, der Titel allein nicht (derselbe
#   Titel erscheint beim selben Label mehrfach). Deshalb heben erst Label UND
#   Nummer auf „sicher", und eine ABWEICHENDE Nummer ist ein echtes Gegenindiz
#   (Strafe). So war die Ceder-Bewertung schon immer — bleibt unveraendert.
#
# 'lyric' (Krabbelkiste): Es geht um den TEXT eines Songs. Lyrics gelten pro
#   Titel, nicht pro Pressung — die Lyric-Datei einer anderen Aufnahme desselben
#   Songs ist trotzdem der richtige Text. Deshalb dominiert der Titel (er allein
#   traegt schon „wahrscheinlich"), und Label/Nummer sind reiner BONUS ohne
#   Strafe: eine abweichende Nummer darf einen guten Titeltreffer nie kippen.
_PROFILES = {
    'record': {'t_exact': 45, 't_sim': 32, 't_far': 15,
               'label_full': 25, 'label_part': 12,
               'num_bonus': 30, 'num_penalty': -15},
    'lyric':  {'t_exact': 70, 't_sim': 52, 't_far': 28,
               'label_full': 15, 'label_part': 8,
               'num_bonus': 15, 'num_penalty': 0},
}


def score_match(want_title: str, want_label: str, want_number: str,
                cand_title: str, cand_label: str, cand_number: str,
                profile: str = 'record') -> tuple:
    """Bewertet einen Kandidaten gegen den gesuchten Song. Rueckgabe (score, why).

    `profile` waehlt die Gewichtung ('record' fuer die Ceder-Aufnahmen-Suche,
    'lyric' fuer die titelzentrierte Krabbelkiste — siehe _PROFILES). Der Wert ist
    NICHT geklemmt, damit ein Aufrufer mit Zusatz-Straftermen (z.B. Ceders „kein
    Cue Sheet") sauber weiterrechnen kann; das Maximum jedes Profils ist 100.
    """
    p = _PROFILES.get(profile, _PROFILES['record'])
    score, why = 0, []
    sim = title_similarity(cand_title, want_title)
    if sim >= 0.995:
        score += p['t_exact']
        why.append(_t("ceder_why_title_exact"))
    elif sim >= 0.85:
        score += p['t_sim']
        why.append(_t("ceder_why_title_similar", pct=f"{sim:.0%}"))
    elif sim >= 0.6:
        score += p['t_far']
        why.append(_t("ceder_why_title_far", pct=f"{sim:.0%}"))
    else:
        why.append(_t("ceder_why_title_diff", pct=f"{sim:.0%}"))

    if want_label and cand_label:
        lsim = title_similarity(cand_label, want_label)
        if lsim >= 0.9:
            score += p['label_full']
            why.append(_t("ceder_why_label_match"))
        elif lsim >= 0.7:
            score += p['label_part']
            why.append(_t("ceder_why_label_similar"))
        else:
            why.append(_t("ceder_why_label_diff"))

    if want_number and cand_number:
        if str(want_number).lstrip("0").lower() == str(cand_number).lstrip("0").lower():
            score += p['num_bonus']
            why.append(_t("ceder_why_number_match"))
        elif p['num_penalty']:
            score += p['num_penalty']
            why.append(_t("ceder_why_number_diff", num=cand_number))

    return (score, why)


def confidence_word(score: int) -> str:
    """sicher / wahrscheinlich / unsicher — fuer die Anzeige (uebersetzt)."""
    if score >= 90:
        return _t("ceder_conf_high")
    if score >= 60:
        return _t("ceder_conf_medium")
    return _t("ceder_conf_low")


# ---------------------------------------------------------------------------
# Kompletter Datei-gegen-Song-Vergleich (fuer die Krabbelkiste-Suche)
# ---------------------------------------------------------------------------

@dataclass
class FileMatch:
    """Bester Treffer einer Lyric-Datei fuer einen gesuchten Song."""
    score: int = 0
    reasons: list = field(default_factory=list)
    source: str = ""          # 'filename' | 'content'  (Herkunfts-Schluessel)
    found_title: str = ""
    found_label: str = ""
    found_number: str = ""


def best_match(want_title: str, want_label_field: str,
               filename_raw: str, content_raws: Optional[list] = None,
               lists: Optional["zip_import.ImportLists"] = None) -> FileMatch:
    """Bester Treffer aus Dateiname ODER Datei-Inhalt fuer einen Song.

    Bewertet den Dateinamen und (optional) mehrere Inhalts-Kopfzeilen als
    Rohtext. Je Quelle wird geparst und mit dem 'lyric'-Profil bewertet; der
    hoehere Score gewinnt und die Herkunft wird festgehalten.

    Zusaetzlich ein Containment-Booster: steht der Songtitel KOMPLETT im Rohtext
    (Datei-/Zeilenname), gilt der Titel als Volltreffer — auch wenn der
    Dateiname-Parser Titel und Label falsch getrennt hat (typisch bei
    Labelnamen ohne Trennzeichen wie 'BadBadLeroyBrown-WagonWheel-212').
    """
    want_lname, want_number = split_label_number(want_label_field)
    nwant = _norm(want_title)

    best = FileMatch(score=-9999)
    sources = [("filename", filename_raw or "")]
    for c in (content_raws or []):
        sources.append(("content", c))

    for source, raw in sources:
        pn = parse_name(raw, lists)
        raw_score, why = score_match(
            want_title, want_lname, want_number,
            pn.title, pn.label_name, pn.number, profile='lyric')
        # Containment: Titel steckt vollstaendig im Rohtext -> als exakter Titel
        # werten (Label/Nummer-Bonus des Parses bleibt erhalten), falls das besser
        # ist als der regulaere Titelvergleich.
        if len(nwant) >= 5 and nwant in _norm(raw):
            cscore, cwhy = score_match(
                want_title, want_lname, want_number,
                want_title, pn.label_name, pn.number, profile='lyric')
            if cscore > raw_score:
                raw_score, why = cscore, cwhy
        clamped = max(0, min(100, raw_score))
        if clamped > best.score:
            best = FileMatch(score=clamped, reasons=why, source=source,
                             found_title=pn.title, found_label=pn.label_name,
                             found_number=pn.number)
    return best
