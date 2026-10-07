"""
Crash Handler fuer Callers Caddy.

Faengt unbehandelte Python-Exceptions ab und schreibt ein Logfile.
Registriert ausserdem Qts eigenen Message-Handler fuer qWarning/qCritical/qFatal.
Enthaelt einen Ring-Buffer fuer die letzten Benutzeraktionen,
damit man nach einem Absturz sieht, was kurz vorher passiert ist.

Verwendung:
    import crash_handler
    crash_handler.setup(app_dir)          # einmalig beim Start
    crash_handler.log_action("Song geladen: Titel")  # an kritischen Stellen
"""

import sys
import os
import glob
import traceback
from collections import deque
from datetime import datetime

_logger = None  # Singleton

# INI-Key: Dateiname des zuletzt beim Start gemeldeten Crash-Logs
LAST_NOTIFIED_KEY = "crash/last_notified"
# INI-Key: Problemliste, zu der report_once zuletzt ein Log geschrieben hat
REPORTED_PROBLEMS_KEY = "crash/db_update_reported"


class CrashLogger:
    RING_SIZE = 25

    def __init__(self, app_dir: str):
        self._app_dir = app_dir
        self._ring: deque = deque(maxlen=self.RING_SIZE)
        self._context_provider = None  # callable() -> dict{"song": str, "location": str}

    def set_context_provider(self, fn):
        """Registriert eine Funktion, die beim Crash Kontext-Infos liefert."""
        self._context_provider = fn

    def log_action(self, action: str):
        """Traegt eine Benutzeraktion in den Ring-Buffer ein."""
        ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        self._ring.append(f"{ts}  {action}")

    # ---- Installation ----

    def install(self):
        """Ueberschreibt sys.excepthook fuer unbehandelte Python-Exceptions."""
        sys.excepthook = self._on_unhandled_exception

    def install_qt_handler(self):
        """Registriert Qts Message-Handler fuer qWarning, qCritical, qFatal.

        Muss nach QApplication() aufgerufen werden.
        QtWarningMsg  -> Ring-Buffer-Eintrag
        QtCriticalMsg -> Ring-Buffer + sofortiges Log auf Disk
        QtFatalMsg    -> Ring-Buffer + sofortiges Log auf Disk
                         (Prozess stirbt danach — kein Python-Handler bekommt das mehr)
        QtDebugMsg / QtInfoMsg werden ignoriert (zu laut).
        """
        try:
            from PySide6.QtCore import qInstallMessageHandler, QtMsgType
        except ImportError:
            return

        def _qt_message_handler(mode, context, message):
            if mode == QtMsgType.QtWarningMsg:
                self.log_action(f"[Qt Warning] {message}")
            elif mode == QtMsgType.QtCriticalMsg:
                self.log_action(f"[Qt Critical] {message}")
                self._write_log(reason=f"Qt Critical: {message}")
            elif mode == QtMsgType.QtFatalMsg:
                self.log_action(f"[Qt Fatal] {message}")
                self._write_log(reason=f"Qt Fatal: {message}")

        qInstallMessageHandler(_qt_message_handler)

    # ---- Interne Log-Helfer ----

    def _collect_header(self, reason: str) -> list:
        """Erstellt den gemeinsamen Log-Kopf (Kontext + Ring-Buffer)."""
        ctx = {}
        if self._context_provider:
            try:
                ctx = self._context_provider()
            except Exception:
                pass

        lines = [
            "=== Callers Caddy — Crash Report ===",
            f"Zeit:     {datetime.now().isoformat()}",
            f"Grund:    {reason}",
            "",
            "--- Kontext ---",
            f"Song:     {ctx.get('song', 'unbekannt')}",
            f"Lokation: {ctx.get('location', 'unbekannt')}",
            "",
            "--- Letzte Aktionen (Ring-Buffer) ---",
        ]
        if self._ring:
            for entry in self._ring:
                lines.append(f"  {entry}")
        else:
            lines.append("  (keine Aktionen aufgezeichnet)")
        return lines

    def write_report(self, reason: str, extra_lines=None):
        """Schreibt sofort ein Crash-/Diagnose-Log (ohne Exception-Objekt).

        Fuer Faelle, die wir GEZIELT abfangen (z.B. Audio-Backend nicht ladbar)
        und mit eigenen Diagnose-Zeilen anreichern wollen, statt auf eine
        unbehandelte Exception zu warten. Gibt den Pfad des Logs zurueck."""
        return self._write_log(reason=reason, extra_lines=extra_lines)

    def _write_log(self, reason: str, exc_type=None, exc_value=None, exc_tb=None,
                   extra_lines=None):
        """Schreibt sofort ein Crash-Logfile auf Disk. Pfad, "" bei Fehler."""
        # Mikrosekunden: zwei Fehler in derselben Sekunde ueberschreiben sich
        # nicht; sortiert trotzdem korrekt nach alten Namen ('.' < '_').
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        # Crash-Logs liegen in logs/crashes/. Ordner robust erzeugen.
        crash_dir = os.path.join(self._app_dir, "logs", "crashes")
        try:
            os.makedirs(crash_dir, exist_ok=True)
        except OSError:
            crash_dir = self._app_dir  # Fallback bei Permission-Fehler
        log_path = os.path.join(crash_dir, f"crash_{timestamp}.log")
        # Die Uhr rueckt unter Windows nur etwa jede Millisekunde weiter: bei
        # gleichem Namen Zaehler anhaengen ('_1' sortiert nach '.log').
        n = 0
        while os.path.exists(log_path):
            n += 1
            log_path = os.path.join(crash_dir, f"crash_{timestamp}_{n}.log")

        lines = self._collect_header(reason)

        if extra_lines:
            lines += ["", "--- Diagnose ---"] + list(extra_lines)

        if exc_type is not None:
            tb_text = "".join(traceback.format_tb(exc_tb))
            lines += [
                "",
                "--- Exception ---",
                f"Typ:     {exc_type.__name__}",
                f"Meldung: {exc_value}",
                "",
                "--- Stacktrace ---",
                tb_text,
            ]

        try:
            with open(log_path, "w", encoding="utf-8") as f:
                f.write("\n".join(lines))
        except Exception:
            return ""
        return log_path

    def _on_unhandled_exception(self, exc_type, exc_value, exc_tb):
        self._write_log(
            reason="Unbehandelte Python-Exception",
            exc_type=exc_type,
            exc_value=exc_value,
            exc_tb=exc_tb,
        )
        sys.__excepthook__(exc_type, exc_value, exc_tb)

    @staticmethod
    def find_crash_logs(app_dir: str, newer_than: str = "") -> list:
        """Gibt sortierte Liste aller crash_*.log-Dateipfade zurueck (neueste zuerst).
        Schaut primaer in logs/crashes/, faellt zurueck auf app_dir (Legacy).
        newer_than: nur Logs, deren Dateiname (Zeitstempel) groesser ist —
        so werden bereits gemeldete Logs beim naechsten Start uebersprungen."""
        results = []
        for d in (os.path.join(app_dir, "logs", "crashes"), app_dir):
            results.extend(glob.glob(os.path.join(d, "crash_*.log")))
        results = [p for p in set(results) if os.path.basename(p) > newer_than]
        return sorted(results, key=os.path.basename, reverse=True)


def setup(app_dir: str) -> CrashLogger:
    """Initialisiert den Crash-Handler und gibt den Logger zurueck.

    Installiert den Python-excepthook und (sofern PySide verfuegbar) den
    Qt-Message-Handler. Idempotent: Mehrfachaufrufe behalten denselben Logger
    (inkl. Ring-Buffer) und stellen nur sicher, dass die Hooks installiert
    sind. So kann der Handler GANZ FRUEH (vor riskanten Imports, noch ohne
    QApplication) installiert und in main() gefahrlos erneut aufgerufen werden.
    """
    global _logger
    if _logger is None:
        _logger = CrashLogger(app_dir)
    _logger.install()
    _logger.install_qt_handler()
    return _logger


def write_report(reason: str, extra_lines=None) -> str:
    """Schreibt ein Diagnose-Log (no-op wenn nicht initialisiert).
    Pfad des Logs, "" wenn nichts geschrieben wurde."""
    if _logger:
        return _logger.write_report(reason, extra_lines)
    return ""


def mark_notified(settings, log_path: str):
    """Vermerkt ein Log als gemeldet, damit der Start-Hinweis es nicht mehr
    zeigt. Der Vermerk laeuft nur vorwaerts: ein aelteres Log setzt ihn nicht
    zurueck (sonst kaeme ein neueres beim naechsten Start wieder hoch)."""
    name = os.path.basename(log_path)
    if name > str(settings.value(LAST_NOTIFIED_KEY, "") or ""):
        settings.setValue(LAST_NOTIFIED_KEY, name)
        settings.sync()


def report_once(settings, reason: str, problems: list) -> str:
    """Log zu einem Problem, das bei jedem Start wieder auftritt (intern#166).
    Geschrieben wird nur, wenn sich die Problemliste seit dem letzten Log
    geaendert hat. Das Log gilt sofort als gemeldet: Der Caller sieht dazu
    schon den eigenen Dialog, der Start-Hinweis soll es nicht nochmal zeigen.
    Pfad des neuen Logs, "" wenn keins geschrieben wurde."""
    # Bewusst einfach: Vermerk bleibt stehen, wenn die Probleme verschwinden. Kommt
    # genau dieselbe Liste spaeter zurueck, gibt es kein neues Log (Dialog schon).
    fingerprint = " | ".join(sorted(problems))
    if fingerprint == str(settings.value(REPORTED_PROBLEMS_KEY, "") or ""):
        return ""
    path = write_report(reason, [f"  {p}" for p in problems])
    if path:
        settings.setValue(REPORTED_PROBLEMS_KEY, fingerprint)
        mark_notified(settings, path)
    return path


def log_action(action: str):
    """Traegt eine Aktion in den Ring-Buffer ein (no-op wenn nicht initialisiert)."""
    if _logger:
        _logger.log_action(action)
