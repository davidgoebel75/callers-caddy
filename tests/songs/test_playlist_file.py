"""Playlist-Datei lesen, parsen, schreiben (intern#140), ohne Qt."""
import pytest

from caddy.songs.playlist_file import PlaylistLine, parse_lines, read, write


def test_rundreise_mit_und_ohne_cut(tmp_path):
    lines = [PlaylistLine("P", 2, 16, "Alpha"),
             PlaylistLine("S", 1, 0, "Käse mit 3 Worten"),
             PlaylistLine("P", 10, 0, "7 Zwerge")]
    p = str(tmp_path / "l.txt")
    write(p, lines)
    assert read(p) == lines


def test_schreibformat_und_utf8(tmp_path):
    p = tmp_path / "l.txt"
    write(str(p), [PlaylistLine("P", 2, 16, "Käse"), PlaylistLine("S", 3, 0, "B")])
    assert p.read_bytes() == "P 2:16 Käse\nS 3 B\n".encode("utf-8").replace(
        b"\n", b"\r\n" if _crlf() else b"\n")


def _crlf():
    import os
    return os.linesep == "\r\n"


@pytest.mark.parametrize("text, expected", [
    ("P Song Titel", PlaylistLine("P", 0, 0, "Song Titel")),      # Altformat
    ("P Song", PlaylistLine("P", 0, 0, "Song")),
    ("S 3 Titel", PlaylistLine("S", 3, 0, "Titel")),
    ("P 2:16 Titel", PlaylistLine("P", 2, 16, "Titel")),
    ("X 1 Titel", PlaylistLine("P", 1, 0, "Titel")),              # Modus unbekannt
    ("s 1 t", PlaylistLine("S", 1, 0, "t")),                      # klein geschrieben
    ("  P 1 Titel  ", PlaylistLine("P", 1, 0, "Titel")),
    ("P 2:x Titel", PlaylistLine("P", 0, 0, "2:x Titel")),
])
def test_parse_zeile(text, expected):
    assert parse_lines([text]) == [expected]


def test_leere_und_einwortzeilen_werden_uebersprungen():
    assert parse_lines(["", "   ", "Nur", "P 1 A\n"]) == [PlaylistLine("P", 1, 0, "A")]


def test_ohne_cut_bleibt_cut_token_im_namen():
    # Verhalten von load_permanent_filters (Abweichung, siehe abweichungen-fuer-david.md)
    assert parse_lines(["P 2:16 Titel", "P 2 Titel"], with_cut=False) == [
        PlaylistLine("P", 0, 0, "2:16 Titel"), PlaylistLine("P", 2, 0, "Titel")]


@pytest.mark.parametrize("encoding", ["utf-8", "cp1252"])
def test_lesen_utf8_und_cp1252(tmp_path, encoding):
    p = tmp_path / "l.txt"
    p.write_bytes("P 1 Käse\n".encode(encoding))
    assert read(str(p)) == [PlaylistLine("P", 1, 0, "Käse")]


def test_fehlende_datei_wirft_oserror(tmp_path):
    with pytest.raises(OSError):
        read(str(tmp_path / "gibtsnicht.txt"))
