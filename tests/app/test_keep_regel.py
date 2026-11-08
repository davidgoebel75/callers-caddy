"""Test-DBs und Widgets gehen durch die Fixture `keep` (CODING_STANDARDS, Tests).

Was liegen bleibt, sammelt ein spaeterer gc.collect() an zufaelliger Stelle
ein, und die volle Suite stuerzt nur auf manchen Rechnern ab (PR #119).
Mechanisch pruefbar sind zwei Muster in tests/:

1. `SongDatabase(...)` nur direkt in `keep(...)`.
2. Kein `.deleteLater()`: es loescht erst im naechsten Event-Loop-Durchlauf,
   also irgendwo in einem spaeteren Test.

Ratsche wie in test_architecture.py: die heutigen Stellen stehen in
_KNOWN_LEAKS. Wer eine Stelle behebt, senkt ihren Zaehler, sonst faellt der
Test. Die Liste soll schrumpfen, nicht wachsen.
"""
import ast
from collections import Counter
from pathlib import Path

_TESTS = Path(__file__).resolve().parents[1]

# Vorgefunden bei Einfuehrung der Pruefung. Neue Tests brauchen keinen Eintrag.
_KNOWN_LEAKS = {
    "assignments/test_band_filter_cover.py": 1,
    "assignments/test_call_figures_picker.py": 3,
    "assignments/test_call_mapping_optimize.py": 4,
    "assignments/test_call_mapping_set_suggestions.py": 3,
    "assignments/test_call_text_figures.py": 3,
    "assignments/test_callmap_import.py": 2,
    "assignments/test_figure_set_filters.py": 1,
    "db/test_db_accessors.py": 1,
    "db/test_play_stats.py": 1,
    "db/test_potential_queries.py": 2,
    "db/test_schema.py": 1,
    "lyrics/test_lyrics_timing.py": 1,
    "lyrics/test_lyrics_zoom_after_load.py": 1,
    "lyrics/test_lyrics_zoom_settings.py": 1,
    "lyrics/test_reading_band.py": 1,
    "lyrics/test_sync_point_lines.py": 1,
    "playback/test_loop_widget_button_grid.py": 1,
    "playback/test_potential_bulk_autoloop_preset.py": 1,
    "playback/test_transport_icon_disabled.py": 1,
    "sequences/test_hidden_sequences.py": 2,
    "sequences/test_seq_invariants_bands.py": 2,
    "sequences/test_sequence_editor_figures.py": 2,
    "sequences/test_sequence_view_context_menu.py": 1,
    "sequences/test_to_call_scroll.py": 1,
    "settings/test_app_ini_settings.py": 1,
    "settings/test_float_geom_migration.py": 1,
    "songs/test_metadata_match.py": 1,
    "songs/test_song_types.py": 1,
    "songs/test_subfolder_duplicate_repair.py": 1,
    "songs/test_zip_reimport_linked.py": 1,
}


def _leaks(root):
    """Counter {Pfad relativ zu root: Anzahl} aller Stellen ohne keep."""
    found = Counter()
    for path in sorted(root.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), str(path))
        kept = {id(arg) for node in ast.walk(tree)
                if isinstance(node, ast.Call)
                and getattr(node.func, "id", None) == "keep"
                for arg in node.args}
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            name = getattr(func, "id", None) or getattr(func, "attr", None)
            if ((name == "SongDatabase" and id(node) not in kept)
                    or (name == "deleteLater" and isinstance(func, ast.Attribute))):
                found[path.relative_to(root).as_posix()] += 1
    return found


def test_tests_raeumen_ueber_keep_ab():
    found = dict(_leaks(_TESTS))
    diff = {k: (_KNOWN_LEAKS.get(k, 0), found.get(k, 0))
            for k in found.keys() | _KNOWN_LEAKS.keys()
            if found.get(k) != _KNOWN_LEAKS.get(k)}
    assert not diff, (
        f"Stellen ohne keep (Datei: (erwartet, gefunden)): {diff}. "
        f"Neue Test-DBs und Widgets: `x = keep(...)` statt close()/deleteLater(); "
        f"behobene Stellen aus _KNOWN_LEAKS streichen.")


def test_pruefung_erkennt_beide_muster(tmp_path):
    (tmp_path / "test_x.py").write_text(
        "def test_a(keep):\n"
        "    ok = keep(SongDatabase(':memory:'))\n"
        "    db = SongDatabase(':memory:')\n"
        "    box.deleteLater()\n",
        encoding="utf-8")
    assert _leaks(tmp_path) == {"test_x.py": 2}
