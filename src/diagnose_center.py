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

from i18n import _t


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
        - Titel (Klassenattribute sind Translations-Schluessel, intern#236;
          uebersetzt wird erst beim Aufbau, damit die aktuelle Sprache gilt)
        - "Was misst dieser Test" + "Was du tun musst" + Dauer + Ergebnis
        - Start / Abbrechen Buttons
        - Live-Status-Zeile
        - Ergebnis-Karte mit Pfad + Ordner-oeffnen
    """

    title = ""
    what_it_measures = ""
    what_you_do = ""
    expected_duration = ""
    expected_result_hint = ""

    @staticmethod
    def _tr(key: str) -> str:
        """Schluessel uebersetzen; leer bleibt leer, "—" bleibt "—"."""
        return _t(key) if key and key != "—" else key

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
        title_lbl = QLabel(self._tr(self.title))
        font = title_lbl.font()
        font.setBold(True)
        font.setPointSize(font.pointSize() + 2)
        title_lbl.setFont(font)
        lay.addWidget(title_lbl)

        # "Was misst dieser Test"
        if self.what_it_measures:
            lay.addWidget(self._make_section(_t("diag_section_measures"),
                                             self._tr(self.what_it_measures)))
        if self.what_you_do:
            lay.addWidget(self._make_section(_t("diag_section_todo"),
                                             self._tr(self.what_you_do)))

        # Meta-Zeile
        meta_lines = []
        if self.expected_duration:
            meta_lines.append(_t("diag_meta_duration",
                                 value=self._tr(self.expected_duration)))
        if self.expected_result_hint:
            meta_lines.append(_t("diag_meta_result",
                                 value=self._tr(self.expected_result_hint)))
        if meta_lines:
            meta = QLabel("\n".join(meta_lines))
            meta.setStyleSheet("color: #555;")
            lay.addWidget(meta)

        # Button-Reihe
        btn_row = QHBoxLayout()
        self._start_btn = QPushButton(_t("diag_btn_start"))
        self._start_btn.clicked.connect(self._on_start_clicked)
        self._cancel_btn = QPushButton(_t("diag_btn_cancel"))
        self._cancel_btn.clicked.connect(self._on_cancel_clicked)
        self._cancel_btn.setEnabled(False)
        btn_row.addWidget(self._start_btn)
        btn_row.addWidget(self._cancel_btn)
        btn_row.addStretch()
        lay.addLayout(btn_row)

        # Status
        self._status_lbl = QLabel(_t("diag_status_ready"))
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
        self._open_folder_btn = QPushButton(_t("diag_btn_open_folder"))
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
        self._status_lbl.setText(_t("diag_status_done", icon=icon))
        self._result_summary.setText(summary)
        if file_path:
            self._last_result_path = file_path
            self._result_path_lbl.setText(
                _t("diag_log_saved", path=file_path))
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
            self.finish(_t("diag_error", error=e), "", ok=False)

    def _on_cancel_clicked(self):
        if not self._running:
            return
        self.cancel_test()
        self._running = False
        self._start_btn.setEnabled(True)
        self._cancel_btn.setEnabled(False)
        self.set_status(_t("diag_status_cancelled"))

    def _on_open_folder(self):
        if self._last_result_path:
            open_in_explorer(self._last_result_path)


# ---------------------------------------------------------------------------
# Test A — System-Snapshot
# ---------------------------------------------------------------------------

class SystemSnapshotTest(BaseTestWidget):
    title = "diag_a_title"
    what_it_measures = "diag_a_measures"
    what_you_do = "diag_todo_just_start"
    expected_duration = "diag_a_duration"
    expected_result_hint = "diag_result_log_file"

    def run_test(self):
        self.set_status(_t("diag_a_status"))
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
            self.finish(_t("diag_write_error", error=e), "", ok=False)
            return

        self.finish(
            _t("diag_a_done", lines=len(lines),
               size=fmt_size(os.path.getsize(path))),
            path, ok=True)


# ---------------------------------------------------------------------------
# Test D — QTimer-Inventur
# ---------------------------------------------------------------------------

class QTimerInventoryTest(BaseTestWidget):
    title = "diag_d_title"
    what_it_measures = "diag_d_measures"
    what_you_do = "diag_todo_just_start"
    expected_duration = "diag_d_duration"
    expected_result_hint = "diag_result_log_file"

    def run_test(self):
        self.set_status(_t("diag_d_status"))
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
            self.finish(_t("diag_write_error", error=e), "", ok=False)
            return

        suspicious = sum(1 for t in timers if t[0] >= 30000)
        if suspicious > 0:
            summary = _t("diag_d_done_suspicious", count=len(timers),
                         suspicious=suspicious)
        else:
            summary = _t("diag_d_done_ok", count=len(timers))
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
                _t("diag_f_progress", elapsed=elapsed,
                   total=self._duration_s, top=top_str[:80]))
        self.finished.emit(samples)


class ExternalLoadTest(BaseTestWidget):
    title = "diag_f_title"
    what_it_measures = "diag_f_measures"
    what_you_do = "diag_f_todo"
    expected_duration = "diag_f_duration"
    expected_result_hint = "diag_result_log_file"

    def __init__(self, app_dir, parent=None):
        super().__init__(app_dir, parent)
        self._worker = None
        self._thread = None

    def run_test(self):
        self.set_status(_t("diag_f_status_start"))
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
            self.finish(_t("diag_f_no_samples"), "", ok=False)
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
            self.finish(_t("diag_write_error", error=e), "", ok=False)
            return

        top_name = top_culprits[0][0] if top_culprits else _t("diag_none")
        self.finish(
            _t("diag_f_done", count=len(samples), name=top_name),
            path, ok=True)


# ---------------------------------------------------------------------------
# Test G — Stall-Sentinel (passiv, Status-Anzeige)
# ---------------------------------------------------------------------------

class StallSentinelStatus(BaseTestWidget):
    title = "diag_g_title"
    what_it_measures = "diag_g_measures"
    what_you_do = "diag_g_todo"
    expected_duration = "—"
    expected_result_hint = "diag_g_result_hint"

    def __init__(self, app_dir, parent=None):
        super().__init__(app_dir, parent)
        self._start_btn.setText(_t("diag_g_refresh"))
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
            self.finish(_t("diag_g_unavailable"), "", ok=False)
            return

        lines = []
        lines.append(_t("diag_g_stat_uptime", value=stats.get('uptime', '?')))
        lines.append(_t("diag_g_stat_count", value=stats.get('count', 0)))
        lines.append(_t("diag_g_stat_max", value=stats.get('max_ms', 0)))
        if stats.get("last_at"):
            lines.append(_t("diag_g_stat_last", value=stats['last_at']))
        self._result_summary.setText("\n".join(lines))
        self._result_path_lbl.setText(_t("diag_g_tip"))
        self._open_folder_btn.setVisible(False)
        self._result_frame.setVisible(True)
        self._status_lbl.setText(_t("diag_g_status_updated"))
        self._running = False
        self._start_btn.setEnabled(True)


# ---------------------------------------------------------------------------
# Test H — Bundle
# ---------------------------------------------------------------------------

class BundleTest(BaseTestWidget):
    title = "diag_h_title"
    what_it_measures = "diag_h_measures"
    what_you_do = "diag_h_todo"
    expected_duration = "diag_h_duration"
    expected_result_hint = "diag_h_result_hint"

    def run_test(self):
        self.set_status(_t("diag_h_status"))
        logs_root = os.path.join(self._app_dir, "logs")
        if not os.path.isdir(logs_root):
            self.finish(_t("diag_h_no_logs"), "", ok=False)
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
            self.finish(_t("diag_h_error", error=e), "", ok=False)
            return

        size = os.path.getsize(out_path)
        self.finish(
            _t("diag_h_done", count=added, size=fmt_size(size)),
            out_path, ok=True)


# ---------------------------------------------------------------------------
# Audio-Test-Stubs (B/C/E — kommen in v0.92)
# ---------------------------------------------------------------------------

class _ComingSoonWidget(BaseTestWidget):
    expected_duration = "—"
    expected_result_hint = "—"

    def _build_ui(self):
        super()._build_ui()
        self._start_btn.setText(_t("diag_soon_btn"))
        self._start_btn.setEnabled(False)
        self._cancel_btn.setVisible(False)
        info = QLabel(_t("diag_soon_info"))
        info.setStyleSheet(
            "color: #b58900; font-style: italic; padding: 6px; "
            "background: #fff8e0; border: 1px solid #e8c060; "
            "border-radius: 4px;")
        info.setWordWrap(True)
        # Vor dem Status einfuegen
        self.layout().insertWidget(self.layout().count() - 3, info)


class SilencePlaybackTest(_ComingSoonWidget):
    title = "diag_b_title"
    what_it_measures = "diag_b_measures"
    what_you_do = "diag_b_todo"


class HostapiCompareTest(_ComingSoonWidget):
    title = "diag_c_title"
    what_it_measures = "diag_c_measures"
    what_you_do = "diag_soon_todo"


class FadeOutStressTest(_ComingSoonWidget):
    title = "diag_e_title"
    what_it_measures = "diag_e_measures"
    what_you_do = "diag_soon_todo"


# ---------------------------------------------------------------------------
# Haupt-Dialog
# ---------------------------------------------------------------------------

class DiagnoseCenterDialog(QDialog):
    """Diagnose-Center mit Tabs fuer einzelne Tests."""

    def __init__(self, app_dir: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(_t("diag_window_title"))
        self.resize(720, 600)
        self._app_dir = app_dir

        lay = QVBoxLayout(self)

        # Kopfzeile mit "Logs-Ordner öffnen"
        top = QHBoxLayout()
        title = QLabel(f"<h2>{_t('diag_window_title')}</h2>")
        top.addWidget(title)
        top.addStretch()
        open_logs_btn = QPushButton(_t("diag_open_logs"))
        open_logs_btn.clicked.connect(self._open_logs)
        top.addWidget(open_logs_btn)
        lay.addLayout(top)

        intro = QLabel(_t("diag_intro"))
        intro.setWordWrap(True)
        intro.setStyleSheet("padding: 4px 0 8px 0; color: #444;")
        lay.addWidget(intro)

        tabs = QTabWidget()
        # System
        sys_tabs = QTabWidget()
        sys_tabs.setTabPosition(QTabWidget.West)
        sys_tabs.addTab(SystemSnapshotTest(app_dir),
                        _t("diag_a_tab"))
        sys_tabs.addTab(QTimerInventoryTest(app_dir),
                        _t("diag_d_tab"))
        tabs.addTab(sys_tabs, _t("diag_tab_system"))

        # Audio
        audio_tabs = QTabWidget()
        audio_tabs.setTabPosition(QTabWidget.West)
        audio_tabs.addTab(SilencePlaybackTest(app_dir),
                          _t("diag_b_tab"))
        audio_tabs.addTab(HostapiCompareTest(app_dir),
                          _t("diag_c_tab"))
        audio_tabs.addTab(FadeOutStressTest(app_dir),
                          _t("diag_e_tab"))
        tabs.addTab(audio_tabs, _t("diag_tab_audio"))

        # Externes
        ext_tabs = QTabWidget()
        ext_tabs.setTabPosition(QTabWidget.West)
        ext_tabs.addTab(ExternalLoadTest(app_dir),
                        _t("diag_f_tab"))
        ext_tabs.addTab(StallSentinelStatus(app_dir),
                        _t("diag_g_tab"))
        tabs.addTab(ext_tabs, _t("diag_tab_external"))

        # Bundle
        tabs.addTab(BundleTest(app_dir), _t("diag_tab_bundle"))

        lay.addWidget(tabs)

        # Footer
        footer = QHBoxLayout()
        footer.addStretch()
        close_btn = QPushButton(_t("diag_close"))
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
