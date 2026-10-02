"""Buffer-Diagnostik darf die App nicht abschiessen (intern #54).

`get_audio_diag()` liest `_diag_history` — eine Deque, die der Audio-Callback
aus seinem eigenen Thread parallel befuellt und vorne wieder leert. Frueher
lief der Generator-Ausdruck direkt ueber die Live-Deque; traf eine Mutation
genau die Iteration, warf Python `RuntimeError: deque mutated during
iteration`, und weil der Aufruf im ungeschuetzten `_update_all`-Timer sitzt,
riss das die ganze App mit.

Der Test braucht weder Audio-Hardware noch einen zweiten Thread: eine Deque,
die beim Iterieren genau das tut was der Callback tut (anhaengen), macht den
Fall deterministisch. `get_audio_diag` wird ungebunden auf einem Dummy
aufgerufen — die Methode liest nur die vier `_diag_*`-Attribute.
"""
import collections
from types import SimpleNamespace

import pytest

from audio_engine import AudioEngine


class _MutiertBeimIterieren(collections.deque):
    """Deque, die sich waehrend der Iteration selbst veraendert.

    Genau das macht der Audio-Callback (`append` + `popleft`) — hier nur
    reproduzierbar statt zufaellig.
    """

    def __iter__(self):
        it = super().__iter__()
        self.append((1.0, 99.0))  # Mutation nach dem Anlegen des Iterators
        return it


def _engine(history):
    """Dummy mit denselben Attributen, die get_audio_diag anfasst."""
    return SimpleNamespace(_diag_history=history, _diag_buf_ms=42.0, _diag_xruns=3)


def test_rolling_minimum_aus_der_history():
    hist = collections.deque([(0.0, 80.0), (0.1, 25.0), (0.2, 60.0)])
    d = AudioEngine.get_audio_diag(_engine(hist))
    assert d == {"buf_ms": 42.0, "min10s": 25.0, "xruns": 3, "history_len": 3}


def test_leere_history_faellt_auf_den_letzten_buffer_stand_zurueck():
    d = AudioEngine.get_audio_diag(_engine(collections.deque()))
    assert d["min10s"] == 42.0
    assert d["history_len"] == 0


def test_mutation_waehrend_des_lesens_stuerzt_nicht_ab():
    # Gegenprobe: ohne Snapshot fliegt genau hier der RuntimeError
    hist = _MutiertBeimIterieren([(0.0, 80.0), (0.1, 25.0)])
    with pytest.raises(RuntimeError, match="mutated during iteration"):
        min(v for _, v in hist)

    d = AudioEngine.get_audio_diag(_engine(hist))
    # Diagnostik ist unkritisch: lieber Fallback-Werte als ein Absturz
    assert d["buf_ms"] == 42.0
    assert d["xruns"] == 3
