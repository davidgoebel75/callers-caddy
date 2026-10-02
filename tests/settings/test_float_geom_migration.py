"""Alte floatgeom-Bytes absturzsicher lesen und verlustfrei umstellen (#121).

Bis 0.159 stand die Floating-Position der Tool-Fenster als saveGeometry()-
Bytes unter floatgeom/<dock>. Der Rueckfall las sie per
QDataStream(QByteArray(data)) — das temporaere QByteArray war schon frei,
der Stream las Muell und die App stuerzte beim Start ab. Ausserdem stellte
das Beenden nur schwebende Docks auf floatrect um; bei angedockten lief der
Rueckfall so bei jedem Start.

Geprueft werden die echten Methoden aus P29MainWindow an einem schlanken
Stellvertreter-Fenster mit echten QDockWidgets, ohne das Hauptfenster
hochzufahren. Die INI ist eine echte QSettings-Datei unter tmp_path.
"""
import struct

import pytest
from PySide6.QtCore import QByteArray, QRect, QSettings
from PySide6.QtWidgets import QDockWidget, QMainWindow, QWidget

import main

W = main.P29MainWindow

# Davids echter Eintrag floatgeom/dock_reports (66 Bytes, Version 3.0):
# frame (840,1)-(1308,831), normal (840,32)-(1308,831)
DAVID_RECT = QRect(840, 32, 469, 800)


def _saved_geometry(frame, normal, major=3, minor=0):
    """Bytes im Format von QWidget.saveGeometry() (Version 3.0, 66 Bytes)."""
    return (struct.pack(">IHH8i", 0x1D9D0CB, major, minor, *frame, *normal)
            + struct.pack(">iBBi", 0, 0, 0, 2560)
            + struct.pack(">4i", 0, 0, 2559, 1439))


DAVID_BYTES = _saved_geometry((840, 1, 1308, 831), (840, 32, 1308, 831))


class _Fenster:
    """Stellvertreter mit den echten Methoden aus P29MainWindow."""
    _save_float_geoms = W._save_float_geoms
    _read_float_rect = W._read_float_rect
    _restore_float_geoms = W._restore_float_geoms
    _connect_float_geom_handlers = W._connect_float_geom_handlers
    _on_float_dock_visible = W._on_float_dock_visible
    _rect_from_saved_geometry = staticmethod(W._rect_from_saved_geometry)
    _apply_float_rect = staticmethod(W._apply_float_rect)

    def __init__(self, docks):
        self._docks = docks
        self._pending_float_geom = {}
        self._float_geom_connected = False

    def _floating_tool_docks(self):
        return self._docks


@pytest.fixture
def fenster(qapp):
    """Hauptfenster mit angedocktem dock_reports und schwebendem dock_rules."""
    mw = QMainWindow()
    mw.setCentralWidget(QWidget())
    angedockt = QDockWidget("Reports", mw)
    angedockt.setObjectName("dock_reports")
    schwebend = QDockWidget("Rules", mw)
    schwebend.setObjectName("dock_rules")
    for d in (angedockt, schwebend):
        d.setWidget(QWidget())
        mw.addDockWidget(main.Qt.LeftDockWidgetArea, d)
    schwebend.setFloating(True)
    schwebend.setGeometry(300, 200, 400, 300)
    yield _Fenster([angedockt, schwebend]), angedockt, schwebend
    mw.deleteLater()


def _ini(tmp_path, **floatgeom):
    s = QSettings(str(tmp_path / "callers_caddy.ini"), QSettings.IniFormat)
    for name, data in floatgeom.items():
        s.setValue(f"floatgeom/{name}", QByteArray(data))
    s.sync()
    return s


def _neu_laden(s):
    """INI frisch von der Platte lesen, wie beim naechsten Start."""
    s.sync()
    return QSettings(s.fileName(), QSettings.IniFormat)


def _beenden(f, s):
    """Beenden wie _save_layout: s ist die App-INI und zugleich das Ziel."""
    f._settings = s
    f._save_float_geoms(s)


# ---- Lesen der alten Bytes -------------------------------------------------

def test_davids_bytes_ergeben_normal_geometry():
    assert len(DAVID_BYTES) == 66
    assert W._rect_from_saved_geometry(QByteArray(DAVID_BYTES)) == DAVID_RECT
    assert W._rect_from_saved_geometry(DAVID_BYTES) == DAVID_RECT


def test_echte_save_geometry_bytes_ergeben_normal_geometry(qapp):
    w = QWidget()
    w.setGeometry(123, 145, 321, 234)
    w.show()
    qapp.processEvents()
    try:
        data = w.saveGeometry()
        assert W._rect_from_saved_geometry(data) == w.normalGeometry()
        assert W._rect_from_saved_geometry(data) == QRect(123, 145, 321, 234)
    finally:
        w.close()


@pytest.mark.parametrize("data", [
    None,
    b"",
    b"\x01\xd9\xd0",                                  # zu kurz
    DAVID_BYTES[:39],                                 # Kopf abgeschnitten
    b"\x00" * 66,                                     # falsche Magic
    b"kein Geometrie-Blob, sondern Text" * 3,
    _saved_geometry((0, 0, 10, 10), (50, 50, 10, 10)),        # invalid
    _saved_geometry((0, 0, 10, 10), (-2118049770, 65301,
                                     519830763, 1217055028)),  # Muell
    12345,
], ids=["None", "leer", "kurz", "abgeschnitten", "magic", "text",
        "invalid", "muell", "int"])
def test_kaputte_bytes_ergeben_none(data):
    assert W._rect_from_saved_geometry(data) is None


def test_zehntausend_aufrufe_ohne_absturz_und_stabil():
    """Die alte Fassung lieferte schon beim ersten Aufruf Muell und stuerzte
    nach wenigen tausend Aufrufen ab (Exit 139)."""
    for _ in range(10_000):
        assert W._rect_from_saved_geometry(QByteArray(DAVID_BYTES)) == DAVID_RECT


# ---- Umstellen beim Beenden ------------------------------------------------

def test_angedocktes_dock_wird_umgestellt(fenster, tmp_path):
    f, angedockt, _ = fenster
    s = _ini(tmp_path, dock_reports=DAVID_BYTES)
    f._restore_float_geoms(s)
    _beenden(f, s)
    s = _neu_laden(s)
    assert s.value("floatrect/dock_reports") == DAVID_RECT
    assert s.value("floatgeom/dock_reports") is None
    assert not angedockt.isFloating()


def test_angedocktes_dock_nach_sichtbarwerden(fenster, tmp_path):
    """visibilityChanged poppt den vorgemerkten Wert auch fuer ein angedocktes
    Dock — dann traegt der Rueckfall auf die INI die Umstellung."""
    f, angedockt, _ = fenster
    s = _ini(tmp_path, dock_reports=DAVID_BYTES)
    f._restore_float_geoms(s)
    f._on_float_dock_visible(angedockt, True)
    assert "dock_reports" not in f._pending_float_geom
    _beenden(f, s)
    s = _neu_laden(s)
    assert s.value("floatrect/dock_reports") == DAVID_RECT
    assert s.value("floatgeom/dock_reports") is None


def test_schwebendes_dock_wird_umgestellt(fenster, tmp_path):
    f, _, schwebend = fenster
    s = _ini(tmp_path, dock_rules=DAVID_BYTES)
    _beenden(f, s)
    s = _neu_laden(s)
    assert s.value("floatrect/dock_rules") == schwebend.geometry()
    assert s.value("floatgeom/dock_rules") is None


def test_kaputte_bytes_bleiben_stehen(fenster, tmp_path):
    f, _, _ = fenster
    kaputt = b"\x00" * 66
    s = _ini(tmp_path, dock_reports=kaputt)
    f._restore_float_geoms(s)
    _beenden(f, s)
    s = _neu_laden(s)
    assert s.value("floatrect/dock_reports") is None
    assert bytes(s.value("floatgeom/dock_reports")) == kaputt


def test_vorhandenes_floatrect_hat_vorrang(fenster, tmp_path):
    f, _, _ = fenster
    s = _ini(tmp_path, dock_reports=DAVID_BYTES)
    s.setValue("floatrect/dock_reports", QRect(10, 20, 300, 400))
    f._restore_float_geoms(s)
    _beenden(f, s)
    s = _neu_laden(s)
    assert s.value("floatrect/dock_reports") == QRect(10, 20, 300, 400)
    assert s.value("floatgeom/dock_reports") is None


def _export(f, pfad):
    """Wie _save_layout_to_file: Ziel ist eine eigene Layout-Datei."""
    ziel = QSettings(str(pfad), QSettings.IniFormat)
    f._save_float_geoms(ziel)
    return _neu_laden(ziel)


def test_export_nimmt_position_aus_app_ini(fenster, tmp_path):
    """Angedocktes Dock ohne Vormerk-Wert: die Position kommt aus der
    App-INI, nicht aus der (neuen) Zieldatei."""
    f, _, _ = fenster
    app = _ini(tmp_path)
    app.setValue("floatrect/dock_reports", QRect(10, 20, 300, 400))
    f._settings = app
    ziel = _export(f, tmp_path / "layout_neu.ini")
    assert ziel.value("floatrect/dock_reports") == QRect(10, 20, 300, 400)


def test_export_ueberschreibt_alte_layout_datei(fenster, tmp_path):
    """Eine alte Layout-Datei mit veraltetem floatgeom bekommt die aktuelle
    Position aus der App-INI; das alte floatgeom verschwindet danach."""
    f, _, _ = fenster
    alt = QSettings(str(tmp_path / "layout_alt.ini"), QSettings.IniFormat)
    alt.setValue("floatgeom/dock_reports", QByteArray(DAVID_BYTES))
    alt.sync()
    app = _ini(tmp_path)
    app.setValue("floatrect/dock_reports", QRect(10, 20, 300, 400))
    f._settings = app
    ziel = _export(f, tmp_path / "layout_alt.ini")
    assert ziel.value("floatrect/dock_reports") == QRect(10, 20, 300, 400)
    assert ziel.value("floatgeom/dock_reports") is None


def test_mehrfacher_start_mit_alter_ini(fenster, tmp_path, monkeypatch):
    """Erster Start stellt um; ab dem zweiten laeuft der Rueckfall nicht mehr,
    und die Position bleibt ueber alle Starts gleich."""
    f, _, _ = fenster
    s = _ini(tmp_path, dock_reports=DAVID_BYTES)
    rueckfall = []
    echt = W._rect_from_saved_geometry

    def gezaehlt(data):
        rueckfall.append(data)
        return echt(data)

    monkeypatch.setattr(_Fenster, "_rect_from_saved_geometry",
                        staticmethod(gezaehlt))
    for start in range(3):
        f._pending_float_geom.clear()
        f._restore_float_geoms(s)
        assert f._pending_float_geom["dock_reports"] == DAVID_RECT
        _beenden(f, s)
        s = _neu_laden(s)
        assert s.value("floatrect/dock_reports") == DAVID_RECT
        assert s.value("floatgeom/dock_reports") is None
    assert len(rueckfall) == 1
