"""Schritt-Funktionen der Massenlaeufe ohne Qt (intern#139).

Ein Schritt bekommt die Worker-Verbindung und einen Job (song_id, filepath,
name), schreibt OHNE Commit und gibt True (erledigt) oder False (uebersprungen)
zurueck. Das SQL steht in song_db, hier nur der Ablauf.
"""
from song_db_potential import PotentialMixin

QT_FREE = True


def bpm_step(conn, job, detect=None) -> bool:
    """Ermittelt die BPM eines Songs und schreibt base_bpm."""
    sid, filepath, _name = job
    if detect is None:
        from bpm_detector import detect_bpm as detect   # zieht scipy: lazy
    bpm = detect(filepath)
    if not bpm or bpm <= 0:
        return False
    PotentialMixin.write_base_bpm(conn, sid, bpm)
    return True
