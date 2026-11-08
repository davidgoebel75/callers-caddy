"""Sync-Point-Schluessel und Body-Laenge (intern#140)."""
import pathlib

import pytest

from caddy.lyrics import sync_keys
from caddy.lyrics.sync_keys import (SINGING_BODY_BEATS, is_sync_key, key_prefix,
                                    like_pattern, make_key, parse_key)


def test_praefix_und_schluessel_wie_bisher():
    assert key_prefix(1, 1) == "lyric_sync_m1_l1_"
    assert make_key(2, 10, 7) == "lyric_sync_m2_l10_7"


@pytest.mark.parametrize("m, l, i", [(1, 1, 1), (12, 3, 45), (2, 10, 100)])
def test_rundreise(m, l, i):
    assert parse_key(make_key(m, l, i)) == (m, l, i)


@pytest.mark.parametrize("key", [
    "lyric_sync_m1_l1_", "lyric_sync_m1_l1_x", "lyric_sections_l1_a",
    "lyric_sync_move_line", "", "xlyric_sync_m1_l1_1", "lyric_sync_m1_l1_1x"])
def test_fremdschluessel_werden_abgelehnt(key):
    assert parse_key(key) is None


def test_is_sync_key():
    assert is_sync_key("lyric_sync_m1_l1_3")
    assert is_sync_key("lyric_sync_irgendwas")
    assert not is_sync_key("lyric_sections_l1_1")


def test_like_muster():
    assert like_pattern() == "lyric_sync_%"
    assert like_pattern(1, 1) == "lyric_sync_m1_l1_%"
    assert like_pattern(2, 10) == "lyric_sync_m2_l10_%"


def test_body_laenge():
    assert SINGING_BODY_BEATS == 448 == 7 * 64


def test_body_detect_nutzt_dieselbe_zahl():
    src = (pathlib.Path(sync_keys.__file__).parents[2] / "singing_body_detect.py")
    assert "SINGING_BODY_BEATS as BODY_BEATS" in src.read_text(encoding="utf-8")


def test_like_pattern_mit_nur_einem_slot_ist_allgemein():
    assert like_pattern(1) == "lyric_sync_%"
    assert like_pattern(lyric_slot=1) == "lyric_sync_%"
