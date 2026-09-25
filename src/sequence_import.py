"""Sequenz-Import: Format-Erkennung, Parser und Schreibweise (intern#21).

Qt-frei. Der SequenceImportDialog ist nur die Oberflaeche davor.

Unterstuetzte Formate:
  - MDB / ACCDB (alte CC1-Datenbank)
  - JSON (Ceder-Eigen-Schema, Array mit calls/level/seq_type/difficulty)
  - CSDS (Vic Ceder Choreo-DB Export, @-Bloecke + #KEY=VALUE#)
  - Freitext (Leerzeile / Ceder-Web-Header als Trenner)

parse_files() liefert je Sequenz ein Dict mit den Keys
calls (list[str]), seq_type, difficulty, level, source_id (je str).
Unlesbare Dateien werden protokolliert und uebersprungen.
"""

import json
import os
import re
import sys

FMT_MDB = "mdb"
FMT_JSON = "json"
FMT_CSDS = "csds"
FMT_FREETEXT = "freetext"

# Gross-/Kleinschreibung der Call-Texte beim Import
CASE_ASIS = "asis"    # 1. wie im Text (unveraendert)
CASE_UPPER = "upper"  # 2. ALLES GROSSBUCHSTABEN
CASE_TITLE = "title"  # 3. Erster Buchstabe je Wort gross, Rest klein

# CSDS-SEQTYPE-Nummer -> lesbarer Name. Kanonische Ceder-Konvention:
# "Singer (...)" und Pfeil "➔" als Trenner. Muss unter
# song_db.canonicalize_seq_type unveraendert bleiben (Test sichert das),
# sonst entstehen doppelte Filter-Kategorien.
SEQTYPE_NAMES = {
    "5":   "Static Set ➔ Resolve",
    "10":  "Singer (Corner progression)",
    "20":  "Singer (R-H Lady progression)",
    "30":  "Singing break",
    "40":  "Stir the bucket",
    "80":  "Static Set ➔ Zero Line",
    "90":  "Static Set ➔ Zero Box",
    "95":  "Zero Line ➔ Resolve",
    "100": "Zero Line ➔ Zero Line",
    "110": "Zero Line ➔ Zero Box",
    "115": "Zero Box ➔ Resolve",
    "120": "Zero Box ➔ Zero Line",
    "130": "Zero Box ➔ Zero Box",
}
_DIFFICULTY_MAP = {"EASY": "Easy", "MEDIUM": "Medium", "HARD": "Hard"}
# Ceder-Header-Erkennung: Zeilen mit ID=<Zahl> sind Sequenz-Trennzeilen.
_CEDER_HEADER_RE = re.compile(r'\bID\s*=\s*\d+\b', re.IGNORECASE)
_CSDS_CALL_TAG_RE = re.compile(r'<C[^>]*>(.*?)</C>')


def _seq(calls, seq_type="", difficulty="", level="", source_id=""):
    return {"calls": calls, "seq_type": seq_type, "difficulty": difficulty,
            "level": level, "source_id": source_id}


def _read_text(path: str, size: int = -1, newline=None) -> str:
    """Liest UTF-8, faellt bei Dekodierfehler auf cp1252 zurueck."""
    try:
        with open(path, encoding="utf-8", newline=newline) as f:
            return f.read(size)
    except UnicodeDecodeError:
        with open(path, encoding="cp1252", newline=newline) as f:
            return f.read(size)


def detect_format(path: str) -> str:
    """Erkennt das Format anhand Datei-Endung + Inhalts-Stichprobe."""
    ext = os.path.splitext(path)[1].lower()
    if ext in (".mdb", ".accdb"):
        return FMT_MDB
    # Inhalts-Stichprobe (erste 4 KB reichen fuer alle Sniffs)
    try:
        head = _read_text(path, 4096)
    except Exception:
        return FMT_FREETEXT
    # CSDS: @-Block mit #REC=/#SEQTYPE=
    if "@" in head and ("#REC=" in head or "#SEQTYPE=" in head):
        return FMT_CSDS
    # JSON: beginnt mit [ oder {
    stripped = head.lstrip()
    if ext == ".json" or stripped.startswith("[") or stripped.startswith("{"):
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, (list, dict)):
                return FMT_JSON
        except Exception:
            pass
    return FMT_FREETEXT


def parse_files(paths: list, fmt: str) -> list:
    """Parst die Dateien im angegebenen Format zu Sequenz-Dicts.

    MDB nutzt nur die erste Datei. JSON und CSDS entfernen Dubletten ueber
    die Quell-ID, auch ueber mehrere Dateien hinweg.
    """
    if fmt == FMT_MDB:
        return _parse_mdb(paths[0])
    if fmt == FMT_JSON:
        return _parse_json(paths)
    if fmt == FMT_CSDS:
        return _parse_csds(paths)
    return _parse_freetext_files(paths)


def _parse_mdb(path: str) -> list:
    # mdb_reader liegt in src/migration/ (Sub-Paket neben main.py)
    migration_dir = os.path.join(os.path.dirname(__file__), "migration")
    if migration_dir not in sys.path:
        sys.path.insert(0, migration_dir)
    from mdb_reader import MdbReader  # type: ignore
    result = []
    for seq in MdbReader(path).read_sequences():
        calls = []
        for i in range(1, 16):
            val = seq.get(f"Feld{i}", None)
            if isinstance(val, str) and val.strip() and val.strip() != "-":
                calls.append(val.strip())
        if not calls:
            continue
        level = seq.get("Level", "") or ""
        if isinstance(level, str):
            level = level.strip()
        result.append(_seq(calls, level=level))
    return result


def _parse_json(paths: list) -> list:
    result = []
    seen_ids = set()
    for path in paths:
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            print(f"[SeqImport JSON] {path}: {e}")
            continue
        if not isinstance(data, list):
            continue
        for seq in data:
            if not isinstance(seq, dict):
                continue
            src_id = str(seq.get("id", "") or "")
            if src_id and src_id in seen_ids:
                continue
            if src_id:
                seen_ids.add(src_id)
            calls = [str(c).strip() for c in seq.get("calls", [])
                     if isinstance(c, str) and c.strip()]
            if not calls:
                continue
            result.append(_seq(
                calls,
                seq_type=str(seq.get("seq_type", "") or "").strip(),
                difficulty=str(seq.get("difficulty", "") or "").strip(),
                level=str(seq.get("level", "") or "").strip(),
                source_id=src_id,
            ))
    return result


def _parse_csds(paths: list) -> list:
    result = []
    seen_ids = set()
    for path in paths:
        try:
            with open(path, encoding="utf-8", errors="replace") as f:
                text = f.read()
        except Exception as e:
            print(f"[SeqImport CSDS] {path}: {e}")
            continue
        for block in text.split('@'):
            difficulty = ""
            rec_id = ""
            seq_type = ""
            calls = []
            for line in block.splitlines():
                s = line.strip()
                if not s:
                    continue
                if s.startswith('#') and s.endswith('#'):
                    inner = s[1:-1]
                    if inner in _DIFFICULTY_MAP:
                        difficulty = _DIFFICULTY_MAP[inner]
                    elif inner.startswith('REC='):
                        rec_id = inner[4:]
                    elif inner.startswith('SEQTYPE='):
                        seq_type = SEQTYPE_NAMES.get(inner[8:], inner[8:])
                    # PROOFREAD, AUTHOR etc. ignorieren
                else:
                    # <C ALT="...">text</C> -> text, Trailing-Komma weg
                    call = _CSDS_CALL_TAG_RE.sub(r'\1', s).rstrip(',').strip()
                    if call:
                        calls.append(call)
            if not calls:
                continue
            if rec_id and rec_id in seen_ids:
                continue
            if rec_id:
                seen_ids.add(rec_id)
            result.append(_seq(calls, seq_type=seq_type, difficulty=difficulty,
                               source_id=rec_id))
    return result


def _parse_freetext_files(paths: list) -> list:
    result = []
    for path in paths:
        try:
            # newline="" verhindert die Universal-Newline-Uebersetzung
            # beim Lesen. Sonst wandelt Python '\r\r\n' (SqView-Export:
            # doppeltes CR pro Zeile) schon hier in '\n\n' um — eine
            # Phantom-Leerzeile pro Call, die parse_freetext nicht mehr von
            # einem echten Sequenz-Trenner unterscheiden koennte. Mit
            # rohem '\r' normalisiert parse_freetext '\r+\n' → '\n' korrekt.
            text = _read_text(path, newline="")
        except Exception as e:
            print(f"[SeqImport Freitext] {path}: {e}")
            continue
        result.extend(_seq(calls) for calls in parse_freetext(text))
    return result


def parse_freetext(text: str) -> list:
    """Parst Freitext in eine Liste von Sequenzen (list[list[str]]).

    Drei Formate (auto-erkannt):
      1. Eine Zeile pro Sequenz, Calls durch Komma getrennt.
      2. Ein Call pro Zeile, Sequenzen durch Leerzeile(n) getrennt.
      3. Wie 2., zusaetzlich Trennzeichen am Ende der Zeile (`,` oder `;`).

    Sequenz-Trenner ist eine Leerzeile ODER eine Ceder-Header-Zeile (enthaelt
    `ID=<digits>`, z.B. "Mainstream -- Singer (Corner progression)   Easy
    ID=6734   Print"). Header-Zeilen werden verworfen.
    """
    # Zeilenenden normalisieren, BEVOR gesplittet wird. Manche Quellen
    # (z. B. SqView-Exporte) schreiben pro Zeile ein doppeltes CR: '\r\r\n'.
    # splitlines() zerlegt das lone '\r' in eine zusaetzliche Phantom-
    # Leerzeile — dann wuerde jeder Call als eigene Sequenz erkannt.
    # '\r+\n' → '\n' (deckt '\r\n' und '\r\r\n…' ab), danach lone CR (alt-Mac).
    text = re.sub(r'\r+\n', '\n', text)
    text = text.replace('\r', '\n')
    sequences = []
    block_lines = []

    def _flush_block():
        # Block-Inhalt: Zeilen trimmen + trailing , ; entfernen
        cleaned = [s for s in (ln.strip().rstrip(',;').strip()
                               for ln in block_lines) if s]
        if not cleaned:
            return
        # Format-Erkennung: 1 Zeile + Komma → Komma-Split, sonst je Zeile = ein Call
        if len(cleaned) == 1 and ',' in cleaned[0]:
            calls = [c.strip() for c in cleaned[0].split(',') if c.strip()]
        else:
            calls = cleaned
        if calls:
            sequences.append(calls)

    for ln in text.split('\n'):
        if ln.strip() == "" or _CEDER_HEADER_RE.search(ln):
            # Leerzeile ODER Ceder-Header → vorigen Block abschliessen,
            # Header-Zeile selbst nicht uebernehmen.
            _flush_block()
            block_lines = []
        else:
            block_lines.append(ln)
    _flush_block()
    return sequences


def apply_case(text: str, mode: str) -> str:
    """Wendet den Gross-/Kleinschreibungs-Modus auf einen Call-Text an.

    CASE_TITLE macht jeden Buchstaben gross, dem KEIN alphanumerisches
    Zeichen vorausgeht — also am Wortanfang und auch nach Trennzeichen wie
    Leerzeichen, '-', '(', ')', '/', '&'. Nach einer Ziffer bleibt der
    Buchstabe klein, damit '1ST' zu '1st' wird (nicht '1St' wie .title()).
    Beispiele: 'WALK-GIRLS' -> 'Walk-Girls', '(LOOK AT HER)' -> '(Look At Her)'.
    """
    if mode == CASE_UPPER:
        return text.upper()
    if mode == CASE_TITLE:
        out = []
        prev_alnum = False
        for ch in text:
            if ch.isalpha():
                out.append(ch.lower() if prev_alnum else ch.upper())
            else:
                out.append(ch)
            prev_alnum = ch.isalnum()
        return "".join(out)
    return text  # CASE_ASIS
