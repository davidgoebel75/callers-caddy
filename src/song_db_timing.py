"""Beats je Call nach CALLERLAB (intern#164): Tabelle call_timing in der DB.

Mixin: SongDatabase erbt die Methoden. Braucht nur self._conn.

Quelle ist src/callerlab_timing.json (erzeugt von tools/beats/build_callerlab_timing.py
aus der Pflegedatei). Beim Start ersetzt seed_call_timing() die Tabelle komplett, wenn
die Version der Datei nicht zur Marke callerlab_timing_version in app_meta passt oder die
Tabelle leer ist. Die Daten sind reine Referenz; Nutzer pflegen hier nichts, deshalb kein
Backup vor dem Ersetzen.
"""
import json
import os

TIMING_FILE = "callerlab_timing.json"
META_KEY = "callerlab_timing_version"
_INT_COLS = ("beats", "beats_bis", "anything_ab")
_COLS = ("programm", "call", "entity_ids", "variante", "typ", "beats", "beats_bis",
         "anything_ab", "quelle", "bemerkung", "standard", "variante_regel")


def _db_row(r: dict) -> tuple:
    out = []
    for c in _COLS:
        v = (r.get(c) or "").strip()
        if c in _INT_COLS:
            out.append(int(v) if v else None)
        elif c == "standard":
            out.append(1 if v == "1" else 0)
        else:
            out.append(v)
    return tuple(out)


class CallTimingMixin:
    """Befuellen und Lesen der Beat-Tabelle."""

    def seed_call_timing(self, path: str | None = None, force: bool = False) -> bool:
        """Spielt callerlab_timing.json ein, wenn noetig. True = Tabelle ersetzt."""
        path = path or os.path.join(os.path.dirname(os.path.abspath(__file__)), TIMING_FILE)
        if not os.path.exists(path):
            print(f"[SongDB] Beat-Tabelle uebersprungen: {TIMING_FILE} nicht gefunden")
            return False
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        version = str(data.get("version", ""))
        row = self._conn.execute(
            "SELECT value FROM app_meta WHERE key=?", (META_KEY,)).fetchone()
        filled = self._conn.execute("SELECT 1 FROM call_timing LIMIT 1").fetchone()
        if not force and filled and row and row[0] == version:
            return False
        rows = [_db_row(r) for r in data.get("rows", [])]
        with self._conn:
            self._conn.execute("DELETE FROM call_timing")
            self._conn.executemany(
                f"INSERT INTO call_timing (id, {', '.join(_COLS)}) "
                f"VALUES (?, {', '.join('?' * len(_COLS))})",
                [(i, *r) for i, r in enumerate(rows, start=1)])
            self._conn.execute(
                "INSERT INTO app_meta (key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (META_KEY, version))
        print(f"[SongDB] Beat-Tabelle eingespielt: {len(rows)} Zeilen (version {version})")
        return True

    def get_call_timing_rows(self) -> list[dict]:
        """Alle Zeilen in Dateireihenfolge, als Dicts fuer caddy.beats.calc.BeatTable."""
        cur = self._conn.execute(
            f"SELECT {', '.join(_COLS)} FROM call_timing ORDER BY id")
        return [dict(zip(_COLS, r)) for r in cur.fetchall()]
