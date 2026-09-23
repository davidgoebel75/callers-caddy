"""Reparatur: Doppelgaenger von Songs aus Musik-Unterordnern (intern#106).

Bis v0.158 hat _on_file_loaded() einen geladenen Song nur ueber den Basename
gesucht. Lag die Datei in einem Unterordner eines Musik-Slots (DB-Eintrag mit
relativem Pfad, z.B. 'Patter/Song.mp3'), fand get_or_create('Song.mp3') nichts
und legte einen zweiten Eintrag mit Default-Werten an (Pattern + Singing).
Alle Aenderungen in den Song-Daten landeten danach an diesem Doppelgaenger.

Diese Reparatur fuehrt jeden Doppelgaenger B in sein Original A zurueck:
- Songs-Felder: B gewinnt, wo der Nutzer dort etwas geaendert hat (Wert
  weicht vom Anlage-Default aus get_or_create ab). Sonst bleibt A.
  filename und date_added bleiben immer von A.
- song_properties (Marker, Varianten, Extended Data): B gewinnt pro Key.
- Genres: Vereinigung, ohne das bei B automatisch vergebene "NEW".
- play_history wird auf A umgehaengt, song_location_stats zusammengefuehrt.
Danach wird B geloescht.

Ein Paar gilt nur als Doppelgaenger, wenn eindeutig: B hat keinen Ordnerpfad,
genau EIN Eintrag A hat einen relativen Pfad mit gleichem Basename, A's Datei
ist auffindbar und B's Datei NICHT (sonst waere B ein legitimer Song im
Slot-Stamm, oder das Laufwerk ist gerade nicht erreichbar).
"""
import os
import posixpath

from song_db import Song, SongDatabase

# Songs-Felder, die vom Doppelgaenger uebernommen werden koennen
_MERGE_FIELDS = ("artist", "label", "quality", "base_bpm", "standard_tempo",
                 "pitch", "volume", "loop_in", "loop_out", "loop_offset_ms",
                 "lyrics_file", "is_pattern", "is_singing", "err")


def find_pairs(db: SongDatabase, find_song_file) -> list:
    """Liefert [(original, doppelgaenger), ...] als Song-Paare."""
    songs = db.get_all()
    by_base = {}
    for s in songs:
        if "/" in s.filename:
            by_base.setdefault(posixpath.basename(s.filename), []).append(s)
    pairs = []
    for b in songs:
        if "/" in b.filename:
            continue
        candidates = by_base.get(b.filename, [])
        if len(candidates) != 1:
            continue
        a = candidates[0]
        if find_song_file(a.filename) and not find_song_file(b.filename):
            pairs.append((a, b))
    return pairs


def _merge_song_fields(a: Song, b: Song) -> Song:
    default = Song(filename=b.filename,
                   title=os.path.splitext(b.filename)[0],
                   is_pattern=1, is_singing=1)
    if b.title != default.title:
        a.title = b.title
    for field in _MERGE_FIELDS:
        value = getattr(b, field)
        if value != getattr(default, field):
            setattr(a, field, value)
    return a


def merge_pair(db: SongDatabase, a: Song, b: Song):
    """Fuehrt Doppelgaenger b in Original a zusammen und loescht b."""
    conn = db._conn
    db.update(_merge_song_fields(a, b))

    conn.execute(
        "INSERT OR REPLACE INTO song_properties (song_id, key, value) "
        "SELECT ?, key, value FROM song_properties WHERE song_id = ?",
        (a.id, b.id))
    conn.execute("DELETE FROM song_properties WHERE song_id = ?", (b.id,))

    new_gid = db.get_genre_id_by_name("NEW")
    conn.execute(
        "INSERT OR IGNORE INTO song_genres (song_id, genre_id) "
        "SELECT ?, genre_id FROM song_genres WHERE song_id = ? AND genre_id != ?",
        (a.id, b.id, new_gid))

    conn.execute("UPDATE play_history SET song_id = ? WHERE song_id = ?",
                 (a.id, b.id))
    conn.execute(
        "INSERT INTO song_location_stats (song_id, location_id, last_played, play_count) "
        "SELECT ?, location_id, last_played, play_count "
        "FROM song_location_stats WHERE song_id = ? "
        "ON CONFLICT(song_id, location_id) DO UPDATE SET "
        "  last_played = MAX(last_played, excluded.last_played), "
        "  play_count = play_count + excluded.play_count",
        (a.id, b.id))
    conn.commit()

    # Entfernt B samt Rest-Genres, Rest-Stats und potential_ignored
    db.delete(b.id)
    print(f"[Repair#106] Doppelgaenger #{b.id} '{b.filename}' in "
          f"#{a.id} '{a.filename}' zusammengefuehrt")


def repair_subfolder_duplicates(db: SongDatabase, find_song_file) -> int:
    """Findet und repariert alle Doppelgaenger. Rueckgabe: Anzahl Paare."""
    pairs = find_pairs(db, find_song_file)
    for a, b in pairs:
        merge_pair(db, a, b)
    return len(pairs)
