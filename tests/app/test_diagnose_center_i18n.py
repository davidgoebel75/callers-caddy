"""Diagnose-Center in allen Sprachen (intern#236).

Das Diagnose-Center war komplett fest auf Deutsch. Im Support schicken wir
Nutzer dorthin (Bundle senden) - englische und japanische Nutzer standen vor
einer rein deutschen Oberflaeche.

Geprueft wird die echte Oberflaeche: Dialog in de/en/ja aufbauen, die Tests
A, D, G und H wirklich laufen lassen und JEDEN sichtbaren Text einsammeln.
Die Inhalte der Log-Dateien bleiben bewusst deutsch (fuer den Entwickler).
"""
import ast
import json
import pathlib
import re
import zipfile

import pytest

import i18n
from i18n import _t

_SRC = pathlib.Path(__file__).resolve().parents[2] / "src"
_LANGS = ("de", "en", "ja")
# Typisch deutsche Woerter/Zeichen, die in en/ja nicht auftauchen duerfen
_DEUTSCH = re.compile(r"[äöüßÄÖÜ„]|\b(und|der|die|das|nicht|Datei|Ordner|"
                      r"Test starten|Abbrechen|Schließen|Sekunden|bitte)\b")


def _tr() -> dict:
    return json.loads((_SRC / "translations.json").read_text(encoding="utf-8"))


def _verwendete_schluessel() -> set:
    """Alle Schluessel, die diagnose_center.py per _t() oder als
    Klassenattribut (title/what_it_measures/...) benutzt."""
    baum = ast.parse((_SRC / "diagnose_center.py").read_text(encoding="utf-8"))
    keys = set()
    for node in ast.walk(baum):
        if (isinstance(node, ast.Call) and getattr(node.func, "id", None) == "_t"
                and node.args and isinstance(node.args[0], ast.Constant)):
            keys.add(node.args[0].value)
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant):
            for t in node.targets:
                if (isinstance(t, ast.Name) and t.id in (
                        "title", "what_it_measures", "what_you_do",
                        "expected_duration", "expected_result_hint")
                        and node.value.value not in ("", "—")):
                    keys.add(node.value.value)
    return keys


def test_alle_schluessel_vollstaendig_und_platzhalter_gleich():
    tr = _tr()
    keys = _verwendete_schluessel() | {"menu_diagnose_center", "diag_open_error"}
    assert len(keys) > 60
    fehler = []
    for k in sorted(keys):
        entry = tr.get(k)
        if not entry or not all(entry.get(l) for l in _LANGS):
            fehler.append(f"{k}: fehlt/unvollstaendig")
            continue
        ph = {l: set(re.findall(r"\{(\w+)\}", entry[l])) for l in _LANGS}
        if not (ph["de"] == ph["en"] == ph["ja"]):
            fehler.append(f"{k}: Platzhalter ungleich {ph}")
        for l in ("en", "ja"):
            if _DEUTSCH.search(entry[l]):
                fehler.append(f"{k}/{l}: deutsch? {entry[l][:60]!r}")
    assert not fehler, "\n".join(fehler)


_J = r"[぀-ヿ一-鿿]"


def test_japanisch_hausregeln():
    """Schreibweisen wie im Rest der App (erhoben aus translations.json):
    Leerzeichen zwischen lateinischen Woertern und Japanisch, フォルダ statt
    フォルダー, vollbreite Klammern, 音飛び fuer Aussetzer, keine Halbbreit-
    Katakana, kein Gedankenstrich mitten im Satz, Satzende wie im Deutschen."""
    tr = _tr()
    fehler = []
    for k in sorted(_verwendete_schluessel() | {"menu_diagnose_center", "diag_open_error"}):
        de, ja = tr[k]["de"], re.sub(r"<[^>]+>", "", tr[k]["ja"])
        if re.search(rf"[A-Za-z]{_J}|{_J}[A-Za-z]", ja):
            fehler.append(f"{k}: Leerzeichen Latein/Japanisch fehlt: {ja}")
        if re.search(rf"{_J}\(|\){_J}|^\(", ja):
            fehler.append(f"{k}: schmale Klammer: {ja}")
        for falsch in ("フォルダー", "音切れ"):
            if falsch in ja:
                fehler.append(f"{k}: {falsch}: {ja}")
        if re.search(r"[｡-ﾟ]", ja):
            fehler.append(f"{k}: Halbbreit-Katakana: {ja}")
        if re.search(rf"{_J} ?— ?{_J}", ja):
            fehler.append(f"{k}: Gedankenstrich im Satz: {ja}")
        if de.rstrip().endswith(".") and not ja.rstrip().endswith(("。", "！")):
            fehler.append(f"{k}: Satzende fehlt: {ja}")
        if ja.count("「") != ja.count("」") or ja.count("（") != ja.count("）"):
            fehler.append(f"{k}: Klammern unpaarig: {ja}")
    assert not fehler, "\n".join(fehler)


def test_keine_festen_texte_mehr_in_der_oberflaeche():
    """Keine deutschen String-Literale mehr an Qt-Widgets / finish / set_status."""
    src = (_SRC / "diagnose_center.py").read_text(encoding="utf-8")
    verdaechtig = re.findall(
        r'(?:QLabel|QPushButton|setText|setWindowTitle|addTab|set_status|finish|'
        r'emit)\(\s*(?:[\w_]+,\s*)?f?["\'][^"\']*[A-Za-zÄÖÜäöü]{3}', src)
    # Nur HTML um einen schon uebersetzten Text
    verdaechtig = [v for v in verdaechtig if v != 'QLabel(f"<b>{header']
    assert not verdaechtig, verdaechtig


@pytest.fixture
def sprache():
    alt = i18n.get_language()
    yield i18n.set_language
    i18n.set_language(alt)


def _texte(widget):
    """Alle sichtbaren Texte des Dialogs (inkl. Reiter)."""
    from PySide6.QtWidgets import QLabel, QPushButton, QTabWidget
    out = [widget.windowTitle()]
    for w in widget.findChildren(QLabel):
        out.append(w.text())
    for w in widget.findChildren(QPushButton):
        out.append(w.text())
    for tw in widget.findChildren(QTabWidget):
        out.extend(tw.tabText(i) for i in range(tw.count()))
    return [t for t in out if t]


def _pruefe_texte(texte, lang):
    fehler = []
    for t in texte:
        roh = re.sub(r"<[^>]+>", "", t)
        if re.search(r"\bdiag_\w+|menu_diagnose", roh):
            fehler.append(f"roher Schluessel: {roh!r}")
        if re.search(r"\{\w+\}", roh):
            fehler.append(f"Platzhalter uebrig: {roh!r}")
        # Pfade/Dateinamen ausnehmen (logs/diagnose/..., *.txt, *.zip)
        ohne_pfade = re.sub(r"\S*[/\\]\S*|\S+\.(txt|zip)", "", roh)
        if lang != "de" and _DEUTSCH.search(ohne_pfade):
            fehler.append(f"deutsch in {lang}: {roh[:80]!r}")
    assert not fehler, "\n".join(fehler[:15])


@pytest.mark.parametrize("lang", _LANGS)
def test_dialog_und_testlaeufe_in_jeder_sprache(qapp, keep, tmp_path, sprache, lang):
    sprache(lang)
    from diagnose_center import (DiagnoseCenterDialog, SystemSnapshotTest,
                                 QTimerInventoryTest, StallSentinelStatus,
                                 BundleTest)
    (tmp_path / "logs" / "perf").mkdir(parents=True)
    (tmp_path / "logs" / "perf" / "p1.txt").write_text("x", encoding="utf-8")
    (tmp_path / "callers_caddy.ini").write_text("[a]\nb=1\n", encoding="utf-8")

    dlg = keep(DiagnoseCenterDialog(str(tmp_path)))
    texte = _texte(dlg)
    assert dlg.windowTitle() == _t("diag_window_title")

    def tests(cls):
        return [w for w in dlg.findChildren(cls)]

    # Echte Laeufe: Ergebnis-/Statustexte sind erst danach sichtbar
    for cls in (SystemSnapshotTest, QTimerInventoryTest, StallSentinelStatus,
                BundleTest):
        (w,) = tests(cls)
        w._on_start_clicked()
        assert w._result_frame.isVisibleTo(w), cls.__name__
        texte += [w._status_lbl.text(), w._result_summary.text(),
                  w._result_path_lbl.text()]
    # Abbrechen-Status
    (a,) = tests(SystemSnapshotTest)
    a._running = True
    a._on_cancel_clicked()
    texte.append(a._status_lbl.text())

    _pruefe_texte(texte, lang)
    # Das Bundle ist wirklich entstanden
    (h,) = tests(BundleTest)
    assert zipfile.is_zipfile(h._last_result_path)


def test_menue_und_fehlermeldung_uebersetzt():
    src = (_SRC / "main.py").read_text(encoding="utf-8")
    assert 'addAction("Diagnose-Center' not in src
    assert "Konnte Diagnose-Center nicht" not in src
    assert '_t("menu_diagnose_center")' in src
