"""Tests fuer das Mengengeruest je Tanzprogramm in tools/seq_invariants.py (BL-210.1).

Geprueft wird ausschliesslich die oeffentliche Funktion ``capture()`` gegen eine
frische temporaere DB. Beim Oeffnen spielt ``SongDatabase`` die gebuendelte
Referenz ein (reference_calls.json, 775 call_programs), es gibt also echte
Figuren mit echten Baendern.

Testaufbau (zwei Sequenzen, Figuren bewusst gewaehlt):

  Sequenz "einfach": Circle Left + Dosado      -> Baender je Figur {10, 30}
  Sequenz "A2":      Circle Left + Box Transfer-> Box Transfer nur Band {60}

Daraus folgen die erwarteten Trefferzahlen (Vorgabe, NICHT aus der Rechnung des
Werkzeugs abgeleitet):

  Basic 1 (Band 10): nur die einfache Sequenz  -> 1
  Advanced 2 (60):   beide Sequenzen           -> 2
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools"))

import seq_invariants  # noqa: E402


# Figuren der Referenz mit bekannten Baendern (siehe Modul-Docstring)
CALL_SIMPLE = ["Circle Left", "Dosado"]
CALL_A2 = ["Circle Left", "Box Transfer"]
MAPPINGS = [
    ("Circle Left", "call_circle_left"),
    ("Dosado", "call_dosado"),
    ("Box Transfer", "call_box_transfer"),
]


@pytest.fixture(scope="module")
def db_path(tmp_path_factory):
    """Frische DB mit genau zwei Sequenzen und bekannten Figuren-Zuordnungen."""
    from song_db import SongDatabase

    path = str(tmp_path_factory.mktemp("bands") / "test.db")
    db = SongDatabase(path)
    db.set_call_text_mappings(MAPPINGS)
    db.insert_sequence(CALL_SIMPLE)
    db.insert_sequence(CALL_A2)
    db.close()   # capture() oeffnet die DB selbst
    return path


@pytest.fixture(scope="module")
def snap(db_path):
    return seq_invariants.capture(db_path)


def test_band_treffer_je_tanzprogramm(snap):
    counts = snap["band_counts"]
    # Basic 1 kennt nur Band 10: die A2-Sequenz faellt raus.
    assert counts["bands_BASIC1"] == 1
    # Advanced 2 deckt alles bis Band 60: beide Sequenzen sind tanzbar.
    assert counts["bands_A2"] == 2


def test_nur_zaehlt_sequenzen_die_das_oberste_band_brauchen(snap):
    counts = snap["band_counts"]
    # "Nur A2": Box Transfer (Band 60) ist mit den Baendern darunter nicht
    # tanzbar -> genau die A2-Sequenz bleibt uebrig.
    assert counts["bands_A2_only"] == 1
    # "Nur Mainstream 2026": die einfache Sequenz ist schon mit Basic 1/2
    # tanzbar, braucht Band 30 also nicht -> kein Treffer.
    assert counts["bands_MS2026_only"] == 0
    # Unter Band 10 liegt nichts: wie im Widget (_get_bands_below -> None)
    # bleibt der "Nur"-Filter aus und die Zahl entspricht dem Band-Treffer.
    assert counts["bands_BASIC1_only"] == counts["bands_BASIC1"] == 1


def test_mengengeruest_ist_wiederholbar(db_path, snap):
    # Referenz v3 bringt 20 Tanzprogramme mit, jedes mit Band -> 20 Mengen,
    # je Menge zwei Zahlen (Band-Treffer und "nur").
    assert snap["band_sets"] == 20
    assert len(snap["band_counts"]) == 2 * snap["band_sets"]
    # Zweiter Lauf auf derselben DB muss dieselben Zahlen liefern, sonst ist der
    # Fingerabdruck als Vorher/Nachher-Nachweis unbrauchbar.
    zweiter = seq_invariants.capture(db_path)
    assert zweiter["band_counts"] == snap["band_counts"]
    assert zweiter["band_counts_hash"] == snap["band_counts_hash"]


def test_enthaelt_erfasst_auch_weitere_figuren_der_menge(tmp_path):
    # BL-210: Dosado steht nur in der Zusatztabelle, Box Transfer ist die
    # hoechste Figur. Der Fingerabdruck muss beide Figuren erfassen.
    from song_db import SongDatabase

    path = str(tmp_path / "menge.db")
    db = SongDatabase(path)
    db.insert_sequence(["Dosado & Box Transfer"])
    db.set_call_text_figures("Dosado & Box Transfer",
                             ["call_dosado", "call_box_transfer"])
    db.close()

    snap = seq_invariants.capture(path)

    assert snap["contains_entity_count"] == 2
    assert snap["contains_total_hits"] == 2
