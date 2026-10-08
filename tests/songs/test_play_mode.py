"""Abspielart eines Playlist-Eintrags, getrennt vom Song-Typ (intern#179).

Ein Other-Song, von Hand in die Playlist gelegt, spielt einmal durch: keine
Patter-Fuellung, die Typ-Spalte zeigt O.
"""
from types import SimpleNamespace

import pytest

import song_types
from playlist_widget import PlaylistEntry, PlaylistManagerWidget, PlaylistWidget
from song_db import Song
from song_types import PlayMode


@pytest.mark.parametrize("flags, play_mode", [
    ((1, 0), PlayMode.LOOP),
    ((1, 1), PlayMode.LOOP),
    ((0, 1), PlayMode.ONCE),
    ((0, 0), PlayMode.ONCE),
])
def test_abspielart_je_song_typ(flags, play_mode):
    assert song_types.play_mode(*flags) is play_mode


def test_kuerzel_aus_datei_wird_abspielart():
    entry = PlaylistEntry(song=Song(), play_mode="S")
    assert entry.play_mode is PlayMode.ONCE
    assert f"{entry.play_mode}" == "S"   # Playlist-Datei und Shortcode bleiben P/S


def _manager(type_filter=0):
    """Nur die Teile des Planners, die _determine_play_mode/_make_entry brauchen;
    Patter-Fuellung auf 'target', Ziellaenge 7 min, jeder Song 3 min lang."""
    mgr = SimpleNamespace(
        _filter_bar=SimpleNamespace(type_filter=type_filter),
        _settings=SimpleNamespace(value=lambda key, default: "target"),
        _pw=SimpleNamespace(_get_song_duration=lambda song: 180.0),
        get_target_duration=lambda: 7.0,
    )
    mgr._apply_patter_fill = lambda e: PlaylistManagerWidget._apply_patter_fill(mgr, e)
    return mgr


def _add(mgr, song):
    play_mode = PlaylistManagerWidget._determine_play_mode(mgr, song)
    return PlaylistManagerWidget._make_entry(mgr, song, play_mode)


def _song(is_pattern, is_singing):
    return Song(filename="x.mp3", is_pattern=is_pattern, is_singing=is_singing,
                loop_in=10.0, loop_out=40.0, base_bpm=128.0)


def test_other_song_spielt_einmal_ohne_patter_fuellung():
    entry = _add(_manager(), _song(False, False))
    assert entry.play_mode is PlayMode.ONCE
    assert entry.loop_count == 0


def test_patter_song_bekommt_patter_fuellung():
    # Gegenprobe: dieselbe Einrichtung fuellt einen Patter auf die Ziellaenge
    entry = _add(_manager(), _song(True, False))
    assert entry.play_mode is PlayMode.LOOP
    assert entry.loop_count > 0


@pytest.mark.parametrize("type_key, play_mode", [
    (song_types.PATTER, PlayMode.LOOP),
    (song_types.SINGING, PlayMode.ONCE),
])
def test_typ_filter_entscheidet_bei_ps_song(type_key, play_mode):
    mgr = _manager(song_types.FILTER_ID[type_key])
    assert PlaylistManagerWidget._determine_play_mode(mgr, _song(True, True)) is play_mode


def test_typ_spalte_zeigt_song_typ(qapp):
    pw = PlaylistWidget(db=None, paths=SimpleNamespace(find_song_file=lambda f: None))
    pw.add_entry(PlaylistEntry(song=_song(False, False), play_mode=PlayMode.ONCE))
    pw.add_entry(PlaylistEntry(song=_song(True, True), play_mode=PlayMode.ONCE))
    assert [pw._pl_table.item(r, 1).text() for r in range(2)] == ["O", "PS"]
    assert [pw._pl_table.item(r, 3).text() for r in range(2)] == ["1", "1"]
