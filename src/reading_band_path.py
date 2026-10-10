"""Lesebalken-Kurve und In-Lesebalken Countdown (intern#172, intern#148).

Qt-frei: reine Rechnung auf (Sekunde, Dokument-Y)-Punkten. Das Lyrics-Widget
liefert die Geometrie (Anker-Y, Abschnittsanfang, Abschnittsende) und fragt
hier, wo der gesungene Text zur Songzeit steht. Scroll und Lesebalken nutzen
dieselbe Kurve.

Regeln:
- Vor dem ersten Anker wartet der Balken auf der ersten Textzeile des
  Abschnitts und laeuft so spaet los, dass er im Tempo des folgenden Stuecks
  am Anker ankommt.
- Vor einem Ruecksprung laeuft er im bisherigen Tempo bis zum Abschnittsende
  weiter, wartet dort und gleitet dann kurz vor dem Ziel zurueck.
"""
import math
from statistics import median

# Folgt der naechste Anker innerhalb dieser Zeit, beendet der Anker einen
# Abschnitt (danach springt der Text woanders hin), intern#76.
SECTION_END_GAP_SEC = 2.0
# So lange vor dem Ziel beginnt der Ruecksprung.
BACK_SNAP_SEC = 1.5
# Anlauf zum ersten Anker, wenn kein Tempo aus dem Folgestueck ableitbar ist.
LEAD_IN_FALLBACK_SEC = 4.0


def ends_section(times, i) -> bool:
    """Anker i beendet einen Abschnitt: letzter Anker, oder der naechste folgt
    binnen SECTION_END_GAP_SEC. times = Ankerzeiten, aufsteigend."""
    return i == len(times) - 1 or times[i + 1] - times[i] <= SECTION_END_GAP_SEC


def _speed(a, b):
    """Tempo (Y je Sekunde) des Stuecks a -> b, None wenn es kein ruhiges
    Vorwaerts-Stueck ist (Ruecksprung oder Abschnittsende-Paar)."""
    (t0, y0), (t1, y1) = a, b
    if t1 - t0 <= SECTION_END_GAP_SEC or y1 <= y0:
        return None
    return (y1 - y0) / (t1 - t0)


def build_path(anchors, dur, doc_h, start_y=None, end_ys=None):
    """Stuetzpunkte der Kurve und die Zeitfenster der Rueckspruenge.

    anchors: [(Sekunde, Y)] nach Zeit sortiert.
    start_y: Y der ersten Textzeile im Abschnitt des ersten Ankers (None =
             unbekannt, dann laeuft die Kurve wie frueher vom Dokumentanfang).
    end_ys:  je Anker das Y des Abschnittsendes (Unterkante der letzten
             Textzeile vor der naechsten Ueberschrift) oder None.
    Rueckgabe: (points, snaps) mit points = [(Sekunde, Y)] und
    snaps = [(von, bis)].
    """
    dur = float(dur)
    doc_h = float(doc_h)
    if not anchors:
        return [(0.0, 0.0), (dur, doc_h)], []
    pts = [(float(t), float(y)) for t, y in anchors]
    times = [t for t, _y in pts]
    ends = list(end_ys) if end_ys else [None] * len(pts)
    speeds = [s for s in (_speed(pts[i], pts[i + 1]) for i in range(len(pts) - 1)) if s]
    ref_speed = median(speeds) if speeds else None

    points, snaps = [], []
    t0, y0 = pts[0]
    if start_y is None:
        points.append((0.0, 0.0))
    elif start_y >= y0 or t0 <= 0:
        points.append((0.0, y0))
    else:
        speed = _speed(pts[0], pts[1]) if len(pts) > 1 else None
        lead = (y0 - start_y) / speed if speed else LEAD_IN_FALLBACK_SEC
        points.append((0.0, float(start_y)))
        if t0 - lead > 0:
            points.append((t0 - lead, float(start_y)))
    points.append((t0, y0))

    for i in range(1, len(pts)):
        tp, yp = pts[i - 1]
        t, y = pts[i]
        if y < yp and t > tp:
            snap_start = t - min(BACK_SNAP_SEC, t - tp)
            hold_y = yp
            end = ends[i - 1]
            if (end is not None and end > yp and snap_start > tp
                    and not ends_section(times, i - 1)):
                speed = (_speed(pts[i - 2], pts[i - 1]) if i >= 2 else None) or ref_speed
                if speed:
                    reach = tp + (end - yp) / speed
                    if reach <= snap_start:
                        points.append((reach, float(end)))
                        hold_y = float(end)
                    else:
                        hold_y = yp + speed * (snap_start - tp)
            points.append((snap_start, hold_y))
            snaps.append((snap_start, t))
        points.append((t, y))

    if dur > pts[-1][0]:
        points.append((dur, max(doc_h, pts[-1][1])))
    return points, snaps


def position(pos, path):
    """(Y, im Ruecksprung?) der Kurve zur Songzeit pos."""
    points, snaps = path
    snapping = any(a < pos <= b for a, b in snaps)
    for i in range(len(points) - 1):
        t0, y0 = points[i]
        t1, y1 = points[i + 1]
        if pos <= t1:
            if t1 <= t0:
                return float(y1), snapping
            frac = max(0.0, min(1.0, (pos - t0) / (t1 - t0)))
            return y0 + frac * (y1 - y0), snapping
    return float(points[-1][1]), snapping


def section_change_times(anchors, section_ids):
    """Zeiten der Anker, die einen neuen Abschnitt beginnen: anderer Abschnitt
    als der Anker davor, oder Ruecksprung im Text (Wiederholung). Der erste
    Anker zaehlt nicht (dort zaehlt der Start-Countdown).

    section_ids: je Anker eine Kennung seines Abschnitts im Dokument.
    """
    out = []
    for i in range(1, len(anchors)):
        if section_ids[i] != section_ids[i - 1] or anchors[i][1] < anchors[i - 1][1]:
            out.append(float(anchors[i][0]))
    return out


def beats_until_change(pos, change_times, bpm, max_beats):
    """Beats bis zum naechsten Abschnittswechsel, None ausserhalb des
    Vorlaufs (mehr als max_beats entfernt, kein Wechsel mehr, kein BPM).
    pos und change_times in Song-Sekunden, bpm = Base-BPM des Songs."""
    if not bpm or bpm <= 0 or max_beats <= 0:
        return None
    nxt = min((t for t in change_times if t > pos), default=None)
    if nxt is None:
        return None
    beats = math.ceil((nxt - pos) * bpm / 60.0)
    return beats if 1 <= beats <= max_beats else None
