"""Update-Quelle aus der INI (Schluessel update/url)."""
import pytest
from PySide6.QtCore import QSettings

import update_check

TEST_URL = "https://drive.google.com/drive/folders/TEST_ORDNER"


@pytest.fixture
def settings(tmp_path):
    return QSettings(str(tmp_path / "callers_caddy.ini"), QSettings.IniFormat)


def test_ohne_eintrag_gilt_standard(settings):
    assert update_check.configured_url(settings) == update_check.UPDATE_URL
    assert update_check.custom_source_note(settings) == ""


def test_ohne_settings_gilt_standard():
    assert update_check.configured_url(None) == update_check.UPDATE_URL


def test_eintrag_wird_genutzt(settings):
    settings.setValue("update/url", f"  {TEST_URL}  ")
    assert update_check.configured_url(settings) == TEST_URL
    assert TEST_URL in update_check.custom_source_note(settings)


@pytest.mark.parametrize("value", ["", "   ", "callerscaddy.de/test", "file:///C:/x",
                                   "http://drive.google.com/drive/folders/X"])
def test_ungueltiger_eintrag_faellt_auf_standard(settings, value):
    settings.setValue("update/url", value)
    assert update_check.configured_url(settings) == update_check.UPDATE_URL
    assert update_check.custom_source_note(settings) == ""


def test_find_latest_update_fragt_die_uebergebene_url(monkeypatch):
    fetched = []
    monkeypatch.setattr(update_check, "_fetch", lambda url: fetched.append(url) or "")
    assert update_check.find_latest_update("2.0.0", TEST_URL) is None
    assert fetched == [TEST_URL]


def test_find_latest_update_ohne_url_nimmt_aktuelle_konstante(monkeypatch):
    """tools/update_check_probe.py setzt UPDATE_URL am Modul um."""
    fetched = []
    monkeypatch.setattr(update_check, "_fetch", lambda url: fetched.append(url) or "")
    monkeypatch.setattr(update_check, "UPDATE_URL", TEST_URL)
    update_check.find_latest_update("2.0.0")
    assert fetched == [TEST_URL]
