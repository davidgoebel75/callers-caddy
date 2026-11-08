"""Ein Tippfehler im INI-Schluessel wird in lyrics_widget nicht still verschluckt (intern#144)."""
from types import SimpleNamespace

import pytest

from caddy.settings import ini_keys
from lyrics_widget import LyricsWidget


def _kaputt(*a, **k):
    raise KeyError("lyrics/tippfehler")


@pytest.mark.parametrize("methode", ["init_dynamic_preference", "reload_invert_settings"])
def test_unbekannter_schluessel_wirft_keyerror(monkeypatch, methode):
    fake = SimpleNamespace(_settings=object())
    monkeypatch.setattr(ini_keys, "get", _kaputt)
    with pytest.raises(KeyError):
        getattr(LyricsWidget, methode)(fake)
