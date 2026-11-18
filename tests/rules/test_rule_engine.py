"""RuleEngine ohne Qt: Speichern/Laden, INI-Overrides, eigene Regeln,
Stream-Deck-Nummern, Bedingungen, manuelles Ausfuehren, Suspend, Log."""
import json

import pytest

from rule_engine import ActionDef, ConditionDef, Rule, RuleEngine


class FakeSettings:
    """Das Stueck QSettings, das die Engine benutzt."""

    def __init__(self, values=None):
        self.values = dict(values or {})
        self.synced = 0

    def value(self, key, default=None, type=None):
        v = self.values.get(key, default)
        return bool(v) if type is bool else v

    def setValue(self, key, value):
        self.values[key] = value

    def sync(self):
        self.synced += 1


def _rule(id, trigger="t", actions=("a",), conditions=(), **kw):
    return Rule(id=id, name=id.upper(), active=kw.pop("active", True),
                trigger=trigger,
                conditions=[[ConditionDef(c) for c in g] for g in conditions],
                actions=[ActionDef(a) for a in actions], **kw)


def _write(path, rules):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"version": 1,
                                "rules": [r.to_dict() for r in rules]}),
                    encoding="utf-8")


@pytest.fixture
def engine(tmp_path):
    eng = RuleEngine(str(tmp_path))
    yield eng
    eng.close()


# --- Rule.to_dict / from_dict ------------------------------------------------

def test_rule_round_trip_alle_felder():
    r = Rule(id="usr_1", name="Ä-Regel", active=False, trigger="key_w",
             conditions=[[ConditionDef("c1", {"x": 1}), ConditionDef("c2")],
                         [ConditionDef("c3")]],
             actions=[ActionDef("a1", {"dock": "lyrics"})],
             once_per_song=True, button_number=3,
             button_icon="play.svg", button_tooltip="Tip")
    back = Rule.from_dict(r.to_dict(), source="user")
    assert back == r


def test_to_dict_laesst_standardwerte_weg():
    d = _rule("r").to_dict()
    assert "once_per_song" not in d
    assert "button_number" not in d


def test_to_dict_deck_felder_nur_mit_buttonnummer():
    d = _rule("r", button_icon="x.svg", button_tooltip="t").to_dict()
    assert "button_icon" not in d and "button_tooltip" not in d
    d = _rule("r", button_number=2).to_dict()
    assert d["button_number"] == 2
    assert "button_icon" not in d and "button_tooltip" not in d


def test_from_dict_fehlende_felder():
    r = Rule.from_dict({"button_number": None}, source="system")
    assert (r.id, r.name, r.active, r.trigger) == ("", "", True, "")
    assert r.conditions == [] and r.actions == []
    assert r.source == "system" and r.button_number == 0
    assert r.once_per_song is False
    assert (r.button_icon, r.button_tooltip) == ("", "")
    r = Rule.from_dict({"button_number": "4", "conditions": [[{}]],
                        "actions": [{}]})
    assert r.button_number == 4 and r.source == "user"
    assert r.conditions == [[ConditionDef("", {})]]
    assert r.actions == [ActionDef("", {})]


def test_standardwerte_der_datenklassen():
    assert ConditionDef("c").params == {} and ActionDef("a").params == {}
    r = Rule("r", "R", True, "t", [], [])
    assert (r.source, r.once_per_song, r.button_number,
            r.button_icon, r.button_tooltip) == ("user", False, 0, "", "")


def test_registry():
    from rule_engine import RuleRegistry
    reg = RuleRegistry()
    reg.add_condition("c", "C")
    reg.add_condition("c2", "C2", {"x": {"type": "int"}})
    reg.add_action("a", "A")
    reg.add_action("a2", "A2", {"y": {}}, group="Audio")
    assert reg.conditions["c"].params_schema == {}
    assert reg.conditions["c2"].params_schema == {"x": {"type": "int"}}
    assert (reg.actions["a"].params_schema, reg.actions["a"].group) == ({}, "")
    assert (reg.actions["a2"].params_schema, reg.actions["a2"].group) == (
        {"y": {}}, "Audio")
    assert reg.conditions["c"].display_name == "C"


# --- Laden / Speichern -------------------------------------------------------

def test_speichern_und_laden(tmp_path, engine):
    engine.add_user_rule(_rule("u1", trigger="key_w"))
    engine.add_user_rule(_rule("u2"))

    eng2 = RuleEngine(str(tmp_path))
    eng2.load()
    try:
        assert [r.id for r in eng2.get_user_rules()] == ["u1", "u2"]
        assert all(r.source == "user" for r in eng2.get_user_rules())
    finally:
        eng2.close()
    data = json.loads((tmp_path / "rules" / "rules_user.json")
                      .read_text(encoding="utf-8"))
    assert data["version"] == 1


def test_datei_bleibt_lesbar(tmp_path, engine):
    engine.add_user_rule(Rule("u1", "Ändern", True, "t", [], []))
    raw = (tmp_path / "rules" / "rules_user.json").read_text(encoding="utf-8")
    assert "Ändern" in raw                    # kein Ä


def test_neue_id_aus_millisekunden(engine, monkeypatch):
    import rule_engine
    monkeypatch.setattr(rule_engine.time, "time", lambda: 1700000000.1234)
    r = _rule("")
    engine.add_user_rule(r)
    assert r.id == "usr_1700000000123"


def test_laden_ohne_dateien(tmp_path, engine):
    engine.load()
    assert engine.get_merged_rules() == []
    assert (tmp_path / "rules").is_dir()


def test_laden_system_vor_user(tmp_path, engine):
    _write(tmp_path / "rules" / "rules_system.json", [_rule("s1")])
    _write(tmp_path / "rules" / "rules_user.json", [_rule("u1")])
    engine.load()
    merged = engine.get_merged_rules()
    assert [(r.id, r.source) for r in merged] == [("s1", "system"), ("u1", "user")]


def test_laden_registriert_fehlende_trigger(tmp_path, engine):
    engine.registry.add_trigger("song_loaded", "Song Loaded")
    _write(tmp_path / "rules" / "rules_user.json",
           [_rule("u1", trigger="key_ab"), _rule("u2", trigger="my_custom"),
            _rule("u3", trigger="song_loaded")])
    engine.load()
    t = engine.registry.triggers
    assert t["key_ab"].display_name == "Key AB"
    assert t["my_custom"].display_name == "My Custom"
    assert t["song_loaded"].display_name == "Song Loaded"   # unveraendert


@pytest.mark.parametrize("kaputt", [
    '{"rules": [{"id": "u1", "name": "Wichtig"',        # abgebrochen
    '',                                                 # leer
    '{"rules": [{"id": "u1"}, "kaputt"]}',              # eine Regel unlesbar
])
def test_kaputte_datei_wird_beiseitegelegt(tmp_path, engine, kaputt):
    p = tmp_path / "rules" / "rules_user.json"
    p.parent.mkdir()
    p.write_text(kaputt, encoding="utf-8")
    engine.load()
    assert engine.get_user_rules() == []
    assert not p.exists()
    gesichert = engine.broken_user_rules_path
    assert gesichert.startswith(str(p) + ".broken-")
    assert open(gesichert, encoding="utf-8").read() == kaputt
    assert "ERROR" in (tmp_path / "logs" / "rules.log").read_text(encoding="utf-8")


def test_kaputte_datei_ueberlebt_naechstes_speichern(tmp_path, engine):
    p = tmp_path / "rules" / "rules_user.json"
    p.parent.mkdir()
    kaputt = '{"rules": [{"id": "u1", "name": "Wichtig"'
    p.write_text(kaputt, encoding="utf-8")
    engine.load()
    engine.add_user_rule(_rule("neu"))
    reste = [f.read_text(encoding="utf-8") for f in p.parent.iterdir()]
    assert kaputt in reste


def test_abgebrochenes_speichern_laesst_datei_heil(tmp_path, engine, monkeypatch):
    p = tmp_path / "rules" / "rules_user.json"
    _write(p, [_rule("u1")])
    vorher = p.read_text(encoding="utf-8")
    engine.load()

    def halb_schreiben(obj, f, **kw):
        f.write('{"rules": [')
        raise OSError("Platte voll")

    monkeypatch.setattr("rule_engine.json.dump", halb_schreiben)
    with pytest.raises(OSError):
        engine.add_user_rule(_rule("neu"))
    assert p.read_text(encoding="utf-8") == vorher
    assert [f.name for f in p.parent.iterdir()] == ["rules_user.json"]


def test_heile_datei_kein_beiseitelegen(tmp_path, engine):
    _write(tmp_path / "rules" / "rules_user.json", [_rule("u1")])
    engine.load()
    assert engine.broken_user_rules_path is None
    assert [f.name for f in (tmp_path / "rules").iterdir()] == ["rules_user.json"]


# --- INI-Overrides der Systemregeln -------------------------------------------

@pytest.mark.parametrize("ini, aktiv", [
    ("true", True), ("1", True), ("yes", True), ("True", True),
    ("false", False), ("0", False), ("nein", False), (False, False)])
def test_override_aktiv(tmp_path, ini, aktiv):
    _write(tmp_path / "rules" / "rules_system.json", [_rule("s1", active=not aktiv)])
    st = FakeSettings({"rules/streamdeck_seeded_v1": True,
                       "rules/sys_s1_active": ini})
    eng = RuleEngine(str(tmp_path), st)
    eng.load()
    try:
        assert eng.get_system_rules()[0].active is aktiv
    finally:
        eng.close()


def test_override_deck_felder(tmp_path):
    _write(tmp_path / "rules" / "rules_system.json", [_rule("s1"), _rule("s2")])
    st = FakeSettings({"rules/streamdeck_seeded_v1": True,
                       "rules/sys_s1_button_number": "7",
                       "rules/sys_s1_button_icon": "x.svg",
                       "rules/sys_s1_button_tooltip": "Tipp",
                       "rules/sys_s2_button_number": "kaputt"})
    eng = RuleEngine(str(tmp_path), st)
    eng.load()
    try:
        s1, s2 = eng.get_system_rules()
        assert (s1.button_number, s1.button_icon, s1.button_tooltip) == (7, "x.svg", "Tipp")
        assert s2.button_number == 0
        assert s1.active is True     # kein Override: Wert aus der JSON bleibt
    finally:
        eng.close()


def test_override_speichern(tmp_path):
    st = FakeSettings({"rules/streamdeck_seeded_v1": True})
    _write(tmp_path / "rules" / "rules_system.json", [_rule("s1")])
    eng = RuleEngine(str(tmp_path), st)
    eng.load()
    try:
        heard = []
        eng.add_rules_changed_listener(lambda: heard.append(1))
        eng.get_system_rules()[0].button_icon = "i.svg"   # Kopie der Liste,
        eng.get_system_rules()[0].button_tooltip = "T"    # gleiche Objekte
        eng.toggle_system_rule("s1", False)
        assert st.values["rules/sys_s1_active"] is False
        assert st.values["rules/sys_s1_button_number"] == 0
        assert st.values["rules/sys_s1_button_icon"] == "i.svg"
        assert st.values["rules/sys_s1_button_tooltip"] == "T"
        assert st.synced and heard == [1]
    finally:
        eng.close()


def test_ohne_settings_kein_override(tmp_path, engine):
    _write(tmp_path / "rules" / "rules_system.json", [_rule("s1")])
    engine.load()
    engine.save_system_overrides()      # darf nicht scheitern
    assert engine.get_system_rules()[0].button_number == 0


# --- Erstbestueckung Stream Deck ---------------------------------------------

def test_erstbestueckung_einmalig(tmp_path):
    sys_rules = [_rule("sys_key_f5_play"), _rule("sys_key_f6_pause",
                                                   button_number=9),
                 _rule("sys_other")]
    _write(tmp_path / "rules" / "rules_system.json", sys_rules)
    st = FakeSettings()
    eng = RuleEngine(str(tmp_path), st)
    eng.load()
    try:
        f5, f6, other = eng.get_system_rules()
        assert (f5.button_number, f5.button_icon) == (1, "play.svg")
        assert f6.button_number == 9            # schon belegt: bleibt
        assert other.button_number == 0
        assert st.values["rules/streamdeck_seeded_v1"] is True
        assert st.values["rules/sys_sys_key_f5_play_button_number"] == 1
    finally:
        eng.close()

    # User nimmt F5 vom Deck; naechster Start bestueckt nicht neu
    st.values["rules/sys_sys_key_f5_play_button_number"] = 0
    eng = RuleEngine(str(tmp_path), st)
    eng.load()
    try:
        assert eng.get_system_rules()[0].button_number == 0
    finally:
        eng.close()


@pytest.mark.parametrize("rid, nummer, icon", [
    ("sys_key_f5_play", 1, "play.svg"),
    ("sys_key_f6_pause", 2, "pause.svg"),
    ("sys_key_f7_stop", 3, "stop.svg"),
    ("sys_key_f8_fade_out", 4, "fade-out.svg"),
    ("sys_key_space_toggle", 5, "play-pause.svg"),
])
def test_erstbestueckung_belegung(tmp_path, rid, nummer, icon):
    _write(tmp_path / "rules" / "rules_system.json", [_rule(rid)])
    eng = RuleEngine(str(tmp_path), FakeSettings())
    eng.load()
    eng.close()
    r = eng.get_system_rules()[0]
    assert (r.button_number, r.button_icon) == (nummer, icon)


def test_erstbestueckung_setzt_flag_auch_ohne_treffer(tmp_path):
    _write(tmp_path / "rules" / "rules_system.json", [_rule("sys_other")])
    st = FakeSettings()
    eng = RuleEngine(str(tmp_path), st)
    eng.load()
    eng.close()
    assert st.values["rules/streamdeck_seeded_v1"] is True
    assert "rules/sys_sys_other_active" not in st.values   # nichts gespeichert


# --- Eigene Regeln verwalten -------------------------------------------------

def test_add_vergibt_id_und_quelle(engine):
    r = _rule("", trigger="key_s")
    r.source = "system"
    engine.add_user_rule(r)
    assert r.id.startswith("usr_") and r.source == "user"
    assert "key_s" in engine.registry.triggers


def test_update_delete_mit_hoerern(engine):
    calls = []
    engine.on_rules_changed = lambda: calls.append("einzel")
    engine.add_rules_changed_listener(lambda: calls.append("liste"))
    engine.add_user_rule(_rule("u1"))
    engine.update_user_rule(_rule("u1", trigger="key_q", actions=("b",)))
    assert engine.get_user_rules()[0].trigger == "key_q"
    assert "key_q" in engine.registry.triggers
    engine.delete_user_rule("u1")
    assert engine.get_user_rules() == []
    assert calls == ["einzel", "liste"] * 3


def test_update_unbekannte_id_aendert_nichts(engine):
    engine.add_user_rule(_rule("u1"))
    engine.update_user_rule(_rule("xx", trigger="key_z"))
    assert [r.id for r in engine.get_user_rules()] == ["u1"]


def test_hoerer_einmalig_und_fehler_isoliert(engine):
    calls = []
    def boom():
        raise RuntimeError("x")
    def ok():
        calls.append(1)
    engine.add_rules_changed_listener(boom)
    engine.add_rules_changed_listener(ok)
    engine.add_rules_changed_listener(ok)
    engine.delete_user_rule("nix")
    assert calls == [1]


def test_umsortieren(tmp_path, engine):
    for i in ("a", "b", "c"):
        engine.add_user_rule(_rule(i))
    engine.reorder_user_rules(["c", "zz", "a"])     # b fehlt, zz unbekannt
    assert [r.id for r in engine.get_user_rules()] == ["c", "a", "b"]
    data = json.loads((tmp_path / "rules" / "rules_user.json")
                      .read_text(encoding="utf-8"))
    assert [r["id"] for r in data["rules"]] == ["c", "a", "b"]


def test_get_listen_sind_kopien(engine):
    engine.add_user_rule(_rule("u1"))
    engine.get_user_rules().clear()
    engine.get_system_rules().append(_rule("x"))
    assert len(engine.get_user_rules()) == 1
    assert engine.get_system_rules() == []


# --- Stream Deck -------------------------------------------------------------

def _deck(engine):
    return [(r.id, r.button_number) for r in engine.get_stream_deck_rules()]


@pytest.fixture
def deck_engine(tmp_path):
    _write(tmp_path / "rules" / "rules_system.json",
           [_rule("s1", button_number=1), _rule("s2", button_number=4)])
    _write(tmp_path / "rules" / "rules_user.json",
           [_rule("u1", button_number=2), _rule("u2"),
            _rule("u3", button_number=3, active=False)])
    st = FakeSettings({"rules/streamdeck_seeded_v1": True})
    eng = RuleEngine(str(tmp_path), st)
    eng.load()
    yield eng, st
    eng.close()


def test_deck_nur_aktive_sortiert(deck_engine):
    eng, _ = deck_engine
    assert _deck(eng) == [("s1", 1), ("u1", 2), ("s2", 4)]


@pytest.mark.parametrize("wunsch, erwartet", [
    (1, ["u2", "s1", "u1", "u3", "s2"]),
    (3, ["s1", "u1", "u2", "u3", "s2"]),
    (5, ["s1", "u1", "u3", "s2", "u2"]),
    (99, ["s1", "u1", "u3", "s2", "u2"]),   # auf N+1 geklemmt
])
def test_deck_einsortieren_lueckenlos(deck_engine, wunsch, erwartet):
    eng, _ = deck_engine
    eng.set_stream_deck_params("u2", wunsch, "i.svg", None)
    alle = sorted((r for r in eng.get_merged_rules() if r.button_number),
                  key=lambda r: r.button_number)
    assert [r.id for r in alle] == erwartet
    assert [r.button_number for r in alle] == [1, 2, 3, 4, 5]
    u2 = eng._find_rule("u2")
    assert (u2.button_icon, u2.button_tooltip) == ("i.svg", "")


@pytest.mark.parametrize("wunsch", [0, -3, None])
def test_deck_entfernen_rueckt_nach(deck_engine, wunsch):
    eng, st = deck_engine
    eng.set_stream_deck_params("u1", wunsch, "", "")
    assert eng._find_rule("u1").button_number == 0
    nums = {r.id: r.button_number for r in eng.get_merged_rules()}
    assert (nums["s1"], nums["u3"], nums["s2"]) == (1, 2, 3)
    assert st.values["rules/sys_s2_button_number"] == 3     # System persistiert


def test_deck_icon_leer(deck_engine):
    eng, _ = deck_engine
    eng.set_stream_deck_params("u1", 2, None, "Tipp")
    u1 = eng._find_rule("u1")
    assert (u1.button_icon, u1.button_tooltip) == ("", "Tipp")


def test_deck_unbekannte_regel(deck_engine):
    eng, _ = deck_engine
    eng.set_stream_deck_params("nix", 1, "", "")
    assert _deck(eng) == [("s1", 1), ("u1", 2), ("s2", 4)]


def test_deck_aenderung_gespeichert(tmp_path, deck_engine):
    eng, _ = deck_engine
    eng.set_stream_deck_params("u2", 1, "", "")
    data = json.loads((tmp_path / "rules" / "rules_user.json")
                      .read_text(encoding="utf-8"))
    assert {r["id"]: r.get("button_number", 0) for r in data["rules"]}["u2"] == 1


# --- Bedingungen -------------------------------------------------------------

def _wired(engine, ctx=None):
    log = []
    engine.register_condition("yes", lambda c, p: True)
    engine.register_condition("no", lambda c, p: False)
    engine.register_condition("param", lambda c, p: c.get("v") == p.get("want"))
    engine.register_action("a", lambda p: log.append(("a", p)))
    engine.register_action("b", lambda p: log.append(("b", p)))
    engine.set_context_provider(lambda: dict(ctx or {}))
    return log


@pytest.mark.parametrize("groups, feuert", [
    ((), True),                           # keine Bedingung: immer
    ((("yes", "yes"),), True),
    ((("yes", "no"),), False),            # UND
    ((("no",), ("yes",)), True),          # ODER
    ((("no",), ("yes", "no")), False),
    ((("unknown",), ("yes",)), True),     # unbekannt macht nur Gruppe falsch
    ((("unknown", "yes"),), False),
])
def test_bedingungen_und_oder(engine, groups, feuert):
    log = _wired(engine)
    engine.add_user_rule(_rule("u1", conditions=groups))
    engine.fire_trigger("t")
    assert bool(log) is feuert


def test_bedingung_bekommt_kontext_und_params(engine):
    log = _wired(engine, {"v": 5})
    r = _rule("u1")
    r.conditions = [[ConditionDef("param", {"want": 5})]]
    engine.add_user_rule(r)
    engine.fire_trigger("t")
    assert log == [("a", {})]


# --- Manuell ausfuehren ------------------------------------------------------

def test_manuell_fuehrt_aus_ohne_trigger(engine):
    log = _wired(engine)
    engine.add_user_rule(_rule("u1", trigger="anders", actions=("a", "b")))
    engine.execute_rule_manual("u1")
    assert [t for t, _ in log] == ["a", "b"]
    assert engine._firing is False


@pytest.mark.parametrize("kw, rid", [
    ({"active": False}, "u1"),
    ({"conditions": (("no",),)}, "u1"),
    ({}, "fehlt"),
])
def test_manuell_tut_nichts(engine, kw, rid):
    log = _wired(engine)
    engine.add_user_rule(_rule("u1", **kw))
    engine.execute_rule_manual(rid)
    assert log == []


def test_manuell_bekommt_kontext(engine):
    log = _wired(engine, {"v": 5})
    r = _rule("u1")
    r.conditions = [[ConditionDef("param", {"want": 5})]]
    engine.add_user_rule(r)
    engine.execute_rule_manual("u1")
    assert log == [("a", {})]


def test_manuell_ohne_context_provider(engine):
    log = []
    engine.register_action("a", lambda p: log.append(p))
    engine.add_user_rule(_rule("u1"))
    engine.execute_rule_manual("u1")
    assert log == [{}]


def test_manuell_schleifenschutz(engine):
    log = _wired(engine)
    engine.add_user_rule(_rule("inner", actions=("b",)))
    engine.register_action("a", lambda p: engine.execute_rule_manual("inner"))
    engine.add_user_rule(_rule("outer", actions=("a",)))
    engine.execute_rule_manual("outer")
    assert log == []
    assert engine._firing is False


def test_manuell_fehler_im_kontext(engine):
    def boom():
        raise RuntimeError("x")
    engine.set_context_provider(boom)
    engine.add_user_rule(_rule("u1"))
    engine.execute_rule_manual("u1")
    assert engine._firing is False


# --- trigger_matches_any_action ----------------------------------------------

def test_matches_any_action(engine):
    log = _wired(engine)
    engine.add_user_rule(_rule("u1", actions=("a", "b")))
    engine.add_user_rule(_rule("u2", trigger="t2", conditions=(("no",),),
                               actions=("x",)))
    assert engine.trigger_matches_any_action("t", {"b"}) is True
    assert engine.trigger_matches_any_action("t", {"x"}) is False
    assert engine.trigger_matches_any_action("t2", {"x"}) is False
    assert log == []                 # nur pruefen, nicht ausfuehren


def test_matches_any_action_gesperrt(engine):
    _wired(engine)
    engine.add_user_rule(_rule("u1"))
    with engine.suspended("x"):
        assert engine.trigger_matches_any_action("t", {"a"}) is False
    assert engine.trigger_matches_any_action("t", {"a"}) is True
    def boom():
        raise RuntimeError("x")
    engine.set_context_provider(boom)
    assert engine.trigger_matches_any_action("t", {"a"}) is False
    engine.set_context_provider(None)
    assert engine.trigger_matches_any_action("t", {"a"}) is False


# --- Suspend -----------------------------------------------------------------

def test_suspended_kontextmanager_auch_bei_fehler(engine):
    with pytest.raises(ValueError):
        with engine.suspended("a") as e:
            assert e is engine and engine.is_suspended
            raise ValueError
    assert not engine.is_suspended


def test_resume_ohne_suspend_ignoriert(engine):
    engine.resume("x")
    assert engine._suspend_count == 0
    engine.suspend()
    engine.suspend("a")
    engine.resume("a")
    assert engine.is_suspended
    engine.resume()
    assert not engine.is_suspended


def test_resume_unbekannter_grund(engine):
    engine.suspend("a")
    engine.resume("b")                  # Grund unbekannt: nur Zaehler sinkt
    assert not engine.is_suspended


@pytest.mark.parametrize("gruende, bypass, feuert", [
    (["x"], (), False),
    ([""], ("",), False),               # ohne Grund nie umgehbar
    (["music"], ("music",), True),
    (["music", "x"], ("music",), False),
    (["music", "x"], ("music", "x"), True),
    (["music", "music"], ("music",), True),
])
def test_suspend_bypass(engine, gruende, bypass, feuert):
    log = _wired(engine)
    engine.add_user_rule(_rule("u1"))
    for g in gruende:
        engine.suspend(g)
    engine.fire_trigger("t", bypass_suspend=bypass)
    assert bool(log) is feuert


def test_resume_gibt_grund_frei(engine):
    log = _wired(engine)
    engine.add_user_rule(_rule("u1"))
    engine.suspend("music")
    engine.resume("music")
    engine.suspend()                    # ohne Grund: blockiert alles
    engine.fire_trigger("t", bypass_suspend=("music",))
    assert log == []


def test_alle_passenden_regeln_feuern(engine):
    log = _wired(engine)
    engine.add_user_rule(_rule("aus", active=False, actions=("b",)))
    engine.add_user_rule(_rule("anders", trigger="t2", actions=("b",)))
    engine.add_user_rule(_rule("einmal", once_per_song=True, actions=("b",)))
    engine.add_user_rule(_rule("ok1", actions=("a",)))
    engine.add_user_rule(_rule("ok2", actions=("a",)))
    engine.fire_trigger("t")            # einmal + ok1 + ok2
    engine.fire_trigger("t")            # ok1 + ok2
    assert [t for t, _ in log] == ["b", "a", "a", "a", "a"]


def test_fire_schleifenschutz(engine):
    log = _wired(engine)
    engine.register_action("a", lambda p: (log.append("a"),
                                           engine.fire_trigger("t")))
    engine.add_user_rule(_rule("u1"))
    engine.fire_trigger("t")
    assert log == ["a"]
    assert engine._firing is False


def test_play_timer_ohne_log_spam(tmp_path, engine):
    _wired(engine)
    engine.fire_trigger("play_timer")
    with engine.suspended("x"):
        engine.fire_trigger("play_timer")
    engine._log("MARK", "-")
    text = (tmp_path / "logs" / "rules.log").read_text(encoding="utf-8")
    assert "play_timer" not in text
    engine.fire_trigger("t")
    with engine.suspended("x"):
        engine.fire_trigger("t2")
    text = (tmp_path / "logs" / "rules.log").read_text(encoding="utf-8")
    assert "NO_MATCH" in text and "'t2' geschluckt" in text


def test_once_per_song_reset(engine):
    log = _wired(engine)
    engine.add_user_rule(_rule("u1", once_per_song=True))
    engine.fire_trigger("t")
    engine.fire_trigger("t")
    assert len(log) == 1
    engine.reset_song_fired()
    engine.fire_trigger("t")
    assert len(log) == 2


def test_aktion_fehler_und_unbekannt_brechen_nicht_ab(engine):
    log = _wired(engine)
    def boom(p):
        raise RuntimeError("x")
    engine.register_action("boom", boom)
    engine.add_user_rule(_rule("u1", actions=("boom", "fehlt", "a")))
    engine.fire_trigger("t")
    assert log == [("a", {})]


def test_fire_ohne_context_provider(engine):
    log = []
    engine.register_action("a", lambda p: log.append(p))
    engine.add_user_rule(_rule("u1"))
    engine.fire_trigger("t")
    assert log == [] and engine._firing is False


# --- Log ---------------------------------------------------------------------

def test_log_rotation(tmp_path, monkeypatch):
    monkeypatch.setattr(RuleEngine, "_LOG_MAX_BYTES", 100)
    monkeypatch.setattr(RuleEngine, "_LOG_KEEP_LINES", 3)
    logs = tmp_path / "logs"
    logs.mkdir()
    (logs / "rules.log").write_text("".join(f"zeile {i}\n" for i in range(50)),
                                    encoding="utf-8")
    eng = RuleEngine(str(tmp_path))
    eng._rotate_log()
    lines = (logs / "rules.log").read_text(encoding="utf-8").splitlines()
    assert lines[0].startswith("[LOG ROTATED")
    assert lines[1:] == ["zeile 47", "zeile 48", "zeile 49"]


def test_log_genau_an_grenze_bleibt(tmp_path, monkeypatch):
    monkeypatch.setattr(RuleEngine, "_LOG_MAX_BYTES", 4)
    logs = tmp_path / "logs"
    logs.mkdir()
    (logs / "rules.log").write_bytes(b"abc\n")          # genau 4 Bytes
    RuleEngine(str(tmp_path))._rotate_log()
    assert (logs / "rules.log").read_bytes() == b"abc\n"


def test_log_in_vorhandenen_ordner(tmp_path, engine):
    (tmp_path / "logs").mkdir()
    engine._log("TEST", "da")
    assert "da" in (tmp_path / "logs" / "rules.log").read_text(encoding="utf-8")


def test_log_schreibt_und_close(tmp_path, engine):
    engine._log("TEST", "hallo")
    engine.close()
    engine.close()                    # zweimal: kein Fehler
    text = (tmp_path / "logs" / "rules.log").read_text(encoding="utf-8")
    assert "TEST" in text and "hallo" in text
