"""Call-Map Export/Import (intern#79).

Qt-frei: Dateiformat, Parser und die Entscheidungshilfen fuer die
Konfliktklaerung. Die DB-Seite (Vergleich, Schreiben) steckt in song_db,
der Dialog in dialogs_mapping_conflict.

Formate:
- v2 (Export ab intern#79): Objekt mit Header und je Call-Text einem Eintrag
  samt Figuren-Menge und canonical_name:
      {"format": "callers-caddy-callmap", "version": 2, "exported_at": ...,
       "mappings": [{"call_text": ..., "mapped_by": ...,
                     "figures": [{"entity_id": ..., "canonical_name": ...}]}]}
  "figures": [] ist eine bewusste "keine Figur"-Zuordnung.
- v1 (alt): flache Liste, eine Zeile je Figur
      [{"call_text": ..., "entity_id": ..., "mapped_by": ...}, ...]
  entity_id null = "keine Figur".
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass, field

FORMAT_NAME = "callers-caddy-callmap"
FORMAT_VERSION = 2

# Rangfolge der Quellen fuer die Empfehlung (intern#88/#79):
# auto < inferred < manual. Unbekannte Werte (z. B. "import") zaehlen wie auto.
_SOURCE_RANK = {"auto": 0, "inferred": 1, "manual": 2}


def source_rank(mapped_by) -> int:
    return _SOURCE_RANK.get(str(mapped_by or "").lower(), 0)


@dataclass
class ImportedMapping:
    figures: list = field(default_factory=list)   # [] = "keine Figur"
    mapped_by: str = "auto"


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------

def build_export(db) -> dict:
    """v2-Export aller Zuordnungen der DB (Mengen, hoechste Figur zuerst)."""
    names = {}
    for eid, cname, _to, _prog in db.get_teaching_order_calls():
        names.setdefault(eid, cname)
    grouped = {}
    for r in db.get_all_call_text_mappings():
        entry = grouped.setdefault(
            r["call_text"], {"call_text": r["call_text"],
                             "mapped_by": r["mapped_by"] or "auto",
                             "figures": []})
        if r["entity_id"]:
            entry["figures"].append({"entity_id": r["entity_id"],
                                     "canonical_name": names.get(r["entity_id"], "")})
    return {
        "format": FORMAT_NAME,
        "version": FORMAT_VERSION,
        "exported_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "mappings": list(grouped.values()),
    }


# ---------------------------------------------------------------------------
# Import
# ---------------------------------------------------------------------------

def parse_import(data) -> dict:
    """Liest v1 (flache Liste) und v2 (Objekt mit Header).

    Rueckgabe {call_text: ImportedMapping}. Wirft ValueError bei unbekanntem
    Format.
    """
    if isinstance(data, list):
        return _parse_v1(data)
    if isinstance(data, dict) and data.get("format") == FORMAT_NAME:
        if int(data.get("version", 0)) > FORMAT_VERSION:
            raise ValueError(
                f"Call-Map-Version {data.get('version')} ist neuer als diese "
                f"Programmversion ({FORMAT_VERSION}).")
        return _parse_v2(data.get("mappings") or [])
    raise ValueError("Unbekanntes Call-Map-Format.")


def _parse_v1(rows: list) -> dict:
    out = {}
    for r in rows:
        if not isinstance(r, dict) or not r.get("call_text"):
            continue
        ct = str(r["call_text"])
        m = out.setdefault(ct, ImportedMapping(
            mapped_by=str(r.get("mapped_by") or "auto")))
        eid = r.get("entity_id")
        if eid and eid not in m.figures:
            m.figures.append(str(eid))
    return out


def _parse_v2(entries: list) -> dict:
    out = {}
    for e in entries:
        if not isinstance(e, dict) or not e.get("call_text"):
            continue
        figs = []
        for f in e.get("figures") or []:
            eid = f.get("entity_id") if isinstance(f, dict) else f
            if eid and eid not in figs:
                figs.append(str(eid))
        out[str(e["call_text"])] = ImportedMapping(
            figures=figs, mapped_by=str(e.get("mapped_by") or "auto"))
    return out


# ---------------------------------------------------------------------------
# Entscheidungshilfen fuer Konflikte (A = lokal, B = Import)
# ---------------------------------------------------------------------------

def recommend(local_figs, local_mb, import_figs, import_mb) -> str:
    """Empfehlung je Konflikt (David, intern#79):
    1. Detailliertheit: mehr Figuren gewinnt.
    2. Gleich viele: Quelle manual > inferred > auto.
    3. Gleichstand: A (lokal)."""
    if len(import_figs) != len(local_figs):
        return "B" if len(import_figs) > len(local_figs) else "A"
    return "B" if source_rank(import_mb) > source_rank(local_mb) else "A"


def _similarity(a, b) -> float:
    a, b = set(a), set(b)
    if not a and not b:
        return 1.0
    return len(a & b) / len(a | b)


def closer_to(target, local_figs, import_figs):
    """'A' oder 'B': welche Seite der Ziel-Menge (z. B. Mustererkennung)
    naeher kommt. None ohne Ziel oder bei Gleichstand."""
    if not target:
        return None
    sa, sb = _similarity(target, local_figs), _similarity(target, import_figs)
    if sa == sb:
        return None
    return "A" if sa > sb else "B"


def make_pattern_suggester(to_calls, figure_sets):
    """callable(call_text) -> Figuren, die die Mustererkennung fuer den Text
    sieht: der Mengen-Vorschlag (suggest_figure_set) oder, bei einem
    Volltreffer auf einen kanonischen Namen, genau diese Figur. [] ohne
    Erkennung. Lookups aus dem Stand VOR dem Import (figure_sets)."""
    from sequence_mapper import canon_key, figure_set_lookups, suggest_figure_set
    exact_lookup, rest_lookup = figure_set_lookups(to_calls, figure_sets)

    def suggest(call_text):
        figs = suggest_figure_set(call_text, exact_lookup, rest_lookup)[0]
        if figs:
            return list(figs)
        hit = exact_lookup.get(canon_key(call_text))
        return [hit] if hit else []
    return suggest


def manual_side(local_mb, import_mb):
    """'A'/'B': die Seite mit Quelle manual. None, wenn beide oder keine."""
    la = str(local_mb or "").lower() == "manual"
    lb = str(import_mb or "").lower() == "manual"
    if la == lb:
        return None
    return "A" if la else "B"
