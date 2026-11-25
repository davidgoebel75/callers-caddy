"""Zeitachse einer getanzten Sequenz (Square Flow, intern#247).

- Zuordnung gesendete Zeile -> Kartenzeile (eine Kartenzeile kann 0..n gesendete Zeilen haben).
- Beats je Kartenzeile fuer das Sequenz-Detail (#164).
- Stellung der Taenzer zu einem Beat (Interpolation zwischen den Engine-Bildern).
- Beat <-> Sekunde ueber das Tempo des Songs.
"""
import bisect
import math

QT_FREE = True


def card_beats(n_cards, src, line_beats, end_src=None, beats_end=None):
    """Beats je Kartenzeile: Summe der gesendeten Zeilen dieser Kartenzeile, None ohne Wert.
    src/end_src aus mapping.prepare(); line_beats = Beats je gesendeter Zeile (Engine);
    beats_end = Beats des Aufloese-Calls bzw. von Swing + Promenade."""
    res = [None] * n_cards
    for i, s in enumerate(src):
        if s is None or i >= len(line_beats) or s >= n_cards:
            continue
        res[s] = round((res[s] or 0) + line_beats[i], 2)
    if beats_end is not None and end_src is not None and end_src < n_cards:
        res[end_src] = round((res[end_src] or 0) + beats_end, 2)
    return res


def beats_to_seconds(beats, bpm):
    return beats * 60.0 / bpm if bpm and bpm > 0 else 0.0


def seconds_to_beats(seconds, bpm):
    return seconds * bpm / 60.0 if bpm and bpm > 0 else 0.0


def _lerp_angle(a, b, f):
    d = ((b - a + 540) % 360) - 180
    return a + d * f


class Timeline:
    """Animation aus einer Engine-Antwort mit "animation" (frames-Schritt > 0)."""

    def __init__(self, animation):
        an = animation or {}
        self.dancers = an.get("dancers") or []
        frames = an.get("frames") or []
        self._t = [f[0] for f in frames]
        self._poses = [f[1] for f in frames]
        self.call_starts = list(an.get("call_starts") or [])
        self.total_beats = float(an.get("total_beats") or 0.0)

    def empty(self):
        return not self._poses

    def pose_at(self, beat):
        """[[x, y, winkel], ...] je Taenzer zum Beat (linear interpoliert, Winkel kuerzester Weg)."""
        if not self._poses:
            return []
        if beat <= self._t[0]:
            return self._poses[0]
        if beat >= self._t[-1]:
            return self._poses[-1]
        i = bisect.bisect_right(self._t, beat) - 1
        t0, t1 = self._t[i], self._t[i + 1]
        f = (beat - t0) / (t1 - t0) if t1 > t0 else 0.0
        a, b = self._poses[i], self._poses[i + 1]
        return [[pa[0] + (pb[0] - pa[0]) * f, pa[1] + (pb[1] - pa[1]) * f,
                 _lerp_angle(pa[2], pb[2], f)] for pa, pb in zip(a, b)]

    def line_at(self, beat):
        """Index der gesendeten Zeile, die zum Beat getanzt wird (-1 vor dem Start)."""
        if not self.call_starts or beat < 0:
            return -1
        return max(0, bisect.bisect_right(self.call_starts, beat) - 1)

    def line_span(self, i):
        """(Start-Beat, End-Beat) der gesendeten Zeile i."""
        start = self.call_starts[i]
        end = self.call_starts[i + 1] if i + 1 < len(self.call_starts) else self.total_beats
        return start, end

    def extent(self):
        """Groesste Entfernung eines Taenzers von der Mitte ueber die ganze Animation."""
        return max((math.hypot(x, y) for p in self._poses for x, y, _ in p), default=0.0)
