"""Eine Sequenz komplett durchrechnen: Mapping, Endkontrolle, Animation (intern#247).

Ergebnis fuer Square Flow und Sequenz-Detail, je Kartenzeile aufbereitet. `run` ist
engine.TamEngine.run (blockiert, nur im Hintergrund-Thread aufrufen).
"""
from caddy.choreo import mapping, pruefband, timeline

QT_FREE = True

FRAME_STEP = 0.25        # Beat-Abstand der Zwischenbilder fuer die Animation


def _card_spans(n_cards, src, end_src, call_starts, total, n_body):
    """(Start-Beat, End-Beat) je Kartenzeile oder None. Gesendete Zeilen ab n_body sind der
    Aufloese-Call (gehoert zu end_src)."""
    spans = [None] * n_cards
    for i, start in enumerate(call_starts):
        end = call_starts[i + 1] if i + 1 < len(call_starts) else total
        card = src[i] if i < n_body else end_src
        if card is None or card >= n_cards:
            continue
        old = spans[card]
        spans[card] = (start, end) if old is None else (min(old[0], start), max(old[1], end))
    return spans


def analyse_sequence(run, calls, seq_type, app=None, frames=FRAME_STEP):
    """-> dict (siehe unten). calls = Kartenzeilen wie im Sequenz-Detail."""
    calls = list(calls)
    prep = mapping.prepare(calls, seq_type, app)
    hreq = mapping.heimplatz_request(prep)
    lines, zweit, art = mapping.finish(prep, run(hreq) if hreq else None)
    res = pruefband.analyse(run, prep["type"], prep["end"], prep["n_start"], lines, zweit, art)
    used = res["lines"]
    end = prep["end"]
    # Animation mit Aufloese-Call (Singer: Swing + Promenade); scheitert der, ohne ihn.
    anim = None
    with_end = bool(end and res["stufe1"])
    if with_end:
        anim = run({"lines": used + [end], "frames": frames})
        if not anim.get("ok"):
            anim, with_end = None, False
    if anim is None:
        anim = run({"lines": used, "frames": frames})
    an = anim.get("animation") or {}
    line_beats = list(anim.get("beats") or [])
    beats_end = line_beats[len(used)] if with_end and len(line_beats) > len(used) else None
    card_beats = timeline.card_beats(len(calls), prep["src"], line_beats[:len(used)],
                                     prep["end_src"], beats_end)
    spans = _card_spans(len(calls), prep["src"], prep["end_src"],
                        an.get("call_starts") or [], an.get("total_beats") or 0, len(used))
    fail_card = None
    if not res["stufe1"] and res["fail_pos"] is not None and res["fail_pos"] < len(prep["src"]):
        fail_card = prep["src"][res["fail_pos"]]
    known = [b for b in card_beats if b is not None]
    return {
        "type": prep["type"],
        "lines": used,
        "src": prep["src"],
        "end": end,
        "end_src": prep["end_src"],
        "with_end": with_end,
        "n_start": prep["n_start"],
        "stufe1": res["stufe1"],
        "urteil": res["urteil"],
        "band": res["band"],
        "tam": res["tam"],
        "lesart": res["lesart"],
        "fassung": res["fassung"],
        "error": res["error"],
        "fail_pos": res["fail_pos"],
        "fail_card": fail_card,
        "targets": pruefband.targets_for(prep["type"]),
        "animation": an,
        "tam_calls": anim.get("tam_calls") or [],
        "card_beats": card_beats,
        "card_spans": spans,
        "beats_total": round(sum(known), 1) if known else None,
    }
