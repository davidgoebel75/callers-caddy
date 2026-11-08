"""Sync-Point-Schluessel im Lyric-Fenster (intern#140, Charakterisierung).

Die Schluessel `lyric_sync_m<musik>_l<lyric>_<index>` liegen als song_properties
in der DB. Der Test haelt fest, was geschrieben, gelesen und kopiert wird.
"""
import pytest
from PySide6.QtCore import QSettings

from lyrics_widget import LyricsWidget


class FakeDb:
    """Nur die zwei Property-Methoden, die das Lyric-Fenster nutzt."""

    def __init__(self, props=None):
        self.props = dict(props or {})

    def get_properties(self, song_id):
        return {k: v for k, v in self.props.items() if v != ""}

    def set_property(self, song_id, key, value):
        self.props[key] = value


@pytest.fixture
def make_widget(keep, tmp_path):
    from path_manager import PathManager

    def _make(props=None, music_slot=1, lyric_slot=1):
        ini = QSettings(str(tmp_path / "w.ini"), QSettings.IniFormat)
        w = keep(LyricsWidget(PathManager(ini)))
        w._db = FakeDb(props)
        w._sync_song_id = 7
        w._sync_music_slot = music_slot
        w._sync_lyric_slot = lyric_slot
        return w
    return _make


def test_anker_werden_durchnummeriert_geschrieben(make_widget):
    w = make_widget()
    w._sync_anchors = [[20.0, 5], [12.5, 3]]
    w._persist_sync_anchors()
    assert w._db.props == {"lyric_sync_m1_l1_1": "12.50|3",
                           "lyric_sync_m1_l1_2": "20.00|5"}


def test_anker_der_kombi_werden_geladen_andere_ignoriert(make_widget):
    w = make_widget({"lyric_sync_m2_l3_1": "9.00|1",
                     "lyric_sync_m2_l3_2": "4.00|0",
                     "lyric_sync_m1_l1_1": "1.00|0"}, music_slot=2, lyric_slot=3)
    w._load_sync_anchors()
    assert w._sync_anchors == [[4.0, 0], [9.0, 1]]


def test_persist_leert_alte_schluessel_der_kombi(make_widget):
    w = make_widget({"lyric_sync_m1_l1_1": "1.00|0", "lyric_sync_m1_l1_2": "2.00|0",
                     "lyric_sync_m2_l1_1": "3.00|0"})
    w._sync_anchors = [[5.0, 1]]
    w._persist_sync_anchors()
    assert w._db.props["lyric_sync_m1_l1_1"] == "5.00|1"
    assert w._db.props["lyric_sync_m1_l1_2"] == ""
    assert w._db.props["lyric_sync_m2_l1_1"] == "3.00|0"


def test_kopieren_uebernimmt_anker_der_quell_kombi(make_widget):
    w = make_widget({"lyric_sync_m2_l1_1": "7.00|2", "lyric_sync_m2_l1_2": "3.00|1"})
    w._copy_sync_from(w._db.get_properties(7), (2, 1))
    assert w._sync_anchors == [[3.0, 1], [7.0, 2]]
    assert w._db.props["lyric_sync_m1_l1_1"] == "3.00|1"
    assert w._db.props["lyric_sync_m1_l1_2"] == "7.00|2"
