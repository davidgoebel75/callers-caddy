"""Beat-Tabelle call_timing (intern#164): Befuellen beim Start, je Version einmal."""
import json
from pathlib import Path

import pytest

from caddy.beats import calc

SRC_JSON = Path(__file__).resolve().parents[2] / "src" / "callerlab_timing.json"


@pytest.fixture
def db(tmp_path, keep):
    from song_db import SongDatabase

    return keep(SongDatabase(str(tmp_path / "t.db")))


def _meta(db):
    row = db._conn.execute(
        "SELECT value FROM app_meta WHERE key='callerlab_timing_version'").fetchone()
    return row[0] if row else None


def test_frische_db_hat_die_tabelle_aus_der_datei(db):
    data = json.loads(SRC_JSON.read_text(encoding="utf-8"))
    rows = db.get_call_timing_rows()
    assert len(rows) == len(data["rows"])
    assert _meta(db) == data["version"]
    assert [r["call"] for r in rows] == [r["call"] for r in data["rows"]]


def test_typen_in_der_db(db):
    tr = next(r for r in db.get_call_timing_rows() if r["call"].startswith("Transfer and"))
    assert isinstance(tr["beats"], int) and tr["anything_ab"] == 5
    assert {r["standard"] for r in db.get_call_timing_rows()} == {0, 1}
    assert any(r["beats"] is None for r in db.get_call_timing_rows())  # not_timed


def test_rechnung_aus_der_db_wie_aus_der_datei(db):
    data = json.loads(SRC_JSON.read_text(encoding="utf-8"))
    t_db, t_file = calc.BeatTable(db.get_call_timing_rows()), calc.BeatTable(data["rows"])
    for ents, text in ((["call_square_thru"], "Heads Square Thru 4"),
                       (["call_square_thru"], "Square Thru 3"),
                       (["call_arm_turns"], "Allemande Left 3/4")):
        assert calc.line_beats(t_db, ents, text) == calc.line_beats(t_file, ents, text)


def test_gleiche_version_spielt_nicht_erneut_ein(db):
    assert db.seed_call_timing() is False


def test_neue_version_ersetzt_die_tabelle(db, tmp_path):
    data = {"version": "neu", "rows": [
        {"programm": "MS", "call": "X", "entity_ids": "call_x", "typ": "fest",
         "beats": "4", "standard": "1"}]}
    p = tmp_path / "t.json"
    p.write_text(json.dumps(data), encoding="utf-8")
    assert db.seed_call_timing(str(p)) is True
    rows = db.get_call_timing_rows()
    assert len(rows) == 1 and rows[0]["beats"] == 4 and rows[0]["beats_bis"] is None
    assert _meta(db) == "neu"


def test_leere_tabelle_wird_trotz_marke_neu_befuellt(db):
    db._conn.execute("DELETE FROM call_timing")
    db._conn.commit()
    assert db.seed_call_timing() is True
    assert db.get_call_timing_rows()


def test_fehlende_datei_laesst_die_db_in_ruhe(db, tmp_path):
    n = len(db.get_call_timing_rows())
    assert db.seed_call_timing(str(tmp_path / "fehlt.json")) is False
    assert len(db.get_call_timing_rows()) == n
