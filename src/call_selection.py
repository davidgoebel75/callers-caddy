"""
Geteilte Call-Auswahl-Logik fuer das To-Call-Widget und den [to_call]-Shortcode
(BL-199).

Eine Stelle loest eine Auswahl in eine konkrete Call-Liste auf; eine Stelle
baut aus einer Auswahl den kuerzest-moeglichen Shortcode. Beides nutzen sowohl
der "Fuellen"-Dialog des Widgets als auch das Einfuegen/Abhaken in den Notizen.

Shortcode-Formen (Namen-basiert, im Notiz-Rohtext lesbar):
  [to_call program="Mainstream (2026)"]                     -> ganzes Programm
  [to_call program="Mainstream (2026)" except="Scoot Back"] -> Programm minus X
  [to_call calls="Square Thru, Swing Thru"]                 -> explizite Liste

Sweet-Spot: Sind mehr als die Haelfte der Programm-Calls gewaehlt, ist die
Ausnahme-Liste kuerzer -> program+except. Sonst die explizite calls-Liste.
"""


def _split_names(raw) -> list:
    """Komma-separierte Namensliste aus einem Shortcode-Wert -> Liste (getrimmt)."""
    if not raw:
        return []
    return [part.strip() for part in str(raw).split(",") if part.strip()]


def _all_calls_by_name(db) -> dict:
    """{lower(name): (entity_id, canonical_name)} ueber alle echten Calls."""
    return {name.strip().lower(): (eid, name) for eid, name in db.get_real_calls()}


def resolve_calls(db, program: str = "", calls=None, except_names=None) -> list:
    """Loest eine Auswahl in eine Call-Liste auf.

    Args:
        program: Programm-Label (call_programs.program), z. B. "Mainstream (2026)".
        calls: explizite Namensliste (Liste ODER komma-separierter String).
        except_names: bei Programm-Auswahl auszunehmende Namen (Liste/String).

    Prioritaet: explizite `calls` schlagen `program`. Returns Liste von
    (entity_id, canonical_name) in Teaching-Order (bzw. Eingabereihenfolge bei
    expliziter Liste).
    """
    call_list = calls if isinstance(calls, list) else _split_names(calls)
    if call_list:
        lut = _all_calls_by_name(db)
        out = []
        for nm in call_list:
            hit = lut.get(nm.strip().lower())
            if hit:
                out.append(hit)
        return out

    base = db.get_calls_for_program(program) if program else []
    ex = except_names if isinstance(except_names, list) else _split_names(except_names)
    if ex:
        ex_set = {n.strip().lower() for n in ex}
        base = [(eid, name) for (eid, name) in base
                if name.strip().lower() not in ex_set]
    return base


def build_shortcode_params(program_label: str, all_names: list,
                           selected_names: list) -> dict:
    """Baut die kuerzeste Shortcode-Parameter-Form fuer eine Auswahl.

    Args:
        program_label: Label des Programms (leer -> immer explizite Liste).
        all_names: alle Call-Namen des Programms (Teaching-Order).
        selected_names: die gewaehlten Namen (Teilmenge von all_names).

    Returns:
        dict fuer shortcode_text("to_call", ...).
    """
    all_order = list(all_names)
    sel = set(selected_names)
    selected_ordered = [n for n in all_order if n in sel]

    if program_label and len(selected_ordered) == len(all_order) and all_order:
        # Alles gewaehlt -> nur Programm
        return {"program": program_label}

    if program_label and len(selected_ordered) * 2 >= len(all_order) and all_order:
        # Mehrheit gewaehlt -> Programm + Ausnahmen (kuerzer)
        except_ordered = [n for n in all_order if n not in sel]
        if not except_ordered:
            return {"program": program_label}
        return {"program": program_label, "except": ", ".join(except_ordered)}

    # Minderheit (oder kein Programm) -> explizite Liste
    return {"calls": ", ".join(selected_ordered)}
