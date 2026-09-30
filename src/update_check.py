"""
Update-Pruefung fuer Callers Caddy.
====================================
Prueft beim Programmstart, ob im Download-Bereich eine neuere Version als die
installierte vorliegt, und bietet bei Bedarf den Direkt-Download der Update-ZIP an.

Ablauf / Design
---------------
- Der Redirect `callerscaddy.de/download-area` zeigt auf einen oeffentlichen
  Google-Drive-Ordner. Der Redirect bleibt die EINZIGE fest verdrahtete Adresse —
  dahinter kann jederzeit ein anderer Ordner gehaengt werden.
- Struktur im Ordner: pro Version ein Unterordner ("0.129", "0.130", ...), darin
  drei ZIPs. NUR `Callers_Caddy_Update_<version>.zip` (schlankes Update, ohne
  DB/INI/User-Daten) darf geladen werden — NICHT die Vollinstallation
  (`Callers_Caddy_<version>.zip`) und NICHT die Code-ZIP.
- Erkennung haengt bewusst an der Update-ZIP-DATEI, nicht am Ordnernamen: ein
  leerer/halbfertiger Versionsordner (noch keine Update-ZIP hochgeladen) loest
  KEINEN Fehlalarm aus.

Zweistufig (spart Requests im Normalfall):
    Stufe 1 (1 HTTP-Request): Elternordner-HTML laden → Versionsordner-Namen
       auslesen. Ist KEINE Ordnernummer hoeher als die installierte, ist sofort
       Schluss — der haeufige Fall bei jedem Start (nur 1 Request).
    Stufe 2 (nur wenn eine hoehere Nummer existiert): erst dann in die hoeheren
       Ordner schauen (hoechster zuerst) und die tatsaechlich vorhandene
       Update-ZIP + deren Datei-ID ermitteln. Fehlt sie (leerer/halbfertiger
       Ordner), wird die naechsttiefere noch-hoehere Version geprueft.

Der Download nutzt die `confirm=t`-Direkt-URL von Drive: Damit wird die
Virenscan-Zwischenseite (>100 MB) uebersprungen und die Datei laedt direkt.

Robustheit: Die Erkennung haengt an Googles HTML-Markup. Aendert Google das,
findet der Parser nichts und die App meldet einfach nichts (kein Crash, kein
Nerv-Popup). Jeder Fehler (offline, Timeout, Markup-Aenderung) → stiller Abbruch.
"""

from __future__ import annotations

import re
import threading
import urllib.request
from datetime import date, timedelta

from PySide6.QtCore import QObject, Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QCheckBox, QMessageBox

from i18n import _t

# Stabile Adresse — Redirect auf den jeweils aktuellen Download-Ordner.
UPDATE_URL = "https://callerscaddy.de/download-area"
_FOLDER_URL = "https://drive.google.com/drive/folders/{folder_id}"
# `confirm=t` ueberspringt die Virenscan-Warnseite bei grossen Dateien (>100 MB).
_DOWNLOAD_URL = (
    "https://drive.usercontent.google.com/download"
    "?id={file_id}&export=download&confirm=t"
)

_TIMEOUT = 12
_USER_AGENT = "Mozilla/5.0 (Callers Caddy Update Check)"

# Snooze: Erinnerung fuer diese Anzahl Tage ruhen lassen (Checkbox im Dialog).
_SNOOZE_DAYS = 7
# INI-Schluessel (in der callers_caddy.ini des Hauptfensters).
_SNOOZE_UNTIL_KEY = "update/snooze_until"      # ISO-Datum, bis wann still
_SNOOZE_VERSION_KEY = "update/snooze_version"  # verschobene Version

# Drive-Objekt-IDs stehen als data-id="..." an den DOM-Elementen.
_DATA_ID_RE = re.compile(r'data-id="([a-zA-Z0-9_-]{20,})"')
# Versionsordner: aria-label="0.130 Shared folder". Die zugehoerige data-id
# steht zuverlaessig davor (naechste data-id vor dem Label).
_FOLDER_LABEL_RE = re.compile(r'aria-label="(\d+\.\d+) Shared folder"')
# Nur die schlanke Update-ZIP ist ein gueltiges Download-Ziel.
_UPDATE_FILE_RE = re.compile(r"Callers_Caddy_Update_(\d+\.\d+)\.zip")


def _parse_version(text):
    """'0.130' -> (0, 130). Gibt None zurueck, wenn kein Versions-String."""
    if not text:
        return None
    try:
        return tuple(int(part) for part in text.strip().split("."))
    except (ValueError, AttributeError):
        return None


def _fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
        return resp.read().decode("utf-8", "replace")


def _nearest_id_before(ids, pos):
    """Naechste (positionsmaessig davor liegende) data-id vor pos, oder None.

    `ids`: Liste (position, id). Drive rendert die data-id eines Elements
    kurz vor dessen Beschriftung — die naechste data-id davor gehoert dazu.
    """
    best = None
    for p, idv in ids:
        if p < pos and (best is None or p > best[0]):
            best = (p, idv)
    return best[1] if best else None


def _list_version_folders(parent_html):
    """[(version_tuple, version_str, folder_id)] der Versionsordner, hoechste zuerst."""
    ids = [(m.start(), m.group(1)) for m in _DATA_ID_RE.finditer(parent_html)]
    out = []
    for m in _FOLDER_LABEL_RE.finditer(parent_html):
        vt = _parse_version(m.group(1))
        fid = _nearest_id_before(ids, m.start())
        if vt and fid:
            out.append((vt, m.group(1), fid))
    out.sort(reverse=True)  # hoechste Version zuerst
    return out


def _find_update_zip(folder_html):
    """(version_str, file_id) der Update-ZIP im Ordner, oder None wenn keine da."""
    m = _UPDATE_FILE_RE.search(folder_html)
    if not m:
        return None
    ids = [(mm.start(), mm.group(1)) for mm in _DATA_ID_RE.finditer(folder_html)]
    fid = _nearest_id_before(ids, m.start())
    if not fid:
        return None
    return m.group(1), fid


def find_latest_update(current_version):
    """Ermittelt zweistufig, ob ein hoeheres Update mit echter Update-ZIP vorliegt.

    Stufe 1: Nur der Elternordner wird geladen. Gibt es keinen Versionsordner
    mit hoeherer Nummer als `current_version`, endet die Pruefung mit 1 Request.
    Stufe 2: Nur die hoeheren Ordner (hoechster zuerst) werden inhaltlich
    geprueft, bis eine echte Update-ZIP gefunden wird.

    Returns:
        (version_str, download_url) oder None (kein hoeheres Update / Fehler).
    """
    current = _parse_version(current_version)
    if not current:
        return None
    folders = _list_version_folders(_fetch(UPDATE_URL))
    # Stufe 1: nur Ordner mit hoeherer Nummer sind ueberhaupt interessant.
    candidates = [f for f in folders if f[0] > current]
    if not candidates:
        return None  # keine hoehere Ordnernummer -> fertig (nur 1 Request)
    # Stufe 2: jetzt erst in die hoeheren Ordner schauen (bereits absteigend sortiert).
    for _vt, _vstr, folder_id in candidates:
        found = _find_update_zip(_fetch(_FOLDER_URL.format(folder_id=folder_id)))
        if found:
            file_version, file_id = found
            return file_version, _DOWNLOAD_URL.format(file_id=file_id)
    return None


class UpdateChecker(QObject):
    """Orchestriert Pruefung + Dialog. An das Hauptfenster haengen, damit der
    QObject im Main-Thread lebt (Dialog laeuft dann sicher im Main-Thread)."""

    # Ergebnis der Hintergrund-Pruefung (version, download_url, ok). ok=False
    # NUR bei echtem Fehler (offline/Timeout/Markup) -- damit die manuelle
    # Pruefung "aktuell" von "nicht erreichbar" unterscheiden kann.
    # ("", "", True) = aktuell.
    _check_done = Signal(str, str, bool)

    def __init__(self, window, current_version):
        # parent=window -> Thread-Affinitaet Main-Thread; haelt uns zudem am Leben
        super().__init__(window)
        self._window = window
        self._current_version = current_version
        # QSettings des Hauptfensters (callers_caddy.ini) fuer die Snooze-Persistenz.
        self._settings = getattr(window, "_settings", None)
        self._running = False
        self._manual = False
        # Queued: emittiert wird im Hintergrund-Thread, der Slot laeuft im
        # Main-Thread.
        self._check_done.connect(self._on_result, Qt.QueuedConnection)

    def start(self):
        """Automatische Pruefung beim Start — still, wenn kein Update vorliegt,
        respektiert die Snooze-Ruhephase."""
        self._begin(manual=False)

    def check_now(self):
        """Manuelle Pruefung aus dem Menue — gibt IMMER Rueckmeldung (Update /
        aktuell / nicht erreichbar) und ignoriert die Snooze-Ruhephase."""
        self._begin(manual=True)

    def _begin(self, manual):
        if self._running:
            # laeuft bereits -> kein zweiter Thread. Ein manueller Klick
            # waehrend der Start-Pruefung bekommt trotzdem Rueckmeldung,
            # sobald das Ergebnis da ist.
            if manual:
                self._manual = True
            return
        self._running = True
        self._manual = manual
        # intern#134: Daemon-Thread statt QThread. Ein QThread, der beim
        # Beenden noch im Netz-Timeout haengt, wird mit dem Hauptfenster
        # zerstoert -> Qt Fatal "QThread: Destroyed while thread is still
        # running". Ein Daemon-Thread endet einfach mit dem Prozess.
        threading.Thread(target=self._run_check, daemon=True,
                         name="UpdateCheck").start()

    def _run_check(self):
        """Netzwerk-Abfrage im Daemon-Thread (Main-Thread bleibt frei)."""
        try:
            result = find_latest_update(self._current_version)
        except Exception:
            version, url, ok = "", "", False
        else:
            version, url = result if result else ("", "")
            ok = True
        try:
            self._check_done.emit(version, url, ok)
        except RuntimeError:
            pass  # App wird gerade beendet, der Checker ist schon zerstoert

    def _is_snoozed(self, latest_version):
        """True, wenn die Erinnerung fuer `latest_version` noch ruht.

        Ruht nur, solange das gespeicherte Snooze-Datum in der Zukunft liegt
        UND keine NOCH neuere Version als die verschobene erschienen ist —
        eine echte neue Version soll trotz Snooze gemeldet werden.
        """
        if not self._settings:
            return False
        until_raw = self._settings.value(_SNOOZE_UNTIL_KEY, "")
        if not until_raw:
            return False
        try:
            until = date.fromisoformat(str(until_raw))
        except ValueError:
            return False
        if date.today() >= until:
            return False  # Snooze abgelaufen
        snoozed = _parse_version(str(self._settings.value(_SNOOZE_VERSION_KEY, "")))
        newest = _parse_version(latest_version)
        if newest and snoozed and newest > snoozed:
            return False  # neuere Version als verschoben -> trotzdem melden
        return True

    def _set_snooze(self, latest_version):
        """Erinnerung fuer `_SNOOZE_DAYS` Tage ruhen lassen."""
        if not self._settings:
            return
        until = date.today() + timedelta(days=_SNOOZE_DAYS)
        self._settings.setValue(_SNOOZE_UNTIL_KEY, until.isoformat())
        self._settings.setValue(_SNOOZE_VERSION_KEY, latest_version)
        self._settings.sync()

    def _on_result(self, latest_version, download_url, ok):
        # Laeuft im Main-Thread.
        manual = self._manual
        self._running = False  # Pruefung beendet, neue wieder erlaubt
        if latest_version and download_url:
            current = _parse_version(self._current_version)
            newest = _parse_version(latest_version)
            if current and newest and newest > current:
                # Snooze gilt nur fuer die automatische Pruefung, nie manuell.
                if manual or not self._is_snoozed(latest_version):
                    self._show_update_dialog(latest_version, download_url)
                return
        # Kein hoeheres Update: nur die manuelle Pruefung meldet sich ueberhaupt.
        if manual:
            if ok:
                self._show_up_to_date()
            else:
                self._show_check_failed()

    def _show_up_to_date(self):
        QMessageBox.information(
            self._window,
            _t("update_none_title"),
            _t("update_none_text", current=self._current_version),
        )

    def _show_check_failed(self):
        QMessageBox.warning(
            self._window,
            _t("update_error_title"),
            _t("update_error_text"),
        )

    def _show_update_dialog(self, latest_version, download_url):
        box = QMessageBox(self._window)
        box.setIcon(QMessageBox.Information)
        box.setWindowTitle(_t("update_available_title"))
        box.setText(_t("update_available_text", version=latest_version,
                       current=self._current_version))
        snooze_cb = QCheckBox(_t("update_snooze_checkbox"))
        box.setCheckBox(snooze_cb)
        download_btn = box.addButton(
            _t("update_download_now"), QMessageBox.AcceptRole)
        box.addButton(_t("update_later"), QMessageBox.RejectRole)
        box.setDefaultButton(download_btn)
        box.exec()
        if snooze_cb.isChecked():
            self._set_snooze(latest_version)
        if box.clickedButton() is download_btn:
            QDesktopServices.openUrl(QUrl(download_url))
