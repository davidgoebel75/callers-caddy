"""Update-Pruefung: Versionsordner und Update-ZIPs im Schema ab 2.0 (Major.Minor.Patch).

Ohne Netz: die Parser bekommen nachgebautes Drive-HTML.
"""
import re

import pytest

import update_check


def _folder(fid, label):
    return f'<div data-id="{fid}"><span aria-label="{label} Shared folder"></span></div>'


_IDS = {v: f"id_{v.replace('.', '_')}_xxxxxxxxxxxxxxxxxxxx" for v in
        ("0.161", "0.162", "2.0.0", "2.0.9", "2.0.10", "2.1.0")}


@pytest.mark.parametrize("text, expected", [
    ("2.0.16", (2, 0, 16)), ("0.162", (0, 162)), ("", None), ("2.0.x", None),
])
def test_parse_version(text, expected):
    assert update_check._parse_version(text) == expected


def test_2_0_0_liegt_ueber_den_prototyp_nummern():
    assert update_check._parse_version("2.0.0") > update_check._parse_version("0.162")
    assert update_check._parse_version("2.0.10") > update_check._parse_version("2.0.9")


def test_ordnerliste_kennt_beide_formate_und_sortiert_numerisch():
    html = "".join(_folder(fid, v) for v, fid in _IDS.items())
    found = [v for _vt, v, _fid in update_check._list_version_folders(html)]
    assert found == ["2.1.0", "2.0.10", "2.0.9", "2.0.0", "0.162", "0.161"]


@pytest.mark.parametrize("version", ["2.0.0", "2.0.16", "0.162"])
def test_update_zip_wird_erkannt(version):
    html = f'<div data-id="file_xxxxxxxxxxxxxxxxxxxxxx">Callers_Caddy_Update_{version}.zip</div>'
    assert update_check._find_update_zip(html) == (version, "file_xxxxxxxxxxxxxxxxxxxxxx")


def test_vollpaket_ist_kein_download_ziel():
    html = '<div data-id="file_xxxxxxxxxxxxxxxxxxxxxx">Callers_Caddy_2.0.0.zip</div>'
    assert update_check._find_update_zip(html) is None


# Erkennung, wie sie in allen ausgelieferten Clients bis 0.162 steckt.
# NICHT anpassen: das ist eingefrorener Fremdstand, den wir nicht mehr aendern koennen.
_OLD_FOLDER_RE = re.compile(r'aria-label="(\d+\.\d+) Shared folder"')
_OLD_UPDATE_RE = re.compile(r"Callers_Caddy_Update_(\d+\.\d+)\.zip")


def _old_client_sees(parent_html, current="0.162"):
    cur = tuple(int(p) for p in current.split("."))
    return [m.group(1) for m in _OLD_FOLDER_RE.finditer(parent_html)
            if tuple(int(p) for p in m.group(1).split(".")) > cur]


def _download_area():
    return (_folder(_IDS["0.162"], "0.162") + _folder("bridge_xxxxxxxxxxxxxxxxxxxx", "2.0")
            + _folder(_IDS["2.0.0"], "2.0.0"))


def test_alter_client_findet_nur_die_bruecke():
    # Ohne Brueckenordner saehe 0.162 gar nichts: "2.0.0" passt nicht in sein Muster.
    assert _old_client_sees(_folder(_IDS["2.0.0"], "2.0.0")) == []
    assert _old_client_sees(_download_area()) == ["2.0"]
    m = _OLD_UPDATE_RE.search("Callers_Caddy_Update_2.0.zip")
    assert m and m.group(1) == "2.0"
    # Die echte 2.x-Update-ZIP erkennt er nicht, die Bruecke braucht den eigenen Namen.
    assert _OLD_UPDATE_RE.search("Callers_Caddy_Update_2.0.0.zip") is None


def test_neuer_client_ueberspringt_die_bruecke(monkeypatch):
    found = [v for _vt, v, _fid in update_check._list_version_folders(_download_area())]
    assert found == ["2.0.0", "0.162"]
    inner = '<div data-id="file_xxxxxxxxxxxxxxxxxxxxxx">Callers_Caddy_Update_2.0.zip</div>'
    monkeypatch.setattr(update_check, "_fetch",
                        lambda url: _download_area() if url == update_check.UPDATE_URL else inner)
    # 2.0.0 installiert: die Bruecke ist kein Update, auch nicht bei spaeteren Nummern
    assert update_check.find_latest_update("2.0.0") is None
    assert update_check.find_latest_update("2.0.7") is None


def test_von_0_162_auf_2_0_0(monkeypatch):
    parent = _folder(_IDS["0.162"], "0.162") + _folder(_IDS["2.0.0"], "2.0.0")
    inner = '<div data-id="file_xxxxxxxxxxxxxxxxxxxxxx">Callers_Caddy_Update_2.0.0.zip</div>'
    monkeypatch.setattr(update_check, "_fetch",
                        lambda url: parent if url == update_check.UPDATE_URL else inner)
    version, url = update_check.find_latest_update("0.162")
    assert version == "2.0.0" and "file_xxxxxxxxxxxxxxxxxxxxxx" in url
    assert update_check.find_latest_update("2.0.0") is None
