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
    # Sprache sicherstellen (kein Erststart-Dialog) + Perf-Logging nach Flag.
    if not s.contains("display/language"):
        s.setValue("display/language", "de")
    s.setValue("debug/performance_logging", "true" if perf_logging else "false")
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

    t0 = time.perf_counter()
    window = cc_main.P29MainWindow()
    timings["startup_window_init"] = (time.perf_counter() - t0) * 1000.0

    t0 = time.perf_counter()
    window.show()
    # main() startet die Sequenzen deferred nach dem ersten Paint — nachbilden.
    QTimer.singleShot(0, window._init_sequences)
    QApplication.processEvents()
    timings["startup_show"] = (time.perf_counter() - t0) * 1000.0

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


def scenario(bench: Bench, timings: dict):
    """Spielt den Nutzer-Ablauf ab. v1: Schritt 1 (Start) + Schritt 2 (Suche
    je Referenz-Song).

    Schritte 3-8 (Song waehlen, Play, Stop, Lokation, Sequenz-Widget, Filter)
    folgen inkrementell — jeder mit der beim Bau festgezurrten CC-Naht. Siehe
    Issue #72 fuer die Gesamtliste.
    """
    window = bench.window

    # --- Schritt 1: App-Start (Teilphasen aus dem Boot) ----------------------
    for phase in ("startup_qapplication", "startup_import",
                  "startup_window_init", "startup_show"):
        bench.add(phase, timings.get(phase, 0.0))
    startup_total = sum(timings.get(p, 0.0) for p in
                        ("startup_qapplication", "startup_import",
                         "startup_window_init", "startup_show"))
    bench.add("startup_total", startup_total)

    # sicherstellen, dass die Songliste steht
    bench.wait_until(lambda: getattr(window.song_list, "_all_songs", None)
                     is not None, timeout_ms=3000)
    song_count = len(getattr(window.song_list, "_all_songs", []) or [])
    if not song_count:
        bench.add("songlist_search", 0.0, ok=False,
                  meta={"grund": "keine Songs in DB"})
        return

    # --- Schritt 2: Suche in der Songliste (je Referenz-Song) ----------------
    # Typ-Filter bleibt auf "Alle" (Default), damit Patter UND Singing sichtbar
    # sind. Zwischen den Suchen wird das Suchfeld geleert.
    fb = window.song_list._filter_bar
    for name, title_sub, query in TARGETS:
        fb.edit_search.clear()
        bench.pump()
        t0 = time.perf_counter()
        fb.edit_search.setText(query)     # loest synchron _apply_filter aus
        bench.pump()
        dt = (time.perf_counter() - t0) * 1000.0
        hits = len(getattr(window.song_list, "_filtered", []) or [])
        target = find_target_song(window, title_sub)
        row = row_in_filtered(window, target) if target else -1
        bench.add(f"search_{name}", dt, ok=(target is not None), meta={
            "query": query, "treffer": hits,
            "ziel": title_sub, "gefunden": target is not None,
            "zeile_in_treffern": row,
        })

    # --- Schritt 3+4: Song auswaehlen + Play (Patter "Tu Es Foutu") ----------
    # Keine neue CC-Naht: wir rufen die vorhandenen Callbacks und pollen
    # engine.is_loaded() / engine.is_playing() (beide Zustaende existieren).
    _select_and_play(bench, TARGETS[0][1])   # ("Tu Es Foutu")


def _select_and_play(bench: Bench, title_sub: str):
    window = bench.window
    engine = window.player.engine
    target = find_target_song(window, title_sub)
    if not target:
        bench.add("song_select", 0.0, ok=False, meta={"grund": f"{title_sub} nicht gefunden"})
        return

    # Schritt 3: Auswahl (wie ein Klick in der Liste) -> laedt die Datei.
    # engine.load() ist synchron (sf.read), is_loaded() flippt danach sofort.
    engine.stop()  # sicherer Ausgangszustand
    t0 = time.perf_counter()
    window._on_song_selected(target.id)      # Songliste-Callback (1:1 wie Klick)
    loaded = bench.wait_until(engine.is_loaded, timeout_ms=15000)
    dt = (time.perf_counter() - t0) * 1000.0
    bench.add("song_select", dt, ok=loaded, meta={
        "song": getattr(target, "title", "") or getattr(target, "filename", ""),
        "geladen": loaded,
    })
    if not loaded:
        bench.add("song_play", 0.0, ok=False, meta={"grund": "Datei nicht geladen (MP3 im Musikordner?)"})
        return

    # Schritt 4: Play-Latenz (Aufruf -> is_playing). Enthaelt den synchronen
    # play()-Aufwand (Feed + Preprocess + WSOLA-Warmup) — nah an der gefuehlten
    # Startverzoegerung. Ohne konfigurierte Rules laeuft der Orchestrator direkt.
    t0 = time.perf_counter()
    window.player._on_play()                 # Play-Button-Pfad (Orchestrator)
    playing = bench.wait_until(engine.is_playing, timeout_ms=10000)
    dt = (time.perf_counter() - t0) * 1000.0
    bench.add("song_play", dt, ok=playing, meta={"is_playing": playing})

    # Aufraeumen: Stream stoppen (Schritt 5 "Stop" wird spaeter eigens gemessen).
    engine.stop()
    bench.pump(50)


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
