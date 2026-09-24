"""intern#106: Doppelgaenger von Unterordner-Songs erkennen und zusammenfuehren."""
import pytest

from song_db import Song, SongDatabase
from subfolder_duplicate_repair import find_pairs, repair_subfolder_duplicates


@pytest.fixture
def db(tmp_path):
    d = SongDatabase(str(tmp_path / "test.db"))
    d.seed_default_genres()
    yield d
    d.close()


def _finder(existing):
    """find_song_file-Ersatz: nur die genannten DB-Dateinamen sind auffindbar."""
    return lambda name: f"X:/music/{name}" if name in existing else None


def _make_pair(db):
    """Original per Import (nur Pattern) + Doppelgaenger wie bis v0.158."""
    a = db.insert(Song(filename="Patter/Get_Lucky.mp3", title="Get Lucky",
                       label="RYL 101", is_pattern=1, is_singing=0))
    b = db.get_or_create("Get_Lucky.mp3")   # Default: Pattern + Singing
    return a, b


def test_findet_doppelgaenger(db):
    a, b = _make_pair(db)
    pairs = find_pairs(db, _finder({"Patter/Get_Lucky.mp3"}))
    assert [(p.id, q.id) for p, q in pairs] == [(a.id, b.id)]


def test_legitimer_song_im_slot_stamm_bleibt(db):
    _make_pair(db)
    finder = _finder({"Patter/Get_Lucky.mp3", "Get_Lucky.mp3"})
    assert find_pairs(db, finder) == []


def test_offline_laufwerk_wird_nicht_angefasst(db):
    _make_pair(db)
    assert find_pairs(db, _finder(set())) == []


def test_mehrdeutiger_basename_wird_nicht_angefasst(db):
    _make_pair(db)
    db.insert(Song(filename="Singing/Get_Lucky.mp3", title="Get Lucky 2"))
    finder = _finder({"Patter/Get_Lucky.mp3", "Singing/Get_Lucky.mp3"})
    assert find_pairs(db, finder) == []


def test_zusammenfuehren_uebernimmt_aenderungen_des_doppelgaengers(db):
    a, b = _make_pair(db)
    # Nutzer hat am Doppelgaenger korrigiert und gespielt
    b.is_singing = 0
    b.base_bpm = 124.0
    db.update(b)
    db.set_property(b.id, "marker_1_time", "12.5")
    loc = db.insert_location("Club")
    db.log_play(b.id, loc.id)
    db.log_play(a.id, loc.id)

    n = repair_subfolder_duplicates(db, _finder({"Patter/Get_Lucky.mp3"}))

    assert n == 1
    assert db.get_by_id(b.id) is None
    merged = db.get_by_id(a.id)
    assert merged.filename == "Patter/Get_Lucky.mp3"
    assert (merged.is_pattern, merged.is_singing) == (1, 0)
    assert merged.base_bpm == 124.0
    # Unveraenderte Defaults am Doppelgaenger ueberschreiben das Original nicht
    assert merged.title == "Get Lucky"
    assert merged.label == "RYL 101"
    assert db.get_properties(a.id).get("marker_1_time") == "12.5"
    hist = db._conn.execute(
        "SELECT COUNT(*) FROM play_history WHERE song_id = ?", (a.id,)).fetchone()[0]
    assert hist == 2
    count = db._conn.execute(
        "SELECT play_count FROM song_location_stats WHERE song_id = ? AND location_id = ?",
        (a.id, loc.id)).fetchone()[0]
    assert count == 2
    assert len(db.get_all()) == 1


def test_default_pattern_singing_ueberschreibt_import_nicht(db):
    a, b = _make_pair(db)   # b unveraendert: P+S Default
    repair_subfolder_duplicates(db, _finder({"Patter/Get_Lucky.mp3"}))
    merged = db.get_by_id(a.id)
    assert (merged.is_pattern, merged.is_singing) == (1, 0)


_FIND_A = _finder({"Patter/Get_Lucky.mp3"})


def test_pattern_singing_werden_als_paar_uebernommen(db):
    """Echter Fall: Original Pattern, am Doppelgaenger auf Singing umgestellt.
    Feldweise kaeme (0,0) heraus — weder Pattern noch Singing."""
    a, b = _make_pair(db)
    b.is_pattern, b.is_singing = 0, 1
    db.update(b)
    repair_subfolder_duplicates(db, _FIND_A)
    merged = db.get_by_id(a.id)
    assert (merged.is_pattern, merged.is_singing) == (0, 1)


def test_titel_mit_leerzeichen_vor_endung_gilt_nicht_als_aenderung(db):
    """Echter Fall 'ESP 446 - Barbie .mp3': der gespeicherte Titel ist ohne
    das Leerzeichen am Ende — das ist keine Nutzer-Aenderung."""
    a = db.insert(Song(filename="Patter/ESP 446 - Barbie .mp3", title="Barbie",
                       label="ESP 446", is_pattern=1, is_singing=0))
    b = db.get_or_create("ESP 446 - Barbie .mp3")
    b.title = "ESP 446 - Barbie"
    db.update(b)
    repair_subfolder_duplicates(db, _finder({a.filename}))
    merged = db.get_by_id(a.id)
    assert (merged.title, merged.label) == ("Barbie", "ESP 446")


def test_songdauer_als_loop_out_ueberschreibt_echten_loop_nicht(db):
    a, b = _make_pair(db)
    a.loop_in, a.loop_out = 12.0, 180.0
    db.update(a)
    b.loop_out = 229.0        # beim Laden automatisch eingetragene Songdauer
    db.update(b)
    repair_subfolder_duplicates(db, _FIND_A)
    merged = db.get_by_id(a.id)
    assert (merged.loop_in, merged.loop_out) == (12.0, 180.0)


def test_loop_des_doppelgaengers_wenn_original_keinen_hat(db):
    a, b = _make_pair(db)
    b.loop_out = 229.0
    db.update(b)
    repair_subfolder_duplicates(db, _FIND_A)
    assert db.get_by_id(a.id).loop_out == 229.0


def test_echter_loop_am_doppelgaenger_gewinnt(db):
    a, b = _make_pair(db)
    a.loop_in, a.loop_out = 12.0, 180.0
    db.update(a)
    b.loop_in, b.loop_out = 15.0, 190.0
    db.update(b)
    repair_subfolder_duplicates(db, _FIND_A)
    merged = db.get_by_id(a.id)
    assert (merged.loop_in, merged.loop_out) == (15.0, 190.0)


def test_varianten_werden_nur_komplett_uebernommen(db):
    a, b = _make_pair(db)
    db.set_property(a.id, "music_1_file", "Patter/Get_Lucky_alt.mp3")
    db.set_property(a.id, "music_1_name", "Alt")
    db.set_property(a.id, "music_2_name", "Zweite")
    db.set_property(b.id, "music_1_name", "Neu")
    repair_subfolder_duplicates(db, _FIND_A)
    props = db.get_properties(a.id)
    assert props.get("music_1_name") == "Neu"
    assert "music_1_file" not in props          # keine Mischung aus A und B
    assert props.get("music_2_name") == "Zweite"


def test_genre_new_des_doppelgaengers_wird_nicht_uebernommen(db):
    a, b = _make_pair(db)
    new_id = db.get_genre_id_by_name("NEW")
    db._conn.execute("DELETE FROM song_genres WHERE song_id = ?", (a.id,))
    db._conn.commit()
    repair_subfolder_duplicates(db, _FIND_A)
    assert new_id not in [gid for gid, _ in db.get_genres_for_song(a.id)]


def test_basename_vergleich_ohne_gross_kleinschreibung(db):
    a = db.insert(Song(filename="Patter/Get_Lucky.MP3", title="Get Lucky",
                       is_pattern=1, is_singing=0))
    b = db.get_or_create("get_lucky.mp3")
    pairs = find_pairs(db, _finder({a.filename}))
    assert [(p.id, q.id) for p, q in pairs] == [(a.id, b.id)]


def test_sicherung_vor_der_reparatur(db, tmp_path):
    _make_pair(db)
    repair_subfolder_duplicates(db, _FIND_A)
    assert list(tmp_path.glob("test.db.bak_pre_intern106_*"))


def test_ohne_paare_keine_sicherung(db, tmp_path):
    repair_subfolder_duplicates(db, _FIND_A)
    assert not list(tmp_path.glob("test.db.bak_pre_intern106_*"))


def test_playlist_wird_auf_neuen_titel_umgeschrieben(db, tmp_path):
    a = db.insert(Song(filename="Sing/DR 86 - Tom Dooley.mp3", title="Tom Dooley",
                       label="DR 86", is_pattern=0, is_singing=1))
    db.get_or_create("DR 86 - Tom Dooley.mp3")  # Titel = Rohtitel
    pl_dir = tmp_path / "playlists"
    pl_dir.mkdir()
    pl = pl_dir / "Abend.txt"
    pl.write_text("S 0 DR 86 - Tom Dooley\nP 3 Anderer Song\n", encoding="utf-8")

    repair_subfolder_duplicates(db, _finder({a.filename}), str(pl_dir))

    assert pl.read_text(encoding="utf-8") == "S 0 Tom Dooley\nP 3 Anderer Song\n"
    assert (pl_dir / "Abend.txt.bak_intern106").read_text(encoding="utf-8") \
        == "S 0 DR 86 - Tom Dooley\nP 3 Anderer Song\n"


def test_zusammenfuehren_ist_atomar(db):
    """Scheitert das Zusammenfuehren mittendrin, bleibt alles wie vorher."""
    a, b = _make_pair(db)
    merged = db.get_by_id(a.id)
    merged.title = "Veraendert"
    with pytest.raises(Exception):
        db.merge_songs(merged, b.id, {"kaputt": object()})
    assert db.get_by_id(a.id).title == "Get Lucky"
    assert db.get_by_id(b.id) is not None


# ---- Laden: kein neuer Doppelgaenger -------------------------------------

def test_laden_aus_unterordner_legt_keinen_doppelgaenger_an(db):
    a = db.insert(Song(filename="Sub/X.mp3", title="X"))
    song = db.get_or_create_for_file("Sub/X.mp3")
    assert song.id == a.id
    assert len(db.get_all()) == 1


def test_laden_unbekannter_datei_legt_neu_an(db):
    song = db.get_or_create_for_file("Neu.mp3")
    assert song.filename == "Neu.mp3"
    assert len(db.get_all()) == 1
