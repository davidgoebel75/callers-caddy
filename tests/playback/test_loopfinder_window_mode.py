"""Loop Finder: Suchfenster in Prozent oder Zeit (intern#207).

Umschalten rechnet anhand der Songdauer um, Presets fuehren den Modus mit,
alte Presets laden als Prozent, unpassende Fenster starten keine Analyse.
"""
import json

import pytest

import loop_windows as lw
from i18n import _t
from loopfinder_widget import LoopFinderWidget


@pytest.fixture
def finder(keep, tmp_path):
    w = keep(LoopFinderWidget())
    w.set_presets_dir(str(tmp_path))
    # Songdauer ohne Audiodatei vorgeben (Lazy-Load ueberspringen)
    w._filepath = "song.mp3"
    w._waveform_loaded = True
    w._song_duration = 200.0
    return w


def _values(w):
    return tuple(s.value() for s in w._window_spins())


def test_start_in_prozent(finder):
    assert finder.window_mode() == lw.MODE_PCT
    assert _values(finder) == (7, 21, 64, 79)
    assert finder._spin_in_start.text() == "7 %"


def test_umschalten_rechnet_um_und_meldet(finder):
    seen = []
    finder.on_window_mode_changed = seen.append
    finder._combo_mode.setCurrentIndex(finder._combo_mode.findData(lw.MODE_TIME))
    assert finder.window_mode() == lw.MODE_TIME
    assert _values(finder) == (14, 42, 72, 42)
    assert finder._spin_in_start.text() == "+0:14"
    assert finder._spin_out_start.text() == "−1:12"
    assert seen == [lw.MODE_TIME]
    finder.set_window_mode(lw.MODE_PCT)
    assert _values(finder) == (7, 21, 64, 79)
    assert seen == [lw.MODE_TIME, lw.MODE_PCT]


def test_zeit_info_labels_zeigen_songposition(finder):
    finder.set_window_mode(lw.MODE_TIME)
    assert finder._lbl_t_out_start.text() != "–"
    assert finder._current_windows() == (14.0, 42.0, 128.0, 158.0)


def test_zeiteingabe_m_ss_und_sekunden(finder):
    finder.set_window_mode(lw.MODE_TIME)
    spin = finder._spin_in_start
    assert spin.valueFromText("1:05") == 65
    assert spin.valueFromText("+0:20") == 20
    assert spin.valueFromText("45") == 45
    assert finder._spin_out_end.valueFromText("−0:50") == 50


def test_zeit_preset_speichern_und_laden(finder, tmp_path):
    finder.set_window_mode(lw.MODE_TIME)
    data = finder._current_settings_as_preset()
    assert data["mode"] == lw.MODE_TIME
    assert finder._save_preset("Intro", data)
    stored = json.loads((tmp_path / "Intro.json").read_text(encoding="utf-8"))
    assert stored["mode"] == "time"

    finder.set_window_mode(lw.MODE_PCT)
    finder._apply_preset_to_ui(finder._load_preset("Intro"))
    assert finder.window_mode() == lw.MODE_TIME
    assert _values(finder) == (14, 42, 72, 42)


def test_altes_preset_ohne_mode_laedt_als_prozent(finder, tmp_path):
    (tmp_path / "Alt.json").write_text(json.dumps(
        {"in_start": 10, "in_end": 20, "out_start": 70, "out_end": 80,
         "compare_beats": 16, "selection_strategy": "best_64"}), encoding="utf-8")
    finder.set_window_mode(lw.MODE_TIME)
    finder._apply_preset_to_ui(finder._load_preset("Alt"))
    assert finder.window_mode() == lw.MODE_PCT
    assert _values(finder) == (10, 20, 70, 80)


def test_unpassende_fenster_starten_keine_analyse(finder):
    finder.set_window_mode(lw.MODE_TIME)
    # Loop-In bis 3:00 reicht bei 200 s in Loop-Out hinein
    finder._spin_in_end.setValue(180)
    assert finder._lbl_status.text() == _t("lf_status_windows_mismatch")
    finder._on_analyze()
    assert finder._worker is None
    assert finder._lbl_status.text() == _t("lf_status_windows_mismatch")


# ---- Ohne Songdauer: Standardfenster des Modus (Review PR #132) ---------------

def test_start_im_zeitmodus_ohne_song(keep, tmp_path):
    """Wie beim App-Start mit loop/finder_window_mode=time: noch kein Song."""
    w = keep(LoopFinderWidget())
    w.set_presets_dir(str(tmp_path))
    w.set_window_mode(lw.MODE_TIME, convert=False)
    assert w.window_mode() == lw.MODE_TIME
    assert _values(w) == lw.default_values(lw.MODE_TIME) == (20, 59, 50, 20)
    assert w._spin_in_start.text() == "+0:20"
    assert w._spin_out_start.text() == "−0:50"
    # Mit Song passen die Fenster: 20-59 s / 150-180 s bei 200 s
    assert lw.resolve_windows(w._current_settings_as_preset(), 200.0) == (
        20.0, 59.0, 150.0, 180.0)


def test_umschalten_ohne_song_nimmt_standardwerte(keep, tmp_path):
    w = keep(LoopFinderWidget())
    w.set_presets_dir(str(tmp_path))
    w._waveform_loaded = True                     # kein Lazy-Load, Dauer 0
    w.set_window_mode(lw.MODE_TIME)
    assert _values(w) == lw.default_values(lw.MODE_TIME)
    w.set_window_mode(lw.MODE_PCT)
    assert _values(w) == (7, 21, 64, 79)
