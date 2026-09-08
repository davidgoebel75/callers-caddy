"""
Pitch-Shifter — stateful Resampler (hinter dem Stretcher)
=========================================================
Architektur ab 2026-06-03: Resampling laeuft HINTER dem WSOLA-Stretcher
(siehe SoundTouch, RateTransposer am Ende der Pipeline fuer rate > 1).

Damit:
- Stretcher-Input ist immer Original-Audio (kein pre-resampletes Audio im
  5-Sekunden-Puffer). Pitch-Wechsel zur Laufzeit sind in <100 ms hoerbar,
  weil nur der kleine Resampler-Carry-Buffer durchlaufen wird.
- Stretcher-Tempo kompensiert wie zuvor (`1/pitch_ratio`) — AR-021-Pattern
  greift unveraendert: nur Parameter setzen, kein Flush.

Pitch wird in Halbtoenen angegeben:
  +1.0 = einen Halbton hoeher
  -1.0 = einen Halbton tiefer
  0.0  = unveraendert (passthrough — keine Interpolation)

Formel: pitch_ratio = 2^(semitones / 12)

Interpolation: Catmull-Rom (Cubic-Hermite) mit 4-Punkt-Kernel.
State zwischen Bloecken:
  _tail  : letzte 3 Input-Samples pro Kanal (Lookback fuer Cubic an Block-Naht)
  _phase : fraktionale Lese-Position relativ zum naechsten Input-Chunk
  _out_carry : restliche Output-Samples eines Aufrufs, die noch nicht abgeholt wurden
"""

import numpy as np


class PitchShifter:
    """Stateful Resampler. Wird nach dem WSOLA-Stretcher betrieben.

    Eingang: vom Stretcher kommendes Audio (bereits time-stretched).
    Ausgang: pitch-verschobenes Audio mit unveraenderter Dauer (bei korrekter
    Stretcher-Kompensation via `tempo_compensation()`).
    """

    def __init__(self, channels=2, sample_rate=44100):
        self.channels = channels
        self.sample_rate = sample_rate
        self._semitones = 0.0
        self._pitch_ratio = 1.0

        # Interpolator-State
        self._tail = np.zeros((3, channels), dtype=np.float32)
        self._tail_valid = False
        # _phase: fraktionale Lese-Position relativ zum Anfang des naechsten Input-Chunks.
        # Kann zu Anfang eines Aufrufs negativ sein, wenn wir noch im Tail-Bereich lesen.
        self._phase = 0.0
        # _out_carry: vom letzten _resample_chunk produzierte, aber noch nicht abgeholte Frames
        self._out_carry = np.zeros((0, channels), dtype=np.float32)

    # ---------- Public API ----------

    @property
    def semitones(self):
        return self._semitones

    @property
    def pitch_ratio(self):
        """Aktuelles Pitch-Verhaeltnis (>1 = hoeher, <1 = tiefer)."""
        return self._pitch_ratio

    def set_pitch(self, semitones):
        """Pitch setzen in Halbtoenen (-12.0 bis +12.0).

        Kein Flush, kein Reset — der Resampler laeuft kontinuierlich mit dem
        neuen Ratio weiter (SoundTouch RateTransposer-Pattern).
        """
        self._semitones = max(-12.0, min(12.0, float(semitones)))
        self._pitch_ratio = 2.0 ** (self._semitones / 12.0)

    def tempo_compensation(self):
        """Tempo-Kompensationsfaktor fuer den WSOLA-Stretcher.

        Bei pitch_ratio=R bewirkt das Resampling am Ende eine Tempo-Aenderung
        um den Faktor 1/R (R>1: Output kuerzer/schneller). Damit die Dauer
        gleich bleibt, muss der Stretcher um 1/R kompensieren — d.h. langsamer
        spielen wenn R>1.

        Returns: float — wird mit user_tempo * today_tempo multipliziert.
        """
        return 1.0 / self._pitch_ratio

    @property
    def is_passthrough(self):
        """True wenn Semitone-Offset unter Schwelle (kein Resampling noetig)."""
        return abs(self._semitones) < 0.01

    def reset(self):
        """Interpolator-State zuruecksetzen (z.B. nach Seek, Stretcher-Flush)."""
        self._tail.fill(0)
        self._tail_valid = False
        self._phase = 0.0
        self._out_carry = np.zeros((0, self.channels), dtype=np.float32)

    def fetch(self, n_out: int, source) -> np.ndarray:
        """Liefert exakt `n_out` Frames Output, holt vom Source nach Bedarf.

        Args:
            n_out: gewuenschte Anzahl Output-Frames
            source: Objekt mit `retrieve(n) -> np.ndarray` (typisch: StreamingTimeStretcher)

        Returns:
            np.ndarray (n_out, channels), float32. Bei Source-Unterlauf wird
            mit Null aufgefuellt — gleiche Semantik wie stretcher.retrieve.
        """
        if self.is_passthrough:
            # Wenn vorher Carry vorhanden war (aktiver Pitch → Passthrough-Wechsel):
            # zuerst Carry abspielen, dann direkt vom Source.
            if len(self._out_carry) > 0:
                result = np.zeros((n_out, self.channels), dtype=np.float32)
                take = min(len(self._out_carry), n_out)
                result[:take] = self._out_carry[:take]
                self._out_carry = self._out_carry[take:]
                remaining = n_out - take
                if remaining > 0:
                    src = source.retrieve(remaining)
                    if src is not None and len(src) > 0:
                        m = min(len(src), remaining)
                        result[take:take + m] = src[:m]
                return result
            # Reiner Passthrough: direkt durchreichen, aber Tail mitfuehren
            # damit ein spaeterer Wechsel auf aktiv klickfrei startet.
            src = source.retrieve(n_out)
            if src is None or len(src) == 0:
                return np.zeros((n_out, self.channels), dtype=np.float32)
            if len(src) >= 3:
                self._tail = src[-3:].copy()
                self._tail_valid = True
            self._phase = 0.0
            if len(src) < n_out:
                result = np.zeros((n_out, self.channels), dtype=np.float32)
                result[:len(src)] = src
                return result
            return src

        result = np.zeros((n_out, self.channels), dtype=np.float32)
        out_pos = 0

        # 1) Carry vom letzten Aufruf zuerst abspielen
        if len(self._out_carry) > 0:
            take = min(len(self._out_carry), n_out)
            result[out_pos:out_pos + take] = self._out_carry[:take]
            out_pos += take
            self._out_carry = self._out_carry[take:]

        # 2) Solange neue Frames brauchen, vom Source holen und resamplen
        safety_iter = 0
        while out_pos < n_out:
            needed = n_out - out_pos
            # Input-Bedarf: needed * ratio plus Sicherheitsmarge fuer Phase
            input_needed = int(np.ceil(needed * self._pitch_ratio)) + 4
            chunk = source.retrieve(input_needed)
            if chunk is None or len(chunk) == 0:
                break
            produced = self._resample_chunk(chunk)
            n_prod = len(produced)
            if n_prod > 0:
                take = min(n_prod, needed)
                result[out_pos:out_pos + take] = produced[:take]
                out_pos += take
                if take < n_prod:
                    # Rest fuer naechsten fetch aufheben
                    self._out_carry = produced[take:].copy()
                    break

            safety_iter += 1
            if safety_iter > 8:
                # Sicherheitsabbruch: sollte nie greifen, aber bei extremen Ratios
                # oder leerem Source nicht endlos schleifen.
                break

        return result

    # ---------- Interne Resampling-Mechanik ----------

    def _resample_chunk(self, data: np.ndarray) -> np.ndarray:
        """Stateful Cubic-Hermite-Resample (Catmull-Rom).

        Input: (n_in, channels) float32.
        Output: variable Laenge, abhaengig von ratio und Phase.
        """
        n_in = len(data)
        if n_in == 0:
            return np.zeros((0, self.channels), dtype=np.float32)
        if data.ndim == 1:
            data = data.reshape(-1, 1)

        # Erweiterter Buffer: 3 Lookback-Samples vorne dran (aus _tail), damit
        # Cubic auch am Block-Anfang funktioniert ohne Diskontinuitaet.
        if self._tail_valid:
            buf = np.concatenate([self._tail, data], axis=0)
        else:
            buf = np.concatenate(
                [np.zeros((3, self.channels), dtype=np.float32), data], axis=0
            )
            self._tail_valid = True

        ratio = self._pitch_ratio
        x = self._phase  # Position in "data-frame-Koordinaten" (0 = Start von `data`)

        # Maximal lesbare data-frame-Position:
        # - Cubic braucht p0..p3 mit Indizes (floor(x)-1, floor(x), floor(x)+1, floor(x)+2)
        # - In buf-Koordinaten: +3 Offset (Tail-Praefix).
        # - max p3-Index = len(buf)-1 = n_in+2.  → floor(x) ≤ n_in - 3.
        max_floor = n_in - 3
        if x > max_floor:
            # Nichts zu produzieren in diesem Chunk — Tail + Phase merken, weiter.
            self._update_tail_and_phase(data, x, 0)
            return np.zeros((0, self.channels), dtype=np.float32)

        # Anzahl Output-Frames: x + k*ratio ≤ max_floor → k_max = floor((max_floor - x) / ratio)
        # Output-Anzahl = k_max + 1 (k von 0 bis k_max inklusive)
        n_out = int(np.floor((max_floor - x) / ratio)) + 1
        if n_out <= 0:
            self._update_tail_and_phase(data, x, 0)
            return np.zeros((0, self.channels), dtype=np.float32)

        positions = x + np.arange(n_out, dtype=np.float64) * ratio
        floor_pos = np.floor(positions).astype(np.int64)
        frac = (positions - floor_pos).astype(np.float32).reshape(-1, 1)

        # buf-Indizes (Tail-Offset +3)
        base = floor_pos + 3
        p0 = buf[base - 1]
        p1 = buf[base]
        p2 = buf[base + 1]
        p3 = buf[base + 2]

        # Catmull-Rom (Cubic-Hermite)
        # f(t) = 0.5 * (2*p1 + (-p0+p2)*t + (2*p0-5*p1+4*p2-p3)*t^2 + (-p0+3*p1-3*p2+p3)*t^3)
        t = frac
        t2 = t * t
        t3 = t2 * t
        out = 0.5 * (
            2.0 * p1
            + (-p0 + p2) * t
            + (2.0 * p0 - 5.0 * p1 + 4.0 * p2 - p3) * t2
            + (-p0 + 3.0 * p1 - 3.0 * p2 + p3) * t3
        )

        self._update_tail_and_phase(data, x, n_out)
        return out.astype(np.float32)

    def _update_tail_and_phase(self, data: np.ndarray, x: float, n_out: int):
        """Tail aus den letzten 3 Frames von `data` setzen, Phase um n_in verschieben."""
        n_in = len(data)
        if n_in >= 3:
            self._tail = data[-3:].copy()
        else:
            # Sehr kleiner Chunk — alte Tail-Reste mitnehmen
            combined = np.concatenate([self._tail, data], axis=0)
            self._tail = combined[-3:].copy()
        # Neue Phase: alte Phase + verbrauchte Output-Frames × Ratio − n_in (relativ zum
        # neuen Chunk-Start, der jetzt um n_in nach rechts gewandert ist)
        ratio = self._pitch_ratio
        self._phase = (x + n_out * ratio) - n_in
