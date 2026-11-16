"""Audio-Dateifilter (intern#252): Kein Dialog bietet *.m4a an - libsndfile
kann kein AAC, die Datei liesse sich nicht laden. Hinweis-Sound und Regel
"Play Sound" nutzen denselben uebersetzten Filter wie der Oeffnen-Dialog."""
import re

import i18n
import main
from rule_definitions import register_v1_definitions
from rule_engine import RuleEngine
from settings_dialog import SETTINGS_META
from zip_import import AUDIO_EXTENSIONS


def _exts(text):
    first = text.split(";;")[0]
    return set(re.findall(r"\*(\.\w+)", first))


def test_filter_bietet_genau_die_ladbaren_endungen(tmp_path):
    eng = RuleEngine(str(tmp_path))
    register_v1_definitions(eng)
    rule_meta = eng.registry.actions["play_sound"].params_schema["path"]["file_filter"]
    sound_meta = SETTINGS_META["audio/alert_sound_path"]["file_filter"]
    assert sound_meta == rule_meta == "filter_audio_files"
    for lang, text in i18n._translations["filter_audio_files"].items():
        assert _exts(text) == set(AUDIO_EXTENSIONS), lang


def test_import_endungen_gleich():
    """Filter und Import duerfen nicht auseinanderlaufen."""
    assert set(main.P29MainWindow._IMPORT_AUDIO_EXTS) == set(AUDIO_EXTENSIONS)
