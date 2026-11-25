"""Einstellungsdialog: Sektionsliste links und Suche (intern#269)."""
from PySide6.QtCore import QSettings

from settings_dialog import SettingsDialog, matches_query


def test_treffer_logik():
    assert matches_query("", "egal")
    assert matches_query("laut", "Lautstärke des Zweitgeräts")
    assert matches_query("LOOP fade", "Fade beim Loop-Ende")
    assert not matches_query("loop fade", "Loop-Ende")


def _dialog(qapp, keep, tmp_path):
    settings = QSettings(str(tmp_path / "t.ini"), QSettings.IniFormat)
    dlg = keep(SettingsDialog(None, settings))
    dlg._populate_groups_deferred()   # sonst erst per QTimer im Event-Loop
    return dlg


def _visible_rows(dlg):
    return [r for g in dlg._groups for r in g.rows
            if not g.group.isHidden() and g.form.isRowVisible(r.label)]


def test_liste_links_hat_eine_zeile_pro_sektion(qapp, keep, tmp_path):
    dlg = _dialog(qapp, keep, tmp_path)
    assert dlg._nav.count() == len(dlg._groups) > 5
    assert dlg._nav.item(0).text() == dlg._groups[0].group.title()


def test_suche_nach_label_zeigt_nur_passende_zeilen(qapp, keep, tmp_path):
    dlg = _dialog(qapp, keep, tmp_path)
    total = len(_visible_rows(dlg))
    row = next(r for r in dlg._rows if r.full_key == "notes/first_note_factor")
    dlg._search.setText(row.label.text().rstrip(":"))
    shown = _visible_rows(dlg)
    assert row in shown and len(shown) < total
    # Sektionen ohne Treffer verschwinden auch links
    hidden = [i for i in range(dlg._nav.count()) if dlg._nav.item(i).isHidden()]
    assert hidden and all(dlg._groups[i].group.isHidden() for i in hidden)


def test_sektionstitel_zeigt_ganze_sektion(qapp, keep, tmp_path):
    dlg = _dialog(qapp, keep, tmp_path)
    audio = next(g for g in dlg._groups if g.section == "audio")
    dlg._search.setText(audio.group.title())
    assert all(audio.form.isRowVisible(r.label) for r in audio.rows)
    # Titel + Wort aus einer Zeile: nur diese Zeile, auch wenn ihr Label
    # den Sektionsnamen nicht enthaelt
    row = audio.rows[0]
    word = row.label.text().rstrip(":").split()[0]
    dlg._search.setText(f"{audio.group.title()} {word}")
    assert audio.form.isRowVisible(row.label)
    assert dlg._nav.currentRow() == dlg._groups.index(audio)


def test_labels_gleich_breit_und_feldgroessen_nach_typ(qapp, keep, tmp_path):
    from settings_dialog import _FIELD_WIDTHS
    dlg = _dialog(qapp, keep, tmp_path)
    assert len({r.label.width() for r in dlg._rows if r.label.minimumWidth()}) == 1
    for r in dlg._rows:
        if r._widget_type in _FIELD_WIDTHS:
            assert r.widget.maximumWidth() == _FIELD_WIDTHS[r._widget_type]


def test_klick_auf_letzten_eintrag_bleibt_markiert(qapp, keep, tmp_path):
    dlg = _dialog(qapp, keep, tmp_path)
    last = dlg._nav.count() - 1
    dlg._on_nav_clicked(dlg._nav.item(last))
    assert dlg._nav.currentRow() == last


def test_ohne_treffer_hinweis_und_leeren_stellt_alles_wieder_her(qapp, keep, tmp_path):
    dlg = _dialog(qapp, keep, tmp_path)
    total = len(_visible_rows(dlg))
    dlg._search.setText("xyzzy-gibt-es-nicht")
    assert _visible_rows(dlg) == []
    assert not dlg._no_hits.isHidden()
    dlg._search.clear()
    assert len(_visible_rows(dlg)) == total
    assert dlg._no_hits.isHidden()
