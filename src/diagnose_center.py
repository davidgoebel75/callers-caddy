"""Diagnose-Center fuer Callers Caddy (v0.91, Strang 3 Anti-Ruckler-Backlog).

Sammelt System- und Audio-Daten zur Aussetzer-Diagnose, ohne dass der User
externe Tools (LatencyMon, Sysinternals, PowerShell) installieren muss.
Alle Tests laufen aus der App heraus, alle Outputs landen in logs/diagnose/.

Test-Katalog:
  A — System-Snapshot (autonom)
  B — Stille-Wiedergabe-Test (Stub, kommt in v0.92)
  C — Hostapi-Vergleich (Stub, kommt in v0.92)
  D — QTimer-Inventur (autonom)
  E — Fade-Out-Stress-Test (Stub, kommt in v0.92)
  F — Externe-Last-Sampling (60 s, psutil-basiert)
  G — Stall-Sentinel (passiv im Hintergrund, Status-Anzeige hier)
  H — Bundle "Senden an Entwickler" (ZIP)
"""

import os
import platform
import zipfile
import subprocess
from datetime import datetime

from PySide6.QtCore import QTimer, QThread, Signal, QObject
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QTabWidget,
    QWidget,
    QPushButton,
    QLabel,
    QFrame,
    QApplication,
)
from PySide6.QtGui import QFont


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def diagnose_dir(app_dir: str) -> str:
    """logs/diagnose/ — wird bei Bedarf erzeugt."""
    p = os.path.join(app_dir, "logs", "diagnose")
    try:
        os.makedirs(p, exist_ok=True)
    except OSError:
        pass
    return p


def open_in_explorer(path: str):
    """Oeffnet Windows-Explorer, Datei selektiert."""
    try:
        if os.path.isfile(path):
            subprocess.Popen(["explorer", "/select,", os.path.normpath(path)])
        else:
            os.startfile(path)
    except (OSError, FileNotFoundError):
        pass


def fmt_size(n_bytes: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n_bytes < 1024:
            return f"{n_bytes:.1f} {unit}"
        n_bytes /= 1024
    return f"{n_bytes:.1f} TB"


# ---------------------------------------------------------------------------
# BaseTestWidget — gemeinsames Pattern
# ---------------------------------------------------------------------------

class BaseTestWidget(QWidget):
    """Pattern fuer jeden Test:
        - Titel
        - "Was misst dieser Test" + "Was du tun musst" + Dauer + Ergebnis
        - Start / Abbrechen Buttons
        - Live-Status-Zeile
        - Ergebnis-Karte mit Pfad + Ordner-oeffnen
    """

    title = "Test"
    what_it_measures = ""
    what_you_do = ""
    expected_duration = ""
    expected_result_hint = ""

    def __init__(self, app_dir: str, parent=None):
        super().__init__(parent)
        self._app_dir = app_dir
        self._running = False
        self._last_result_path = ""
        self._build_ui()

    def _build_ui(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 16, 16, 16)
        lay.setSpacing(10)

        # Titel
        title_lbl = QLabel(self.title)
        font = title_lbl.font()
        font.setBold(True)
        font.setPointSize(font.pointSize() + 2)
        title_lbl.setFont(font)
        lay.addWidget(title_lbl)

        # "Was misst dieser Test"
        if self.what_it_measures:
            lay.addWidget(self._make_section("Was misst dieser Test:",
                                             self.what_it_measures))
        if self.what_you_do:
            lay.addWidget(self._make_section("Was du tun musst:",
                                             self.what_you_do))

        # Meta-Zeile
        meta_lines = []
        if self.expected_duration:
            meta_lines.append(f"Dauer:    {self.expected_duration}")
        if self.expected_result_hint:
            meta_lines.append(f"Ergebnis: {self.expected_result_hint}")
        if meta_lines:
            meta = QLabel("\n".join(meta_lines))
            meta.setStyleSheet("color: #555;")
            lay.addWidget(meta)

        # Button-Reihe
        btn_row = QHBoxLayout()
        self._start_btn = QPushButton("Test starten")
        self._start_btn.clicked.connect(self._on_start_clicked)
        self._cancel_btn = QPushButton("Abbrechen")
        self._cancel_btn.clicked.connect(self._on_cancel_clicked)
        self._cancel_btn.setEnabled(False)
        btn_row.addWidget(self._start_btn)
        btn_row.addWidget(self._cancel_btn)
        btn_row.addStretch()
        lay.addLayout(btn_row)

        # Status
        self._status_lbl = QLabel("Bereit.")
        self._status_lbl.setStyleSheet("color: #444; padding: 4px;")
        lay.addWidget(self._status_lbl)

        # Ergebnis-Karte (versteckt bis fertig)
        self._result_frame = QFrame()
        self._result_frame.setFrameShape(QFrame.StyledPanel)
        self._result_frame.setVisible(False)
        rlay = QVBoxLayout(self._result_frame)
        self._result_summary = QLabel("")
        self._result_summary.setWordWrap(True)
        rlay.addWidget(self._result_summary)

        self._result_path_lbl = QLabel("")
        self._result_path_lbl.setFont(QFont("Consolas", 9))
        self._result_path_lbl.setWordWrap(True)
        self._result_path_lbl.setStyleSheet("color: #333; padding-top: 6px;")
        rlay.addWidget(self._result_path_lbl)

        result_btn_row = QHBoxLayout()
        self._open_folder_btn = QPushButton("Ordner öffnen")
        self._open_folder_btn.clicked.connect(self._on_open_folder)
        result_btn_row.addWidget(self._open_folder_btn)
        result_btn_row.addStretch()
        rlay.addLayout(result_btn_row)

        lay.addWidget(self._result_frame)
        lay.addStretch()

    def _make_section(self, header: str, body: str) -> QWidget:
        w = QWidget()
        wl = QVBoxLayout(w)
        wl.setContentsMargins(0, 0, 0, 0)
        wl.setSpacing(2)
        h = QLabel(f"<b>{header}</b>")
        wl.addWidget(h)
        b = QLabel(body)
        b.setWordWrap(True)
        b.setStyleSheet("padding-left: 10px;")
        wl.addWidget(b)
        return w

    # ---- Subclass-API ----

    def run_test(self):
        """Subklasse ueberschreibt. Soll set_status() / finish() aufrufen."""
        raise NotImplementedError

    def cancel_test(self):
        """Subklasse ueberschreibt, falls Test abbrechbar ist."""
        pass

    # ---- UI-Helpers fuer Subklassen ----

    def set_status(self, text: str):
        self._status_lbl.setText(text)
        QApplication.processEvents()

    def finish(self, summary: str, file_path: str = "", ok: bool = True):
        self._running = False
        self._start_btn.setEnabled(True)
        self._cancel_btn.setEnabled(False)
        icon = "✓" if ok else "⚠"
        self._status_lbl.setText(f"{icon} Test abgeschlossen.")
        self._result_summary.setText(summary)
        if file_path:
            self._last_result_path = file_path
            self._result_path_lbl.setText(
                f"Log gespeichert unter:\n{file_path}")
            self._open_folder_btn.setVisible(True)
        else:
            self._last_result_path = ""
            self._result_path_lbl.setText("")
            self._open_folder_btn.setVisible(False)
        self._result_frame.setVisible(True)

    def _on_start_clicked(self):
        if self._running:
            return
        self._running = True
        self._start_btn.setEnabled(False)
        self._cancel_btn.setEnabled(True)
        self._result_frame.setVisible(False)
        try:
            self.run_test()
        except Exception as e:
            self.finish(f"Fehler: {e}", "", ok=False)

    def _on_cancel_clicked(self):
        if not self._running:
            return
        self.cancel_test()
        self._running = False
        self._start_btn.setEnabled(True)
        self._cancel_btn.setEnabled(False)
        self.set_status("Test abgebrochen — nichts gespeichert.")

    def _on_open_folder(self):
        if self._last_result_path:
            open_in_explorer(self._last_result_path)


# ---------------------------------------------------------------------------
# Test A — System-Snapshot
# ---------------------------------------------------------------------------

class SystemSnapshotTest(BaseTestWidget):
    title = "A) System-Snapshot"
    what_it_measures = ('Wir sammeln Eckdaten deines Systems: Windows-Version, '
                        'CPU, RAM, Audio-Geräte mit allen verfügbaren Backends, '
                        'Callers-Caddy-Version und INI-Einstellungen.')
    what_you_do = 'Klicke auf „Test starten". Es ist nichts weiter zu tun.'
    expected_duration = "ca. 2 Sekunden"
    expected_result_hint = "Log-Datei in logs/diagnose/"

    def run_test(self):
        self.set_status("Sammle Daten…")
        try:
            from system_report import generate_compact_header
        except ImportError:
            generate_compact_header = None

        lines = []
        lines.append(f"=== System-Snapshot {datetime.now():%Y-%m-%d %H:%M:%S} ===")
        try:
            import main as _m
            lines.append(f"Callers Caddy: v{getattr(_m, '__version__', '?')}")
        except Exception:
            pass
        lines.append(f"Python:        {platform.python_version()}")
        lines.append(f"Platform:      {platform.platform()}")
        lines.append(f"Maschine:      {platform.machine()}")
        lines.append(f"Prozessor:     {platform.processor()}")

        # psutil — CPU/RAM
        try:
            import psutil
            lines.append(f"CPU-Kerne:     {psutil.cpu_count(logical=False)} physisch, "
                         f"{psutil.cpu_count(logical=True)} logisch")
            freq = psutil.cpu_freq()
            if freq:
                lines.append(f"CPU-Takt:      aktuell {freq.current:.0f} MHz, "
                             f"max {freq.max:.0f} MHz")
            mem = psutil.virtual_memory()
            lines.append(f"RAM:           {mem.total / 1024**3:.1f} GB gesamt, "
                         f"{mem.available / 1024**3:.1f} GB frei "
                         f"({mem.percent}% Auslastung)")
        except ImportError:
            lines.append("psutil:        nicht verfuegbar")

        # Audio
        if generate_compact_header:
            try:
                for ln in generate_compact_header("snapshot"):
                    lines.append(ln)
            except Exception as e:
                lines.append(f"[Audio-Header-Fehler] {e}")

        # INI
        lines.append("")
        lines.append("=== INI-Inhalt ===")
        ini_path = os.path.join(self._app_dir, "callers_caddy.ini")
        if os.path.exists(ini_path):
            try:
                with open(ini_path, "r", encoding="utf-8") as f:
                    lines.append(f.read())
            except OSError as e:
                lines.append(f"[INI-Lesefehler] {e}")
        else:
            lines.append(f"(keine INI bei {ini_path})")

        # Speichern
        stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        path = os.path.join(diagnose_dir(self._app_dir),
                            f"system_{stamp}.txt")
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write("\n".join(lines))
        except OSError as e:
            self.finish(f"Konnte Datei nicht schreiben: {e}", "", ok=False)
            return

        self.finish(
            f"System-Snapshot erstellt ({len(lines)} Zeilen, "
            f"{fmt_size(os.path.getsize(path))}).",
            path, ok=True)


# ---------------------------------------------------------------------------
# Test D — QTimer-Inventur
# ---------------------------------------------------------------------------

class QTimerInventoryTest(BaseTestWidget):
    title = "D) QTimer-Inventur"
    what_it_measures = ('Wir listen alle aktiven Timer in Callers Caddy mit '
                        'ihrem Intervall auf. Hilft uns zu prüfen, ob ein '
                        'interner Timer im 60-Sekunden-Takt feuert (siehe '
                        'Anti-Ruckler-Backlog AR-017).')
    what_you_do = 'Klicke auf „Test starten". Es ist nichts weiter zu tun.'
    expected_duration = "sofort"
    expected_result_hint = "Log-Datei in logs/diagnose/"

    def run_test(self):
        self.set_status("Suche aktive Timer…")
        timers = self._collect_timers()
        lines = []
        lines.append(f"=== QTimer-Inventur {datetime.now():%Y-%m-%d %H:%M:%S} ===")
        lines.append(f"Gefunden: {len(timers)} aktive QTimer")
        lines.append("")
        if not timers:
            lines.append("(keiner)")
        else:
            # Sortiere nach Intervall absteigend — lange Intervalle sind verdaechtig
            for interval_ms, obj_class, obj_name in sorted(
                    timers, key=lambda t: -t[0]):
                tag = ""
                if interval_ms >= 30000:
                    tag = "  <-- VERDAECHTIG (>= 30 s)"
                lines.append(f"  {interval_ms:>10d} ms  {obj_class:30s}  "
                             f"{obj_name}{tag}")

        stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        path = os.path.join(diagnose_dir(self._app_dir),
                            f"qtimer_{stamp}.txt")
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write("\n".join(lines))
        except OSError as e:
            self.finish(f"Konnte Datei nicht schreiben: {e}", "", ok=False)
            return

        suspicious = sum(1 for t in timers if t[0] >= 30000)
        if suspicious > 0:
            summary = (f"{len(timers)} aktive QTimer. "
                       f"⚠ {suspicious} mit Intervall ≥ 30 s "
                       f"— bitte Log an Entwickler.")
        else:
            summary = (f"{len(timers)} aktive QTimer, "
                       "keiner mit ≥ 30 s Intervall.")
        self.finish(summary, path, ok=(suspicious == 0))

    def _collect_timers(self):
        """Walk alle QObjects, finde aktive QTimer mit interval > 0."""
        result = []
        app = QApplication.instance()
        if not app:
            return result
        try:
            seen = set()
            for tl in app.topLevelWidgets():
                self._walk(tl, seen, result)
        except Exception:
            pass
        return result

    def _walk(self, obj, seen, result):
        if id(obj) in seen:
            return
        seen.add(id(obj))
        try:
            if isinstance(obj, QTimer) and obj.isActive():
                result.append((obj.interval(),
                               obj.metaObject().className(),
                               obj.objectName() or "(unbenannt)"))
            for child in obj.children():
                self._walk(child, seen, result)
        except (RuntimeError, AttributeError):
            pass


# ---------------------------------------------------------------------------
# Test F — Externe-Last-Sampling
# ---------------------------------------------------------------------------

class ExternalLoadWorker(QObject):
    progress = Signal(str)
    finished = Signal(list)  # [(timestamp, top_procs_str), ...]

    def __init__(self, duration_s: int):
        super().__init__()
        self._duration_s = duration_s
        self._cancel = False

    def cancel(self):
        self._cancel = True

    def run(self):
        import time
        try:
            import psutil
        except ImportError:
            self.finished.emit([("[ERROR]", "psutil nicht installiert")])
            return

        samples = []
        # Warmup damit cpu_percent valide Werte liefert
        for p in psutil.process_iter(["name"]):
            try:
                p.cpu_percent(None)
            except Exception:
                pass
        t_start = time.monotonic()
        own_pid = os.getpid()
        sample_interval = 1.0  # 1 Sekunde
        next_sample = t_start
        while not self._cancel:
            now = time.monotonic()
            if now >= t_start + self._duration_s:
                break
            if now < next_sample:
                time.sleep(min(0.1, next_sample - now))
                continue
            next_sample += sample_interval
            top = []
            for p in psutil.process_iter(["name"]):
                if p.pid == own_pid:
                    continue
                try:
                    cpu = p.cpu_percent(None)
                except Exception:
                    continue
                if cpu > 0:
                    top.append((cpu, p.info.get("name") or f"PID-{p.pid}"))
            top.sort(reverse=True)
            top5 = top[:5]
            stamp = datetime.now().strftime("%H:%M:%S")
            top_str = "  ".join(f"{n}={c:.0f}%" for c, n in top5)
            samples.append((stamp, top_str))
            elapsed = int(now - t_start)
            self.progress.emit(
                f"Läuft… {elapsed}/{self._duration_s} s. "
                f"Aktuell Top: {top_str[:80]}")
        self.finished.emit(samples)


class ExternalLoadTest(BaseTestWidget):
    title = "F) Externe-Last-Sampling (60 s)"
    what_it_measures = ("Wir prüfen, welche anderen Programme während der "
                        "Wiedergabe CPU brauchen — Antivirus, Cloud-Sync, "
                        "Treiber-Services etc. Hilft den möglichen "
                        "Ruckler-Verursacher von außen einzugrenzen.")
    what_you_do = ('① Klick auf „Test starten". '
                   '② Mach in den nächsten 60 Sekunden das, was du sonst auch '
                   'machst während Musik läuft (Browser, Word, andere '
                   'Programme öffnen). '
                   '③ Warte bis der Test fertig ist.')
    expected_duration = "60 Sekunden"
    expected_result_hint = "Log-Datei in logs/diagnose/"

    def __init__(self, app_dir, parent=None):
        super().__init__(app_dir, parent)
        self._worker = None
        self._thread = None

    def run_test(self):
        self.set_status("Starte Sampling…")
        self._worker = ExternalLoadWorker(duration_s=60)
        self._thread = QThread(self)
        self._worker.moveToThread(self._thread)
        self._worker.progress.connect(self.set_status)
        self._worker.finished.connect(self._on_worker_finished)
        self._thread.started.connect(self._worker.run)
        self._thread.start()

    def cancel_test(self):
        if self._worker:
            self._worker.cancel()

    def _on_worker_finished(self, samples):
        try:
            self._thread.quit()
            self._thread.wait(2000)
        except Exception:
            pass
        if not samples:
            self.finish("Kein Sample erfasst (Test zu kurz abgebrochen?).",
                        "", ok=False)
            return
        # Aggregat: welche Prozesse traten wie oft in Top-5 auf?
        from collections import Counter
        cnt = Counter()
        for _, top_str in samples:
            for tok in top_str.split("  "):
                if "=" in tok:
                    name = tok.split("=")[0]
                    cnt[name] += 1
        top_culprits = cnt.most_common(10)

        lines = []
        lines.append(f"=== Externe-Last-Sampling "
                     f"{datetime.now():%Y-%m-%d %H:%M:%S} ===")
        lines.append(f"Samples:       {len(samples)} (1 pro Sekunde)")
        lines.append("")
        lines.append("Top-Prozesse nach Häufigkeit in Top-5 CPU:")
        for name, c in top_culprits:
            lines.append(f"  {c:3d} × {name}")
        lines.append("")
        lines.append("Zeitlinie:")
        for stamp, top_str in samples:
            lines.append(f"  {stamp}  {top_str}")

        stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        path = os.path.join(diagnose_dir(self._app_dir),
                            f"external_load_{stamp}.txt")
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write("\n".join(lines))
        except OSError as e:
            self.finish(f"Konnte Datei nicht schreiben: {e}", "", ok=False)
            return

        top_name = top_culprits[0][0] if top_culprits else "(keine)"
        self.finish(
            f"60 Samples erfasst. Häufigster Top-CPU-Prozess "
            f"(außer Callers Caddy): {top_name}",
            path, ok=True)


# ---------------------------------------------------------------------------
# Test G — Stall-Sentinel (passiv, Status-Anzeige)
# ---------------------------------------------------------------------------

class StallSentinelStatus(BaseTestWidget):
    title = "G) Stall-Sentinel (passive Hintergrund-Überwachung)"
    what_it_measures = ("Der Sentinel läuft die ganze Zeit im Hintergrund mit "
                        "und prüft alle 50 ms, ob der Main-Thread blockiert "
                        "war. Bei jedem Block > 100 ms wird ein Eintrag im "
                        "Perflog erzeugt. Hier siehst du nur den aktuellen "
                        "Status.")
    what_you_do = 'Nichts. Klicke auf „Aktualisieren" für aktuelle Zahlen.'
    expected_duration = "—"
    expected_result_hint = "Stalls landen direkt im Perflog (logs/perf/)"

    def __init__(self, app_dir, parent=None):
        super().__init__(app_dir, parent)
        self._start_btn.setText("Aktualisieren")
        self._cancel_btn.setVisible(False)

    def run_test(self):
        # Sentinel-Status aus perf.py auslesen, falls API existiert (BL-201:
        # frueher aus main.py — Perf-Zustand liegt jetzt im Blatt-Modul perf).
        try:
            import perf as _p
            getter = getattr(_p, "get_stall_sentinel_stats", None)
            if getter:
                stats = getter()
            else:
                stats = None
        except Exception:
            stats = None

        if not stats:
            self.finish(
                "Sentinel-Statistik nicht verfügbar (alte Version oder "
                "Sentinel deaktiviert).", "", ok=False)
            return

        lines = []
        lines.append(f"Sentinel aktiv seit:        {stats.get('uptime', '?')}")
        lines.append(f"Stalls > 100 ms erkannt:    {stats.get('count', 0)}")
        lines.append(f"Längster Stall:             "
                     f"{stats.get('max_ms', 0)} ms")
        if stats.get("last_at"):
            lines.append(f"Letzter Stall:              {stats['last_at']}")
        self._result_summary.setText("\n".join(lines))
        self._result_path_lbl.setText(
            "Tipp: Stalls landen automatisch im Perflog der laufenden Sitzung "
            "(logs/perf/). Bitte das Perflog ans Bundle anhängen.")
        self._open_folder_btn.setVisible(False)
        self._result_frame.setVisible(True)
        self._status_lbl.setText("Status aktualisiert.")
        self._running = False
        self._start_btn.setEnabled(True)


# ---------------------------------------------------------------------------
# Test H — Bundle
# ---------------------------------------------------------------------------

class BundleTest(BaseTestWidget):
    title = 'H) Bundle „Senden an Entwickler"'
    what_it_measures = ("Packt die letzten Logs in eine ZIP-Datei, die du "
                        "per E-Mail an den Entwickler schicken kannst.")
    what_you_do = ('① Klick auf „Test starten". '
                   '② Anschließend Ordner öffnen, ZIP per Mail anhängen.')
    expected_duration = "ca. 5 Sekunden"
    expected_result_hint = "ZIP-Datei in logs/diagnose/"

    def run_test(self):
        self.set_status("Sammle Logs…")
        logs_root = os.path.join(self._app_dir, "logs")
        if not os.path.isdir(logs_root):
            self.finish("Kein logs/-Ordner gefunden — nichts zu bündeln.",
                        "", ok=False)
            return

        stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        out_path = os.path.join(diagnose_dir(self._app_dir),
                                f"bundle_{stamp}.zip")
        added = 0
        try:
            with zipfile.ZipFile(out_path, "w",
                                 zipfile.ZIP_DEFLATED) as zf:
                # Perflogs: die jüngsten 5
                perf_dir = os.path.join(logs_root, "perf")
                if os.path.isdir(perf_dir):
                    files = [(f, os.path.getmtime(os.path.join(perf_dir, f)))
                             for f in os.listdir(perf_dir)
                             if f.endswith(".txt")]
                    files.sort(key=lambda t: -t[1])
                    for name, _ in files[:5]:
                        zf.write(os.path.join(perf_dir, name),
                                 f"perf/{name}")
                        added += 1
                # Diagnose-Files der letzten 7 Tage
                diag_dir = os.path.join(logs_root, "diagnose")
                if os.path.isdir(diag_dir):
                    import time
                    cutoff = time.time() - 7 * 86400
                    for name in os.listdir(diag_dir):
                        full = os.path.join(diag_dir, name)
                        if name.endswith(".zip"):
                            continue  # keine alten Bundles mit reinpacken
                        if os.path.getmtime(full) < cutoff:
                            continue
                        zf.write(full, f"diagnose/{name}")
                        added += 1
                # rules.log
                rl = os.path.join(logs_root, "rules.log")
                if os.path.exists(rl):
                    zf.write(rl, "rules.log")
                    added += 1
                # system_report.txt
                sr = os.path.join(logs_root, "system_report.txt")
                if os.path.exists(sr):
                    zf.write(sr, "system_report.txt")
                    added += 1
                # INI (Konfiguration)
                ini = os.path.join(self._app_dir, "callers_caddy.ini")
                if os.path.exists(ini):
                    zf.write(ini, "callers_caddy.ini")
                    added += 1
                # Crash-Logs (alle vorhandenen, sind klein)
                crash_dir = os.path.join(logs_root, "crashes")
                if os.path.isdir(crash_dir):
                    for name in os.listdir(crash_dir):
                        if name.endswith(".log"):
                            zf.write(os.path.join(crash_dir, name),
                                     f"crashes/{name}")
                            added += 1
                # Version-Info
                try:
                    import main as _m
                    ver = getattr(_m, "__version__", "?")
                except Exception:
                    ver = "?"
                zf.writestr(
                    "VERSION.txt",
                    f"Callers Caddy v{ver}\n"
                    f"Bundle erstellt: {datetime.now():%Y-%m-%d %H:%M:%S}\n"
                    f"OS: {platform.platform()}\n")
        except OSError as e:
            self.finish(f"Bundle-Fehler: {e}", "", ok=False)
            return

        size = os.path.getsize(out_path)
        self.finish(
            f"Bundle erstellt mit {added} Datei(en) "
            f"({fmt_size(size)}).\n\n"
            f"Bitte diese ZIP-Datei per E-Mail an den Entwickler senden. "
            f"Vielen Dank für die Mithilfe!",
            out_path, ok=True)


# ---------------------------------------------------------------------------
# Audio-Test-Stubs (B/C/E — kommen in v0.92)
# ---------------------------------------------------------------------------

class _ComingSoonWidget(BaseTestWidget):
    expected_duration = "—"
    expected_result_hint = "—"

    def _build_ui(self):
        super()._build_ui()
        self._start_btn.setText("In Vorbereitung")
        self._start_btn.setEnabled(False)
        self._cancel_btn.setVisible(False)
        info = QLabel(
            "Dieser Test ist in Vorbereitung und kommt mit der nächsten "
            "Version (v0.92). Bis dahin sind die Tests A, D, F und H "
            "die aussagekräftigsten.")
        info.setStyleSheet(
            "color: #b58900; font-style: italic; padding: 6px; "
            "background: #fff8e0; border: 1px solid #e8c060; "
            "border-radius: 4px;")
        info.setWordWrap(True)
        # Vor dem Status einfuegen
        self.layout().insertWidget(self.layout().count() - 3, info)


class SilencePlaybackTest(_ComingSoonWidget):
    title = "B) Stille-Wiedergabe-Test (60 s) — Vorbereitung"
    what_it_measures = ("Wir spielen einen leisen Test-Ton (Sinus + "
                        "Rauschen) für 60 s und protokollieren Aussetzer "
                        "und Stalls.")
    what_you_do = ('Klick auf „Test starten" — sobald verfügbar. '
                   'Solange: bitte Test A + F nutzen, das liefert schon '
                   'viel Information.')


class HostapiCompareTest(_ComingSoonWidget):
    title = "C) Hostapi-Vergleich — Vorbereitung"
    what_it_measures = ("Wir spielen den Test-Ton nacheinander durch jedes "
                        "verfügbare Audio-Backend (MME, WASAPI, WDM-KS) "
                        "und vergleichen die Aussetzer-Quote.")
    what_you_do = 'Klick auf „Test starten" — sobald verfügbar.'


class FadeOutStressTest(_ComingSoonWidget):
    title = "E) Fade-Out-Stress-Test — Vorbereitung"
    what_it_measures = ("Wir messen wie sauber der Fade-Out auf deinem "
                        "System läuft. Seit v0.91 ist Fade-Out vektorisiert "
                        "und sollte auch auf schwacher CPU glatt sein.")
    what_you_do = 'Klick auf „Test starten" — sobald verfügbar.'


# ---------------------------------------------------------------------------
# Haupt-Dialog
# ---------------------------------------------------------------------------

class DiagnoseCenterDialog(QDialog):
    """Diagnose-Center mit Tabs fuer einzelne Tests."""

    def __init__(self, app_dir: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Diagnose-Center")
        self.resize(720, 600)
        self._app_dir = app_dir

        lay = QVBoxLayout(self)

        # Kopfzeile mit "Logs-Ordner öffnen"
        top = QHBoxLayout()
        title = QLabel("<h2>Diagnose-Center</h2>")
        top.addWidget(title)
        top.addStretch()
        open_logs_btn = QPushButton("Logs-Ordner öffnen")
        open_logs_btn.clicked.connect(self._open_logs)
        top.addWidget(open_logs_btn)
        lay.addLayout(top)

        intro = QLabel(
            "Hier kannst du auf deinem System ein paar Tests laufen lassen, "
            "die dem Entwickler helfen, Aussetzer-Ursachen zu finden. Jeder "
            "Test schreibt eine Log-Datei nach <code>logs/diagnose/</code>. "
            'Am Ende kannst du mit „Bundle" alles in eine ZIP packen und '
            "per E-Mail schicken.")
        intro.setWordWrap(True)
        intro.setStyleSheet("padding: 4px 0 8px 0; color: #444;")
        lay.addWidget(intro)

        tabs = QTabWidget()
        # System
        sys_tabs = QTabWidget()
        sys_tabs.setTabPosition(QTabWidget.West)
        sys_tabs.addTab(SystemSnapshotTest(app_dir),
                        "A) System-Snapshot")
        sys_tabs.addTab(QTimerInventoryTest(app_dir),
                        "D) QTimer-Inventur")
        tabs.addTab(sys_tabs, "System")

        # Audio
        audio_tabs = QTabWidget()
        audio_tabs.setTabPosition(QTabWidget.West)
        audio_tabs.addTab(SilencePlaybackTest(app_dir),
                          "B) Stille-Wiedergabe")
        audio_tabs.addTab(HostapiCompareTest(app_dir),
                          "C) Hostapi-Vergleich")
        audio_tabs.addTab(FadeOutStressTest(app_dir),
                          "E) Fade-Out-Stress")
        tabs.addTab(audio_tabs, "Audio")

        # Externes
        ext_tabs = QTabWidget()
        ext_tabs.setTabPosition(QTabWidget.West)
        ext_tabs.addTab(ExternalLoadTest(app_dir),
                        "F) Externe-Last")
        ext_tabs.addTab(StallSentinelStatus(app_dir),
                        "G) Stall-Sentinel")
        tabs.addTab(ext_tabs, "Externes")

        # Bundle
        tabs.addTab(BundleTest(app_dir), "Bundle senden")

        lay.addWidget(tabs)

        # Footer
        footer = QHBoxLayout()
        footer.addStretch()
        close_btn = QPushButton("Schließen")
        close_btn.clicked.connect(self.accept)
        footer.addWidget(close_btn)
        lay.addLayout(footer)

    def _open_logs(self):
        logs_path = os.path.join(self._app_dir, "logs")
        try:
            os.makedirs(logs_path, exist_ok=True)
        except OSError:
            pass
        open_in_explorer(logs_path)
