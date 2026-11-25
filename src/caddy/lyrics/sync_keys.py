"""Sync-Point-Schluessel und Laenge des Singing-Call-Bodys (intern#140).

Ein SyncPoint liegt als song_property `lyric_sync_m<musik>_l<lyric>_<index>`.
Hier entstehen und zerfallen diese Schluessel; wer sie sonst braucht, ruft die
Funktionen auf, statt den Text selbst zu bauen (tests/app/test_architecture.py
achtet darauf). Der Wert (`"{sec:.2f}|{block}"`) bleibt bei den Aufrufern.
"""
import re

QT_FREE = True

KEY_PREFIX = "lyric_sync_"          # alle Sync-Point-Schluessel beginnen so

# Ein Singing-Call-Body ist starr 7 x 64 = 448 Beats. Die Zahl lebt hier und
# nicht in singing_body_detect, weil das numpy und loop_finder mitzieht.
SINGING_BODY_BEATS = 448

_KEY_RE = re.compile(r"^lyric_sync_m(\d+)_l(\d+)_(\d+)$")


def key_prefix(music_slot: int, lyric_slot: int) -> str:
    """Praefix aller Schluessel einer (Musik x Lyric)-Kombi."""
    return f"{KEY_PREFIX}m{music_slot}_l{lyric_slot}_"


def make_key(music_slot: int, lyric_slot: int, index: int) -> str:
    return f"{key_prefix(music_slot, lyric_slot)}{index}"


def parse_key(key: str) -> tuple[int, int, int] | None:
    """(Musik-Slot, Lyric-Slot, Index) oder None, wenn kein Sync-Point-Schluessel."""
    m = _KEY_RE.match(key)
    return (int(m.group(1)), int(m.group(2)), int(m.group(3))) if m else None


def is_sync_key(key: str) -> bool:
    return key.startswith(KEY_PREFIX)


def like_pattern(music_slot: int | None = None, lyric_slot: int | None = None) -> str:
    """SQL-LIKE-Muster: ohne Slots alle Sync-Schluessel, mit Slots eine Kombi.

    Das `_` ist in LIKE ein Joker; das war schon vorher so und bleibt (Verhalten
    nicht aendern)."""
    if music_slot is None or lyric_slot is None:
        return f"{KEY_PREFIX}%"
    return f"{key_prefix(music_slot, lyric_slot)}%"
