"""Abweichende gleichnamige Lyrics-Datei: Rueckfrage in den Song-Daten und
gesammelt nach dem Import (intern#167).

Geprueft werden die echten Methoden von SongDataWidget und P29MainWindow auf
schlanken Ersatzobjekten (ohne DB-Datei, Audio und Docks).
"""
import os
from types import SimpleNamespace

import pytest
from PySide6.QtWidgets import QDialog

import dialogs_lyrics_conflict
import lyrics_files
import main
import songdata_widget
from dialogs_lyrics_conflict import LyricsConflictDialog
from lyrics_files import KEEP_BOTH, REPLACE, USE_EXISTING

W = main.P29MainWindow
NEWER, OLDER = 2_000_000_000, 1_000_000_000


class _Sitzung:
    """Fake der aktuellen Sitzung: kein QObject (Windows-Crash-Falle), nur song/set_song."""

    def __init__(self, song=None, **kw):
        self.song = song
        self.__dict__.update(kw)

    def set_song(self, song):
        self.song = song


def _write(path, text, mtime=None):
    path.write_text(text, encoding="utf-8")
    if mtime is not None:
        os.utime(path, (mtime, mtime))
    return str(path)


@pytest.fixture
def dirs(tmp_path):
    outside, lyrics = tmp_path / "outside", tmp_path / "lyrics"
    outside.mkdir()
    lyrics.mkdir()
    return outside, lyrics


def _paths(lyrics):
    return SimpleNamespace(
        lyrics_dir=str(lyrics),
        to_relative_lyric_filename=lambda p: os.path.relpath(
            p, str(lyrics)).replace(os.sep, "/"))


# ---- Song-Daten: "Lyrics waehlen" ----

class _SongData:
    _lyrics_name_for = songdata_widget.SongDataWidget._lyrics_name_for

    def __init__(self, lyrics):
        self.paths = _paths(lyrics)


@pytest.fixture
def asked(monkeypatch):
    """Ersetzt die Rueckfrage; asked.answer ist die Antwort des Callers."""
    state = SimpleNamespace(conflicts=[], answer=None)

    def _ask(_parent, conflict):
        state.conflicts.append(conflict)
        return state.answer

    monkeypatch.setattr(songdata_widget, "ask_lyrics_conflict", _ask)
    return state


def test_datei_von_ausserhalb_wird_in_den_lyrics_ordner_kopiert(dirs, asked):
    outside, lyrics = dirs
    src = _write(outside / "Song.html", "neu")
    assert _SongData(lyrics)._lyrics_name_for(src) == "Song.html"
    assert (lyrics / "Song.html").read_text(encoding="utf-8") == "neu"
    assert asked.conflicts == []


def test_datei_im_unterordner_des_lyrics_ordners_bleibt_wo_sie_ist(dirs, asked):
    _outside, lyrics = dirs
    (lyrics / "sub").mkdir()
    src = _write(lyrics / "sub" / "Song.html", "text")
    _write(lyrics / "Song.html", "anderer text")
    assert _SongData(lyrics)._lyrics_name_for(src) == "sub/Song.html"
    assert asked.conflicts == []


@pytest.mark.parametrize("answer, name, shown", [
    (REPLACE, "Song.html", "neu"),
    (KEEP_BOTH, "Song_1.html", "neu"),
    (USE_EXISTING, "Song.html", "alt"),
])
def test_abweichende_datei_der_caller_entscheidet(dirs, asked, answer, name, shown):
    outside, lyrics = dirs
    src = _write(outside / "Song.html", "neu")
    _write(lyrics / "Song.html", "alt")
    asked.answer = answer
    assert _SongData(lyrics)._lyrics_name_for(src) == name
    assert (lyrics / name).read_text(encoding="utf-8") == shown
    assert len(asked.conflicts) == 1


def test_abbrechen_laesst_song_und_dateien_unveraendert(dirs, asked):
    outside, lyrics = dirs
    src = _write(outside / "Song.html", "neu")
    _write(lyrics / "Song.html", "alt")
    asked.answer = None
    assert _SongData(lyrics)._lyrics_name_for(src) is None
    assert sorted(p.name for p in lyrics.iterdir()) == ["Song.html"]
    assert (lyrics / "Song.html").read_text(encoding="utf-8") == "alt"


# ---- Listen-Dialog ----

@pytest.fixture
def two_conflicts(dirs):
    outside, lyrics = dirs
    for name, src_mtime, dest_mtime in (("A.html", NEWER, OLDER),
                                        ("B.html", OLDER, NEWER)):
        _write(outside / name, "neu", mtime=src_mtime)
        _write(lyrics / name, "alt", mtime=dest_mtime)
    return [lyrics_files.find_conflict(str(outside / n), str(lyrics))
            for n in ("A.html", "B.html")], lyrics


def test_vorauswahl_nur_eine_juengere_datei_ersetzt(qapp, two_conflicts):
    conflicts, _lyrics = two_conflicts
    dlg = LyricsConflictDialog(conflicts)
    assert dlg.decisions() == [REPLACE, USE_EXISTING]


def test_fuer_alle_setzt_jede_zeile(qapp, two_conflicts):
    conflicts, _lyrics = two_conflicts
    dlg = LyricsConflictDialog(conflicts)
    dlg._combo_all.setCurrentIndex(dlg._combo_all.findData(KEEP_BOTH))
    dlg._apply_to_all(dlg._combo_all.currentIndex())
    assert dlg.decisions() == [KEEP_BOTH, KEEP_BOTH]


@pytest.fixture
def same_target(dirs):
    """Zwei juengere, verschiedene Song.html aus zwei Ordnern, beide mit
    demselben Ziel im Lyrics-Ordner (Review zu #101)."""
    outside, lyrics = dirs
    _write(lyrics / "Song.html", "alt", mtime=OLDER)
    conflicts = []
    for sub in ("A", "B"):
        (outside / sub).mkdir()
        src = _write(outside / sub / "Song.html", f"neu {sub}", mtime=NEWER)
        conflicts.append(lyrics_files.find_conflict(src, str(lyrics)))
    return conflicts, lyrics


def test_dieselbe_zieldatei_ersetzt_nur_die_erste_zeile(qapp, same_target):
    conflicts, _lyrics = same_target
    dlg = LyricsConflictDialog(conflicts)
    assert dlg.decisions() == [REPLACE, KEEP_BOTH]
    second = dlg._combos[1]
    assert not second.model().item(second.findData(REPLACE)).isEnabled()
    dlg._combo_all.setCurrentIndex(dlg._combo_all.findData(REPLACE))
    dlg._apply_to_all(dlg._combo_all.currentIndex())
    assert dlg.decisions() == [REPLACE, KEEP_BOTH]


def test_dieselbe_zieldatei_bisherige_fassung_bleibt_als_bak(
        qapp, same_target, monkeypatch):
    conflicts, lyrics = same_target
    monkeypatch.setattr(LyricsConflictDialog, "exec", lambda self: QDialog.Accepted)
    names = dialogs_lyrics_conflict.resolve_with_dialog(None, conflicts)
    assert names == ["Song.html", "Song_1.html"]
    assert (lyrics / "Song.html.bak").read_text(encoding="utf-8") == "alt"
    assert (lyrics / "Song.html").read_text(encoding="utf-8") == "neu A"
    assert (lyrics / "Song_1.html").read_text(encoding="utf-8") == "neu B"


def test_fehler_im_listen_dialog_werden_gesammelt_gemeldet(
        qapp, two_conflicts, monkeypatch):
    conflicts, lyrics = two_conflicts
    monkeypatch.setattr(LyricsConflictDialog, "exec", lambda self: QDialog.Accepted)
    monkeypatch.setattr(LyricsConflictDialog, "decisions",
                        lambda self: [REPLACE, REPLACE])

    def failing(_conflict, _decision):
        raise OSError("gesperrt")
    monkeypatch.setattr(lyrics_files, "resolve", failing)
    shown = []
    monkeypatch.setattr(dialogs_lyrics_conflict.QMessageBox, "warning",
                        lambda _parent, _title, text: shown.append(text))
    names = dialogs_lyrics_conflict.resolve_with_dialog(None, conflicts)
    assert names == ["A.html", "B.html"]            # vorhandene bleiben verknuepft
    assert len(shown) == 1
    assert "A.html: gesperrt" in shown[0] and "B.html: gesperrt" in shown[0]


def test_abbrechen_im_listen_dialog_aendert_nichts(qapp, two_conflicts, monkeypatch):
    conflicts, lyrics = two_conflicts
    monkeypatch.setattr(LyricsConflictDialog, "exec", lambda self: QDialog.Rejected)
    names = dialogs_lyrics_conflict.resolve_with_dialog(None, conflicts)
    assert names == ["A.html", "B.html"]
    assert (lyrics / "A.html").read_text(encoding="utf-8") == "alt"
    assert sorted(p.name for p in lyrics.iterdir()) == ["A.html", "B.html"]


# ---- Import ----

class _Fenster:
    _LYRICS_EXTENSIONS = W._LYRICS_EXTENSIONS
    _build_lyrics_map = W._build_lyrics_map
    _find_and_import_lyrics = W._find_and_import_lyrics
    _resolve_import_lyrics_conflicts = W._resolve_import_lyrics_conflicts

    def __init__(self, lyrics):
        self.paths = _paths(lyrics)
        self.updated = []
        self.session = _Sitzung()       # kein Song geladen
        self.db = SimpleNamespace(
            update_lyrics_file=lambda sid, name: self.updated.append((sid, name)))

    def _parse_filename(self, name):
        return (name, "")


def test_import_verknuepft_die_vorhandene_datei_und_merkt_den_konflikt(dirs):
    outside, lyrics = dirs
    _write(outside / "Song.html", "neu")
    _write(lyrics / "Song.html", "alt")
    found = []
    fenster = _Fenster(lyrics)
    assert fenster._find_and_import_lyrics("Song", str(outside), found) == "Song.html"
    assert (lyrics / "Song.html").read_text(encoding="utf-8") == "alt"
    assert [c.name for c in found] == ["Song.html"]


def test_import_ohne_abweichung_merkt_nichts(dirs):
    outside, lyrics = dirs
    _write(outside / "Song.html", "gleich")
    _write(lyrics / "Song.html", "gleich")
    found = []
    assert _Fenster(lyrics)._find_and_import_lyrics(
        "Song", str(outside), found) == "Song.html"
    assert found == []


def test_nach_dem_import_wechseln_songs_bei_beide_behalten_die_datei(
        qapp, two_conflicts, monkeypatch):
    conflicts, lyrics = two_conflicts
    monkeypatch.setattr(LyricsConflictDialog, "exec", lambda self: QDialog.Accepted)
    monkeypatch.setattr(LyricsConflictDialog, "decisions",
                        lambda self: [KEEP_BOTH, REPLACE])
    # Das Ersatzfenster ist kein QWidget und taugt nicht als Dialog-Elter.
    monkeypatch.setattr(
        main, "resolve_with_dialog",
        lambda _parent, c: dialogs_lyrics_conflict.resolve_with_dialog(None, c))
    fenster = _Fenster(lyrics)
    # Zwei Songs teilen sich A.html, einer nutzt B.html
    fenster._resolve_import_lyrics_conflicts(
        [(1, conflicts[0]), (2, conflicts[0]), (3, conflicts[1])])
    assert fenster.updated == [(1, "A_1.html"), (2, "A_1.html")]
    assert (lyrics / "A.html").read_text(encoding="utf-8") == "alt"
    assert (lyrics / "A_1.html").read_text(encoding="utf-8") == "neu"
    assert (lyrics / "B.html").read_text(encoding="utf-8") == "neu"
    assert (lyrics / "B.html.bak").read_text(encoding="utf-8") == "alt"


def test_import_ohne_konflikte_zeigt_keinen_dialog(dirs, monkeypatch):
    _outside, lyrics = dirs

    def _no_dialog(*_a, **_kw):
        raise AssertionError("Dialog darf nicht erscheinen")

    monkeypatch.setattr(main, "resolve_with_dialog", _no_dialog)
    _Fenster(lyrics)._resolve_import_lyrics_conflicts([])


@pytest.mark.parametrize("shown, reloads", [("B.html", 1), ("Anderer.html", 0)])
def test_nach_dem_ersetzen_zeigt_das_lyric_fenster_den_neuen_text(
        qapp, two_conflicts, monkeypatch, shown, reloads):
    conflicts, lyrics = two_conflicts
    monkeypatch.setattr(LyricsConflictDialog, "exec", lambda self: QDialog.Accepted)
    monkeypatch.setattr(LyricsConflictDialog, "decisions", lambda self: [REPLACE])
    monkeypatch.setattr(
        main, "resolve_with_dialog",
        lambda _parent, c: dialogs_lyrics_conflict.resolve_with_dialog(None, c))
    fenster = _Fenster(lyrics)
    fenster.session.set_song(SimpleNamespace(id=3))
    shown_path = str(lyrics / shown)
    fenster.lyrics_widget = SimpleNamespace(is_showing=lambda p: p == shown_path)
    calls = []
    fenster._reload_current_lyrics = lambda: calls.append(1)
    fenster._resolve_import_lyrics_conflicts([(3, conflicts[1])])
    assert len(calls) == reloads
