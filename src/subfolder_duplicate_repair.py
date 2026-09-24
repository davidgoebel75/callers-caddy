"""Reparatur: Doppelgaenger von Songs aus Musik-Unterordnern (intern#106).

Bis v0.158 hat _on_file_loaded() einen geladenen Song nur ueber den Basename
gesucht. Lag die Datei in einem Unterordner eines Musik-Slots (DB-Eintrag mit
relativem Pfad, z.B. 'Patter/Song.mp3'), fand get_or_create('Song.mp3') nichts
und legte einen zweiten Eintrag mit Default-Werten an (Pattern + Singing).
Alle Aenderungen in den Song-Daten landeten danach an diesem Doppelgaenger.

Diese Reparatur fuehrt jeden Doppelgaenger B in sein Original A zurueck:
- Songs-Felder: B gewinnt, wo der Nutzer dort etwas geaendert hat (Wert
  weicht von SongDatabase.new_song() ab). Sonst bleibt A. Dabei:
  * Pattern/Singing nur als Paar (sonst entsteht z.B. weder-noch).
  * Loop (in/out/offset) nur als Einheit, und nur wenn A keinen Loop hat
    oder B einen echten Loop-In gesetzt hat. B's loop_out ist sonst meist nur
    die Songdauer, die beim Laden automatisch eingetragen wird.
  * filename und date_added bleiben immer von A.
- song_properties: B gewinnt pro Key; Musik-Varianten (music_N_*) je Nummer
  nur komplett, damit keine Variante aus Name von B und Datei von A entsteht.
- Genres: Vereinigung, ohne das bei B automatisch vergebene "NEW".
- play_history wird auf A umgehaengt, song_location_stats zusammengefuehrt.
- Playlist-Dateien, die B unter dessen Titel/Dateinamen fuehren, werden auf
  A's Titel umgeschrieben (Sicherung '.bak_intern106' daneben).
Vor dem ersten Zusammenfuehren wird die DB gesichert; scheitert das, wird
nichts repariert.

Ein Paar gilt nur als Doppelgaenger, wenn eindeutig: B hat keinen Ordnerpfad,
genau EIN Eintrag A hat einen relativen Pfad mit gleichem Basename (Gross-/
Kleinschreibung egal, wie unter Windows), A's Datei ist auffindbar und B's
Datei NICHT (sonst waere B ein legitimer Song im Slot-Stamm, oder das
Laufwerk ist gerade nicht erreichbar).
"""
import copy
import os
import posixpath
import re

from song_db import Song, SongDatabase

# Einzelfelder, die vom Doppelgaenger uebernommen werden koennen
_MERGE_FIELDS = ("artist", "label", "quality", "base_bpm", "standard_tempo",
                 "pitch", "volume", "lyrics_file", "err")
_LOOP_FIELDS = ("loop_in", "loop_out", "loop_offset_ms")

_VARIANT_KEY_RE = re.compile(r"^music_(\d+)_")
_PLAYLIST_COUNT_RE = re.compile(r"\d+(:\d+)?")


def _base_key(filename: str) -> str:
    return posixpath.basename(filename.replace("\\", "/")).casefold()


def _has_folder(filename: str) -> bool:
    return "/" in filename or "\\" in filename


def find_pairs(db: SongDatabase, find_song_file) -> list:
    """Liefert [(original, doppelgaenger), ...] als Song-Paare."""
    songs = db.get_all()
    by_base = {}
    for s in songs:
        if _has_folder(s.filename):
            by_base.setdefault(_base_key(s.filename), []).append(s)
    pairs = []
    for b in songs:
        if _has_folder(b.filename):
            continue
        candidates = by_base.get(_base_key(b.filename), [])
        if len(candidates) > 1:
            print(f"[Repair#106] Mehrdeutig, uebersprungen: #{b.id} '{b.filename}' "
                  f"({len(candidates)} Originale in Unterordnern)")
        if len(candidates) != 1:
            continue
        a = candidates[0]
        if find_song_file(a.filename) and not find_song_file(b.filename):
            pairs.append((a, b))
    return pairs


def merge_song_fields(a: Song, b: Song) -> Song:
    """A mit den Nutzer-Aenderungen von B (Regeln siehe Modul-Docstring)."""
    default = SongDatabase.new_song(b.filename)
    merged = copy.copy(a)
    if (b.title or "").strip() != default.title.strip():
        merged.title = b.title
    for field in _MERGE_FIELDS:
        value = getattr(b, field)
        if value != getattr(default, field):
            setattr(merged, field, value)
    if (b.is_pattern, b.is_singing) != (default.is_pattern, default.is_singing):
        merged.is_pattern, merged.is_singing = b.is_pattern, b.is_singing
    a_has_loop = a.loop_in > 0.0 or a.loop_out > 0.0
    b_changed_loop = any(getattr(b, f) != getattr(default, f) for f in _LOOP_FIELDS)
    if b_changed_loop and (not a_has_loop or b.loop_in > 0.0):
        for field in _LOOP_FIELDS:
            setattr(merged, field, getattr(b, field))
    return merged


def merge_properties(props_a: dict, props_b: dict) -> dict:
    """B gewinnt pro Key; Musik-Varianten je Nummer nur als Ganzes."""
    b_variants = {m.group(1) for k in props_b if (m := _VARIANT_KEY_RE.match(k))}
    merged = {k: v for k, v in props_a.items()
              if not ((m := _VARIANT_KEY_RE.match(k)) and m.group(1) in b_variants)}
    merged.update(props_b)
    return merged


def _split_playlist_line(line: str):
    """(Praefix, Eintrag) einer Playlist-Zeile — Format wie PlaylistWidget:
    'MODE [N[:CUT]] Titel'. Praefix bleibt beim Umschreiben unveraendert."""
    parts = line.split(" ", 2)
    if len(parts) < 2:
        return None
    if len(parts) == 3 and _PLAYLIST_COUNT_RE.fullmatch(parts[1]):
        return f"{parts[0]} {parts[1]} ", parts[2]
    return f"{parts[0]} ", line.split(" ", 1)[1]


def rewrite_playlists(playlist_dir: str, renames: dict) -> list:
    """Ersetzt in allen Playlist-Dateien (*.txt) Eintraege gemaess renames
    {alter Eintrag: neuer Titel}. Gibt die geaenderten Dateien zurueck."""
    changed = []
    if not renames or not playlist_dir or not os.path.isdir(playlist_dir):
        return changed
    for root, _dirs, files in os.walk(playlist_dir):
        for name in files:
            if not name.lower().endswith(".txt"):
                continue
            path = os.path.join(root, name)
            try:
                with open(path, "r", encoding="utf-8") as f:
                    lines = f.read().splitlines(keepends=True)
            except (OSError, UnicodeDecodeError):
                continue
            out, hits = [], 0
            for line in lines:
                body = line.rstrip("\r\n")
                split = _split_playlist_line(body.strip())
                if split and split[1] in renames:
                    line = split[0] + renames[split[1]] + line[len(body):]
                    hits += 1
                out.append(line)
            if not hits:
                continue
            try:
                with open(path + ".bak_intern106", "w", encoding="utf-8") as f:
                    f.writelines(lines)
                with open(path, "w", encoding="utf-8") as f:
                    f.writelines(out)
                changed.append(path)
                print(f"[Repair#106] Playlist '{name}': {hits} Eintrag/Eintraege umgeschrieben")
            except OSError as e:
                print(f"[Repair#106] WARNUNG: Playlist '{name}' nicht umschreibbar: {e}")
    return changed


def repair_subfolder_duplicates(db: SongDatabase, find_song_file,
                                playlist_dir: str = "") -> int:
    """Findet und repariert alle Doppelgaenger. Rueckgabe: Anzahl Paare."""
    pairs = find_pairs(db, find_song_file)
    if not pairs:
        return 0
    if not db.backup_copy("pre_intern106"):
        print("[Repair#106] Keine Sicherung moeglich — Reparatur ausgelassen")
        return 0
    new_genre_id = db.get_genre_id_by_name("NEW")
    renames = {}
    for a, b in pairs:
        merged = merge_song_fields(a, b)
        props = merge_properties(db.get_properties(a.id), db.get_properties(b.id))
        db.merge_songs(merged, b.id, props, skip_genre_id=new_genre_id)
        for old in (b.title, b.filename):
            if old and old != merged.title:
                renames[old] = merged.title
    # Nur umschreiben, wenn der alte Eintrag nicht noch einen anderen Song trifft
    renames = {old: new for old, new in renames.items()
               if db.get_by_title(old) is None and db.get_by_filename(old) is None}
    rewrite_playlists(playlist_dir, renames)
    print(f"[Repair#106] {len(pairs)} Doppelgaenger zusammengefuehrt")
    return len(pairs)
