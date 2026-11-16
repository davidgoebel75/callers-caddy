"""Audio-Dateifilter (intern#252): Kein Dialog bietet *.m4a an - libsndfile
kann kein AAC, die Datei liesse sich nicht laden. Hinweis-Sound und Regel
"Play Sound" nutzen denselben uebersetzten Filter wie der Oeffnen-Dialog."""
import re

from i18n import _t
from rule_definitions import register_v1_definitions
from rule_engine import RuleEngine
from settings_dialog import SETTINGS_META
from zip_import import AUDIO_EXTENSIONS


def _exts(file_filter):
    first = _t(file_filter).split(";;")[0]
    return set(re.findall(r"\*(\.\w+)", first))


def test_filter_bietet_genau_die_ladbaren_endungen(tmp_path):
    eng = RuleEngine(str(tmp_path))
    register_v1_definitions(eng)
    rule_meta = eng.registry.actions["play_sound"].params_schema["path"]["file_filter"]
    sound_meta = SETTINGS_META["audio/alert_sound_path"]["file_filter"]
    for f in (sound_meta, rule_meta, "filter_audio_files"):
        assert _exts(f) == set(AUDIO_EXTENSIONS)
