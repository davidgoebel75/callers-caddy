"""Pilot Square als einzige Ablage fuer Farbe + Name je Taenzer (intern#249)."""
from pilot_square_widget import PilotSquareWidget


def test_daten_signal_und_bearbeiten(keep, monkeypatch):
    import pilot_dancer_dialog as pdd
    w = keep(PilotSquareWidget())
    got = []
    w.dancers_changed.connect(got.append)
    w._select_box(w._couples[2].woman)
    w._apply_color_to_selected("#e74c3c")
    assert got[-1] == {(2, False): {"color": "#e74c3c", "name": ""}}
    w._couples[1].man.setPlainText("Tom")
    assert got[-1][(1, True)] == {"color": None, "name": "Tom"}

    class _Fake:
        Accepted = 1

        def __init__(self, title, name, color, palette, colors, parent):
            assert name == "Tom" and color is None and None in palette

        def exec(self):
            return 1

        def result_name(self):
            return "Thomas"

        def result_color(self):
            return "#3498db"

    monkeypatch.setattr(pdd, "PilotDancerDialog", _Fake)
    assert w.edit_dancer(1, True) is True
    assert w.dancer_data()[(1, True)] == {"color": "#3498db", "name": "Thomas"}
    assert got[-1] == w.dancer_data()
