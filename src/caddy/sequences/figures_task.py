"""Figuren je Sequenz nach Datenaenderungen neu vorbauen (intern#274).

Pull-Verfahren: Die Aufgabe sagt nur, ob sie etwas zu tun hat, und stoesst dann den
Vorbau im SequencePrefetchWorker an. Wer zieht, ist austauschbar: bis intern#46 ein
langsamer Takt in main.py (nicht bei laufender Musik), spaeter die Idle-Warmup-Queue
oder ein Leerlauf-Detektor. Ein Pull kostet eine Mini-Abfrage auf den Trigger-Zaehler
(sequence_data_version); gearbeitet wird nur, wenn sich die Daten wirklich geaendert
haben. So muss keine Schreibstelle Bescheid geben (Import, Editor, Loeschen,
Programm-Abgleich, Call-Mapping; vgl. Review #192, Punkt 7).

Kein Qt, kein eigenes SQL: nur Aufrufe der DB-Schicht und des Workers.
"""


class FiguresPrefetchTask:
    """pull() -> True, wenn der Vorbau angestossen wurde."""

    def __init__(self, db, worker):
        self._db = db
        self._worker = worker
        # Stand beim Erzeugen: Der erste Pull darf sofort vorbauen, wenn sich die
        # Daten seitdem nicht bewegt haben.
        self._last_ver = db.sequence_data_version()

    def pull(self) -> bool:
        """Vorbau anstossen, wenn alles drei gilt: Die Figuren passen nicht zum
        aktuellen Datenstand, der Zaehler steht seit dem letzten Pull still (kein
        Import mehr im Gange) und kein Vorbau ist unterwegs."""
        ver = self._db.sequence_data_version()
        stable = ver == self._last_ver
        self._last_ver = ver
        if not stable:
            return False                     # Daten bewegen sich noch: naechster Pull
        if self._worker.figures_pending():
            return False
        if self._db.has_sequence_figures():
            return False
        self._worker.request_figures()
        return True
