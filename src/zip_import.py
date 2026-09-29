"""Analyse von Label-Song-Paketen (ZIP) fuer den Import (BL-157).

Reine Logik, GUI-frei und ohne Qt-/main-Abhaengigkeiten, damit der Analyzer
eigenstaendig testbar ist (vgl. Lyrics-Matcher). Anbindung an UI, Perf-Logging
und DB erfolgt in main.py.

Begriffe:
- Bundle:   ein Song mit allen zugehoerigen Dateien (Haupt-MP3 + Varianten + Lyrics).
            Standard: ein ZIP = ein Bundle (1 Kauf = 1 Song). Enthaelt ein ZIP
            mehrere verschiedene Songs (Patter-Lieferung mit zwei Titeln, Label-
            Bundle aus einer Verkaufsaktion), erkennt der Splitter das (ZipGroup);
            ob getrennt importiert wird, entscheidet der User (intern#125).
- Modifier: Varianten-Kennzeichen, entweder als Klammer-Suffix '(V)' ODER direkt
            an der Labelnummer ('WM 002v' -> Label 'WM 002' + Modifier 'v').
- Haupt-MP3: die MP3 ohne Modifier/Rolle (Instrumental). Der User kann im Preview
            die Reihenfolge per Drag&Drop aendern; Position 1 = Primaer.

Pflegbare Wissensbasis (BL-157-Erweiterung): vier Listen, die der User im Dialog
pflegt. Standard-Eintraege leben im Code (DEFAULT_*), die User-Datei enthaelt nur
das Delta (eigene/geaenderte Eintraege + bewusst entfernte Standards). Beim Laden
wird gemergt: Standard + User (User gewinnt), entfernte Standards fallen raus.
Updates liefern neue Standards, ohne die User-Datei zu ueberschreiben.

Perf-Marken: alle laengeren Schritte rufen optional perf_cb(label, seconds) auf.
Default None = kein Overhead. main.py routet das auf perf_log().
"""

from __future__ import annotations

import difflib
import fnmatch
import json
import os
import re
import shutil
import tempfile
import time
import zipfile
from dataclasses import dataclass, field
from typing import Callable, Optional

# Mirror der Filter aus main.py: Audio-Import-Endungen bzw. _LYRICS_EXTENSIONS.
# Bei Aenderungen dort hier nachziehen.
AUDIO_EXTENSIONS = ('.mp3', '.wav', '.flac', '.ogg', '.aiff', '.aif')
LYRICS_EXTENSIONS = ('.rtf', '.htm', '.html', '.txt', '.docx', '.pdf')
# Format-Praeferenz fuer die Lyrics-Primaer-Vorauswahl (hochwertigstes zuerst).
_LYRICS_PRIORITY = ('.html', '.htm', '.rtf', '.txt', '.docx', '.pdf')

# ---------------------------------------------------------------------------
# Pflegbare Listen: Standard-Eintraege (im Code). User-Overrides in der JSON.
# ---------------------------------------------------------------------------

# 1) Modifier-/Varianten-Abkuerzungen: Token -> lesbare Bezeichnung.
DEFAULT_MODIFIERS = {
    '':     'Instrumental',
    'V':    'Vocal',
    'VJ':   'Vocal',
    'VOCAL': 'Vocal',
    'INST': 'Instrumental',
    'M':    'Melody',
    'L':    'Lead',
    'NL':   'No Lead Instrument',
    'NB':   'No Backup Vocals',
    'NBL':  'No Backup Vocals, No Lead',
    'NO MELODY': 'No Melody',
    'WL':   'With Lead',
    'K':    'Karaoke',
    'KAR':  'Karaoke',
    'C':    'Cued',
    'CUED': 'Cued',
    'CALL': 'Called',
    'H':    'Harmony',
    'HARM': 'Harmony',
    'H1':   'Harmony 1',
    'H2':   'Harmony 2',
    'H3':   'Harmony 3',
    # Rhythm-Records-Schema (RR): Tonart-Kennung am Vocal-Track. Bewusst nur die
    # eindeutigen Compound-Tokens — bare 'F'/'M' NICHT, weil 'M' bereits 'Melody'
    # belegt (Kollision). Die nackte F/M-Key-Kennung steht ohnehin nur auf dem
    # Cue-Sheet, nie auf einer Audiodatei.
    'FV':   'Female Vocal',
    'MV':   'Male Vocal',
    'MX':   'Mix',
    'MIX':  'Mix',
}

# 2) Label-Verzeichnis: Kuerzel -> Vollname (Vollname optional). Hilft, Label und
#    Titel sicher zu trennen und so Modifier am Label-Suffix abzuspalten.
#    Bewusst klein als Starter — der User/Community pflegt die Liste auf.
#    Labels MIT Bindestrich oder Leerzeichen sind hier besonders wichtig: sie
#    werden vor dem Titel/Label-Split maskiert, damit der Bindestrich im
#    Labelnamen nicht als Trenner missverstanden wird (SquareDesk-Ansatz).
DEFAULT_LABELS = {
    'WM': '',
    '4-Bar-B': '',
    'Circle-D': '',
    'Jay-Bar-Kay': '',
    'Hi-Hat': '',
    'New Beat': '',
    'Blue Star': '',
    'Wagon Wheel': '',
    'Red Boot': '',
}

# 3) Beiwerk-/Ignorier-Muster: Glob-Muster (gegen den ZIP-internen Pfad) -> Notiz.
#    Diese Dateien sind technisches Drumherum (z.B. Word-HTML-Export) und werden
#    nicht als Song/Lyrics behandelt, aber im Vollstaendigkeitscheck ausgewiesen.
DEFAULT_IGNORE_PATTERNS = {
    '*_files/*':              'Word/HTML-Beiwerk',
    '*.thmx':                 'Office-Design',
    'colorschememapping.xml': 'Word-HTML-Beiwerk',
    'filelist.xml':           'Word-HTML-Beiwerk',
    '*.xml':                  'XML-Beiwerk',
    '*.jpg':                  'Bild/Cover',
    '*.jpeg':                 'Bild/Cover',
    '*.png':                  'Bild/Cover',
    '*.gif':                  'Bild/Cover',
    '*.bmp':                  'Bild/Cover',
    'thumbs.db':              'Windows-Vorschau-Cache',
    'desktop.ini':            'Windows-Ordnereinstellung',
    '.ds_store':              'macOS-Beiwerk',
}

# 4) Rollen-Schluesselwoerter: Wort im Dateinamen -> Rolle (Vorbelegung der
#    Bezeichnung). z.B. 'original Born to Hand Jive.mp3' -> 'Original'.
DEFAULT_ROLE_KEYWORDS = {
    'original':     'Original',
    'demo':         'Demo',
    'sample':       'Sample',
    'cued':         'Cued',
    'karaoke':      'Karaoke',
    'instrumental': 'Instrumental',
    # 'vocal' als freies Wort im Dateinamen (SquareDesk erkennt das ebenso) —
    # die Token-Formen 'V'/'VJ' laufen weiter ueber die Modifier-Liste.
    'vocal':        'Vocal',
    'vocals':       'Vocal',
    # Patter-Lieferungen: 'red feather-extended.mp3' neben 'red feather.mp3'
    # (intern#125). Ohne den Eintrag galt die Extended-Spur als Hauptspur.
    'extended':     'Extended',
}

_JUNK_NAMES = {'thumbs.db', '.ds_store'}

# Label-Muster (mirror von main._LABEL_PATTERN): Buchstaben + opt. Space + Ziffern + Suffix.
# Suffix erlaubt Gross-/Kleinbuchstaben UND Ziffern, damit auch 'RR 409F' (Key im
# ZIP-Namen) und 'RR 409h1' (Harmony-Index) als Label erkannt werden.
_LABEL_PATTERN = re.compile(r'^[A-Za-z]+\s?\d+[A-Za-z0-9+]*$')
# Zusatz-Muster (aus SquareDesk uebernommene Praxisfaelle; _LABEL_PATTERN bleibt
# unveraendert der Spiegel von main._LABEL_PATTERN — diese hier sind ein Superset
# NUR fuer den ZIP-Import):
# a) Label-Kuerzel mit Ziffer im Namensteil: 'OGRMP3 04' (Space vor Nummer Pflicht,
#    sonst waere die Grenze Kuerzel/Nummer mehrdeutig).
_LABEL_PATTERN_DIGITS = re.compile(r'^[A-Za-z][A-Za-z0-9]*\s\d+[A-Za-z0-9+]*$')
# b) Mehrwort-Label generisch: 'New Beat 203a', 'Blue Star 1790'. Konservativ:
#    max. 3 Woerter, Nummer >= 3-stellig (sonst wuerden Titel wie 'Summer of 69'
#    faelschlich als Label gewertet).
_LABEL_PATTERN_MULTIWORD = re.compile(
    r'^[A-Za-z]+(?:\s[A-Za-z]+){1,2}\s?\d{3,5}[A-Za-z0-9+]{0,3}$')
# c) Reine Nummer als Label, nur links ('123 - Chicken Plucker'). Rechts bewusst
#    nicht (dort waere '... - 1999' eher Jahreszahl/Versionsnummer).
_LABEL_PATTERN_NUMONLY = re.compile(r'^\d{1,5}[A-Za-z]?$')
# c2) Kompakter Label-Token als kompletter Dateiname (SqView-Stil): 'A1005m',
#     'sd318v', 'CHIC3002'. Kein Leerzeichen, max. 4 Buchstaben, min. 2 Ziffern —
#     so bleiben echte Titel ('Track 3', 'Free m') aussen vor. Der Suffix wird
#     spaeter regulaer via strip_label_suffix_modifier als Modifier abgespalten,
#     wodurch z.B. das Paar 'A1005'/'A1005v' korrekt zu Haupt-MP3 + Vocal wird.
_LABEL_PATTERN_COMPACT = re.compile(r'^[A-Za-z]{1,4}\d{2,5}[A-Za-z0-9]{0,2}$')
# d) Punkt statt Bindestrich als Trenner: '123.Chicken Plucker' / '123. Chicken Plucker'.
_NUMDOT_RE = re.compile(r'^(\d{1,5})\.\s*(\S.*)$')
# e) Label-Nummer mit Bindestrich statt Space, unbekanntes Label:
#    'Paper Doll - Windsor-4936B' bzw. 'Windsor-4936 - Paper Doll'.
_TITLE_DASH_LABELDASHNUM = re.compile(
    r'^(.+?)\s*-\s*([A-Za-z]{1,9})-(\d{1,5}[A-Za-z0-9]{0,3})$')
_LABELDASHNUM_DASH_TITLE = re.compile(
    r'^([A-Za-z]{1,9})-(\d{1,5}[A-Za-z0-9]{0,3})\s*-\s*(.+)$')
# Klammer-Modifier an beliebiger Stelle. Beide Label-Schemata kommen vor:
#   'Title - GP 509 (V)'      (Modifier am Ende, GP)
#   'Title (V) - STING 22209' (Modifier vor dem Label, STING)
# Wir nehmen das LETZTE Klammerpaar als Modifier und putzen den Rest zum Basename.
_MODIFIER_RE = re.compile(r'\(([^()]*)\)')
# Label-Suffix-Modifier: <Label-Buchstaben> <Ziffern><Modifier-Buchstaben[+Ziffer]>.
# Beispiel 'WM 002v' -> Stamm 'WM 002', Suffix 'v'; 'RR 409h1' -> Stamm 'RR 409',
# Suffix 'h1'. Nur abspalten, wenn der Suffix ein bekannter Modifier-Token ist
# (sonst bleibt ein Flip-Side-Suffix wie '509a' Teil des Labels).
# Letternteil darf Leerzeichen enthalten, damit auch 'New Beat 203v' greift.
_LABEL_SUFFIX_RE = re.compile(r'^([A-Za-z][A-Za-z ]*?\s?\d+)([A-Za-z]+\d*)$')


def _norm_key(s: str) -> str:
    """Normalisiert auf reine Alphanumerik (case-insensitiv) fuer robuste Vergleiche."""
    return re.sub(r'[^a-z0-9]', '', s.lower())


def _normalize_name(s: str) -> str:
    """Putzt Download-Slugs: '%20' und '_' -> Leerzeichen, Whitespace buendeln.

    'ego_112_-_go_tell_aunt_rhody' -> 'ego 112 - go tell aunt rhody'.
    """
    s = s.replace('%20', ' ').replace('_', ' ')
    return re.sub(r'\s{2,}', ' ', s).strip()


def _smart_titlecase(s: str) -> str:
    """Title-Case, aber nur wenn der Text komplett klein oder komplett gross ist.

    Slugs ('go tell aunt rhody') und Schrei-Namen ('GO TELL AUNT RHODY') werden
    lesbar; gemischte Schreibweisen ('McGregor Special') bleiben unangetastet.
    """
    letters = [c for c in s if c.isalpha()]
    if not letters:
        return s
    if not (all(c.islower() for c in letters) or all(c.isupper() for c in letters)):
        return s
    return ' '.join(w[:1].upper() + w[1:].lower() for w in s.split(' '))


# Maskierung fuer Labels mit Bindestrich ('4-Bar-B', 'Circle-D'): vor dem Split
# durch dashfreie Platzhalter ersetzen, nach dem Split zuruecktauschen. Sonst
# zerschneidet der Titel/Label-Split den Labelnamen (SquareDesk loest das genauso).
_MASK_ALPHABET = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'


def _mask_dash_labels(name: str, labelmap: Optional[dict]) -> tuple:
    """Ersetzt bekannte Bindestrich-Labels durch Platzhalter (case-insensitiv).

    Rueckgabe (maskierter_name, mapping Platzhalter->Original-Schreibweise).
    """
    mapping = {}
    if not labelmap:
        return (name, mapping)
    i = 0
    # Laengste Kuerzel zuerst, damit 'Jay-Bar-Kay' vor einem etwaigen 'Bar-Kay' greift.
    for key in sorted(labelmap, key=len, reverse=True):
        if '-' not in key or i >= len(_MASK_ALPHABET):
            continue
        pat = re.compile(re.escape(key), re.IGNORECASE)
        m = pat.search(name)
        if not m:
            continue
        token = f'QQLBL{_MASK_ALPHABET[i]}'
        mapping[token] = m.group(0)  # Original-Schreibweise erhalten
        name = pat.sub(token, name)
        i += 1
    return (name, mapping)


def _unmask(s: str, mapping: dict) -> str:
    for token, original in mapping.items():
        s = s.replace(token, original)
    return s


# ---------------------------------------------------------------------------
# ManagedList: Standard (Code) + User-Delta (Datei). Merge mit User-Vorrang.
# ---------------------------------------------------------------------------

@dataclass
class ManagedList:
    """Eine pflegbare Schluessel->Wert-Liste mit Standard- und User-Anteil.

    defaults : Standard-Eintraege aus dem Code (nicht in der User-Datei).
    entries  : User-Eintraege (neu oder gegenueber dem Standard geaendert).
    removed  : Schluessel von Standards, die der User bewusst entfernt hat.
    """
    defaults: dict
    entries: dict = field(default_factory=dict)
    removed: list = field(default_factory=list)

    def effective(self) -> dict:
        """Effektive Liste: Standard (ohne entfernte) ueberlagert mit User-Eintraegen."""
        out = {k: v for k, v in self.defaults.items() if k not in self.removed}
        out.update(self.entries)
        return out

    def is_custom(self, key: str) -> bool:
        """True, wenn der Schluessel ein User-Eintrag ist (nicht reiner Standard)."""
        return key in self.entries and self.defaults.get(key) != self.entries.get(key) \
            or key not in self.defaults

    def set_from_effective(self, eff: dict) -> None:
        """Berechnet das Delta (entries/removed) aus einer vollstaendigen Liste.

        So liefert der Dialog einfach die sichtbare Gesamtliste; wir leiten daraus
        ab, was vom Standard abweicht und welche Standards entfernt wurden.
        """
        self.entries = {k: v for k, v in eff.items() if self.defaults.get(k) != v}
        self.removed = [k for k in self.defaults if k not in eff]

    def merge_in(self, other_eff: dict) -> None:
        """Fuegt eine fremde Liste additiv ein (Austausch zwischen Usern).

        Fremde Eintraege werden uebernommen; entfernte Standards, die die fremde
        Liste wieder mitbringt, werden reaktiviert. Bestehendes bleibt erhalten.
        """
        eff = self.effective()
        eff.update(other_eff)
        self.set_from_effective(eff)


@dataclass
class ImportLists:
    """Buendel der vier pflegbaren Listen."""
    modifiers: ManagedList
    labels: ManagedList
    ignore: ManagedList
    roles: ManagedList

    @classmethod
    def defaults(cls) -> 'ImportLists':
        return cls(
            modifiers=ManagedList(dict(DEFAULT_MODIFIERS)),
            labels=ManagedList(dict(DEFAULT_LABELS)),
            ignore=ManagedList(dict(DEFAULT_IGNORE_PATTERNS)),
            roles=ManagedList(dict(DEFAULT_ROLE_KEYWORDS)),
        )

    def as_dict(self) -> dict:
        """Serialisiert nur das Delta (entries/removed) pro Liste."""
        def _d(ml: ManagedList) -> dict:
            return {'entries': ml.entries, 'removed': ml.removed}
        return {
            'version': 1,
            'lists': {
                'modifiers': _d(self.modifiers),
                'labels':    _d(self.labels),
                'ignore':    _d(self.ignore),
                'roles':     _d(self.roles),
            },
        }


def _apply_delta(ml: ManagedList, data: dict) -> None:
    if not isinstance(data, dict):
        return
    ent = data.get('entries')
    rem = data.get('removed')
    if isinstance(ent, dict):
        ml.entries = {str(k): str(v) for k, v in ent.items()}
    if isinstance(rem, list):
        ml.removed = [str(k) for k in rem]


def load_lists(path: Optional[str]) -> ImportLists:
    """Laedt die vier Listen (Defaults + User-Delta aus path).

    Existiert path nicht, wird einmalig versucht, eine alte zip_modifiers.json im
    selben Ordner als Modifier-Liste zu uebernehmen (Rueckwaertskompatibilitaet).
    """
    lists = ImportLists.defaults()
    if path and os.path.isfile(path):
        try:
            with open(path, 'r', encoding='utf-8') as fh:
                data = json.load(fh)
            block = data.get('lists', {}) if isinstance(data, dict) else {}
            _apply_delta(lists.modifiers, block.get('modifiers', {}))
            _apply_delta(lists.labels,    block.get('labels', {}))
            _apply_delta(lists.ignore,    block.get('ignore', {}))
            _apply_delta(lists.roles,     block.get('roles', {}))
        except (OSError, ValueError):
            pass
        return lists
    # Migration: alte zip_modifiers.json (flache Token->Bezeichnung-Map).
    if path:
        legacy = os.path.join(os.path.dirname(path), 'zip_modifiers.json')
        if os.path.isfile(legacy):
            try:
                with open(legacy, 'r', encoding='utf-8') as fh:
                    old = json.load(fh)
                if isinstance(old, dict) and old:
                    lists.modifiers.set_from_effective(
                        {str(k): str(v) for k, v in old.items()})
            except (OSError, ValueError):
                pass
    return lists


def save_lists(lists: ImportLists, path: str) -> None:
    """Schreibt das Delta der vier Listen nach path."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as fh:
        json.dump(lists.as_dict(), fh, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------------
# Datei-Klassifikation
# ---------------------------------------------------------------------------

def split_title_label(name: str, labelmap: Optional[dict] = None) -> tuple:
    """Zerlegt einen Basenamen in (title, label).

    Grundmuster wie main._parse_filename (Split am Bindestrich + _LABEL_PATTERN),
    fuer den ZIP-Import aber um Praxisfaelle aus SquareDesk erweitert:
    Slug-Normalisierung, Bindestrich-Labels via Maskierung, Mehrwort-Labels,
    Nummer-only-Labels, Punkt-Trenner und 'Label-Nummer'-Schreibweisen.

    labelmap (optional) erhoeht die Sicherheit: Steht eines der Kuerzel als Label
    am Anfang oder Ende, wird diese Seite bevorzugt als Label gewertet.
    """
    name = _normalize_name(name)
    masked, mapping = _mask_dash_labels(name, labelmap)

    def _out(title: str, label: str) -> tuple:
        return (_unmask(title, mapping).strip(), _unmask(label, mapping).strip())

    if '-' not in masked:
        m = _NUMDOT_RE.match(masked)
        if m:
            return _out(m.group(2), m.group(1))
        if _LABEL_PATTERN_COMPACT.match(masked):
            # Dateiname IST das Label ('A1005m') — Titel = Label, damit der
            # Bundle-Titel nie leer wird.
            return _out(masked, masked)
        return _out(masked, '')

    left, right = masked.rsplit('-', 1)
    left, right = left.strip(), right.strip()
    left2, right2 = masked.split('-', 1)
    left2, right2 = left2.strip(), right2.strip()

    def _is_label(s: str) -> bool:
        return bool(s) and bool(_LABEL_PATTERN.match(s)
                                or _LABEL_PATTERN_DIGITS.match(s))

    if _is_label(right):
        return _out(left, right)
    if _is_label(left2):
        return _out(right2, left2)

    # 'Paper Doll - Windsor-4936B' / 'Windsor-4936 - Paper Doll' (Label-Nummer
    # mit Bindestrich, Label nicht in der Liste — sonst haette die Maskierung
    # schon gegriffen). Label normiert mit Space statt Bindestrich.
    m = _TITLE_DASH_LABELDASHNUM.match(masked)
    if m:
        return _out(m.group(1), f"{m.group(2)} {m.group(3)}")
    m = _LABELDASHNUM_DASH_TITLE.match(masked)
    if m:
        return _out(m.group(3), f"{m.group(1)} {m.group(2)}")

    # Fallback ueber bekannte Label-Kuerzel (auch mehrwortig, auch ohne strikte
    # Mustertreffer): Seite = bekanntes Kuerzel + Nummer(+Suffix)?
    if labelmap:
        known = {_norm_key(k) for k in labelmap if k}

        def _is_known_label(s: str) -> bool:
            nk = _norm_key(s)
            return any(nk.startswith(k)
                       and re.match(r'^\d+[a-z0-9]*$', nk[len(k):])
                       for k in known)
        if _is_known_label(right):
            return _out(left, right)
        if _is_known_label(left2):
            return _out(right2, left2)

    # Mehrwort-Label generisch, nur rechts ('Streets of London - New Beat 203a').
    if _LABEL_PATTERN_MULTIWORD.match(right):
        return _out(left, right)

    # Reine Nummer als Label, nur links ('123 - Chicken Plucker'). Der Titel darf
    # dabei nicht mit einer Ziffer beginnen — sonst wuerde '10-20Hoedown' zu
    # Label '10' + Titel '20Hoedown' zerlegt.
    if _LABEL_PATTERN_NUMONLY.match(left2) and right2 and not right2[0].isdigit():
        return _out(right2, left2)

    return _out(masked, '')


def strip_modifier(stem: str) -> tuple:
    """Zerlegt einen Stem in (base, modifier) anhand des LETZTEN Klammerpaars.

    modifier='' wenn keine Klammer. Bereinigt verwaiste '-' an den Raendern.
    """
    matches = list(_MODIFIER_RE.finditer(stem))
    if not matches:
        return (stem.strip(), '')
    m = matches[-1]
    modifier = m.group(1).strip()
    base = stem[:m.start()] + stem[m.end():]
    base = re.sub(r'\s{2,}', ' ', base).strip()
    base = re.sub(r'\s*-\s*$', '', base).strip()
    base = re.sub(r'^\s*-\s*', '', base).strip()
    return (base, modifier)


def strip_label_suffix_modifier(label: str, modmap: dict) -> tuple:
    """Spaltet einen Modifier ab, der direkt an der Labelnummer klebt.

    'WM 002v' -> ('WM 002', 'v'), aber nur wenn 'v' ein bekannter Modifier-Token
    ist. Unbekannte Suffixe (Flip-Side wie '509a') bleiben Teil des Labels.
    Rueckgabe (clean_label, modifier); modifier='' wenn nichts abgespalten.
    """
    if not label:
        return (label, '')
    m = _LABEL_SUFFIX_RE.match(label.strip())
    if not m:
        return (label, '')
    stem, suffix = m.group(1), m.group(2)
    nk = _norm_key(suffix)
    for tok in modmap:
        if tok and _norm_key(tok) == nk:
            return (stem.strip(), suffix)
    return (label, '')


def strip_trailing_word_modifier(stem: str, modmap: dict) -> tuple:
    """Spaltet einen Modifier ab, der als freies Wort am Dateinamen-Ende steht.

    'I Cant Fight This Feeling VJ' -> ('I Cant Fight This Feeling', 'VJ'), aber nur
    wenn das letzte Wort ein bekannter Modifier-Token ist. Sonst bleibt es Teil des
    Titels ('... Feeling' wird nicht angetastet).
    Rueckgabe (rest, modifier); modifier='' wenn nichts abgespalten.
    """
    parts = stem.split()
    if len(parts) < 2:
        return (stem, '')
    last = parts[-1]
    nk = _norm_key(last)
    if not nk:
        return (stem, '')
    for tok in modmap:
        if tok and _norm_key(tok) == nk:
            return (' '.join(parts[:-1]).strip(), last)
    return (stem, '')


def modifier_label(token: str, modmap: dict) -> str:
    """Lesbare Bezeichnung fuer einen Modifier-Token; faellt auf den Roh-Token zurueck."""
    if token in modmap:
        return modmap[token]
    nk = _norm_key(token)
    for k, v in modmap.items():
        if _norm_key(k) == nk:
            return v
    return token


def _role_for(stem: str, rolemap: dict) -> tuple:
    """Findet ein Rollen-Schluesselwort im Stem. Rueckgabe (keyword, rolle) oder ('','')."""
    low = stem.lower()
    for kw, role in rolemap.items():
        if not kw:
            continue
        if re.search(r'(?<![a-z0-9])' + re.escape(kw.lower()) + r'(?![a-z0-9])', low):
            return (kw, role)
    return ('', '')


def classify_audio(stem: str, modmap: dict, labelmap: dict, rolemap: dict) -> dict:
    """Bestimmt fuer einen Audio-Stem Modifier/Rolle/Bezeichnung + Primaer-Eignung.

    Reihenfolge: Klammer-Modifier > Label-Suffix-Modifier > Rollen-Keyword >
    Instrumental (= Haupt-Kandidat).
    Rueckgabe-Dict: {modifier, label_text, is_main}.
    """
    stem = _normalize_name(stem)
    base, mod = strip_modifier(stem)
    if mod:
        return {'modifier': mod, 'label_text': modifier_label(mod, modmap),
                'is_main': False}
    title, label = split_title_label(stem, labelmap)
    _clean, suffix_mod = strip_label_suffix_modifier(label, modmap)
    if suffix_mod:
        return {'modifier': suffix_mod,
                'label_text': modifier_label(suffix_mod, modmap), 'is_main': False}
    _rest, word_mod = strip_trailing_word_modifier(title, modmap)
    if word_mod:
        return {'modifier': word_mod,
                'label_text': modifier_label(word_mod, modmap), 'is_main': False}
    kw, role = _role_for(stem, rolemap)
    if role:
        return {'modifier': '', 'label_text': role, 'is_main': False}
    return {'modifier': '', 'label_text': modmap.get('', 'Instrumental'),
            'is_main': True}


def song_key(stem: str, modmap: dict, labelmap: dict, rolemap: dict) -> str:
    """Titel-Schluessel eines Datei-Stems fuer den Splitter (intern#125).

    Zieht Klammer-Modifier, Label, freie Modifier-Woerter und Rollen-Keywords
    ab und normalisiert auf Alphanumerik: 'red feather-extended' und
    'Red Feather (V)' ergeben beide 'redfeather'. '' = kein Titel erkennbar
    (z. B. nur Labelnummer).
    """
    base, _ = strip_modifier(_normalize_name(stem))
    title, _label = split_title_label(base, labelmap)
    title, _ = strip_trailing_word_modifier(title, modmap)
    low = title.lower()
    for kw in rolemap:
        if kw:
            low = re.sub(r'(?<![a-z0-9])' + re.escape(kw.lower()) + r'(?![a-z0-9])',
                         ' ', low)
    return _norm_key(low)


def _key_similarity(a: str, b: str) -> float:
    """Aehnlichkeit zweier Titel-Schluessel (0..1). Enthaltensein zaehlt voll,
    aber erst ab 6 Zeichen, damit kurze Schluessel nicht alles verschlucken."""
    if a == b:
        return 1.0
    if not a or not b:
        return 0.0
    short, long_ = sorted((a, b), key=len)
    if len(short) >= 6 and short in long_:
        return 1.0
    return difflib.SequenceMatcher(None, a, b).ratio()


# Ab dieser Aehnlichkeit gelten zwei Titel als derselbe Song.
_SAME_SONG = 0.85


# ---------------------------------------------------------------------------
# Datamodelle des Analyse-Ergebnisses
# ---------------------------------------------------------------------------

@dataclass
class AudioCandidate:
    path: str          # absoluter Pfad im Temp-Ordner
    filename: str      # Basename
    stem: str          # Name ohne Endung
    modifier: str      # Roh-Modifier ('' = Instrumental)
    label_text: str    # vorbelegte, editierbare Bezeichnung
    is_primary_suggested: bool = False


@dataclass
class LyricsCandidate:
    path: str
    filename: str
    ext: str
    label_text: str = ''   # vorbelegte, editierbare Bezeichnung (Variante)
    is_primary_suggested: bool = False
    selected: bool = True


@dataclass
class SongBundle:
    base: str          # nackter Basename / ZIP-Name
    title: str
    label: str
    audio: list = field(default_factory=list)    # Primaer-Vorschlag zuerst
    lyrics: list = field(default_factory=list)
    # Typ-Vorbelegung: Singing nur mit passenden Lyrics, sonst Patter (intern#125).
    singing_suggested: bool = False


# Grund fuer Lyrics, die in einem geteilten ZIP keinem Song zuzuordnen sind.
UNASSIGNED_LYRICS_REASON = 'keinem Song zuordenbar'


@dataclass
class ZipGroup:
    """Ein ZIP mit beiden moeglichen Sichten (intern#125).

    merged = alles als ein Song (bisheriges Verhalten), split = ein Bundle je
    erkanntem Song (nur gefuellt, wenn der Splitter mehrere Songs findet).
    Welche Sicht gilt, entscheidet der User (use_split).
    """
    zip_file: str                                   # Basename inkl. .zip
    merged: SongBundle
    split: list = field(default_factory=list)
    unassigned: list = field(default_factory=list)  # Lyrics-Basenamen ohne Song (split)
    use_split: bool = False

    @property
    def is_multi(self) -> bool:
        return len(self.split) > 1

    def bundles(self) -> list:
        return self.split if (self.use_split and self.is_multi) else [self.merged]


@dataclass
class AnalysisResult:
    bundles: list = field(default_factory=list)
    ignored: list = field(default_factory=list)   # Basenamen weder Audio noch Lyrics
    ignored_reasons: dict = field(default_factory=dict)  # name -> Grund (Beiwerk/unbekannt)
    total_files: int = 0                            # alle entpackten Nutzdateien
    temp_dir: str = ''
    zips: list = field(default_factory=list)        # ZipGroup je ZIP (intern#125)

    def refresh_bundles(self) -> None:
        """bundles nach den use_split-Entscheidungen der ZipGroups neu aufbauen."""
        self.bundles = [b for z in self.zips for b in z.bundles()]

    @property
    def multi_song_zips(self) -> list:
        return [z for z in self.zips if z.is_multi]

    @property
    def other_files(self) -> list:
        """(Basename, Grund) aller nicht importierten Dateien, inkl. Lyrics, die
        in einem geteilten ZIP keinem Song zuzuordnen sind."""
        out = [(n, self.ignored_reasons.get(n, '')) for n in self.ignored]
        for z in self.zips:
            if z.use_split and z.is_multi:
                out.extend((n, UNASSIGNED_LYRICS_REASON) for n in z.unassigned)
        return out

    @property
    def assigned_count(self) -> int:
        return sum(len(b.audio) + len(b.lyrics) for b in self.bundles)

    @property
    def is_complete(self) -> bool:
        """Vollstaendigkeitscheck: jede Datei ist zugeordnet oder gelistet."""
        return self.assigned_count + len(self.other_files) == self.total_files


def _is_junk(name: str) -> bool:
    base = os.path.basename(name)
    if base.lower() in _JUNK_NAMES:
        return True
    if base.startswith('._'):
        return True
    if '__MACOSX' in name:
        return True
    return False


def _matches_ignore(rel_path: str, patterns: dict) -> Optional[str]:
    """Gibt den Notiz-Text zurueck, wenn rel_path auf ein Ignorier-Muster passt."""
    rp = rel_path.replace('\\', '/').lower()
    base = os.path.basename(rp)
    for pat, note in patterns.items():
        p = pat.lower()
        if fnmatch.fnmatch(rp, p) or fnmatch.fnmatch(base, p):
            return note or 'ignoriert'
    return None


def extract_zips(zip_paths, dest_dir: str,
                 perf_cb: Optional[Callable[[str, float], None]] = None) -> list:
    """Entpackt alle ZIPs nach dest_dir (je ZIP eigener Unterordner).

    Extrahiert flach auf den Basenamen (kein Zip-Slip, keine Tiefenstruktur), haelt
    aber den ZIP-internen relativen Pfad fest (fuer Ignorier-Muster).
    Rueckgabe: Liste von Dicts je ZIP:
        {'zip': pfad, 'name': basename_ohne_endung, 'files': [(abs_path, rel_path), ...]}
    """
    out = []
    for zp in zip_paths:
        t0 = time.perf_counter()
        name = os.path.splitext(os.path.basename(zp))[0]
        stem = _norm_key(name) or 'zip'
        sub = os.path.join(dest_dir, stem)
        n, i = sub, 1
        while os.path.exists(n):
            n, i = f"{sub}_{i}", i + 1
        os.makedirs(n, exist_ok=True)
        files = []
        try:
            with zipfile.ZipFile(zp) as zf:
                for info in zf.infolist():
                    if info.is_dir() or _is_junk(info.filename):
                        continue
                    target = os.path.join(n, os.path.basename(info.filename))
                    # Namenskollision beim Flachklopfen vermeiden.
                    tn, k = target, 1
                    while os.path.exists(tn):
                        root, ext = os.path.splitext(target)
                        tn, k = f"{root}_{k}{ext}", k + 1
                    target = tn
                    with zf.open(info) as src, open(target, 'wb') as dst:
                        shutil.copyfileobj(src, dst)
                    files.append((target, info.filename))
        except (zipfile.BadZipFile, OSError):
            continue
        out.append({'zip': zp, 'name': name, 'files': files})
        if perf_cb:
            perf_cb(f"zip_import.extract[{os.path.basename(zp)}]",
                    time.perf_counter() - t0)
    return out


def _make_bundle(zbase: str, audio_files: list, lyrics_files: list,
                 modmap: dict, labelmap: dict, rolemap: dict,
                 title_from_audio: bool = False) -> SongBundle:
    """Baut ein Song-Bundle aus Audio- (abs, fn, stem) und Lyrics-Dateien
    (abs, fn, ext).

    title_from_audio: Titel immer aus der Primaer-MP3 statt aus dem ZIP-Namen
    (fuer Songs aus einem geteilten ZIP, dessen Name nur zu einem passt).
    """
    # Audio-Kandidaten klassifizieren + Primaer-Vorschlag.
    audio_objs = []
    for (path, fn, stem) in audio_files:
        info = classify_audio(stem, modmap, labelmap, rolemap)
        audio_objs.append(AudioCandidate(
            path=path, filename=fn, stem=stem,
            modifier=info['modifier'], label_text=info['label_text']))
    primary_idx = next((i for i, (a, src) in enumerate(zip(audio_objs, audio_files))
                        if classify_audio(src[2], modmap, labelmap, rolemap)['is_main']),
                       None)
    if primary_idx is None and audio_objs:
        primary_idx = 0
    if primary_idx is not None:
        audio_objs[primary_idx].is_primary_suggested = True
    audio_objs.sort(key=lambda a: (not a.is_primary_suggested, a.filename.lower()))

    # Titel/Label: bevorzugt aus der primaeren Audiodatei (nach dem Sort an
    # Position 0) — sie traegt den verlaesslichen Klartextnamen. Der ZIP-Datei-
    # name ist oft ein Download-Slug ('ego_112_-_go_tell...') oder nur das Label
    # ('STING 22209'). Nur uebernehmen, wenn die Primaer-MP3 ein sauberes Label
    # liefert; sonst beim ZIP-Namen bleiben (kein Regressionsrisiko).
    title, label = split_title_label(zbase, labelmap)
    if audio_objs:
        base_stem, _ = strip_modifier(audio_objs[0].stem)
        a_title, a_label = split_title_label(base_stem, labelmap)
        if a_label or title_from_audio:
            title, label = a_title, a_label
    clean_label, _ = strip_label_suffix_modifier(label, modmap)
    # Slug-/GROSSSCHREIB-Titel lesbar machen (nur bei komplett einheitlicher
    # Schreibung — gemischte Titel bleiben unangetastet).
    title = _smart_titlecase(title)
    bundle = SongBundle(base=zbase, title=title, label=clean_label or label)
    bundle.audio = audio_objs

    # Lyrics-Kandidaten + Primaer nach Format-Praeferenz.
    lyr_objs = []
    for (p, f, e) in lyrics_files:
        stem = os.path.splitext(f)[0]
        _b, mod = strip_modifier(stem)
        lbl = modifier_label(mod, modmap) if mod else e.lstrip('.').upper()
        lyr_objs.append(LyricsCandidate(path=p, filename=f, ext=e, label_text=lbl))
    if lyr_objs:
        def _rank(lc):
            return (_LYRICS_PRIORITY.index(lc.ext)
                    if lc.ext in _LYRICS_PRIORITY else len(_LYRICS_PRIORITY))
        lyr_objs.sort(key=lambda lc: (_rank(lc), lc.filename.lower()))
        lyr_objs[0].is_primary_suggested = True
    bundle.lyrics = lyr_objs
    bundle.singing_suggested = bool(lyr_objs)
    return bundle


def split_songs(audio_files: list, lyrics_files: list, modmap: dict,
                labelmap: dict, rolemap: dict) -> tuple:
    """Splitter (intern#125): teilt die Dateien eines ZIPs in Songs auf.

    Audios mit aehnlichem Titel-Schluessel (song_key) bilden einen Song.
    Geteilt wird nur, wenn es mindestens zwei Songs gibt UND jeder eine eigene
    Hauptspur hat — so bleibt 'Titel.mp3' + 'Titel (V).mp3' sicher ein Song.
    Lyrics gehen an den Song mit dem aehnlichsten Titel; ohne eindeutigen
    Treffer landen sie in 'unassigned' statt still an einem Song.

    Rueckgabe: ([(audio_files, lyrics_files), ...], unassigned_lyrics) oder
    ([], []), wenn nicht geteilt wird.
    """
    groups = []   # [key, [audio...], has_main]
    for af in sorted(audio_files, key=lambda a: a[1].lower()):
        key = song_key(af[2], modmap, labelmap, rolemap)
        is_main = classify_audio(af[2], modmap, labelmap, rolemap)['is_main']
        best = max(groups, key=lambda g: _key_similarity(key, g[0]), default=None)
        if best is not None and _key_similarity(key, best[0]) >= _SAME_SONG:
            best[1].append(af)
            best[2] = best[2] or is_main
        else:
            groups.append([key, [af], is_main])
    if len(groups) < 2 or not all(g[2] for g in groups):
        return ([], [])

    lyr_by_group = [[] for _ in groups]
    unassigned = []
    for lf in lyrics_files:
        key = song_key(os.path.splitext(lf[1])[0], modmap, labelmap, rolemap)
        scores = [_key_similarity(key, g[0]) for g in groups]
        top = max(scores)
        # Eindeutig: bester Treffer ueber der Schwelle und kein Gleichstand.
        if top >= _SAME_SONG and scores.count(top) == 1:
            lyr_by_group[scores.index(top)].append(lf)
        else:
            unassigned.append(lf[1])
    return ([(g[1], lyr) for g, lyr in zip(groups, lyr_by_group)], unassigned)


def analyze(zip_paths, lists: Optional[ImportLists] = None,
            dest_dir: Optional[str] = None,
            perf_cb: Optional[Callable[[str, float], None]] = None) -> AnalysisResult:
    """Analysiert ein oder mehrere Label-ZIPs und liefert je ZIP ein Song-Bundle.

    Enthaelt ein ZIP mehrere Songs, traegt die ZipGroup zusaetzlich die geteilte
    Sicht; result.bundles zeigt zunaechst die zusammengefasste (use_split=False),
    bis der Aufrufer nach Rueckfrage umschaltet und refresh_bundles() ruft.

    Args:
        zip_paths: Liste von ZIP-Pfaden.
        lists:     ImportLists (Default: nur Code-Standards). Aus Rueckwaerts-
                   kompatibilitaet wird auch ein reines Modifier-Dict akzeptiert.
        dest_dir:  Zielordner zum Entpacken (Default: neuer Temp-Ordner).
        perf_cb:   optionaler Callback(label, seconds) fuer Perf-Marken.
    """
    if lists is None:
        lists = ImportLists.defaults()
    elif isinstance(lists, dict):  # Alt-Aufruf mit modmap
        ml = ImportLists.defaults()
        ml.modifiers.set_from_effective(lists)
        lists = ml

    modmap   = lists.modifiers.effective()
    labelmap = lists.labels.effective()
    ignoremap = lists.ignore.effective()
    rolemap  = lists.roles.effective()

    if not dest_dir:
        dest_dir = tempfile.mkdtemp(prefix='cc_zipimport_')

    zips = extract_zips(zip_paths, dest_dir, perf_cb=perf_cb)

    t0 = time.perf_counter()
    result = AnalysisResult(temp_dir=dest_dir)

    for z in zips:
        audio_files = []   # (abs, fn, stem)
        lyrics_files = []  # (abs, fn, ext)
        for (abs_path, rel_path) in z['files']:
            result.total_files += 1
            fn = os.path.basename(abs_path)
            note = _matches_ignore(rel_path, ignoremap)
            if note is not None:
                result.ignored.append(fn)
                result.ignored_reasons[fn] = note
                continue
            stem, ext = os.path.splitext(fn)
            ext_l = ext.lower()
            if ext_l in AUDIO_EXTENSIONS:
                audio_files.append((abs_path, fn, stem))
            elif ext_l in LYRICS_EXTENSIONS:
                lyrics_files.append((abs_path, fn, ext_l))
            else:
                result.ignored.append(fn)
                result.ignored_reasons[fn] = 'unbekannter Dateityp'

        if not audio_files and not lyrics_files:
            continue

        zbase = z['name']
        group = ZipGroup(
            zip_file=os.path.basename(z['zip']),
            merged=_make_bundle(zbase, audio_files, lyrics_files,
                                modmap, labelmap, rolemap))
        parts, unassigned = split_songs(audio_files, lyrics_files,
                                        modmap, labelmap, rolemap)
        group.split = sorted(
            (_make_bundle(zbase, a, lyr, modmap, labelmap, rolemap,
                          title_from_audio=True) for a, lyr in parts),
            key=lambda b: b.title.lower())
        group.unassigned = unassigned
        result.zips.append(group)

    result.zips.sort(key=lambda g: g.merged.title.lower())
    result.refresh_bundles()
    if perf_cb:
        perf_cb("zip_import.scan", time.perf_counter() - t0)
    return result


def cleanup(result: AnalysisResult) -> None:
    """Loescht den Temp-Ordner einer Analyse (nach Commit oder Abbruch)."""
    if result.temp_dir and os.path.isdir(result.temp_dir):
        shutil.rmtree(result.temp_dir, ignore_errors=True)
