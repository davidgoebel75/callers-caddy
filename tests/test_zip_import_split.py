"""ZIP-Import: mehrere Songs in einem ZIP (intern#125).

Nachgebaut aus dem Nutzer-Fall: Eine Patter-Lieferung mit zwei Titeln, je mit
Extended-Version, landete als EIN Song. Die Tests pruefen den Splitter
(Aufteilen nur mit eigener Hauptspur je Song), die Typ-Vorbelegung nach Lyrics
und im Preview das Umschalten je ZIP sowie den Duplikat-Hinweis.
"""
import zipfile

import pytest

import zip_import

RED_FEATHER = ["let's dance.mp3", "let's dance-extended.mp3",
               "red feather.mp3", "red feather-extended.mp3"]


@pytest.fixture
def make_zip(tmp_path):
    def _make(name, files):
        p = tmp_path / name
        with zipfile.ZipFile(p, "w") as zf:
            for f in files:
                zf.writestr(f, b"x")
        return str(p)
    return _make


@pytest.fixture
def analyze(tmp_path):
    results = []

    def _run(*zips):
        r = zip_import.analyze(list(zips), dest_dir=str(tmp_path / "out"))
        results.append(r)
        return r
    yield _run
    for r in results:
        zip_import.cleanup(r)


def _titles(bundles):
    return [b.title for b in bundles]


def test_zwei_patter_mit_extended_werden_erkannt(make_zip, analyze):
    r = analyze(make_zip("2002 Red Feather.zip", RED_FEATHER))
    g = r.zips[0]
    assert g.is_multi
    assert _titles(g.split) == ["Let's Dance", "Red Feather"]
    for b in g.split:
        assert [a.label_text for a in b.audio] == ["Instrumental", "Extended"]
        assert not b.singing_suggested       # keine Lyrics -> Patter
    # Ohne Entscheidung bleibt es beim bisherigen Verhalten: ein Song.
    assert len(r.bundles) == 1


def test_umschalten_auf_getrennt(make_zip, analyze):
    r = analyze(make_zip("2002 Red Feather.zip", RED_FEATHER))
    r.zips[0].use_split = True
    r.refresh_bundles()
    assert _titles(r.bundles) == ["Let's Dance", "Red Feather"]
    assert r.is_complete


def test_bundle_mit_vielen_songs_und_lyrics(make_zip, analyze):
    r = analyze(make_zip("Sale.zip", [
        "Song Alpha.mp3", "Song Alpha (V).mp3", "Beta Blues.mp3",
        "Gamma Ray.mp3", "Beta Blues.rtf", "cue.pdf"]))
    g = r.zips[0]
    assert _titles(g.split) == ["Beta Blues", "Gamma Ray", "Song Alpha"]
    beta, gamma, alpha = g.split
    assert [lc.filename for lc in beta.lyrics] == ["Beta Blues.rtf"]
    assert beta.singing_suggested and not gamma.singing_suggested
    assert [a.label_text for a in alpha.audio] == ["Instrumental", "Vocal"]
    # Unzuordenbare Lyrics fallen nur in der geteilten Sicht unter "Sonstige".
    assert g.unassigned == ["cue.pdf"]
    assert r.other_files == []
    g.use_split = True
    r.refresh_bundles()
    assert r.other_files == [("cue.pdf", zip_import.UNASSIGNED_LYRICS_REASON)]
    assert r.is_complete


@pytest.mark.parametrize("files", [
    ["RR 123 - Some Song.mp3", "RR 123 - Some Song (V).mp3", "RR123.rtf"],
    ["Alpha.mp3", "Beta (V).mp3"],          # zweiter "Song" ohne Hauptspur
    ["Title.mp3", "Title-extended.mp3"],
])
def test_kein_split_ohne_eigene_hauptspur_je_song(make_zip, analyze, files):
    r = analyze(make_zip("pkg.zip", files))
    assert not r.zips[0].is_multi
    assert len(r.bundles) == 1


def test_singing_nur_mit_lyrics(make_zip, analyze):
    r = analyze(make_zip("RR 123.zip", [
        "RR 123 - Some Song.mp3", "RR 123 - Some Song (V).mp3", "RR123.rtf"]))
    assert r.bundles[0].singing_suggested   # ein Song: jede Lyrics-Datei zaehlt
    r = analyze(make_zip("Patter.zip", ["Hoedown.mp3"]))
    assert not r.bundles[0].singing_suggested


def test_song_key_zieht_modifier_und_rollen_ab():
    lists = zip_import.ImportLists.defaults()
    args = (lists.modifiers.effective(), lists.labels.effective(),
            lists.roles.effective())
    assert zip_import.song_key("red feather-extended", *args) == "redfeather"
    assert zip_import.song_key("Red Feather (V)", *args) == "redfeather"


# ---------------------------------------------------------------------------
# Preview-Dialog
# ---------------------------------------------------------------------------

def _dialog(result, dup_lookup=None, tmp_path=None):
    from zip_import_dialog import ZipImportPreviewDialog
    lists = zip_import.ImportLists.defaults()
    return ZipImportPreviewDialog(result, lists, str(tmp_path / "lists.json"),
                                  dup_lookup=dup_lookup)


def test_preview_umschalten_je_zip(qapp, make_zip, analyze, tmp_path):
    r = analyze(make_zip("2002 Red Feather.zip", RED_FEATHER),
                make_zip("Patter.zip", ["Hoedown.mp3"]))
    r.zips[0].use_split = True
    r.refresh_bundles()
    dlg = _dialog(r, tmp_path=tmp_path)
    # Reihenfolge je ZIP; ohne Label im MP3-Namen kommt der Titel wie bisher
    # aus dem ZIP-Namen ("Patter").
    assert [d["title"] for d in dlg.get_decisions()] == \
        ["Let's Dance", "Red Feather", "Patter"]
    # Typ-Vorbelegung: alle ohne Lyrics -> Patter
    assert all(d["is_pattern"] and not d["is_singing"] for d in dlg.get_decisions())

    dlg._on_split_toggled(r.zips[0], merged=True)
    decisions = dlg.get_decisions()
    assert len(decisions) == 2
    assert len(decisions[0]["audio"]) == 4
    dlg._on_split_toggled(r.zips[0], merged=False)
    assert len(dlg.get_decisions()) == 3


def test_preview_duplikat_bietet_anhaengen_an(qapp, make_zip, analyze, tmp_path):
    r = analyze(make_zip("2002 Red Feather.zip", RED_FEATHER))
    r.zips[0].use_split = True
    r.refresh_bundles()
    existing = {"let's dance.mp3": "Let's Dance"}
    dlg = _dialog(r, dup_lookup=existing.get, tmp_path=tmp_path)
    by_title = {d["title"]: d for d in dlg.get_decisions()}
    assert by_title["Let's Dance"]["attach_new"] is True
    assert by_title["Red Feather"]["attach_new"] is False
    # Haken abwaehlen -> nichts anhaengen
    ui = next(u for u in dlg._bundles_ui if u["title"].text() == "Let's Dance")
    ui["dup_chk"].setChecked(False)
    by_title = {d["title"]: d for d in dlg.get_decisions()}
    assert by_title["Let's Dance"]["attach_new"] is False
