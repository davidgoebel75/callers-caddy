"""Lyrics-Dateien in den Lyrics-Ordner uebernehmen (intern#167).

Die Anzeige liest Lyrics nur aus dem Lyrics-Ordner. Kommt eine Datei von
ausserhalb (Auswahl in den Song-Daten, Import), wird sie dorthin kopiert.
Liegt dort schon eine gleichnamige Datei mit anderem Inhalt, entscheidet
nicht dieses Modul, sondern der Caller: find_conflict() beschreibt den Fall,
resolve() fuehrt die Entscheidung aus.

Ohne Qt, damit die Regel ohne Fenster testbar ist.
"""
import filecmp
import os
import shutil
from dataclasses import dataclass

# Entscheidungen des Callers bei einer abweichenden gleichnamigen Datei
REPLACE = "replace"            # vorhandene ersetzen, alte als .bak sichern
KEEP_BOTH = "keep_both"        # neue als 'Name_1.ext' daneben legen
USE_EXISTING = "use_existing"  # vorhandene weiterverwenden, nichts kopieren

# Vermutung aus dem Aenderungsdatum
NEWER = "newer"      # neue Datei juenger -> vermutlich ueberarbeitete Fassung
OLDER = "older"      # neue Datei aelter -> vermutlich fruehere Fassung
UNCLEAR = "unclear"  # gleiches Datum, anderer Inhalt

# Unterhalb davon gelten zwei Aenderungsdaten als gleich (FAT speichert auf
# 2 Sekunden genau, Kopien ueber USB-Sticks verlieren die Nachkommastellen).
_MTIME_TOLERANCE_S = 2.0


@dataclass
class LyricsConflict:
    """Gleichnamige Datei mit anderem Inhalt liegt schon im Lyrics-Ordner."""
    src: str            # neue Datei (ausserhalb des Lyrics-Ordners)
    dest: str           # vorhandene Datei im Lyrics-Ordner
    src_mtime: float
    dest_mtime: float
    src_size: int
    dest_size: int

    @property
    def name(self) -> str:
        return os.path.basename(self.dest)

    @property
    def guess(self) -> str:
        diff = self.src_mtime - self.dest_mtime
        if diff > _MTIME_TOLERANCE_S:
            return NEWER
        if diff < -_MTIME_TOLERANCE_S:
            return OLDER
        return UNCLEAR


def _same_file(a: str, b: str) -> bool:
    try:
        return os.path.samefile(a, b)
    except OSError:
        return False


def is_inside(path: str, lyrics_dir: str) -> bool:
    """True, wenn path im Lyrics-Ordner oder einem Unterordner davon liegt."""
    fp = os.path.normcase(os.path.abspath(path))
    base = os.path.normcase(os.path.abspath(lyrics_dir))
    try:
        return os.path.commonpath([fp, base]) == base
    except ValueError:      # verschiedene Laufwerke
        return False


def find_conflict(src: str, lyrics_dir: str):
    """LyricsConflict, wenn im Lyrics-Ordner eine gleichnamige Datei mit
    anderem Inhalt liegt, sonst None (kein Ziel, dieselbe Datei oder Inhalt
    Byte fuer Byte gleich)."""
    dest = os.path.join(lyrics_dir, os.path.basename(src))
    if not os.path.isfile(dest) or _same_file(src, dest):
        return None
    if filecmp.cmp(src, dest, shallow=False):
        return None
    s, d = os.stat(src), os.stat(dest)
    return LyricsConflict(src=src, dest=dest, src_mtime=s.st_mtime,
                          dest_mtime=d.st_mtime, src_size=s.st_size,
                          dest_size=d.st_size)


def adopt(src: str, lyrics_dir: str) -> str:
    """Kopiert src in den Lyrics-Ordner, falls dort noch keine gleichnamige
    Datei liegt, und gibt den Dateinamen zurueck. Eine vorhandene Datei bleibt
    unberuehrt; ob sie abweicht, sagt find_conflict()."""
    os.makedirs(lyrics_dir, exist_ok=True)
    dest = os.path.join(lyrics_dir, os.path.basename(src))
    if not os.path.exists(dest):
        shutil.copy2(src, dest)
    return os.path.basename(dest)


def _numbered_name(src: str, dest: str) -> str:
    """Pfad 'Name_1.ext', 'Name_2.ext', ... fuer die neue Datei: eine dort
    schon liegende Kopie mit dem Inhalt von src, sonst der erste freie."""
    root, ext = os.path.splitext(dest)
    k = 1
    while os.path.exists(f"{root}_{k}{ext}"):
        if filecmp.cmp(src, f"{root}_{k}{ext}", shallow=False):
            break
        k += 1
    return f"{root}_{k}{ext}"


def _copy_replacing(src: str, dest: str):
    """Ersetzt dest durch src in einem Schritt: Bricht das Kopieren ab,
    bleibt dest vollstaendig, wie es war."""
    tmp = dest + ".tmp"
    try:
        shutil.copy2(src, tmp)
        os.replace(tmp, dest)
    except OSError:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise


def resolve(conflict: LyricsConflict, decision: str) -> str:
    """Fuehrt die Entscheidung des Callers aus und gibt den Dateinamen im
    Lyrics-Ordner zurueck, den der Song danach verwendet."""
    if decision == REPLACE:
        # Alte Fassung sichern; eine fruehere Sicherung wird ersetzt.
        shutil.copy2(conflict.dest, conflict.dest + ".bak")
        _copy_replacing(conflict.src, conflict.dest)
        return conflict.name
    if decision == KEEP_BOTH:
        dest = _numbered_name(conflict.src, conflict.dest)
        if not os.path.exists(dest):
            shutil.copy2(conflict.src, dest)
        return os.path.basename(dest)
    if decision == USE_EXISTING:
        return conflict.name
    raise ValueError(f"unbekannte Entscheidung: {decision!r}")
