"""Eine Sequenz komplett durchrechnen: Mapping, Endkontrolle, Animation (intern#247).

Ergebnis fuer Square Flow und Sequenz-Detail, je Kartenzeile aufbereitet. `run` ist
engine.TamEngine.run (blockiert, nur im Hintergrund-Thread aufrufen).
"""
import hashlib
import json
import re
import zlib
from urllib.parse import quote

from caddy.choreo import mapping, pruefband, timeline

QT_FREE = True

FRAME_STEP = 0.25        # Beat-Abstand der Zwischenbilder fuer die Animation
# Erhoehen, wenn sich Inhalt oder Form des Ergebnisses aendern: alte Eintraege in
# sequence_choreo passen dann nicht mehr und werden neu gerechnet.
CACHE_FORMAT = 1
_MAPPING_FP = None


def mapping_fingerprint():
    """Stand von Mapping-Tabelle und Regeln (fuer den Cache-Schluessel)."""
    global _MAPPING_FP
    if _MAPPING_FP is None:
        from caddy.choreo import call_table
        h = hashlib.sha256()
        try:
            with open(call_table.CSV_PATH, "rb") as f:
                h.update(f.read())
        except OSError:
            pass
        h.update("|".join(sorted(mapping.RULES)).encode("utf-8"))
        _MAPPING_FP = h.hexdigest()
    return _MAPPING_FP


def input_hash(calls, seq_type, app=None):
    """Schluessel eines Ergebnisses: Kartenzeilen, Typ, App-Callnamen dieser Zeilen,
    Mapping-Stand und Ergebnisform. Die Engine-Version steht getrennt (engine_ver)."""
    app = app or {}
    blob = json.dumps([CACHE_FORMAT, mapping_fingerprint(), seq_type or "", list(calls),
                       {c: app[c] for c in calls if c in app}],
                      ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def to_cache(result):
    """Ergebnis ohne Animation als JSON (fuer sequence_choreo.result_json; die Animation
    steht gepackt daneben in anim_z, siehe anim_to_blob)."""
    return json.dumps({k: v for k, v in result.items() if k != "animation"},
                      ensure_ascii=False)


def from_cache(text, anim_z=None):
    """Ergebnis aus sequence_choreo. Mit anim_z (intern#263) kommt die Animation dazu,
    das Ergebnis ist dann vollstaendig; ohne (oder unlesbar) ist "animation" None."""
    try:
        res = json.loads(text)
    except (TypeError, ValueError):
        return None
    if not isinstance(res, dict):
        return None
    res["animation"] = anim_from_blob(anim_z)
    res["cached"] = True
    return res


# anim_z fuer "die Engine hat geantwortet, aber keine Animation geliefert" (z. B. ein nicht
# lesbarer Call): leeres Blob, in SQLite von NULL verschieden. Zaehlt als vollstaendig, damit
# die Engine die Sequenz nicht in jeder Sitzung neu rechnet (Review #196).
NO_ANIM = b""


def anim_to_blob(result):
    """Animation eines Ergebnisses zlib-gepackt fuer sequence_choreo.anim_z (intern#263).
    Ohne Animation: NO_ANIM, wenn das Ergebnis endgueltig ist, sonst None (Timeout oder
    Engine-Abbruch: beim naechsten Mal neu rechnen). Ca. 40 KB JSON werden zu ca. 10 KB."""
    if not isinstance(result, dict):
        return None
    anim = result.get("animation")
    if not anim:
        return None if result.get("transient") else NO_ANIM
    raw = json.dumps(anim, ensure_ascii=False, separators=(",", ":"))
    return zlib.compress(raw.encode("utf-8"), 6)


def cache_complete(cached, anim_z):
    """Ist ein Eintrag aus sequence_choreo fertig (Animation da oder NO_ANIM)?"""
    return bool(cached and cached.get("animation")) or (anim_z is not None
                                                        and bytes(anim_z) == NO_ANIM)


def anim_from_blob(blob):
    """Gegenstueck zu anim_to_blob; None bei fehlendem, leerem (NO_ANIM) oder kaputtem
    Eintrag."""
    if not blob:
        return None
    try:
        anim = json.loads(zlib.decompress(bytes(blob)).decode("utf-8"))
    except (zlib.error, TypeError, ValueError, UnicodeDecodeError):
        return None
    return anim if isinstance(anim, dict) and anim else None


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


# Lesart-Arten (mapping.alternatives "kinds"), bei denen Callers Caddy die Bedeutung
# ergaenzt oder geraten hat (intern#254, Stufe 3). Die uebrigen passen nur die Schreibweise an.
MEANING_KINDS = ("kontext", "kreis", "app", "mehrfach")


def _plain(text):
    t = (text or "").lower().replace("&", " and ")
    t = re.sub(r"\([^)]*\)", " ", t)
    return re.sub(r"[^a-z0-9/]+", " ", t).strip()


def read_as(calls, lines, src, alt_used):
    """Je getanzter Zeile, die anders gelesen wurde als sie auf der Karte steht:
    {"card": Kartenzeile, "text": gesendeter Text, "kind": Lesart-Art, "meaning": bool}."""
    out = []
    for i, line in enumerate(lines):
        if i >= len(alt_used) or i >= len(src) or src[i] is None or src[i] >= len(calls):
            continue
        if isinstance(line, dict):
            u = alt_used[i] or 0
            text = " | ".join(line["alts"][u])
            kind = line["kinds"][u]
        else:
            text, kind = line, "roh"
        card_text = calls[src[i]]
        if kind == "roh" and _plain(text) == _plain(card_text):
            continue
        out.append({"card": src[i], "text": text, "kind": kind,
                    "meaning": kind in MEANING_KINDS})
    return out


def resolved_calls(lines, alt_used=()):
    """Einzel-Calls, wie Taminations sie getanzt hat: bei Alternativen die benutzte,
    ohne Ergebnis (nach einem Abbruch) die erste."""
    out = []
    for i, line in enumerate(lines):
        if isinstance(line, dict):
            u = alt_used[i] if i < len(alt_used) and alt_used[i] is not None else 0
            out += line["alts"][u]
        else:
            out.append(line)
    return out


TAMINATIONS_URL = "https://www.tamtwirlers.org/taminations/#/?main=SEQUENCER&formation=Squared%20Set&calls="


def taminations_url(calls):
    """Deep-Link in den Taminations-Sequencer (Startformation Squared Set)."""
    return TAMINATIONS_URL + ";".join(quote(c, safe="") for c in calls)


def prepared_calls(calls, seq_type, app=None):
    """Einzel-Calls ohne Engine (erste Lesart je Zeile, mit Aufloese-Call)."""
    prep = mapping.prepare(list(calls), seq_type, app)
    lines, _zweit, _art = mapping.finish(prep)
    return resolved_calls(lines) + ([prep["end"]] if prep["end"] else [])


def analyse_sequence(run, calls, seq_type, app=None, frames=FRAME_STEP):
    """-> dict (siehe unten). calls = Kartenzeilen wie im Sequenz-Detail."""
    calls = list(calls)
    transient = []                       # Abbrueche ohne Engine-Urteil (Timeout, ...)
    _run = run

    def run(req):
        r = _run(req)
        if r.get("transient"):
            transient.append(r.get("error"))
        return r

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
    alt_used = res["engine"].get("alt_used") or []
    sent = resolved_calls(used, alt_used) + ([end] if with_end else [])
    return {
        "read_as": read_as(calls, used, prep["src"], alt_used),
        "sent": sent,
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
        # Beats der ganzen Animation (mit Aufloese-Call); Figuren-Uhr im Singing Call
        "anim_total": an.get("total_beats") or None,
        "beats_total": round(sum(known), 1) if known else None,
        # True: ein Lauf brach ohne Engine-Urteil ab, das Ergebnis ist nicht endgueltig
        "transient": bool(transient),
    }
