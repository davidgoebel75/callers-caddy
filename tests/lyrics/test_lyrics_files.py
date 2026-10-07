"""Lyrics-Dateien in den Lyrics-Ordner uebernehmen: gleichnamige Datei mit
anderem Inhalt erkennen, Entscheidung des Callers ausfuehren (intern#167).
"""
import os

import pytest

import lyrics_files
from lyrics_files import KEEP_BOTH, NEWER, OLDER, REPLACE, UNCLEAR, USE_EXISTING


@pytest.fixture
def dirs(tmp_path):
    outside, lyrics = tmp_path / "outside", tmp_path / "lyrics"
    outside.mkdir()
    lyrics.mkdir()
    return outside, lyrics


def _write(path, text, mtime=None):
    path.write_text(text, encoding="utf-8")
    if mtime is not None:
        os.utime(path, (mtime, mtime))
    return str(path)


def test_ohne_gleichnamige_datei_kein_konflikt_und_kopie(dirs):
    outside, lyrics = dirs
    src = _write(outside / "Song.html", "neu")
    assert lyrics_files.find_conflict(src, str(lyrics)) is None
    assert lyrics_files.adopt(src, str(lyrics)) == "Song.html"
    assert (lyrics / "Song.html").read_text(encoding="utf-8") == "neu"


def test_gleicher_inhalt_ist_kein_konflikt_trotz_anderem_datum(dirs):
    outside, lyrics = dirs
    src = _write(outside / "Song.html", "gleich", mtime=2_000_000_000)
    _write(lyrics / "Song.html", "gleich", mtime=1_000_000_000)
    assert lyrics_files.find_conflict(src, str(lyrics)) is None


def test_datei_aus_dem_lyrics_ordner_selbst_ist_kein_konflikt(dirs):
    _outside, lyrics = dirs
    src = _write(lyrics / "Song.html", "text")
    assert lyrics_files.find_conflict(src, str(lyrics)) is None


def test_anderer_inhalt_bei_gleicher_groesse_ist_ein_konflikt(dirs):
    outside, lyrics = dirs
    src = _write(outside / "Song.html", "neu")
    _write(lyrics / "Song.html", "alt")
    conflict = lyrics_files.find_conflict(src, str(lyrics))
    assert conflict is not None
    assert conflict.name == "Song.html"
    assert conflict.src_size == conflict.dest_size == 3


@pytest.mark.parametrize("src_mtime, dest_mtime, guess", [
    (1_000_000_100, 1_000_000_000, NEWER),
    (1_000_000_000, 1_000_000_100, OLDER),
    (1_000_000_001, 1_000_000_000, UNCLEAR),     # innerhalb der Toleranz
])
def test_vermutung_aus_dem_aenderungsdatum(dirs, src_mtime, dest_mtime, guess):
    outside, lyrics = dirs
    src = _write(outside / "Song.html", "neu", mtime=src_mtime)
    _write(lyrics / "Song.html", "alt", mtime=dest_mtime)
    assert lyrics_files.find_conflict(src, str(lyrics)).guess == guess


def test_adopt_laesst_eine_vorhandene_datei_unberuehrt(dirs):
    outside, lyrics = dirs
    src = _write(outside / "Song.html", "neu")
    _write(lyrics / "Song.html", "alt")
    assert lyrics_files.adopt(src, str(lyrics)) == "Song.html"
    assert (lyrics / "Song.html").read_text(encoding="utf-8") == "alt"


@pytest.fixture
def conflict(dirs):
    outside, lyrics = dirs
    src = _write(outside / "Song.html", "neu")
    _write(lyrics / "Song.html", "alt")
    return lyrics_files.find_conflict(src, str(lyrics)), lyrics


def test_ersetzen_sichert_die_alte_fassung_als_bak(conflict):
    c, lyrics = conflict
    assert lyrics_files.resolve(c, REPLACE) == "Song.html"
    assert (lyrics / "Song.html").read_text(encoding="utf-8") == "neu"
    assert (lyrics / "Song.html.bak").read_text(encoding="utf-8") == "alt"


def test_beide_behalten_legt_die_neue_mit_nummer_daneben(conflict):
    c, lyrics = conflict
    (lyrics / "Song_1.html").write_text("belegt", encoding="utf-8")
    assert lyrics_files.resolve(c, KEEP_BOTH) == "Song_2.html"
    assert (lyrics / "Song_2.html").read_text(encoding="utf-8") == "neu"
    assert (lyrics / "Song.html").read_text(encoding="utf-8") == "alt"
    assert (lyrics / "Song_1.html").read_text(encoding="utf-8") == "belegt"


def test_vorhandene_weiterverwenden_aendert_nichts(conflict):
    c, lyrics = conflict
    assert lyrics_files.resolve(c, USE_EXISTING) == "Song.html"
    assert sorted(p.name for p in lyrics.iterdir()) == ["Song.html"]
    assert (lyrics / "Song.html").read_text(encoding="utf-8") == "alt"


def test_is_inside_erkennt_ordner_und_unterordner(dirs):
    outside, lyrics = dirs
    assert lyrics_files.is_inside(str(lyrics / "Song.html"), str(lyrics))
    assert lyrics_files.is_inside(str(lyrics / "sub" / "Song.html"), str(lyrics))
    assert not lyrics_files.is_inside(str(outside / "Song.html"), str(lyrics))
    # Nachbarordner mit gleichem Namensanfang zaehlt nicht
    assert not lyrics_files.is_inside(str(lyrics) + "2/Song.html", str(lyrics))
