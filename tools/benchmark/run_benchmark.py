"""Callers-Caddy Performance-Benchmark — unbeaufsichtigter externer Runner.

Faehrt das ECHTE Hauptfenster in-process hoch und spielt einen typischen
Nutzer-Ablauf ab (Suchen, Auswaehlen, Play, Sequenzen ...), misst jeden Schritt
und schreibt die Zahlen maschinell auswertbar als JSON nach results/.

Dieses Skript ist bewusst NICHT Teil der ausgelieferten App: es liegt unter
tools/ (in installer/build.py als EXCLUDE_DIR gefuehrt) und wird weder ins EXE
noch ins Release-ZIP gepackt. Die gesamte Szenario- und Auswertungslogik lebt
hier extern; im App-Code selbst braucht es nur minimale "Test-Nahte".

Prinzip DB-Wahl OHNE App-Aenderung: Callers Caddy leitet DB/INI aus dem
Arbeitsverzeichnis (cwd) ab (PathManager: <cwd>/callers_caddy.db). Der Runner
legt daher ein Sandbox-cwd an, kopiert die gewuenschte DB dort als
callers_caddy.db hinein und wechselt VOR dem Import von main.py hinein. So ist
--db frei waehlbar (leer vs. voll) und der Single-Instance-Lock (haengt an cwd)
kollidiert nicht mit einer echten laufenden Instanz.

Aufruf (mit demselben Python wie der Dev-Start, siehe run-cc-dev.bat):
    python tools/benchmark/run_benchmark.py --db "C:\\pfad\\zur.db" --label "vor Fix X"

Doku/Design: siehe Issue davidgoebel75/callers-caddy-intern#72.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import statistics
import sys
import time
from datetime import datetime
from pathlib import Path

# --- Pfade -------------------------------------------------------------------
# tools/benchmark/ -> parents[2] = Repo-Wurzel; der App-Code liegt in src/.
BENCH_DIR = Path(__file__).resolve().parent
REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_DIR = REPO_ROOT / "src"
RESULTS_DIR = BENCH_DIR / "results"
SANDBOX_DIR = BENCH_DIR / ".sandbox"


# --- kleine Mess-/Warte-Helfer ----------------------------------------------

class Bench:
    """Sammelt Schritt-Timings und haelt die App-Referenzen."""

    def __init__(self, app, window, label, repeat):
        self.app = app
        self.window = window
        self.label = label
        self.repeat = repeat
        self.steps: list[dict] = []

    def add(self, name, ms, ok=True, meta=None):
        entry = {"name": name, "ms": round(ms, 1), "ok": bool(ok)}
        if meta:
            entry["meta"] = meta
        self.steps.append(entry)
        flag = "OK " if ok else "ERR"
        print(f"  [{flag}] {name:<28} {ms:8.1f} ms"
              + (f"   {meta}" if meta else ""))
        return entry

    def pump(self, ms=0):
        """Qt-Eventloop kurz laufen lassen (Repaints/Deferred-Timer)."""
        from PySide6.QtWidgets import QApplication
        deadline = time.perf_counter() + ms / 1000.0
        QApplication.processEvents()
        while time.perf_counter() < deadline:
            QApplication.processEvents()

    def wait_until(self, pred, timeout_ms=5000, poll_ms=10):
        """Pumpt Events bis pred() True ist oder Timeout. Gibt erreicht? zurueck."""
        from PySide6.QtWidgets import QApplication
        deadline = time.perf_counter() + timeout_ms / 1000.0
        while time.perf_counter() < deadline:
            if pred():
                return True
            QApplication.processEvents()
            time.sleep(poll_ms / 1000.0)
        return pred()


# --- Sandbox / Boot ----------------------------------------------------------

def _clone_settings_ini(source_ini: Path, sandbox: Path, source_dir: Path,
                        perf_logging: bool):
    """Klont die echte INI in die Sandbox — "Erstbevoelkerung" mit GENAU den
    Einstellungen des Quellordners (z.B. 2_Test), damit die Messung dem
    entspricht, was der Nutzer im Alltag erlebt (Audio-Geraet, MMCSS,
    Feed-Ahead, Skin, Layout ...).

    Einzige Anpassung: relative Pfade unter [paths] werden absolut gegen den
    Quellordner aufgeloest — weil das Arbeitsverzeichnis wechselt und sie sonst
    ins leere Sandbox-Verzeichnis zeigen wuerden (Musik/Lyrics nicht gefunden).
    """
    from PySide6.QtCore import QSettings
    dst = sandbox / "callers_caddy.ini"
    shutil.copy2(source_ini, dst)   # verbatim (gleiches QSettings-INI-Format)

    s = QSettings(str(dst), QSettings.IniFormat)
    s.beginGroup("paths")
    for key in s.childKeys():
        raw = s.value(key, "")
        if isinstance(raw, str) and raw and not os.path.isabs(raw):
            s.setValue(key, os.path.abspath(os.path.join(str(source_dir), raw)))
    s.endGroup()
    # Daten-Verzeichnisse (lyrics/playlists/import) stehen oft NICHT in der INI
    # und defaulten dann relativ zum (leeren) Sandbox-cwd. Damit Lyrics-Dateien
    # (fuer Dynamic-Lyrics) und Playlists gefunden werden, auf die echten
    # Quellordner zeigen, sofern sie existieren.
    for key, default in (("import_dir", "neu"), ("lyrics_dir", "lyrics"),
                         ("playlist_dir", "playlists")):
        ini_key = f"paths/{key}"
        if not s.contains(ini_key):
            src_path = os.path.join(str(source_dir), default)
            if os.path.isdir(src_path):
                s.setValue(ini_key, os.path.abspath(src_path))
    # Sprache sicherstellen (kein Erststart-Dialog) + Perf-Logging nach Flag.
    if not s.contains("display/language"):
        s.setValue("display/language", "de")
    s.setValue("debug/performance_logging", "true" if perf_logging else "false")
    # Headless-Override: der Feedback-Dialog beim Stop ist ein MODALER Nutzer-
    # Dialog (main._trigger_song_stopped) — unbeaufsichtigt wuerde er blockieren.
    # Er ist reine UX, kein Performance-Pfad, daher fuer den Benchmark aus.
    s.setValue("feedback/enabled", "false")
    # Dynamic-Lyrics-Modus vorwaehlen (falls nicht gesetzt), sonst kaeme beim
    # ersten Toggle ein modaler Auswahl-Dialog. Vorhandene Wahl bleibt erhalten.
    if not s.contains("lyrics/dynamic_mode"):
        s.setValue("lyrics/dynamic_mode", "1")
    s.sync()


def prepare_sandbox(db_path: str | None, settings_ini: str | None,
                    perf_logging: bool) -> Path:
    """Legt ein frisches Sandbox-Arbeitsverzeichnis an und praepariert DB + INI.

    Die INI wird aus dem echten Quellordner geklont (Default: Geschwister-INI
    der --db, sonst --settings). Fehlt eine Quelle, wird eine minimale INI
    geschrieben. Rueckgabe: der Sandbox-Pfad (wird zum cwd der App).
    """
    if SANDBOX_DIR.exists():
        shutil.rmtree(SANDBOX_DIR, ignore_errors=True)
    SANDBOX_DIR.mkdir(parents=True, exist_ok=True)
    (SANDBOX_DIR / "music").mkdir(exist_ok=True)

    # Gewuenschte DB als callers_caddy.db hineinlegen. Ohne --db bleibt es leer
    # (SongDatabase legt beim ersten Zugriff ein leeres Schema an) -> nuetzlich
    # fuer den "leere DB"-Vergleichslauf.
    if db_path:
        src = Path(db_path)
        if not src.is_file():
            raise SystemExit(f"--db nicht gefunden: {src}")
        shutil.copy2(src, SANDBOX_DIR / "callers_caddy.db")

    # INI-Quelle bestimmen: explizit via --settings, sonst neben der --db.
    source_ini = None
    if settings_ini:
        source_ini = Path(settings_ini)
        if not source_ini.is_file():
            raise SystemExit(f"--settings nicht gefunden: {source_ini}")
    elif db_path:
        cand = Path(db_path).resolve().parent / "callers_caddy.ini"
        if cand.is_file():
            source_ini = cand

    if source_ini:
        print(f"  INI geklont aus: {source_ini}")
        _clone_settings_ini(source_ini, SANDBOX_DIR, source_ini.resolve().parent,
                            perf_logging)
    else:
        # Fallback: minimale INI (kein Quellordner vorhanden).
        (SANDBOX_DIR / "callers_caddy.ini").write_text(
            "[display]\nlanguage=de\nskin=default\n"
            "[paths]\nmusic_dir_1=music\n"
            f"[debug]\nperformance_logging={'true' if perf_logging else 'false'}\n",
            encoding="utf-8",
        )
    return SANDBOX_DIR


def _instrument_repair106(timings: dict):
    """Misst die Doppelgaenger-Pruefung beim Start (intern#106) ohne CC-Naht:
    die Modul-Funktionen werden vor dem Fenster-Init umwickelt. main.py
    importiert repair_subfolder_duplicates erst beim Aufruf, und die Reparatur
    ruft find_pairs ueber den Modul-Namen -> beide Wrapper greifen.

    timings bekommt:
      startup_repair106_check  find_pairs (laeuft bei JEDEM Start)
      startup_repair106_total  kompletter Aufruf inkl. Sicherung + Zusammenfuehren
      repair106_meta           Songs, Kandidaten, Dateipruefungen, Paare
    Fehlt das Modul (aelterer Stand), wird nichts gemessen."""
    try:
        import subfolder_duplicate_repair as sdr
    except ImportError:
        return
    orig_find, orig_repair = sdr.find_pairs, sdr.repair_subfolder_duplicates
    meta = timings.setdefault("repair106_meta", {})

    def find_pairs(db, find_song_file):
        calls = {"n": 0, "ms": 0.0}

        def counted(name):
            t = time.perf_counter()
            try:
                return find_song_file(name)
            finally:
                calls["n"] += 1
                calls["ms"] += (time.perf_counter() - t) * 1000.0

        t0 = time.perf_counter()
        pairs = orig_find(db, counted)
        timings["startup_repair106_check"] = (time.perf_counter() - t0) * 1000.0
        meta.update(songs=db.count(), datei_pruefungen=calls["n"],
                    datei_pruefungen_ms=round(calls["ms"], 1), paare=len(pairs))
        return pairs

    def repair(*args, **kwargs):
        t0 = time.perf_counter()
        try:
            return orig_repair(*args, **kwargs)
        finally:
            timings["startup_repair106_total"] = (time.perf_counter() - t0) * 1000.0

    sdr.find_pairs = find_pairs
    sdr.repair_subfolder_duplicates = repair


def boot(sandbox: Path, perf_logging: bool):
    """Faehrt QApplication + P29MainWindow hoch. Gibt (app, window, timings).

    timings: dict der Boot-Teilphasen (vom Runner gemessen — die in-App perf.py-
    Marken liegen in main(), das wir bewusst NICHT aufrufen).
    """
    # cwd MUSS vor dem main-Import stehen: PathManager (DB/INI) und der
    # Single-Instance-Lock leiten beide aus os.getcwd() ab.
    os.chdir(sandbox)
    if str(SRC_DIR) not in sys.path:
        sys.path.insert(0, str(SRC_DIR))

    # Verwaisten Sandbox-Lock entfernen: import main greift auf Modulebene den
    # Single-Instance-Lock; bleibt von einem abgebrochenen Lauf ein Lock liegen,
    # zeigt CC eine MODALE MessageBox und blockiert (offscreen fatal). Der
    # Lock-Name haengt am cwd-Hash (siehe main._acquire_single_instance_lock).
    import hashlib
    import tempfile
    _tag = hashlib.md5(os.path.abspath(str(sandbox)).encode("utf-8", "replace")).hexdigest()[:8]
    try:
        os.remove(os.path.join(tempfile.gettempdir(), f"callers_caddy_{_tag}.lock"))
    except OSError:
        pass

    timings = {}

    t0 = time.perf_counter()
    from PySide6.QtWidgets import QApplication
    from PySide6.QtCore import QTimer
    app = QApplication.instance() or QApplication(sys.argv[:1])
    timings["startup_qapplication"] = (time.perf_counter() - t0) * 1000.0

    # import main zieht die schweren App-Module (PySide6-Widgets, audio_engine,
    # song_db ...) und greift auf Modulebene den Lock (dank Sandbox-cwd harmlos).
    t0 = time.perf_counter()
    import perf
    import main as cc_main
    from i18n import set_language
    timings["startup_import"] = (time.perf_counter() - t0) * 1000.0

    set_language("de")
    perf.configure(perf_logging, version=cc_main.__version__)
    if perf_logging:
        perf.open_perf_file()

    _instrument_repair106(timings)

    t0 = time.perf_counter()
    window = cc_main.P29MainWindow()
    timings["startup_window_init"] = (time.perf_counter() - t0) * 1000.0

    t0 = time.perf_counter()
    window.show()
    # main() startet die Sequenzen deferred nach dem ersten Paint — nachbilden.
    QTimer.singleShot(0, window._init_sequences)
    QApplication.processEvents()
    timings["startup_show"] = (time.perf_counter() - t0) * 1000.0

    # Sicherheitsnetz gegen unerwartete MODALE Dialoge (Feedback, Tutorial,
    # Bestaetigungen ...): ein wiederkehrender Timer schliesst jeden Modal-/
    # Popup-Dialog sofort. Verhindert Haenger im unbeaufsichtigten Lauf; feuert
    # auch in verschachtelten exec()-Eventloops.
    def _dismiss_modals():
        w = app.activeModalWidget() or app.activePopupWidget()
        if w is not None:
            w.close()
    _guard = QTimer()
    _guard.setInterval(200)
    _guard.timeout.connect(_dismiss_modals)
    _guard.start()
    window._bench_modal_guard = _guard   # Referenz halten (kein GC)

    timings["cc_version"] = cc_main.__version__
    return app, window, timings


# --- Szenario-Schritte -------------------------------------------------------

def find_target_song(window, title_sub: str):
    """Sucht einen Song per Titel-Teilstring (case-insensitive) in der geladenen
    Liste. Default-Ziel ist "Sounds Of Silence": voll gepflegt (Lyrics, Sync,
    Sequenzen) und weit genug unten fuer eine realistische Suche. Rueckgabe:
    Song oder None."""
    tl = title_sub.lower().strip()
    for s in getattr(window.song_list, "_all_songs", []) or []:
        t = (getattr(s, "title", "") or getattr(s, "filename", "") or "")
        if tl in t.lower():
            return s
    return None


def row_in_filtered(window, song) -> int:
    """Position des Songs in der aktuell gefilterten Liste (0-basiert) oder -1."""
    sid = getattr(song, "id", None)
    for idx, s in enumerate(getattr(window.song_list, "_filtered", []) or []):
        if getattr(s, "id", None) == sid:
            return idx
    return -1


# Feste Referenz-Songs (voll gepflegt, weit genug unten fuer echte Suche):
#   ("Kurzname", Titel-Teilstring, Suchbegriff)
# - Patter:  "Tu Es Foutu"       (Suche "tu"    -> ~12 Treffer)
# - Singing: "Sounds Of Silence" (Suche "sound" -> ~3 Treffer; Lyrics/Sync/Seq)
TARGETS = [
    ("patter",  "Tu Es Foutu",       "tu"),
    ("singing", "Sounds Of Silence", "sound"),
]

# Contains-Filter fuer Schritt 8 (haeufiger Mainstream-Call). Findet er nichts,
# wird trotzdem die Filter-Operation gemessen (Treffer stehen im meta).
SEQ_FILTER_TERM = "Square Thru"


def _measure(bench: Bench, name, fn, wait_pred=None, timeout_ms=10000):
    """Fuehrt fn() aus und misst die Wandzeit. Mit wait_pred wird bis zur
    Bedingung gepumpt (Rueckgabe erreicht?), sonst einmal Events gepumpt.
    Druckt eine Live-Fortschrittszeile (auch bei --repeat sichtbar)."""
    print(f"  .. {name} ...", flush=True)
    import faulthandler
    faulthandler.dump_traceback_later(60, exit=True)  # Watchdog: Stack bei Haenger
    t0 = time.perf_counter()
    fn()
    ok = bench.wait_until(wait_pred, timeout_ms=timeout_ms) if wait_pred else True
    if wait_pred is None:
        bench.pump()
    faulthandler.cancel_dump_traceback_later()
    return (time.perf_counter() - t0) * 1000.0, ok


def _select_play_stop(bench: Bench, out: list, title_sub: str, suffix: str) -> bool:
    """Auswahl -> Play -> Stop fuer einen Song. Haengt drei Eintraege an out
    (song_select{suffix}, song_play{suffix}, song_stop{suffix}). Rueckgabe:
    True wenn geladen (Play/Stop wurden dann gemessen)."""
    window = bench.window
    engine = window.player.engine
    target = find_target_song(window, title_sub)
    if not target:
        out.append({"name": f"song_select{suffix}", "ms": 0.0, "ok": False,
                    "meta": {"grund": f"{title_sub} nicht gefunden"}})
        return False

    engine.stop()
    ms, loaded = _measure(bench, f"song_select{suffix}",
                          lambda: window._on_song_selected(target.id),
                          engine.is_loaded, timeout_ms=15000)
    out.append({"name": f"song_select{suffix}", "ms": ms, "ok": loaded, "meta": {
        "song": getattr(target, "title", "") or getattr(target, "filename", ""),
        "geladen": loaded}})
    if not loaded:
        out.append({"name": f"song_play{suffix}", "ms": 0.0, "ok": False,
                    "meta": {"grund": "Datei nicht geladen (MP3 im Musikordner?)"}})
        return False

    # Play-Latenz (Aufruf -> is_playing): synchroner play()-Aufwand
    # (Feed + Preprocess + WSOLA-Warmup).
    ms, playing = _measure(bench, f"song_play{suffix}", window.player._on_play,
                           engine.is_playing, timeout_ms=10000)
    out.append({"name": f"song_play{suffix}", "ms": ms, "ok": playing,
                "meta": {"is_playing": playing}})

    ms, stopped = _measure(bench, f"song_stop{suffix}", window.player._on_stop,
                           lambda: not engine.is_playing(), timeout_ms=5000)
    out.append({"name": f"song_stop{suffix}", "ms": ms, "ok": stopped,
                "meta": {"is_playing": engine.is_playing()}})
    return True


def _lyrics_dynamic(bench: Bench, out: list):
    """Singing-spezifisch (BL-173): Dynamic-Lyrics an/aus — ersetzt den
    Figuren-Text live durch die Sequence-View-Sequenzen. Voraussetzung:
    Lyrics + SyncPoints + Figuren + Sequenzen (Sounds Of Silence erfuellt das).
    Gating-Grund landet im meta, falls Dynamic nicht anwendbar ist."""
    window = bench.window
    lw = window.lyrics_widget
    btn = getattr(lw, "_btn_dynamic", None)
    if btn is None:
        out.append({"name": "lyrics_dynamic_on", "ms": 0.0, "ok": False,
                    "meta": {"grund": "kein Dynamic-Button"}})
        return
    reason = lw._dynamic_gating_reason() if hasattr(lw, "_dynamic_gating_reason") else "?"

    ms, _ = _measure(bench, "lyrics_dynamic_on", lambda: btn.setChecked(True))
    enabled = bool(getattr(lw, "_dynamic_enabled", False))
    out.append({"name": "lyrics_dynamic_on", "ms": ms, "ok": enabled,
                "meta": {"aktiviert": enabled, "gating": reason}})

    ms, _ = _measure(bench, "lyrics_dynamic_off", lambda: btn.setChecked(False))
    out.append({"name": "lyrics_dynamic_off", "ms": ms, "ok": True,
                "meta": {"aktiviert": bool(getattr(lw, "_dynamic_enabled", False))}})


def run_interactive(bench: Bench) -> list[dict]:
    """Schritte 2-8 + Singing-Block (ein Durchlauf). Gibt rohe Schritt-Eintraege
    zurueck (ohne Ausgabe) — scenario() aggregiert bei --repeat den Median."""
    window = bench.window
    fb = window.song_list._filter_bar
    engine = window.player.engine
    out: list[dict] = []

    # --- Schritt 2: Suche je Referenz-Song (Typ-Filter "Alle") ---------------
    for name, title_sub, query in TARGETS:
        fb.edit_search.clear()
        bench.pump()
        ms, _ = _measure(bench, f"search_{name}",
                         lambda q=query: fb.edit_search.setText(q))
        hits = len(getattr(window.song_list, "_filtered", []) or [])
        target = find_target_song(window, title_sub)
        row = row_in_filtered(window, target) if target else -1
        out.append({"name": f"search_{name}", "ms": ms, "ok": target is not None,
                    "meta": {"query": query, "treffer": hits, "ziel": title_sub,
                             "gefunden": target is not None,
                             "zeile_in_treffern": row}})

    # --- Schritte 3-5: Patter "Tu Es Foutu" auswaehlen / Play / Stop ---------
    _select_play_stop(bench, out, TARGETS[0][1], "")

    # --- Schritt 6: Lokation waehlen (Dialog umgehen -> _set_current_location)
    locs = window.db.get_all_locations() or []
    if locs:
        loc = next((l for l in locs if window._location_program_ids(l)), locs[0])
        ms, _ = _measure(bench, "location_apply",
                         lambda: window._set_current_location(loc))
        out.append({"name": "location_apply", "ms": ms, "ok": True,
                    "meta": {"lokation": getattr(loc, "name", ""),
                             "hat_programme": bool(window._location_program_ids(loc))}})
    else:
        out.append({"name": "location_apply", "ms": 0.0, "ok": False,
                    "meta": {"grund": "keine Lokation in DB"}})

    # --- Schritt 7: Sequenz-Widget aufbauen (Reload) -------------------------
    sw = window.sequences_widget
    ms, _ = _measure(bench, "sequences_build", sw.load_sequences)
    seq_count = len(sw.get_filtered_seq_ids() or [])
    out.append({"name": "sequences_build", "ms": ms, "ok": seq_count > 0,
                "meta": {"sequenzen": seq_count}})

    # --- Schritt 8: Sequenzen filtern (Contains) -----------------------------
    ms, _ = _measure(bench, "sequences_filter",
                     lambda: sw.set_contains_filter(SEQ_FILTER_TERM))
    filt_count = len(sw.get_filtered_seq_ids() or [])
    out.append({"name": "sequences_filter", "ms": ms, "ok": True,
                "meta": {"contains": SEQ_FILTER_TERM, "treffer": filt_count}})
    sw.set_contains_filter("")   # Filter zuruecksetzen (fuer den naechsten Lauf)
    bench.pump()

    # --- Singing-Block: "Sounds Of Silence" (voll gepflegt) ------------------
    # Auswahl laedt zugleich Lyrics + SyncPoints; danach Play/Stop und die
    # Dynamic-Lyrics (Figuren-Text -> Sequenzen). Suchfeld vorher leeren, damit
    # der Song sichtbar/auffindbar ist.
    fb.edit_search.clear()
    bench.pump()
    if _select_play_stop(bench, out, TARGETS[1][1], "_singing"):
        _lyrics_dynamic(bench, out)

    return out


def scenario(bench: Bench, timings: dict):
    """Spielt den kompletten Nutzer-Ablauf ab: Schritt 1 (Start, einmalig) +
    Schritte 2-8 (interaktiv, bei --repeat mehrfach -> Median je Schritt)."""
    window = bench.window

    # --- Schritt 1: App-Start (Teilphasen aus dem Boot; einmalig) ------------
    for phase in ("startup_qapplication", "startup_import",
                  "startup_window_init", "startup_show"):
        bench.add(phase, timings.get(phase, 0.0))
    bench.add("startup_total", sum(timings.get(p, 0.0) for p in
              ("startup_qapplication", "startup_import",
               "startup_window_init", "startup_show")))
    # Doppelgaenger-Pruefung (intern#106) — Teil von startup_window_init
    if "startup_repair106_total" in timings:
        meta = timings.get("repair106_meta", {})
        bench.add("startup_repair106_check",
                  timings.get("startup_repair106_check", 0.0), meta=meta)
        bench.add("startup_repair106_total",
                  timings["startup_repair106_total"], meta=meta)

    bench.wait_until(lambda: getattr(window.song_list, "_all_songs", None)
                     is not None, timeout_ms=3000)
    if not len(getattr(window.song_list, "_all_songs", []) or []):
        bench.add("songlist_search", 0.0, ok=False,
                  meta={"grund": "keine Songs in DB"})
        return

    # --- Schritte 2-8: interaktiv, N-fach -> Median --------------------------
    n = max(1, bench.repeat)
    runs = [run_interactive(bench) for _ in range(n)]

    order = [e["name"] for e in runs[0]]
    by_name: dict[str, list] = {}
    for r in runs:
        for e in r:
            by_name.setdefault(e["name"], []).append(e)
    for name in order:
        entries = by_name.get(name, [])
        samples = [e["ms"] for e in entries]
        med = statistics.median(samples) if samples else 0.0
        ok = all(e["ok"] for e in entries)
        meta = dict(entries[-1].get("meta") or {})
        if n > 1:
            meta["n"] = n
            meta["samples_ms"] = [round(s, 1) for s in samples]
        bench.add(name, med, ok=ok, meta=meta)


# --- Report ------------------------------------------------------------------

def write_report(bench: Bench, timings: dict, sandbox: Path, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    label_slug = ""
    if bench.label:
        safe = "".join(c if c.isalnum() else "-" for c in bench.label).strip("-")
        label_slug = f"_{safe}" if safe else ""
    out = out_dir / f"bench_{stamp}{label_slug}.json"

    env = {
        "os": platform.platform(),
        "python": platform.python_version(),
        "cpu": platform.processor() or platform.machine(),
    }
    # Env-Header aus der App wiederverwenden (Version, CPU, RAM, Audio), wenn da.
    try:
        from system_report import generate_compact_header
        env["cc_header"] = generate_compact_header(timings.get("cc_version", "?"))
    except Exception as e:
        env["cc_header_error"] = str(e)

    doc = {
        "run": {
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "cc_version": timings.get("cc_version", "?"),
            "label": bench.label or "",
            "db": str((sandbox / "callers_caddy.db")),
            "repeat": bench.repeat,
        },
        "env": env,
        "steps": bench.steps,
    }
    out.write_text(json.dumps(doc, indent=2, ensure_ascii=False), encoding="utf-8")
    return out


# --- CLI ---------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description="Callers-Caddy Performance-Benchmark")
    ap.add_argument("--db", help="Pfad zur zu testenden DB (leer = leere DB)")
    ap.add_argument("--settings", help="INI, aus der die Einstellungen geklont "
                    "werden (Default: callers_caddy.ini neben --db)")
    ap.add_argument("--label", default="", help="Label fuer den Lauf (ins JSON)")
    ap.add_argument("--repeat", type=int, default=1,
                    help="Anzahl Durchlaeufe (Median-Auswertung folgt)")
    ap.add_argument("--out", default=str(RESULTS_DIR),
                    help="Ausgabeordner fuer die JSON-Reports")
    ap.add_argument("--perf-log", action="store_true",
                    help="zusaetzlich das in-App perf.py-Log (logs/perf/) schreiben")
    args = ap.parse_args()
    out_dir = Path(args.out)

    print(f"Callers-Caddy Benchmark  (Repo: {REPO_ROOT})")
    print(f"  DB:    {args.db or '(leer)'}")
    print(f"  Label: {args.label or '(kein)'}\n")

    sandbox = prepare_sandbox(args.db, args.settings, args.perf_log)
    app, window, timings = boot(sandbox, args.perf_log)
    bench = Bench(app, window, args.label, args.repeat)

    print("Schritte:")
    scenario(bench, timings)

    out = write_report(bench, timings, sandbox, out_dir)
    print(f"\nReport: {out}")

    # sauber schliessen, ohne app.exec()
    window.close()
    app.processEvents()
    return 0


if __name__ == "__main__":
    sys.exit(main())
