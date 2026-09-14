# P35 — Guided Tutorial / Wizard
## Pflichtenheft (technische Spezifikation)

---

## 1. Uebersicht

Leichtgewichtiges Tutorial-System fuer Callers Caddy: Pro Widget eine gefuehrte Tour
mit 3–7 Schritten, dargestellt als Tooltip-Overlays direkt am jeweiligen UI-Element.
Maximal ein Tutorial gleichzeitig aktiv, Reihenfolge ueber Prioritaeten gesteuert.

**Zentrales Konzept: Sequentielle Widget-Einfuehrung.**
Die Tutorials fuehren nacheinander durch die Widgets. Jedes Tutorial:
1. Blendet das zugehoerige Dock-Widget aktiv ein (falls nicht sichtbar)
2. Erklaert die Kernfunktionen des Widgets in 3–7 Schritten
3. Endet mit einem Hinweis auf das Ansicht-Menu ("Dieses Fenster findest du
   jederzeit im Menu Ansicht → [Widget-Name]")

So lernt der Benutzer nicht nur die Funktionen, sondern auch wie er Widgets
selbstaendig ein- und ausblenden kann.

---

## 2. Neue Dateien

| Datei | Zweck |
|---|---|
| `tutorial_engine.py` | Zentrale Steuerung (TutorialEngine), Overlay-Widget, Highlight |
| `tutorial_definitions.py` | Tutorial-Inhalte: Schritte, Element-Referenzen, Prioritaeten |
| translations.json | Neue Keys `tutorial.*` fuer alle Tutorial-Texte (de + en) |

Alles andere (INI, SkinManager, i18n) wird erweitert, nicht ersetzt.

---

## 3. Datenstrukturen

### 3.1 TutorialStep (dataclass)

```python
@dataclass
class TutorialStep:
    element_path: str       # z.B. "player.btn_play" oder "song_list.table"
    title_key: str          # i18n-Key: "tutorial.player.step1.title"
    text_key: str           # i18n-Key: "tutorial.player.step1.text"
    anchor: str = "auto"    # "top", "bottom", "left", "right", "auto"
    action: str = ""        # Optionale Aktion VOR dem Schritt:
                            #   "show_dock:dock_songlist" — Dock einblenden
                            #   "highlight_menu:menu_view" — Menu-Eintrag hervorheben
                            # Leer = keine Aktion
```

**Typischer letzter Schritt** jedes Tutorials zeigt das Ansicht-Menu:

```python
TutorialStep(
    element_path="_menu_bar",       # Spezial-Target: die Menubar selbst
    title_key="tutorial.player.last.title",
    text_key="tutorial.player.last.text",  # "Dieses Fenster findest du unter Ansicht → Player"
    anchor="bottom",
)
```

### 3.2 TutorialDef (dataclass)

```python
@dataclass
class TutorialDef:
    widget_id: str          # Stabil, z.B. "player", "song_list"
    dock_name: str          # ObjectName des Docks: "dock_player"
    priority: int           # Hoeher = wird zuerst angeboten (100 = Player)
    steps: list[TutorialStep]
    auto_show: bool = True  # Dock automatisch einblenden wenn Tutorial startet?
```

**auto_show = True** (Standard): Die Engine ruft `dock.show()` + `dock.raise_()`
auf, bevor der erste Schritt angezeigt wird. So funktioniert das Tutorial auch
fuer Widgets die beim Start nicht sichtbar sind (z.B. Planner, Reports, Potential).

### 3.3 Tutorial-Status (INI)

```ini
[Tutorials]
player = not_started
song_list = not_started
loop = completed
song_data = skipped
```

Moegliche Werte: `not_started`, `completed`, `skipped`

---

## 4. Klassen-Design

### 4.1 TutorialEngine

Zentrale Steuerung — wird einmal in `P29MainWindow.__init__()` erstellt.

```python
class TutorialEngine:
    """Verwaltet Tutorial-Ablauf, Status und Overlay."""

    def __init__(self, main_window, settings: QSettings, skin_mgr: SkinManager):
        self._main = main_window
        self._settings = settings
        self._skin_mgr = skin_mgr
        self._overlay: TutorialOverlay | None = None
        self._active_tutorial: TutorialDef | None = None
        self._current_step: int = 0
        self._widget_map: dict[str, QWidget] = {}  # widget_id -> QWidget-Instanz

    # --- Registrierung ---
    def register_widget(self, widget_id: str, widget: QWidget):
        """Registriert ein Widget fuer Element-Lookup."""
        self._widget_map[widget_id] = widget

    # --- Status ---
    def get_status(self, widget_id: str) -> str:
        return self._settings.value(f"Tutorials/{widget_id}", "not_started")

    def _set_status(self, widget_id: str, status: str):
        self._settings.setValue(f"Tutorials/{widget_id}", status)

    def reset_all(self):
        """Setzt alle Tutorial-Status zurueck (Menu: Tutorials neu starten)."""
        for tut in TUTORIALS:
            self._settings.setValue(f"Tutorials/{tut.widget_id}", "not_started")

    def reset_one(self, widget_id: str):
        """Setzt ein einzelnes Tutorial zurueck."""
        self._settings.setValue(f"Tutorials/{widget_id}", "not_started")

    # --- Trigger ---
    def check_and_start(self):
        """Prueft ob ein Tutorial gestartet werden soll.
        Aufgerufen nach App-Start und nach jedem Tutorial-Ende.

        Sequentielle Logik: Tutorials werden nacheinander angeboten,
        unabhaengig davon ob das Dock gerade sichtbar ist (wird bei
        Start automatisch eingeblendet).
        """
        if self._active_tutorial:
            return  # Bereits aktiv
        pending = [
            t for t in TUTORIALS
            if self.get_status(t.widget_id) == "not_started"
        ]
        if not pending:
            return
        # Hoechste Prioritaet zuerst
        pending.sort(key=lambda t: t.priority, reverse=True)
        self._offer_tutorial(pending[0])

    def _ensure_dock_visible(self, dock_name: str):
        """Blendet ein Dock-Widget ein und bringt es in den Vordergrund."""
        dock = self._main.findChild(QDockWidget, dock_name)
        if dock is not None:
            dock.show()
            dock.raise_()  # Bei Tabs: diesen Tab aktivieren

    # --- Tutorial-Ablauf ---
    def _offer_tutorial(self, tut: TutorialDef):
        """Zeigt Angebot: 'Tour durch [Widget] starten?' mit Ja/Nein."""
        # Implementierung: Kleiner Dialog oder erster Overlay-Schritt
        # mit "Tour starten" / "Ueberspringen"
        ...

    def _start_tutorial(self, tut: TutorialDef):
        # Dock einblenden bevor Tutorial startet
        if tut.auto_show:
            self._ensure_dock_visible(tut.dock_name)
        self._active_tutorial = tut
        self._current_step = 0
        self._show_step()

    def _show_step(self):
        step = self._active_tutorial.steps[self._current_step]

        # Optionale Aktion vor dem Schritt
        if step.action:
            self._execute_action(step.action)

        # Spezial-Target: Menubar
        if step.element_path == "_menu_bar":
            target = self._main.menuBar()
        else:
            target = self._resolve_element(step.element_path)

        if target is None or not target.isVisible():
            self._next_step()  # Element nicht sichtbar → ueberspringen
            return
        if self._overlay:
            self._overlay.close()
        self._overlay = TutorialOverlay(
            self._main, target, step, self._skin_mgr,
            on_next=self._next_step,
            on_skip=self._skip_tutorial,
            on_back=self._prev_step,
            step_num=self._current_step + 1,
            total_steps=len(self._active_tutorial.steps),
        )
        self._overlay.show()

    def _next_step(self):
        self._current_step += 1
        if self._current_step >= len(self._active_tutorial.steps):
            self._finish_tutorial("completed")
        else:
            self._show_step()

    def _prev_step(self):
        if self._current_step > 0:
            self._current_step -= 1
            self._show_step()

    def _skip_tutorial(self):
        self._finish_tutorial("skipped")

    def _finish_tutorial(self, status: str):
        self._set_status(self._active_tutorial.widget_id, status)
        if self._overlay:
            self._overlay.close()
            self._overlay = None
        self._active_tutorial = None
        self._current_step = 0
        # Naechstes Tutorial pruefen (mit kurzem Delay)
        QTimer.singleShot(500, self.check_and_start)

    # --- Schritt-Aktionen ---
    def _execute_action(self, action: str):
        """Fuehrt eine optionale Aktion vor einem Schritt aus.

        Unterstuetzte Aktionen:
          "show_dock:dock_name" — Dock einblenden + raise
        """
        if action.startswith("show_dock:"):
            dock_name = action.split(":", 1)[1]
            self._ensure_dock_visible(dock_name)

    # --- Element-Aufloesung ---
    def _resolve_element(self, element_path: str) -> QWidget | None:
        """Loest 'player.btn_play' auf zu QWidget-Instanz.

        Format: 'widget_id.attribute_name' oder
                'widget_id.attribute.sub_attribute'
        """
        parts = element_path.split(".")
        widget_id = parts[0]
        widget = self._widget_map.get(widget_id)
        if widget is None:
            return None
        obj = widget
        for attr in parts[1:]:
            obj = getattr(obj, attr, None)
            if obj is None:
                return None
        return obj if isinstance(obj, QWidget) else None
```

### 4.2 TutorialOverlay (QWidget)

Transparentes Fullscreen-Overlay ueber dem MainWindow. Zeichnet:
- Abdunkelungs-Maske mit Aussparung fuer das Ziel-Element
- Tooltip-Box mit Titel, Text, Navigation
- Pfeil vom Tooltip zum Ziel-Element

```python
class TutorialOverlay(QWidget):
    """Transparentes Overlay mit Highlight + Tooltip."""

    def __init__(self, parent, target: QWidget, step: TutorialStep,
                 skin_mgr: SkinManager, on_next, on_skip, on_back,
                 step_num: int, total_steps: int):
        super().__init__(parent)
        self.setWindowFlags(Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, False)
        self._target = target
        self._step = step
        self._skin_mgr = skin_mgr
        self._on_next = on_next
        self._on_skip = on_skip
        self._on_back = on_back
        self._step_num = step_num
        self._total_steps = total_steps

        # Tooltip-Widget (innere Box mit Text + Buttons)
        self._tooltip = _TooltipBox(self, step, skin_mgr,
                                     on_next, on_skip, on_back,
                                     step_num, total_steps)
        self._position_tooltip()

        # Volle Groesse des Parent-Fensters
        self.setGeometry(parent.rect())
        self.raise_()

    def _target_rect_global(self) -> QRect:
        """Ziel-Rect in Parent-Koordinaten."""
        pos = self._target.mapTo(self.parent(), QPoint(0, 0))
        return QRect(pos, self._target.size())

    def _position_tooltip(self):
        """Positioniert Tooltip relativ zum Ziel-Element.

        Strategie:
        1. Bevorzugte Richtung aus step.anchor (oder "auto")
        2. Auto: Unten, wenn Platz. Sonst oben. Sonst rechts/links.
        3. Rand-Clipping: Tooltip bleibt im Parent-Rect.
        """
        target_rect = self._target_rect_global()
        tooltip_size = self._tooltip.sizeHint()
        parent_rect = self.parent().rect()
        margin = 12  # Abstand zum Ziel

        anchor = self._step.anchor
        if anchor == "auto":
            # Unten bevorzugt
            if target_rect.bottom() + margin + tooltip_size.height() <= parent_rect.bottom():
                anchor = "bottom"
            elif target_rect.top() - margin - tooltip_size.height() >= parent_rect.top():
                anchor = "top"
            elif target_rect.right() + margin + tooltip_size.width() <= parent_rect.right():
                anchor = "right"
            else:
                anchor = "left"

        # Position berechnen
        if anchor == "bottom":
            x = target_rect.center().x() - tooltip_size.width() // 2
            y = target_rect.bottom() + margin
        elif anchor == "top":
            x = target_rect.center().x() - tooltip_size.width() // 2
            y = target_rect.top() - margin - tooltip_size.height()
        elif anchor == "right":
            x = target_rect.right() + margin
            y = target_rect.center().y() - tooltip_size.height() // 2
        else:  # left
            x = target_rect.left() - margin - tooltip_size.width()
            y = target_rect.center().y() - tooltip_size.height() // 2

        # Rand-Clipping
        x = max(8, min(x, parent_rect.width() - tooltip_size.width() - 8))
        y = max(8, min(y, parent_rect.height() - tooltip_size.height() - 8))

        self._tooltip.move(x, y)
        self._anchor_dir = anchor

    def paintEvent(self, event):
        """Zeichnet Abdunkelung + Highlight-Aussparung + Pfeil."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # 1. Abdunkelung (halbtransparent schwarz)
        overlay_color = QColor(0, 0, 0, 120)
        painter.fillRect(self.rect(), overlay_color)

        # 2. Aussparung fuer Ziel-Element (durchsichtig)
        target_rect = self._target_rect_global().adjusted(-4, -4, 4, 4)
        painter.setCompositionMode(QPainter.CompositionMode_Clear)
        painter.fillRect(target_rect, Qt.transparent)
        painter.setCompositionMode(QPainter.CompositionMode_SourceOver)

        # 3. Highlight-Rahmen um Ziel
        highlight_color = QColor(self._skin_mgr.color("tutorial_highlight", "#4a9eff"))
        pen = QPen(highlight_color, 2.5)
        painter.setPen(pen)
        painter.drawRoundedRect(target_rect, 4, 4)

        # 4. Pfeil von Tooltip zum Ziel
        self._draw_arrow(painter, target_rect, highlight_color)

        painter.end()

    def _draw_arrow(self, painter, target_rect, color):
        """Zeichnet einen Pfeil vom Tooltip-Rand zum Ziel-Rect."""
        # Vereinfacht: Linie + Dreiecksspitze
        ...

    def resizeEvent(self, event):
        """Bei Fenster-Resize neu positionieren."""
        self.setGeometry(self.parent().rect())
        self._position_tooltip()
        self.update()

    def mousePressEvent(self, event):
        """Klick ausserhalb des Tooltips = Skip."""
        if not self._tooltip.geometry().contains(event.pos()):
            self._on_skip()
```

### 4.3 _TooltipBox (QWidget)

Innere Box im Overlay mit Inhalt und Buttons.

```python
class _TooltipBox(QWidget):
    """Tooltip-Inhalt: Titel, Text, Buttons, Schritt-Anzeige."""

    def __init__(self, parent, step, skin_mgr, on_next, on_skip, on_back,
                 step_num, total_steps):
        super().__init__(parent)
        self.setFixedWidth(320)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)

        # Titel
        title = QLabel(_t(step.title_key))
        title.setStyleSheet("font-weight: bold; font-size: 14px;")
        layout.addWidget(title)

        # Text
        text = QLabel(_t(step.text_key))
        text.setWordWrap(True)
        layout.addWidget(text)

        # Schritt-Anzeige + Buttons
        btn_row = QHBoxLayout()
        step_label = QLabel(f"{step_num}/{total_steps}")
        step_label.setStyleSheet("color: #888;")
        btn_row.addWidget(step_label)
        btn_row.addStretch()

        if step_num > 1:
            btn_back = QPushButton(_t("tutorial.btn_back"))
            btn_back.clicked.connect(on_back)
            btn_row.addWidget(btn_back)

        if step_num < total_steps:
            btn_next = QPushButton(_t("tutorial.btn_next"))
            btn_next.clicked.connect(on_next)
            btn_row.addWidget(btn_next)
        else:
            btn_finish = QPushButton(_t("tutorial.btn_finish"))
            btn_finish.clicked.connect(on_next)
            btn_row.addWidget(btn_finish)

        btn_skip = QPushButton(_t("tutorial.btn_skip"))
        btn_skip.clicked.connect(on_skip)
        btn_row.addWidget(btn_skip)

        layout.addLayout(btn_row)

        # Styling
        bg = skin_mgr.color("widget_bg", "#363636")
        fg = skin_mgr.color("text", "#f0f0f0")
        border = skin_mgr.color("tutorial_highlight", "#4a9eff")
        self.setStyleSheet(
            f"background: {bg}; color: {fg}; "
            f"border: 2px solid {border}; border-radius: 8px;"
        )
```

---

## 5. Tutorial-Definitionen (tutorial_definitions.py)

**Reihenfolge** (Prioritaet absteigend — Player zuerst, Potential zuletzt):

| Prio | Widget | Dock | Schritte | Anmerkung |
|------|--------|------|----------|-----------|
| 100 | Player | dock_player | 6 | Kernfunktion, immer sichtbar |
| 90 | Songliste | dock_songlist | 4 | Zweites Kern-Widget |
| 80 | Playlist | dock_playlist | 3 | Getabbt mit Songliste |
| 70 | Loop | dock_loop | 4 | Unter Player |
| 60 | Song-Daten | dock_songdata | 4 | Getabbt mit Lyrics |
| 50 | Planner | dock_manager | 4 | Normalerweise versteckt |
| 40 | Lyrics | dock_lyrics | 2 | Getabbt rechts |
| 30 | Sequenzen | dock_sequences | 3 | Getabbt rechts |
| 20 | Reports | dock_reports | 3 | Floating, versteckt |
| 10 | Potential | dock_potential | 2 | Floating, versteckt |

**Muster**: Jedes Tutorial endet mit einem "Ansicht-Menu"-Schritt als letztem Step.

```python
from tutorial_engine import TutorialStep, TutorialDef

# Wiederverwendbarer letzter Schritt — zeigt auf Ansicht-Menu
def _menu_step(widget_id: str) -> TutorialStep:
    return TutorialStep(
        element_path="_menu_bar",
        title_key=f"tutorial.{widget_id}.menu.title",
        text_key=f"tutorial.{widget_id}.menu.text",
        anchor="bottom",
    )


TUTORIALS: list[TutorialDef] = [

    # --- Player (Prio 100) ---
    TutorialDef(
        widget_id="player",
        dock_name="dock_player",
        priority=100,
        steps=[
            TutorialStep("player.btn_play",
                         "tutorial.player.step1.title",
                         "tutorial.player.step1.text"),
            TutorialStep("player.btn_stop",
                         "tutorial.player.step2.title",
                         "tutorial.player.step2.text"),
            TutorialStep("player.btn_fade",
                         "tutorial.player.step3.title",
                         "tutorial.player.step3.text"),
            TutorialStep("player.slider_tempo",
                         "tutorial.player.step4.title",
                         "tutorial.player.step4.text"),
            TutorialStep("player.btn_preview",
                         "tutorial.player.step5.title",
                         "tutorial.player.step5.text"),
            _menu_step("player"),
        ],
    ),

    # --- Songliste (Prio 90) ---
    TutorialDef(
        widget_id="song_list",
        dock_name="dock_songlist",
        priority=90,
        steps=[
            TutorialStep("song_list.search_input",
                         "tutorial.songlist.step1.title",
                         "tutorial.songlist.step1.text"),
            TutorialStep("song_list.table",
                         "tutorial.songlist.step2.title",
                         "tutorial.songlist.step2.text"),
            TutorialStep("song_list.combo_sort",
                         "tutorial.songlist.step3.title",
                         "tutorial.songlist.step3.text"),
            _menu_step("song_list"),
        ],
    ),

    # --- Playlist (Prio 80) ---
    TutorialDef(
        widget_id="playlist",
        dock_name="dock_playlist",
        priority=80,
        steps=[
            TutorialStep("playlist.table",
                         "tutorial.playlist.step1.title",
                         "tutorial.playlist.step1.text"),
            TutorialStep("playlist.btn_clear",
                         "tutorial.playlist.step2.title",
                         "tutorial.playlist.step2.text"),
            _menu_step("playlist"),
        ],
    ),

    # --- Loop (Prio 70) ---
    TutorialDef(
        widget_id="loop",
        dock_name="dock_loop",
        priority=70,
        steps=[
            TutorialStep("loop.btn_new",
                         "tutorial.loop.step1.title",
                         "tutorial.loop.step1.text"),
            TutorialStep("loop.btn_set_in",
                         "tutorial.loop.step2.title",
                         "tutorial.loop.step2.text"),
            TutorialStep("loop.btn_beat_snap",
                         "tutorial.loop.step3.title",
                         "tutorial.loop.step3.text"),
            _menu_step("loop"),
        ],
    ),

    # --- Song-Daten (Prio 60) ---
    TutorialDef(
        widget_id="song_data",
        dock_name="dock_songdata",
        priority=60,
        steps=[
            TutorialStep("song_data.edit_title",
                         "tutorial.songdata.step1.title",
                         "tutorial.songdata.step1.text"),
            TutorialStep("song_data.btn_browse",
                         "tutorial.songdata.step2.title",
                         "tutorial.songdata.step2.text"),
            TutorialStep("song_data.btn_save",
                         "tutorial.songdata.step3.title",
                         "tutorial.songdata.step3.text"),
            _menu_step("song_data"),
        ],
    ),

    # --- Planner (Prio 50) — normalerweise versteckt ---
    TutorialDef(
        widget_id="playlist_manager",
        dock_name="dock_manager",
        priority=50,
        steps=[
            TutorialStep("playlist_manager.pool_table",
                         "tutorial.planner.step1.title",
                         "tutorial.planner.step1.text"),
            TutorialStep("playlist_manager.playlist_table",
                         "tutorial.planner.step2.title",
                         "tutorial.planner.step2.text"),
            TutorialStep("playlist_manager.btn_confirm",
                         "tutorial.planner.step3.title",
                         "tutorial.planner.step3.text"),
            _menu_step("playlist_manager"),
        ],
    ),

    # --- Lyrics (Prio 40) ---
    TutorialDef(
        widget_id="lyrics",
        dock_name="dock_lyrics",
        priority=40,
        steps=[
            TutorialStep("lyrics.browser",
                         "tutorial.lyrics.step1.title",
                         "tutorial.lyrics.step1.text"),
            _menu_step("lyrics"),
        ],
    ),

    # --- Sequenzen (Prio 30) ---
    TutorialDef(
        widget_id="sequences",
        dock_name="dock_sequences",
        priority=30,
        steps=[
            TutorialStep("sequences.table",
                         "tutorial.sequences.step1.title",
                         "tutorial.sequences.step1.text"),
            TutorialStep("sequences.combo_filter",
                         "tutorial.sequences.step2.title",
                         "tutorial.sequences.step2.text"),
            _menu_step("sequences"),
        ],
    ),

    # --- Reports (Prio 20) — floating, versteckt ---
    TutorialDef(
        widget_id="reports",
        dock_name="dock_reports",
        priority=20,
        steps=[
            TutorialStep("reports.combo_location",
                         "tutorial.reports.step1.title",
                         "tutorial.reports.step1.text"),
            TutorialStep("reports.btn_export",
                         "tutorial.reports.step2.title",
                         "tutorial.reports.step2.text"),
            _menu_step("reports"),
        ],
    ),

    # --- Potential (Prio 10) — floating, versteckt ---
    TutorialDef(
        widget_id="potential",
        dock_name="dock_potential",
        priority=10,
        steps=[
            TutorialStep("potential.tree",
                         "tutorial.potential.step1.title",
                         "tutorial.potential.step1.text"),
            _menu_step("potential"),
        ],
    ),
]
```

**Hinweis**: Die `element_path`-Werte (z.B. `player.btn_play`) werden waehrend der
Implementierung gegen die tatsaechlichen Attributnamen in den Widget-Klassen abgeglichen.
Die obigen Beispiele sind Platzhalter.

---

## 6. Integration in P29MainWindow

### 6.1 Initialisierung (in __init__, nach allen Docks)

```python
from tutorial_engine import TutorialEngine

# Nach allen Dock-Widgets erstellt:
self.tutorial_engine = TutorialEngine(self, self._settings, self.skin_mgr)
self.tutorial_engine.register_widget("player", self.player)
self.tutorial_engine.register_widget("song_list", self.song_list)
self.tutorial_engine.register_widget("loop", self.loop_widget)
self.tutorial_engine.register_widget("song_data", self.song_data)
self.tutorial_engine.register_widget("playlist", self.playlist_widget)
self.tutorial_engine.register_widget("playlist_manager", self.playlist_manager)
self.tutorial_engine.register_widget("lyrics", self.lyrics_widget)
self.tutorial_engine.register_widget("sequences", self.sequences_widget)
self.tutorial_engine.register_widget("reports", self.reports_widget)
self.tutorial_engine.register_widget("potential", self.potential_widget)
```

### 6.2 Trigger nach App-Start

```python
# Am Ende von __init__ oder in showEvent():
QTimer.singleShot(1000, self.tutorial_engine.check_and_start)
```

Der 1-Sekunden-Delay gibt dem Layout Zeit sich aufzubauen.

### 6.3 Menu-Integration

Im **View-Menu** oder als eigenes **Tutorial-Menu**:

```python
tutorial_menu = menu_bar.addMenu(_t("menu_tutorials"))

# Alle Tutorials neu starten
action_reset = tutorial_menu.addAction(_t("tutorial.menu_reset_all"))
action_reset.triggered.connect(self._on_tutorial_reset_all)

# Einzelnes Tutorial starten
for tut in TUTORIALS:
    action = tutorial_menu.addAction(
        _t(f"tutorial.menu_start_{tut.widget_id}")
    )
    action.triggered.connect(
        lambda checked, wid=tut.widget_id: self._on_tutorial_start(wid)
    )
```

```python
def _on_tutorial_reset_all(self):
    self.tutorial_engine.reset_all()
    self.tutorial_engine.check_and_start()

def _on_tutorial_start(self, widget_id: str):
    self.tutorial_engine.reset_one(widget_id)
    self.tutorial_engine.check_and_start()
```

### 6.4 Skin-Wechsel

Bei `_load_skin()`: Overlay (falls aktiv) schliesst und oeffnet sich mit neuen Farben.

```python
# In _load_skin(), nach QApplication.setStyleSheet():
if self.tutorial_engine._overlay:
    self.tutorial_engine._show_step()  # Overlay mit neuen Farben neu zeichnen
```

---

## 7. Skin-Erweiterung

Neue Farben in `skin.json` (alle Themes):

```json
{
  "colors": {
    "tutorial_highlight": "#4a9eff",
    "tutorial_overlay": "rgba(0, 0, 0, 0.47)",
    "tutorial_tooltip_bg": "{{widget_bg}}",
    "tutorial_tooltip_border": "#4a9eff"
  }
}
```

Fuer Light-Theme andere Werte (z.B. `tutorial_overlay: rgba(0,0,0,0.3)`).

---

## 8. Translations (Auszug)

Neue Keys in `translations.json`:

```json
{
  "menu_tutorials": {
    "de": "Tutorials",
    "en": "Tutorials"
  },
  "tutorial.menu_reset_all": {
    "de": "Alle Tutorials zuruecksetzen",
    "en": "Reset all tutorials"
  },
  "tutorial.btn_next": {
    "de": "Weiter",
    "en": "Next"
  },
  "tutorial.btn_back": {
    "de": "Zurueck",
    "en": "Back"
  },
  "tutorial.btn_skip": {
    "de": "Ueberspringen",
    "en": "Skip"
  },
  "tutorial.btn_finish": {
    "de": "Fertig",
    "en": "Done"
  },
  "tutorial.offer_title": {
    "de": "Tour: {widget_name}",
    "en": "Tour: {widget_name}"
  },
  "tutorial.offer_text": {
    "de": "Moechtest du eine kurze Einfuehrung in {widget_name}?",
    "en": "Would you like a quick tour of {widget_name}?"
  },
  "tutorial.offer_yes": {
    "de": "Tour starten",
    "en": "Start tour"
  },
  "tutorial.offer_no": {
    "de": "Nicht jetzt",
    "en": "Not now"
  },

  "tutorial.player.step1.title": {
    "de": "Wiedergabe",
    "en": "Playback"
  },
  "tutorial.player.step1.text": {
    "de": "Mit diesem Button startest du die Wiedergabe des aktuellen Songs.",
    "en": "Click this button to start playing the current song."
  },
  "tutorial.player.step2.title": {
    "de": "Stop",
    "en": "Stop"
  },
  "tutorial.player.step2.text": {
    "de": "Stoppt die Wiedergabe. Der naechste Song in der Playlist wird aktiviert.",
    "en": "Stops playback. The next song in the playlist will be activated."
  },
  "tutorial.player.step3.title": {
    "de": "Fade Out",
    "en": "Fade Out"
  },
  "tutorial.player.step3.text": {
    "de": "Blendet den Song sanft aus — perfekt am Ende eines Tip oder Square.",
    "en": "Smoothly fades out the song — perfect at the end of a tip or square."
  },
  "tutorial.player.step4.title": {
    "de": "Tempo",
    "en": "Tempo"
  },
  "tutorial.player.step4.text": {
    "de": "Hier passt du das Tempo an. Der Originalwert wird automatisch geladen.",
    "en": "Adjust the playback tempo here. The original value is loaded automatically."
  },
  "tutorial.player.step5.title": {
    "de": "Vorhoeren",
    "en": "Preview"
  },
  "tutorial.player.step5.text": {
    "de": "Spielt den Song nur ueber Kopfhoerer ab — die PA bleibt stumm.",
    "en": "Plays the song through headphones only — the PA stays silent."
  },

  "tutorial.songlist.step1.title": {
    "de": "Suche",
    "en": "Search"
  },
  "tutorial.songlist.step1.text": {
    "de": "Tippe hier, um Songs nach Titel oder Interpret zu filtern.",
    "en": "Type here to filter songs by title or artist."
  },
  "tutorial.songlist.step2.title": {
    "de": "Songliste",
    "en": "Song List"
  },
  "tutorial.songlist.step2.text": {
    "de": "Doppelklick laedt den Song in den Player. Die Spalte 'Gespielt' zeigt den Tagesstatus.",
    "en": "Double-click loads the song into the player. The 'Played' column shows today's status."
  },
  "tutorial.songlist.step3.title": {
    "de": "Sortierung",
    "en": "Sorting"
  },
  "tutorial.songlist.step3.text": {
    "de": "Wechsle zwischen Titel, Interpret, Tempo oder zuletzt gespielt.",
    "en": "Switch between title, artist, tempo, or last played."
  }
}
```

Weitere Tutorial-Texte werden bei der Implementierung ergaenzt.

---

## 9. Element-Referenzierung (technische Entscheidung)

### Gewaehlt: Attribut-Pfad (dot notation)

`"player.btn_play"` → `self._widget_map["player"].btn_play`

**Warum:**
- Kein zusaetzliches objectName-Mapping noetig
- Sofort lesbar, welches Widget/Element gemeint ist
- Refactoring-sicher: Wenn ein Attribut umbenannt wird, schlaegt die Aufloesung
  fehl und der Schritt wird uebersprungen (nicht crashed)
- Kein findChild-Overhead

**Voraussetzung:** Die Widget-Attribute (btn_play, slider_tempo etc.) bleiben stabil.
Falls ein Attribut intern umbenannt wird, muss die Tutorial-Definition angepasst werden.

---

## 10. Entscheidungen (abgenommen)

| # | Frage | Entscheidung |
|---|---|---|
| 1 | **Automatisch starten oder fragen?** | **Fragen** — Offer-Overlay mit "Tour starten" / "Nicht jetzt". Skippen moeglich. |
| 2 | **Element nicht sichtbar?** | **Widgets werden aktiv eingeblendet** (`auto_show`). Letzter Schritt jedes Tutorials zeigt das Ansicht-Menu. Tutorials erklaeren Widgets sequentiell nacheinander. |
| 3 | **Tooltip bei Fensterbewegung?** | **Position bei jedem Schritt neu berechnen** + resizeEvent abfangen. Kein Live-Tracking. |
| 4 | **Neustart-Funktion?** | **Ja** — Menu "Tutorials" mit "Alle zuruecksetzen" + Einzel-Reset pro Widget. |
| 5 | **Overlay-Design?** | **Abdunkelung + Highlight-Rahmen + Pfeil.** |
| 6 | **Klick ausserhalb = Skip?** | **Ja** — Tutorial wird als "skipped" gespeichert. (User will evtl. direkt etwas testen — spaeter ueber Menu erneut startbar.) |
| 7 | **Keyboard-Shortcuts?** | **Enter = Next, Escape = Skip.** |

---

## 11. Implementierungsreihenfolge

1. **tutorial_engine.py**: TutorialOverlay + TutorialEngine (Kern-System)
2. **tutorial_definitions.py**: 2-3 Tutorials (Player, Songliste) mit echten element_paths
3. **translations.json**: Tutorial-Keys (de + en)
4. **skin.json**: Tutorial-Farben (alle 4 Themes)
5. **main.py**: Integration (register, trigger, menu)
6. **Test + Feinschliff**: Positionierung, Edge-Cases, alle Widgets
7. **Restliche Tutorials**: Loop, SongData, Playlist, Planner, Lyrics, Sequences, Reports, Potential

---

## 12. Nicht-funktionale Anforderungen

- **Kein neues pip-Paket** — alles mit PySide6-Bordmitteln (QPainter, QWidget)
- **Keine festen Pixel-Positionen** — alles dynamisch berechnet
- **Performance**: Overlay ist ein einzelnes QWidget, kein Fenster-Stack
- **Robustheit**: Fehlende Elemente → Schritt wird uebersprungen, kein Crash
- **Erweiterbar**: Neues Tutorial = neue TutorialDef in tutorial_definitions.py + Keys in translations.json
