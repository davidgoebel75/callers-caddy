"""Crash-Hinweis meldet nur neue Logs (intern #123).

Die Logs unter logs/crashes/ werden nie geloescht. Ohne Filter zeigte der
Start-Hinweis deshalb bei jedem Start alle jemals geschriebenen Logs. Mit
`newer_than` (Dateiname des zuletzt gemeldeten Logs) bleiben nur neuere uebrig.
"""
import os

import crash_handler
from crash_handler import CrashLogger


def _touch(folder, name):
    folder.mkdir(parents=True, exist_ok=True)
    (folder / name).write_text("x", encoding="utf-8")


def test_find_crash_logs_filters_already_notified(tmp_path):
    crashes = tmp_path / "logs" / "crashes"
    _touch(crashes, "crash_20260901_100000.log")
    _touch(crashes, "crash_20260920_120000.log")
    _touch(crashes, "crash_20260925_080000.log")
    _touch(tmp_path, "crash_20260801_090000.log")  # Legacy-Ort

    all_logs = CrashLogger.find_crash_logs(str(tmp_path))
    assert [os.path.basename(p) for p in all_logs] == [
        "crash_20260925_080000.log",
        "crash_20260920_120000.log",
        "crash_20260901_100000.log",
        "crash_20260801_090000.log",
    ]

    new = CrashLogger.find_crash_logs(
        str(tmp_path), newer_than="crash_20260920_120000.log")
    assert len(new) == 1 and new[0].endswith("crash_20260925_080000.log")

    assert CrashLogger.find_crash_logs(
        str(tmp_path), newer_than="crash_20260925_080000.log") == []


def test_new_name_with_microseconds_sorts_after_old_name_same_second(tmp_path):
    """Neues Format crash_..._%f.log liegt hinter altem Namen derselben Sekunde."""
    crashes = tmp_path / "logs" / "crashes"
    _touch(crashes, "crash_20260925_080000.log")          # altes Format
    _touch(crashes, "crash_20260925_080000_123456.log")   # neues Format

    logs = CrashLogger.find_crash_logs(str(tmp_path))
    assert os.path.basename(logs[0]) == "crash_20260925_080000_123456.log"

    new = CrashLogger.find_crash_logs(
        str(tmp_path), newer_than="crash_20260925_080000.log")
    assert [os.path.basename(p) for p in new] == [
        "crash_20260925_080000_123456.log"]


# --- intern#166: DB-Update-Problem bei jedem Start -------------------------

class _Settings(dict):
    """Ersatz fuer QSettings: value/setValue/sync auf einem Dict."""

    def value(self, key, default=None):
        return self.get(key, default)

    def setValue(self, key, value):
        self[key] = value

    def sync(self):
        pass


def _logs(tmp_path):
    return CrashLogger.find_crash_logs(str(tmp_path))


def test_report_once_writes_only_when_problems_change(tmp_path, monkeypatch):
    monkeypatch.setattr(crash_handler, "_logger", CrashLogger(str(tmp_path)))
    settings = _Settings()

    first = crash_handler.report_once(settings, "DB", ["songs.x: kaputt"])
    assert first and len(_logs(tmp_path)) == 1

    # Naechster Start, gleiches Problem: kein weiteres Log
    assert crash_handler.report_once(settings, "DB", ["songs.x: kaputt"]) == ""
    assert len(_logs(tmp_path)) == 1

    # Problemliste geaendert: neues Log
    assert crash_handler.report_once(settings, "DB", ["songs.y: kaputt"])
    assert len(_logs(tmp_path)) == 2


def test_report_once_log_counts_as_notified(tmp_path, monkeypatch):
    """Das Log erscheint beim naechsten Start nicht im allgemeinen Hinweis,
    sonst liegen zwei Dialoge uebereinander."""
    monkeypatch.setattr(crash_handler, "_logger", CrashLogger(str(tmp_path)))
    settings = _Settings()

    crash_handler.report_once(settings, "DB", ["songs.x: kaputt"])

    assert CrashLogger.find_crash_logs(
        str(tmp_path),
        newer_than=settings.value(crash_handler.LAST_NOTIFIED_KEY, "")) == []


def test_mark_notified_never_moves_back():
    settings = _Settings()
    crash_handler.mark_notified(settings, "/x/crash_20261007_080000_000001.log")
    crash_handler.mark_notified(settings, "/x/crash_20261001_080000_000001.log")
    assert settings[crash_handler.LAST_NOTIFIED_KEY] == \
        "crash_20261007_080000_000001.log"


def test_write_log_same_timestamp_keeps_both(tmp_path, monkeypatch):
    """Die Uhr rueckt unter Windows nur etwa jede Millisekunde weiter. Zwei
    Logs mit gleichem Zeitstempel duerfen sich nicht ueberschreiben, und das
    zweite muss als neuer gelten."""
    from datetime import datetime as real_datetime

    class _FrozenClock(real_datetime):
        @classmethod
        def now(cls, tz=None):
            return real_datetime(2026, 10, 7, 8, 0, 0, 123456)

    monkeypatch.setattr(crash_handler, "datetime", _FrozenClock)
    logger = CrashLogger(str(tmp_path))
    first = logger.write_report("A")
    second = logger.write_report("B")

    assert first != second
    assert _logs(tmp_path) == [second, first]
