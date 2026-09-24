"""Vorrang der Leertaste (intern#101).

Die Leertaste ist die Safety-Taste fuer Play/Pause: laeuft Musik, muss sie
greifen, egal wo der Fokus liegt — ausser jemand tippt gerade in ein Textfeld.
Getestet wird die reine Entscheidung (space_should_fire) und die Erkennung
echter Eingabefelder (is_text_input), ohne das Hauptfenster hochzufahren.
"""
from PySide6.QtWidgets import (
    QComboBox, QLineEdit, QPlainTextEdit, QSpinBox, QTextBrowser, QTextEdit,
)

from shortcut_policy import is_text_input, space_should_fire

VERWAIST = 60.0  # letzter Tastendruck ins Feld liegt lange zurueck


def _entscheide(**abweichend):
    lage = dict(text_input_focused=False, playing=False, modal_open=False,
                typing_age_s=VERWAIST)
    lage.update(abweichend)
    return space_should_fire(**lage)


def test_ohne_textfeld_und_dialog_greift_die_leertaste():
    assert _entscheide() is True


def test_musik_steht_textfeld_behaelt_die_leertaste():
    assert _entscheide(text_input_focused=True) is False


def test_musik_laeuft_verwaistes_textfeld_verliert_die_leertaste():
    # Caller ist weg, jemand anderes drueckt Space: Musik muss stoppen.
    assert _entscheide(text_input_focused=True, playing=True) is True


def test_musik_laeuft_wer_gerade_tippt_behaelt_die_leertaste():
    # "Rocky Top": Leerzeichen mitten im Tippen landet im Feld, nicht im Player.
    assert _entscheide(text_input_focused=True, playing=True,
                       typing_age_s=1.0) is False


def test_nach_drei_sekunden_tipppause_greift_die_leertaste_wieder():
    assert _entscheide(text_input_focused=True, playing=True,
                       typing_age_s=3.0) is True


def test_musik_steht_offener_dialog_behaelt_die_leertaste():
    assert _entscheide(modal_open=True) is False


def test_musik_laeuft_leertaste_greift_auch_bei_offenem_dialog():
    # David, intern#101: Musik stoppen geht vor Dialog-Bedienung.
    assert _entscheide(modal_open=True, playing=True) is True


def test_suchfeld_ist_texteingabe(qapp):
    assert is_text_input(QLineEdit()) is True


def test_notizfeld_ist_texteingabe(qapp):
    assert is_text_input(QTextEdit()) is True
    assert is_text_input(QPlainTextEdit()) is True
    assert is_text_input(QSpinBox()) is True


def test_schreibgeschuetztes_lyrics_fenster_ist_keine_texteingabe(qapp):
    # Bug aus intern#101: QTextBrowser erbt von QTextEdit und sperrte alle Hotkeys.
    lyrics = QTextBrowser()
    lyrics.setReadOnly(True)
    assert is_text_input(lyrics) is False


def test_lyrics_im_bearbeiten_modus_ist_texteingabe(qapp):
    lyrics = QTextBrowser()
    lyrics.setReadOnly(False)
    assert is_text_input(lyrics) is True


def test_schreibgeschuetztes_eingabefeld_ist_keine_texteingabe(qapp):
    feld = QLineEdit()
    feld.setReadOnly(True)
    assert is_text_input(feld) is False


def test_auswahlliste_mit_tippfeld_ist_texteingabe(qapp):
    combo = QComboBox()
    combo.setEditable(True)
    assert is_text_input(combo) is True


def test_auswahlliste_ohne_tippfeld_ist_keine_texteingabe(qapp):
    assert is_text_input(QComboBox()) is False
