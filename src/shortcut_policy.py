"""Vorrang der Leertaste vor Textfeldern und Dialogen (intern#101).

Entscheidet, ob die Leertaste dem Player gehoert (Trigger key_space) oder beim
Fokus-Widget bleibt. Die uebrigen Hotkeys (Buchstaben, F-Tasten, Media-Tasten)
regelt weiterhin der eventFilter in main.py; von hier nutzen sie nur
is_text_input. Reine Logik ohne Hauptfenster — der eventFilter sammelt die
Lage ein und reicht sie durch.
"""
from PySide6.QtWidgets import (
    QAbstractSpinBox, QComboBox, QLineEdit, QPlainTextEdit, QTextEdit,
)

# Solange der letzte Tastendruck ins Textfeld juenger ist, gilt "tippt gerade".
# Bewusst fest verdrahtet; ein INI-Wert erst, wenn 3 s sich im Betrieb als
# falsch erweisen.
TYPING_GRACE_S = 3.0


def space_should_fire(*, text_input_focused, playing, modal_open, typing_age_s):
    """True, wenn die Leertaste dem Player gehoert statt dem Fokus-Widget.

    Gehaltene Taste: der eventFilter wendet dieselbe Entscheidung auf jede
    Wiederholung an, feuert aber nur beim ersten Druck.
    """
    if not playing:
        # Wie bisher: Textfeld und Dialog haben Vorrang.
        return not text_input_focused and not modal_open
    # Musik laeuft: Space gewinnt ueberall, nur nicht mitten im Tippen.
    return not text_input_focused or typing_age_s >= TYPING_GRACE_S


def is_text_input(widget):
    """True, wenn in das Widget gerade Text getippt werden kann."""
    if isinstance(widget, QComboBox):
        return widget.isEditable()
    if isinstance(widget, (QLineEdit, QAbstractSpinBox, QPlainTextEdit, QTextEdit)):
        # Schreibgeschuetzt (z.B. Lyrics-Fenster, ein QTextBrowser) zaehlt nicht.
        return not widget.isReadOnly()
    return False
