"""Heads/Sides invertieren fuer Dynamic Lyrics (intern#127).

Die Regeln stammen aus der Analyse aller Lyrics und Sequenzen (siehe Issue);
die Faelle hier sind die dort gefundenen Schreibweisen und Fehltreffer.
"""
import pytest

import heads_sides as hs


@pytest.mark.parametrize("src, expected", [
    # Regel 1: immer tauschen, Schreibweise bleibt
    ("Heads Square Thru 4", "Sides Square Thru 4"),
    ("Sides Promenade 1/2, Heads Star Thru", "Heads Promenade 1/2, Sides Star Thru"),
    ("HDS SQUARE THRU 4", "SDS SQUARE THRU 4"),
    ("Hds Lead Right", "Sds Lead Right"),
    ("Head Ladies Chain 3/4 (Side Men Turn Them)",
     "Side Ladies Chain 3/4 (Head Men Turn Them)"),
    ("Head Position Promenade 1/2", "Side Position Promenade 1/2"),
    ("Heads/Sides Pass Thru", "Sides/Heads Pass Thru"),
    ("(original heads)", "(original sides)"),
    ("HEADS", "SIDES"),
    # Regel 2: nie tauschen
    ("Each Side Face Your Partner", "Each Side Face Your Partner"),
    ("(each side)", "(each side)"),
    ("Cross Head Tie", "Cross Head Tie"),
    ("left-side", "left-side"),
    ("It's a side's thing", "It's a side's thing"),
    ("R-H Star", "R-H Star"),
    ("SD-205", "SD-205"),
    ("HD 2", "HD 2"),
    # Regel 4: Einzelbuchstaben nur in Klammern
    ("(H) SqTh4", "(S) SqTh4"),
    ("H Star", "H Star"),
    # Regel 3: Couple-Nummern 1->2->3->4->1
    ("Couple #1 Face Right", "Couple #2 Face Right"),
    ("Couples 1 & 3 Right & Left Thru", "Couples 2 & 4 Right & Left Thru"),
    ("Couples # 1 & # 3", "Couples # 2 & # 4"),
    ("couple number 4", "couple number 1"),
    ("3&1 Lead Right", "4&2 Lead Right"),
    ("#1 Man & #3 Lady Jaywalk", "#2 Man & #4 Lady Jaywalk"),
    ("first couple split two", "first couple split two"),
    ("1st couple split two", "1st couple split two"),
    # Keine Couple-Nummern: Brueche und die Formation '3 & 1 Lines'
    ("Swing Thru 1 & 1/2", "Swing Thru 1 & 1/2"),
    ("All Acey Deucey (3 & 1 line) Boys Go 1 & 1/2",
     "All Acey Deucey (3 & 1 line) Boys Go 1 & 1/2"),
    ("All Flip The Diamond (from 3&1)", "All Flip The Diamond (from 3&1)"),
])
def test_invert_line(src, expected):
    assert hs.invert_line(src) == expected


@pytest.mark.parametrize("calls", [
    ["Couples 1 & 2 Lead Right", "Heads Pass Thru"],
    ["Couple #4 and #1 Face"],
    ["Couples 1, 2, 3 Circle Left"],
    ["Square Thru Your Couple Number"],
])
def test_asymmetrische_choreo_bleibt_unveraendert(calls):
    assert hs.is_asymmetric(calls)
    assert hs.invert_sequence(calls) == calls


def test_getrennte_nennungen_sind_nicht_benachbart():
    # Entscheidung David: nur innerhalb EINER Nennung zaehlt Nachbarschaft
    calls = ["Couple #1 Face Right", "Couple #2 Face Left"]
    assert not hs.is_asymmetric(calls)
    assert hs.invert_sequence(calls) == ["Couple #2 Face Right",
                                         "Couple #3 Face Left"]


def test_zweimal_invertieren_bei_heads_sides_ist_identitaet():
    calls = ["Heads Square Thru 4", "Sides Rollaway", "Head Ladies Chain"]
    assert hs.invert_sequence(hs.invert_sequence(calls)) == calls


@pytest.mark.parametrize("mode, figs", [
    ("HHSS", {3, 4}), ("HSSH", {2, 3}), ("HSHS", {2, 4}),
    ("hhss", {3, 4}), ("", set()), (None, set()), ("XYZ", set()),
])
def test_inverted_figures(mode, figs):
    assert hs.inverted_figures(mode) == figs


# ---------------------------------------------------------------------------
# Figuren-Zuordnung im Lyrics-Widget (ohne echtes Widget)
# ---------------------------------------------------------------------------

@pytest.fixture
def stub(qapp):
    from lyrics_widget import LyricsWidget

    class _Stub:
        _invert_active = LyricsWidget._invert_active
        _dyn_block_figure = LyricsWidget._dyn_block_figure
        _dyn_invert_flags = LyricsWidget._dyn_invert_flags
        _dynamic_current_part = LyricsWidget._dynamic_current_part

    s = _Stub()
    s._invert_enabled = True
    s._invert_mode = "HHSS"
    s._dyn_part_starts = [10.0, 40.0, 90.0, 120.0]   # Figure 1..4
    s._sync_last_pos = 0.0
    return s


def test_getrennte_bloecke_fest_zugeordnet(stub):
    stub._dyn_block_keys = [(1, 5), (8, 12), (15, 19), (22, 26)]
    stub._dyn_block_figs = [(1,), (2,), (3,), (4,)]
    assert stub._dyn_invert_flags() == (False, False, True, True)
    stub._invert_mode = "HSHS"
    assert stub._dyn_invert_flags() == (False, True, False, True)


def test_gemeinsamer_block_folgt_der_laufenden_figur(stub):
    stub._dyn_block_keys = [(1, 9)]
    stub._dyn_block_figs = [(1, 2, 3, 4)]
    expected = {0.0: False, 15.0: False, 50.0: False,   # Opener, Fig 1, Fig 2
                95.0: True, 130.0: True}                # Fig 3, Fig 4
    for pos, inv in expected.items():
        stub._sync_last_pos = pos
        assert stub._dyn_invert_flags() == (inv,), pos


def test_gemeinsamer_block_ohne_vier_teile_tauscht_nicht(stub):
    stub._dyn_block_keys = [(1, 9)]
    stub._dyn_block_figs = [(1, 2, 3, 4)]
    stub._dyn_part_starts = [10.0, 40.0]
    stub._sync_last_pos = 130.0
    assert stub._dyn_invert_flags() == (False,)


def test_aus_oder_ohne_art_tauscht_nicht(stub):
    stub._dyn_block_keys = [(1, 5)]
    stub._dyn_block_figs = [(3,)]
    stub._invert_enabled = False
    assert stub._dyn_invert_flags() == (False,)
    stub._invert_enabled, stub._invert_mode = True, ""
    assert stub._dyn_invert_flags() == (False,)


# ---------------------------------------------------------------------------
# Einstellungen
# ---------------------------------------------------------------------------

def test_art_bleibt_leer_und_wird_nicht_still_gespeichert(qapp, tmp_path):
    from PySide6.QtCore import QSettings
    from settings_dialog import SettingsDialog
    ini = QSettings(str(tmp_path / "t.ini"), QSettings.IniFormat)
    ini.setValue("lyrics/dynamic_invert_enabled", "false")
    ini.setValue("lyrics/dynamic_invert_mode", "")
    dlg = SettingsDialog(None, ini, focus_key="lyrics/dynamic_invert_mode")
    dlg._populate_groups_deferred()   # sonst erst per QTimer im Event-Loop
    row = next(r for r in dlg._rows if r.full_key == "lyrics/dynamic_invert_mode")
    assert row.widget.currentIndex() == -1
    assert not row.is_changed()
    assert dlg.focus_row("lyrics/dynamic_invert_mode")
    row.widget.setCurrentIndex(row.widget.findData("HSSH"))
    assert row.get_value() == "HSSH"
