"""Call-Map Export/Import mit Konfliktklaerung (intern#79).

Abnahme laut Issue: Export->Import gleiche DB ohne Konflikte, Import mit
geaenderter Menge (A/B/C je einmal), v1-Altdatei, unbekannte entity_id
(ueberspringen + melden). Dazu Davids Ergaenzungen: Empfehlung nach
Detailliertheit, dann Quelle; Massen-Buttons; "keine Figur" als eigene Menge.
"""
import json
from types import SimpleNamespace

import pytest
from PySide6.QtWidgets import QDialog

import mapping_io as mio

SPREAD = "concept_anything_and_spread"
TOUCH = "call_touch_a_quarter"
SWING = "call_swing_thru"
OCEAN = "call_pass_the_ocean"

T_SPREAD = "Heads Touch 1/4 & Spread"
T_SWING = "Swing Thru"
T_NONE = "Weird Comment Line"
T_OCEAN = "Pass The Ocean"


@pytest.fixture
def db(tmp_path):
    from song_db import SongDatabase
    d = SongDatabase(str(tmp_path / "t.db"))
    d.insert_sequence([T_SPREAD, T_SWING, T_NONE, T_OCEAN])
    d.set_call_text_figures(T_SPREAD, [SPREAD], mapped_by="manual")
    d.set_call_text_figures(T_SWING, [SWING], mapped_by="auto")
    d.set_call_text_figures(T_OCEAN, [OCEAN], mapped_by="auto")
    d.apply_call_text_figures_decisions([(T_NONE, [], "manual")])  # "keine Figur"
    return d


def _roundtrip(data):
    return json.loads(json.dumps(data))


# ---------------------------------------------------------------------------
# Format
# ---------------------------------------------------------------------------

def test_export_v2_mit_header_und_canonical(db):
    data = mio.build_export(db)
    assert data["format"] == mio.FORMAT_NAME and data["version"] == 2
    by_ct = {m["call_text"]: m for m in data["mappings"]}
    assert by_ct[T_SPREAD]["figures"] == [
        {"entity_id": SPREAD, "canonical_name": "(Anything) & Spread"}]
    assert by_ct[T_NONE]["figures"] == []           # "keine Figur" bleibt erhalten


def test_export_import_gleiche_db_ohne_konflikte(db):
    diff = db.diff_call_text_figures(mio.parse_import(_roundtrip(mio.build_export(db))))
    assert not diff["new"] and not diff["conflicts"] and not diff["skipped"]
    assert len(diff["identical"]) == 4


def test_v1_altdatei_wird_gelesen(db):
    v1 = _roundtrip(db.get_all_call_text_mappings())   # flache Liste wie bisher
    diff = db.diff_call_text_figures(mio.parse_import(v1))
    assert len(diff["identical"]) == 4 and not diff["conflicts"]


def test_mehrfach_figuren_round_trip(tmp_path, db):
    db.set_call_text_figures(T_SPREAD, [TOUCH, SPREAD], mapped_by="inferred")
    data = _roundtrip(mio.build_export(db))
    from song_db import SongDatabase
    other = SongDatabase(str(tmp_path / "other.db"))
    res = other.diff_call_text_figures(mio.parse_import(data))
    other.apply_call_text_figures_decisions(res["new"])
    assert set(other.get_call_text_figures(T_SPREAD)) == {TOUCH, SPREAD}


def test_unbekanntes_format_wirft():
    with pytest.raises(ValueError):
        mio.parse_import({"foo": 1})
    with pytest.raises(ValueError):
        mio.parse_import({"format": mio.FORMAT_NAME, "version": 99, "mappings": []})


def test_formatname_bleibt_fest():
    # Steht in allen exportierten Dateien; eine Aenderung macht sie unlesbar.
    assert mio.FORMAT_NAME == "callers-caddy-callmap"


def test_export_quelle_und_fehlende_angaben():
    db = SimpleNamespace(
        get_teaching_order_calls=lambda: [],
        get_all_call_text_mappings=lambda: [
            {"call_text": "X", "entity_id": "e1", "mapped_by": None},
            {"call_text": "Y", "entity_id": "e2", "mapped_by": "manual"}])
    data = mio.build_export(db)
    assert "exported_at" in data
    by_ct = {m["call_text"]: m for m in data["mappings"]}
    assert by_ct["X"]["mapped_by"] == "auto"           # ohne Quelle: auto
    assert by_ct["Y"]["mapped_by"] == "manual"
    assert by_ct["X"]["figures"] == [{"entity_id": "e1", "canonical_name": ""}]


def test_zu_neue_version_nennt_die_version():
    with pytest.raises(mio.CallMapFormatError) as exc:
        mio.parse_import({"format": mio.FORMAT_NAME, "version": 99, "mappings": []})
    assert exc.value.params == {"version": 99, "supported": mio.FORMAT_VERSION}


def test_v1_ueberspringt_kaputte_zeilen_und_liest_die_quelle():
    out = mio.parse_import([
        "kaputt", {"call_text": ""},
        {"call_text": "A", "entity_id": "e1", "mapped_by": "manual"},
        {"call_text": "A", "entity_id": "e1"},          # doppelt
        {"call_text": "B", "entity_id": None}])
    assert out["A"].figures == ["e1"] and out["A"].mapped_by == "manual"
    assert out["B"].figures == [] and out["B"].mapped_by == "auto"


def test_v2_ueberspringt_kaputte_eintraege_und_liest_die_quelle():
    out = mio.parse_import({"format": mio.FORMAT_NAME, "version": 2, "mappings": [
        "kaputt", {"call_text": ""},
        {"call_text": "A", "mapped_by": "manual",
         "figures": [{"entity_id": None}, "e1", {"entity_id": "e1"}]},
        {"call_text": "B"}]})
    assert out["A"].figures == ["e1"] and out["A"].mapped_by == "manual"
    assert out["B"].figures == [] and out["B"].mapped_by == "auto"
    assert mio.ImportedMapping().mapped_by == "auto"


# ---------------------------------------------------------------------------
# Vergleich
# ---------------------------------------------------------------------------

def test_unbekannte_figur_wird_uebersprungen_und_gemeldet(db):
    imp = {
        "New A": mio.ImportedMapping([SWING, "action_bogus"], "auto"),
        "New B": mio.ImportedMapping(["action_bogus"], "auto"),
    }
    diff = db.diff_call_text_figures(imp)
    assert diff["new"] == [("New A", [SWING], "auto")]
    assert diff["skipped"] == ["New B"]
    assert diff["unknown_figures"] == ["action_bogus"]


def test_keine_figur_gegen_figur_ist_konflikt(db):
    diff = db.diff_call_text_figures({T_NONE: mio.ImportedMapping([SWING], "auto")})
    assert diff["conflicts"] == [(T_NONE, [], "manual", [SWING], "auto")]


# ---------------------------------------------------------------------------
# Empfehlung und Massen-Regeln
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("loc, lmb, imp, imb, expected", [
    ([SPREAD], "manual", [TOUCH, SPREAD], "inferred", "B"),   # mehr Figuren
    ([TOUCH, SPREAD], "auto", [SPREAD], "manual", "A"),       # mehr Figuren lokal
    ([SWING], "auto", [OCEAN], "manual", "B"),                # gleich viele: Quelle
    ([SWING], "manual", [OCEAN], "inferred", "A"),
    ([SWING], "auto", [OCEAN], "auto", "A"),                  # Gleichstand -> lokal
])
def test_empfehlung(loc, lmb, imp, imb, expected):
    assert mio.recommend(loc, lmb, imp, imb) == expected


def test_closer_to_und_manual_side():
    assert mio.closer_to([TOUCH, SPREAD], [SPREAD], [TOUCH, SPREAD]) == "B"
    assert mio.closer_to([], [SPREAD], [TOUCH]) is None
    assert mio.closer_to([SWING], [SPREAD], [TOUCH]) is None   # Gleichstand
    assert mio.manual_side("manual", "auto") == "A"
    assert mio.manual_side("inferred", "manual") == "B"
    assert mio.manual_side("manual", "manual") is None


def test_quellen_rangfolge():
    rank = mio.source_rank
    assert rank("auto") < rank("inferred") < rank("manual")
    assert rank(None) == rank("import") == rank("auto")   # unbekannt zaehlt wie auto
    assert rank("MANUAL") == rank("manual")


def test_closer_to_bewertet_ueberschuss_und_leere_seite():
    # Lokal exakt, Import mit einer Figur zu viel -> lokal naeher
    assert mio.closer_to([SWING], [SWING], [SWING, OCEAN]) == "A"
    # Leere Seite ist weiter weg als ein Treffer
    assert mio.closer_to([SWING], [], [SWING]) == "B"


def test_muster_vorschlag(db):
    suggest = mio.make_pattern_suggester(
        db.get_teaching_order_calls(), db.get_all_call_text_figures())
    assert suggest("Swing Thru, Pass The Ocean") == [SWING, OCEAN]   # Mengen-Vorschlag
    assert suggest(T_SWING) == [SWING]                                # Volltreffer
    assert suggest(T_NONE) == []


# ---------------------------------------------------------------------------
# Dialog und Ablauf
# ---------------------------------------------------------------------------

def _conflict_dialog(db, conflicts):
    from dialogs_mapping_conflict import MappingConflictDialog
    from sequences_widget import picker_entities_from_to_calls
    to_calls = db.get_teaching_order_calls()
    entities, labels, _ = picker_entities_from_to_calls(to_calls)
    return MappingConflictDialog(
        conflicts, entities, labels,
        suggest_fn=mio.make_pattern_suggester(to_calls, db.get_all_call_text_figures()),
        unknown_fn=db.unknown_figures)


def test_a_b_c_je_einmal(qapp, db, monkeypatch):
    imp = {
        T_SPREAD: mio.ImportedMapping([TOUCH, SPREAD], "inferred"),   # -> B
        T_SWING: mio.ImportedMapping([OCEAN], "auto"),                # -> A
        T_OCEAN: mio.ImportedMapping([SWING], "auto"),                # -> C
    }
    diff = db.diff_call_text_figures(imp)
    dlg = _conflict_dialog(db, diff["conflicts"])
    rows = {c[0]: i for i, c in enumerate(diff["conflicts"])}
    assert dlg.choices()[rows[T_SPREAD]] == "B"            # Empfehlung
    dlg._set_choice(rows[T_SWING], "A")
    monkeypatch.setattr(dlg, "_pick", lambda row: [OCEAN, SWING])
    dlg._combos[rows[T_OCEAN]].setCurrentIndex(2)
    dlg._on_choice(rows[T_OCEAN])
    db.apply_call_text_figures_decisions(dlg.decisions())
    assert set(db.get_call_text_figures(T_SPREAD)) == {TOUCH, SPREAD}
    assert db.get_call_text_figures(T_SWING) == [SWING]
    assert set(db.get_call_text_figures(T_OCEAN)) == {OCEAN, SWING}
    mb = {r["call_text"]: r["mapped_by"] for r in db.get_all_call_text_mappings()}
    assert mb[T_SPREAD] == "inferred" and mb[T_SWING] == "auto" and mb[T_OCEAN] == "manual"


def test_massen_buttons_lassen_c_stehen(qapp, db, monkeypatch):
    imp = {T_SPREAD: mio.ImportedMapping([TOUCH, SPREAD], "inferred"),
           T_SWING: mio.ImportedMapping([OCEAN], "manual")}
    diff = db.diff_call_text_figures(imp)
    dlg = _conflict_dialog(db, diff["conflicts"])
    rows = {c[0]: i for i, c in enumerate(diff["conflicts"])}
    monkeypatch.setattr(dlg, "_pick", lambda row: [SWING])
    dlg._combos[rows[T_SWING]].setCurrentIndex(2)
    dlg._on_choice(rows[T_SWING])
    dlg._set_all(lambda i: "A")
    assert dlg.choices()[rows[T_SPREAD]] == "A"
    assert dlg.choices()[rows[T_SWING]] == "C"
    dlg._closer_to_manual()                    # T_SPREAD: lokal manual -> A
    assert dlg.choices()[rows[T_SPREAD]] == "A"
    dlg._closer_to_pattern()                   # Muster sieht Touch + Spread -> B
    assert dlg.choices()[rows[T_SPREAD]] == "B"


def test_c_abbrechen_stellt_vorige_wahl_wieder_her(qapp, db, monkeypatch):
    diff = db.diff_call_text_figures({T_SWING: mio.ImportedMapping([OCEAN], "auto")})
    dlg = _conflict_dialog(db, diff["conflicts"])
    before = dlg.choices()[0]
    monkeypatch.setattr(dlg, "_pick", lambda row: None)
    dlg._combos[0].setCurrentIndex(2)
    dlg._on_choice(0)
    assert dlg.choices()[0] == before
    assert dlg._combos[0].currentData() == before


def test_ablauf_abbruch_schreibt_nichts(qapp, db, monkeypatch):
    import dialogs_mapping_conflict as dmc
    monkeypatch.setattr(dmc.MappingConflictDialog, "exec",
                        lambda self: QDialog.Rejected)
    data = {"format": mio.FORMAT_NAME, "version": 2, "mappings": [
        {"call_text": "Brand New", "mapped_by": "auto",
         "figures": [{"entity_id": SWING}]},
        {"call_text": T_SWING, "mapped_by": "auto",
         "figures": [{"entity_id": OCEAN}]}]}
    assert dmc.run_mapping_import(None, db, data) is None
    assert db.get_call_text_figures("Brand New") == []
    assert db.get_call_text_figures(T_SWING) == [SWING]


def test_ablauf_ohne_konflikte(qapp, db):
    import dialogs_mapping_conflict as dmc
    data = {"format": mio.FORMAT_NAME, "version": 2, "mappings": [
        {"call_text": "Brand New", "mapped_by": "auto",
         "figures": [{"entity_id": SWING}]},
        {"call_text": T_SWING, "mapped_by": "auto",
         "figures": [{"entity_id": SWING}]}]}
    res = dmc.run_mapping_import(None, db, data)
    assert res["new"] == 1 and res["identical"] == 1 and res["written"] == 1
    assert db.get_call_text_figures("Brand New") == [SWING]


def test_identische_verwaiste_zuordnung_wird_nicht_gemeldet(db):
    """Altbestand: lokale Zuordnung auf eine ID ohne calls-Zeile. Der Reimport
    der eigenen Datei ist identisch und darf nichts als unbekannt melden."""
    # Neu schreiben laesst die DB verwaiste IDs nicht mehr (Fremdschluessel);
    # der Altbestand stammt von frueher -> fuer den Test kurz abschalten.
    db._conn.execute("PRAGMA foreign_keys = OFF")
    db._conn.execute("INSERT OR REPLACE INTO call_text_mappings "
                     "(call_text, entity_id, mapped_by) VALUES (?, ?, 'auto')",
                     ("Circulate", "call_circulate"))
    db._conn.commit()
    db._conn.execute("PRAGMA foreign_keys = ON")
    diff = db.diff_call_text_figures(
        mio.parse_import(_roundtrip(mio.build_export(db))))
    assert "Circulate" in diff["identical"]
    assert diff["unknown_figures"] == [] and diff["skipped"] == []
    # Abweichend -> weiterhin gemeldet
    diff = db.diff_call_text_figures(
        {"Other": mio.ImportedMapping(["call_circulate"], "auto")})
    assert diff["unknown_figures"] == ["call_circulate"] and diff["skipped"] == ["Other"]


def test_nach_filtern_identisch_meldet_keine_unbekannte_figur(db):
    """Review #60: Import {X, verwaist} gegen lokal {X} wird nach dem Filtern
    identisch und nicht geschrieben -> auch nicht als unbekannt melden."""
    diff = db.diff_call_text_figures(
        {T_SWING: mio.ImportedMapping([SWING, "action_bogus"], "auto")})
    assert diff["identical"] == [T_SWING]
    assert diff["unknown_figures"] == [] and not diff["conflicts"]
    # Wird der Text geschrieben (Konflikt), bleibt die Meldung
    diff = db.diff_call_text_figures(
        {T_SWING: mio.ImportedMapping([OCEAN, "action_bogus"], "auto")})
    assert diff["conflicts"] and diff["unknown_figures"] == ["action_bogus"]


def test_c_mit_leerer_auswahl_schreibt_keine_figur(qapp, db, monkeypatch):
    """Review #60: C ohne Figur zeigt "keine Figur" und schreibt es auch als
    manual, statt die Zuordnung zu loeschen."""
    diff = db.diff_call_text_figures({T_SWING: mio.ImportedMapping([OCEAN], "auto")})
    dlg = _conflict_dialog(db, diff["conflicts"])
    monkeypatch.setattr(dlg, "_pick", lambda row: [])
    dlg._combos[0].setCurrentIndex(2)
    dlg._on_choice(0)
    assert dlg.choices()[0] == "C"
    assert dlg._result_figs(0) == []
    db.apply_call_text_figures_decisions(dlg.decisions())
    rows = [r for r in db.get_all_call_text_mappings() if r["call_text"] == T_SWING]
    assert rows == [{"call_text": T_SWING, "entity_id": None, "mapped_by": "manual"}]


@pytest.mark.parametrize("data, key", [
    ({"foo": 1}, "mapping_import_error_unknown_format"),
    ({"format": mio.FORMAT_NAME, "version": 99, "mappings": []},
     "mapping_import_error_newer_version"),
])
def test_formatfehler_tragen_uebersetzbaren_schluessel(data, key):
    from i18n import _t
    with pytest.raises(mio.CallMapFormatError) as exc:
        mio.parse_import(data)
    assert exc.value.key == key
    assert _t(exc.value.key, **exc.value.params) != key   # Schluessel existiert
