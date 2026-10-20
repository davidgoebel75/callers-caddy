"""Schleife der Massenlaeufe ohne Qt (intern#139).

Je Job: Abbruch pruefen, Fortschritt melden, Schritt rufen. Der Qt-Mantel
(bulk_worker.py) stellt Thread, Signale und Verbindung.
"""
from dataclasses import dataclass

QT_FREE = True


@dataclass(frozen=True)
class BulkResult:
    done: int
    skipped: int
    cancelled: bool


def run_bulk(jobs, step, *, conn, is_cancelled, on_progress,
             name_of=lambda job: "", label="Bulk") -> BulkResult:
    """Fuehrt step(conn, job) fuer jeden Job aus.

    step gibt True (erledigt) oder False (uebersprungen) zurueck. Eine
    Ausnahme zaehlt als uebersprungen: Log, rollback, weiter mit dem naechsten
    Job. Nach jedem erledigten Job commit (Ergebnisse bleiben bei Abbruch).
    Jobs sind Tupel mit der Song-ID an Stelle 0."""
    done = skipped = 0
    cancelled = False
    total = len(jobs)
    for i, job in enumerate(jobs):
        if is_cancelled():
            cancelled = True
            break
        on_progress(i + 1, total, name_of(job))
        try:
            if step(conn, job):
                conn.commit()
                done += 1
            else:
                skipped += 1
        except Exception as e:
            print(f"[{label}] Fehler bei Song #{job[0]}: {e}")
            skipped += 1
            try:
                conn.rollback()
            except Exception as e2:
                print(f"[{label}] Rollback fehlgeschlagen: {e2}")
    return BulkResult(done, skipped, cancelled)
