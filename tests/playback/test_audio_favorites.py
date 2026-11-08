"""Audio-Favoriten 1/2 und der Toggle-Knopf im Footer (intern#173).

1 = Hauptausgang (audio/primary_device), 2 = Vorhoer-Kanal
(audio/secondary_device). Geprueft werden die Rechnung in audio_favorites und
die echten Methoden von P29MainWindow auf einem schlanken Ersatzfenster (ohne
Audio, DB und Docks).
"""
from types import SimpleNamespace

import pytest
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QComboBox, QPushButton

import audio_favorites as af
import main

W = main.P29MainWindow

SPEAKER = 3     # Favorit 1
HEADSET = 7     # Favorit 2
OTHER = 9       # drittes Geraet


# ---- Rechnung ----

@pytest.mark.parametrize("raw, expected", [
    ("", None), (None, None), ("  ", None), ("7", 7), (7, 7),
])
def test_parse_device(raw, expected):
    assert af.parse_device(raw) == expected


def test_parse_device_unlesbar():
    assert af.parse_device("abc") is af.UNREADABLE


def test_other():
    assert (af.other(1), af.other(2)) == (2, 1)


def test_marks():
    assert af.marks(af.favorite_devices("3", "7")) == {3: "1", 7: "2"}
    assert af.marks(af.favorite_devices("", "7")) == {None: "1", 7: "2"}
    assert af.marks(af.favorite_devices("3", "3")) == {3: "1+2"}
    assert af.marks(af.favorite_devices("3", "abc")) == {3: "1"}


# ---- Knopf im Footer ----

class _Engine:
    def __init__(self):
        self.device = SPEAKER
        self.switches = []
        self.forgotten = []

    def set_output_device(self, device):
        self.device = device
        self.switches.append(device)

    def forget_device_fallback(self, device):
        self.forgotten.append(device)


class _Fenster:
    _ROLE_AUDIO_BASE_LABEL = W._ROLE_AUDIO_BASE_LABEL
    _audio_favorite_devices = W._audio_favorite_devices
    _audio_device_label = W._audio_device_label
    _refresh_audio_favorite_ui = W._refresh_audio_favorite_ui
    _on_audio_favorite_toggle = W._on_audio_favorite_toggle
    _on_audio_device_changed = W._on_audio_device_changed
    _on_settings_applied = W._on_settings_applied

    def __init__(self, ini):
        self._settings = ini
        self.skin_mgr = None
        self.engine = _Engine()
        self.player = SimpleNamespace(_audition_active=False)
        self.messages = []
        self._status = SimpleNamespace(
            showMessage=lambda text, _ms=0: self.messages.append(text))
        self._audio_device_combo = QComboBox()
        self._audio_device_combo.addItem("System Default", None)
        for name, idx in (("Speakers", SPEAKER), ("Headset", HEADSET), ("HDMI", OTHER)):
            self._audio_device_combo.addItem(name, idx)
        self._audio_device_combo.setCurrentIndex(
            self._audio_device_combo.findData(SPEAKER))
        self._btn_audio_favorite = QPushButton("1")
        self._audio_favorite = 1
        self._refresh_audio_favorite_ui()

    def statusBar(self):
        return self._status

    def texts(self):
        c = self._audio_device_combo
        return [c.itemText(i) for i in range(c.count())]


@pytest.fixture
def fenster(keep, tmp_path):
    ini = QSettings(str(tmp_path / "w.ini"), QSettings.IniFormat)
    ini.setValue("audio/primary_device", str(SPEAKER))
    ini.setValue("audio/secondary_device", str(HEADSET))
    f = _Fenster(ini)
    # Qt-Widgets am Testende abraeumen (CODING_STANDARDS "Tests", PR #119)
    keep(f._audio_device_combo)
    keep(f._btn_audio_favorite)
    return f


def test_start_auf_favorit_1_mit_gekennzeichneter_liste(fenster):
    assert fenster._btn_audio_favorite.text() == "1"
    assert fenster.texts() == ["System Default", "1 · Speakers", "2 · Headset", "HDMI"]


def test_klick_schaltet_auf_favorit_2_und_zurueck(fenster):
    fenster._on_audio_favorite_toggle()
    assert fenster.engine.device == HEADSET
    assert fenster._btn_audio_favorite.text() == "2"
    assert fenster._audio_device_combo.currentData() == HEADSET
    # Favorit 1 bleibt, was er war (die Liste hat ihn nicht ueberschrieben)
    assert fenster._settings.value("audio/primary_device") == str(SPEAKER)

    fenster._on_audio_favorite_toggle()
    assert fenster.engine.device == SPEAKER
    assert fenster._btn_audio_favorite.text() == "1"
    assert fenster._audio_device_combo.currentData() == SPEAKER


def test_auswahl_in_der_liste_wird_neuer_favorit_1(fenster):
    fenster._on_audio_favorite_toggle()                     # auf 2
    combo = fenster._audio_device_combo
    combo.setCurrentIndex(combo.findData(OTHER))
    fenster._on_audio_device_changed(combo.currentIndex())
    assert fenster._settings.value("audio/primary_device") == str(OTHER)
    assert fenster._btn_audio_favorite.text() == "1"
    assert fenster.texts() == ["System Default", "Speakers", "2 · Headset", "1 · HDMI"]


def test_leerer_favorit_ist_der_system_standard(fenster):
    fenster._settings.setValue("audio/secondary_device", "")
    fenster._on_audio_favorite_toggle()
    assert fenster.engine.device is None
    assert fenster._btn_audio_favorite.text() == "2"
    assert fenster.texts()[0] == "2 · System Default"


def test_favorit_ohne_geraet_in_der_liste_schaltet_nicht(fenster):
    fenster._settings.setValue("audio/secondary_device", "42")
    fenster._on_audio_favorite_toggle()
    assert fenster.engine.switches == []
    assert fenster._btn_audio_favorite.text() == "1"
    assert len(fenster.messages) == 1


def test_waehrend_des_vorhoerens_gesperrt(fenster):
    fenster.player._audition_active = True
    fenster._on_audio_favorite_toggle()
    assert fenster.engine.switches == []
    assert fenster._btn_audio_favorite.text() == "1"
    assert len(fenster.messages) == 1


# ---- Geraetewechsel in den Einstellungen waehrend des Vorhoerens (intern#180) ----

def _start_audition(fenster):
    """Wie _on_player_audition: Geraet merken, auf den Vorhoer-Kanal schalten."""
    fenster._pre_audition_device = fenster.engine.device
    fenster.engine.set_output_device(HEADSET)
    fenster.player._audition_active = True
    fenster.engine.switches.clear()


def test_neuer_favorit_2_im_vorhoeren_gilt_auch_nach_dem_vorhoeren(fenster):
    fenster._on_audio_favorite_toggle()                     # auf 2
    _start_audition(fenster)
    fenster._settings.setValue("audio/secondary_device", str(OTHER))
    fenster._on_settings_applied(["audio/secondary_device"])
    assert fenster.engine.device == OTHER
    assert fenster._pre_audition_device == OTHER
    assert fenster._btn_audio_favorite.text() == "2"


def test_neuer_favorit_1_im_vorhoeren_schaltet_erst_danach(fenster):
    _start_audition(fenster)
    fenster._settings.setValue("audio/primary_device", str(OTHER))
    fenster._on_settings_applied(["audio/primary_device"])
    assert fenster.engine.switches == []                    # Vorhoeren bleibt, wo es ist
    assert fenster._pre_audition_device == OTHER
    assert fenster._btn_audio_favorite.text() == "1"
    assert fenster.engine.forgotten == [OTHER]              # intern#237: danach neu versuchen


def test_neuer_favorit_1_ohne_vorhoeren_schaltet_sofort(fenster):
    fenster._settings.setValue("audio/primary_device", str(OTHER))
    fenster._on_settings_applied(["audio/primary_device"])
    assert fenster.engine.device == OTHER


# ---- Geraete-Auswahl im Footer waehrend des Vorhoerens (intern#182) ----

def test_footer_auswahl_im_vorhoeren_schaltet_erst_danach(fenster):
    _start_audition(fenster)
    combo = fenster._audio_device_combo
    combo.setCurrentIndex(combo.findData(OTHER))
    fenster._on_audio_device_changed(combo.currentIndex())
    assert fenster.engine.switches == []                    # Vorhoeren bleibt, wo es ist
    assert fenster._pre_audition_device == OTHER
    assert fenster._settings.value("audio/primary_device") == str(OTHER)
    assert fenster._btn_audio_favorite.text() == "1"


def test_footer_auswahl_ohne_vorhoeren_schaltet_sofort(fenster):
    combo = fenster._audio_device_combo
    combo.setCurrentIndex(combo.findData(OTHER))
    fenster._on_audio_device_changed(combo.currentIndex())
    assert fenster.engine.switches == [OTHER]
    assert fenster.engine.forgotten == [OTHER]              # intern#237


def test_tooltip_nennt_beide_geraete(fenster):
    tip = fenster._btn_audio_favorite.toolTip()
    assert "Speakers" in tip and "Headset" in tip
