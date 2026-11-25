"""Square-Flow-Ergebnis fuer die Anzeige aufbereiten (intern#247), ohne Qt.

Square Flow und Sequenz-Detail zeigen dasselbe Ergebnis an zwei Stellen. Hier steht,
was daraus wird: Hinweiszeilen, Warnung ja/nein, Takte und Fehlertext, wenn die Engine
fehlt oder abgestuerzt ist.
"""
from i18n import _t

QT_FREE = True


def engine_failed(result):
    """True, wenn kein Analyse-Ergebnis vorliegt (Engine fehlt oder ist abgestuerzt).
    Ein Abbruch traegt auch "error", hat aber ein Analyse-Ergebnis."""
    return "stufe1" not in result


def engine_missing(result):
    return result.get("error") == "engine_missing"


def hint_lines(r, calls):
    """Hinweise zum Ergebnis: (Textzeilen, Warnung ja/nein). Warnung = Abbruch, rot,
    strittig; ergaenzte Bedeutungen allein sind ein Hinweis ohne Warnung."""
    lines, strong = [], False
    if not r["stufe1"]:
        strong = True
        fc = r.get("fail_card")
        text = calls[fc] if fc is not None and fc < len(calls) else ""
        lines.append(_t("sf_hint_abbruch").format(line=(fc + 1) if fc is not None else "?",
                                                  text=text))
    elif r.get("urteil") == "rot":
        strong = True
        lines.append(_t("sf_hint_rot").format(type=r.get("type") or ""))
    elif r.get("urteil") == "strittig":
        strong = True
        lines.append(_t("sf_hint_strittig"))
    meaning = [x for x in (r.get("read_as") or []) if x.get("meaning")]
    for x in meaning[:6]:
        lines.append(_t("sf_hint_read_as").format(line=x["card"] + 1, text=x["text"])
                     + f" ({_t('sf_kind_' + x['kind'])})")
    if meaning:
        lines.append(_t("sf_hint_root"))
    return lines, strong


def detail_info(calls, result):
    """Ergebnis -> Angaben fuer das Sequenz-Detail (``set_flow_info``): Takte,
    Abbruchzeile, Warnsymbol mit Text. None bleibt None (Anzeige leeren)."""
    if result is None:
        return None
    if engine_failed(result):
        if engine_missing(result):
            text = _t("sf_engine_missing")
        else:
            text = _t("seq_flow_warn_engine").format(error=result.get("error") or "")
        return {"warn": True, "warn_text": text}
    lines, strong = hint_lines(result, calls)
    return {
        "beats": result.get("card_beats") or [],
        "total": result.get("beats_total"),
        "singer": (result.get("type") or "").lower().startswith("singer"),
        "fail_card": result.get("fail_card"),
        "warn": strong,
        "warn_text": "\n".join(lines) if strong else "",
    }
