"""Vorhoeren ohne startbares Ausgabegeraet (intern#237, Review #158).

Wie beim Play: bleibt die Engine nach play() stehen, zeigt das Vorhoeren den
Hinweis, beendet sich (Hauptgeraet zurueck) und laesst die Knoepfe im
Stop-Zustand, statt "Vorhoeren" ohne Ton anzuzeigen.
"""
import os
import pytest

import player_widget
from skin_manager import SkinManager


class _Engine:
    playing = False

    def __init__(self):
        self.notices = [("failed", "GLE 0x48F")]

    def is_loaded(self):
        return True

    def seek(self, _pos):
        pass

    def play(self):
        pass   # kein Geraet startbar: playing bleibt False

    def take_device_notice(self):
        return self.notices.pop() if self.notices else None


@pytest.fixture
def player(keep):
    sm = SkinManager(os.path.dirname(player_widget.__file__))
    sm.load("default")
    w = keep(player_widget.PlayerWidget(engine=None, paths=None, skin_mgr=sm))
    w.engine = _Engine()
    return w


def test_vorhoeren_ohne_geraet_bleibt_gestoppt(player):
    calls = []
    player.on_audition = lambda: calls.append("an")
    player.on_exit_audition = lambda: calls.append("aus")
    player.btn_audition.setChecked(True)
    player._on_audition()
    assert calls == ["an", "aus"]                 # Hauptgeraet wiederhergestellt
    assert not player._audition_active
    assert not player.btn_audition.isChecked()
    assert not player.btn_pause.isEnabled()
    assert not player.btn_stop.isEnabled()
    assert player._device_notice_box.isVisible()
    assert player.engine.notices == []            # Hinweis abgeholt
