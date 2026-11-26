"""GUI-Pruefung Square Flow + Sequenz-Detail mit echter Engine (intern#263, PR #196).

Aufruf (aus dem Repo-Stamm):
  python -I tools/square_flow_gui_check.py <app-db> [--keep]

<app-db>  App-DB (z. B. callers_caddy.db aus dem Test-Ordner). Wird nur lesend geoeffnet
          und per SQLite-Backup in einen Temp-Ordner kopiert; geprueft wird an der Kopie.
--keep    Temp-Ordner mit DB-Kopie und INI danach nicht loeschen.
Engine: CC_TAM_CLI oder src/caddy/choreo/bin/tam_cli.exe.

Baut Sequenz-Detail und Square Flow wie main.py zusammen. Jede "Sitzung" baut die
Widgets neu (neuer Worker, neue Engine), wie ein Neustart der App. Szenarien:
  1. erste Sitzung, 8 unbekannte Sequenzen, Dock sichtbar: Ergebnis, Takte, anim_z
  2. neue Sitzung: alles aus der DB, gleiches Ergebnis, Engine bleibt aus
  3. Speicher des Sequenz-Details gleich Einzelabfrage
  4. 30 schnelle Spruenge: letztes Ergebnis gehoert zur gezeigten Sequenz
  5. echter Engine-Timeout bei verstecktem Dock: nichts in sequence_choreo
  6. naechste Sitzung, Dock versteckt: rechnet neu und speichert
  7. Dock sichtbar: Animation da
Exit-Code 0 = alles OK, 1 = mindestens ein Fehler.
"""
import argparse
import os
import random
import shutil
import sqlite3
import sys
import tempfile
import time

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
ap.add_argument("db")
ap.add_argument("--keep", action="store_true")
ARGS = ap.parse_args()

TMP = tempfile.mkdtemp(prefix="cc_sf_check_")
DB = os.path.join(TMP, "callers_caddy.db")
_src = sqlite3.connect(f"file:{os.path.abspath(ARGS.db)}?mode=ro", uri=True)
_dst = sqlite3.connect(DB)
_src.backup(_dst)
_dst.close()
_src.close()

from PySide6.QtCore import QSettings  # noqa: E402
from PySide6.QtWidgets import QApplication, QWidget, QHBoxLayout  # noqa: E402

app = QApplication.instance() or QApplication(sys.argv)

from song_db import SongDatabase                      # noqa: E402
from sequences_widget import SequenceViewWidget       # noqa: E402
from caddy.choreo.square_flow_widget import SquareFlowWidget  # noqa: E402
from caddy.choreo.flow_worker import SquareFlowWorker  # noqa: E402
from caddy.choreo.engine import TamEngine             # noqa: E402
from caddy.choreo import flow_info                    # noqa: E402
from caddy.settings import ini_keys                   # noqa: E402

settings = QSettings(os.path.join(TMP, "check.ini"), QSettings.IniFormat)
settings.setValue(ini_keys.SQUARE_FLOW_ENABLED, True)
settings.sync()

FAILS = []


def check(cond, text):
    print(("  OK   " if cond else "  FEHLER ") + text)
    if not cond:
        FAILS.append(text)


def spin(sec):
    end = time.perf_counter() + sec
    while time.perf_counter() < end:
        app.processEvents()
        time.sleep(0.005)


def wait_until(pred, timeout):
    end = time.perf_counter() + timeout
    while time.perf_counter() < end:
        app.processEvents()
        if pred():
            return True
        time.sleep(0.005)
    return False


class Session:
    """Sequenz-Detail und Square Flow, verdrahtet wie in main.py."""

    def __init__(self, ids, dock_visible=True, engine_timeout=None):
        self.db = SongDatabase(DB)
        self.host = QWidget()
        lay = QHBoxLayout(self.host)
        self.view = SequenceViewWidget(db=self.db, settings=settings)
        self.flow = SquareFlowWidget(settings=settings, db_path=DB)
        lay.addWidget(self.view)
        lay.addWidget(self.flow)
        self.results = []                        # (calls, result) je result_ready
        self.flow.result_ready.connect(self._on_result)
        self.view.on_current_sequence_changed = self.push
        if engine_timeout is not None:
            w = SquareFlowWorker(DB, engine=TamEngine(timeout=engine_timeout), parent=self.flow)
            w.ready.connect(self.flow._on_ready)
            self.flow._worker = w
        self.host.resize(1400, 800)
        self.host.show()
        if not dock_visible:
            self.flow.hide()
        spin(0.2)
        t0 = time.perf_counter()
        self.view.set_sequence(self.db, ids, 0)
        self.set_ms = (time.perf_counter() - t0) * 1000
        self.push()

    def _on_result(self, calls, result):
        self.results.append((tuple(calls), result))
        self.view.set_flow_info(calls, flow_info.detail_info(calls, result))

    def push(self):
        v = self.view
        self.flow.set_sequence(v.current_calls(), v.current_sequence_type(),
                               seq_id=v.current_sequence_id())

    def wait_result(self, timeout=60):
        calls = tuple(c for c in self.view.current_calls() if c and str(c).strip())
        ok = wait_until(lambda: any(c == calls and r is not None
                                    for c, r in self.results), timeout)
        for c, r in reversed(self.results):
            if c == calls and r is not None:
                return ok, r
        return ok, None

    def engine_starts(self):
        w = self.flow._worker
        return getattr(w._engine, "start_count", 0) if w and w._engine else 0

    def next(self):
        t0 = time.perf_counter()
        self.view._on_next()
        return (time.perf_counter() - t0) * 1000

    def close(self):
        self.flow.shutdown()
        self.host.close()
        self.host.deleteLater()
        spin(0.3)
        self.db._conn.close()


def cache_rows(ids):
    con = sqlite3.connect(DB)
    rows = {r[0]: r[1:] for r in con.execute(
        f"SELECT sequence_id, anim_z IS NULL, length(anim_z) FROM sequence_choreo "
        f"WHERE sequence_id IN ({','.join('?' * len(ids))})", ids)}
    con.close()
    return rows


def pick_ids(n, exclude=()):
    con = sqlite3.connect(DB)
    cand = [r[0] for r in con.execute(
        "SELECT s.id FROM sequences s LEFT JOIN sequence_choreo c ON c.sequence_id = s.id "
        "WHERE c.sequence_id IS NULL ORDER BY s.id")]
    con.close()
    random.seed(196)
    cand = [i for i in cand if i not in exclude]
    return sorted(random.sample(cand, n))


# ---------------------------------------------------------------------------
print("\n== 1. Erste Sitzung: 8 unbekannte Sequenzen, Dock sichtbar ==")
IDS = pick_ids(8)
s = Session(IDS)
print(f"  set_sequence mit {len(IDS)} Sequenzen: {s.set_ms:.0f} ms")
first = {}
switch_ms = []
for i, sid in enumerate(IDS):
    if i:
        switch_ms.append(s.next())
    ok, r = s.wait_result()
    check(ok and r is not None, f"Sequenz {sid}: Ergebnis da")
    first[sid] = (tuple(s.view.current_calls()), r)
    check(s.view._flow is not None, f"Sequenz {sid}: Takte/Warnung im Sequenz-Detail gesetzt")
print(f"  Wechsel im Hauptthread: max {max(switch_ms):.0f} ms, Mittel "
      f"{sum(switch_ms) / len(switch_ms):.0f} ms")
starts1 = s.engine_starts()
s.close()
rows = cache_rows(IDS)
check(len(rows) == len(IDS), f"alle {len(IDS)} Sequenzen in sequence_choreo ({len(rows)})")
check(all(not null for null, _ in rows.values()), "anim_z überall gesetzt (Animation oder NO_ANIM)")
print(f"  anim_z-Größen: {sorted(l for _, l in rows.values())}")

# ---------------------------------------------------------------------------
print("\n== 2. Neue Sitzung, gleiche Sequenzen: alles aus der DB, Engine bleibt aus ==")
s = Session(IDS)
for i, sid in enumerate(IDS):
    if i:
        s.next()
    ok, r = s.wait_result(10)
    check(ok and r is not None and r.get("cached"), f"Sequenz {sid}: aus der DB")
    if r is not None:
        a, b = first[sid][1], r
        same = (a.get("card_beats") == b.get("card_beats")
                and a.get("urteil") == b.get("urteil")
                and bool(a.get("animation")) == bool(b.get("animation")))
        check(same, f"Sequenz {sid}: Beats/Urteil/Animation wie in Sitzung 1")
spin(0.5)
check(s.engine_starts() == 0, f"Engine nicht gestartet (Starts: {s.engine_starts()})")
s.close()

# ---------------------------------------------------------------------------
print("\n== 3. Sequenz-Detail: Speicher gleich Einzelabfrage ==")
s = Session(IDS)
for i, sid in enumerate(IDS):
    if i:
        s.next()
    fresh = s.db.get_sequence_calls(sid)
    raw = s.db.get_sequence_raw(sid)
    calls_c, typ_c, diff_c = s.view._detail(sid)
    check(list(calls_c) == list(fresh) and (typ_c or "") == raw["seq_type"]
          and (diff_c or "") == raw["difficulty"], f"Sequenz {sid}: Detail = DB")
s.close()

# ---------------------------------------------------------------------------
print("\n== 4. Schnelles Durchklicken (30 Sprünge ohne Warten) ==")
s = Session(IDS)
for _ in range(30):
    s.view._current_idx = random.randrange(len(IDS))
    s.view._update_content()
    s.view._notify_current_sequence_changed()
    app.processEvents()
ok, r = s.wait_result(30)
spin(1.0)
last_calls, last_r = s.results[-1]
check(ok and last_calls == tuple(c for c in s.view.current_calls() if str(c).strip()),
      "letztes Ergebnis gehört zur gezeigten Sequenz")
check(s.view._flow is not None, "Sequenz-Detail hat Takte zur gezeigten Sequenz")
s.close()

# ---------------------------------------------------------------------------
print("\n== 5. Timeout bei verstecktem Dock: nichts in der DB ==")
IDS_T = pick_ids(2, exclude=IDS)
s = Session(IDS_T, dock_visible=False, engine_timeout=0.001)
for i, sid in enumerate(IDS_T):
    if i:
        s.next()
    ok, r = s.wait_result(30)
    tr = bool(r and r.get("transient"))
    print(f"  Sequenz {sid}: transient={tr}, error={r and r.get('error')!r}")
    check(tr, f"Sequenz {sid}: Lauf ist als Abbruch markiert")
s.close()
check(cache_rows(IDS_T) == {}, "keine Zeile in sequence_choreo für die Abbrüche")

print("\n== 6. Nächste Sitzung, Dock weiter versteckt: rechnet neu und speichert ==")
s = Session(IDS_T, dock_visible=False)
for i, sid in enumerate(IDS_T):
    if i:
        s.next()
    ok, r = s.wait_result(60)
    check(ok and r is not None and not r.get("cached") and not r.get("transient"),
          f"Sequenz {sid}: neu gerechnet, kein Abbruch")
starts = s.engine_starts()
s.close()
check(starts >= 1, f"Engine lief ({starts} Start)")
rows = cache_rows(IDS_T)
check(len(rows) == len(IDS_T), "jetzt in sequence_choreo")
print(f"  anim_z NULL (Dock versteckt, keine Animation angefordert): "
      f"{[null for null, _ in rows.values()]}")

print("\n== 7. Dock wieder sichtbar: Animation wird nachgeholt ==")
s = Session(IDS_T)
for i, sid in enumerate(IDS_T):
    if i:
        s.next()
    ok = wait_until(lambda: bool(s.flow._result and s.flow._result.get("animation")), 60)
    check(ok, f"Sequenz {sid}: Animation da")
s.close()
rows = cache_rows(IDS_T)
check(all(not null for null, _ in rows.values()), "anim_z jetzt gesetzt")

print("\n" + ("ALLES OK" if not FAILS else f"{len(FAILS)} FEHLER:\n  - " + "\n  - ".join(FAILS)))
if ARGS.keep:
    print(f"DB-Kopie: {DB}")
else:
    shutil.rmtree(TMP, ignore_errors=True)
sys.exit(1 if FAILS else 0)
