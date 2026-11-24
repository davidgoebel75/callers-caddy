"""Performance-Logging + Startup-Instrumentierung fuer Callers Caddy.

Blatt-Modul (nur stdlib) — bewusst OHNE PySide6/Audio-Importe, damit es ganz
oben in main.py geladen werden kann (vor den schweren Imports) und der
frueheste Messpunkt korrekt liegt. Der gesamte perf-/Sentinel-Zustand lebt hier
als Modul-Global; main.py und diagnose_center.py greifen ausschliesslich ueber
die oeffentlichen Funktionen darauf zu (keine modueluebergreifenden
Global-Schreibzugriffe).

Aktivierung via INI: debug/performance_logging = true (main() ruft configure()).
Ausgabe: stdout UND zeitgestempelte Datei in logs/perf/.
"""

import sys
import os
import threading as _perf_threading
import time as _perf_time

# --- Startup-Perf: fruehester Messpunkt (Import-Zeit dieses Moduls) -----------
# main.py importiert perf ganz oben, noch vor den schweren PySide6/Audio-Imports;
# diese Marken liegen damit so frueh wie moeglich.
T_MODULE_TOP_PERF = _perf_time.perf_counter()
T_MODULE_TOP_WALL = _perf_time.time()


def process_create_epoch():
    """Prozess-Erstellungszeit (Unix-Epoch, Sekunden) via WinAPI GetProcessTimes.
    Das ist der Zeitpunkt VOR der ersten Python-Zeile — misst also Bootloader +
    Interpreter-Init. Gibt None zurueck, wenn nicht ermittelbar (Nicht-Windows /
    Fehler)."""
    try:
        import ctypes
        from ctypes import wintypes
        k32 = ctypes.windll.kernel32
        # argtypes/restype ZWINGEND setzen: sonst kappt ctypes auf 64-Bit die
        # byref-Pointer auf 32 Bit -> GetProcessTimes schlaegt fehl (liefert 0).
        k32.GetCurrentProcess.restype = wintypes.HANDLE
        k32.GetProcessTimes.argtypes = [wintypes.HANDLE] + \
            [ctypes.POINTER(wintypes.FILETIME)] * 4
        k32.GetProcessTimes.restype = wintypes.BOOL
        creation = wintypes.FILETIME()
        exit_t = wintypes.FILETIME()
        kernel_t = wintypes.FILETIME()
        user_t = wintypes.FILETIME()
        if not k32.GetProcessTimes(k32.GetCurrentProcess(),
                                   ctypes.byref(creation), ctypes.byref(exit_t),
                                   ctypes.byref(kernel_t), ctypes.byref(user_t)):
            return None
        # FILETIME: 100-ns-Ticks seit 1601-01-01 -> Unix-Epoch.
        ticks = (creation.dwHighDateTime << 32) | creation.dwLowDateTime
        return ticks / 1e7 - 11644473600.0
    except Exception:
        return None


T_PROCESS_CREATE_EPOCH = process_create_epoch()

# --- Zustand (Modul-Global; nur ueber die Funktionen unten anfassen) ----------
_PERF_ENABLED = False   # Wird via configure() aus INI gesetzt
_APP_VERSION = "?"      # Wird via configure() aus main.__version__ gesetzt
_PERF_FILE = None       # Datei-Handle fuer das Perf-Log
_PERF_LINES = []        # Puffer bis Datei geoeffnet wird
# perf_write wird auch aus Worker-Threads gerufen (Square Flow): Sperre, damit
# Zeilen im Perflog nicht ineinanderlaufen.
_PERF_WRITE_LOCK = _perf_threading.Lock()
# letzten [Perf]-Event tracken, damit der Stall-Detektor sagen kann *was*
# zuletzt auf dem Main-Thread lief, bevor er blockierte.
_LAST_PERF_LABEL = ""
_LAST_PERF_TIME_MONO = 0.0
# in INI gespeicherter Device-Index — fuer generate_compact_header(), damit der
# Perf-Header BEIDE Latenzen zeigt (System-Default UND konfiguriert).
_PERF_CONFIGURED_DEVICE_IDX = None

# Stall-Sentinel: zaehlt Main-Thread-Blocks > 100 ms fuer das Diagnose-Center.
_SENTINEL_START_MONO = _perf_time.monotonic()
_SENTINEL_COUNT = 0
_SENTINEL_MAX_MS = 0
_SENTINEL_LAST_AT = ""  # Wallclock "HH:MM:SS"


# --- Konfiguration / Zustands-Setter (von main.py aufgerufen) -----------------

def configure(enabled, device_index=None, version=None):
    """Setzt den perf-Zustand aus der INI (main()). Ersetzt frueheres direktes
    Schreiben der Modul-Globals ueber die Modulgrenze hinweg."""
    global _PERF_ENABLED, _PERF_CONFIGURED_DEVICE_IDX, _APP_VERSION
    _PERF_ENABLED = bool(enabled)
    _PERF_CONFIGURED_DEVICE_IDX = device_index
    if version is not None:
        _APP_VERSION = version


def is_enabled():
    """True, wenn Performance-Logging aktiv ist."""
    return _PERF_ENABLED


def get_last_perf():
    """(label, time_mono) des letzten [Perf]-Events — fuer den Stall-Detektor."""
    return _LAST_PERF_LABEL, _LAST_PERF_TIME_MONO


def record_stall(gap_ms):
    """Registriert einen Main-Thread-Stall fuer die Sentinel-Statistik."""
    global _SENTINEL_COUNT, _SENTINEL_MAX_MS, _SENTINEL_LAST_AT
    _SENTINEL_COUNT += 1
    if gap_ms > _SENTINEL_MAX_MS:
        _SENTINEL_MAX_MS = int(gap_ms)
    _SENTINEL_LAST_AT = _perf_ts()


def get_stall_sentinel_stats():
    """Liefert Sentinel-Status fuer das Diagnose-Center."""
    uptime_s = int(_perf_time.monotonic() - _SENTINEL_START_MONO)
    h, m, s = uptime_s // 3600, (uptime_s % 3600) // 60, uptime_s % 60
    return {
        "uptime": f"{h:02d}:{m:02d}:{s:02d}",
        "count": _SENTINEL_COUNT,
        "max_ms": _SENTINEL_MAX_MS,
        "last_at": _SENTINEL_LAST_AT,
    }


def _perf_ts():
    """Wallclock-Zeitstempel HH:MM:SS.mmm fuer Video-/Log-Synchronisation."""
    t = _perf_time.time()
    ms = int((t - int(t)) * 1000)
    return _perf_time.strftime("%H:%M:%S", _perf_time.localtime(t)) + f".{ms:03d}"


def perf_write(line: str):
    """Schreibt Perf-Zeile (mit Zeitstempel) in Puffer/Datei und stdout.

    [Sys]-Zeilen werden NICHT gestempelt — sie gehoeren zum Header-Block.
    Zusaetzlich wird das letzte [Perf]-Event fuer den Stall-Detektor gemerkt
    (damit wir bei einem Stall sagen koennen *was* zuletzt lief).
    """
    global _LAST_PERF_LABEL, _LAST_PERF_TIME_MONO
    if line.startswith("[Sys]"):
        stamped = line
    else:
        stamped = f"{_perf_ts()} {line}"
    with _PERF_WRITE_LOCK:
        print(stamped)
        if _PERF_FILE:
            _PERF_FILE.write(stamped + "\n")
            _PERF_FILE.flush()
        else:
            _PERF_LINES.append(stamped)
    # Letzten [Perf]-Event tracken (ohne Zeitstempel-Prefix und ohne Dauer)
    if line.startswith("[Perf]"):
        # "[Perf]   foo.bar (3 entries): 12ms" -> "foo.bar (3 entries)"
        body = line[len("[Perf]"):].strip()
        if ":" in body:
            body = body.rsplit(":", 1)[0]
        _LAST_PERF_LABEL = body
        _LAST_PERF_TIME_MONO = _perf_time.monotonic()


def app_dir():
    """Wurzelverzeichnis der App (EXE-Ordner oder CWD im Dev-Modus)."""
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.getcwd()


def logs_dir():
    """Zentraler Logs-Ordner <app_dir>/logs/. Wird bei Bedarf erzeugt."""
    p = os.path.join(app_dir(), "logs")
    try:
        os.makedirs(p, exist_ok=True)
    except OSError:
        pass
    return p


def _perf_logs_dir():
    p = os.path.join(logs_dir(), "perf")
    try:
        os.makedirs(p, exist_ok=True)
    except OSError:
        pass
    return p


def _perf_rotate(keep=20):
    """Behaelt nur die juengsten <keep> Perf-Logs, loescht aeltere."""
    try:
        d = _perf_logs_dir()
        files = [os.path.join(d, f) for f in os.listdir(d)
                 if f.startswith("perf_") and f.endswith(".txt")]
        files.sort(key=os.path.getmtime, reverse=True)
        for old in files[keep:]:
            try:
                os.remove(old)
            except OSError:
                pass
    except OSError:
        pass


def _migrate_legacy_logs():
    """Verschiebt alte Logs aus dem Root-Verzeichnis in den logs/-Ordner.
    Idempotent: laeuft bei jedem Start, macht aber nur was wenn was zu tun ist.
    """
    _app_dir = app_dir()
    # perf_log.txt -> logs/perf/perf_<mtime>.txt
    old_perf = os.path.join(_app_dir, "perf_log.txt")
    if os.path.exists(old_perf):
        try:
            mtime = _perf_time.localtime(os.path.getmtime(old_perf))
            stamp = _perf_time.strftime("%Y-%m-%d_%H-%M-%S", mtime)
            target = os.path.join(_perf_logs_dir(), f"perf_{stamp}_legacy.txt")
            if not os.path.exists(target):
                os.replace(old_perf, target)
            else:
                os.remove(old_perf)
        except OSError:
            pass
    # crash_*.log -> logs/crashes/
    try:
        crash_target_dir = os.path.join(logs_dir(), "crashes")
        os.makedirs(crash_target_dir, exist_ok=True)
        for name in os.listdir(_app_dir):
            if name.startswith("crash_") and name.endswith(".log"):
                src = os.path.join(_app_dir, name)
                dst = os.path.join(crash_target_dir, name)
                if not os.path.exists(dst):
                    try:
                        os.replace(src, dst)
                    except OSError:
                        pass
    except OSError:
        pass
    # rules/rules.log -> logs/rules.log
    old_rules_log = os.path.join(_app_dir, "rules", "rules.log")
    if os.path.exists(old_rules_log):
        try:
            target = os.path.join(logs_dir(), "rules.log")
            if not os.path.exists(target):
                os.replace(old_rules_log, target)
            else:
                os.remove(old_rules_log)
        except OSError:
            pass
    # system_report.txt -> logs/system_report.txt
    old_sysrep = os.path.join(_app_dir, "system_report.txt")
    if os.path.exists(old_sysrep):
        try:
            target = os.path.join(logs_dir(), "system_report.txt")
            os.replace(old_sysrep, target)
        except OSError:
            pass


def open_perf_file():
    """Oeffnet die Perf-Datei (zeitgestempelt in logs/perf/) und schreibt gepufferte Zeilen."""
    global _PERF_FILE
    if _PERF_FILE:
        return
    try:
        _migrate_legacy_logs()
        _perf_rotate(keep=20)
        stamp = _perf_time.strftime("%Y-%m-%d_%H-%M-%S")
        path = os.path.join(_perf_logs_dir(), f"perf_{stamp}.txt")
        _PERF_FILE = open(path, "w", encoding="utf-8")
        _PERF_FILE.write(f"=== Perf-Log {_perf_time.strftime('%Y-%m-%d %H:%M:%S')} ===\n")
        # System-Header (Version, OS, CPU, RAM, Audio) — macht Logs vergleichbar
        # L2: _PERF_CONFIGURED_DEVICE_IDX uebergeben → Header zeigt BEIDE Latenzen
        try:
            from system_report import generate_compact_header
            for sys_line in generate_compact_header(
                    _APP_VERSION,
                    configured_device_index=_PERF_CONFIGURED_DEVICE_IDX):
                _PERF_FILE.write(sys_line + "\n")
        except Exception as e:
            _PERF_FILE.write(f"[Sys] (Header-Fehler: {e})\n")
        for line in _PERF_LINES:
            _PERF_FILE.write(line + "\n")
        _PERF_FILE.flush()
        _PERF_LINES.clear()
    except OSError:
        pass


def perf_start():
    """Startet eine Zeitmessung. Gibt den Startpunkt zurueck."""
    return _perf_time.perf_counter() if _PERF_ENABLED else 0


def perf_log(label: str, t_start: float, t_end: float = 0):
    """Loggt eine Zeitmessung wenn Performance-Logging aktiv ist."""
    if not _PERF_ENABLED:
        return
    if t_end == 0:
        t_end = _perf_time.perf_counter()
    perf_write(f"[Perf] {label}: {(t_end - t_start)*1000:.0f}ms")


def perf_split(label: str, t_start: float):
    """Loggt und gibt neuen Startpunkt zurueck (fuer Ketten-Messungen)."""
    now = _perf_time.perf_counter() if _PERF_ENABLED else 0
    if _PERF_ENABLED:
        perf_write(f"[Perf] {label}: {(now - t_start)*1000:.0f}ms")
    return now
