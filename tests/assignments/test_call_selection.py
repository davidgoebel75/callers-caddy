"""Call-Auswahl fuer To-Call-Widget und [to_call]-Shortcode (call_selection)."""
import pytest

from call_selection import build_shortcode_params, resolve_calls


class FakeDb:
    REAL = [(1, "Square Thru"), (2, "Swing Thru"), (3, " Scoot Back "),
            (4, "Hinge")]
    PROGRAMS = {"MS": [(1, "Square Thru"), (2, "Swing Thru"),
                       (3, " Scoot Back ")]}

    def get_real_calls(self):
        return list(self.REAL)

    def get_calls_for_program(self, program):
        return list(self.PROGRAMS.get(program, []))


DB = FakeDb()


@pytest.mark.parametrize("calls, erwartet", [
    ("Hinge, square thru", [(4, "Hinge"), (1, "Square Thru")]),  # Eingabefolge
    (["  SWING THRU ", "Unbekannt"], [(2, "Swing Thru")]),
    ("scoot back", [(3, " Scoot Back ")]),       # DB-Name mit Leerraum
    (" , ,Hinge,", [(4, "Hinge")]),
])
def test_explizite_liste(calls, erwartet):
    assert resolve_calls(DB, calls=calls) == erwartet


def test_explizite_liste_schlaegt_programm():
    assert resolve_calls(DB, program="MS", calls="Hinge",
                         except_names="Hinge") == [(4, "Hinge")]


@pytest.mark.parametrize("calls", ["", None, [], " , "])
def test_leere_liste_faellt_auf_programm_zurueck(calls):
    assert len(resolve_calls(DB, program="MS", calls=calls)) == 3


@pytest.mark.parametrize("ex, erwartet", [
    (None, [1, 2, 3]),
    ("swing thru", [1, 3]),
    (["Scoot Back", "Square Thru"], [2]),
    ("Gibt es nicht", [1, 2, 3]),
])
def test_programm_mit_ausnahmen(ex, erwartet):
    got = resolve_calls(DB, program="MS", except_names=ex)
    assert [eid for eid, _ in got] == erwartet


def test_ohne_programm_und_liste_leer():
    class Spy(FakeDb):
        def get_calls_for_program(self, program):
            raise AssertionError(f"ohne Programm abgefragt: {program!r}")
    assert resolve_calls(Spy()) == []
    assert resolve_calls(DB, program="Unbekannt") == []


ALL = ["A", "B", "C", "D"]


@pytest.mark.parametrize("label, sel, erwartet", [
    ("MS", ALL, {"program": "MS"}),
    ("MS", ["D", "C", "B", "A", "X"], {"program": "MS"}),   # Reihenfolge egal
    ("MS", ["A", "C", "D"], {"program": "MS", "except": "B"}),
    ("MS", ["D", "A"], {"program": "MS", "except": "B, C"}),  # genau Haelfte
    ("MS", ["C"], {"calls": "C"}),
    ("MS", [], {"calls": ""}),
    ("", ALL, {"calls": "A, B, C, D"}),                       # ohne Programm
    ("MS", ["D", "B", "X"], {"program": "MS", "except": "A, C"}),
])
def test_kuerzester_shortcode(label, sel, erwartet):
    assert build_shortcode_params(label, ALL, sel) == erwartet


@pytest.mark.parametrize("n_sel, erwartet", [
    (2, {"calls": "A, B"}),                       # 2 von 5: Minderheit
    (3, {"program": "MS", "except": "D, E"}),     # 3 von 5: Mehrheit
])
def test_kuerzester_shortcode_grenze_ungerade(n_sel, erwartet):
    five = ["A", "B", "C", "D", "E"]
    assert build_shortcode_params("MS", five, five[:n_sel]) == erwartet


def test_kuerzester_shortcode_leeres_programm():
    assert build_shortcode_params("MS", [], ["A"]) == {"calls": ""}


def test_shortcode_rundweg_ueber_resolve():
    """Was build_shortcode_params baut, loest resolve_calls zur Auswahl auf."""
    names = [n for _, n in DB.PROGRAMS["MS"]]
    for sel in (names, names[:2], names[:1]):
        p = build_shortcode_params("MS", names, sel)
        got = resolve_calls(DB, program=p.get("program", ""),
                            calls=p.get("calls"), except_names=p.get("except"))
        assert [n for _, n in got] == sel
