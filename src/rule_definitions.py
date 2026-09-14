"""
Rule Definitions V1 — Whitelist der erlaubten Trigger, Bedingungen und Aktionen.

Alle Namen bleiben Englisch (keine i18n). Zielgruppe: Fortgeschrittene User.
"""

from rule_engine import RuleEngine


def register_v1_definitions(engine: RuleEngine):
    """Registriert alle V1-Trigger, Bedingungen und Aktionen in der Registry."""

    reg = engine.registry

    # --- Trigger ---
    # Manuell-only: feuert NICHT automatisch. Solche Rules werden ausschliesslich
    # ueber das Virtual Stream Deck (oder manuellen Aufruf) ausgeloest — die App
    # ruft fire_trigger("manual") bewusst NIE auf. Steht bewusst ganz oben, damit
    # er im Trigger-Dropdown leicht zu finden ist.
    reg.add_trigger("manual",            "Virtual Stream Deck (manual only)")
    reg.add_trigger("song_started",      "Song Started")
    reg.add_trigger("song_stopped",      "Song Stopped")
    reg.add_trigger("song_paused",       "Song Paused")
    reg.add_trigger("song_resumed",      "Song Resumed")
    reg.add_trigger("song_changed",      "Song Changed")
    reg.add_trigger("app_started",       "App Started")
    reg.add_trigger("manager_closed",    "Playlist Manager Closed")
    reg.add_trigger("play_timer",       "Play Timer (periodic)")
    # Keyboard-Trigger
    reg.add_trigger("key_f1",            "Key F1")
    reg.add_trigger("key_f2",            "Key F2")
    reg.add_trigger("key_f3",            "Key F3")
    reg.add_trigger("key_f4",            "Key F4")
    reg.add_trigger("key_f5",            "Key F5")
    reg.add_trigger("key_f6",            "Key F6")
    reg.add_trigger("key_f7",            "Key F7")
    reg.add_trigger("key_f8",            "Key F8")
    reg.add_trigger("key_f9",            "Key F9")
    reg.add_trigger("key_f10",           "Key F10")
    reg.add_trigger("key_f11",           "Key F11")
    reg.add_trigger("key_f12",           "Key F12")
    reg.add_trigger("key_f13",           "Key F13")
    reg.add_trigger("key_f14",           "Key F14")
    reg.add_trigger("key_f15",           "Key F15")
    reg.add_trigger("key_f16",           "Key F16")
    reg.add_trigger("key_f17",           "Key F17")
    reg.add_trigger("key_f18",           "Key F18")
    reg.add_trigger("key_f19",           "Key F19")
    reg.add_trigger("key_f20",           "Key F20")
    reg.add_trigger("key_f21",           "Key F21")
    reg.add_trigger("key_f22",           "Key F22")
    reg.add_trigger("key_f23",           "Key F23")
    reg.add_trigger("key_f24",           "Key F24")
    reg.add_trigger("key_space",         "Key Space")
    reg.add_trigger("key_l",             "Key L")
    reg.add_trigger("key_p",             "Key P")
    # Media-/Fn-Tasten
    reg.add_trigger("key_volume_up",      "Key Volume+")
    reg.add_trigger("key_volume_down",    "Key Volume−")
    reg.add_trigger("key_volume_mute",    "Key Mute")
    reg.add_trigger("key_media_play",     "Key Media Play/Pause")
    reg.add_trigger("key_media_stop",     "Key Media Stop")
    reg.add_trigger("key_media_next",     "Key Media Next")
    reg.add_trigger("key_media_prev",     "Key Media Previous")
    reg.add_trigger("key_brightness_up",  "Key Brightness+")
    reg.add_trigger("key_brightness_down","Key Brightness−")

    # --- Bedingungen ---
    reg.add_condition("song_type_is_singing",  "Song Type = Singing Call")
    reg.add_condition("song_type_is_patter",   "Song Type = Patter")
    reg.add_condition("lyrics_available",       "Lyrics Available")
    reg.add_condition("lyrics_not_available",   "Lyrics Not Available")
    reg.add_condition("loop_set",               "Loop Set")
    reg.add_condition("loop_not_set",           "Loop Not Set")
    reg.add_condition("bpm_set",                "BPM Set")
    reg.add_condition("bpm_not_set",            "BPM Not Set")
    reg.add_condition("location_selected",      "Location Selected")
    reg.add_condition("location_not_selected",  "No Location Selected")
    reg.add_condition("play_duration_above",    "Play Duration Above (min)",
                      {"minutes": {"type": "float", "default": 5,
                                   "min": 0.5, "max": 60}})
    # BL-205: Gesamtlaenge des Songs gegen Schwellwert (mm:ss) vergleichen.
    # Operator und Wert bleiben englisch (Rules-interne Namen, i18n-Ausnahme).
    reg.add_condition("song_length",            "Song Length",
                      {"operator": {"type": "choice",
                                    "choices": ["above", "below"],
                                    "default": "above"},
                       "value": {"type": "mmss", "default": "3:00"}})

    # --- Aktionen ---

    # Transport
    reg.add_action("play",              "Play",               {}, group="Transport")
    reg.add_action("pause",             "Pause",              {}, group="Transport")
    reg.add_action("stop",              "Stop",               {}, group="Transport")
    reg.add_action("fade_out",          "Fade Out",           {}, group="Transport")
    reg.add_action("play_pause_toggle", "Play/Pause Toggle",  {}, group="Transport")
    reg.add_action("goto_position", "Go To Position",
                   {"position": {"type": "choice",
                                 "choices": ["start", "loop_in", "loop_out", "end"],
                                 "default": "start"}}, group="Transport")
    # Relative Verschiebung ab der aktuellen Position (mm:ss.cs, +/-).
    # Nutzen: per Button 'nochmal Zeit fuers Beenden' des Liedes gewinnen.
    reg.add_action("shift_position", "Shift Position (relative ±)",
                   {"offset": {"type": "time_offset", "default": "-0:20"}},
                   group="Transport")
    # Custom-Jump-Marker an der aktuellen Abspielposition setzen. Feuert nur bei
    # laufender Wiedergabe; Caption = aktuelle Position als mm:ss. Nah-Duplikate
    # (<1 s zu einem bestehenden Marker) werden uebersprungen.
    reg.add_action("create_jump_marker", "Create Jump Marker",
                   {}, group="Transport")
    # BL-177: Pause direkt starten (mit Pausendauer als Parameter).
    # minutes = 0 -> Standard-Pausendauer der aktuellen Lokation.
    reg.add_action("start_break", "Start Break",
                   {"minutes": {"type": "float", "default": 5,
                                "min": 0, "max": 60, "step": 0.5}},
                   group="Transport")
    reg.add_action("start_break_last_song", "Start Break with last Song",
                   {"minutes": {"type": "float", "default": 5,
                                "min": 0, "max": 60, "step": 0.5}},
                   group="Transport")

    # Audio
    reg.add_action("tempo_change", "Change Today's Tempo (±%)",
                   {"delta": {"type": "int", "default": 2, "min": -50, "max": 50}},
                   group="Audio")
    reg.add_action("song_tempo_change", "Change Song Tempo (±%, persistent)",
                   {"delta": {"type": "int", "default": 2, "min": -50, "max": 50}},
                   group="Audio")
    reg.add_action("pitch_change", "Change Pitch (±Semitones)",
                   {"delta": {"type": "float", "default": 0.5, "min": -6.0, "max": 6.0, "step": 0.5}},
                   group="Audio")
    reg.add_action("volume_change", "Change Volume (±)",
                   {"delta": {"type": "float", "default": -0.05, "min": -1.0, "max": 1.0, "step": 0.05}},
                   group="Audio")
    reg.add_action("live_volume_change", "Change Live-Volume (±)",
                   {"delta": {"type": "int", "default": -10, "min": -100, "max": 100}},
                   group="Audio")
    reg.add_action("live_volume_set", "Set Live-Volume (absolute %)",
                   {"value": {"type": "int", "default": 100, "min": 0, "max": 100}},
                   group="Audio")
    reg.add_action("auto_set_best_loop", "Auto-Set Best Loop",
                   {"preset": {"type": "preset_choice", "default": "Singing"}},
                   group="Audio")
    reg.add_action("auto_detect_bpm",    "Auto-Detect BPM",    {}, group="Audio")
    reg.add_action("toggle_loop_active", "Toggle Loop Active", {}, group="Audio")

    # Layout & Docks
    reg.add_action("dock_open",  "Open Widget",     {"dock_name": {"type": "dock_choice"},
                   "open_position": {"type": "choice", "choices": ["centered", "last"],
                                     "default": "centered"}}, group="Layout & Docks")
    reg.add_action("dock_close", "Close Widget",    {"dock_name": {"type": "dock_choice"}}, group="Layout & Docks")
    reg.add_action("dock_focus", "Focus Widget",    {"dock_name": {"type": "dock_choice"}}, group="Layout & Docks")
    # BL-176: wie Focus Widget, aber setzt zusaetzlich den Mauszeiger in die Mitte
    # des Widgets (z.B. Lyrics — sofort weiterscrollen ohne Maus-Reise).
    reg.add_action("dock_focus_cursor", "Focus Widget + Cursor", {"dock_name": {"type": "dock_choice"}}, group="Layout & Docks")
    reg.add_action("dock_fullsize", "Fullsize Widget", {"dock_name": {"type": "dock_choice"}}, group="Layout & Docks")
    reg.add_action("dock_custom_size", "Custom Size Widget",
                   {"dock_name": {"type": "dock_choice"},
                    "width_pct":  {"type": "int", "default": 90, "min": 5, "max": 100},
                    "height_pct": {"type": "int", "default": 90, "min": 5, "max": 100},
                    "x_pct":      {"type": "int", "default": 50, "min": 0, "max": 100},
                    "y_pct":      {"type": "int", "default": 50, "min": 0, "max": 100}},
                   group="Layout & Docks")
    reg.add_action("layout_load", "Load Layout",
                   {"layout_name": {"type": "layout_choice"}}, group="Layout & Docks")
    reg.add_action("dual_view", "Dual-View (two widgets side by side)",
                   {"dock_left":  {"type": "dock_choice"},
                    "dock_right": {"type": "dock_choice"},
                    "split":      {"type": "choice",
                                   "choices": ["50:50", "33:67", "67:33"],
                                   "default": "50:50"}}, group="Layout & Docks")
    reg.add_action("dual_view_toggle", "Toggle Dual-View (open/restore)",
                   {"dock_left":  {"type": "dock_choice"},
                    "dock_right": {"type": "dock_choice"},
                    "split":      {"type": "choice",
                                   "choices": ["50:50", "33:67", "67:33"],
                                   "default": "50:50"}}, group="Layout & Docks")
    reg.add_action("dual_view_close", "Close Dual-View", {}, group="Layout & Docks")
    reg.add_action("break_toggle", "Toggle Break-Timer (open/close)", {}, group="Layout & Docks")

    # Lyrics & Scroll
    reg.add_action("auto_scroll_start", "Start Auto-Scroll",   {}, group="Lyrics & Scroll")
    reg.add_action("auto_scroll_stop",  "Stop Auto-Scroll",    {}, group="Lyrics & Scroll")
    reg.add_action("lyrics_auto_width", "Lyrics Auto-Width",   {}, group="Lyrics & Scroll")

    # Sequence View
    reg.add_action("sequenceview_open",     "Open Detail View",       {}, group="Sequence View")
    reg.add_action("sequenceview_close",    "Close Detail View",      {}, group="Sequence View")
    reg.add_action("sequenceview_focus",    "Focus (bring to front)", {}, group="Sequence View")
    reg.add_action("sequenceview_maximize", "Maximize (90% screen)",  {}, group="Sequence View")
    reg.add_action("sequenceview_prev",     "Previous Sequence",      {}, group="Sequence View")
    reg.add_action("sequenceview_next",     "Next Sequence",          {}, group="Sequence View")
    # BL-182: Zufallssprung zu einer beliebigen passenden Sequenz (analog "Next",
    # aber immer zufaellig — per Regel/Fernbedienung ausloesbar).
    reg.add_action("sequenceview_random",   "Random Sequence",        {}, group="Sequence View")
    # BL-181 A: Sequenz-Type-Filter umschalten (z.B. Singing-Figures vs. Patter-Module/Get-Outs)
    reg.add_action("sequence_set_type", "Set Sequence Type",
                   {"seq_type": {"type": "seqtype_choice"}}, group="Sequence View")

    # Sequence Filter — Filter des Sequenzen-Widgets per Regel setzen.
    # BL-192: aktives Tanzprogramm setzen (Mehrfachauswahl).
    reg.add_action("set_dance_program", "Set Dance Program(s)",
                   {"program_ids": {"type": "program_multichoice", "default": ""}},
                   group="Sequence Filter")
    # BL-193: Contains-Filter (bestimmter Call). Leer = kein Filter.
    reg.add_action("seqfilter_contains", "Set Sequence-Filter: Contains",
                   {"call": {"type": "call_choice", "default": ""}},
                   group="Sequence Filter")
    # BL-194: Limit-Filter (hoechster Call / Programm-Grenze). Leer = kein Filter.
    reg.add_action("seqfilter_limit", "Set Sequence-Filter: Limit",
                   {"call": {"type": "call_choice", "default": ""}},
                   group="Sequence Filter")
    # BL-195: "Only"-Filter (hoechster Call muss im Programm des Limits liegen).
    reg.add_action("seqfilter_only", "Set Sequence-Filter: Only",
                   {"state": {"type": "choice", "choices": ["On", "Off"],
                              "default": "On"}},
                   group="Sequence Filter")
    # BL-196: Difficulty-Filter. Leer = kein Filter.
    reg.add_action("seqfilter_difficulty", "Set Sequence-Filter: Difficulty",
                   {"difficulty": {"type": "difficulty_choice", "default": ""}},
                   group="Sequence Filter")
    # BL-197: Tags-Filter (aus BL-191). Leer = kein Filter.
    reg.add_action("seqfilter_tags", "Set Sequence-Filter: Tags",
                   {"tag": {"type": "tags_choice", "default": ""}},
                   group="Sequence Filter")

    # BL-181 B: Song nach Typ + Sortierung auswaehlen und in den Player laden (cue, kein Autoplay).
    # "Recommendation" liefert deterministisch immer den besten Song; die
    # Zufalls-Sortierungen ("Random", "Weighted Random") ziehen bei jedem
    # Auslösen neu und liefern daher wechselnde Songs.
    reg.add_action("load_song", "Load Song",
                   {"type": {"type": "choice",
                             "choices": ["Singing", "Patter"],
                             "default": "Singing"},
                    "sort": {"type": "choice",
                             "choices": ["Recommendation", "Weighted Random (Balanced Roulette)",
                                         "Random", "Quality", "Last Played",
                                         "Alphabetical", "Date Added"],
                             "default": "Recommendation"}},
                   group="Transport")

    # Notes
    reg.add_action("notes_tick_top", "Tick Top Open Note", {}, group="Notes")

    # Workflow
    reg.add_action("auto_advance",        "Auto-Advance (Next Playlist Song)", {}, group="Workflow")
    reg.add_action("open_location_dialog","Open Location Dialog",              {}, group="Workflow")
    reg.add_action("toggle_manager",      "Toggle Playlist Manager",           {}, group="Workflow")

    # Photo
    reg.add_action("photo_capture", "Photo Capture",    {}, group="Photo")
    reg.add_action("photo_show",    "Photo Show (90%)", {}, group="Photo")

    # Genre
    reg.add_action("genre_add",    "Add Genre to Song",
                   {"genre_name": {"type": "genre_choice"}}, group="Genre")
    reg.add_action("genre_remove", "Remove Genre from Song",
                   {"genre_name": {"type": "genre_choice"}}, group="Genre")

    # Info & Warnings
    reg.add_action("log_message", "Log Message",
                   {"message": {"type": "text"}}, group="Info & Warnings")
    reg.add_action("statusbar_message", "Statusbar Message",
                   {"message": {"type": "text"},
                    "duration_ms": {"type": "int", "default": 3000}},
                   group="Info & Warnings")
    # BL-137: Sound abspielen — mischt eine Audiodatei in den laufenden Stream
    reg.add_action("play_sound", "Play Sound",
                   {"path":   {"type": "file",
                               "file_filter": "Audio (*.mp3 *.wav *.flac *.ogg *.m4a);;All Files (*.*)"},
                    "volume": {"type": "float", "default": 1.0,
                               "min": 0.0, "max": 2.0, "step": 0.05}},
                   group="Info & Warnings")
    reg.add_action("system_ping",           "System Ping (Beep)",        {}, group="Info & Warnings")
    reg.add_action("warn_background", "Warning Background Color",
                   {"level": {"type": "int", "default": 1, "min": 1, "max": 2}},
                   group="Info & Warnings")
    reg.add_action("warn_background_reset", "Reset Background Color",    {}, group="Info & Warnings")


# --- Default System-Rules ---

SYSTEM_RULES_DEFAULT = {
    "version": 1,
    "rules": [
        {
            "id": "sys_singing_lyrics_fullscreen",
            "name": "Singing Call → Lyrics Fullscreen",
            "active": True,
            "trigger": "song_started",
            "conditions": [
                [{"type": "song_type_is_singing"}]
            ],
            "actions": [
                {"type": "dock_open", "params": {"dock_name": "lyrics"}},
                {"type": "dock_fullsize", "params": {"dock_name": "lyrics"}},
                {"type": "dock_focus", "params": {"dock_name": "lyrics"}},
                {"type": "auto_scroll_start", "params": {}},
            ],
        },
        {
            "id": "sys_singing_stop_default",
            "name": "Singing Call Stop → Default Layout",
            "active": True,
            "trigger": "song_stopped",
            "conditions": [
                [{"type": "song_type_is_singing"}]
            ],
            "actions": [
                {"type": "auto_scroll_stop", "params": {}},
                {"type": "layout_load", "params": {"layout_name": "default"}},
            ],
        },
        {
            "id": "sys_singing_pause_default",
            "name": "Singing Call Pause → Default Layout",
            "active": True,
            "trigger": "song_paused",
            "conditions": [
                [{"type": "song_type_is_singing"}]
            ],
            "actions": [
                {"type": "auto_scroll_stop", "params": {}},
                {"type": "layout_load", "params": {"layout_name": "default"}},
            ],
        },
        {
            "id": "sys_stop_auto_advance",
            "name": "Song Stop → Auto-Advance",
            "active": True,
            "trigger": "song_stopped",
            "conditions": [],
            "actions": [
                {"type": "auto_advance", "params": {}},
            ],
        },
        {
            "id": "sys_manager_closed_focus_playlist",
            "name": "Manager Closed → Focus Playlist",
            "active": True,
            "trigger": "manager_closed",
            "conditions": [],
            "actions": [
                {"type": "dock_focus", "params": {"dock_name": "playlist"}},
            ],
        },
        # --- Keyboard-Shortcuts ---
        {
            "id": "sys_key_f5_play",
            "name": "F5 → Play",
            "active": True,
            "trigger": "key_f5",
            "conditions": [],
            "actions": [{"type": "play", "params": {}}],
            "button_number": 1,
            "button_icon": "play.svg",
        },
        {
            "id": "sys_key_f6_pause",
            "name": "F6 → Pause",
            "active": True,
            "trigger": "key_f6",
            "conditions": [],
            "actions": [{"type": "pause", "params": {}}],
            "button_number": 2,
            "button_icon": "pause.svg",
        },
        {
            "id": "sys_key_f7_stop",
            "name": "F7 → Stop",
            "active": True,
            "trigger": "key_f7",
            "conditions": [],
            "actions": [{"type": "stop", "params": {}}],
            "button_number": 3,
            "button_icon": "stop.svg",
        },
        {
            "id": "sys_key_f8_fade_out",
            "name": "F8 → Fade Out",
            "active": True,
            "trigger": "key_f8",
            "conditions": [],
            "actions": [{"type": "fade_out", "params": {}}],
            "button_number": 4,
            "button_icon": "fade-out.svg",
        },
        {
            "id": "sys_key_space_toggle",
            "name": "Space → Play/Pause Toggle",
            "active": True,
            "trigger": "key_space",
            "conditions": [],
            "actions": [{"type": "play_pause_toggle", "params": {}}],
            "button_number": 5,
            "button_icon": "play-pause.svg",
        },
        {
            "id": "sys_key_l_location",
            "name": "L → Open Location Dialog",
            "active": True,
            "trigger": "key_l",
            "conditions": [],
            "actions": [{"type": "open_location_dialog", "params": {}}],
        },
        {
            "id": "sys_key_p_manager",
            "name": "P → Toggle Playlist Manager",
            "active": True,
            "trigger": "key_p",
            "conditions": [],
            "actions": [{"type": "toggle_manager", "params": {}}],
        },
    ],
}
