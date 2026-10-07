"""Song-Typ "Other": weder Patter noch Singing (intern#170).

Die Definition steht in song_types; geprueft wird sie selbst und ihre Nutzung
in Song-Daten (drittes Haekchen), Filterleiste, Statistik und Regeln.
"""
import contextlib
import io
import tempfile
from types import SimpleNamespace

import pytest
from PySide6.QtWidgets import QCheckBox

import song_types
import songdata_widget
from rule_definitions import register_v1_definitions
from rule_engine import RuleEngine
from song_db import Song, SongDatabase
from song_types import OTHER, PATTER, SINGING

# (is_pattern, is_singing) -> Kuerzel
FLAGS = {(1, 0): "P", (0, 1): "S", (1, 1): "PS", (0, 0): "O"}


@pytest.mark.parametrize("flags, tag", FLAGS.items())
def test_kuerzel_je_schalterstellung(flags, tag):
    assert song_types.type_tag(*flags) == tag


@pytest.mark.parametrize("type_key, tags", [
    (PATTER, {"P", "PS"}),
    (SINGING, {"S", "PS"}),
    (OTHER, {"O"}),
])
def test_other_schliesst_patter_und_singing_aus(type_key, tags):
    hits = {tag for flags, tag in FLAGS.items()
            if song_types.matches(*flags, type_key)}
    assert hits == tags


def test_unbekannter_typ_ist_ein_fehler():
    with pytest.raises(ValueError):
        song_types.matches(1, 0, "round")


# ---- Song-Daten: drittes Haekchen ----

class _SongData:
    _sync_other_checkbox = songdata_widget.SongDataWidget._sync_other_checkbox
    _on_type_toggled = songdata_widget.SongDataWidget._on_type_toggled
    _on_other_toggled = songdata_widget.SongDataWidget._on_other_toggled

    def __init__(self, is_pattern, is_singing):
        self.saves = 0
        self.chk_pattern, self.chk_singing, self.chk_other = (
            QCheckBox(), QCheckBox(), QCheckBox())
        self.chk_pattern.toggled.connect(self._on_type_toggled)
        self.chk_singing.toggled.connect(self._on_type_toggled)
        self.chk_other.toggled.connect(self._on_other_toggled)
        self.chk_pattern.setChecked(bool(is_pattern))
        self.chk_singing.setChecked(bool(is_singing))
        self._sync_other_checkbox()
        self.saves = 0

    def _auto_save(self, *_args):
        self.saves += 1

    def state(self):
        return (self.chk_pattern.isChecked(), self.chk_singing.isChecked(),
                self.chk_other.isChecked())


@pytest.mark.parametrize("flags", FLAGS)
def test_other_ist_an_wenn_patter_und_singing_aus_sind(qapp, flags):
    w = _SongData(*flags)
    assert w.state()[2] == (flags == (0, 0))


def test_other_ankreuzen_schaltet_patter_und_singing_ab(qapp):
    w = _SongData(1, 1)
    w.chk_other.setChecked(True)
    assert w.state() == (False, False, True)
    assert w.saves == 1


def test_patter_ankreuzen_schaltet_other_ab(qapp):
    w = _SongData(0, 0)
    w.chk_pattern.setChecked(True)
    assert w.state() == (True, False, False)
    assert w.saves == 1


def test_other_laesst_sich_nicht_einfach_abwaehlen(qapp):
    """Ohne Patter oder Singing bliebe ein Song ohne Typ — das ist Other."""
    w = _SongData(0, 0)
    w.chk_other.setChecked(False)
    assert w.state() == (False, False, True)
    assert w.saves == 0


def test_letzten_typ_abwaehlen_macht_den_song_zu_other(qapp):
    w = _SongData(0, 1)
    w.chk_singing.setChecked(False)
    assert w.state() == (False, False, True)


# ---- Filterleiste ----

def _songs():
    return [SimpleNamespace(title=tag, filename=f"{tag}.mp3", label="",
                            is_pattern=p, is_singing=s, quality=0, id=i,
                            date_added="")
            for i, ((p, s), tag) in enumerate(FLAGS.items(), start=1)]


@pytest.mark.parametrize("filter_id, tags", [
    (0, ["O", "P", "PS", "S"]),
    (1, ["P", "PS"]),
    (2, ["PS", "S"]),
    (3, ["O"]),
])
def test_typ_filter_der_songliste(qapp, filter_id, tags):
    bar = songdata_widget.SongFilterBar()
    bar.set_type_filter(filter_id)
    assert bar.type_filter == filter_id
    assert sorted(s.title for s in bar.filter_and_sort(_songs())) == tags


# ---- Statistik ----

@pytest.fixture
def db(tmp_path):
    with contextlib.redirect_stdout(io.StringIO()):
        db = SongDatabase(str(tmp_path / "types.db"))
    for (p, s), tag in FLAGS.items():
        db.insert(Song(filename=f"{tag}.mp3", title=tag,
                       is_pattern=p, is_singing=s))
    yield db
    db.close()


@pytest.mark.parametrize("type_key, tags", [
    (None, ["O", "P", "PS", "S"]),
    ("pattern", ["P", "PS"]),
    ("singing", ["PS", "S"]),
    ("other", ["O"]),
])
def test_statistik_listet_songs_je_typ(db, type_key, tags):
    assert sorted(r[1] for r in db.songs_by_type(type_key)) == tags


# ---- Regeln ----

def test_regeln_kennen_other_als_bedingung_und_bei_load_song():
    eng = RuleEngine(tempfile.gettempdir())
    register_v1_definitions(eng)
    assert "song_type_is_other" in eng.registry.conditions
    choices = eng.registry.actions["load_song"].params_schema["type"]["choices"]
    assert choices == ["Singing", "Patter", "Other"]
