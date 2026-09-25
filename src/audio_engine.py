"""
Audio-Engine
==============
Wiederverwendbare Audio-Engine mit Tempo, Pitch, Loop und Seek.
Ab P16: Heutiges Tempo (Session-Faktor) getrennt vom Song-Tempo.
"""

import os
import sys
import time
import platform
import collections
import numpy as np
import threading

# --- Native Audio-Bibliotheken abgesichert laden ---------------------------
# soundfile (libsndfile) und sounddevice (PortAudio) laden native DLLs. Auf
# manchen Zielrechnern schlaegt das fehl, z.B. weil der Virenscanner die DLL
# blockiert/in Quarantaene verschiebt oder die heruntergeladene ZIP vor dem
# Entpacken nicht "zugelassen" wurde (Windows Mark-of-the-Web). Frueher riss
# dieser Import die komplette App mit einem rohen Python-Traceback ab — und
# zwar BEVOR ueberhaupt ein Qt-Fenster existierte, sodass kein verstaendlicher
# Hinweis moeglich war. Jetzt fangen wir den Fehler ab und merken ihn uns;
# main.py prueft das beim Start und zeigt einen Klartext-Dialog mit Loesungsweg.
AUDIO_IMPORT_ERROR = None
try:
    import soundfile as sf
    import sounddevice as sd
except Exception as _audio_exc:  # OSError (DLL nicht ladbar), ImportError, ...
    sf = None
    sd = None
    AUDIO_IMPORT_ERROR = _audio_exc


def audio_backend_available():
    """True, wenn sounddevice/soundfile inkl. ihrer nativen DLLs geladen sind."""
    return sd is not None and sf is not None


def format_audio_import_error():
    """Baut (Titel, Klartext-Nachricht) fuer den Fehlerdialog beim Start.

    Erkennt den haeufigsten Fall (PortAudio/libsndfile-DLL konnte nicht geladen
    werden) und erklaert dem Endnutzer in einfacher Sprache, was zu tun ist —
    statt ihm den rohen Traceback ('error 0x7e') zu zeigen.
    """
    title = "Audio-System konnte nicht geladen werden"
    detail = str(AUDIO_IMPORT_ERROR) if AUDIO_IMPORT_ERROR else "Unbekannter Fehler"
    msg = (
        "Callers Caddy konnte die Audio-Komponente (PortAudio) nicht laden und "
        "kann ohne sie nicht starten.\n\n"
        "Das liegt fast immer am Rechner, nicht am Programm — meist an einer "
        "dieser zwei Ursachen:\n\n"
        "  •  Der Virenscanner hat die Datei 'libportaudio64bit.dll' blockiert "
        "oder in die Quarantäne verschoben.\n"
        "  •  Die heruntergeladene ZIP-Datei wurde vor dem Entpacken nicht "
        "\"zugelassen\" (Windows-Sperre / Mark-of-the-Web).\n\n"
        "So beheben Sie es:\n\n"
        "  1.  Im Virenscanner nachsehen, ob Callers Caddy bzw. "
        "'libportaudio64bit.dll' blockiert wurde — wiederherstellen und den "
        "Programmordner als Ausnahme eintragen.\n"
        "  2.  Falls nichts blockiert ist: die Original-ZIP erneut herunterladen, "
        "vor dem Entpacken per Rechtsklick → Eigenschaften → \"Zulassen\" "
        "freigeben, dann komplett neu entpacken und starten.\n\n"
        "Eine ausführliche Diagnosedatei wurde im Ordner 'logs\\crashes' abgelegt — "
        "bitte diese bei einer Rückfrage an den Support schicken.\n\n"
        "── Technische Details (für den Support) ──────────────\n"
        f"{detail}"
    )
    return title, msg


def _portaudio_candidate_paths():
    """Erwartete Speicherorte der PortAudio-DLL — ohne sounddevice zu importieren.

    Wir koennen das Paket trotzdem lokalisieren (find_spec laedt die native DLL
    NICHT), bzw. im gefrorenen Build liegt sie unter _MEIPASS.
    """
    paths = []
    rel = os.path.join("_sounddevice_data", "portaudio-binaries",
                       "libportaudio64bit.dll")
    # Gefrorener PyInstaller-Build (onedir): DLLs unter _internal (_MEIPASS)
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        paths.append(os.path.join(meipass, rel))
    # Dev / pip-Installation: Speicherort ueber find_spec (laedt keine DLL).
    # _sounddevice_data liegt je nach Layout NEBEN sounddevice.py (Einzelmodul,
    # so bei 0.5.x) ODER eine Ebene hoeher (Paket-Layout) — beide Orte pruefen.
    try:
        import importlib.util
        spec = importlib.util.find_spec("sounddevice")
        if spec and spec.origin:
            d = os.path.dirname(spec.origin)
            paths.append(os.path.join(d, rel))
            paths.append(os.path.join(os.path.dirname(d), rel))
    except Exception:
        pass
    # Duplikate raus, Reihenfolge erhalten
    seen, unique = set(), []
    for p in paths:
        if p not in seen:
            seen.add(p)
            unique.append(p)
    return unique


def collect_audio_diagnostics():
    """Sammelt Diagnose-Zeilen, wenn das Audio-Backend nicht geladen werden konnte.

    Ziel: die ECHTE Ursache unterscheidbar machen, die der Windows-Fehlercode
    126 (0x7e) selbst verschweigt:
      • DLL FEHLT  → vom Virenscanner geloescht / in Quarantaene.
      • DLL DA, laedt aber nicht → blockiert (Mark-of-the-Web / aktiver
        Zugriffsschutz des Virenscanners).
    """
    app_dir = (os.path.dirname(sys.executable)
               if getattr(sys, "frozen", False) else os.getcwd())
    lines = []
    lines.append(f"Python:    {sys.version.split()[0]} ({platform.machine()})")
    lines.append(f"Plattform: {platform.platform()}")
    lines.append(f"Frozen:    {getattr(sys, 'frozen', False)}")
    lines.append(f"App-Dir:   {app_dir}")
    lines.append("")

    # --- Region/Locale-Pruefung: Non-ASCII-Pfad = haeufige Ursache fuer 0x7e --
    # sounddevice/CFFI laedt die DLL ueber die ANSI-Variante von LoadLibrary;
    # Zeichen ausserhalb der System-Codepage (z.B. tschechische/deutsche
    # Diakritika im Benutzernamen) lassen das Laden mit Fehler 126 scheitern.
    lines.append("Region / Pfad-Kodierung:")
    non_ascii = [c for c in app_dir if ord(c) > 127]
    if non_ascii:
        lines.append(f"  ⚠ App-Pfad enthaelt Nicht-ASCII-Zeichen: {''.join(sorted(set(non_ascii)))}")
        lines.append("    → SEHR WAHRSCHEINLICHE URSACHE des DLL-Ladefehlers (0x7e).")
        lines.append("    → Abhilfe: App in einen reinen ASCII-Pfad verschieben,")
        lines.append("      z.B. C:\\Callers_Caddy (nicht unter C:\\Users\\<Name mit Sonderzeichen>).")
    else:
        lines.append("  App-Pfad ist reines ASCII (Pfad-Kodierung als Ursache unwahrscheinlich).")
    try:
        import locale
        import ctypes
        acp = ctypes.windll.kernel32.GetACP()
        lines.append(f"  Windows ANSI-Codepage (GetACP): {acp}")
        lines.append(f"  Bevorzugte Locale-Kodierung:    {locale.getpreferredencoding(False)}")
        # 8.3-Kurzpfad verfuegbar? Fehlt er bei Non-ASCII-Pfad, ist 126 quasi sicher.
        buf = ctypes.create_unicode_buffer(260)
        if ctypes.windll.kernel32.GetShortPathNameW(app_dir, buf, 260):
            short = buf.value
            same = (short == app_dir)
            lines.append(f"  8.3-Kurzpfad: {short}" + ("  (identisch — kein Kurzname)" if same else ""))
    except Exception as _e:
        lines.append(f"  (Codepage/Kurzpfad nicht ermittelbar: {_e})")
    lines.append("")

    # Vollstaendige Fehlerkette — die unterste (CFFI-)Ebene nennt DLL-Pfad + 0x7e
    lines.append("Fehlerkette beim Import (sounddevice/soundfile):")
    exc, seen = AUDIO_IMPORT_ERROR, 0
    if exc is None:
        lines.append("  (kein Fehler gespeichert — Backend war verfuegbar?)")
    while exc is not None and seen < 6:
        lines.append(f"  {type(exc).__name__}: {exc}")
        exc = exc.__cause__ or exc.__context__
        seen += 1
    lines.append("")

    # PortAudio-DLL physisch pruefen — DAS ist das entscheidende Signal
    lines.append("PortAudio-DLL (libportaudio64bit.dll):")
    found_any = False
    for p in _portaudio_candidate_paths():
        if os.path.exists(p):
            found_any = True
            try:
                size = os.path.getsize(p)
            except OSError:
                size = -1
            lines.append(f"  VORHANDEN  {p}")
            lines.append(f"             Groesse={size} Bytes, lesbar={os.access(p, os.R_OK)}")
        else:
            lines.append(f"  FEHLT      {p}")
    if not found_any:
        lines.append("  → DLL an keinem erwarteten Ort gefunden:")
        lines.append("    deutet auf QUARANTAENE/LOESCHUNG durch den Virenscanner hin.")
    else:
        lines.append("  → DLL ist vorhanden. Scheitert das Laden trotzdem, deutet das")
        lines.append("    auf eine BLOCKADE hin (Mark-of-the-Web / Virenscanner-Zugriffsschutz).")
    return lines

from time_stretcher import StreamingTimeStretcher
from pitch_shifter import PitchShifter

# pycaw: per-App-Volume ueber Windows WASAPI (artefaktfrei, ausserhalb des Streams)
try:
    from pycaw.pycaw import AudioUtilities, ISimpleAudioVolume
    _PYCAW_AVAILABLE = True
except ImportError:
    _PYCAW_AVAILABLE = False


FEED_AHEAD_SECONDS = 5.0
BLOCK_SIZE = 1024
RESAMPLE_BLOCK_SIZE = 8192
WSOLA_WINDOW_SIZE = 8192
LOOP_XFADE_FRAMES = 2048     # Default ~46ms bei 44100 Hz — PCM-Crossfade am Loop-Uebergang
PREPROCESS_OUTPUT_SECONDS = 1.0   # Fix B (AR-020): 0.25 → 1.0 — groessere Output-Polster-Reserve,
                                  # damit Lock-Hold-Spitzen den 11ms-WDM-KS-Hardware-Buffer nicht mehr trifft.

# --- Anti-Ruckler-Schalter (siehe docs/anti_ruckler_backlog.md) -------------
MMCSS_ENABLED = True   # AR-009: Feeder-Thread auf MMCSS "Pro Audio" hochstufen
LOG_UNDERFLOWS = True  # AR-010: Callback-Underflow-Events ins Perf-Log schreiben

# --- Diag-Logger-Hook -------------------------------------------------------
# Wird von main.py ueberschrieben, damit [Diag]-Zeilen ins gestempelte perf_log
# wandern. Default: print (funktioniert ohne main.py-Abhaengigkeit).
_diag_log = print

def set_diag_logger(fn):
    """Erlaubt main.py, [Diag]-Zeilen ins Perf-Log umzuleiten."""
    global _diag_log
    _diag_log = fn


def _apply_mmcss_pro_audio():
    """Hebt den aktuellen Thread auf MMCSS 'Pro Audio' Prioritaet (Windows).

    Loest AR-009: PortAudio gibt seinem eigenen Callback-Thread MMCSS-Prio,
    aber unser Python-Feeder-Daemon laeuft mit normaler Prioritaet. Damit
    bevorzugt der Windows-Scheduler den UI-Thread, und der Feeder hungert
    bei Last (auch ohne GIL-Effekt). Mit MMCSS "Pro Audio" steht der Feeder
    ueber UI-Threads im Scheduler.

    Returns: (success: bool, message: str) — Caller loggt das Ergebnis.
    """
    try:
        import ctypes
        avrt = ctypes.WinDLL("avrt.dll")
        avrt.AvSetMmThreadCharacteristicsW.argtypes = [
            ctypes.c_wchar_p, ctypes.POINTER(ctypes.c_ulong)
        ]
        avrt.AvSetMmThreadCharacteristicsW.restype = ctypes.c_void_p
        task_idx = ctypes.c_ulong(0)
        handle = avrt.AvSetMmThreadCharacteristicsW(
            "Pro Audio", ctypes.byref(task_idx)
        )
        if not handle:
            err = ctypes.get_last_error()
            return False, f"AvSetMmThreadCharacteristicsW failed (GetLastError={err})"
        return True, f"MMCSS 'Pro Audio' aktiv (task_idx={task_idx.value})"
    except Exception as e:
        return False, f"MMCSS nicht verfuegbar: {e}"


def compute_loop_offset(audio_data, sample_rate, loop_in, loop_out):
    """Headless-Kern der Loop-Offset-Messung (Tiefpass-Kreuzkorrelation <200Hz).

    Vergleicht nur die tiefen Frequenzen (<200Hz, Bassdrum/Bass) am Loop-Ende
    mit dem Loop-Anfang, Suchbereich +-2s. loop_in/loop_out in Samples.

    Returns (apply_offset_samples, apply_ms, correlation) oder None. Der Offset
    ist bereits vorzeichen-korrigiert: positiver Offset = loop_out verlaengern.
    Ohne Engine-Zustand nutzbar (z.B. im Bulk-BeatSnap-Worker, BL-172)."""
    from scipy.signal import butter, sosfiltfilt, correlate

    if audio_data is None or not sample_rate:
        return None
    if loop_out <= loop_in:
        return None

    window = int(0.5 * sample_rate)
    search = int(2.0 * sample_rate)

    data = audio_data
    if data.ndim > 1:
        data = data.mean(axis=1)

    filter_margin = int(0.05 * sample_rate)
    ref_start = max(0, loop_out - window - filter_margin)
    ref_end = min(loop_out + filter_margin, len(data))
    cand_start = max(0, loop_in - search - filter_margin)
    cand_end = min(len(data), loop_in + window + search + filter_margin)

    ref_region = data[ref_start:ref_end]
    cand_region = data[cand_start:cand_end]
    if len(ref_region) < window or len(cand_region) < window:
        return None

    cutoff = 200.0
    nyquist = sample_rate / 2.0
    sos = butter(4, cutoff / nyquist, btype='low', output='sos')
    ref_lp = sosfiltfilt(sos, ref_region)
    cand_lp = sosfiltfilt(sos, cand_region)

    ref_offset = loop_out - ref_start - filter_margin
    ref = ref_lp[ref_offset - window:ref_offset]
    if len(ref) < window:
        ref = ref_lp[-window - filter_margin:-filter_margin]
    if len(ref) < window:
        return None

    ref_norm = ref - ref.mean()
    ref_energy = np.sqrt(np.sum(ref_norm ** 2))
    if ref_energy < 1e-10:
        return None

    loop_in_idx = loop_in - cand_start
    cand_slice_start = max(0, loop_in_idx - search)
    cand_slice_end = min(len(cand_lp), loop_in_idx + window + search)
    cand_slice = cand_lp[cand_slice_start:cand_slice_end]
    if len(cand_slice) < window:
        return None

    corr_raw = correlate(cand_slice, ref_norm, mode='valid')
    cand_centered = cand_slice - np.mean(cand_slice)
    sq = cand_centered ** 2
    cumsum = np.concatenate([[0], np.cumsum(sq)])
    local_energy = np.sqrt(cumsum[window:] - cumsum[:-window])
    denom = ref_energy * local_energy
    denom[denom < 1e-10] = 1e-10
    corr_normalized = corr_raw / denom

    global_max = float(np.max(corr_normalized))
    threshold = max(0.1, global_max * 0.5)
    offsets = np.arange(len(corr_normalized)) + cand_slice_start - loop_in_idx
    good_mask = corr_normalized >= threshold
    if not np.any(good_mask):
        return None
    good_offsets = offsets[good_mask]
    good_corrs = corr_normalized[good_mask]
    closest_idx = np.argmin(np.abs(good_offsets))
    best_offset = int(good_offsets[closest_idx])
    best_corr = float(good_corrs[closest_idx])
    offset_ms = best_offset / sample_rate * 1000

    # Vorzeichen invertieren (siehe measure_loop_offset).
    return (-best_offset, -offset_ms, best_corr)


class AudioEngine:
    """Audio-Engine mit Tempo, Pitch, Loop und Seek."""

    def __init__(self):
        self.audio_data = None
        self.sample_rate = None
        self.channels = None
        self.playing = False
        self.paused = False
        self.stream = None
        self.stretcher = None
        self.pitcher = None

        # Stream-Konfiguration (um unnoetige Neustart zu vermeiden)
        self._stream_sr = None
        self._stream_ch = None
        self._stream_device = None  # Tatsaechlich verwendetes Geraet (nach Fallback-Aufloesung)
        self._stream_exclusive = False  # War der letzte Stream im WASAPI-Exclusive-Modus?
        # Fallback-Cache: {requested_device → effective_device} wenn WASAPI-Init in dieser
        # Session fehlgeschlagen ist. Verhindert erneuten WASAPI-Versuch z.B. nach Audition.
        self._device_fallback: dict = {}

        # Device-Recovery: Zeitstempel des letzten Wiederherstellungsversuchs
        self._last_recovery_attempt = 0.0
        # Gewaehltes Ausgabegeraet (None = System-Standard, int = sd-Geraete-Index)
        self._output_device = None
        # AR-008: WASAPI Exclusive Mode (umgeht den Shared-Mode-Glitch, PortAudio #303).
        # Greift nur, wenn das aktuelle Device ein WASAPI-Device ist; sonst ignoriert.
        self._wasapi_exclusive = False

        self._feed_pos = 0
        self._user_tempo = 1.0      # Song-Tempo (per-Song, gespeichert)
        self._today_tempo = 1.0     # Heutiges Tempo (Session-Faktor)
        self._lock = threading.Lock()

        # Feeder-Thread: hält den Stretcher-Input-Buffer gefüllt,
        # unabhängig vom UI-Main-Thread
        self._feeder_stop = threading.Event()
        self._feeder_thread = threading.Thread(
            target=self._feeder_loop, daemon=True, name="AudioFeeder")
        self._feeder_thread.start()

        self._loop_in = 0
        self._loop_out = 0
        self._loop_active = False

        # Song-Volume (multiplikativer Faktor, 0.0–1.0, persistent per Song)
        # Smooth-Rampe: _song_volume gleitet zu _song_volume_target
        # Ramp-Rate: max. Aenderung pro Sample (~50ms fuer 0→1 @44100Hz)
        self._song_volume = 1.0
        self._song_volume_target = 1.0
        self._volume_ramp_rate = 1.0 / (0.05 * 44100)  # ~0.00045/Sample

        # Live-Volume: per-App WASAPI (artefaktfrei, Session-Faktor, nicht persistent)
        self._live_volume = 1.0          # aktueller Wert (0.0–1.0)
        self._min_volume = 0.0           # Mindest-Boden (aus INI)
        self._wasapi_session = None      # gecachte ISimpleAudioVolume-Instanz
        self._wasapi_pid = os.getpid()

        # Fade-Out
        self._fade_volume = 1.0
        self._fade_step = 0.0     # Abnahme pro Sample-Frame
        self._fading = False

        # WSOLA-Warmup: erste Hops verarbeiten aber nicht ausgeben
        self._warmup_frames = 0

        # Loop-Crossfade: Nahtloser Uebergang ohne flush()/warmup.
        # Am Loop-Ende werden die letzten LOOP_XFADE_FRAMES Samples
        # mit den ersten Samples von loop_in ueberblendet (raw PCM).
        # WSOLA bekommt dadurch keinen harten Sprung im Input.
        self._loop_xfade_skip = 0   # Samples am loop_in die uebersprungen werden (bereits eingeblendet)
        self._loop_xfade_frames = LOOP_XFADE_FRAMES  # Konfigurierbar via set_loop_crossfade_ms()
        self._loop_offset_frames = 0  # Pro Song, via set_loop_offset_ms() oder measure_loop_offset()
        # BL-164: Anzahl Samples, um die EIN Loop-Durchlauf (der erste) verkuerzt
        # wird, damit die Gesamt-Patterlaenge naeher an die Wunschzeit kommt.
        # 0 = kein Cut → identisches Loop-Verhalten wie bisher.
        self._loop_cut_frames = 0

        # Playback-Zaehler: Zaehlt tatsaechlich ausgegebene Samples im Callback.
        # Wird bei play()/seek() auf die aktuelle Position gesetzt.
        # Praeziseste Quelle fuer die tatsaechliche Wiedergabe-Position
        # (im Gegensatz zu _feed_pos, das dem Audio vorauseilt).
        self._playback_sample = 0
        # Anzeige-Glaettung: letzter von _estimate_playback_pos gelieferter Wert.
        # Unterdrueckt Mini-Rueckspruenge (~1s) beim Estimator-Wechsel am loop_in
        # (Puffer-Differenz zwischen Feed-Schaetzung und Playback-Zaehler).
        # None = kein Vorwert (nach Load/Seek/Stop).
        self._display_pos_guard = None

        # Audio-Buffer-Diagnostik
        # _diag_buf_ms:    Output-Buffer-Stand in ms beim letzten Callback (atomar geschrieben)
        # _diag_xruns:     PortAudio-Underflows seit letztem reset_diag()
        # _diag_history:   deque von (timestamp, buf_ms) fuer Rolling-Min (letzte 10s)
        self._diag_buf_ms = 0.0
        self._diag_xruns = 0
        self._diag_history = collections.deque()  # (t, buf_ms)
        # AR-010: Underflow-Events sammeln (im Callback befuellt, vom Feeder geleert + geloggt)
        # Tuple: (wallclock_str, buf_ms_at_underflow, frames, was_warmup)
        self._underflow_events = collections.deque(maxlen=200)
        # AR-020 T1: Frame-Count-Sampling der ersten N Callbacks pro Stream.
        # WDM-KS-Verdacht: liefert unregelmaessige Block-Groessen → hoerbare Wackler.
        # Wird im Callback befuellt (nur Append, sehr billig), vom Feeder als
        # Histogramm geloggt sobald voll. _frame_samples_done verhindert Doppel-Logs.
        self._frame_samples = []
        self._frame_samples_done = False
        self._frame_samples_target = 200

        # Loop-Count: 0 = Endlos (Standard), N = Anzahl Loops dann weiter bis Song-Ende
        self._loop_count_target = 0   # Gewuenschte Anzahl Loops (0=endlos)
        self._loop_count_done = 0     # Bereits durchlaufene Loops

        # Callback fuer Song-Ende (UI kann sich registrieren)
        self.on_song_finished = None
        # Callback fuer Song geladen
        self.on_song_loaded = None

        # BL-137: Alert-Sound (Timer-Ueberzug). Wird in den laufenden Stream
        # gemischt — gleicher Output-Stream, gleiches Geraet. Default AUS
        # (None). Wenn aktiv: _alert_data = float32 (n_frames, channels),
        # _alert_pos = naechstes Frame zum Abspielen.
        self._alert_data = None
        self._alert_pos = 0
        self._alert_volume = 1.0

        # Output-Capture (nur fuer Diagnose-Tools, Default AUS).
        # Wenn _capture_buf nicht None ist, schreibt der Callback jeden Output-Block
        # in den vorallokierten Ringspeicher. Im Normalbetrieb ein einziger
        # `is None`-Check pro Callback — keine Perf-Auswirkung.
        self._capture_buf = None          # np.ndarray (n_frames, channels) oder None
        self._capture_pos = 0
        self._capture_full = False
        self._capture_events = []         # Liste (sample_index, tag) — vom Tool gefuellt

    def play_alert(self, samples, volume: float = 1.0):
        """BL-137: Alert-Sound in den laufenden Audio-Stream einmischen.

        Wird im Callback nach dem Song-Output additiv addiert (Clip-Schutz auf [-1, 1]).
        Identisches Ausgabegerät wie der Song — keine zweiten Streams.

        Args:
            samples: np.ndarray (n_frames,) Mono oder (n_frames, channels) Stereo, float32
            volume:  Lautstärke-Faktor (0.0–1.0+)
        """
        if samples is None or len(samples) == 0:
            return
        arr = np.asarray(samples, dtype=np.float32)
        if arr.ndim == 1:
            # Mono → auf Stream-Kanalzahl duplizieren
            n_ch = self.channels or 2
            arr = np.repeat(arr.reshape(-1, 1), n_ch, axis=1)
        elif arr.ndim == 2 and self.channels and arr.shape[1] != self.channels:
            # Kanal-Mismatch: Stereo→Mono oder Mono→Stereo umwandeln
            if arr.shape[1] == 1 and self.channels >= 2:
                arr = np.repeat(arr, self.channels, axis=1)
            elif arr.shape[1] >= 2 and self.channels == 1:
                arr = arr.mean(axis=1, keepdims=True)
            else:
                # Best-Effort: linke Kanaele nehmen / mit Nullen auffuellen
                if arr.shape[1] > self.channels:
                    arr = arr[:, : self.channels]
                else:
                    pad = np.zeros((len(arr), self.channels - arr.shape[1]), dtype=np.float32)
                    arr = np.concatenate([arr, pad], axis=1)
        self._alert_data = arr
        self._alert_pos = 0
        self._alert_volume = max(0.0, float(volume))

    def stop_alert(self):
        """Aktiven Alert-Sound vorzeitig abbrechen."""
        self._alert_data = None
        self._alert_pos = 0

    def start_output_capture(self, seconds: float):
        """Aktiviert Output-Capture fuer Diagnose-Tools.

        Reserviert einen Ring-Buffer mit `seconds * sample_rate` Frames.
        Der Audio-Callback schreibt jeden ausgegebenen Block hinein, bis voll.
        NICHT im Normalbetrieb verwenden — nur fuer Pitch-/Tempo-Transition-Tests.
        """
        if self.sample_rate is None or self.channels is None:
            raise RuntimeError("start_output_capture: erst load() aufrufen")
        n = int(seconds * self.sample_rate)
        self._capture_buf = np.zeros((n, self.channels), dtype=np.float32)
        self._capture_pos = 0
        self._capture_full = False
        self._capture_events = []

    def capture_mark(self, tag: str):
        """Setzt einen Zeitstempel auf der Capture-Zeitachse (Sample-Index + Tag)."""
        if self._capture_buf is not None:
            self._capture_events.append((self._capture_pos, tag))

    def stop_output_capture(self):
        """Stoppt Capture und liefert (samples, sample_rate, events).

        samples: np.ndarray (n_used, channels) float32 — nur die tatsaechlich gefuellten Frames.
        """
        if self._capture_buf is None:
            return None, self.sample_rate, []
        buf = self._capture_buf[: self._capture_pos].copy()
        events = list(self._capture_events)
        self._capture_buf = None
        self._capture_pos = 0
        self._capture_full = False
        self._capture_events = []
        return buf, self.sample_rate, events

    def load(self, filepath):
        # playing=False ZUERST setzen — Callback gibt dann nur noch Stille aus,
        # bevor wir den Stretcher austauschen (Race-Condition vermeiden)
        self.playing = False
        self.paused = False
        self._fading = False
        self._fade_volume = 1.0
        self._fade_step = 0.0

        data, sr = sf.read(filepath, dtype='float32')
        if data.ndim == 1:
            data = data.reshape(-1, 1)

        # Neuen Stretcher + Pitcher VORHER vorbereiten
        new_stretcher = StreamingTimeStretcher(
            channels=data.shape[1],
            sample_rate=sr,
            window_size=WSOLA_WINDOW_SIZE,
            search_range=512
        )
        new_pitcher = PitchShifter(
            channels=data.shape[1],
            sample_rate=sr
        )

        # Erst jetzt alle Felder atomar aktualisieren (unter Lock, damit
        # der Feeder-Thread nicht mitten im _feed_stretcher mit halb-altem
        # State arbeitet)
        with self._lock:
            self.audio_data = data
            self.sample_rate = sr
            self.channels = data.shape[1]
            self._feed_pos = 0
            self._playback_sample = 0
            self._display_pos_guard = None  # Anzeige-Glaettung zuruecksetzen
            self._user_tempo = 1.0
            # _today_tempo wird NICHT zurueckgesetzt (Session-Wert!)
            self._loop_in = 0
            self._loop_out = len(data)
            self._loop_active = False
            self._loop_count_target = 0
            self._loop_count_done = 0
            self._loop_cut_frames = 0  # BL-164: Cut nicht auf neuen Song vererben
            self.stretcher = new_stretcher
            self.pitcher = new_pitcher

        duration = data.shape[0] / sr

        # Song-Wechsel ins Perf-Log — erleichtert spaetere Forensik bei Aussetzern,
        # SR-MISMATCH, Stream-Reopens usw. (welche Datei war's eigentlich?)
        import os as _os
        _diag_log(
            f"[Diag] Song geladen: '{_os.path.basename(filepath)}' "
            f"sr={sr}Hz ch={data.shape[1]} dur={duration:.1f}s "
            f"pfad='{_os.path.abspath(filepath)}'"
        )

        if self.on_song_loaded:
            self.on_song_loaded(filepath, duration)

        return duration

    @property
    def loop_in_seconds(self):
        if self.sample_rate:
            return self._loop_in / self.sample_rate
        return 0.0

    @property
    def loop_out_seconds(self):
        if self.sample_rate and self.audio_data is not None:
            return self._loop_out / self.sample_rate
        return 0.0

    def set_loop_in(self, seconds):
        """Setzt Loop-In auf eine bestimmte Position in Sekunden."""
        if self.sample_rate:
            self._loop_in = max(0, int(seconds * self.sample_rate))
            if self._loop_in >= self._loop_out:
                self._loop_in = max(0, self._loop_out - int(self.sample_rate))

    def set_loop_out(self, seconds):
        """Setzt Loop-Out auf eine bestimmte Position in Sekunden."""
        if self.sample_rate and self.audio_data is not None:
            self._loop_out = min(len(self.audio_data),
                                 int(seconds * self.sample_rate))
            if self._loop_out <= self._loop_in:
                self._loop_out = min(len(self.audio_data),
                                     self._loop_in + int(self.sample_rate))

    def set_loop_in_at_current(self):
        pos = self._estimate_playback_pos()
        self._loop_in = max(0, pos)
        if self._loop_in >= self._loop_out:
            self._loop_in = max(0, self._loop_out - int(self.sample_rate))

    def set_loop_out_at_current(self):
        pos = self._estimate_playback_pos()
        if self.audio_data is not None:
            self._loop_out = min(len(self.audio_data), pos)
        if self._loop_out <= self._loop_in:
            self._loop_out = min(len(self.audio_data),
                                 self._loop_in + int(self.sample_rate))

    def set_loop_active(self, active):
        self._loop_active = bool(active)
        if active:
            self._loop_count_done = 0  # Bei Aktivierung Zaehler zuruecksetzen

    def set_loop_count(self, count):
        """Loop-Anzahl setzen. 0 = Endlos (Standard), N = nach N Loops weiterspielen."""
        self._loop_count_target = max(0, int(count))
        self._loop_count_done = 0

    def set_loop_cut_seconds(self, seconds):
        """BL-164: Kuerzt EINEN (den ersten) Loop-Durchlauf um 'seconds', damit die
        Gesamt-Patterlaenge naeher an die Wunschzeit kommt. 0 = kein Cut.

        Greift nur bei loop_count_target >= 2 (es braucht einen inneren Durchlauf;
        der letzte Durchlauf bleibt voll, damit der Ausstieg loop_out->Tail
        unveraendert bleibt). Die Sekunden entstehen aus (cut_beats * 60/bpm) im
        Aufrufer, das Beat-Raster (64/32) haelt den Ruecksprung phrasen-sauber.
        """
        with self._lock:
            self._loop_cut_frames = max(0, int(seconds * self.sample_rate))

    @property
    def loop_count_target(self):
        return self._loop_count_target

    @property
    def loop_count_done(self):
        return self._loop_count_done

    @property
    def loop_count_remaining(self):
        if self._loop_count_target <= 0:
            return -1  # Endlos
        return max(0, self._loop_count_target - self._loop_count_done)

    def set_loop_crossfade_ms(self, ms):
        """Crossfade-Dauer am Loop-Uebergang in Millisekunden setzen."""
        if self.sample_rate:
            self._loop_xfade_frames = max(0, int(ms * self.sample_rate / 1000))
        else:
            self._loop_xfade_frames = max(0, int(ms * 44100 / 1000))

    def set_loop_offset_ms(self, ms):
        """Loop-Offset in Millisekunden setzen.

        Positiv = spaeter springen (Loop laeuft laenger),
        Negativ = frueher springen (Loop wird kuerzer).
        """
        if self.sample_rate:
            self._loop_offset_frames = int(ms * self.sample_rate / 1000)
        else:
            self._loop_offset_frames = int(ms * 44100 / 1000)

    def snap_loop_to_beats(self, beat_times):
        """Snappt Loop-In und Loop-Out auf den naechsten Beat.

        Args:
            beat_times: numpy-Array mit Beat-Zeitpunkten in Sekunden

        Returns:
            (new_in_seconds, new_out_seconds) oder None bei Fehler
        """
        import numpy as np
        print(f"[Engine.snap] audio={'ja' if self.audio_data is not None else 'NEIN'}, sr={self.sample_rate}, beats={len(beat_times)}")
        if self.audio_data is None or self.sample_rate is None:
            print("[Engine.snap] ABBRUCH: Kein Audio geladen")
            return None
        if len(beat_times) < 2:
            print("[Engine.snap] ABBRUCH: Weniger als 2 Beats")
            return None

        in_sec = self.loop_in_seconds
        out_sec = self.loop_out_seconds
        print(f"[Engine.snap] Aktuelle Positionen: In={in_sec:.3f}s, Out={out_sec:.3f}s")

        # Naechsten Beat fuer Loop-In finden
        idx_in = np.argmin(np.abs(beat_times - in_sec))
        new_in = beat_times[idx_in]

        # Naechsten Beat fuer Loop-Out finden
        idx_out = np.argmin(np.abs(beat_times - out_sec))
        new_out = beat_times[idx_out]

        print(f"[Engine.snap] Snap-Ziel: In={new_in:.3f}s (Beat #{idx_in}), Out={new_out:.3f}s (Beat #{idx_out})")

        # Sicherstellen dass Out > In mit mindestens 1 Sekunde Abstand
        if new_out <= new_in + 1.0:
            # Naechsten Beat NACH new_in + 1s suchen
            candidates = beat_times[beat_times > new_in + 1.0]
            if len(candidates) > 0:
                new_out = candidates[np.argmin(np.abs(candidates - out_sec))]
                print(f"[Engine.snap] Out korrigiert auf {new_out:.3f}s (min 1s Abstand)")
            else:
                print("[Engine.snap] ABBRUCH: Kein gueltiger Snap moeglich")
                return None  # Kein gueltiger Snap moeglich

        # Setzen
        self.set_loop_in(new_in)
        self.set_loop_out(new_out)
        print(f"[Engine.snap] Gesetzt: In={self.loop_in_seconds:.3f}s, Out={self.loop_out_seconds:.3f}s")
        return (self.loop_in_seconds, self.loop_out_seconds)

    def jump_to_loop_test(self):
        if self.sample_rate is None:
            return
        test_pos = self._loop_out - int(5.0 * self.sample_rate)
        test_pos = max(self._loop_in, test_pos)
        self.seek(test_pos / self.sample_rate)
        if not self._loop_active:
            self._loop_active = True

    def seek(self, position_seconds):
        if self.audio_data is None or self.sample_rate is None:
            return
        target = int(position_seconds * self.sample_rate)
        target = max(0, min(len(self.audio_data), target))
        # Unter Lock: kein Wettlauf mit Feeder-Thread
        with self._lock:
            self._feed_pos = target
            self._playback_sample = target
            self._loop_xfade_skip = 0  # Reset bei manuellem Seek
            self._display_pos_guard = None  # Anzeige-Glaettung: Rueckwaerts-Seek erlauben
            if self.stretcher:
                self.stretcher.flush()
                if self.pitcher:
                    # Post-Stretcher-Pitcher: bei Seek muss Interpolator-State
                    # auch zurueck (Tail/Carry sind veraltet), sonst Klick beim
                    # ersten Output-Block nach Seek.
                    self.pitcher.reset()
                self._feed_stretcher()
                # Kurzer Warmup nach Seek waehrend Wiedergabe:
                # WSOLA-Fenster muessen nach flush() neu einschwingen
                if self.playing:
                    self._warmup_frames = int(0.05 * self.sample_rate)

    def seek_with_crossfade(self, position_seconds, crossfade_ms=46):
        """Seek mit sanftem Uebergang: Warmup-Dauer an Crossfade-Parameter anpassen."""
        if self.audio_data is None or self.sample_rate is None:
            return
        self.seek(position_seconds)
        # Warmup-Dauer auf Crossfade-Parameter setzen (Fade-In am Ziel)
        if self.playing:
            self._warmup_frames = max(1, int(crossfade_ms * self.sample_rate / 1000))

    def _estimate_playback_pos(self):
        if not self.stretcher or not self.sample_rate:
            return 0
        # Ab Post-Stretcher-Pitch-Architektur (2026-06-03): Stretcher-Input
        # ist Original-Audio, daher KEIN ratio-Faktor mehr auf `buffered`.
        # intern#100: Der vorberechnete Output-Buffer (PREPROCESS_OUTPUT_SECONDS,
        # seit AR-020 1 s) ist schon aus dem Input verschwunden, aber noch nicht
        # zu hoeren -- ohne Abzug lief die Position ~1 s vor dem Ton (Anzeige,
        # Loop-In/-Out setzen). Output-Frames x Stretcher-Tempo = Original-Frames;
        # Pitcher-Carry analog (x pitch_ratio x Stretcher-Tempo = User-Tempo).
        # Nur Lesezugriffe ohne Lock, wie input_available().
        buffered = max(0, self.stretcher.input_available())
        buffered += self.stretcher.output_available() * self.stretcher.tempo
        if self.pitcher:
            buffered += (len(self.pitcher._out_carry)
                         * self._user_tempo * self._today_tempo)
        pos = max(0, self._feed_pos - int(buffered))
        # Nach Loop-Wrap kann _feed_pos nahe loop_in sein waehrend
        # der Buffer noch altes Audio enthaelt → pos klemmen.
        # NUR wenn Feed bereits im Loop-Bereich ist (nicht bei Pattern-Start
        # wo Wiedergabe noch vor loop_in laeuft).
        if self._loop_active and self._loop_out > self._loop_in:
            if self._feed_pos >= self._loop_in:
                if pos < self._loop_in:
                    # Feed hat bereits gewrappt, Callback aber noch nicht
                    # (z.B. Audition: 5s vor Loop-Out starten → Slider soll
                    # diese 5s korrekt anzeigen, nicht einfrieren).
                    # _playback_sample zaehlt tatsaechlich ausgegebene Samples
                    # (in Output-Frames, bei Tempo=1.0 == Original-Frames).
                    # Kein Tempo-Faktor hier: der Seek-Offset ist bereits in
                    # Original-Samples gesetzt; wir nutzen _playback_sample
                    # als Naehering (leicht ungenau bei Tempo != 1.0, aber
                    # deutlich besser als Einfrieren bei loop_in).
                    pos = self._playback_sample
                pos = min(pos, self._loop_out)

        # Anzeige-Glaettung: kleine Rueckspruenge (< 3s) sind Puffer-Artefakte
        # des Estimator-Wechsels (Feed-Schaetzung vs. Playback-Zaehler, Differenz
        # = Stretcher-Output-Puffer ~1s) — schlucken, Slider laeuft monoton.
        # ECHTE Loop-Ruckspruenge (Cut/Wrap, 15s bis Minuten) gehen durch.
        if self.playing and not self.paused:
            last = self._display_pos_guard
            if (last is not None and pos < last
                    and (last - pos) < int(3.0 * (self.sample_rate or 44100))):
                pos = last
            self._display_pos_guard = pos
        return pos

    def _combined_tempo(self):
        pitch_comp = self.pitcher.tempo_compensation() if self.pitcher else 1.0
        return self._user_tempo * self._today_tempo * pitch_comp

    def _feed_stretcher(self):
        """Fuettert den Stretcher mit Audio-Daten bis zum Feed-Ahead-Puffer.

        Loop-Mechanismus: Am Loop-Ende wird ein PCM-Crossfade ausgefuehrt —
        die letzten LOOP_XFADE_FRAMES des Loops werden mit den ersten Frames
        von loop_in ueberblendet. Kein flush(), kein Warmup, kein Seek noetig.
        WSOLA bekommt einen glatten Input-Strom ohne Diskontinuitaet.
        """
        if self.audio_data is None or self.stretcher is None:
            return
        feed_ahead = int(FEED_AHEAD_SECONDS * self.sample_rate)
        loop_out = self._loop_out if self._loop_active else len(self.audio_data)

        while self.stretcher.input_available() < feed_ahead:
            # Effektives Loop-Out mit Offset (positiv = spaeter, negativ = frueher)
            effective_loop_out = loop_out + self._loop_offset_frames if self._loop_active else loop_out
            # BL-164: EINEN (den ersten) Durchlauf um _loop_cut_frames verkuerzen,
            # damit die Gesamt-Patterlaenge naeher an die Wunschzeit kommt. Der
            # Ruecksprung erfolgt frueher (loop_out - cut -> loop_in); der Crossfade
            # unten haengt an effective_loop_out und greift daher automatisch am
            # vorgezogenen Punkt. Nur bei target>=2 (letzter Durchlauf bleibt voll,
            # Ausstieg loop_out->Tail unangetastet). Bei cut=0 identischer Pfad.
            if (self._loop_active and self._loop_cut_frames > 0
                    and self._loop_count_done == 0
                    and self._loop_count_target >= 2):
                effective_loop_out -= self._loop_cut_frames
            if self.audio_data is not None:
                effective_loop_out = min(effective_loop_out, len(self.audio_data))

            # Am Ende angekommen?
            if self._feed_pos >= effective_loop_out:
                if self._loop_active:
                    self._loop_count_done += 1
                    # Loop-Count erreicht? → Loop deaktivieren, weiter bis Song-Ende
                    if self._loop_count_target > 0 and self._loop_count_done >= self._loop_count_target:
                        self._loop_active = False
                        self._loop_xfade_skip = 0
                        continue  # Weiter abspielen bis Song-Ende
                    # Nahtloser Loop-Wrap: ueberspringe bereits eingeblendete Samples
                    self._feed_pos = self._loop_in + self._loop_xfade_skip
                    self._loop_xfade_skip = 0
                    continue
                break

            remaining = effective_loop_out - self._feed_pos
            chunk_size = min(RESAMPLE_BLOCK_SIZE, remaining)
            if chunk_size <= 0:
                break

            chunk = self.audio_data[self._feed_pos:self._feed_pos + chunk_size]

            # PCM-Crossfade am Loop-Uebergang: Wenn dieser Chunk das Loop-Ende
            # erreicht, ueberblenden wir die letzten Samples mit dem Loop-Anfang.
            # Das passiert VOR dem Pitch-Shift, damit WSOLA glatten Input bekommt.
            if self._loop_active and self._feed_pos + chunk_size >= effective_loop_out:
                loop_len = self._loop_out - self._loop_in
                xf_len = min(self._loop_xfade_frames, chunk_size, loop_len // 2)
                if xf_len > 0:
                    chunk = chunk.copy()  # audio_data nicht veraendern!
                    start_idx = chunk_size - xf_len
                    # Fade-Kurven (linear reicht bei 46ms voellig)
                    fade_out = np.linspace(1.0, 0.0, xf_len, dtype=np.float32)
                    fade_in = 1.0 - fade_out
                    if chunk.ndim > 1:
                        fade_out = fade_out.reshape(-1, 1)
                        fade_in = fade_in.reshape(-1, 1)
                    # Audio vom Loop-Anfang holen und einblenden
                    loop_start = self.audio_data[self._loop_in:self._loop_in + xf_len]
                    chunk[start_idx:] = chunk[start_idx:] * fade_out + loop_start * fade_in
                    self._loop_xfade_skip = xf_len

            # Pitch-Shifting laeuft ab 2026-06-03 HINTER dem Stretcher
            # (SoundTouch-Architektur fuer rate > 1). Stretcher-Input ist
            # ab jetzt immer Original-Audio — kein pre-resampletes Audio
            # mehr im 5-s-Puffer, daher kein Tempo-Wobble bei Pitch-Wechsel.
            self.stretcher.feed(chunk)
            self._feed_pos += chunk_size

    def _feeder_loop(self):
        """Haelt den Stretcher-Input- UND Output-Buffer gefuellt — Daemon-Thread.

        Alle 20ms:
        1. Input-Buffer fuellen (_feed_stretcher, unter AudioEngine-Lock)
        2. Output-Buffer vorverarbeiten (preprocess, unter Stretcher-Lock)

        Der Audio-Callback liest NUR noch vom vorbereiteten Output-Buffer ab —
        kein WSOLA-Processing mehr im Callback. Damit ist die Callback-Laufzeit
        O(1) (Array-Slice) statt O(n) (variable WSOLA-Berechnung), was Stottern
        auch ohne UI-Interaktion verhindert.
        """
        # AR-009: MMCSS-Hochstufung als allererste Aktion im Feeder-Thread.
        # Muss IM Thread aufgerufen werden (avrt operiert auf aktuellem Thread).
        if MMCSS_ENABLED:
            ok, msg = _apply_mmcss_pro_audio()
            _diag_log(f"[Diag] Feeder-Thread MMCSS: {msg}")
        else:
            _diag_log("[Diag] Feeder-Thread MMCSS: deaktiviert (MMCSS_ENABLED=False)")

        while not self._feeder_stop.wait(timeout=0.02):
            if self.playing and not self.paused and self.audio_data is not None:
                try:
                    with self._lock:
                        self._feed_stretcher()
                    # Preprocess WSOLA-Output (ohne AudioEngine-Lock — Stretcher hat eigenen Lock)
                    # Ein Lock-Release pro Hop damit der Callback zwischen Hops lesen kann.
                    if self.stretcher and self.sample_rate:
                        target = int(PREPROCESS_OUTPUT_SECONDS * self.sample_rate)
                        self.stretcher.preprocess(target)
                except Exception:
                    # Feeder darf NIE crashen — sonst stoppt das Audio
                    pass

            # AR-010: Underflow-Events des Callbacks ins Perf-Log spuelen.
            # Wir loggen NICHT im Callback selbst (I/O verschlimmert den Stall).
            while self._underflow_events:
                try:
                    ts, buf_ms, frames, was_warmup = self._underflow_events.popleft()
                except IndexError:
                    break
                tag = " (warmup)" if was_warmup else ""
                # buf_ms == 0 → wir waren tatsaechlich leer (Feeder konnte nicht nachfuellen).
                # buf_ms > 0 → Buffer war gefuellt, PortAudio/Treiber hat trotzdem gemeldet
                #              (Hostapi-Glitch, DPC-Stall, Device-Wechsel).
                if buf_ms < 1.0:
                    diag = "BUFFER LEER → Feeder/GIL-Verdacht"
                else:
                    diag = "BUFFER GEFUELLT → Treiber/Hostapi/DPC-Verdacht"
                _diag_log(
                    f"[Diag] PortAudio output_underflow @ {ts} "
                    f"buf={buf_ms:.1f}ms frames={frames}{tag} → {diag}"
                )

            # AR-020 T1 (c): Frame-Count-Histogramm dumpen, sobald genug Samples
            # gesammelt wurden. Einmal pro Stream. Zeigt ob der Treiber konstante
            # Block-Groessen liefert (WDM-KS-Verdacht: schwankende frames-Werte).
            if (not self._frame_samples_done
                    and len(self._frame_samples) >= self._frame_samples_target):
                try:
                    samples = list(self._frame_samples)  # Kopie, falls Callback weiterschreibt
                    counts = collections.Counter(samples)
                    n = len(samples)
                    f_min, f_max = min(samples), max(samples)
                    # Top-5 haeufigste Block-Groessen mit Anteil in %
                    top = counts.most_common(5)
                    top_str = ", ".join(
                        f"{val}×{cnt} ({cnt * 100 / n:.0f}%)"
                        for val, cnt in top
                    )
                    distinct = len(counts)
                    _diag_log(
                        f"[Diag] Callback-frames-Histogramm (erste {n}): "
                        f"min={f_min} max={f_max} distinct={distinct} | top: {top_str}"
                    )
                except Exception as e:
                    _diag_log(f"[Diag] Callback-frames-Histogramm fehlgeschlagen: {e}")
                finally:
                    self._frame_samples_done = True

    def check_loop_point(self):
        """Wird noch vom UI-Timer aufgerufen — jetzt No-Op.

        Loop-Uebergaenge werden nahtlos im Feed via PCM-Crossfade
        geloest, kein Seek/Flush mehr noetig.
        """
        pass

    def measure_loop_offset(self, auto_apply=True):
        """Misst den optimalen Loop-Offset per Tiefpass-Kreuzkorrelation.

        Vergleicht nur die tiefen Frequenzen (<200Hz, Bassdrum/Bass) am
        Loop-Ende mit dem Loop-Anfang. Sucht im Bereich +-2 Sekunden
        (mehrere Beats), um auch groessere Beat-Verschiebungen zu finden.

        Nutzt FFT-basierte Korrelation (scipy.signal.correlate) fuer
        effiziente Berechnung auch bei grossem Suchbereich.

        Args:
            auto_apply: Wenn True und Korrelation > 0.1, wird der Offset
                        automatisch in _loop_offset_frames uebernommen.

        Returns:
            (offset_samples, offset_ms, correlation) oder None bei Fehler
        """
        # Kern in Modulfunktion compute_loop_offset ausgelagert (BL-172), damit
        # der Bulk-BeatSnap-Worker denselben Offset headless messen kann.
        if self.audio_data is None or self.sample_rate is None:
            return None
        result = compute_loop_offset(
            self.audio_data, self.sample_rate, self._loop_in, self._loop_out)
        if result is None:
            return None
        apply_offset, apply_ms, best_corr = result
        print(f"[Loop-Offset] Messung (Tiefpass <200Hz): {apply_ms:.1f}ms, "
              f"Korrelation={best_corr:.4f}")
        if auto_apply and best_corr >= 0.1:
            self._loop_offset_frames = apply_offset
            print(f"[Loop-Offset] Auto-Apply: {apply_ms:.1f}ms")
        elif auto_apply:
            print(f"[Loop-Offset] Korrelation zu niedrig ({best_corr:.4f} < 0.1), "
                  f"kein Auto-Apply")
        return (apply_offset, apply_ms, best_corr)

    def _trim_output_for_param_change(self):
        """AR-021 (SoundTouch-Stil): bei Tempo/Pitch-Wechsel den output_buf
        von HINTEN auf 150 ms kuerzen, statt zu flushen.

        Damit hoert der User den neuen Parameter nach max. 150 ms (statt erst
        nach Abspielen der gesamten 1 s Reserve). Stretcher-State bleibt
        unangetastet — kein Phase-Sprung, kein Doppelgaenger, keine Stille.
        """
        if not self.stretcher or not self.sample_rate:
            return
        max_frames = int(0.150 * self.sample_rate)
        self.stretcher.trim_output_to(max_frames)
        _diag_log(f"[Diag] AR-021 param_change: output_buf auf {max_frames} frames (~150ms) gekuerzt")
    def start_fade_out(self, duration_s=5.0):
        """Startet einen linearen Fade-Out ueber die angegebene Dauer."""
        if not self.playing or self.sample_rate is None:
            return
        total_samples = int(duration_s * self.sample_rate)
        if total_samples <= 0:
            return
        self._fade_step = 1.0 / total_samples
        self._fade_volume = 1.0
        self._fading = True

    def is_fading(self):
        return self._fading

    def _ensure_stream(self):
        """Stream erstellen oder wiederverwenden.

        Erstellt den OutputStream nur wenn noetig (anderes Format oder
        noch keiner vorhanden). Vermeidet Windows-Treiber-Initialisierung
        bei jedem Play-Aufruf, was Brummen/Knacken am Song-Start verursacht.
        """
        # Effektives Geraet: Fallback-Cache pruefen. Wenn device X in dieser Session
        # bereits gescheitert ist (Fallback 2 wurde verwendet), direkt das bekannte
        # Ersatz-Geraet nehmen — kein erneuter WASAPI-Versuch noetig.
        effective_device = self._device_fallback.get(self._output_device, self._output_device)

        need_new = (
            self.stream is None
            or self._stream_sr != self.sample_rate
            or self._stream_ch != self.channels
            or self._stream_device != effective_device
            or self._stream_exclusive != self._wasapi_exclusive
        )
        if need_new:
            if self.stream is not None:
                self.stream.close()
            # AR-008: extra_settings nur wenn Device ein WASAPI-Device ist und Exclusive aktiv
            extra = self._wasapi_extra_settings()
            # AR-013/M (v0.88): Versuchs-Log — was wollen wir oeffnen?
            # Endergebnis kommt aus dem existierenden [Diag] Stream gestartet-Log unten.
            try:
                if effective_device is None:
                    _diag_log("[Diag] Stream-Init Versuch: device=None (System-Default)")
                else:
                    _dev = sd.query_devices(int(effective_device))
                    try:
                        _ha = sd.query_hostapis(_dev['hostapi'])['name']
                    except Exception:
                        _ha = f"#{_dev.get('hostapi', '?')}"
                    # AR-020 T1+: hw_default des Versuchs-Devices loggen.
                    # Wenn != self.sample_rate, ist ein SR-Mismatch wahrscheinliche
                    # Fehlerursache (-9997 Invalid sample rate) bzw. erzeugt schlechtes
                    # Treiber-Resampling (WDM-KS/Realtek-Verdacht).
                    _hw_sr = _dev.get('default_samplerate', None)
                    _hw_sr_str = f"{_hw_sr:.0f}Hz" if _hw_sr else "?"
                    _mismatch = ""
                    if _hw_sr and abs(_hw_sr - self.sample_rate) > 1:
                        _mismatch = f" ⚠ SR-MISMATCH (wir fordern {self.sample_rate}Hz)"
                    _diag_log(
                        f"[Diag] Stream-Init Versuch: device={effective_device}, "
                        f"name='{_dev.get('name', '?')}', hostapi={_ha}, "
                        f"hw_default={_hw_sr_str}, "
                        f"exclusive={'JA' if extra is not None else 'nein'}{_mismatch}"
                    )
            except Exception as _e:
                _diag_log(f"[Diag] Stream-Init Versuch: device={effective_device} (Info nicht lesbar: {_e})")
            try:
                self.stream = sd.OutputStream(
                    samplerate=self.sample_rate,
                    channels=self.channels,
                    dtype='float32',
                    callback=self._callback,
                    blocksize=BLOCK_SIZE,
                    latency='low',
                    device=effective_device,
                    extra_settings=extra,
                )
            except Exception as e:
                # Fallback 1: ohne extra_settings (Exclusive-Init kann scheitern)
                if extra is not None:
                    _diag_log(f"[Diag] WASAPI Exclusive-Init fehlgeschlagen ({e}) — fallback auf Shared")
                    extra = None
                else:
                    # AR-013/M: Stream-Open mit dem gewuenschten Device ist gescheitert.
                    # Wenn der User WASAPI gewaehlt hat und wir hier landen, war's das.
                    _diag_log(
                        f"[Diag] Stream-Init fehlgeschlagen mit device={effective_device} ({e}) "
                        f"— Fallback 1 auf gleiches Device ohne extra_settings"
                    )
                try:
                    self.stream = sd.OutputStream(
                        samplerate=self.sample_rate,
                        channels=self.channels,
                        dtype='float32',
                        callback=self._callback,
                        blocksize=BLOCK_SIZE,
                        latency='low',
                        device=effective_device,
                    )
                except Exception as e2:
                    # Fallback 2: System-Standard-Device verwenden falls das gewaehlte nicht verfuegbar ist
                    _diag_log(
                        f"[Diag] Stream-Init Fallback 1 ebenfalls fehlgeschlagen ({e2}) "
                        f"— Fallback 2 auf System-Standard (Default-Hostapi, meist MME). "
                        f"User-Auswahl device={self._output_device} wird IGNORIERT!"
                    )
                    self.stream = sd.OutputStream(
                        samplerate=self.sample_rate,
                        channels=self.channels,
                        dtype='float32',
                        callback=self._callback,
                        blocksize=BLOCK_SIZE,
                        latency='low'
                    )
                    # Fallback-Cache eintragen: naechstes Mal direkt System-Default nehmen
                    self._device_fallback[self._output_device] = None
                    effective_device = None
            self.stream.start()
            self._stream_sr = self.sample_rate
            self._stream_ch = self.channels
            self._stream_device = effective_device  # tatsaechliches Geraet (nach Fallback-Aufloesung)
            self._stream_exclusive = (extra is not None)
            # AR-020 T1: Frame-Count-Sampling fuer neuen Stream zuruecksetzen
            self._frame_samples = []
            self._frame_samples_done = False
            # AR-007 Diagnose: tatsaechlich verwendetes Device + Hostapi loggen
            try:
                dev_idx = self.stream.device
                if isinstance(dev_idx, (list, tuple)):
                    dev_idx = dev_idx[0] if dev_idx else None
                if dev_idx is None:
                    dev_info = sd.query_devices(kind="output")
                else:
                    dev_info = sd.query_devices(dev_idx)
                try:
                    hostapi_name = sd.query_hostapis(dev_info["hostapi"])["name"]
                except Exception:
                    hostapi_name = f"#{dev_info.get('hostapi', '?')}"
                # AR-020 T1 (a): Hardware-native Sample-Rate des Devices loggen.
                # Wenn != stream.samplerate, uebernimmt der Treiber Resampling — auf
                # WDM-KS/Realtek HD historisch schlecht (Aliasing-Artefakte hoerbar).
                hw_sr = dev_info.get("default_samplerate", None)
                hw_sr_str = f"{hw_sr:.0f}Hz" if hw_sr else "?"
                _diag_log(
                    f"[Diag] Stream gestartet: '{dev_info['name']}' "
                    f"hostapi={hostapi_name} sr={self.stream.samplerate:.0f}Hz "
                    f"(hw_default={hw_sr_str}) "
                    f"ch={self.stream.channels} blocksize={self.stream.blocksize} "
                    f"latency={self.stream.latency * 1000:.1f}ms "
                    f"exclusive={'JA' if self._stream_exclusive else 'nein'}"
                )
            except Exception as e:
                _diag_log(f"[Diag] Stream gestartet (Info nicht lesbar: {e})")
            # WASAPI-Session nach Stream-Start suchen (Session existiert erst jetzt)
            self._wasapi_session = None
            threading.Thread(target=self._wasapi_lookup_delayed,
                             daemon=True).start()

    def _wasapi_lookup_delayed(self):
        """Sucht WASAPI-Session nach kurzem Delay (Stream braucht ~100ms zum Registrieren)."""
        time.sleep(0.2)
        self._wasapi_lookup()
        # Aktuellen Live-Volume-Wert direkt anwenden
        if self._wasapi_session is not None and self._live_volume != 1.0:
            self._wasapi_set(self._live_volume)

    def _callback(self, outdata, frames, time_info, status):
        # AR-020 T1 (c): Frame-Count-Sampling. Append ist O(1), kein Lock noetig
        # (Liste wird nur vom Feeder gelesen wenn _frame_samples_done=True gesetzt wird).
        if not self._frame_samples_done and len(self._frame_samples) < self._frame_samples_target:
            self._frame_samples.append(frames)

        if not self.playing or self.paused or self.stretcher is None:
            outdata[:] = 0
            return

        # Output-Buffer-Stand VOR retrieve() messen (in ms) — vorgezogen, damit der
        # Underflow-Event mit dem korrekten Buf-Stand korreliert werden kann.
        buf_ms_now = 0.0
        if self.sample_rate:
            buf_frames = self.stretcher.output_available()
            buf_ms_now = buf_frames / self.sample_rate * 1000.0
            self._diag_buf_ms = buf_ms_now
            now = time.monotonic()
            self._diag_history.append((now, buf_ms_now))
            # Eintraege aelter als 10s entfernen
            cutoff = now - 10.0
            while self._diag_history and self._diag_history[0][0] < cutoff:
                self._diag_history.popleft()

        # PortAudio-Underflow zaehlen UND Event sammeln (AR-010)
        # Im Callback NICHT direkt loggen (I/O blockiert) — der Feeder druckt die Events.
        if status and status.output_underflow:
            self._diag_xruns += 1
            if LOG_UNDERFLOWS:
                ts = time.strftime("%H:%M:%S") + f".{int((time.time()%1)*1000):03d}"
                try:
                    self._underflow_events.append(
                        (ts, buf_ms_now, frames, self._warmup_frames > 0)
                    )
                except Exception:
                    pass

        # WSOLA-Warmup: Daten verarbeiten aber Stille ausgeben,
        # bis die Overlap-Add-Fenster stabil eingeschwungen sind.
        # Im Warmup gehen die Frames auch durch den Pitcher, damit dessen
        # Interpolator-State (Tail/Phase/Carry) mit den verworfenen Samples
        # eingeschwungen ist, wenn die Wiedergabe startet.
        if self._warmup_frames > 0:
            try:
                if self.pitcher:
                    self.pitcher.fetch(frames, self.stretcher)
                else:
                    self.stretcher.retrieve(frames)
            except Exception:
                pass
            self._warmup_frames -= frames
            outdata[:] = 0
            return

        try:
            if self.pitcher:
                stretched = self.pitcher.fetch(frames, self.stretcher)
            else:
                stretched = self.stretcher.retrieve(frames)
        except Exception:
            outdata[:] = 0
            return

        # Fade-Out anwenden — vektorisiert (AR-018, v0.91).
        # Vorher: Python-for ueber 1024 Samples im Callback -> auf schwacher CPU
        # (Celeron N3450) hoerbares Stottern beim Fade-Out trotz WDM-KS.
        if self._fading:
            n = len(stretched)
            # Lineare Volume-Rampe: startet bei _fade_volume, faellt pro Sample um _fade_step
            # Wert _nach_ Sample i = _fade_volume - (i+1)*_fade_step
            ramp = self._fade_volume - (np.arange(1, n + 1, dtype=np.float32) * self._fade_step)
            if ramp[-1] <= 0:
                # Fade endet in diesem Block — ab zero_idx ist alles 0
                zero_idx = int(np.argmax(ramp <= 0))
                ramp[zero_idx:] = 0
                if stretched.ndim == 2:
                    stretched *= ramp[:, np.newaxis]
                else:
                    stretched *= ramp
                self._fade_volume = 0
                self._fading = False
                self.playing = False
                if self.on_song_finished:
                    self.on_song_finished()
            else:
                if stretched.ndim == 2:
                    stretched *= ramp[:, np.newaxis]
                else:
                    stretched *= ramp
                self._fade_volume = float(ramp[-1])

        # Song-Volume anwenden (multiplikativ, mit Smooth-Rampe)
        vol = self._song_volume
        vol_target = self._song_volume_target
        if vol != vol_target:
            n = len(stretched)
            # Maximale Aenderung in diesem Buffer begrenzen
            max_delta = self._volume_ramp_rate * n
            delta = vol_target - vol
            if abs(delta) <= max_delta:
                end_vol = vol_target
            else:
                end_vol = vol + max_delta * (1.0 if delta > 0 else -1.0)
            ramp = np.linspace(vol, end_vol, n, dtype='float32')
            if stretched.ndim == 2:
                stretched *= ramp[:, np.newaxis]
            else:
                stretched *= ramp
            self._song_volume = end_vol
        elif vol != 1.0:
            stretched *= vol

        # BL-137: Alert-Sound einmischen (additiv, mit Clip-Schutz).
        # Im Normalbetrieb: ein `is not None`-Check, sonst nichts.
        alert = self._alert_data
        if alert is not None:
            ap = self._alert_pos
            remaining = len(alert) - ap
            if remaining <= 0:
                # Alert ausgespielt — Buffer freigeben
                self._alert_data = None
                self._alert_pos = 0
            else:
                n = min(frames, remaining)
                stretched[:n] = np.clip(
                    stretched[:n] + alert[ap:ap + n] * self._alert_volume,
                    -1.0, 1.0,
                )
                self._alert_pos = ap + n
                if self._alert_pos >= len(alert):
                    self._alert_data = None
                    self._alert_pos = 0

        outdata[:] = stretched
        self._playback_sample += frames

        # Diagnose-Capture (nur aktiv wenn start_output_capture() aufgerufen).
        # Im Normalbetrieb: ein `is not None`-Check, sonst nichts. Kein Lock.
        cap = self._capture_buf
        if cap is not None and not self._capture_full:
            pos = self._capture_pos
            end = pos + frames
            if end >= len(cap):
                end = len(cap)
                self._capture_full = True
                n = end - pos
                cap[pos:end] = stretched[:n]
            else:
                cap[pos:end] = stretched
            self._capture_pos = end

        # Playback-Counter im Loop-Bereich halten (fuer Positions-Anzeige)
        if self._loop_active and self._loop_out > self._loop_in:
            if self._playback_sample >= self._loop_out:
                loop_len = self._loop_out - self._loop_in
                self._playback_sample = (
                    self._loop_in
                    + (self._playback_sample - self._loop_out) % loop_len
                )

        # Song-Ende nur wenn KEIN Loop aktiv ist
        if not self._loop_active:
            if (self._feed_pos >= len(self.audio_data)
                    and not self.stretcher.can_process()):
                self.playing = False
                if self.on_song_finished:
                    self.on_song_finished()

    def set_tempo(self, tempo):
        """Song-Tempo setzen (per-Song, gespeichert in DB).

        AR-021 (SoundTouch-Stil): nur Stretcher-Parameter aktualisieren, kein
        Flush, kein Trim. Latenz bis zu 1 s (Output-Buffer-Reserve) wird in
        Kauf genommen — dafuer keine Position-Spruenge, keine Klicks, keine Stille.
        """
        self._user_tempo = max(0.5, min(1.5, float(tempo)))
        if self.stretcher:
            self.stretcher.set_tempo(self._combined_tempo())
            _diag_log("[Diag] AR-021 set_tempo: nur Parameter, kein Trim (SoundTouch-Stil)")

    def set_today_tempo(self, tempo):
        """Heutiges Tempo setzen (Session-Faktor, nicht gespeichert)."""
        self._today_tempo = max(0.5, min(1.5, float(tempo)))
        if self.stretcher:
            self.stretcher.set_tempo(self._combined_tempo())
            _diag_log("[Diag] AR-021 set_today_tempo: nur Parameter, kein Trim")

    def set_pitch(self, semitones):
        if self.pitcher:
            self.pitcher.set_pitch(semitones)
            if self.stretcher:
                self.stretcher.set_tempo(self._combined_tempo())
                _diag_log("[Diag] AR-021 set_pitch: nur Parameter, kein Trim")

    def set_volume(self, factor):
        """Setzt den Song-Volume-Faktor (multiplikativ, 0.0–1.0).

        Aenderungen werden im Audio-Callback smooth gerampt (~50ms),
        damit keine Knackser oder Spruenge hoerbar sind.
        """
        self._song_volume_target = max(0.0, min(1.0, float(factor)))

    def set_min_volume(self, floor: float):
        """Setzt den Mindest-Lautstaerke-Boden fuer Live-Volume (aus INI)."""
        self._min_volume = max(0.0, min(1.0, float(floor)))

    def set_live_volume(self, factor: float):
        """Setzt die Live-Lautstaerke ueber Windows WASAPI (artefaktfrei).

        Aendert die per-App-Lautstaerke im Windows Audio Mixer — komplett
        ausserhalb des Audiostreams, kein Ramp noetig, kein Knacken.
        Der Wert wird auf [_min_volume, 1.0] geclampet.
        """
        clamped = max(self._min_volume, min(1.0, float(factor)))
        self._live_volume = clamped
        self._wasapi_set(clamped)

    def get_live_volume(self) -> float:
        """Gibt die aktuelle Live-Lautstaerke zurueck."""
        return self._live_volume

    def reset_live_volume(self):
        """Setzt Live-Volume auf 1.0 zurueck (z.B. bei Song-Wechsel)."""
        self._live_volume = 1.0
        self._wasapi_set(1.0)

    def _wasapi_lookup(self):
        """Sucht die eigene Audio-Session via pycaw und cached sie."""
        if not _PYCAW_AVAILABLE:
            return
        try:
            sessions = AudioUtilities.GetAllSessions()
            for s in sessions:
                if s.ProcessId == self._wasapi_pid:
                    self._wasapi_session = s._ctl.QueryInterface(ISimpleAudioVolume)
                    return
        except Exception:
            pass

    def _wasapi_set(self, value: float):
        """Setzt per-App-Volume via WASAPI. Sucht Session falls noch nicht gecacht."""
        if not _PYCAW_AVAILABLE:
            return
        if self._wasapi_session is None:
            self._wasapi_lookup()
        if self._wasapi_session is None:
            return
        try:
            self._wasapi_session.SetMasterVolume(value, None)
        except Exception:
            # Session ungueltig (z.B. nach Stream-Neustart) — neu suchen
            self._wasapi_session = None

    def play(self):
        if self.audio_data is None:
            return
        self._fading = False
        self._fade_volume = 1.0
        self._fade_step = 0.0
        if self.paused:
            self.paused = False
            return
        if self.stretcher:
            self.stretcher.set_tempo(self._combined_tempo())
        # Initial-Fuellung unter Lock — vor dem Start des Streams
        with self._lock:
            self._feed_stretcher()
        # Output-Buffer sofort vorbefuellen (nicht erst nach 20ms Feeder-Zyklus)
        if self.stretcher and self.sample_rate:
            target = int(PREPROCESS_OUTPUT_SECONDS * self.sample_rate)
            self.stretcher.preprocess(target)
        # WSOLA-Warmup: ~200ms verarbeiten und verwerfen, damit
        # die Overlap-Add-Fenster sauber eingeschwungen sind
        self._warmup_frames = int(0.2 * self.sample_rate)
        self.playing = True
        self.paused = False
        # Stream wiederverwenden statt jedes Mal neu erstellen
        # Der Feeder-Thread laeuft bereits seit __init__ und uebernimmt
        # ab jetzt das kontinuierliche Fuettern (playing=True)
        self._ensure_stream()

    def pause(self):
        if self.playing:
            self.paused = True

    def stop(self):
        self.playing = False
        self.paused = False
        self._fading = False
        self._fade_volume = 1.0
        self._fade_step = 0.0
        self._loop_xfade_skip = 0
        # Stream NICHT schliessen — bleibt offen fuer den naechsten Play
        # (Callback gibt Stille aus wenn self.playing == False)
        self._feed_pos = self._loop_in if self._loop_active else 0
        self._playback_sample = self._feed_pos
        self._display_pos_guard = None  # Anzeige-Glaettung zuruecksetzen
        # Stretcher reset: sicher, weil playing=False → Callback nutzt ihn nicht mehr
        if self.stretcher:
            self.stretcher.reset()
        if self.pitcher:
            self.pitcher.reset()

    def shutdown(self):
        """Stream endgueltig schliessen (nur bei App-Ende aufrufen)."""
        self.playing = False
        # Feeder-Thread beenden (Daemon, wuerde sonst beim App-Exit ohnehin sterben,
        # aber sauberer Stop verhindert Zugriff auf bereits geschlossene Ressourcen)
        self._feeder_stop.set()
        if self._feeder_thread and self._feeder_thread.is_alive():
            self._feeder_thread.join(timeout=0.5)
        if self.stream is not None:
            self.stream.close()
            self.stream = None
            self._stream_sr = None
            self._stream_ch = None
            self._stream_device = None

    def ensure_stream_alive(self):
        """Prueft ob der OutputStream noch aktiv ist und startet ihn bei Bedarf neu.

        Wird vom UI-Timer (Main-Thread) aufgerufen waehrend playing=True.
        Behandelt den Fall: Audio-Device entfernt (USB-Soundkarte, HDMI-Disconnect, etc.)
        → stream.active=False → Stream wird neu erstellt sobald ein Device verfuegbar ist.
        Throttling: maximal 1 Versuch alle 2 Sekunden (verhindert Spam bei dauerhaft fehlendem Device).
        """
        if not self.playing or self.paused:
            return
        if self.stream is None or self.stream.active:
            return  # Stream laeuft normal

        import time as _t
        now = _t.monotonic()
        if now - self._last_recovery_attempt < 2.0:
            return  # Noch nicht wieder versuchen
        self._last_recovery_attempt = now

        print("[AudioEngine] Stream nicht mehr aktiv — versuche Device-Recovery")
        try:
            self.stream.close()
        except Exception:
            pass
        self.stream = None
        self._stream_sr = None
        self._stream_ch = None
        self._stream_device = None
        try:
            self._ensure_stream()
            print("[AudioEngine] Stream neu gestartet (Device-Recovery erfolgreich)")
        except Exception as e:
            print(f"[AudioEngine] Stream-Neustart fehlgeschlagen: {e}")

    def set_output_device(self, device_index):
        """Setzt das Audio-Ausgabegeraet und startet den Stream bei Bedarf neu.

        device_index: int (Geraete-Index aus sd.query_devices()) oder None (System-Standard).
        Bei laufender Wiedergabe wird der Stream sofort auf das neue Geraet umgeschaltet.
        """
        if self._output_device == device_index:
            return
        self._output_device = device_index
        self._restart_stream_after_config_change()

    def set_wasapi_exclusive(self, enabled: bool):
        """AR-008: Schaltet WASAPI Exclusive Mode fuer das aktuelle Device an/aus.

        Greift nur, wenn das aktuelle Device ein WASAPI-Device ist; sonst
        wird das Flag gesetzt, aber beim naechsten Stream-Init ignoriert.
        """
        enabled = bool(enabled)
        if self._wasapi_exclusive == enabled:
            return
        self._wasapi_exclusive = enabled
        self._restart_stream_after_config_change()

    def _restart_stream_after_config_change(self):
        """Schliesst den Stream und oeffnet bei laufender Wiedergabe sofort neu."""
        if self.stream is not None:
            try:
                self.stream.close()
            except Exception:
                pass
            self.stream = None
            self._stream_sr = None
            self._stream_ch = None
            self._stream_device = None
            self._stream_exclusive = False
        if self.playing and not self.paused and self.audio_data is not None:
            try:
                self._ensure_stream()
            except Exception as e:
                print(f"[AudioEngine] Stream-Neustart fehlgeschlagen: {e}")

    def _wasapi_extra_settings(self):
        """Liefert sd.WasapiSettings(exclusive=True) wenn _wasapi_exclusive und
        das aktuelle Device ein WASAPI-Device ist; sonst None."""
        if not self._wasapi_exclusive:
            return None
        try:
            # Device-Info holen — bei None (System-Standard) wird Default-Output gemeint.
            if self._output_device is None:
                dev_info = sd.query_devices(kind="output")
            else:
                dev_info = sd.query_devices(self._output_device)
            hostapi_name = sd.query_hostapis(dev_info["hostapi"])["name"]
            if "WASAPI" not in hostapi_name.upper():
                # Exclusive ist nur fuer WASAPI sinnvoll — bei anderen Hostapis ignorieren
                return None
            return sd.WasapiSettings(exclusive=True)
        except Exception:
            return None

    def get_position_seconds(self):
        if self.stretcher and self.sample_rate:
            return self._estimate_playback_pos() / self.sample_rate
        return 0.0

    def get_playback_position_seconds(self):
        """Praezise Wiedergabe-Position basierend auf dem Sample-Counter.

        Zaehlt die tatsaechlich vom Audio-Callback ausgegebenen Samples.
        Praeziser als get_position_seconds() (das auf Feed-Position minus
        geschaetztem Buffer basiert), weil es misst was wirklich gespielt wird.
        """
        if self.sample_rate:
            return self._playback_sample / self.sample_rate
        return 0.0

    def get_audio_diag(self):
        """Gibt aktuelle Buffer-Diagnostik zurück (fuer Konsolen-Output im _update_all-Timer).

        Returns dict mit:
            buf_ms:   Output-Buffer-Stand beim letzten Callback (in ms)
            min10s:   Rolling-Minimum der letzten 10 Sekunden (in ms)
            xruns:    PortAudio-Underflows seit letztem reset_audio_diag()
        """
        # Snapshot ziehen: _diag_history wird parallel vom Audio-Callback
        # befuellt. Direkte Iteration ueber die Live-Deque warf sporadisch
        # "RuntimeError: deque mutated during iteration" -> App-Crash. Der
        # Callback darf nicht gelockt werden (Echtzeit), darum kopieren und
        # den seltenen Mutations-Fall abfangen — Diagnostik ist unkritisch.
        try:
            snapshot = list(self._diag_history)
        except RuntimeError:
            snapshot = []
        min10s = min((v for _, v in snapshot), default=self._diag_buf_ms)
        return {
            "buf_ms":      self._diag_buf_ms,
            "min10s":      min10s,
            "xruns":       self._diag_xruns,
            "history_len": len(snapshot),
        }

    def reset_audio_diag(self):
        """Setzt Diagnostik-Zaehler zurueck (z.B. bei Song-Start)."""
        self._diag_buf_ms = 0.0
        self._diag_xruns = 0
        self._diag_history.clear()

    def get_and_reset_stretcher_stats(self):
        """AR-020: Stretcher-Statistik fuer Diagnose-Log abrufen.

        Wird vom AudioBuf-Sampler in main.py alle 5 s aufgerufen. Zeigt
        Fix A (passthrough vs. correlation) und Fix C (Lock-Hold-Zeiten)
        in Aktion. Bei keinem Stretcher: None.
        """
        if self.stretcher is None:
            return None
        return self.stretcher.get_and_reset_stats()

    def get_duration_seconds(self):
        if self.sample_rate and self.audio_data is not None:
            return (self.audio_data.shape[0] / self.sample_rate) / (self._user_tempo * self._today_tempo)
        return 0.0

    def get_original_duration(self):
        if self.sample_rate and self.audio_data is not None:
            return self.audio_data.shape[0] / self.sample_rate
        return 0.0

    def is_playing(self):
        return self.playing and not self.paused

    def is_paused(self):
        return self.playing and self.paused

    def is_loaded(self):
        return self.audio_data is not None
