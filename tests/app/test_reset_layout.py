"""„Layout zurücksetzen“ stürzt nicht ab (intern#240).

Qt bis 6.10.2 zerstört beim tabifyDockWidget() die interne Dock-Liste, wenn
eines der beiden Docks schon in einer Tab-Gruppe steckt (im Nachbau aus
intern#241 ab 6.10.3 behoben, vgl. auch QTBUG-143841 in 6.12) – die App
stürzte dann mit einer Access Violation ab. Der
Reset nimmt deshalb die Haupt-Docks erst aus dem Layout und tabbt nur Docks,
die in keiner Gruppe stecken.

Geprueft an echten QDockWidgets mit der echten _reset_layout-Methode, aus
einer Lage, in der alle Haupt-Docks in Tab-Gruppen stecken (wie nach einem
gespeicherten Layout).
"""
import pytest
from PySide6.QtCore import QSettings, Qt
from PySide6.QtWidgets import QDockWidget, QMainWindow, QWidget

import main

W = main.P29MainWindow

HAUPT = {"dock_player": "dock_player", "dock_loop": "dock_loop",
         "dock_data": "dock_songdata", "dock_list": "dock_songlist",
         "dock_playlist": "dock_playlist", "dock_lyrics": "dock_lyrics",
         "dock_sequences": "dock_sequences"}
VERSTECKT = ("dock_loop_finder", "dock_manager", "dock_reports", "dock_potential",
             "dock_photo", "dock_rules", "dock_evening_planner", "dock_clock")


class _Haupt(QMainWindow):
    _reset_layout = W._reset_layout
    # Dual View (intern#231) beendet _reset_layout am Ende; hier ohne Belang
    _dual_view_discard = lambda self: None

    def __init__(self, ini):
        super().__init__()
        self.setCentralWidget(QWidget())
        self.setDockOptions(QMainWindow.AnimatedDocks | QMainWindow.AllowTabbedDocks
                            | QMainWindow.AllowNestedDocks)
        self._settings = ini
        self._pre_fullsize_state = {}
        namen = dict(HAUPT, **{a: a for a in VERSTECKT},
                     dock_notes="dock_notes", dock_sequence_view="dock_sequence_view")
        for attr, obj in namen.items():
            d = QDockWidget(obj, self)
            d.setObjectName(obj)
            d.setWidget(QWidget())
            self.addDockWidget(Qt.RightDockWidgetArea, d)
            setattr(self, attr, d)
        # Ausgangslage: Haupt-Docks stecken bunt gemischt in Tab-Gruppen
        self.tabifyDockWidget(self.dock_notes, self.dock_lyrics)
        self.tabifyDockWidget(self.dock_notes, self.dock_data)
        self.tabifyDockWidget(self.dock_notes, self.dock_sequences)
        self.tabifyDockWidget(self.dock_sequences, self.dock_sequence_view)
        self.tabifyDockWidget(self.dock_list, self.dock_playlist)
        self.tabifyDockWidget(self.dock_player, self.dock_loop)
        self.show()


@pytest.fixture
def haupt(qapp, tmp_path, keep):
    ini = QSettings(str(tmp_path / "callers_caddy.ini"), QSettings.IniFormat)
    h = keep(_Haupt(ini))
    qapp.processEvents()
    return h


def _tabs(h, dock):
    return sorted(d.objectName() for d in h.tabifiedDockWidgets(dock))


def test_reset_mehrfach_ohne_absturz_mit_standard_layout(haupt, qapp):
    h = haupt
    for _ in range(5):
        h._reset_layout()
        qapp.processEvents()
    for attr in HAUPT:
        d = getattr(h, attr)
        assert not d.isFloating() and d.isVisible(), attr
    assert _tabs(h, h.dock_list) == ["dock_playlist"]
    assert set(_tabs(h, h.dock_lyrics)) >= {"dock_songdata", "dock_sequences"}
    assert _tabs(h, h.dock_player) == [] and _tabs(h, h.dock_loop) == []
    # Spalten: Player | Songliste | Lyrics
    assert h.dock_player.x() < h.dock_list.x() < h.dock_lyrics.x()
    assert h.dock_loop.y() > h.dock_player.y()                 # Loop unter Player
    for attr in VERSTECKT:
        assert not getattr(h, attr).isVisible(), attr
