"""ZIP-Import: Datei ist schon Variante eines anderen Songs (intern#132).

Fall aus dem Review zu #58: Ein Paket wurde zusammengefasst importiert,
`red feather.mp3` ist also Variante von „Let's Dance“. Ein getrennter
Re-Import darf dafuer keinen zweiten Song auf dieselbe Datei anlegen; er
weist in der Vorschau darauf hin und ueberspringt die Datei. Das gilt fuer
alle Spuren eines Pakets.
"""
import contextlib
import io
from types import SimpleNamespace

import pytest

import main
import zip_import
from song_db import Song, SongDatabase

W = main.P29MainWindow


@pytest.fixture
def db(tmp_path):
    with contextlib.redirect_stdout(io.StringIO()):
        db = SongDatabase(str(tmp_path / "songs.db"))
    yield db
    db.close()


@pytest.fixture
def lets_dance(db):
    """„Let's Dance“ mit „red feather.mp3“ als Variante (frueherer Import)."""
    song = db.insert(Song(filename="let's dance.mp3", title="Let's Dance"))
    db.add_variant(song.id, "music", "Red Feather", "red feather.mp3")
    return song


# ---- song_db ----

def test_variant_owner_findet_song_ohne_gross_klein(db, lets_dance):
    assert db.get_variant_owner("Red Feather.MP3").id == lets_dance.id


def test_variant_owner_nur_varianten_der_art(db, lets_dance):
    assert db.get_variant_owner("let's dance.mp3") is None      # Hauptdatei
    assert db.get_variant_owner("red feather.mp3", "lyric") is None
    assert db.get_variant_owner("unbekannt.mp3") is None


# ---- Import ----

class _Fenster:
    _import_zip_bundles = W._import_zip_bundles
    _zip_same_file_in_library = W._zip_same_file_in_library
    _zip_variant_owner = W._zip_variant_owner
    _zip_linked_owner = W._zip_linked_owner
    _zip_linked_title = W._zip_linked_title

    def __init__(self, db, music_dir, lyrics_dir):
        self.db = db
        self.paths = SimpleNamespace(music_dir=str(music_dir),
                                     lyrics_dir=str(lyrics_dir))
        self.imported = []
        self.player = SimpleNamespace(_load_file=lambda _p: None)
        self.song_list = SimpleNamespace(refresh=lambda: None)
        self.dock_list = SimpleNamespace(show=lambda: None, raise_=lambda: None)

    def _import_single_audio(self, path, **_kw):
        import os
        name = os.path.basename(path)
        self.imported.append(name)
        song = self.db.insert(Song(filename=name, title=name))
        return {"song": song, "status": "new", "dest": path}


@pytest.fixture
def fenster(db, tmp_path, monkeypatch):
    music = tmp_path / "music"
    music.mkdir()
    (music / "red feather.mp3").write_bytes(b"x")    # liegt schon in der Bibliothek
    lyrics = tmp_path / "lyrics"
    lyrics.mkdir()
    src = tmp_path / "zip"
    src.mkdir()
    for name in ("red feather.mp3", "neu.mp3"):
        (src / name).write_bytes(b"x")
    messages = []
    monkeypatch.setattr(main.QMessageBox, "information",
                        lambda _p, _t, text: messages.append(text))
    f = _Fenster(db, music, lyrics)
    f.src = src
    f.messages = messages
    return f


def _bundle(fenster, *names, title=None):
    return {"audio": [{"path": str(fenster.src / n), "label_text": "Instrumental"}
                      for n in names],
            "lyrics": [], "title": title or names[0], "label": "",
            "is_pattern": True, "is_singing": False, "attach_new": False}


def test_hauptspur_als_variante_wird_uebersprungen(fenster, lets_dance):
    fenster._import_zip_bundles(None, [_bundle(fenster, "red feather.mp3")])
    assert fenster.imported == []                   # kein zweiter Song
    assert "red feather.mp3" in fenster.messages[0]
    assert "Let's Dance" in fenster.messages[0]


def test_zusatzspur_als_variante_wird_nicht_angehaengt(fenster, lets_dance, db):
    fenster._import_zip_bundles(None, [_bundle(fenster, "neu.mp3", "red feather.mp3")])
    assert fenster.imported == ["neu.mp3"]
    neu = db.get_by_filename("neu.mp3")
    assert db.get_variants(neu.id, "music") == []
    assert "Let's Dance" in fenster.messages[0]


def test_andere_datei_gleichen_namens_ist_kein_treffer(fenster, lets_dance):
    (fenster.src / "red feather.mp3").write_bytes(b"anders")   # andere Groesse
    assert fenster._zip_variant_owner(str(fenster.src / "red feather.mp3")) is None


def test_erstimport_bleibt_unveraendert(fenster):
    fenster._import_zip_bundles(None, [_bundle(fenster, "red feather.mp3")])
    assert fenster.imported == ["red feather.mp3"]


def test_vorschau_titel(fenster, lets_dance):
    assert fenster._zip_linked_title(str(fenster.src / "red feather.mp3")) == "Let's Dance"
    assert fenster._zip_linked_title(str(fenster.src / "neu.mp3")) is None


# ---- Vorschau ----

def test_vorschau_zeigt_hinweis_ohne_anhaengen(qapp, keep, tmp_path):
    import zipfile
    from zip_import_dialog import ZipImportPreviewDialog
    p = tmp_path / "2002 Red Feather.zip"
    with zipfile.ZipFile(p, "w") as zf:
        for f in ("let's dance.mp3", "red feather.mp3"):
            zf.writestr(f, b"x")
    r = zip_import.analyze([str(p)], dest_dir=str(tmp_path / "out"))
    try:
        r.zips[0].use_split = True
        r.refresh_bundles()
        linked = lambda path: "Let's Dance" if path.endswith("red feather.mp3") else None
        dlg = keep(ZipImportPreviewDialog(
            r, zip_import.ImportLists.defaults(), str(tmp_path / "lists.json"),
            linked_lookup=linked))
        ui = next(u for u in dlg._bundles_ui if u["title"].text() == "Red Feather")
        assert not ui["dup_row"].isHidden()
        assert ui["dup_chk"].isHidden()
        assert "Let's Dance" in ui["dup_lbl"].text()
        other = next(u for u in dlg._bundles_ui if u["title"].text() == "Let's Dance")
        assert other["dup_row"].isHidden()
        by_title = {d["title"]: d for d in dlg.get_decisions()}
        assert by_title["Red Feather"]["attach_new"] is False
    finally:
        zip_import.cleanup(r)
