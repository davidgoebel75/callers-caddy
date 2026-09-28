"""Crash-Hinweis meldet nur neue Logs (intern #123).

Die Logs unter logs/crashes/ werden nie geloescht. Ohne Filter zeigte der
Start-Hinweis deshalb bei jedem Start alle jemals geschriebenen Logs. Mit
`newer_than` (Dateiname des zuletzt gemeldeten Logs) bleiben nur neuere uebrig.
"""
import os

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
