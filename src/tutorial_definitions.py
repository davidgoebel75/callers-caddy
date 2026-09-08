"""
Tutorial-Definitionen fuer Callers Caddy (P35).
================================================
Jedes Widget hat ein Tutorial mit 3–7 Schritten.

Reihenfolge (Prioritaet absteigend):
  Player → Lokationen (Dialog) → Song List → Song Data → Planner →
  Playlist → Loop → Beat Snap (Dialog) → Lyrics → Sequences →
  Reports → Potential

Attribut-Pfade muessen mit den tatsaechlichen Widget-Attributen uebereinstimmen:
  "player.btn_play" → main_window.player.btn_play (QWidget)
  "a+b" → Multi-Highlight: beide Elemente gleichzeitig rahmen
"""

from tutorial_engine import TutorialStep, TutorialDef


# ---------------------------------------------------------------------------
# Dialog-Tutorial: Lokationen
# ---------------------------------------------------------------------------

LOCATION_DIALOG_STEPS: list[TutorialStep] = [
    TutorialStep(
        "list_widget",
        "tutorial.location.list.title",
        "tutorial.location.list.text",
    ),
    TutorialStep(
        "btn_add",
        "tutorial.location.add.title",
        "tutorial.location.add.text",
    ),
    TutorialStep(
        "btn_rename",
        "tutorial.location.rename.title",
        "tutorial.location.rename.text",
    ),
    TutorialStep(
        "btn_no_location",
        "tutorial.location.none.title",
        "tutorial.location.none.text",
    ),
]


# ---------------------------------------------------------------------------
# Dialog-Tutorial: Beat Snap
# ---------------------------------------------------------------------------

BEAT_SNAP_DIALOG_STEPS: list[TutorialStep] = [
    TutorialStep(
        "_waveform_out",
        "tutorial.beat_snap.waveform_out.title",
        "tutorial.beat_snap.waveform_out.text",
    ),
    TutorialStep(
        "_waveform_in",
        "tutorial.beat_snap.waveform_in.title",
        "tutorial.beat_snap.waveform_in.text",
    ),
    TutorialStep(
        "_btn_audition",
        "tutorial.beat_snap.audition.title",
        "tutorial.beat_snap.audition.text",
    ),
    TutorialStep(
        "_btn_snap",
        "tutorial.beat_snap.snap.title",
        "tutorial.beat_snap.snap.text",
    ),
    TutorialStep(
        "_btn_apply+_btn_close",
        "tutorial.beat_snap.apply.title",
        "tutorial.beat_snap.apply.text",
    ),
]


TUTORIALS: list[TutorialDef] = [

    # --- Player (Prio 100) ---
    TutorialDef(
        widget_id="player",
        dock_name="dock_player",
        priority=100,
        steps=[
            TutorialStep("player.btn_play",
                         "tutorial.player.play.title",
                         "tutorial.player.play.text"),
            TutorialStep("player.btn_stop",
                         "tutorial.player.stop.title",
                         "tutorial.player.stop.text"),
            TutorialStep("player.btn_fade",
                         "tutorial.player.fade.title",
                         "tutorial.player.fade.text"),
            TutorialStep("player.spin_today_tempo",
                         "tutorial.player.today_tempo.title",
                         "tutorial.player.today_tempo.text"),
            TutorialStep("player.spin_tempo",
                         "tutorial.player.tempo.title",
                         "tutorial.player.tempo.text"),
            TutorialStep("player.spin_pitch",
                         "tutorial.player.pitch.title",
                         "tutorial.player.pitch.text"),
            TutorialStep("player.slider_position",
                         "tutorial.player.position.title",
                         "tutorial.player.position.text"),
            TutorialStep("player.section_bar",
                         "tutorial.player.sections.title",
                         "tutorial.player.sections.text"),
            TutorialStep("player.btn_location",
                         "tutorial.player.location.title",
                         "tutorial.player.location.text"),
        ],
    ),

    # Lokationen = Dialog-Tutorial (wird nach Player automatisch getriggert)

    # --- New Songs / Loop (Prio 97) ---
    TutorialDef(
        widget_id="loop",
        dock_name="dock_loop",
        priority=97,
        steps=[
            TutorialStep("loop.btn_new",
                         "tutorial.loop.step1.title",
                         "tutorial.loop.step1.text"),
            TutorialStep("loop.btn_find_loop",
                         "tutorial.loop.step2.title",
                         "tutorial.loop.step2.text"),
        ],
    ),

    # --- Loop Finder (Prio 96) — direkt nach New Songs ---
    TutorialDef(
        widget_id="loop_finder",
        dock_name="dock_loop_finder",
        priority=96,
        steps=[
            TutorialStep("loop_finder._waveform",
                         "tutorial.loop_finder.waveform.title",
                         "tutorial.loop_finder.waveform.text"),
            TutorialStep("loop_finder._spin_in_start+loop_finder._spin_in_end+"
                         "loop_finder._spin_out_start+loop_finder._spin_out_end",
                         "tutorial.loop_finder.regions.title",
                         "tutorial.loop_finder.regions.text"),
            TutorialStep("loop_finder._combo_window",
                         "tutorial.loop_finder.window.title",
                         "tutorial.loop_finder.window.text"),
            TutorialStep("loop_finder._btn_analyze",
                         "tutorial.loop_finder.analyze.title",
                         "tutorial.loop_finder.analyze.text"),
            TutorialStep("loop_finder._table",
                         "tutorial.loop_finder.results.title",
                         "tutorial.loop_finder.results.text"),
            TutorialStep("loop_finder._btn_apply",
                         "tutorial.loop_finder.apply.title",
                         "tutorial.loop_finder.apply.text"),
        ],
    ),

    # --- Layout-Einfuehrung (Prio 95) — nach Lokationen, vor Songliste ---
    TutorialDef(
        widget_id="layout_intro",
        dock_name="dock_player",  # Zeigt auf Player als Beispiel-Dock
        priority=95,
        auto_show=False,  # Kein Dock einblenden noetig
        offer_text_key="tutorial.layout.offer_text",
        steps=[
            TutorialStep("_dock_player_title",
                         "tutorial.layout.drag.title",
                         "tutorial.layout.drag.text"),
            TutorialStep("_dock_player_title",
                         "tutorial.layout.undock.title",
                         "tutorial.layout.undock.text"),
            TutorialStep("_dock_player_title",
                         "tutorial.layout.resize.title",
                         "tutorial.layout.resize.text"),
            TutorialStep("_menu_bar",
                         "tutorial.layout.save.title",
                         "tutorial.layout.save.text"),
        ],
    ),

    # --- Songliste (Prio 90) ---
    TutorialDef(
        widget_id="song_list",
        dock_name="dock_songlist",
        priority=90,
        steps=[
            TutorialStep("song_list.edit_search",
                         "tutorial.songlist.step1.title",
                         "tutorial.songlist.step1.text"),
            TutorialStep("song_list.table",
                         "tutorial.songlist.step2.title",
                         "tutorial.songlist.step2.text"),
        ],
    ),

    # --- Song-Daten (Prio 80) ---
    TutorialDef(
        widget_id="song_data",
        dock_name="dock_songdata",
        priority=80,
        steps=[
            TutorialStep("song_data.edit_title",
                         "tutorial.songdata.step1.title",
                         "tutorial.songdata.step1.text"),
            TutorialStep("song_data.btn_browse_file",
                         "tutorial.songdata.step2.title",
                         "tutorial.songdata.step2.text"),
            TutorialStep("song_data.spin_bpm+song_data.btn_auto_bpm",
                         "tutorial.songdata.step3.title",
                         "tutorial.songdata.step3.text"),
            TutorialStep("song_data.btn_browse_lyrics",
                         "tutorial.songdata.step4.title",
                         "tutorial.songdata.step4.text"),
        ],
    ),

    # --- Planner (Prio 70) — normalerweise versteckt ---
    TutorialDef(
        widget_id="playlist_manager",
        dock_name="dock_manager",
        priority=70,
        steps=[
            TutorialStep("playlist_manager._rb_all+playlist_manager._combo_genre+playlist_manager._combo_sort",
                         "tutorial.planner.filters.title",
                         "tutorial.planner.filters.text"),
            TutorialStep("playlist_manager._pool_table",
                         "tutorial.planner.step1.title",
                         "tutorial.planner.step1.text"),
            TutorialStep("playlist_manager._pl_table",
                         "tutorial.planner.step2.title",
                         "tutorial.planner.step2.text"),
            TutorialStep("playlist_manager._btn_confirm",
                         "tutorial.planner.step3.title",
                         "tutorial.planner.step3.text"),
        ],
    ),

    # --- Playlist (Prio 60) ---
    TutorialDef(
        widget_id="playlist",
        dock_name="dock_playlist",
        priority=60,
        steps=[
            TutorialStep("playlist._pl_table",
                         "tutorial.playlist.step1.title",
                         "tutorial.playlist.step1.text"),
            TutorialStep("playlist._btn_load+playlist._btn_save",
                         "tutorial.playlist.step2.title",
                         "tutorial.playlist.step2.text"),
        ],
    ),

    # --- Lyrics (Prio 40) ---
    TutorialDef(
        widget_id="lyrics",
        dock_name="dock_lyrics",
        priority=40,
        steps=[
            TutorialStep("lyrics._browser",
                         "tutorial.lyrics.step1.title",
                         "tutorial.lyrics.step1.text"),
            TutorialStep("lyrics._btn_auto_scroll",
                         "tutorial.lyrics.step2.title",
                         "tutorial.lyrics.step2.text"),
        ],
    ),

    # --- Sequenzen (Prio 30) ---
    TutorialDef(
        widget_id="sequences",
        dock_name="dock_sequences",
        priority=30,
        steps=[
            TutorialStep("sequences._table",
                         "tutorial.sequences.step1.title",
                         "tutorial.sequences.step1.text"),
            TutorialStep("sequences._combo_contains",
                         "tutorial.sequences.step2.title",
                         "tutorial.sequences.step2.text"),
        ],
    ),

    # --- Reports (Prio 20) — floating, nie dockbar ---
    TutorialDef(
        widget_id="reports",
        dock_name="dock_reports",
        priority=20,
        steps=[
            TutorialStep("reports._combo_location",
                         "tutorial.reports.step1.title",
                         "tutorial.reports.step1.text"),
            TutorialStep("reports._btn_export",
                         "tutorial.reports.step2.title",
                         "tutorial.reports.step2.text"),
        ],
    ),

    # --- Rules (Prio 16) — floating, versteckt ---
    TutorialDef(
        widget_id="rules",
        dock_name="dock_rules",
        priority=16,
        steps=[
            TutorialStep("rules._table",
                         "tutorial.rules.list.title",
                         "tutorial.rules.list.text"),
            TutorialStep("rules._btn_add",
                         "tutorial.rules.add.title",
                         "tutorial.rules.add.text"),
            TutorialStep("rules._edit_name+rules._chk_active+rules._chk_once",
                         "tutorial.rules.name.title",
                         "tutorial.rules.name.text"),
            TutorialStep("rules._combo_trigger",
                         "tutorial.rules.trigger.title",
                         "tutorial.rules.trigger.text"),
            TutorialStep("rules._cond_group",
                         "tutorial.rules.conditions.title",
                         "tutorial.rules.conditions.text"),
            TutorialStep("rules._action_group",
                         "tutorial.rules.actions.title",
                         "tutorial.rules.actions.text"),
            TutorialStep("rules._btn_export+rules._btn_import",
                         "tutorial.rules.import_export.title",
                         "tutorial.rules.import_export.text"),
        ],
    ),

    # --- Potential (Prio 10) — floating, versteckt ---
    TutorialDef(
        widget_id="potential",
        dock_name="dock_potential",
        priority=10,
        steps=[
            TutorialStep("potential._table",
                         "tutorial.potential.step1.title",
                         "tutorial.potential.step1.text"),
        ],
    ),
]
