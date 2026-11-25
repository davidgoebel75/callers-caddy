"""Figuren-Uhr im Singing Call (Square Flow Phase 2, intern#247).

Qt-frei. Ein Figuren-Fenster reicht von SyncPoint zu SyncPoint (Anfang und Ende eines
FIGURE-Teils). Die Kartenzeilen der Sequenz werden darin anteilig nach ihren Beats verteilt.
Lesebalken und Square Flow rechnen mit denselben Anteilen; am naechsten SyncPoint wird hart
neu angesetzt. Ungenauigkeiten (vor allem Swing & Promenade) nehmen wir hin.

Grundlage ist das Ergebnis von analysis.analyse_sequence (auch aus dem DB-Cache):
"card_spans" = (Start-Beat, End-Beat) je Kartenzeile, "anim_total" = Beats der Animation.
"""

QT_FREE = True


def figure_total(result):
    """Gesamt-Beats der getanzten Figur (mit Aufloese-Call, falls getanzt), None ohne Wert.
    Aeltere Cache-Eintraege kennen "anim_total" nicht: dann das Ende der letzten Kartenzeile."""
    if not result:
        return None
    total = result.get("anim_total")
    if not total:
        an = result.get("animation") or {}
        total = an.get("total_beats")
    if not total:
        ends = [sp[1] for sp in (result.get("card_spans") or []) if sp]
        total = max(ends) if ends else None
    return float(total) if total and total > 0 else None


def beats_usable(result):
    """Taugt das Ergebnis fuer den Lesebalken nach Beats? Nicht bei Abbruch oder roter
    Sequenz (Entscheidung David: dann laeuft der Lesebalken wie heute nach Zeilen)."""
    return bool(result) and bool(result.get("stufe1")) and result.get("urteil") != "rot" \
        and figure_total(result) is not None


def card_fractions(result, n_cards):
    """Anteil am Figuren-Fenster, an dem jede Kartenzeile beginnt (0..1), None je Zeile ohne
    Beat-Spanne. Ganz None, wenn das Ergebnis nicht taugt oder nicht zu n_cards passt."""
    if not beats_usable(result):
        return None
    spans = result.get("card_spans") or []
    if len(spans) != n_cards:
        return None
    total = figure_total(result)
    out = [None if not sp else max(0.0, min(1.0, float(sp[0]) / total)) for sp in spans]
    return out if any(f is not None for f in out) else None


def beat_anchors(t0, t1, fractions, line_of_card):
    """Zwischenanker [(Sekunde, Zeile)] je Kartenzeile im Fenster t0..t1. Die erste Zeile
    beginnt am Fenster-Anker selbst (kein doppelter Anker). Zeiten streng steigend."""
    if not fractions or t1 is None or t0 is None or t1 <= t0:
        return []
    out, last = [], t0
    for i, f in enumerate(fractions):
        if i == 0 or f is None:
            continue
        t = t0 + (t1 - t0) * f
        if last < t < t1:
            out.append((t, line_of_card(i)))
            last = t
    return out


def beat_in_window(pos, t0, t1, total):
    """Beat der Figur zur Songzeit pos, anteilig im Fenster t0..t1 (begrenzt auf 0..total)."""
    if t1 <= t0 or not total:
        return 0.0
    f = max(0.0, min(1.0, (pos - t0) / (t1 - t0)))
    return f * total


def beat_by_tempo(pos, t0, bpm):
    """Beat seit Fensterbeginn im Song-Tempo (fuer abgebrochene Sequenzen: deren Animation
    endet an der Abbruchzeile, die Gesamtlaenge ist unbekannt)."""
    if not bpm or bpm <= 0:
        return 0.0
    return max(0.0, (pos - t0) * bpm / 60.0)


def part_windows(anchors, start_lines, block_of_line):
    """Figuren-Fenster [(Start, Ende, nur_Rahmen, Block)] je Figuren-Teil aus den SyncPoints.

    anchors:       [(Sekunde, Zeile)] nach Zeit sortiert (Zeilen im Original-Dokument).
    start_lines:   Zeilen, auf denen ein Teil beginnt (FIGURE-Ueberschriften, key[0]).
    block_of_line: Zeile -> (l0, l1) des Figuren-Blocks oder None.
    Ende = letzter Anker im selben Block vor dem naechsten Teil-Anfang (beim Auto-Sync der
    Ende-Anker auf der letzten Blockzeile), None ohne einen solchen.
    nur_Rahmen = zwischen Anfang und Ende liegen keine weiteren Anker im Block (nur dann
    setzt der Lesebalken Zwischenanker nach Beats; eigene Anker des Callers haben Vorrang).
    """
    starts = [i for i, (_t, line) in enumerate(anchors) if line in start_lines]
    out = []
    for n, i in enumerate(starts):
        t0, line0 = anchors[i]
        block = block_of_line(line0)
        stop = starts[n + 1] if n + 1 < len(starts) else len(anchors)
        inner = [j for j in range(i + 1, stop)
                 if block and block[0] < anchors[j][1] <= block[1]]
        if not inner:
            out.append((float(t0), None, False, block))
            continue
        end = inner[-1]
        out.append((float(t0), float(anchors[end][0]), len(inner) == 1, block))
    return out
