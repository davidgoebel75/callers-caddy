"""
Rule Engine fuer Callers Caddy — V1

Wenn-Dann-Automationen: 1 Trigger → 0-N Bedingungen (AND/OR) → 1-N Aktionen.
First Match Wins, System- und User-Rules getrennt, Loop-Schutz, Logging.
"""

import json
import os
import time
from dataclasses import dataclass, field


# ---------------------------------------------------------------------------
# Datenklassen
# ---------------------------------------------------------------------------

@dataclass
class ActionDef:
    """Eine Aktion innerhalb einer Rule."""
    type: str           # z.B. "dock_open"
    params: dict = field(default_factory=dict)


@dataclass
class ConditionDef:
    """Eine Bedingung innerhalb einer AND-Gruppe."""
    type: str           # z.B. "song_type_is_singing"
    params: dict = field(default_factory=dict)


@dataclass
class Rule:
    """Eine vollstaendige Regel."""
    id: str
    name: str
    active: bool
    trigger: str                           # genau 1 Trigger
    conditions: list  # list[list[ConditionDef]]  — Aussen=OR, Innen=AND
    actions: list     # list[ActionDef]
    source: str = "user"                   # "system" oder "user"
    once_per_song: bool = False            # Nur einmal pro Song feuern
    # --- Stream Deck (BL-168) ---
    button_number: int = 0                 # 0 = nicht im Stream Deck; >0 = Position
    button_icon: str = ""                  # SVG-Dateiname aus images/ (theme-eingefaerbt)
    button_tooltip: str = ""               # Hinweistext; leer = Rule-Name

    def to_dict(self) -> dict:
        d = {
            "id": self.id,
            "name": self.name,
            "active": self.active,
            "trigger": self.trigger,
            "conditions": [
                [{"type": c.type, "params": c.params} for c in group]
                for group in self.conditions
            ],
            "actions": [
                {"type": a.type, "params": a.params} for a in self.actions
            ],
        }
        if self.once_per_song:
            d["once_per_song"] = True
        # Stream-Deck-Felder nur schreiben, wenn die Rule ueberhaupt am Deck teilnimmt
        if self.button_number > 0:
            d["button_number"] = self.button_number
            if self.button_icon:
                d["button_icon"] = self.button_icon
            if self.button_tooltip:
                d["button_tooltip"] = self.button_tooltip
        return d

    @staticmethod
    def from_dict(d: dict, source: str = "user") -> "Rule":
        conditions = []
        for group in d.get("conditions", []):
            and_group = []
            for c in group:
                and_group.append(ConditionDef(
                    type=c.get("type", ""),
                    params=c.get("params", {}),
                ))
            conditions.append(and_group)

        actions = []
        for a in d.get("actions", []):
            actions.append(ActionDef(
                type=a.get("type", ""),
                params=a.get("params", {}),
            ))

        return Rule(
            id=d.get("id", ""),
            name=d.get("name", ""),
            active=d.get("active", True),
            trigger=d.get("trigger", ""),
            conditions=conditions,
            actions=actions,
            source=source,
            once_per_song=d.get("once_per_song", False),
            button_number=int(d.get("button_number", 0) or 0),
            button_icon=d.get("button_icon", ""),
            button_tooltip=d.get("button_tooltip", ""),
        )


# ---------------------------------------------------------------------------
# Registry (Whitelist)
# ---------------------------------------------------------------------------

@dataclass
class TriggerInfo:
    type_str: str
    display_name: str       # Englisch, keine i18n


@dataclass
class ConditionInfo:
    type_str: str
    display_name: str
    params_schema: dict = field(default_factory=dict)


@dataclass
class ActionInfo:
    type_str: str
    display_name: str
    params_schema: dict = field(default_factory=dict)
    group: str = ""
    # params_schema z.B.: {"dock_name": {"type": "dock_choice"}}


class RuleRegistry:
    """Whitelist der erlaubten Trigger, Bedingungen und Aktionen."""

    def __init__(self):
        self.triggers: dict[str, TriggerInfo] = {}
        self.conditions: dict[str, ConditionInfo] = {}
        self.actions: dict[str, ActionInfo] = {}

    def add_trigger(self, type_str: str, display_name: str):
        self.triggers[type_str] = TriggerInfo(type_str, display_name)

    def add_condition(self, type_str: str, display_name: str,
                      params_schema: dict = None):
        self.conditions[type_str] = ConditionInfo(
            type_str, display_name, params_schema or {})

    def add_action(self, type_str: str, display_name: str,
                   params_schema: dict = None, group: str = ""):
        self.actions[type_str] = ActionInfo(
            type_str, display_name, params_schema or {}, group=group)


# ---------------------------------------------------------------------------
# Rule Engine
# ---------------------------------------------------------------------------

class RuleEngine:
    """Laedt, speichert, evaluiert und fuehrt Rules aus."""

    _LOG_MAX_BYTES = 1_000_000   # 1 MB
    _LOG_KEEP_LINES = 500

    def __init__(self, app_dir: str, settings=None):
        self._app_dir = app_dir
        self._settings = settings          # QSettings fuer System-Rule-Overrides
        self._rules_dir = os.path.join(app_dir, "rules")
        # rules.log liegt seit v0.91 in logs/, JSON-Dateien bleiben in rules/
        self._logs_dir = os.path.join(app_dir, "logs")

        self._rules_system: list[Rule] = []
        self._rules_user: list[Rule] = []

        self.registry = RuleRegistry()

        # Evaluatoren und Handler (werden von aussen registriert)
        self._condition_evaluators: dict[str, callable] = {}
        self._action_handlers: dict[str, callable] = {}
        self._context_provider = None      # callable() -> dict

        # Loop-Schutz
        self._firing = False

        # Suspend-Counter: solange > 0 werden Trigger geschluckt.
        # Counter statt Bool, damit verschachtelte suspend()/resume() Paare
        # sich nicht gegenseitig stoeren (z.B. Loop-Finder-Audition innerhalb
        # eines anderen suspended-Blocks).
        self._suspend_count = 0
        self._suspend_reasons: list[str] = []

        # Once-per-Song Tracking
        self._fired_this_song: set = set()

        # Logging
        self._log_file = None

        # Callback fuer Widget-Benachrichtigung.
        # on_rules_changed bleibt fuer Abwaertskompatibilitaet als einzelner
        # Callback bestehen; zusaetzliche Hoerer (z.B. Stream Deck) registrieren
        # sich ueber add_rules_changed_listener().
        self.on_rules_changed = None
        self._rules_changed_listeners: list = []

    # --- Registrierung ---

    def register_condition(self, type_str: str, evaluator):
        """Registriert einen Condition-Evaluator: fn(context) -> bool"""
        self._condition_evaluators[type_str] = evaluator

    def register_action(self, type_str: str, handler):
        """Registriert einen Action-Handler: fn(params: dict) -> None"""
        self._action_handlers[type_str] = handler

    def set_context_provider(self, provider):
        """Provider: fn() -> dict mit aktuellem App-Zustand."""
        self._context_provider = provider

    def add_rules_changed_listener(self, callback):
        """Registriert einen zusaetzlichen Hoerer fuer Rule-Aenderungen."""
        if callback not in self._rules_changed_listeners:
            self._rules_changed_listeners.append(callback)

    def _notify_rules_changed(self):
        """Benachrichtigt alle Hoerer (Einzel-Callback + Listener-Liste)."""
        if self.on_rules_changed:
            self.on_rules_changed()
        for cb in self._rules_changed_listeners:
            try:
                cb()
            except Exception as e:
                self._log("ERROR", f"rules_changed listener: {e}")

    # --- JSON laden / speichern ---

    def load(self):
        """Laedt System- und User-Rules aus JSON-Dateien."""
        os.makedirs(self._rules_dir, exist_ok=True)
        self._rotate_log()

        # System-Rules
        sys_path = os.path.join(self._rules_dir, "rules_system.json")
        self._rules_system = self._load_json(sys_path, source="system")
        self._apply_system_overrides()
        self._seed_streamdeck_defaults()

        # User-Rules
        usr_path = os.path.join(self._rules_dir, "rules_user.json")
        self._rules_user = self._load_json(usr_path, source="user")

        # Dynamische Trigger registrieren (Tasten, die der User selbst erstellt hat)
        self._register_missing_triggers()

        self._log("LOAD", f"System: {len(self._rules_system)} rules, "
                          f"User: {len(self._rules_user)} rules")

    def save_user_rules(self):
        """Speichert User-Rules in JSON."""
        os.makedirs(self._rules_dir, exist_ok=True)
        usr_path = os.path.join(self._rules_dir, "rules_user.json")
        data = {
            "version": 1,
            "rules": [r.to_dict() for r in self._rules_user],
        }
        with open(usr_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def save_system_overrides(self):
        """Speichert Overrides fuer System-Rules in INI (Aktiv + Stream Deck)."""
        if not self._settings:
            return
        for rule in self._rules_system:
            base = f"rules/sys_{rule.id}"
            self._settings.setValue(f"{base}_active", rule.active)
            # Stream-Deck-Overrides (BL-168): auch fuer System-Rules pinbar
            self._settings.setValue(f"{base}_button_number", rule.button_number)
            self._settings.setValue(f"{base}_button_icon", rule.button_icon)
            self._settings.setValue(f"{base}_button_tooltip", rule.button_tooltip)
        self._settings.sync()

    def _load_json(self, path: str, source: str) -> list[Rule]:
        if not os.path.exists(path):
            return []
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            rules = []
            for rd in data.get("rules", []):
                rules.append(Rule.from_dict(rd, source=source))
            return rules
        except Exception as e:
            self._log("ERROR", f"Load {path}: {e}")
            return []

    def _apply_system_overrides(self):
        """Wendet INI-Overrides auf System-Rules an (Aktiv + Stream Deck)."""
        if not self._settings:
            return
        for rule in self._rules_system:
            base = f"rules/sys_{rule.id}"
            val = self._settings.value(f"{base}_active", None)
            if val is not None:
                rule.active = str(val).lower() in ("true", "1", "yes")
            # Stream-Deck-Overrides (BL-168)
            bn = self._settings.value(f"{base}_button_number", None)
            if bn is not None:
                try:
                    rule.button_number = int(bn)
                except (TypeError, ValueError):
                    rule.button_number = 0
            icon = self._settings.value(f"{base}_button_icon", None)
            if icon is not None:
                rule.button_icon = str(icon)
            tip = self._settings.value(f"{base}_button_tooltip", None)
            if tip is not None:
                rule.button_tooltip = str(tip)

    # Erstbestueckung des Stream Decks: die immer vorhandenen Shortcut-System-
    # Rules (F5-F8, Space) bekommen Position + Icon. Reihenfolge = Buttonnummer.
    _STREAMDECK_SEED = {
        "sys_key_f5_play":      (1, "play.svg"),
        "sys_key_f6_pause":     (2, "pause.svg"),
        "sys_key_f7_stop":      (3, "stop.svg"),
        "sys_key_f8_fade_out":  (4, "fade-out.svg"),
        "sys_key_space_toggle": (5, "play-pause.svg"),
    }

    def _seed_streamdeck_defaults(self):
        """Einmalig pro Installation: legt die Standard-Shortcut-Rules aufs Deck.

        Laeuft genau einmal (Flag in INI). So bekommen auch Bestandsinstallationen
        die Erstbestueckung, ohne dass ein spaeteres Entfernen durch den User beim
        naechsten Start wieder ueberschrieben wird.
        """
        if not self._settings:
            return
        if self._settings.value("rules/streamdeck_seeded_v1", False, type=bool):
            return
        changed = False
        for rule in self._rules_system:
            seed = self._STREAMDECK_SEED.get(rule.id)
            if seed and rule.button_number == 0:
                rule.button_number, rule.button_icon = seed
                changed = True
        if changed:
            self.save_system_overrides()
            self._log("SEED", "Stream Deck mit Standard-Shortcuts bestueckt")
        self._settings.setValue("rules/streamdeck_seeded_v1", True)
        self._settings.sync()

    def _register_missing_triggers(self):
        """Registriert Trigger, die in Rules vorkommen, aber nicht in der Registry sind.

        Dies ermöglicht es, dass dynamisch erstellte Trigger (key_w, etc.) persistent sind:
        1. User erstellt einen neuen Trigger key_w
        2. User erstellt eine Rule mit diesem Trigger
        3. Rule wird in rules_user.json gespeichert
        4. Beim nächsten App-Start: Diese Methode registriert key_w automatisch
        """
        used_triggers = set()
        for rule in self._rules_system + self._rules_user:
            used_triggers.add(rule.trigger)

        # Für jeden Trigger, der nicht in der Registry ist → registrieren
        for trigger_name in used_triggers:
            if trigger_name not in self.registry.triggers:
                # Trigger ist "key_*" oder ein anderer benutzerdef. Trigger
                # Generiere einen anständigen Display-Namen
                if trigger_name.startswith("key_"):
                    # key_w → "Key W", key_f5 → "Key F5"
                    rest = trigger_name[4:].upper()  # "W" oder "F5"
                    display_name = f"Key {rest}"
                else:
                    # Andere benutzerdefinierte Trigger
                    display_name = trigger_name.replace("_", " ").title()

                self.registry.add_trigger(trigger_name, display_name)
                self._log("TRIGGER", f"Auto-registered missing trigger: {trigger_name}")

    # --- Rules verwalten ---

    def get_merged_rules(self) -> list[Rule]:
        """Alle Rules in Prioritaetsreihenfolge (System zuerst, dann User)."""
        return self._rules_system + self._rules_user

    def get_system_rules(self) -> list[Rule]:
        return list(self._rules_system)

    def get_user_rules(self) -> list[Rule]:
        return list(self._rules_user)

    def add_user_rule(self, rule: Rule):
        rule.source = "user"
        if not rule.id:
            rule.id = f"usr_{int(time.time() * 1000)}"
        self._rules_user.append(rule)
        # Neuen Trigger sofort registrieren, sonst feuert eine frisch angelegte
        # Tasten-Regel (z.B. key_s) erst nach App-Neustart (der eventFilter prueft
        # trigger_name in registry.triggers). Methode ist idempotent.
        self._register_missing_triggers()
        self.save_user_rules()
        self._notify_rules_changed()

    def update_user_rule(self, rule: Rule):
        """Aktualisiert eine bestehende User-Rule (nach ID)."""
        for i, r in enumerate(self._rules_user):
            if r.id == rule.id:
                self._rules_user[i] = rule
                break
        # Geaenderten Trigger sofort registrieren (analog add_user_rule).
        self._register_missing_triggers()
        self.save_user_rules()
        self._notify_rules_changed()

    def delete_user_rule(self, rule_id: str):
        self._rules_user = [r for r in self._rules_user if r.id != rule_id]
        self.save_user_rules()
        self._notify_rules_changed()

    def reorder_user_rules(self, rule_ids: list[str]):
        """Setzt die Reihenfolge der User-Rules nach ID-Liste."""
        id_map = {r.id: r for r in self._rules_user}
        reordered = [id_map[rid] for rid in rule_ids if rid in id_map]
        # Sicherheit: Falls IDs fehlen, ans Ende anfuegen
        seen = set(rule_ids)
        for r in self._rules_user:
            if r.id not in seen:
                reordered.append(r)
        self._rules_user = reordered
        self.save_user_rules()

    def toggle_system_rule(self, rule_id: str, active: bool):
        """Aktiviert/deaktiviert eine System-Rule (Override in INI)."""
        for r in self._rules_system:
            if r.id == rule_id:
                r.active = active
                break
        self.save_system_overrides()
        # Deaktivieren/Aktivieren muss das Stream Deck live neu aufbauen
        # (Button erscheint/verschwindet), daher Hoerer benachrichtigen.
        self._notify_rules_changed()

    # --- Stream Deck (BL-168) ---

    def _find_rule(self, rule_id: str):
        """Liefert das Rule-Objekt (System oder User) oder None."""
        for r in self.get_merged_rules():
            if r.id == rule_id:
                return r
        return None

    def get_stream_deck_rules(self) -> list[Rule]:
        """Aktive Rules mit button_number > 0, aufsteigend nach Nummer sortiert.

        Inaktive Rules (active=False) erscheinen NICHT im Stream Deck — analog
        zum automatischen Trigger-Pfad (_iter_matching_rules), der sie ebenfalls
        ueberspringt.
        """
        deck = [r for r in self.get_merged_rules()
                if r.button_number > 0 and r.active]
        deck.sort(key=lambda r: r.button_number)
        return deck

    def _renumber_deck_compact(self, target: Rule, desired: int):
        """Vergibt LUeckENLOS zusammenhaengende Nummern 1..N an alle Deck-Rules.

        Pragmatisch (BL-168): es gibt immer genau so viele verschiedene Nummern
        wie Deck-Buttons. `target` wird an Position `desired` einsortiert
        (1-basiert, auf 1..N+1 geklemmt); desired <= 0 entfernt target vom Deck.
        Danach bekommen alle Deck-Rules der Reihe nach 1..N — keine Luecken.
        """
        others = sorted(
            (r for r in self.get_merged_rules()
             if r is not target and r.button_number > 0),
            key=lambda r: r.button_number,
        )
        if desired <= 0:
            target.button_number = 0
            for i, r in enumerate(others, start=1):
                r.button_number = i
            return
        pos = max(1, min(int(desired), len(others) + 1))
        ordered = others[:pos - 1] + [target] + others[pos - 1:]
        for i, r in enumerate(ordered, start=1):
            r.button_number = i

    def set_stream_deck_params(self, rule_id: str, button_number: int,
                               button_icon: str, button_tooltip: str):
        """Setzt die Stream-Deck-Parameter einer Rule (System oder User).

        Die Buttonnummer wird als gewuenschte Position interpretiert; danach
        werden ALLE Deck-Rules lueckenlos auf 1..N neu nummeriert. User-Rules und
        System-Overrides werden persistiert und alle Hoerer benachrichtigt.
        """
        rule = self._find_rule(rule_id)
        if rule is None:
            self._log("ERROR", f"set_stream_deck_params: rule '{rule_id}' not found")
            return
        rule.button_icon = button_icon or ""
        rule.button_tooltip = button_tooltip or ""
        self._renumber_deck_compact(rule, max(0, int(button_number or 0)))
        # Neunummerierung kann System- und User-Rules betreffen — beide schreiben
        self.save_user_rules()
        self.save_system_overrides()
        self._notify_rules_changed()

    def execute_rule_manual(self, rule_id: str):
        """Fuehrt die Actions einer Rule per manuellem Klick (Stream Deck) aus.

        Trigger wird uebersprungen, Conditions werden JEDOCH ausgewertet — sind
        sie nicht erfuellt, passiert still nichts (nur Log-Eintrag).
        """
        if self._firing:
            self._log("BLOCKED", f"Manual exec '{rule_id}' blocked (loop protection)")
            return
        rule = self._find_rule(rule_id)
        if rule is None:
            self._log("ERROR", f"execute_rule_manual: rule '{rule_id}' not found")
            return
        if not rule.active:
            self._log("SKIPPED", f"Manual '{rule.name}': rule inactive")
            return
        self._firing = True
        try:
            context = self._context_provider() if self._context_provider else {}
            if self._evaluate_conditions(rule.conditions, context):
                self._log("MANUAL", f"Rule '{rule.name}' [{rule.id}]")
                self._execute_actions(rule.actions, rule.name)
            else:
                self._log("SKIPPED",
                          f"Manual '{rule.name}': conditions not met")
        except Exception as e:
            self._log("ERROR", f"execute_rule_manual('{rule_id}'): {e}")
        finally:
            self._firing = False

    # --- Once-per-Song ---

    def reset_song_fired(self):
        """Setzt das Once-per-Song Tracking zurueck (bei neuem Song)."""
        self._fired_this_song.clear()

    # --- Trigger auswerten (Kernlogik) ---

    # --- Suspend / Resume ---------------------------------------------------
    # Erlaubt es, fuer abgegrenzte Aktionen (Loop-Finder-Audition, Beat-Snap-
    # Vorhoeren etc.) saemtliche Rules temporaer auszuschalten — ohne dass
    # einzelne Aktionen aus dem Code heraus geprueft werden muessen, ob sie
    # gerade laufen duerfen. Zentral, wiederverwendbar.

    def suspend(self, reason: str = ""):
        """Trigger-Verarbeitung vorruebergehend aussetzen. Aufrufe sind
        verschachtelbar — jedem suspend() muss ein resume() folgen.
        """
        self._suspend_count += 1
        if reason:
            self._suspend_reasons.append(reason)
        self._log("SUSPEND",
                  f"depth={self._suspend_count} reason={reason or '-'}")

    def resume(self, reason: str = ""):
        """Suspend zuruecknehmen. Wenn der Counter auf 0 faellt, feuern
        Trigger wieder normal.
        """
        if self._suspend_count <= 0:
            self._log("WARN", "resume() ohne aktiven suspend() ignoriert")
            return
        self._suspend_count -= 1
        if reason and reason in self._suspend_reasons:
            self._suspend_reasons.remove(reason)
        self._log("RESUME",
                  f"depth={self._suspend_count} reason={reason or '-'}")

    @property
    def is_suspended(self) -> bool:
        return self._suspend_count > 0

    def suspended(self, reason: str = ""):
        """Kontext-Manager fuer `with engine.suspended('loop_finder'): ...`.

        Bricht selbst bei Exceptions sauber ab. Bevorzugte Form fuer
        synchrone Bloecke; bei lang laufenden asynchronen Aktionen
        (z.B. Audition mit User-Stop) stattdessen explizit suspend/resume.
        """
        engine = self
        class _Cm:
            def __enter__(self_inner):
                engine.suspend(reason)
                return engine
            def __exit__(self_inner, exc_type, exc, tb):
                engine.resume(reason)
                return False
        return _Cm()

    # ------------------------------------------------------------------------

    def fire_trigger(self, trigger: str):
        """Haupteinstieg: Evaluiert Rules fuer diesen Trigger.
        All Match — alle passenden Rules werden ausgefuehrt.
        """
        # Suspend hat Vorrang vor Loop-Schutz — Trigger werden komplett
        # ignoriert (kein BLOCKED-Log fuer jede einzelne Aktion).
        if self._suspend_count > 0:
            # play_timer ist haeufig (alle 100ms), nicht in jedem Tick loggen.
            if trigger != "play_timer":
                self._log("SUSPENDED",
                          f"trigger '{trigger}' geschluckt "
                          f"(depth={self._suspend_count})")
            return

        # Loop-Schutz
        if self._firing:
            self._log("BLOCKED",
                      f"Re-entrant trigger '{trigger}' blocked (loop protection)")
            return

        self._firing = True
        try:
            # play_timer ist haeufig — nur loggen wenn es Matches gibt
            log_trigger = trigger != "play_timer"
            if log_trigger:
                self._log("TRIGGER", trigger)

            if not self._context_provider:
                self._log("ERROR", "No context provider registered")
                return

            context = self._context_provider()
            matched = False

            for rule in self._iter_matching_rules(trigger, context):
                self._log("MATCH", f"Rule '{rule.name}' [{rule.id}]")
                self._execute_actions(rule.actions, rule.name)
                matched = True
                if rule.once_per_song:
                    self._fired_this_song.add(rule.id)

            if not matched and log_trigger:
                self._log("NO_MATCH", f"No rule matched trigger '{trigger}'")

        except Exception as e:
            self._log("ERROR", f"fire_trigger('{trigger}'): {e}")
        finally:
            self._firing = False

    def _iter_matching_rules(self, trigger: str, context: dict):
        """Liefert alle Rules, die fuer diesen Trigger JETZT feuern wuerden
        (aktiv, Trigger passt, once_per_song beachtet, Bedingungen erfuellt).

        EINZIGE Quelle der Match-Logik — genutzt von fire_trigger UND
        trigger_matches_any_action, damit der Play-Gate exakt dieselben Rules
        sieht, die auch tatsaechlich feuern (kein zweiter Pfad).
        """
        for rule in self.get_merged_rules():
            if not rule.active:
                continue
            if rule.trigger != trigger:
                continue
            # Once-per-Song: bereits gefeuerte Rules ueberspringen
            if rule.once_per_song and rule.id in self._fired_this_song:
                continue
            if self._evaluate_conditions(rule.conditions, context):
                yield rule

    def trigger_matches_any_action(self, trigger: str, action_types: set) -> bool:
        """True, wenn eine feuerbereite Rule dieses Triggers mindestens eine
        Aktion aus action_types enthaelt.

        Fuer den Play-Gate (PlayBarrier): entscheidet, ob der hoerbare
        Audio-Start auf Layout-/Loop-Aktionen warten muss. Wertet Bedingungen
        aus, fuehrt aber KEINE Aktionen aus und veraendert keinen Zustand.
        """
        if self._suspend_count > 0:
            return False
        if not self._context_provider:
            return False
        try:
            context = self._context_provider()
        except Exception:
            return False
        for rule in self._iter_matching_rules(trigger, context):
            for action in rule.actions:
                if action.type in action_types:
                    return True
        return False

    def _evaluate_conditions(self, condition_groups, context: dict) -> bool:
        """AND innerhalb einer Gruppe, OR zwischen Gruppen.
        Leere Bedingungsliste = immer wahr.
        """
        if not condition_groups:
            return True

        # OR: mindestens eine Gruppe muss matchen
        for group in condition_groups:
            if self._evaluate_and_group(group, context):
                return True
        return False

    def _evaluate_and_group(self, group, context: dict) -> bool:
        """Alle Bedingungen in der Gruppe muessen wahr sein (AND)."""
        for cond in group:
            evaluator = self._condition_evaluators.get(cond.type)
            if evaluator is None:
                self._log("ERROR", f"Unknown condition: '{cond.type}'")
                return False
            if not evaluator(context, cond.params):
                return False
        return True

    def _execute_actions(self, actions, rule_name: str):
        """Fuehrt Aktionen sequentiell aus."""
        for action in actions:
            handler = self._action_handlers.get(action.type)
            if handler is None:
                self._log("ERROR",
                          f"Unknown action '{action.type}' in rule '{rule_name}'")
                continue
            try:
                _t0 = time.perf_counter()
                handler(action.params)
                _ms = (time.perf_counter() - _t0) * 1000
                self._log("ACTION",
                          f"{action.type}({action.params}) [{_ms:.1f}ms] [rule: {rule_name}]")
            except Exception as e:
                self._log("ERROR",
                          f"Action '{action.type}' failed: {e} [rule: {rule_name}]")

    # --- Logging ---

    def _log(self, category: str, message: str):
        """Schreibt eine Zeile ins rules.log."""
        try:
            if self._log_file is None:
                os.makedirs(self._logs_dir, exist_ok=True)
                log_path = os.path.join(self._logs_dir, "rules.log")
                self._log_file = open(log_path, "a", encoding="utf-8")

            ts = time.strftime("%Y-%m-%d %H:%M:%S")
            line = f"[{ts}] {category:10s} {message}\n"
            self._log_file.write(line)
            self._log_file.flush()
        except Exception:
            pass  # Logging darf nie die App crashen

    def _rotate_log(self):
        """Kuerzt das Log wenn es zu gross wird."""
        log_path = os.path.join(self._logs_dir, "rules.log")
        try:
            if not os.path.exists(log_path):
                return
            size = os.path.getsize(log_path)
            if size <= self._LOG_MAX_BYTES:
                return
            with open(log_path, "r", encoding="utf-8") as f:
                lines = f.readlines()
            keep = lines[-self._LOG_KEEP_LINES:]
            with open(log_path, "w", encoding="utf-8") as f:
                f.write(f"[LOG ROTATED — kept last {len(keep)} lines]\n")
                f.writelines(keep)
        except Exception:
            pass

    def close(self):
        """Log-Datei schliessen (bei App-Ende)."""
        if self._log_file:
            try:
                self._log_file.close()
            except Exception:
                pass
            self._log_file = None
