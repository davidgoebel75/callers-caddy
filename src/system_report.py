"""System-Report fuer Callers Caddy — Diagnose-Informationen sammeln.

Erzeugt eine system_report.txt mit Hardware-, Software- und
Timing-Informationen zur Fehleranalyse auf verschiedenen Rechnern.
"""

import os
import sys
import platform
import subprocess
from datetime import datetime

from PySide6.QtCore import QTimer, QElapsedTimer, Qt
from PySide6.QtWidgets import QApplication, QProgressDialog


def _collect_os_info():
    """Windows-Version, Build, Architektur."""
    lines = []
    lines.append(f"OS:             {platform.platform()}")
    lines.append(f"OS-Version:     {platform.version()}")
    lines.append(f"Architektur:    {platform.machine()}")
    lines.append(f"Rechnername:    {platform.node()}")
    return lines


def _collect_cpu_info():
    """CPU-Modell, Kerne, Taktrate."""
    lines = []
    lines.append(f"CPU:            {platform.processor()}")

    # Kerne via os
    phys = os.cpu_count()
    lines.append(f"Logische Kerne: {phys}")

    # Detailliertere CPU-Info aus Registry (Windows)
    try:
        import winreg
        key = winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"HARDWARE\DESCRIPTION\System\CentralProcessor\0"
        )
        name, _ = winreg.QueryValueEx(key, "ProcessorNameString")
        mhz, _ = winreg.QueryValueEx(key, "~MHz")
        winreg.CloseKey(key)
        lines.append(f"CPU-Name:       {name.strip()}")
        lines.append(f"CPU-Takt:       {mhz} MHz")
    except Exception:
        pass

    return lines


def _collect_ram_info():
    """RAM gesamt/verfuegbar via Windows Kernel32 API (kein wmic noetig)."""
    lines = []
    try:
        import ctypes
        import ctypes.wintypes

        class MEMORYSTATUSEX(ctypes.Structure):
            _fields_ = [
                ("dwLength", ctypes.wintypes.DWORD),
                ("dwMemoryLoad", ctypes.wintypes.DWORD),
                ("ullTotalPhys", ctypes.c_uint64),
                ("ullAvailPhys", ctypes.c_uint64),
                ("ullTotalPageFile", ctypes.c_uint64),
                ("ullAvailPageFile", ctypes.c_uint64),
                ("ullTotalVirtual", ctypes.c_uint64),
                ("ullAvailVirtual", ctypes.c_uint64),
                ("ullAvailExtendedVirtual", ctypes.c_uint64),
            ]

        mem = MEMORYSTATUSEX()
        mem.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
        ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(mem))
        total_mb = mem.ullTotalPhys // (1024 * 1024)
        avail_mb = mem.ullAvailPhys // (1024 * 1024)
        load = mem.dwMemoryLoad
        lines.append(f"RAM gesamt:     {total_mb} MB")
        lines.append(f"RAM frei:       {avail_mb} MB")
        lines.append(f"RAM-Auslastung: {load}%")
    except Exception as e:
        lines.append(f"RAM:            (Fehler: {e})")
    return lines


def _collect_energy_profile():
    """Aktiver Windows-Energieplan via PowerShell (zuverlaessiger als powercfg)."""
    lines = []
    try:
        # PowerShell-Einzeiler — funktioniert auch auf Win11 26200+
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "(Get-CimInstance -Namespace root/cimv2/power "
             "-ClassName Win32_PowerPlan -Filter \"IsActive=True\")."
             "ElementName"],
            capture_output=True, text=True, timeout=10
        )
        name = result.stdout.strip()
        if name:
            lines.append(f"Energieplan:    {name}")
        else:
            # Fallback: powercfg
            result2 = subprocess.run(
                ["powercfg", "/getactivescheme"],
                capture_output=True, text=True, timeout=10
            )
            output = result2.stdout.strip()
            if "(" in output:
                name = output[output.index("(") + 1:output.rindex(")")]
                lines.append(f"Energieplan:    {name}")
            else:
                lines.append(f"Energieplan:    {output or '(unbekannt)'}")
    except Exception as e:
        lines.append(f"Energieplan:    (Fehler: {e})")
    return lines


def _collect_display_info():
    """Monitore, Aufloesung, DPI-Skalierung."""
    lines = []
    app = QApplication.instance()
    if not app:
        lines.append("Display:        (QApplication nicht verfuegbar)")
        return lines

    screens = app.screens()
    lines.append(f"Monitore:       {len(screens)}")
    for i, screen in enumerate(screens):
        geom = screen.geometry()
        dpr = screen.devicePixelRatio()
        dpi = screen.logicalDotsPerInch()
        phys = screen.physicalSize()
        lines.append(
            f"  Monitor {i + 1}:    {geom.width()}x{geom.height()} @ "
            f"{dpr:.1f}x Skalierung, {dpi:.0f} DPI, "
            f"{phys.width():.0f}x{phys.height():.0f}mm"
        )

    # Qt-Platform
    plat = app.platformName()
    lines.append(f"Qt-Platform:    {plat}")

    return lines


def _collect_gpu_info():
    """GPU-Informationen via PowerShell Get-CimInstance (kein wmic noetig)."""
    lines = []
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "Get-CimInstance Win32_VideoController | "
             "Select-Object Name, DriverVersion, "
             "@{N='VRAM_MB';E={[math]::Round($_.AdapterRAM/1MB)}} | "
             "Format-List"],
            capture_output=True, text=True, timeout=10
        )
        gpus = []
        current = {}
        for line in result.stdout.strip().split("\n"):
            line = line.strip()
            if line.startswith("Name"):
                current["name"] = line.split(":", 1)[1].strip()
            elif line.startswith("DriverVersion"):
                current["driver"] = line.split(":", 1)[1].strip()
            elif line.startswith("VRAM_MB"):
                val = line.split(":", 1)[1].strip()
                current["ram"] = f"{val} MB"
            elif not line and current:
                gpus.append(current)
                current = {}
        if current:
            gpus.append(current)

        if gpus:
            for i, gpu in enumerate(gpus):
                name = gpu.get("name", "?")
                driver = gpu.get("driver", "?")
                ram = gpu.get("ram", "?")
                lines.append(f"GPU {i + 1}:          {name}")
                lines.append(f"  Treiber:      {driver}")
                lines.append(f"  VRAM:         {ram}")
        else:
            # Fallback: Windows Registry
            lines.extend(_collect_gpu_from_registry())
    except Exception as e:
        # Fallback: Windows Registry
        try:
            lines.extend(_collect_gpu_from_registry())
        except Exception as e2:
            lines.append(f"GPU:            (Fehler: {e2})")

    return lines


def _collect_gpu_from_registry():
    """GPU-Info aus der Windows Registry (Fallback)."""
    import winreg
    lines = []
    base = r"SYSTEM\CurrentControlSet\Control\Class" \
           r"\{4d36e968-e325-11ce-bfc1-08002be10318}"
    idx = 0
    while True:
        try:
            key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, f"{base}\\{idx:04d}")
            name, _ = winreg.QueryValueEx(key, "DriverDesc")
            try:
                driver, _ = winreg.QueryValueEx(key, "DriverVersion")
            except FileNotFoundError:
                driver = "?"
            winreg.CloseKey(key)
            lines.append(f"GPU {idx + 1}:          {name}")
            lines.append(f"  Treiber:      {driver}")
            idx += 1
        except OSError:
            break
    if not lines:
        lines.append("GPU:            (keine erkannt)")
    return lines


def _collect_audio_info():
    """Audio-Devices via sounddevice + PortAudio-Version."""
    lines = []
    try:
        import sounddevice as sd

        # PortAudio-Version
        pa = sd.get_portaudio_version()
        lines.append(f"PortAudio:      v{pa[0]} — {pa[1]}")

        # Default Output
        try:
            default = sd.query_devices(kind="output")
            lines.append(f"Audio-Output:   {default['name']}")
            lines.append(f"  Samplerate:   {default['default_samplerate']:.0f} Hz")
            lines.append(
                f"  Latenz:       "
                f"low={default['default_low_output_latency'] * 1000:.1f}ms, "
                f"high={default['default_high_output_latency'] * 1000:.1f}ms"
            )
            lines.append(f"  Max Kanaele:  {default['max_output_channels']}")
        except Exception as e:
            lines.append(f"Audio-Output:   (Fehler: {e})")

        # Alle Output-Devices auflisten
        lines.append("")
        lines.append("  Alle Output-Devices:")
        devices = sd.query_devices()
        for i, dev in enumerate(devices):
            if dev["max_output_channels"] > 0:
                marker = " [DEFAULT]" if dev["name"] == default.get("name") else ""
                lines.append(
                    f"    [{i}] {dev['name']} "
                    f"({dev['default_samplerate']:.0f} Hz, "
                    f"lat={dev['default_low_output_latency'] * 1000:.1f}ms)"
                    f"{marker}"
                )
    except ImportError:
        lines.append("Audio:          sounddevice nicht verfuegbar")
    except Exception as e:
        lines.append(f"Audio:          (Fehler: {e})")

    return lines


def _collect_software_info(app_version):
    """Python, Qt, Library-Versionen."""
    lines = []

    frozen = getattr(sys, 'frozen', False)
    lines.append(f"Callers Caddy:  v{app_version}")
    lines.append(f"Modus:          {'EXE (PyInstaller)' if frozen else 'Python (Source)'}")
    lines.append(f"Python:         {sys.version}")

    try:
        import PySide6
        lines.append(f"PySide6:        {PySide6.__version__}")
    except Exception:
        pass

    try:
        from PySide6.QtCore import qVersion
        lines.append(f"Qt:             {qVersion()}")
    except Exception:
        pass

    try:
        import numpy
        lines.append(f"numpy:          {numpy.__version__}")
    except Exception:
        pass

    try:
        import scipy
        lines.append(f"scipy:          {scipy.__version__}")
    except Exception:
        pass

    try:
        import sounddevice
        lines.append(f"sounddevice:    {sounddevice.__version__}")
    except Exception:
        pass

    try:
        import soundfile
        lines.append(f"soundfile:      {soundfile.__version__}")
    except Exception:
        pass

    return lines


def _measure_timer_jitter(count=200, interval_ms=16):
    """Misst QTimer-Jitter: count Ticks bei interval_ms.

    Gibt (mean, stddev, min, max, einzelwerte) zurueck.
    Blockiert den Event-Loop ueber processEvents().
    """
    results = []
    elapsed = QElapsedTimer()
    state = {"running": True, "last_ns": 0}

    timer = QTimer()
    timer.setTimerType(Qt.PreciseTimer)
    timer.setInterval(interval_ms)

    def on_tick():
        now = elapsed.nsecsElapsed()
        if state["last_ns"] > 0:
            delta_ms = (now - state["last_ns"]) / 1_000_000.0
            results.append(delta_ms)
        state["last_ns"] = now
        if len(results) >= count:
            timer.stop()
            state["running"] = False

    timer.timeout.connect(on_tick)
    elapsed.start()
    timer.start()

    app = QApplication.instance()
    while state["running"]:
        app.processEvents()

    if not results:
        return 0, 0, 0, 0, []

    mean = sum(results) / len(results)
    variance = sum((x - mean) ** 2 for x in results) / len(results)
    stddev = variance ** 0.5
    return mean, stddev, min(results), max(results), results


def generate_compact_header(app_version, configured_device_index=None):
    """Liefert eine kompakte System-Info als Liste von Zeilen mit '[Sys] '-Prefix.

    Schnell (kein Subprocess, kein Timer-Jitter-Messen) — gedacht fuer den
    Header eines Perf-Logs. Subprocess-Quellen (Energieplan, GPU) werden
    bewusst weggelassen, damit der App-Start nicht verzoegert wird.

    configured_device_index: Geraete-Index (int) des in der INI gespeicherten
        Audio-Outputs. Wenn gesetzt und verschieden vom System-Default, wird
        BEIDES ausgegeben — System-Default-Latenz UND konfigurierte Latenz
        (L2, AR-015-Diagnose: verhindert die Verwechslung von MME-Default-
        Latenz mit tatsaechlicher WDM-KS-Latenz im Stream).
    """
    lines = []

    # Software
    frozen = getattr(sys, 'frozen', False)
    lines.append(f"Callers Caddy: v{app_version} ({'EXE' if frozen else 'Source'})")
    try:
        from PySide6.QtCore import qVersion
        import PySide6
        py_short = sys.version.split()[0]
        lines.append(f"Python: {py_short}, PySide6: {PySide6.__version__}, Qt: {qVersion()}")
    except Exception:
        lines.append(f"Python: {sys.version.split()[0]}")

    # OS (cheap)
    try:
        lines.append(f"OS: {platform.platform()}")
    except Exception:
        pass

    # CPU (cheap — Registry oder cpu_count Fallback)
    try:
        import winreg
        key = winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"HARDWARE\DESCRIPTION\System\CentralProcessor\0",
        )
        name, _ = winreg.QueryValueEx(key, "ProcessorNameString")
        mhz, _ = winreg.QueryValueEx(key, "~MHz")
        winreg.CloseKey(key)
        lines.append(
            f"CPU: {name.strip()} @ {mhz} MHz, {os.cpu_count()} logische Kerne"
        )
    except Exception:
        lines.append(f"CPU: {platform.processor()}, {os.cpu_count()} logische Kerne")

    # RAM (cheap — kernel32)
    try:
        import ctypes
        import ctypes.wintypes

        class MEMORYSTATUSEX(ctypes.Structure):
            _fields_ = [
                ("dwLength", ctypes.wintypes.DWORD),
                ("dwMemoryLoad", ctypes.wintypes.DWORD),
                ("ullTotalPhys", ctypes.c_uint64),
                ("ullAvailPhys", ctypes.c_uint64),
                ("ullTotalPageFile", ctypes.c_uint64),
                ("ullAvailPageFile", ctypes.c_uint64),
                ("ullTotalVirtual", ctypes.c_uint64),
                ("ullAvailVirtual", ctypes.c_uint64),
                ("ullAvailExtendedVirtual", ctypes.c_uint64),
            ]

        mem = MEMORYSTATUSEX()
        mem.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
        ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(mem))
        total_mb = mem.ullTotalPhys // (1024 * 1024)
        avail_mb = mem.ullAvailPhys // (1024 * 1024)
        lines.append(
            f"RAM: {total_mb} MB gesamt, {avail_mb} MB frei "
            f"({mem.dwMemoryLoad}% Auslastung)"
        )
    except Exception:
        pass

    # Audio: PortAudio-Version + Default-Output + Hostapi (Diagnose AR-007)
    # L2 (AR-015): System-Default UND konfiguriertes Device ausgeben — verhindert
    # dass Logs "Latenz 90ms (MME-Default)" zeigen obwohl WDM-KS mit 11ms aktiv ist.
    try:
        import sounddevice as sd
        pa = sd.get_portaudio_version()
        lines.append(f"PortAudio: {pa[1]}")

        def _device_info_line(dev, label="Audio-Output"):
            """Erzeugt eine kompakte Zusammenfassung eines Output-Devices."""
            try:
                ha = sd.query_hostapis(dev["hostapi"])["name"]
            except Exception:
                ha = f"#{dev.get('hostapi', '?')}"
            return (
                f"{label}: {dev['name']} ({ha}) "
                f"@ {dev['default_samplerate']:.0f} Hz, "
                f"Latenz low={dev['default_low_output_latency'] * 1000:.1f}ms / "
                f"high={dev['default_high_output_latency'] * 1000:.1f}ms"
            )

        try:
            default = sd.query_devices(kind="output")
            # Robuster Weg den Default-Output-Index zu ermitteln (sounddevice liefert
            # bei query_devices(kind="output") kein "index"-Feld zuverlaessig)
            try:
                default_idx = sd.default.device[1]  # (input_idx, output_idx)
            except Exception:
                default_idx = None
            lines.append(_device_info_line(default, "Audio-Output (System-Default)"))

            # Konfiguriertes Device (aus INI) — falls verschieden vom System-Default
            if configured_device_index is not None and configured_device_index != default_idx:
                try:
                    cfg_dev = sd.query_devices(configured_device_index)
                    lines.append(_device_info_line(cfg_dev, "Audio-Output (konfiguriert)"))
                except Exception as e:
                    lines.append(f"Audio-Output (konfiguriert): idx={configured_device_index} (Info nicht lesbar: {e})")
            elif configured_device_index is not None:
                # Gleicher Index wie System-Default — nur einmal ausgeben, mit Hinweis
                lines.append("Audio-Output (konfiguriert): = System-Default (oben)")

            # Alle verfuegbaren Hostapis auflisten — Diagnose-Hilfe falls Wechsel sinnvoll
            try:
                all_apis = [a["name"] for a in sd.query_hostapis()]
                lines.append(f"Audio-Hostapis verfuegbar: {', '.join(all_apis)}")
            except Exception:
                pass
        except Exception as e:
            lines.append(f"Audio-Output: (Fehler: {e})")
    except Exception:
        lines.append("Audio: sounddevice nicht verfuegbar")

    # Audio-Engine-Konstanten (lazy, optional)
    try:
        import audio_engine as _ae
        lines.append(
            f"Audio-Engine: FEED_AHEAD={_ae.FEED_AHEAD_SECONDS}s, "
            f"PREPROCESS={_ae.PREPROCESS_OUTPUT_SECONDS}s, "
            f"BLOCK={_ae.BLOCK_SIZE}"
        )
    except Exception:
        pass

    return [f"[Sys] {line}" for line in lines]


def generate_report(app_version, app_dir, progress_parent=None):
    """Erzeugt den kompletten System-Report.

    Args:
        app_version: Versionsnummer der App
        app_dir: App-Verzeichnis (fuer Ausgabedatei)
        progress_parent: Parent-Widget fuer Fortschrittsdialog (optional)

    Returns:
        Pfad zur erzeugten Report-Datei
    """
    # Fortschrittsdialog
    progress = None
    if progress_parent:
        progress = QProgressDialog(
            "System-Report wird erstellt...", None, 0, 8, progress_parent
        )
        progress.setWindowTitle("System-Report")
        progress.setWindowModality(Qt.WindowModal)
        progress.setMinimumDuration(0)
        progress.setValue(0)
        QApplication.processEvents()

    sections = []
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def advance(step, label=""):
        if progress:
            progress.setValue(step)
            if label:
                progress.setLabelText(label)
            QApplication.processEvents()

    # Header
    sections.append(f"Callers Caddy — System-Report")
    sections.append(f"Erstellt: {timestamp}")
    sections.append("=" * 60)

    # 1. Software
    advance(1, "Software-Versionen...")
    sections.append("\n[Software]")
    sections.extend(_collect_software_info(app_version))

    # 2. OS
    advance(2, "Betriebssystem...")
    sections.append("\n[Betriebssystem]")
    sections.extend(_collect_os_info())

    # 3. CPU
    advance(3, "CPU...")
    sections.append("\n[CPU]")
    sections.extend(_collect_cpu_info())

    # 4. RAM
    advance(4, "RAM...")
    sections.append("\n[RAM]")
    sections.extend(_collect_ram_info())

    # 5. Energieplan
    sections.append("\n[Energie]")
    sections.extend(_collect_energy_profile())

    # 6. GPU
    advance(5, "GPU...")
    sections.append("\n[GPU]")
    sections.extend(_collect_gpu_info())

    # 7. Display
    advance(6, "Display...")
    sections.append("\n[Display]")
    sections.extend(_collect_display_info())

    # 8. Audio
    advance(7, "Audio-Devices...")
    sections.append("\n[Audio]")
    sections.extend(_collect_audio_info())

    # 9. Timer-Jitter (dauert ~3.5 Sekunden)
    advance(8, "QTimer-Jitter messen (ca. 3 Sek.)...")
    sections.append("\n[QTimer-Jitter]")
    sections.append(f"Test:           200x 16ms-Timer (PreciseTimer)")
    mean, stddev, tmin, tmax, values = _measure_timer_jitter(200, 16)
    sections.append(f"Mittelwert:     {mean:.2f} ms (Soll: 16.00 ms)")
    sections.append(f"Std-Abw.:       {stddev:.2f} ms")
    sections.append(f"Min:            {tmin:.2f} ms")
    sections.append(f"Max:            {tmax:.2f} ms")
    sections.append(f"Jitter (Max-Min): {tmax - tmin:.2f} ms")
    # Histogramm-Buckets
    if values:
        buckets = {}
        for v in values:
            bucket = round(v)
            buckets[bucket] = buckets.get(bucket, 0) + 1
        sections.append(f"Verteilung:")
        for ms in sorted(buckets.keys()):
            bar = "#" * buckets[ms]
            sections.append(f"    {ms:3d}ms: {bar} ({buckets[ms]}x)")

    # Footer
    sections.append("\n" + "=" * 60)
    sections.append("Ende des Reports")

    # Datei schreiben — seit v0.91 in logs/, mit robustem Fallback
    report_text = "\n".join(sections) + "\n"
    logs_dir = os.path.join(app_dir, "logs")
    try:
        os.makedirs(logs_dir, exist_ok=True)
        output_path = os.path.join(logs_dir, "system_report.txt")
    except OSError:
        output_path = os.path.join(app_dir, "system_report.txt")
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(report_text)

    if progress:
        progress.close()

    return output_path
