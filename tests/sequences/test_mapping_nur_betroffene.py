"""Nach einer Mapping-Aenderung nur die betroffenen Sequenzen neu rechnen (intern#278).

Die Schreibfunktionen der Mappings ziehen max_teaching_order und die Figuren je
Sequenz fuer ALLE Sequenzen mit einem geaenderten Call-Text nach. Geprueft wird
immer gegen den Vollaufbau: nachgezogen == alles neu gerechnet. Figuren werden
nur nachgezogen, wenn sie vor dem Schreiben zum Datenstand passten.

Figuren aus der gebuendelten Referenz (vgl. test_figure_set_filters):
  Allemande Right  call_allemande_right  30.0004
  Allemande Thar   call_allemande_thar   29.0053, 40.0026
  Motivate         call_motivate         60.0009
"""
import pytest

import song_db_sequences

RIGHT_T, THAR_T, MOT_T, FREMD_T = ("Allemande Right", "Allemande Thar", "Motivate",
                                   "Unbekannter Text 77")
RIGHT, THAR, MOTIVATE = "call_allemande_right", "call_allemande_thar", "call_motivate"


@pytest.fixture
def db(tmp_path, keep):
    from song_db import SongDatabase

    d = keep(SongDatabase(str(tmp_path / "t.db")))
    d.set_call_text_mappings([(RIGHT_T, RIGHT), (THAR_T, THAR)])
    d.s = {
        "right_fremd": d.insert_sequence([RIGHT_T, FREMD_T]),
        "right_thar": d.insert_sequence([RIGHT_T, THAR_T]),
        "thar": d.insert_sequence([THAR_T]),
        "thar_2": d.insert_sequence([THAR_T, RIGHT_T, THAR_T]),
        "mot": d.insert_sequence([MOT_T]),          # Motivate anfangs ungemappt
    }
    d.recompute_sequence_max_to()
    return d


def _max_to(db):
    return dict(db._conn.execute("SELECT id, max_teaching_order FROM sequences"))


def _figuren_bauen(db):
    db.invalidate_band_cache()
    assert not db.has_sequence_figures()             # gleicht auch die Version ab
    db._sequence_figures()
    assert db.has_sequence_figures()


def _gleich_vollaufbau(db):
    """Nachgezogener Stand == Vollaufbau (Figuren und max_teaching_order)."""
    figs = dict(db._seq_figures)
    assert figs == song_db_sequences._build_sequence_figures(db._conn)
    vorher = _max_to(db)
    db.recompute_sequence_max_to()
    assert _max_to(db) == vorher


SCHREIBWEGE = {
    "set_call_text_mapping": lambda d: d.set_call_text_mapping(THAR_T, MOTIVATE),
    "set_call_text_mappings": lambda d: d.set_call_text_mappings(
        [(THAR_T, MOTIVATE), (MOT_T, MOTIVATE)]),
    "set_call_text_figures": lambda d: d.set_call_text_figures(THAR_T, [RIGHT, MOTIVATE]),
    "set_call_text_figures_bulk": lambda d: d.set_call_text_figures_bulk(
        [(THAR_T, [MOTIVATE]), (RIGHT_T, [RIGHT, THAR])]),
    "delete_call_text_mapping": lambda d: d.delete_call_text_mapping(THAR_T),
    "backfill_auto_mappings": lambda d: d.backfill_auto_mappings(),
}


@pytest.mark.parametrize("weg", SCHREIBWEGE)
def test_nachgezogen_gleich_vollaufbau(db, weg, monkeypatch):
    _figuren_bauen(db)
    figs_vorher, max_to_vorher = dict(db._seq_figures), _max_to(db)
    monkeypatch.setattr(song_db_sequences, "_build_sequence_figures",
                        lambda conn: pytest.fail("Vollaufbau nach der Mapping-Aenderung"))
    SCHREIBWEGE[weg](db)
    assert db.has_sequence_figures()                 # gilt fuer den neuen Datenstand
    db._cover_ids(frozenset({10, 20, 30, 40, 50, 60}))   # Filter ohne Vollaufbau
    monkeypatch.undo()
    # Die Aenderung muss sichtbar etwas bewegt haben, sonst prueft der Test nichts
    assert dict(db._seq_figures) != figs_vorher or _max_to(db) != max_to_vorher
    _gleich_vollaufbau(db)


def test_alle_sequenzen_mit_dem_text_nicht_nur_eine(db):
    _figuren_bauen(db)
    db.set_call_text_mapping(THAR_T, MOTIVATE)
    figs, max_to = db._seq_figures, _max_to(db)
    for key in ("right_thar", "thar", "thar_2"):
        sid = db.s[key]
        assert MOTIVATE in figs[sid]
        assert max_to[sid] == pytest.approx(60.0009, abs=1e-3)
    # Unbeteiligte bleiben, wie sie waren
    assert figs[db.s["right_fremd"]] == frozenset({RIGHT})
    assert max_to[db.s["right_fremd"]] is None


def test_ohne_figuren_wird_nur_die_ebene_nachgezogen(db):
    db.invalidate_band_cache()                       # noch keine Figuren
    db.set_call_text_mapping(THAR_T, MOTIVATE)
    assert not db.has_sequence_figures()             # nichts erfunden
    vorher = _max_to(db)
    db.recompute_sequence_max_to()
    assert _max_to(db) == vorher                     # Ebene trotzdem richtig


def test_veraltete_figuren_werden_nicht_nachgezogen(db):
    _figuren_bauen(db)
    # Andere Aenderung ohne Nachziehen: die Figuren passen danach nicht mehr
    db._conn.execute("INSERT INTO sequence_calls (sequence_id, position, call_text) "
                     "VALUES (?, 9, ?)", (db.s["mot"], RIGHT_T))
    db._conn.commit()
    db.set_call_text_mapping(THAR_T, MOTIVATE)
    assert not db.has_sequence_figures()             # verworfen wie bisher


def test_fehlerhaftes_schreiben_aendert_nichts(db, monkeypatch):
    _figuren_bauen(db)
    figs, max_to = dict(db._seq_figures), _max_to(db)

    def kaputt(*_a, **_kw):
        raise RuntimeError("Absicht")
    monkeypatch.setattr(type(db), "_mapping_changed", kaputt)
    with pytest.raises(RuntimeError):
        db.set_call_text_figures(THAR_T, [MOTIVATE])
    monkeypatch.undo()
    assert db.get_call_text_figures(THAR_T) == [THAR]   # Rollback
    assert _max_to(db) == max_to
    assert dict(db._seq_figures) == figs


def test_refresh_after_mapping_ohne_globale_neuberechnung():
    from sequences_widget import SequencesWidget

    aufrufe = []

    class Db:
        def backfill_auto_mappings(self):
            aufrufe.append("backfill")

        def recompute_sequence_max_to(self, *a, **kw):
            pytest.fail("globales recompute_sequence_max_to nach dem Call-Mapping")

    class Fake:
        db = Db()

        def _populate_dropdowns(self):
            aufrufe.append("dropdowns")

        def load_sequences(self):
            aufrufe.append("load")

    SequencesWidget.refresh_after_mapping(Fake())
    assert aufrufe == ["backfill", "dropdowns", "load"]
