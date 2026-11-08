"""Dual View laesst die eigene Fenstergroesse der Docks in Ruhe (intern#231).

Dual View zeigt zwei Docks als schwebende Fenster nebeneinander. Es benutzt
dafuer dieselben Fenster wie deren eigene Floating-Ansicht. Bisher landete die
Dual-View-Groesse deshalb als "eigene" Groesse im Speicher:
  - 60-s-Autosave / Beenden waehrend Dual View schrieb sie nach floatrect/<dock>,
  - beim Verstecken nach dem Schliessen merkte _on_float_dock_visible sie vor,
  - das Oeffnen verbrauchte die vorgemerkte eigene Groesse.
Oeffnete man Lyrics danach allein, kam es in Dual-View-Groesse.

Geprueft werden die echten Methoden aus P29MainWindow an einem schlanken
Stellvertreter-Hauptfenster mit echten QDockWidgets und echter INI-Datei.
"""
import pytest
from PySide6.QtCore import QRect, QSettings, Qt
from PySide6.QtWidgets import QDockWidget, QMainWindow, QWidget

import main
from ui_helpers import _PlayBarrier

W = main.P29MainWindow

EIGEN = QRect(150, 120, 420, 380)       # Lyrics: eigene schwebende Groesse
EIGEN_RULES = QRect(700, 90, 300, 260)


class _Haupt(QMainWindow):
    """Stellvertreter mit den echten Dual-View- und Geometrie-Methoden."""
    _LAYOUT_VERSION = main._LAYOUT_VERSION
    _DOCK_NAME_ALIASES = W._DOCK_NAME_ALIASES
    _dock_map = W._dock_map
    _rule_dual_view = W._rule_dual_view
    _rule_dual_view_close = W._rule_dual_view_close
    _rule_dual_view_toggle_apply = W._rule_dual_view_toggle_apply
    _rule_dual_view_close_deferred = W._rule_dual_view_close_deferred
    _dual_view_remember = W._dual_view_remember
    _dual_view_restore = W._dual_view_restore
    _dual_view_discard = W._dual_view_discard
    _dual_view_watch = W._dual_view_watch
    _dual_view_schedule_check = W._dual_view_schedule_check
    _dual_view_check_ended = W._dual_view_check_ended
    _reset_layout = W._reset_layout
    _save_layout_to_file = W._save_layout_to_file
    _apply_layout_file = W._apply_layout_file
    _write_layout_state = W._write_layout_state
    _raised_tab_docknames = W._raised_tab_docknames
    _restore_raised_tabs = W._restore_raised_tabs
    _save_float_geoms = W._save_float_geoms
    _read_float_rect = W._read_float_rect
    _restore_float_geoms = W._restore_float_geoms
    _connect_float_geom_handlers = W._connect_float_geom_handlers
    _on_float_dock_visible = W._on_float_dock_visible
    _rect_from_saved_geometry = staticmethod(W._rect_from_saved_geometry)
    _apply_float_rect = staticmethod(W._apply_float_rect)
    _reapply_dock_features = W._reapply_dock_features

    def _apply_saved_dock_free(self):
        pass  # BL-204 "Frei bewegen": hier ohne Belang

    def __init__(self, ini):
        super().__init__()
        self.setCentralWidget(QWidget())
        self._settings = ini
        self._pending_float_geom = {}
        self._float_geom_connected = False
        self._dual_view_saved = {}
        self._dual_view_active = None
        self._pre_dual_view_state = None
        self._play_barrier = _PlayBarrier()
        self.docks = {}
        for name in ("dock_lyrics", "dock_sequences", "dock_rules",
                     "dock_evening_planner"):
            d = QDockWidget(name, self)
            d.setObjectName(name)
            d.setWidget(QWidget())
            self.addDockWidget(Qt.RightDockWidgetArea, d)
            self.docks[name] = d
        self.player = QWidget()
        self.loop_widget = QWidget()
        self.dock_evening_planner = self.docks["dock_evening_planner"]
        self.dock_evening_planner.setFloating(True)
        self.dock_evening_planner.hide()
        self.resize(1000, 700)
        self.show()

    def _floating_tool_docks(self):
        # wie _FLOAT_TOOL_DOCK_ATTRS: Lyrics und Rules ja, Sequences nicht
        return [self.docks["dock_lyrics"], self.docks["dock_rules"]]


@pytest.fixture
def ini(tmp_path):
    return QSettings(str(tmp_path / "callers_caddy.ini"), QSettings.IniFormat)


@pytest.fixture
def haupt(qapp, ini, keep):
    h = keep(_Haupt(ini))
    h._connect_float_geom_handlers()
    qapp.processEvents()
    return h


def _schwebend(h, name, rect, sichtbar=True):
    d = h.docks[name]
    d.setFloating(True)
    d.show()
    d.setGeometry(rect)
    if not sichtbar:
        d.hide()
    return d


DUAL = {"dock_left": "lyrics", "dock_right": "sequences", "split": "50:50"}


def _toggle(h, qapp):
    h._rule_dual_view_toggle_apply(DUAL)
    qapp.processEvents()


def _beenden(h):
    h._save_float_geoms(h._settings)
    h._settings.sync()


# ---- Fehlerwege aus dem Issue ---------------------------------------------

def test_speichern_waehrend_dual_view_behaelt_eigene_groesse(haupt, qapp):
    _schwebend(haupt, "dock_lyrics", EIGEN)
    _toggle(haupt, qapp)                                   # Dual View an
    assert haupt.docks["dock_lyrics"].geometry() != EIGEN  # Dual-Groesse
    _beenden(haupt)                                        # 60-s-Autosave
    assert haupt._settings.value("floatrect/dock_lyrics") == EIGEN


def test_toggle_zu_lyrics_schwebend_sichtbar_wieder_eigene_groesse(haupt, qapp):
    lyr = _schwebend(haupt, "dock_lyrics", EIGEN)
    _toggle(haupt, qapp)
    _toggle(haupt, qapp)                                   # Dual View aus
    assert lyr.isFloating() and lyr.isVisible()
    assert lyr.geometry() == EIGEN


def test_toggle_zu_lyrics_vorher_versteckt_spaeter_eigene_groesse(haupt, qapp):
    lyr = _schwebend(haupt, "dock_lyrics", EIGEN, sichtbar=False)
    _toggle(haupt, qapp)
    _toggle(haupt, qapp)
    assert not lyr.isVisible()
    lyr.show()                                             # spaeter allein oeffnen
    qapp.processEvents()
    assert lyr.isFloating()
    assert lyr.geometry() == EIGEN
    _beenden(haupt)
    assert haupt._settings.value("floatrect/dock_lyrics") == EIGEN


def test_toggle_zu_lyrics_vorher_angedockt_bleibt_angedockt(haupt, qapp, ini):
    ini.setValue("floatrect/dock_lyrics", EIGEN)           # eigene Groesse aus INI
    haupt._restore_float_geoms(ini)
    lyr = haupt.docks["dock_lyrics"]
    assert not lyr.isFloating()
    _toggle(haupt, qapp)
    _toggle(haupt, qapp)
    assert not lyr.isFloating()
    _beenden(haupt)
    assert haupt._settings.value("floatrect/dock_lyrics") == EIGEN


# ---- Entscheidungen aus der Besprechung -----------------------------------

def _close(h, qapp):
    """Aktion "Close Dual-View" (ohne Toggle), deferred wie in der App."""
    h._rule_dual_view_close({})
    qapp.processEvents()


def test_close_aktion_stellt_zustand_von_vorher_her(haupt, qapp):
    """Entscheidung 2: Close dockt nicht mehr an und versteckt nicht, sondern
    stellt den Zustand von vorher her - hier: Lyrics schwebend offen."""
    lyr = _schwebend(haupt, "dock_lyrics", EIGEN)
    seq = haupt.docks["dock_sequences"]
    assert not seq.isFloating() and seq.isVisible()
    haupt._rule_dual_view(DUAL)
    qapp.processEvents()
    _close(haupt, qapp)
    assert lyr.isFloating() and lyr.isVisible() and lyr.geometry() == EIGEN
    assert not seq.isFloating() and seq.isVisible()
    assert haupt._dual_view_saved == {} and haupt._dual_view_active is None


def test_close_ohne_dual_view_tut_nichts(haupt, qapp):
    lyr = _schwebend(haupt, "dock_lyrics", EIGEN)
    _close(haupt, qapp)
    assert lyr.isFloating() and lyr.geometry() == EIGEN


def test_beenden_waehrend_dual_view_speichert_layout_von_vorher(haupt, qapp, ini, keep):
    """Entscheidung 1: windowState/geometry von VOR Dual View in die INI."""
    _schwebend(haupt, "dock_lyrics", EIGEN)
    vorher = haupt.saveState(main._LAYOUT_VERSION)
    _toggle(haupt, qapp)
    assert haupt.saveState(main._LAYOUT_VERSION) != vorher
    haupt._write_layout_state(ini)
    _beenden(haupt)
    assert bytes(ini.value("windowState")) == bytes(vorher)
    # "Neustart": anderes Fenster liest die INI
    neu = keep(_Haupt(QSettings(ini.fileName(), QSettings.IniFormat)))
    neu.restoreState(neu._settings.value("windowState"), main._LAYOUT_VERSION)
    neu._restore_float_geoms(neu._settings)
    qapp.processEvents()
    lyr = neu.docks["dock_lyrics"]
    assert lyr.isFloating() and lyr.isVisible()
    assert lyr.geometry() == EIGEN


def test_ohne_dual_view_speichert_wie_bisher(haupt, qapp, ini):
    _schwebend(haupt, "dock_lyrics", EIGEN)
    haupt._write_layout_state(ini)
    assert bytes(ini.value("windowState")) == bytes(
        haupt.saveState(main._LAYOUT_VERSION))


# ---- Grenzfaelle -----------------------------------------------------------

def test_dual_view_paar_wechseln_dann_schliessen(haupt, qapp):
    """Zweites dual_view (anderes Paar) waehrend offen: beim Schliessen alles
    zurueck auf den Zustand vor dem ERSTEN Oeffnen."""
    lyr = _schwebend(haupt, "dock_lyrics", EIGEN)
    rules = _schwebend(haupt, "dock_rules", EIGEN_RULES)
    _toggle(haupt, qapp)                                         # lyrics|sequences
    haupt._rule_dual_view({"dock_left": "rules", "dock_right": "lyrics"})
    qapp.processEvents()
    assert rules.geometry() != EIGEN_RULES
    _beenden(haupt)
    assert haupt._settings.value("floatrect/dock_rules") == EIGEN_RULES
    assert haupt._settings.value("floatrect/dock_lyrics") == EIGEN
    _toggle(haupt, qapp)                                         # schliessen
    assert lyr.geometry() == EIGEN and rules.geometry() == EIGEN_RULES


def test_nutzer_aendert_dual_fenster_wird_nicht_eigene_groesse(haupt, qapp):
    lyr = _schwebend(haupt, "dock_lyrics", EIGEN)
    _toggle(haupt, qapp)
    lyr.setGeometry(QRect(10, 10, 999, 600))                     # im Dual View gezogen
    lyr.hide()                                                   # und per X zu
    qapp.processEvents()
    _beenden(haupt)
    assert haupt._settings.value("floatrect/dock_lyrics") == EIGEN
    _toggle(haupt, qapp)
    lyr.show()
    qapp.processEvents()
    assert lyr.geometry() == EIGEN


def test_eigene_groesse_nur_in_ini(haupt, qapp, ini):
    """Lyrics in dieser Sitzung noch nie gezeigt: eigene Groesse steht nur
    in der INI bzw. ist vorgemerkt - beides bleibt erhalten."""
    ini.setValue("floatrect/dock_lyrics", EIGEN)
    lyr = haupt.docks["dock_lyrics"]
    lyr.setFloating(True)
    lyr.hide()
    haupt._restore_float_geoms(ini)                              # vorgemerkt
    _toggle(haupt, qapp)
    _beenden(haupt)
    assert ini.value("floatrect/dock_lyrics") == EIGEN
    _toggle(haupt, qapp)
    lyr.show()
    qapp.processEvents()
    assert lyr.geometry() == EIGEN


def test_keine_eigene_groesse_bekannt(haupt, qapp, ini):
    """Angedocktes Lyrics ohne floatrect: nach Dual View wird auch keine
    erfunden (keine Dual-View-Groesse in der INI)."""
    _toggle(haupt, qapp)
    _beenden(haupt)
    assert ini.value("floatrect/dock_lyrics") is None
    _toggle(haupt, qapp)
    _beenden(haupt)
    assert ini.value("floatrect/dock_lyrics") is None


def test_andere_docks_unberuehrt(haupt, qapp):
    """Ein schwebendes Dock, das nicht in Dual View steht, verhaelt sich
    wie bisher (Verstecken merkt seine Groesse vor)."""
    rules = _schwebend(haupt, "dock_rules", EIGEN_RULES)
    _toggle(haupt, qapp)
    rules.setGeometry(QRect(20, 30, 333, 222))
    rules.hide()
    assert haupt._pending_float_geom["dock_rules"] == QRect(20, 30, 333, 222)
    _toggle(haupt, qapp)


def test_layout_laden_beendet_dual_view(haupt, qapp, tmp_path):
    """Layout-Datei waehrend Dual View: Datei ist massgeblich, Dual View ist
    danach beendet, ein spaeterer Toggle oeffnet neu statt zurueckzuholen."""
    lyr = _schwebend(haupt, "dock_lyrics", EIGEN)
    datei = QSettings(str(tmp_path / "mein.ini"), QSettings.IniFormat)
    datei.setValue("windowState", haupt.saveState(main._LAYOUT_VERSION))
    datei.setValue("floatrect/dock_lyrics", QRect(300, 300, 222, 333))
    datei.sync()
    _toggle(haupt, qapp)
    assert haupt._apply_layout_file(datei.fileName())
    qapp.processEvents()
    assert haupt._dual_view_active is None and haupt._dual_view_saved == {}
    assert lyr.geometry() == QRect(300, 300, 222, 333)       # aus der Datei
    _toggle(haupt, qapp)                                     # oeffnet neu
    assert haupt._dual_view_active is not None
    _toggle(haupt, qapp)
    assert lyr.geometry() == QRect(300, 300, 222, 333)


def test_discard_gibt_eigene_groesse_in_vormerkung(haupt, qapp):
    _schwebend(haupt, "dock_lyrics", EIGEN)
    _toggle(haupt, qapp)
    haupt._dual_view_discard()
    assert haupt._pending_float_geom["dock_lyrics"] == EIGEN
    assert haupt._dual_view_active is None and haupt._pre_dual_view_state is None
    _beenden(haupt)                     # Speichern danach: wieder wie ohne Dual View
    assert haupt._settings.value("floatrect/dock_lyrics") == EIGEN


# ---- Review #161 -------------------------------------------------------------

DUAL_RULES = {"dock_left": "rules", "dock_right": "lyrics", "split": "50:50"}


def _dual(h, qapp, params):
    """dual_view per Regel (nicht Toggle), wie im Szenario aus dem Review."""
    h._rule_dual_view(params)
    qapp.processEvents()


def test_beide_per_x_geschlossen_beendet_dual_view(haupt, qapp, ini):
    lyr = _schwebend(haupt, "dock_lyrics", EIGEN)
    _dual(haupt, qapp, DUAL)
    seq = haupt.docks["dock_sequences"]
    lyr.hide()
    qapp.processEvents()
    assert haupt._dual_view_active is not None          # Sequences noch offen
    seq.hide()
    qapp.processEvents()
    assert haupt._dual_view_active is None and haupt._dual_view_saved == {}
    lyr.show()                                           # spaeter uebers Menue
    qapp.processEvents()
    assert lyr.geometry() == EIGEN
    lyr.setGeometry(QRect(40, 50, 500, 400))             # danach groesser gezogen
    haupt._write_layout_state(ini)
    _beenden(haupt)
    assert ini.value("floatrect/dock_lyrics") == QRect(40, 50, 500, 400)
    assert bytes(ini.value("windowState")) == bytes(
        haupt.saveState(main._LAYOUT_VERSION))           # aktuelles Layout
    _toggle(haupt, qapp)                                 # oeffnet neu
    assert haupt._dual_view_active is not None


def test_beide_angedockt_beendet_dual_view(haupt, qapp):
    _schwebend(haupt, "dock_lyrics", EIGEN)
    _dual(haupt, qapp, DUAL)
    for name in ("dock_lyrics", "dock_sequences"):
        haupt.docks[name].setFloating(False)
    qapp.processEvents()
    assert haupt._dual_view_active is None
    assert haupt._pending_float_geom["dock_lyrics"] == EIGEN
    _beenden(haupt)
    assert haupt._settings.value("floatrect/dock_lyrics") == EIGEN


def test_toggle_schliessen_beendet_ohne_discard(haupt, qapp):
    """Waehrend _dual_view_restore verstecken/zeigen sich die Docks; die
    Pruefung darf das Wiederherstellen nicht vorzeitig abbrechen."""
    lyr = _schwebend(haupt, "dock_lyrics", EIGEN)
    _toggle(haupt, qapp)
    _toggle(haupt, qapp)
    qapp.processEvents()
    assert lyr.isFloating() and lyr.isVisible() and lyr.geometry() == EIGEN
    assert "dock_lyrics" not in haupt._pending_float_geom


def _fuer_reset(h, monkeypatch):
    """_reset_layout fasst alle Haupt-Docks an; fehlende als echte Docks
    nachreichen, die Tool-Docks des Stellvertreters bleiben dieselben.
    Das Anordnen (add/split/tabify) ist hier ohne Belang und stuerzte im
    Stellvertreter in der vollen Suite in Qt ab; massgeblich sind
    setFloating(False)/hide() und die Reihenfolge von discard."""
    for meth in ("addDockWidget", "splitDockWidget", "tabifyDockWidget"):
        monkeypatch.setattr(h, meth, lambda *a, **k: None)
    for attr in ("dock_player", "dock_loop", "dock_data", "dock_list",
                 "dock_playlist", "dock_loop_finder", "dock_manager",
                 "dock_reports", "dock_potential", "dock_photo"):
        d = QDockWidget(attr, h)
        d.setObjectName(attr)
        d.setWidget(QWidget())
        QMainWindow.addDockWidget(h, Qt.LeftDockWidgetArea, d)
        setattr(h, attr, d)
    for name in ("dock_lyrics", "dock_sequences", "dock_rules"):
        setattr(h, name, h.docks[name])
    h._pre_fullsize_state = {}


def test_layout_zuruecksetzen_waehrend_dual_view_behaelt_eigene_groesse(
        haupt, qapp, ini, monkeypatch):
    _fuer_reset(haupt, monkeypatch)
    rules = _schwebend(haupt, "dock_rules", EIGEN_RULES)
    _dual(haupt, qapp, DUAL_RULES)
    assert rules.geometry() != EIGEN_RULES
    haupt._reset_layout()
    qapp.processEvents()
    assert haupt._dual_view_active is None
    _beenden(haupt)
    assert ini.value("floatrect/dock_rules") == EIGEN_RULES


def test_layout_in_datei_waehrend_dual_view_speichert_layout_von_vorher(
        haupt, qapp, tmp_path, monkeypatch):
    _schwebend(haupt, "dock_lyrics", EIGEN)
    vorher = haupt.saveState(main._LAYOUT_VERSION)
    _toggle(haupt, qapp)
    ziel = str(tmp_path / "export.ini")
    monkeypatch.setattr(main.QFileDialog, "getSaveFileName",
                        lambda *a, **k: (ziel, ""))
    haupt.skin_mgr = type("S", (), {"skins_dir": str(tmp_path)})()
    haupt._save_layout_to_file()
    datei = QSettings(ziel, QSettings.IniFormat)
    assert bytes(datei.value("windowState")) == bytes(vorher)
    assert datei.value("floatrect/dock_lyrics") == EIGEN


def test_layout_laden_mit_falscher_version_laesst_dual_view_offen(haupt, qapp, tmp_path):
    _schwebend(haupt, "dock_lyrics", EIGEN)
    datei = QSettings(str(tmp_path / "alt.ini"), QSettings.IniFormat)
    datei.setValue("windowState", haupt.saveState(main._LAYOUT_VERSION + 1))
    datei.sync()
    _toggle(haupt, qapp)
    assert not haupt._apply_layout_file(datei.fileName())
    qapp.processEvents()
    assert haupt._dual_view_active is not None           # Toggle schliesst weiter
    _toggle(haupt, qapp)
    assert haupt.docks["dock_lyrics"].geometry() == EIGEN
