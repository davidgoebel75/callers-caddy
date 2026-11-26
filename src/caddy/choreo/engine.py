"""Engine-Client fuer `tam_cli.exe` (Taminations ohne Flutter, intern#163/#247).

Schnittstelle: je Anfrage eine JSON-Zeile auf stdin, je Antwort eine JSON-Zeile auf stdout
(Felder siehe tam-headless/bin/tam_cli.dart: ok, fail_pos, error, warnings, beats, alt_used,
tam_calls, end_ok, end_msg, optional positions/animation).

Regeln (intern#247):
- Der Prozess startet erst mit der ersten Anfrage, nie auf Vorrat.
- Niedrige Prioritaet (BELOW_NORMAL) und kein Konsolenfenster.
- `run()` blockiert: nur aus einem Hintergrund-Thread aufrufen, nie aus dem UI-Thread.
- Antwortet die Engine nicht binnen `timeout` Sekunden oder liefert kein JSON, wird sie neu
  gestartet und die Anfrage als Abbruch beantwortet. Fehlt die Exe, ist `available()` False
  und das Feature faellt weg; Callers Caddy laeuft ohne sie unveraendert.
"""
import json
import os
import queue
import subprocess
import sys
import threading

QT_FREE = True

EXE_NAME = "tam_cli.exe" if os.name == "nt" else "tam_cli"
_BELOW_NORMAL = 0x00004000
_NO_WINDOW = 0x08000000


def find_engine():
    """Pfad zur Engine oder None.
    Reihenfolge: Umgebungsvariable CC_TAM_CLI; im Build neben der EXE unter `choreo/`;
    in der Entwicklung `src/caddy/choreo/bin/` (nicht eingecheckt)."""
    cands = [os.environ.get("CC_TAM_CLI")]
    if getattr(sys, "frozen", False):
        cands.append(os.path.join(os.path.dirname(sys.executable), "choreo", EXE_NAME))
    cands.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "bin", EXE_NAME))
    found = next((p for p in cands if p and os.path.isfile(p)), None)
    return os.path.abspath(found) if found else None


def failed_response(request, error):
    """Antwort im Format von tam_cli fuer einen Abbruch ohne Engine-Ergebnis.
    transient: kein Urteil der Engine (fehlt, Timeout, keine JSON-Antwort); ein neuer
    Lauf kann anders ausgehen (intern#263, Marker "keine Animation" nur ohne)."""
    return {"id": request.get("id"), "ok": False, "fail_pos": None, "error": error,
            "warnings": [], "beats": [], "alt_used": [], "tam_calls": [],
            "end_ok": None, "end_msg": "", "transient": True}


class TamEngine:
    """Ein tam_cli-Dauerprozess. Thread-sicher: Anfragen werden nacheinander bedient."""

    def __init__(self, path=None, timeout=30.0):
        self._path = os.path.abspath(path) if path else find_engine()
        self._timeout = timeout
        self._proc = None
        self._q = None
        self._lock = threading.Lock()
        self._version = None
        self.start_count = 0                 # wie oft der Prozess gestartet wurde (Perf-Marken)

    def available(self):
        return bool(self._path) and os.path.isfile(self._path)

    @property
    def path(self):
        return self._path

    def _start(self):
        flags = (_BELOW_NORMAL | _NO_WINDOW) if os.name == "nt" else 0
        self._proc = subprocess.Popen(
            [self._path], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, text=True, encoding="utf-8", creationflags=flags)
        self.start_count += 1
        self._q = queue.Queue()
        threading.Thread(target=self._read, args=(self._proc, self._q), daemon=True,
                         name="tam_cli-reader").start()

    @staticmethod
    def _read(proc, q):
        try:
            for line in proc.stdout:
                q.put(line)
        except (OSError, ValueError):
            pass
        q.put(None)

    def _kill(self):
        p, self._proc = self._proc, None
        if p is not None:
            try:
                p.kill()
            except OSError:
                pass

    def _raw(self, line):
        """Eine Zeile senden, eine Zeile lesen; None bei Zeitueberschreitung oder Absturz."""
        if self._proc is None or self._proc.poll() is not None:
            self._start()
        try:
            self._proc.stdin.write(line + "\n")
            self._proc.stdin.flush()
            out = self._q.get(timeout=self._timeout)
        except (OSError, ValueError, queue.Empty):
            out = None
        if out is None:
            self._kill()
        return out

    def run(self, request):
        """Eine Sequenz tanzen. request: dict wie tam_cli erwartet. Blockiert."""
        if not self.available():
            return failed_response(request, "engine_missing")
        with self._lock:
            out = self._raw(json.dumps(request, ensure_ascii=False))
            if out is None:
                return failed_response(request, f"timeout ({self._timeout:g} s)")
            try:
                return json.loads(out)
            except ValueError:
                # keine JSON-Antwort: neu starten, damit folgende Antworten nicht verrutschen
                self._kill()
                return failed_response(request, "engine_error: " + out.strip()[:200])

    def version(self):
        """Engine-Stand (fuer Cache-Schluessel), None ohne Engine."""
        if self._version is None and self.available():
            with self._lock:
                out = self._raw('{"cmd":"version"}')
            try:
                self._version = json.loads(out)["version"] if out else None
            except (ValueError, KeyError, TypeError):
                self._version = None
        return self._version

    def close(self):
        with self._lock:
            p, self._proc = self._proc, None
        if p is None:
            return
        try:
            p.stdin.close()
            p.wait(timeout=5)
        except (OSError, subprocess.TimeoutExpired):
            try:
                p.kill()
            except OSError:
                pass
