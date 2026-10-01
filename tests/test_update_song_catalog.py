"""tools/update_song_catalog.py: Pruefung und Diff (intern#126).

Der Git-/PR-Teil wird nicht ausgefuehrt; geprueft wird, was entscheidet, ob
ueberhaupt ein PR entsteht.
"""
import importlib.util
import pathlib

import pytest

_TOOL = pathlib.Path(__file__).resolve().parent.parent / "tools" / "update_song_catalog.py"
_spec = importlib.util.spec_from_file_location("update_song_catalog", _TOOL)
tool = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(tool)

HEADER = ",".join(tool.COLUMNS)


def _csv(path, lines, crlf=False):
    nl = "\r\n" if crlf else "\n"
    path.write_bytes((nl.join([HEADER, *lines]) + nl).encode("utf-8"))
    return path


@pytest.fixture
def target(tmp_path, monkeypatch):
    t = tmp_path / "repo" / "music_extended_data.csv"
    t.parent.mkdir()
    _csv(t, [f"Song {i},Lbl,L,{i},Patter,,,," for i in range(100)])
    monkeypatch.setattr(tool, "TARGET", t)
    return t


def test_falsche_spalten_werden_abgelehnt(tmp_path, target):
    src = tmp_path / "src.csv"
    src.write_text("Title,Label\nA,B\n", encoding="utf-8")
    rows, err = tool.validate(src)
    assert err and "Spalten" in err


def test_stark_geschrumpfter_katalog_wird_abgelehnt(tmp_path, target):
    src = _csv(tmp_path / "src.csv", [f"Song {i},Lbl,L,{i},Patter,,,," for i in range(50)])
    rows, err = tool.validate(src)
    assert err and "geschrumpft" in err


def test_diff_neu_und_entfallen(tmp_path, target):
    lines = [f"Song {i},Lbl,L,{i},Patter,,,," for i in range(1, 100)] + ["Neu,Lbl,L,500,Patter,,,,"]
    rows, err = tool.validate(_csv(tmp_path / "src.csv", lines))
    assert not err
    added, removed = tool.diff(rows)
    assert added == [("Neu", "L", "500")]
    assert removed == [("Song 0", "L", "0")]


def test_crlf_quelle_gilt_als_unveraendert(tmp_path, target):
    """Der Scraper schreibt CRLF, das Repo LF - inhaltlich gleich = kein PR."""
    src = _csv(tmp_path / "src.csv",
               [f"Song {i},Lbl,L,{i},Patter,,,," for i in range(100)], crlf=True)
    rows, err = tool.validate(src)
    assert not err
    assert tool._read(target)[1] == rows


def test_fmt_ohne_nummer():
    assert tool._fmt(("Annie’s Song", "10+1", "")) == "Annie’s Song (10+1)"
    assert tool._fmt(("Titel", "", "")) == "Titel"
