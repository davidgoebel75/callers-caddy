"""Qt-eigene Texte in der App-Sprache (intern#217).

Standard-Buttons (Yes/No/Cancel), Datei-Dialoge und Kontextmenues der
Textfelder beschriftet Qt selbst. Ohne geladene qtbase-Uebersetzung bleiben
sie englisch, auch wenn der Rest per _t() deutsch oder japanisch ist.

Verwendung (nur im GUI-Thread, nach QApplication(...)):

    from qt_translation import install_qt_translation

    install_qt_translation(get_language())

Ein zweiter Aufruf ersetzt die vorige Uebersetzung (Sprachwahl im
Migrations-Tool). Fehlt die .qm-Datei, bleibt Qt englisch wie bisher.
"""

from __future__ import annotations

from PySide6.QtCore import QCoreApplication, QLibraryInfo, QTranslator

# Referenz halten: ein QTranslator ohne Python-Referenz raeumt der GC ab,
# und Qt uebersetzt still wieder englisch.
_translator: QTranslator | None = None


def install_qt_translation(lang: str) -> None:
    """Laedt qtbase_<lang> fuer die laufende QApplication."""
    global _translator
    app = QCoreApplication.instance()
    if _translator is not None:
        app.removeTranslator(_translator)
        _translator = None
    # Englisch ist Qts Grundsprache, dafuer gibt es nichts zu laden
    if lang == "en":
        return
    translator = QTranslator()
    path = QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)
    if translator.load(f"qtbase_{lang}", path):
        app.installTranslator(translator)
        _translator = translator
