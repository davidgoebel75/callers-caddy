"""
Streaming WSOLA Time-Stretcher (v2 - improved quality)
========================================================
WSOLA = Waveform Similarity Overlap-Add

Verbesserungen gegenueber v1:
- Hann-Fenster mit 50% Overlap (COLA-Bedingung)
- Groesseres Analysefenster (4096 Samples)
- Praezise Kreuzkorrelation via numpy (kein Suchschritt-Skip)
- Sauberes Overlap-Add statt linearem Crossfade

Tempo 1.0 = Original, >1.0 = schneller, <1.0 = langsamer.
"""

import numpy as np
import threading
import time


class StreamingTimeStretcher:
    """Streaming WSOLA Time-Stretcher fuer Echtzeit-Tempo-Aenderung.

    Verwendet Hann-Fenster mit 50% Overlap (COLA-Bedingung),
    sodass bei Tempo 1.0 das Signal exakt rekonstruiert wird.
    Bei anderem Tempo findet WSOLA per Kreuzkorrelation die
    besten Splice-Punkte und minimiert Artefakte.
    """

    def __init__(self, channels=2, sample_rate=44100,
                 window_size=4096, search_range=512):
        self.channels = channels
        self.sample_rate = sample_rate
        self.window_size = window_size
        self.syn_hop = window_size // 2       # 50% Overlap (COLA)
        self.search_range = search_range      # Suchbereich fuer beste Ueberlappung

        self._tempo = 1.0
        # Fix C (AR-020): zwei Locks statt einem.
        # _lock     schuetzt internen State (input_buf, ana_pos, ola_buf, _first_window)
        # _out_lock schuetzt NUR output_buf — Callback (retrieve) braucht nur diesen.
        # Damit blockiert eine teure Hop-Berechnung den Audio-Callback nicht mehr.
        self._lock = threading.Lock()
        self._out_lock = threading.Lock()

        # Hann-Fenster (COLA-konform bei 50% Overlap)
        self._window = np.hanning(window_size).astype(np.float32).reshape(-1, 1)

        # Overlap-Add Akkumulator
        self._ola_buf = None

        # Fix A/B/C Diagnostik-Stats (AR-020) — vom Feeder geschrieben, vom
        # Audio-Engine-Sampler alle 5 s abgerufen und reseted.
        self._stats_lock = threading.Lock()
        self._stats_hops_total = 0
        self._stats_hops_passthrough = 0     # Fix A wirkt: Korrelation uebersprungen
        self._stats_hops_correlation = 0     # voller Coarse/Fine-Search
        self._stats_lock_hold_ns_sum = 0     # Summe Lock-Hold-Zeit fuer avg
        self._stats_lock_hold_ns_max = 0     # Max Lock-Hold-Zeit

        self.reset()

    def reset(self):
        """Alle Puffer zuruecksetzen."""
        self._input_buf = np.zeros((0, self.channels), dtype=np.float32)
        self._output_buf = np.zeros((0, self.channels), dtype=np.float32)
        self._ola_buf = np.zeros((self.window_size, self.channels), dtype=np.float32)
        self._ana_pos = 0.0
        self._input_consumed = 0
        self._first_window = True

    @property
    def tempo(self):
        return self._tempo

    def set_tempo(self, tempo):
        """Tempo setzen (0.5 bis 2.0)."""
        self._tempo = max(0.5, min(2.0, float(tempo)))

    def feed(self, data):
        """Audio-Daten einspeisen."""
        if data.ndim == 1:
            data = data.reshape(-1, 1)
        with self._lock:
            self._input_buf = np.concatenate([self._input_buf, data])

    def preprocess(self, target_frames):
        """Output-Buffer bis target_frames befuellen — im Feeder-Thread aufrufen, NICHT im Callback.

        Fix C (AR-020): teure Hop-Berechnung laeuft unter self._lock (internal),
        das Anhaengen ans output_buf unter self._out_lock (kurz). Der Audio-Callback
        (retrieve) wartet nur auf _out_lock — Mikrosekunden statt Millisekunden.
        """
        while True:
            # Schneller Check ob Soll erreicht — nur kurz _out_lock halten.
            with self._out_lock:
                if len(self._output_buf) >= target_frames:
                    break

            # Teure Hop-Berechnung unter _lock (internal state).
            t0 = time.monotonic_ns()
            with self._lock:
                chunk = self._process_one_hop()
            t1 = time.monotonic_ns()

            if chunk is None:
                break

            # Anhaengen unter _out_lock (sehr kurz, Callback-freundlich).
            with self._out_lock:
                self._output_buf = np.concatenate([self._output_buf, chunk])

            # Stats fuer Diagnose
            hold_ns = t1 - t0
            with self._stats_lock:
                self._stats_hops_total += 1
                self._stats_lock_hold_ns_sum += hold_ns
                if hold_ns > self._stats_lock_hold_ns_max:
                    self._stats_lock_hold_ns_max = hold_ns

    def retrieve(self, num_frames):
        """Zeit-gestreckte Audio-Daten abholen — nur aus dem vorbereiteten Output-Buffer lesen.

        Kein WSOLA-Processing hier — das macht preprocess() im Feeder-Thread.
        Fix C (AR-020): braucht nur _out_lock, NICHT _lock — Callback laeuft
        damit parallel zu einer laufenden Hop-Berechnung.
        """
        with self._out_lock:
            if len(self._output_buf) >= num_frames:
                result = self._output_buf[:num_frames]
                self._output_buf = self._output_buf[num_frames:]
                return result
            else:
                result = np.zeros((num_frames, self.channels), dtype=np.float32)
                avail = len(self._output_buf)
                if avail > 0:
                    result[:avail] = self._output_buf
                    self._output_buf = np.zeros((0, self.channels), dtype=np.float32)
                return result

    def trim_output_to(self, max_frames):
        """AR-021 (SoundTouch-Stil): output_buf von HINTEN auf max_frames kuerzen.

        Wird vom audio_engine bei Tempo-/Pitch-Wechsel aufgerufen. Der Anfang
        (was der Callback gerade abspielt) bleibt unangetastet — keine Stille,
        kein Klick. Nur die Reserve am Ende wird weggeworfen, damit das neu
        gerechnete Material (mit neuem Tempo) schneller hoerbar wird.

        Stretcher-State (input_buf, ola_buf, ana_pos) bleibt komplett erhalten
        → keine Position-Spruenge, kein Doppelgaenger-Effekt.
        """
        with self._out_lock:
            if len(self._output_buf) > max_frames:
                self._output_buf = self._output_buf[:max_frames].copy()

    def _process_one_hop(self):
        """Ein WSOLA-Fenster verarbeiten, syn_hop Frames Output liefern."""
        ana_pos_int = int(self._ana_pos)
        ana_hop = self.syn_hop * self._tempo

        # Genug Input?
        needed = ana_pos_int + self.window_size + self.search_range
        if needed > len(self._input_buf):
            return None

        # Beste Ueberlappungsposition finden
        if self._first_window:
            best_pos = ana_pos_int
            self._first_window = False
        else:
            best_pos = self._find_best_position(ana_pos_int)

        # Fenster extrahieren und Hann-Window anwenden
        segment = self._input_buf[best_pos:best_pos + self.window_size].copy()
        windowed = segment * self._window

        # Overlap-Add: neues Fenster zum Akkumulator addieren
        self._ola_buf += windowed

        # Die erste Haelfte (syn_hop Frames) ist fertig -> Output
        output = self._ola_buf[:self.syn_hop].copy()

        # Akkumulator shiften: zweite Haelfte wird erste Haelfte
        new_ola = np.zeros((self.window_size, self.channels), dtype=np.float32)
        new_ola[:self.syn_hop] = self._ola_buf[self.syn_hop:]
        self._ola_buf = new_ola

        # Analyse-Position vorschieben
        self._ana_pos += ana_hop

        # Input-Buffer trimmen
        trim_pos = max(0, int(self._ana_pos) - self.search_range - self.window_size)
        if trim_pos > 0:
            self._input_buf = self._input_buf[trim_pos:]
            self._ana_pos -= trim_pos
            self._input_consumed += trim_pos

        return output

    def _find_best_position(self, nominal_pos):
        """Beste Ueberlappungsposition per Kreuzkorrelation.

        Fix A (AR-020): bei Tempo == 1.0 ist die nominale Position bereits
        mathematisch exakt (COLA-Bedingung mit Hann + 50% Overlap + ana_hop=syn_hop
        garantiert exakte Rekonstruktion). Kreuzkorrelation wuerde nur nominal_pos
        als Optimum reproduzieren, kostet aber ~5-15 ms Lock-Hold auf schwacher CPU.
        Auf Realtek-WDM-KS @ 11 ms Latenz war das als Knistern hoerbar.

        Coarse-to-Fine Suche (nur bei Tempo != 1.0):
        1. Grob: jeden 8. Sample pruefen
        2. Fein: um den besten groben Treffer herum jeden Sample pruefen

        Vergleicht den Anfang des Kandidaten-Segments mit dem
        OLA-Akkumulator, um die Phase optimal zu matchen.
        """
        # Fix A: Passthrough bei Tempo 1.0
        if self._tempo == 1.0:
            with self._stats_lock:
                self._stats_hops_passthrough += 1
            return nominal_pos

        with self._stats_lock:
            self._stats_hops_correlation += 1

        half_search = self.search_range // 2

        # Referenz: OLA-Akkumulator (offene Ueberlappung vom vorigen Fenster)
        ref = self._ola_buf[:self.syn_hop]

        # Mono-Mix fuer Korrelation (schneller als Multichannel)
        if self.channels > 1:
            ref_mono = np.mean(ref, axis=1)
        else:
            ref_mono = ref.ravel()

        compare_len = min(self.syn_hop, 512)  # Kurzer Vergleich reicht
        ref_seg = ref_mono[:compare_len]
        ref_energy = np.dot(ref_seg, ref_seg)
        if ref_energy < 1e-10:
            return nominal_pos  # Stille

        search_start = max(0, nominal_pos - half_search)
        search_end = min(len(self._input_buf) - self.window_size,
                         nominal_pos + half_search)

        if search_start >= search_end:
            return nominal_pos

        # --- Phase 1: Grobe Suche (Schritt 8) ---
        best_corr = -np.inf
        best_pos = nominal_pos
        coarse_step = 8

        for pos in range(search_start, search_end + 1, coarse_step):
            corr = self._correlate_at(pos, ref_seg, ref_energy, compare_len)
            if corr > best_corr:
                best_corr = corr
                best_pos = pos

        # --- Phase 2: Feine Suche (Schritt 1, um besten groben Treffer) ---
        fine_start = max(search_start, best_pos - coarse_step)
        fine_end = min(search_end, best_pos + coarse_step)

        for pos in range(fine_start, fine_end + 1):
            corr = self._correlate_at(pos, ref_seg, ref_energy, compare_len)
            if corr > best_corr:
                best_corr = corr
                best_pos = pos

        return best_pos

    def _correlate_at(self, pos, ref_seg, ref_energy, compare_len):
        """Normalisierte Kreuzkorrelation an einer Position."""
        candidate = self._input_buf[pos:pos + compare_len]
        if self.channels > 1:
            cand_mono = np.mean(candidate, axis=1)
        else:
            cand_mono = candidate.ravel()

        if len(cand_mono) < compare_len:
            return -np.inf

        cand_energy = np.dot(cand_mono, cand_mono)
        if cand_energy < 1e-10:
            return -np.inf

        return np.dot(ref_seg, cand_mono) / np.sqrt(ref_energy * cand_energy)

    def flush(self):
        """Alle Puffer leeren und Menge ungenutzter Daten zurueckgeben.

        Thread-safe: haelt den Lock waehrend der gesamten Operation,
        damit kein retrieve()-Aufruf aus dem Audio-Callback
        auf leere Puffer trifft.

        Returns:
            tuple: (unprocessed_input_samples, buffered_output_samples)
                - unprocessed: Input-Samples die noch nicht verarbeitet wurden
                - output_buffered: Bereits verarbeitete Output-Samples im Puffer
        """
        # Fix C (AR-020): flush schreibt sowohl internen State als auch
        # output_buf → beide Locks halten. Reihenfolge: _lock zuerst, dann
        # _out_lock (preprocess folgt derselben Reihenfolge → kein Deadlock).
        with self._lock:
            with self._out_lock:
                # Wie viel Input ist noch unverarbeitet?
                unprocessed = max(0, len(self._input_buf) - int(self._ana_pos))
                output_buffered = len(self._output_buf)

                # Position-Tracking aktualisieren (was verarbeitet wurde zaehlt)
                self._input_consumed += int(self._ana_pos)

                # Puffer leeren
                self._input_buf = np.zeros((0, self.channels), dtype=np.float32)
                self._output_buf = np.zeros((0, self.channels), dtype=np.float32)
                self._ola_buf = np.zeros((self.window_size, self.channels),
                                         dtype=np.float32)
                self._ana_pos = 0.0
                self._first_window = True

                return unprocessed, output_buffered

    def get_input_position(self):
        """Aktuelle Position im Input-Stream (in Samples)."""
        return self._input_consumed + int(self._ana_pos)

    def input_available(self):
        """Anzahl verfuegbarer Input-Samples im Puffer."""
        return len(self._input_buf) - int(self._ana_pos)

    def output_available(self):
        """Anzahl vorverarbeiteter Output-Samples im Puffer (ohne Lock — nur fuer Diagnostik)."""
        return len(self._output_buf)

    def get_and_reset_stats(self):
        """Stretcher-Statistik fuer Diagnose-Log abrufen + Counter zuruecksetzen.

        Zeigt Fix A (passthrough vs. correlation) und Fix C (Lock-Hold-Zeiten)
        in Aktion. Wird im AudioBuf-Sampler alle 5 s abgerufen.

        Returns:
            dict mit 'hops_total', 'hops_passthrough', 'hops_correlation',
            'lock_hold_ms_avg', 'lock_hold_ms_max'. Bei hops_total=0
            (Wiedergabe pausiert) sind die Felder 0.
        """
        with self._stats_lock:
            total = self._stats_hops_total
            passthrough = self._stats_hops_passthrough
            correlation = self._stats_hops_correlation
            hold_sum_ns = self._stats_lock_hold_ns_sum
            hold_max_ns = self._stats_lock_hold_ns_max
            self._stats_hops_total = 0
            self._stats_hops_passthrough = 0
            self._stats_hops_correlation = 0
            self._stats_lock_hold_ns_sum = 0
            self._stats_lock_hold_ns_max = 0

        avg_ms = (hold_sum_ns / total / 1_000_000.0) if total > 0 else 0.0
        max_ms = hold_max_ns / 1_000_000.0
        return {
            'hops_total': total,
            'hops_passthrough': passthrough,
            'hops_correlation': correlation,
            'lock_hold_ms_avg': avg_ms,
            'lock_hold_ms_max': max_ms,
        }

    def can_process(self):
        """True wenn genug Input fuer mindestens einen weiteren WSOLA-Hop vorhanden."""
        needed = int(self._ana_pos) + self.window_size + self.search_range
        return needed <= len(self._input_buf) or len(self._output_buf) > 0
