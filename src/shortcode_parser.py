"""
Shortcode-Parser fuer Notizen.

Syntax:  [action_id "positional value"]
         [action_id key="value" key2=42]
         [action_id]

Beispiele:
  [load_song "Cotton-Eyed Joe"]
  [sequence_view id=42]
  [sequence_view contains="Swing Thru" limit="MS"]
  [sequence_view]
"""

import re
from typing import NamedTuple


class Shortcode(NamedTuple):
    action_id: str
    params: dict   # str/int-Werte; positional string steht unter '_value'


# Aussen-Klammer: [action_id rest]
_SC_RE = re.compile(r'\[([A-Za-z_]\w*)([^\]]*)\]')

# key="value"  oder  key='value'
_KV_STR_RE = re.compile(r'(\w+)=["\']([^"\']*)["\']')

# key=42  (nur Ziffern, kein Anführungszeichen)
_KV_INT_RE = re.compile(r'(\w+)=(\d+)(?!\w)')

# Erstes positionales Anführungszeichen-Argument (ohne key=)
_POS_STR_RE = re.compile(r'(?<!=)["\']([^"\']+)["\']')


def parse_shortcodes(text: str) -> list[Shortcode]:
    """Gibt alle Shortcodes aus dem Text zurueck, in Reihenfolge ihres Auftretens."""
    result = []
    for m in _SC_RE.finditer(text):
        action_id = m.group(1)
        rest = m.group(2).strip()
        params: dict = {}

        # Benannte String-Parameter
        for kv in _KV_STR_RE.finditer(rest):
            params[kv.group(1)] = kv.group(2)

        # Benannte Integer-Parameter (nur wenn noch nicht als String erfasst)
        for kv in _KV_INT_RE.finditer(rest):
            if kv.group(1) not in params:
                params[kv.group(1)] = int(kv.group(2))

        # Positionales Argument (erstes Anführungszeichen-Token ohne key=)
        if not params:
            pm = _POS_STR_RE.search(rest)
            if pm:
                params['_value'] = pm.group(1)

        result.append(Shortcode(action_id, params))
    return result


def shortcode_text(action_id: str, params: dict) -> str:
    """Serialisiert einen Shortcode zurueck als Text (fuer Notiz-Einfuegung)."""
    if not params:
        return f"[{action_id}]"
    parts = []
    for k, v in params.items():
        if k == '_value':
            parts.append(f'"{v}"')
        elif isinstance(v, int):
            parts.append(f'{k}={v}')
        else:
            parts.append(f'{k}="{v}"')
    return f"[{action_id} {' '.join(parts)}]"


def song_shortcode_text(song_title: str, mode: str = "") -> str:
    """Baut den [load_song]-Shortcode-Text fuer einen Song.

    mode='P'/'S' wird als benannter Parameter geschrieben:
    [load_song title="..." mode="P"] (verhindert Parser-Kollision mit einem
    positionalen Wert). Ohne mode: klassisches Format [load_song "..."]
    (Abwaertskompatibilitaet)."""
    if mode:
        params = {"title": song_title, "mode": mode}
    else:
        params = {"_value": song_title}
    return shortcode_text("load_song", params)
