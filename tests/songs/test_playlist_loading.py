"""Playlist-Dateien laden ueber die drei Leser (intern#140, Charakterisierung).

PlaylistWidget, Custom-Filter-Dialog und permanente Custom-Filter lesen dasselbe
Dateiformat. Die Tests halten fest, was sie heute daraus machen.
"""
import contextlib
import io
from types import SimpleNamespace

import pytest
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QFileDialog

from playlist_widget import PlaylistWidget
from song_db import Song, SongDatabase
from song_types import PlayMode
from songdata_widget import CustomFilterDialog, SongFilterBar


@pytest.fixture
def db(tmp_path, keep):
    with contextlib.redirect_stdout(io.StringIO()):
        d = keep(SongDatabase(str(tmp_path / "pl.db")))
    for name in ("Alpha", "Käse", "Zwei Worte"):
        d.insert(Song(filename=f"{name}.mp3", title=name))
    return d


def _ids(db, *titles):
    return {db.get_by_title(t).id for t in titles}


def _write(tmp_path, text, encoding="utf-8"):
    p = tmp_path / "liste.txt"
    p.write_bytes(text.encode(encoding))
    return str(p)


_PATHS = SimpleNamespace(playlist_dir="", find_song_file=lambda f: None)
CONTENT = "P 2 Alpha\nS 1 Käse\nP Zwei Worte\n\nX\n"


def _pick(monkeypatch, path):
    monkeypatch.setattr(QFileDialog, "getOpenFileName",
                        staticmethod(lambda *a, **k: (path, "")))


@pytest.mark.parametrize("encoding", ["utf-8", "cp1252"])
def test_playlist_widget_laedt_utf8_und_cp1252(tmp_path, keep, db, monkeypatch, encoding):
    pw = keep(PlaylistWidget(db=db, paths=_PATHS))
    _pick(monkeypatch, _write(tmp_path, CONTENT, encoding))
    pw._on_load_playlist()
    got = [(e.song.title, e.play_mode, e.loop_count, e.loop_cut_beats)
           for e in pw._playlist]
    assert [(t, c, cut) for t, _m, c, cut in got] == [
        ("Alpha", 2, 0), ("Käse", 1, 0), ("Zwei Worte", 0, 0)]
    assert [m for _t, m, _c, _cut in got] == [PlayMode.LOOP, PlayMode.ONCE, PlayMode.LOOP]


def test_playlist_widget_liest_cut(tmp_path, keep, db, monkeypatch):
    pw = keep(PlaylistWidget(db=db, paths=_PATHS))
    _pick(monkeypatch, _write(tmp_path, "P 2:16 Alpha\n"))
    pw._on_load_playlist()
    assert [(e.loop_count, e.loop_cut_beats) for e in pw._playlist] == [(2, 16)]


@pytest.mark.parametrize("encoding", ["utf-8", "cp1252"])
def test_custom_filter_dialog_laedt_song_ids(tmp_path, keep, db, monkeypatch, encoding):
    dlg = keep(CustomFilterDialog(db, str(tmp_path), []))
    _pick(monkeypatch, _write(tmp_path, CONTENT, encoding))
    dlg._load_slot(0)
    assert dlg._slots[0]["song_ids"] == _ids(db, "Alpha", "Käse", "Zwei Worte")


def test_custom_filter_dialog_versteht_cut(tmp_path, keep, db, monkeypatch):
    dlg = keep(CustomFilterDialog(db, str(tmp_path), []))
    _pick(monkeypatch, _write(tmp_path, "P 2:16 Alpha\n"))
    dlg._load_slot(0)
    assert dlg._slots[0]["song_ids"] == _ids(db, "Alpha")


def _bar(keep, db, tmp_path, path):
    ini = QSettings(str(tmp_path / "f.ini"), QSettings.IniFormat)
    ini.setValue("custom-filter/slot_0", path)
    bar = keep(SongFilterBar(show_custom_filter=True, db=db, settings=ini))
    bar.load_permanent_filters()
    return bar


def test_permanenter_filter_laedt_song_ids(tmp_path, keep, db):
    bar = _bar(keep, db, tmp_path, _write(tmp_path, CONTENT, "cp1252"))
    assert bar._custom_slots[0]["song_ids"] == _ids(db, "Alpha", "Käse", "Zwei Worte")


def test_permanenter_filter_findet_cut_zeilen(tmp_path, keep, db):
    bar = _bar(keep, db, tmp_path, _write(tmp_path, "P 2:16 Alpha\nP 1 Käse\n"))
    assert bar._custom_slots[0]["song_ids"] == _ids(db, "Alpha", "Käse")


def test_playlist_widget_speichert_im_bisherigen_format(tmp_path, keep, db, monkeypatch):
    from playlist_widget import PlaylistEntry
    pw = keep(PlaylistWidget(db=db, paths=_PATHS))
    pw.add_entry(PlaylistEntry(song=db.get_by_title("Alpha"), play_mode=PlayMode.LOOP,
                               loop_count=2, loop_cut_beats=16))
    pw.add_entry(PlaylistEntry(song=db.get_by_title("Käse"), play_mode=PlayMode.ONCE,
                               loop_count=1))
    target = tmp_path / "aus.txt"
    monkeypatch.setattr(QFileDialog, "getSaveFileName",
                        staticmethod(lambda *a, **k: (str(target), "")))
    pw._on_save_playlist()
    assert target.read_bytes().decode("utf-8").splitlines() == [
        "P 2:16 Alpha", "S 1 Käse"]
