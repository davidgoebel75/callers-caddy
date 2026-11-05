"""Ergebnisdialog der Massenlaeufe im Potential-Dock (intern#226).

Bleiben Songs offen (Abbrechen im Probelauf oder im Rest, "Nein" bei der
Zeitschaetzung), meldet der Dialog den Abbruch mit der Zahl der offenen Songs.
"Uebersprungen" heisst: Erkennung ohne Ergebnis, nicht "Datei nicht gefunden".
"""
from types import SimpleNamespace

import pytest

import potential_widget
from i18n import _t
from potential_widget import PotentialWidget


class _Stub:
    """Nur die Methoden des Abschlusses, ohne Widget-Aufbau."""
    _on_bpm_sample_done = PotentialWidget._on_bpm_sample_done
    _on_bpm_bulk_done = PotentialWidget._on_bpm_bulk_done
    _finalize_bpm = PotentialWidget._finalize_bpm
    _show_bpm_result = PotentialWidget._show_bpm_result
    _on_sstart_sample_done = PotentialWidget._on_sstart_sample_done
    _on_sstart_bulk_done = PotentialWidget._on_sstart_bulk_done
    _finalize_sstart = PotentialWidget._finalize_sstart
    _show_sstart_result = PotentialWidget._show_sstart_result
    _on_syncpts_sample_done = PotentialWidget._on_syncpts_sample_done
    _on_syncpts_bulk_done = PotentialWidget._on_syncpts_bulk_done
    _finalize_syncpts = PotentialWidget._finalize_syncpts
    _show_syncpts_result = PotentialWidget._show_syncpts_result
    _on_bulk_done = PotentialWidget._on_bulk_done

    def __init__(self):
        self._bulk_worker = None
        self.on_bulk_done = None
        self.runs = []

    def _close_progress(self):
        pass

    def refresh(self):
        pass

    def _load_no_bpm_table(self):
        pass

    def _load_no_singing_start_table(self):
        pass

    def _load_check(self, _check):
        pass

    def _run_bulk_bpm(self, jobs):
        self.runs.append(jobs)

    _run_bulk_sstart = _run_bulk_syncpts = _run_bulk_bpm


@pytest.fixture
def dialog(monkeypatch):
    """Faengt den Ergebnistext ab; die Zeitschaetzung beantwortet `answer`."""
    shown = []
    state = SimpleNamespace(answer=potential_widget.QMessageBox.Yes, shown=shown)
    monkeypatch.setattr(potential_widget.QMessageBox, "information",
                        lambda _p, _title, text: shown.append(text))
    monkeypatch.setattr(potential_widget.QMessageBox, "question",
                        lambda *a, **k: state.answer)
    return state


def _worker(cancelled, jobs=()):
    return SimpleNamespace(cancelled=cancelled, _cancelled=cancelled,
                           _jobs=list(jobs))


def _cancel_line(n):
    return _t('pot_bulk_cancelled', open=n)


# ---- BPM ---------------------------------------------------------------

def _bpm(total, rest):
    w = _Stub()
    w._bpm_total = total
    w._bpm_missing = []
    w._bpm_accum = (0, 0)
    w._bpm_rest_jobs = [object()] * rest
    return w


def test_bpm_vollstaendig_meldet_keinen_abbruch(dialog):
    w = _bpm(20, 15)
    w._bulk_worker = _worker(False)
    w._on_bpm_sample_done(5, 0)
    w._on_bpm_bulk_done(14, 1)
    assert len(dialog.shown) == 1
    assert _t('pot_fix_all_done', done=19, total=20, skipped=1) in dialog.shown[0]
    assert "Abgebrochen" not in dialog.shown[0]


def test_bpm_abbruch_im_rest_meldet_offene_songs(dialog):
    # Fall aus dem Issue: 5 Probelauf + 2 im Rest, dann Abbrechen
    w = _bpm(510, 505)
    w._bulk_worker = _worker(False)
    w._on_bpm_sample_done(5, 0)
    w._on_bpm_bulk_done(2, 0)
    assert _cancel_line(503) in dialog.shown[0]


def test_bpm_abbruch_im_probelauf(dialog):
    w = _bpm(20, 15)
    w._bulk_worker = _worker(True)
    w._on_bpm_sample_done(2, 0)
    assert w.runs == []
    assert _cancel_line(18) in dialog.shown[0]


def test_bpm_nein_bei_zeitschaetzung_zaehlt_als_abbruch(dialog):
    dialog.answer = potential_widget.QMessageBox.No
    w = _bpm(20, 15)
    w._bulk_worker = _worker(False)
    w._on_bpm_sample_done(5, 0)
    assert w.runs == []
    assert _cancel_line(15) in dialog.shown[0]


def test_bpm_uebersprungen_nennt_keinen_dateigrund(dialog):
    w = _bpm(3, 0)
    w._on_bpm_bulk_done(2, 1)
    assert "Datei nicht gefunden" not in dialog.shown[0]


# ---- Anfang/Ende und Sync-Punkte --------------------------------------

def test_sstart_nein_bei_zeitschaetzung_zaehlt_als_abbruch(dialog):
    dialog.answer = potential_widget.QMessageBox.No
    w = _Stub()
    w._sstart_total = 20
    w._sstart_missing = []
    w._sstart_rest_jobs = [object()] * 15
    w._bulk_worker = _worker(False)
    w._on_sstart_sample_done(4, 1, [])
    assert _cancel_line(15) in dialog.shown[0]


def test_sstart_vollstaendig_meldet_keinen_abbruch(dialog):
    w = _Stub()
    w._sstart_total = 3
    w._sstart_missing = []
    w._sstart_accum = (0, 0)
    w._sstart_unsure = []
    w._on_sstart_bulk_done(2, 1, [])
    assert "Abgebrochen" not in dialog.shown[0]


def test_syncpts_abbruch_im_rest(dialog):
    w = _Stub()
    w._syncpts_total = 20
    w._syncpts_missing = ["fehlt: Lyric-Datei"]   # zaehlt nicht als offen
    w._syncpts_rest_jobs = [object()] * 15
    w._bulk_worker = _worker(False)
    w._on_syncpts_sample_done(5, 0, [])
    w._bulk_worker = _worker(True)
    w._on_syncpts_bulk_done(3, 1, [])
    assert _cancel_line(11) in dialog.shown[0]


# ---- Auto-Loop, Beat-Snap, Loop-Optimieren ------------------------------

def test_loop_lauf_abbruch_meldet_offene_songs(dialog):
    w = _Stub()
    w._bulk_worker = _worker(True, jobs=range(10))
    w._on_bulk_done(3, 1)
    assert _t('pot_fix_all_done', done=3, total=4, skipped=1) in dialog.shown[0]
    assert _cancel_line(6) in dialog.shown[0]


def test_loop_lauf_vollstaendig_meldet_keinen_abbruch(dialog):
    w = _Stub()
    w._bulk_worker = _worker(False, jobs=range(4))
    w._on_bulk_done(3, 1)
    assert "Abgebrochen" not in dialog.shown[0]
