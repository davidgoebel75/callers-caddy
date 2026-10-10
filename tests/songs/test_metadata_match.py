"""Zuordnungs-Pruefungen fuer Metadaten-Importe (intern#108).

same_song_title: Der Metadaten-Import ordnet ueber die Song-id zu; eine KI hat
Werte an falsche ids gehaengt (stimmig, aber beim falschen Song). Der
zurueckgelieferte Titel muss deshalb zum Song passen.

label_number_matches: Der CSV-Abgleich nahm als Ersatz den ersten Eintrag, bei
dem NUR die Nummer oder NUR das Label-Kuerzel passte.
"""
import pytest

from song_match import label_number_matches, same_song_title


@pytest.mark.parametrize("file_title, db_title, db_filename", [
    ("Ring of fire", "Ring of fire", "Patter/Ring of fire.mp3"),
    ("Ring Of Fire", "Ring of fire", ""),                    # Gross/klein
    ("Rock This Town-Plus", "Rock this town-Plus", ""),
    ("Achy Breaky Heart", "Achy Breaky Heart Plus", ""),     # KI kuerzt leicht
    ("I Can't Stop Loving You", "I Can’t Stop Loving You", ""),  # Quotes
    ("20 Hoedown", "", "Patter/20 Hoedown.mp3"),             # Titel leer -> Datei
])
def test_titel_passt(file_title, db_title, db_filename):
    assert same_song_title(file_title, db_title, db_filename)


@pytest.mark.parametrize("file_title, db_title", [
    ("Rock this town-Plus", "Ring of fire"),      # Fall aus der Nutzer-DB
    ("Hit The Road Jack-Plus", "Tom Dooley-B"),
    ("Wagon Wheel-B", "El Paso"),
])
def test_vertauschter_titel_faellt_auf(file_title, db_title):
    assert not same_song_title(file_title, db_title, "")


@pytest.mark.parametrize("db_label, name, code, number, erwartet", [
    ("RYL 404", "Royal Records", "RYL", "404", True),
    ("Royal Records 404", "Royal Records", "RYL", "404", True),
    ("RYL 0404", "Royal Records", "RYL", "404", True),        # fuehrende Null
    ("RYL 404", "Royal Records", "RYL", "405", False),        # andere Nummer
    ("RYL 404", "Fine Tune", "FT", "404", False),             # nur Nummer gleich
    ("RYL", "Royal Records", "RYL", "404", False),            # keine Nummer
    ("", "Royal Records", "RYL", "404", False),
])
def test_label_und_nummer_muessen_zusammen_passen(db_label, name, code, number,
                                                  erwartet):
    assert label_number_matches(db_label, name, code, number) is erwartet


# --- Ganzer Importweg: vertauschte Zuordnung wird erkannt -------------------

import json
import types

import potential_widget as pw
from song_db import SongDatabase


@pytest.fixture
def import_lauf(qapp, tmp_path, monkeypatch):
    db = SongDatabase(str(tmp_path / "t.db"))
    ring = db.get_or_create("Ring of fire.mp3")
    rock = db.get_or_create("Rock this town.mp3")

    def _lauf(eintraege):
        pfad = tmp_path / "antwort.json"
        pfad.write_text(json.dumps(eintraege), encoding="utf-8")
        monkeypatch.setattr(pw.QFileDialog, "getOpenFileName",
                            staticmethod(lambda *a, **k: (str(pfad), "")))
        gesehen = {}

        class _Vorschau:
            def __init__(self, rows, parent=None, notice=""):
                gesehen["rows"], gesehen["notice"] = rows, notice

            def exec(self):
                return pw.QDialog.Rejected       # nichts schreiben

        monkeypatch.setattr(pw, "_MetaImportPreviewDialog", _Vorschau)
        fake = types.SimpleNamespace(db=db)
        pw.PotentialWidget._on_meta_import(fake)
        return gesehen
    return _lauf, ring, rock


def test_vertauschte_ids_werden_gewarnt(import_lauf):
    lauf, ring, rock = import_lauf
    # KI hat Rock-this-town-Werte an die id von Ring of fire gehaengt
    gesehen = lauf([
        {"id": ring.id, "title": "Rock this town", "original_artist": "Stray Cats"},
        {"id": rock.id, "title": "Rock this town", "original_artist": "Stray Cats"},
    ])
    warnung = {sid: w for sid, _t, _f, _v, w in gesehen["rows"]}
    assert "Rock this town" in warnung[ring.id]      # rot, nicht angehakt
    assert warnung[rock.id] == ""                    # passt
    assert gesehen["notice"] == ""


def test_alte_datei_ohne_titel_gibt_hinweis(import_lauf):
    lauf, ring, _rock = import_lauf
    gesehen = lauf([{"id": ring.id, "original_artist": "Johnny Cash"}])
    assert gesehen["rows"][0][4] == ""               # Zeile selbst unauffaellig
    assert "1" in gesehen["notice"]                  # aber Hinweis oben


def test_unbekannte_id_wird_gewarnt(import_lauf):
    lauf, _ring, _rock = import_lauf
    gesehen = lauf([{"id": 9999, "title": "X", "original_artist": "Y"}])
    assert gesehen["rows"][0][4] != ""
