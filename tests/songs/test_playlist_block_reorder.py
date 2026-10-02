"""Block-Umsortierung der Playlist (Mehrfachauswahl, intern#93).

Testet die reinen Reorder-Funktionen aus playlist_widget — ohne Qt/DB, weil die
kniffligen Faelle (nicht zusammenhaengende Auswahl, Randstau, Drop-Ziel) genau
hier stecken.
"""
from playlist_widget import apply_block_move, apply_block_move_to


# ---- apply_block_move: hoch/runter mit Randstau ---------------------------

def test_move_single_up():
    assert apply_block_move(["a", "b", "c", "d"], [2], -1) == ["a", "c", "b", "d"]


def test_move_single_down():
    assert apply_block_move(["a", "b", "c", "d"], [1], 1) == ["a", "c", "b", "d"]


def test_move_contiguous_block_up():
    # Block {b,c} eins hoch
    assert apply_block_move(["a", "b", "c", "d"], [1, 2], -1) == ["b", "c", "a", "d"]


def test_move_contiguous_block_down():
    assert apply_block_move(["a", "b", "c", "d"], [1, 2], 1) == ["a", "d", "b", "c"]


def test_block_at_top_stays_when_moving_up():
    # {a,b} ganz oben: kein Platz -> unveraendert
    assert apply_block_move(["a", "b", "c", "d"], [0, 1], -1) == ["a", "b", "c", "d"]


def test_block_at_bottom_stays_when_moving_down():
    assert apply_block_move(["a", "b", "c", "d"], [2, 3], 1) == ["a", "b", "c", "d"]


def test_noncontiguous_move_up():
    # 1,3,5 markiert -> jede eins hoch, relative Reihenfolge bleibt
    src = ["a", "b", "c", "d", "e", "f"]
    assert apply_block_move(src, [1, 3, 5], -1) == ["b", "a", "d", "c", "f", "e"]


def test_noncontiguous_move_down():
    src = ["a", "b", "c", "d", "e", "f"]
    assert apply_block_move(src, [0, 2, 4], 1) == ["b", "a", "d", "c", "f", "e"]


def test_partial_block_top_stays_rest_moves():
    # {0,1,3}: 0,1 blockiert am oberen Rand, 3 rueckt auf 2
    assert apply_block_move(["a", "b", "c", "d"], [0, 1, 3], -1) == ["a", "b", "d", "c"]


def test_move_leaves_original_untouched():
    src = ["a", "b", "c"]
    apply_block_move(src, [2], -1)
    assert src == ["a", "b", "c"]


def test_move_empty_selection_noop():
    assert apply_block_move(["a", "b"], [], -1) == ["a", "b"]


# ---- apply_block_move_to: Drag&Drop VOR die Zielzeile ---------------------

def test_drag_single_before_target():
    # "d" (Index 3) vor "b" (Index 1)
    assert apply_block_move_to(["a", "b", "c", "d"], [3], 1) == ["a", "d", "b", "c"]


def test_drag_block_downwards_before_target():
    # Block {a,b} vor "d" (Index 3)
    assert apply_block_move_to(["a", "b", "c", "d"], [0, 1], 3) == ["c", "a", "b", "d"]


def test_drag_noncontiguous_block_keeps_order():
    # {a,c} (0,2) vor "e" (4) -> in Playlist-Reihenfolge a,c einfuegen
    src = ["a", "b", "c", "d", "e"]
    assert apply_block_move_to(src, [0, 2], 4) == ["b", "d", "a", "c", "e"]


def test_drag_to_end_when_target_out_of_range():
    assert apply_block_move_to(["a", "b", "c"], [0], 99) == ["b", "c", "a"]


def test_drop_on_own_selection_is_noop():
    # Ziel liegt in der Auswahl -> keine Aenderung
    assert apply_block_move_to(["a", "b", "c", "d"], [1, 2], 2) == ["a", "b", "c", "d"]


def test_drag_leaves_original_untouched():
    src = ["a", "b", "c"]
    apply_block_move_to(src, [0], 2)
    assert src == ["a", "b", "c"]
