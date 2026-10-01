"""Lyrics-Widget fuer Callers Caddy (BL-201, Stufe 3 — Pilot-Cluster).

Groesster eigenstaendiger Brocken aus main.py: der Lyric-/Text-Editor
(LyricsWidget) mit Abschnitts-Farb-Overlay (_LyricSectionOverlay), den
Abschnitts-Konstanten und den Helferfunktionen lyric_section_lines /
lyric_plain_text. Kommuniziert wie die uebrigen Widgets ueber Signale +
Dependency-Injection; kein Import von main (kein Zirkel).
"""

import os
import re
import time
import difflib

import perf
import singing_sections
import heads_sides
from i18n import _t
from path_manager import PathManager
from skin_manager import SkinManager
from zoom_wheel import install_ctrl_wheel_zoom
from song_db import CHECK_START_GENRE_NAME
from ui_helpers import _WrapButtonBar, mark_toggle

from PySide6.QtCore import (
    Qt, QTimer, QEvent, QPoint, QRect,
)
from PySide6.QtGui import (
    QIcon, QKeySequence, QShortcut, QTextDocument, QPainter, QColor,
    QBrush, QFont, QTextCharFormat, QTextBlockFormat, QTextCursor,
)
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QComboBox,
    QSpinBox, QMenu, QMessageBox, QInputDialog, QColorDialog, QSizePolicy,
    QTextBrowser,
)


# ===========================================================================
# Lyric-Abschnitte: Farb-Overlay (BL-171)
# ===========================================================================

# Kanonische Reihenfolge und Namen der Abschnitte. Die ersten sieben sind das
# Zeitraster des Singing Calls (Teil 1..7), "tag" und "additional" liegen
# ausserhalb — siehe singing_sections.SectionResult.extras.
LYRIC_SECTION_ORDER = ["opener", "figure1", "figure2", "break",
                       "figure3", "figure4", "closer", "tag", "additional"]

# Teil-Nummer des 7er-Rasters -> Abschnittsname
LYRIC_PART_TO_NAME = {1: "opener", 2: "figure1", 3: "figure2", 4: "break",
                      5: "figure3", 6: "figure4", 7: "closer"}

# Kuerzel im Streifen — deckungsgleich mit SectionBarWidget._LABELS (O,1,2,M,3,4,C)
LYRIC_SECTION_LABEL = {"opener": "O", "figure1": "1", "figure2": "2",
                       "break": "M", "figure3": "3", "figure4": "4",
                       "closer": "C", "tag": "T", "additional": "A"}

# Farbe je Abschnitt — Skin-Schluessel + Rueckfallwert. Die ersten sieben
# nutzen exakt die Schluessel und Fallbacks der SectionBarWidget, damit Streifen
# und Abschnittsleiste garantiert dieselben Farben zeigen und nicht nur zufaellig
# gleiche Werte enthalten. Bewusst neun EINZELNE Eintraege, auch wo sich Werte
# heute wiederholen: so laesst sich spaeter jeder Abschnitt einzeln einfaerben,
# ohne die Struktur anzufassen.
#   O/M/C rot (gleiche Rolle), ungerade Figuren hell-, gerade dunkelgrau.
#   Tag und Additional haben eigene Schluessel und starten auf dem Rot.
LYRIC_SECTION_COLORS = {
    "opener":     ("sec_o", "#9e3a3a"),
    "figure1":    ("sec_1", "#6b7280"),
    "figure2":    ("sec_2", "#4a5568"),
    "break":      ("sec_m", "#9e3a3a"),
    "figure3":    ("sec_3", "#6b7280"),
    "figure4":    ("sec_4", "#4a5568"),
    "closer":     ("sec_c", "#9e3a3a"),
    "tag":        ("sec_t", "#9e3a3a"),
    "additional": ("sec_a", "#9e3a3a"),
}


def lyric_section_lines(res, text: str) -> dict:
    """SectionResult + Plain-Text -> {abschnittsname: (startzeile, endzeile)}.

    Gemeinsame Grundlage fuer beide Wege, auf denen Abschnitte entstehen: den
    Auto-Sync im Lyric-Fenster und den Bulk-Lauf im Hintergrund-Worker. Getrennt
    gerechnet wuerden beide frueher oder spaeter unterschiedliche Zeilen
    liefern — und der Streifen saesse je nach Herkunft woanders.

    Zeilen statt Zeichenpositionen, weil die Sync-Marken spaeter Zeichen
    verschieben, aber keine Zeilenumbrueche einfuegen.
    """
    import bisect
    offsets, pos = [], 0
    for raw in text.split("\n"):
        offsets.append(pos)
        pos += len(raw) + 1

    def to_line(char_pos):
        return max(0, bisect.bisect_right(offsets, int(char_pos)) - 1)

    out = {}
    for part, name in LYRIC_PART_TO_NAME.items():
        blk = res.parts.get(part)
        if blk:
            out[name] = (to_line(blk[0]), to_line(blk[1]))
    for name, blk in (getattr(res, "extras", None) or {}).items():
        out[name] = (to_line(blk[0]), to_line(blk[1]))
    return out


class _ReadingBandOverlay(QWidget):
    """Lesebalken (intern#76): farbiges Band ueber dem gerade gesungenen Text.

    Liegt als durchsichtige Flaeche deckungsgleich ueber dem Viewport und
    laesst alle Mausereignisse durch (Sync-Klicks, Markieren, Rad). Kind des
    Browsers, NICHT des Viewports: Beim Scrollen verschiebt Qt die Kinder des
    Viewports mit, der Balken waere mitgewandert. Das Dokument wird nicht
    angefasst. Die Position kommt aus LyricsWidget._band_doc_y
    (Dokument-Y des gesungenen Texts, OHNE "Textsprung timen"); gemalt wird
    relativ zum aktuellen Scroll-Wert. Farbe aus dem Skin ("reading_band").
    """

    _FALLBACK_COLOR = "#4a9eff"

    def __init__(self, owner: 'LyricsWidget'):
        super().__init__(owner._browser)
        self._owner = owner
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.sync_geometry()
        self.show()

    def sync_geometry(self):
        """Deckungsgleich mit dem Viewport (ohne Rahmen und Scrollbalken)."""
        self.setGeometry(self._owner._browser.viewport().geometry())
        self.raise_()

    def band_rect(self):
        """Rechteck des Balkens in Viewport-Koordinaten oder None."""
        o = self._owner
        if (o._band_doc_y is None or not o._reading_band_enabled
                or not o._lyrics_loaded or o._sync_mode or o._edit_mode):
            return None
        h = self.height()
        band_h = max(2, int(h * o._reading_band_height_pct / 100.0))
        y = int(o._band_doc_y) - o._browser.verticalScrollBar().value()
        return QRect(0, y - band_h // 2, self.width(), band_h)

    def paintEvent(self, _event):
        rect = self.band_rect()
        if rect is None or not rect.intersects(self.rect()):
            return
        sm = getattr(self._owner, "_skin_mgr", None)
        try:
            color = QColor(sm.color("reading_band", self._FALLBACK_COLOR)
                           if sm else self._FALLBACK_COLOR)
        except Exception:
            color = QColor(self._FALLBACK_COLOR)
        color.setAlpha(int(255 * self._owner._reading_band_opacity_pct / 100.0))
        painter = QPainter(self)
        painter.fillRect(rect, color)
        painter.end()


class _LyricSectionOverlay(QWidget):
    """Farbstreifen der Lyric-Abschnitte — eine eigene Spalte NEBEN dem Text.

    Bewusst kein Overlay ueber dem Textbereich: dort waere jeder Klick auf eine
    Abschnittskante beim QTextBrowser darunter gelandet und haette einen
    Sync-Punkt gesetzt. Als eigenes Feld gibt es diesen Konflikt nicht, und der
    Text bleibt vollstaendig unverdeckt.

    Es ist KEINE Kopie der SectionBarWidget: kein Button, kein Layout, nur eine
    Malflaeche. Das Dokument wird nicht angefasst — die Sync-Marken sind
    eingefuegter Text, jede weitere Textmanipulation muesste durch dieselbe
    pristine<->display-Buchhaltung.

    Die y-Koordinaten stammen aus cursorRect() und sind Viewport-Koordinaten des
    Browsers. Weil dieses Widget daneben liegt und oben buendig mit dem Browser
    (nicht mit dessen Viewport) sitzt, wird der Rahmenversatz beim Malen
    ausgeglichen.
    """

    # Deckkraft: fast voll. Die Halbtransparenz stammte aus der Zeit, als der
    # Streifen ueber dem Text lag und dessen Lesbarkeit schuetzen musste. Daneben
    # gibt es den Grund nicht mehr — und blass gezogen waren Hell- und Dunkelgrau
    # der Figuren nicht mehr auseinanderzuhalten.
    _ALPHA   = 225
    _GAP     = 3    # Luecke zwischen zwei Abschnitten (vertikal), in Pixel
    _COL_GAP = 2    # Luecke zwischen Spalten desselben Textblocks
    _WIDTH   = 58   # Breite der Spalte in Pixel

    _EDGE_TOL = 5   # Fangbereich um eine Kante, in Pixel
    _CUT_BAND_H = 6  # BL-200: Hoehe des Schnitt-Trenners im Figuren-Balken (Pixel)

    def __init__(self, owner: 'LyricsWidget'):
        super().__init__(owner)
        self._owner = owner
        self.setFixedWidth(self._WIDTH)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)
        # Fuer den Kanten-Cursor braucht es Move-Events ohne gedrueckte Taste
        self.setMouseTracking(True)
        self._drag = None   # (names, "top"|"bottom") waehrend des Ziehens
        self.show()

    def _color_for(self, name: str) -> QColor:
        """Abschnittsfarbe aus dem Skin, sonst Rueckfallwert."""
        key, fallback = LYRIC_SECTION_COLORS.get(name, ("sec_1", "#6b7280"))
        sm = getattr(self._owner, "_skin_mgr", None)
        try:
            return QColor(sm.color(key, fallback) if sm else fallback)
        except Exception:
            return QColor(fallback)

    def _viewport_dy(self) -> int:
        """Versatz zwischen Browser-Oberkante und Viewport-Oberkante (Rahmen)."""
        try:
            vp = self._owner._browser.viewport()
            return vp.mapTo(self._owner._browser, QPoint(0, 0)).y()
        except Exception:
            return 0

    def sync_geometry(self):
        # Hoehe kommt aus dem Layout; nur die Sichtbarkeit steuern wir. Der
        # Streifen ist ein Werkzeug zum Bearbeiten, kein Orientierungshilfe im
        # Live-Betrieb — dafuer gibt es die Fortschrittsleiste in der
        # Statuszeile. Also nur im Sync-Modus, und nur mit Abschnitten.
        self.setVisible(bool(self._owner._sync_mode
                             and self._owner._lyric_sections))

    def _column_rects(self) -> list:
        """[(name, QRect)] — die Flaeche JEDER einzelnen Abschnittsspalte.

        Gemeinsame Quelle fuer Zeichnen und Treffererkennung. Getrennt gerechnet
        wuerden beide frueher oder spaeter auseinanderlaufen, und dann laege der
        Griffbereich nicht mehr dort, wo die Kante zu sehen ist.
        """
        dy = self._viewport_dy()
        bar_w = self.width() - 1
        if bar_w <= 0:
            return []

        # 1) Balken auf Spuren verteilen. Ueberlappen sich zwei Abschnitte
        #    senkrecht, muessen sie nebeneinander — das deckt sowohl den
        #    Normalfall (Opener/Break/Closer auf demselben Text) als auch
        #    teilweise Ueberlappung nach dem Verschieben ab. Wer sich NICHT
        #    ueberlappt, darf dieselbe Spur weiternutzen und bleibt breit.
        placed, lane_bottom = [], []
        for name, y0, y1 in self._owner.section_rects():
            top = y0 + dy + self._GAP
            bottom = y1 + dy - self._GAP
            if bottom <= top:
                # Sehr kurzer Abschnitt: lieber duenn zeichnen als verschwinden
                bottom = top + 1
            for lane, occupied_until in enumerate(lane_bottom):
                if top > occupied_until:
                    lane_bottom[lane] = bottom
                    break
            else:
                lane_bottom.append(bottom)
                lane = len(lane_bottom) - 1
            placed.append((name, lane, top, bottom))

        # 2) Breite aus der Spuranzahl. Alle Balken nutzen dasselbe Raster,
        #    damit eine Spalte beim Scrollen nicht springt.
        n_lanes = max(1, len(lane_bottom))
        col_w = (bar_w - self._COL_GAP * (n_lanes - 1)) / n_lanes
        if col_w < 1:
            col_w = bar_w / n_lanes
        out = []
        for name, lane, top, bottom in placed:
            cx = lane * (col_w + self._COL_GAP)
            out.append((name, QRect(int(cx), int(top),
                                    max(1, int(col_w)), int(bottom - top))))
        return out

    def paintEvent(self, event):
        cols = self._column_rects()
        if not cols:
            return
        dy = self._viewport_dy()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        font = painter.font()
        font.setBold(True)
        font.setPixelSize(11)
        painter.setFont(font)

        for name, rect in cols:
            col = self._color_for(name)
            col.setAlpha(self._ALPHA)
            painter.setPen(Qt.NoPen)
            painter.setBrush(col)
            painter.drawRoundedRect(rect, 4, 4)
            # Kuerzel nur, wenn die Spalte gross genug dafuer ist
            if rect.height() >= 16 and rect.width() >= 11:
                painter.setPen(QColor(255, 255, 255, 210))
                painter.drawText(rect, Qt.AlignHCenter | Qt.AlignTop,
                                 LYRIC_SECTION_LABEL.get(name, "?"))
            # BL-200: Schnitt-Trenner im Figuren-Balken (Call-Ende → Gesangstext).
            # Nur wo der Schnitt echt INNERHALB des Blocks liegt (sonst kein Tail).
            # Als breites Band in der Widget-Hintergrundfarbe: durchtrennt den
            # farbigen Balken und faellt so in JEDEM Theme auf.
            cy = self._figure_cut_overlay_y(name, dy)
            if cy is not None and rect.top() + 3 < cy < rect.bottom() - 3:
                band_h = self._CUT_BAND_H
                band = QRect(rect.left(), int(cy) - band_h // 2,
                             rect.width(), band_h)
                painter.setPen(Qt.NoPen)
                painter.setBrush(self.palette().color(self.backgroundRole()))
                painter.drawRect(band)
        painter.end()

    def _figure_cut_overlay_y(self, name: str, dy: int):
        """Overlay-y-Koordinate des Schnitt-Strichs einer Figur, sonst None."""
        if name not in self._owner._DYNAMIC_FIGURES:
            return None
        by = self._owner.figure_cut_y(name)
        return None if by is None else int(by) + dy

    # ---- Kanten ziehen (nur im Sync-Modus, weil nur dort sichtbar) ----

    def _hit_edge(self, x: int, y: int):
        """(name, "top"|"bottom") wenn (x,y) nahe einer Kante liegt, sonst None.

        Getroffen wird die EINZELNE Spalte unter dem Mauszeiger, nicht die
        Gruppe: liegen Opener und Middle Break nach der Auto-Analyse auf
        demselben Text, sollen sie sich trotzdem getrennt verschieben lassen —
        etwa um den Break nachtraeglich in die Alternativen Lyrics zu ziehen.
        Nach dem ersten Zug haben sie unterschiedliche Bereiche und bekommen
        ohnehin eigene Balken.

        Ober- und Unterkante sind getrennt greifbar. Genau dafuer sitzt zwischen
        den Balken die Luecke aus _GAP: ohne sie laegen das Ende des einen und
        der Anfang des naechsten Abschnitts uebereinander.
        """
        best = None
        best_dist = self._EDGE_TOL + 1
        dy = self._viewport_dy()
        for name, rect in self._column_rects():
            if not (rect.left() - 1 <= x <= rect.right() + 1):
                continue
            edges = [("top", rect.top()), ("bottom", rect.bottom())]
            # BL-200: der Schnitt-Strich der Figur ist eine dritte greifbare Kante
            cy = self._figure_cut_overlay_y(name, dy)
            if cy is not None and rect.top() < cy < rect.bottom():
                edges.append(("cut", cy))
            for edge, ey in edges:
                d = abs(y - ey)
                if d < best_dist:
                    best_dist, best = d, (name, edge)
        return best

    def mouseMoveEvent(self, event):
        pos = event.position()
        x, y = int(pos.x()), int(pos.y())
        if self._drag is not None:
            self._apply_drag(y)
            return
        self.setCursor(Qt.SizeVerCursor if self._hit_edge(x, y) else Qt.ArrowCursor)

    def mousePressEvent(self, event):
        if event.button() != Qt.LeftButton:
            return
        pos = event.position()
        hit = self._hit_edge(int(pos.x()), int(pos.y()))
        if hit is not None:
            self._drag = hit
            self.setCursor(Qt.SizeVerCursor)

    def mouseReleaseEvent(self, event):
        if self._drag is None:
            return
        self._drag = None
        self.setCursor(Qt.ArrowCursor)
        # Erst beim Loslassen schreiben — nicht bei jedem Pixel der Bewegung
        self._owner._persist_lyric_sections()
        self._owner._persist_figure_cuts()

    def _apply_drag(self, y: int):
        name, edge = self._drag
        line = self._owner.line_at_viewport_y(y - self._viewport_dy())
        if line is None:
            return
        sections = self._owner._lyric_sections
        rng = sections.get(name)
        if not rng:
            return
        l0, l1 = rng
        # BL-200: Schnitt-Strich verschieben — aendert NICHT die Abschnittsgrenzen
        # (Timing/Anker bleiben), nur die Call-Ende-Zeile im Figuren-Block.
        if edge == "cut":
            new_cut = max(l0 + 1, min(line, l1))  # echt im Block halten
            if self._owner._figure_cuts.get(name) != new_cut:
                self._owner._figure_cuts[name] = new_cut
                self.update()
            return
        if edge == "top":
            l0 = min(line, l1)      # Anfang darf das Ende nicht ueberholen
        else:
            l1 = max(line, l0)
        if (l0, l1) != rng:
            sections[name] = (l0, l1)
            self.update()

    def _figure_at(self, x: int, y: int):
        """Name der Figuren-Spalte unter (x,y), sonst None. Nur Figuren (1..4)
        tragen einen Schnitt-Trenner — Opener/Break/Closer werden ignoriert."""
        for name, rect in self._column_rects():
            if name in self._owner._DYNAMIC_FIGURES and rect.contains(x, y):
                return name
        return None

    def contextMenuEvent(self, event):
        # Der Streifen ist nur im Sync-Modus sichtbar; dort auch das Menue.
        if not self._owner._sync_mode:
            return
        pos = event.pos()
        x, y = int(pos.x()), int(pos.y())
        name = self._figure_at(x, y)
        if name is None:
            return
        dy = self._viewport_dy()
        has_cut = self._figure_cut_overlay_y(name, dy) is not None
        menu = QMenu(self)
        if has_cut:
            act = menu.addAction(_t("ctx_figure_cut_delete"))
        else:
            act = menu.addAction(_t("ctx_figure_cut_add"))
        if menu.exec(event.globalPos()) is not act:
            return
        if has_cut:
            self._owner._suppress_figure_cut(name)
        else:
            line = self._owner.line_at_viewport_y(y - dy)
            self._owner._place_figure_cut(name, line)


class LyricsWidget(QWidget):
    """Lyrics-Anzeige fuer den aktuell geladenen Song.

    Unterstuetzte Formate:
      - HTML/HTM: Nativ ueber QTextBrowser (auch Word-generiertes HTML)
                  Externes CSS (z.B. cuesheet2.css) wird automatisch inlined.
      - RTF:      Konvertierung zu HTML mit Erhalt von Farben/Bold/Italic
      - DOCX:     Reine Anzeige (eigener Mini-Parser -> HTML, Bold/Italic/Farben)
      - PDF:      Reine Anzeige (Textextraktion via pypdf, Lazy-Import)
      - TXT:      Direkte Anzeige

    DOCX und PDF sind reine Anzeige-Formate (BL-146). Bearbeiten geht nicht
    direkt; stattdessen wird beim Edit-Versuch angeboten, eine bearbeitbare
    HTML-Kopie anzulegen (gleicher Migrationspfad wie bei RTF/TXT).

    Nicht unterstuetzt (Platzhalter):
      - DOC, ZIP
    """

    _SUPPORTED_HTML = {".htm", ".html"}
    _SUPPORTED_RTF = {".rtf"}
    _SUPPORTED_TEXT = {".txt"}
    _SUPPORTED_DOCX = {".docx"}
    _SUPPORTED_PDF = {".pdf"}
    # Formate, die nur angezeigt (nicht direkt editiert) werden koennen:
    # Beim Edit-Versuch wird eine HTML-Kopie angeboten (BL-146).
    _DISPLAY_ONLY = {".docx", ".pdf"}

    # Inline-Formatierungs-Tags, die auf Balance geprueft werden (siehe
    # _find_unclosed_inline_tags). Block-Tags (p, div, li, table, ...) werden
    # bewusst NICHT geprueft: Word laesst deren Endtags routinemaessig weg,
    # das ist normal und harmlos. Ein offen gebliebenes Inline-Tag dagegen
    # "leakt" in Qt's Renderer bis zum Dokumentende (z.B. <nobr> -> white-space:
    # nowrap fuer den kompletten Rest des Songs).
    _INLINE_BALANCE_TAGS = frozenset({
        'b', 'i', 'u', 's', 'strike', 'em', 'strong', 'span',
        'font', 'nobr', 'sub', 'sup', 'big', 'small', 'tt', 'a',
    })

    # BL-160: Hintergrundfarbe der Inline-Sync-Marker (nur im Sync-Modus sichtbar)
    _SYNC_MARKER_BG = "#ffd54f"
    _SYNC_MARKER_FG = "#000000"
    # BL-160/161: Wo die Ankerzeile im Viewport landet, wenn ihre Zeit erreicht
    # ist (Anteil von oben). 0.5 = Mitte: aktuelle Zeile zentriert, gleich viel
    # Kontext darueber wie darunter. Per INI ("lyric_sync/viewport_frac")
    # ueberschreibbar (siehe __init__).
    _SYNC_ANCHOR_VIEWPORT_FRAC = 0.3   # intern#76: "Leseposition", INI lyrics/reading_position_pct

    # Manuelles Scrollen (Rad/Ziehen/Tasten) setzt den Auto-Scroll fuer diese
    # Zeitspanne aus, damit man waehrend der Wiedergabe zu einer Zeile blaettern
    # und dort einen Set Point setzen kann. Jedes weitere Scrollen verlaengert
    # das Fenster; danach laeuft der Auto-Scroll von selbst wieder an.
    _MANUAL_SCROLL_PAUSE_SEC = 6.0
    # BL-160: Bei Rueckwaerts-Sprung (z.B. wiederholte Sequenz) Position halten
    # und erst diese Sekunden vor dem Ziel schnell zurueckscrollen — sonst kriecht
    # der Text langsam rueckwaerts und ist nicht lesbar.
    _SYNC_BACK_SNAP_SECONDS = 1.5

    # Standard-CSS fuer Square-Dance-Cuesheets (cuesheet2.css u.a.)
    _CUESHEET_CSS = """
        .title { font-size: 18pt; font-weight: bold; }
        .label { font-size: 12pt; font-style: italic; color: gray; }
        .artist { font-size: 12pt; }
        .hdr, .pointed { font-size: 13pt; font-weight: bold; text-decoration: underline; }
        .lyrics, .pointed { font-style: italic; }
        .comment { font-size: 10pt; color: gray; }
    """

    def __init__(self, paths: PathManager, skin_mgr: SkinManager = None, db=None):
        super().__init__()
        self.paths = paths
        self._skin_mgr = skin_mgr
        self._db = db
        # Aktuell geladener Song (zum Aktualisieren des lyrics_file-Eintrags
        # in der DB, falls beim Bearbeiten von RTF/TXT eine neue HTML-Datei
        # angelegt wird). Wird in load_song() gesetzt.
        self._current_song = None
        # Absoluter Pfad der aktuell angezeigten Lyrics-Datei
        # (None wenn nur Platzhalter sichtbar).
        self._current_path = None
        # Edit-Modus-State
        self._edit_mode = False
        self._dirty = False
        # Format-Toolbar wird lazy in _build_format_toolbar() angelegt
        self._format_toolbar = None
        self._format_toolbar_widget = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(4)

        # Statuszeile (Dateiname oder Hinweis)
        self._label_status = QLabel("\u2014")
        self._label_status.setStyleSheet("font-size: 11px; color: #999;")
        layout.addWidget(self._label_status)

        # --- Toolbar: Auto-Scroll, Auto-Size, Zoom ---
        # _WrapButtonBar: Buttons behalten ihre textabgeleitete (bzw. feste)
        # Breite und brechen in die naechste Zeile um, wenn das Widget schmaler
        # wird als die Zeile vertraegt (gleiches Pattern wie Songliste/Playlist).
        toolbar = _WrapButtonBar()

        self._btn_auto_scroll = QPushButton(_t("btn_auto_scroll"))
        mark_toggle(self._btn_auto_scroll, active=True)
        self._btn_auto_scroll.setChecked(True)
        self._btn_auto_scroll.setToolTip(_t("tooltip_auto_scroll"))
        self._btn_auto_scroll.toggled.connect(self._on_auto_scroll_toggled)
        toolbar.add(self._btn_auto_scroll)

        # BL-160: Sync-Punkte setzen/bearbeiten
        self._btn_sync = QPushButton(_t("btn_lyric_sync"))
        self._btn_sync.setCheckable(True)
        self._btn_sync.setProperty("checkable", "true")
        self._btn_sync.setToolTip(_t("tooltip_lyric_sync"))
        self._btn_sync.toggled.connect(self._on_sync_toggled)
        toolbar.add(self._btn_sync)

        # BL-161: Auto-Sync-Erfassung — nur im Automatik-Modus sichtbar.
        # Der User markiert nur Start (Beginn 1. Teil) und Ende (Ende 7. Teil);
        # CC berechnet daraus die 7 gleich langen Abschnitte.
        self._btn_sync_start = QPushButton(_t("btn_sync_set_start"))
        self._btn_sync_start.setToolTip(_t("tooltip_sync_set_start"))
        self._btn_sync_start.clicked.connect(self._on_auto_set_start)
        self._btn_sync_start.setVisible(False)
        toolbar.add(self._btn_sync_start)

        self._btn_sync_end = QPushButton(_t("btn_sync_set_end"))
        self._btn_sync_end.setToolTip(_t("tooltip_sync_set_end"))
        self._btn_sync_end.clicked.connect(self._on_auto_set_end)
        self._btn_sync_end.setVisible(False)
        toolbar.add(self._btn_sync_end)

        self._label_sync_time = QLabel("0:00")
        self._label_sync_time.setStyleSheet("font-size: 11px; font-weight: bold;")
        self._label_sync_time.setVisible(False)
        toolbar.add(self._label_sync_time)

        self._btn_auto_size = QPushButton(_t("btn_auto_size"))
        mark_toggle(self._btn_auto_size, active=True)
        self._btn_auto_size.setChecked(True)
        self._btn_auto_size.setToolTip(_t("tooltip_auto_size"))
        self._btn_auto_size.toggled.connect(self._on_auto_size_toggled)
        toolbar.add(self._btn_auto_size)

        self._btn_auto_width = QPushButton(_t("btn_auto_width"))
        mark_toggle(self._btn_auto_width, active=True)
        self._btn_auto_width.setToolTip(_t("tooltip_auto_width"))
        self._btn_auto_width.toggled.connect(self._on_auto_width_toggled)
        toolbar.add(self._btn_auto_width)

        # BL-173: Dynamic Lyrics — rechts neben den Auto-Buttons (Auto-Scroll/
        # Auto-Size/Auto-Width), damit der Fluss nicht zerrissen wird. Ersetzt
        # den Figuren-Text temporaer durch die im Sequence-View gewaehlten
        # Sequenzen (Lyric-Datei bleibt unberuehrt).
        self._btn_dynamic = QPushButton(_t("btn_dynamic_lyrics"))
        mark_toggle(self._btn_dynamic, active=True)
        self._btn_dynamic.setToolTip(_t("tooltip_dynamic_lyrics"))
        self._btn_dynamic.toggled.connect(self._on_dynamic_toggled)
        toolbar.add(self._btn_dynamic)

        # intern#127: Spiegel-Button direkt hinter "Dynamic Lyrics" — tauscht
        # Heads/Sides in den Figuren der gewaehlten Art. Ohne gewaehlte Art
        # fuehrt der Klick in die Einstellungen (siehe _on_invert_clicked).
        self._btn_invert = QPushButton()
        self._btn_invert.setFixedSize(28, 28)
        mark_toggle(self._btn_invert, active=True)
        _inv_icon_dir = (skin_mgr.icon_dir.replace("\\", "/")
                         if skin_mgr and skin_mgr.icon_dir else "")
        if _inv_icon_dir:
            self._btn_invert.setIcon(QIcon(f"{_inv_icon_dir}/mirror-hs.svg"))
        else:
            self._btn_invert.setText("⇄")
        self._btn_invert.setToolTip(_t("tooltip_dynamic_invert_choose"))
        self._btn_invert.clicked.connect(self._on_invert_clicked)
        toolbar.add(self._btn_invert)

        # BL-171: Songstart (und damit alle SyncPoints + Ende) um ∓1 s verschieben.
        # Nur im Sync-Modus sichtbar (Toggle in _on_sync_toggled). Rufen dieselbe
        # Logik wie das Kontextmenue "Alle verschieben" (_shift_all_anchors) auf —
        # keine Redundanz. Links neben den Zoom-Buttons.
        self._btn_sync_shift_earlier = QPushButton(_t("btn_sync_shift_earlier"))
        self._btn_sync_shift_earlier.setToolTip(_t("tooltip_sync_shift_earlier"))
        self._btn_sync_shift_earlier.clicked.connect(
            lambda: self._shift_all_anchors(-1.0))
        self._btn_sync_shift_earlier.setVisible(False)
        toolbar.add(self._btn_sync_shift_earlier)

        self._btn_sync_shift_later = QPushButton(_t("btn_sync_shift_later"))
        self._btn_sync_shift_later.setToolTip(_t("tooltip_sync_shift_later"))
        self._btn_sync_shift_later.clicked.connect(
            lambda: self._shift_all_anchors(1.0))
        self._btn_sync_shift_later.setVisible(False)
        toolbar.add(self._btn_sync_shift_later)

        # Skin-Pfad fuer SVG-Icons
        skin_dir = ""
        if skin_mgr and skin_mgr.icon_dir:
            skin_dir = skin_mgr.icon_dir.replace("\\", "/")

        self._btn_zoom_out = QPushButton()
        self._btn_zoom_out.setFixedSize(28, 28)
        self._btn_zoom_out.setToolTip(_t("tooltip_zoom_out"))
        if skin_dir:
            self._btn_zoom_out.setIcon(QIcon(f"{skin_dir}/zoom-out.svg"))
        else:
            self._btn_zoom_out.setText("\u2212")
        self._btn_zoom_out.clicked.connect(self._on_zoom_out)
        toolbar.add(self._btn_zoom_out)

        self._label_zoom = QLabel("100%")
        self._label_zoom.setAlignment(Qt.AlignCenter)
        self._label_zoom.setFixedWidth(44)
        self._label_zoom.setStyleSheet("font-size: 11px;")
        toolbar.add(self._label_zoom)

        self._btn_zoom_in = QPushButton()
        self._btn_zoom_in.setFixedSize(28, 28)
        self._btn_zoom_in.setToolTip(_t("tooltip_zoom_in"))
        if skin_dir:
            self._btn_zoom_in.setIcon(QIcon(f"{skin_dir}/zoom-in.svg"))
        else:
            self._btn_zoom_in.setText("+")
        self._btn_zoom_in.clicked.connect(self._on_zoom_in)
        toolbar.add(self._btn_zoom_in)

        # Edit-Button (Stift): schaltet Read- ↔ Edit-Modus um.
        # Im Edit-Modus wird daraus ein Speichern-Button (Diskette).
        self._btn_edit = QPushButton()
        self._btn_edit.setFixedSize(28, 28)
        self._btn_edit.setCheckable(True)
        self._btn_edit.setProperty("checkable", "true")
        self._btn_edit.setToolTip(_t("tooltip_lyrics_edit"))
        if skin_dir:
            self._btn_edit.setIcon(QIcon(f"{skin_dir}/pencil.svg"))
        else:
            self._btn_edit.setText("✎")  # Fallback ohne SVG
        self._btn_edit.toggled.connect(self._on_edit_toggled)
        toolbar.add(self._btn_edit)

        layout.addWidget(toolbar)

        # Text-Browser (Read-only, HTML + Plaintext)
        # Lyrics-Widget ignoriert Theme-Farben: immer weisser Hintergrund,
        # Dateien werden 1:1 original dargestellt (wie im Browser/Word).
        self._browser = QTextBrowser()
        self._browser.setOpenExternalLinks(False)
        self._browser.setReadOnly(True)
        self._browser.setStyleSheet("QTextBrowser { background-color: white; }")
        # BL-166: STRG + Mausrad zoomt wie die +/- Buttons. Der Filter
        # verbraucht das Event, damit nicht zusaetzlich der eingebaute
        # QTextBrowser-Zoom greift.
        install_ctrl_wheel_zoom(self._browser, self._on_zoom_in, self._on_zoom_out)

        # BL-171: Abschnitts-Overlay. {name: (start_line, end_line)} auf dem
        # Plain-Text — Zeilen, nicht Qt-Bloecke: manche Lyrics (RTF mit <br>)
        # sind EIN Block mit vielen Zeilen, Block-Indizes taugen daher nicht.
        self._lyric_sections: dict = {}
        # BL-200: manuell verschobene Schnitt-Zeile je Figur (figureN -> abs. Zeile).
        # Nur User-Overrides; fehlt ein Eintrag, gilt der Algorithmus-Default.
        self._figure_cuts: dict = {}
        self._line_offsets: list = []   # Zeile -> Zeichenposition (pristine)
        self._section_overlay = _LyricSectionOverlay(self)
        self._browser.verticalScrollBar().valueChanged.connect(
            lambda _v: self._section_overlay.update())
        # intern#76: Lesebalken. _band_doc_y = Dokument-Y des gesungenen Texts
        # (None = nichts anzeigen); Werte aus der INI (reload_reading_settings).
        self._band_doc_y = None
        self._last_dur = 0.0              # zuletzt gesehene Songdauer (Neuaufbau)
        self._interp_snapping = False     # letzte Interpolation im Ruecksprung?
        self._heading_kw = None           # Keyword-Woerter (lazy, singing_sections)
        self._reading_band_enabled = True
        self._reading_band_height_pct = 20
        self._reading_band_opacity_pct = 30
        self._reading_band = _ReadingBandOverlay(self)
        self._browser.verticalScrollBar().valueChanged.connect(
            lambda _v: self._reading_band.update())
        # Manuelles Scrollen erkennen: actionTriggered feuert bei Rad/Ziehen/
        # Tasten, aber NICHT bei unserem programmatischen setValue() — damit
        # entsteht keine Rueckkopplung mit dem Auto-Scroll.
        self._browser.verticalScrollBar().actionTriggered.connect(
            self._on_manual_scroll)

        # Default-StyleSheet: schwarzer Text auf weiss (Fallback fuer
        # Elemente ohne eigene Farbangabe). Theme-unabhaengig.
        self._update_default_stylesheet()

        # State fuer Auto-Fit / Auto-Scroll
        self._auto_scroll_enabled = True  # User-Toggle fuer Auto-Scroll
        self._auto_size_enabled = True    # User-Toggle fuer Auto-Size
        self._auto_width_enabled = False  # User-Toggle fuer Auto-Width (exklusiv mit Auto-Size)
        self._auto_scroll_active = False  # True wenn Lyrics laenger als Viewport
        self._base_font_size = 13        # Standard-Schriftgroesse
        self._current_font_size = 13     # Aktuelle (evtl. skalierte) Groesse
        self._lyrics_loaded = False       # Ob gerade Lyrics geladen sind
        self._refit_conn = None           # Aktive documentSizeChanged-Verbindung fuer Refit-nach-Load
        # Cache der Original-Schriftgroessen pro Fragment.
        # Liste von (position, length, original_pt). Wird nach jedem Laden
        # neu aufgebaut. Damit Zoom/Auto-Width auch dann funktionieren, wenn
        # die HTML-Datei Inline-font-size auf jedem Span hat (Qt's toHtml()
        # tut das standardmaessig) — Inline-Sizes ueberschreiben den Default-
        # Font, also muessen wir sie selbst skalieren.
        self._original_sizes = []

        # --- BL-160: Lyrics-Sync-Punkte ---
        # Sync-Punkte koppeln eine Songzeit (Sekunde) fest an eine Textzeile
        # (Block-Index). Zwischen den Ankern interpoliert der Auto-Scroll
        # stueckweise linear statt stumpf linear ueber den ganzen Song.
        # Identitaet pro (Musik-Variante x Lyric-Variante) — wird vom
        # Hauptfenster ueber set_sync_identity() gesetzt.
        self._sync_mode = False           # True = Anker setzen/bearbeiten
        self._sync_anchors = []           # Liste von [sekunde, block] (Cache)
        self._sync_song_id = None
        self._sync_music_slot = 1         # 1 = Primaer, 2+ = Variante
        self._sync_lyric_slot = 1
        self._sync_last_pos = 0.0         # zuletzt gesehene Wiedergabeposition (Sek.)
        # intern#115: Timing-Parameter in ganzen Sekunden, negativ = frueher
        self._text_jump_offset = 0        # Auto-Scroll erreicht SyncPoints verschoben
        self._dynamic_swap_offset = 0     # Figuren-Grenzen von Dynamic Lyrics verschoben
        self._scroll_last_val = -1        # letzter gesetzter Scroll-Wert (Anti-Jitter)
        self._manual_scroll_until = 0.0   # bis hierhin Auto-Scroll aussetzen (monotonic)
        self._sync_move_anchor = None     # gesetzter Anker, der per Klick verschoben wird
        # Text-Stand vor einem In-App-Edit (nur waehrend des Edit-Modus
        # gesetzt), um Sync-Anker nach dem Speichern per Diff nachzufuehren.
        self._pre_edit_text = None
        # Aktuell im Dokument eingefuegte Marker als (pristine_pos, laenge).
        # Noetig, um zwischen pristine-Textpositionen (Anker) und der durch
        # Marker verschobenen Anzeige umzurechnen.
        self._marker_inserts = []
        # Callback → MainWindow schaltet im Sync-Modus Rules + History-Logging ab
        # (gleicher Mechanismus wie Audition/Loop-Finder). Signatur: (active: bool)
        self.on_sync_mode_changed = None
        # Callback → MainWindow startet die automatische Body-Erkennung (Worker).
        # Ergebnis kommt asynchron via apply_detected_body() zurueck.
        self.on_request_body_detect = None
        # Callback → MainWindow, wenn singing_start/-end neu gesetzt wurde
        # (invalidiert u.a. den Start-Countdown-Cache).
        self.on_singing_marks_changed = None

        # --- BL-173: Dynamic Lyrics ---
        # Ersetzt zur Laufzeit den Text der Figuren-Abschnitte (figure1..4) durch
        # die AKTUELL im Sequence-View gezeigte Sequenz. Das Sequence-View ist die
        # Quelle der Wahrheit: bei Option 2 blaettert Callers Caddy dort an jeder
        # Figuren-Teil-Grenze weiter, und das Lyric-Feld spiegelt, was dort steht
        # (dieselbe Schnittstelle traegt spaeter das Nutzer-Blaettern). Die
        # Lyric-Datei bleibt unberuehrt; SyncPoints werden nachgefuehrt.
        self._dynamic_enabled = False
        self._dynamic_document = None      # getauschtes QTextDocument (Ref halten)
        self._dynamic_anchors = None       # nachgefuehrte Anker fuers Auto-Scroll
        self._pre_dynamic = None           # Snapshot fuer sauberes Zuruecksetzen
        self._dyn_part_starts = []         # Startzeit je Figuren-Teil (Sek., sortiert)
        self._dyn_block_keys = []          # eindeutige Figuren-Bloecke (Original-Zeilen)
        self._dyn_rendered_part = 0        # bis zu welchem Figuren-Teil auto-geblaettert
        self._dyn_factor = 1.0             # Zoom-Faktor zum Zeitpunkt des Einschaltens
        self._dyn_render_pending = False   # deferter Re-Render eingeplant
        self._dyn_advance_pending = False  # defertes Weiterblaettern eingeplant
        self._dynamic_wanted = False       # Wunschzustand, ueberlebt Songwechsel
        # intern#127: Heads/Sides invertieren (INI lyrics/dynamic_invert_*)
        self._invert_enabled = False
        self._invert_mode = ""             # "" = noch keine Art gewaehlt
        self._dyn_block_figs = []          # je Block (wie _dyn_block_keys): Figur-Nummern
        self._dyn_invert_state = ()        # je Block: zuletzt invertiert gerendert?
        # Callback(full_key) -> Einstellungen an dieser Zeile oeffnen (MainWindow)
        self.open_settings_at = None
        # Modus ("1"/"2") wird lazy aus der App-INI gelesen — NICHT aus einem
        # bare QSettings(), das auf einen anderen Store zeigen wuerde (intern#136).
        # Leer = beim ersten Einschalten fragen.
        self._settings = paths.settings
        self._dynamic_mode = ""
        # Schnittstelle zum Sequence-View (Quelle der Wahrheit):
        self.get_current_sequence_calls = None  # () -> list[str] der aktuellen Sequenz
        self.advance_sequence_view = None        # () -> im Sequence-View weiterblaettern
        self.randomize_start_sequence_view = None  # BL-182: () -> beim Dynamic-Start zufaellige erste Sequenz (falls Shuffle an)

        # --- BL-161: Automatik-Erfassung (2 Klicks → 7 Abschnitte) ---
        self._auto_calc_active = False    # True = Start/Ende werden gerade erfasst
        self._auto_start_sec = None       # markierter Beginn 1. Teil (Sek.)
        self._auto_end_sec = None         # markiertes Ende 7. Teil (Sek.)
        # intern#76: Leseposition und Lesebalken aus der INI ([lyrics])
        self.reload_reading_settings()

        # --- Format-Toolbar (nur im Edit-Modus sichtbar) ---
        self._format_toolbar_widget = self._build_format_toolbar()
        self._format_toolbar_widget.setVisible(False)
        layout.addWidget(self._format_toolbar_widget)

        # Text + Abschnittsstreifen nebeneinander. Der Streifen liegt bewusst
        # NEBEN dem Text, nicht darueber: als Overlay landeten Klicks auf einer
        # Abschnittskante im Text darunter und legten dort einen Sync-Punkt an.
        text_row = QHBoxLayout()
        text_row.setContentsMargins(0, 0, 0, 0)
        text_row.setSpacing(2)
        text_row.addWidget(self._browser, 1)
        text_row.addWidget(self._section_overlay, 0)
        layout.addLayout(text_row, 1)

        # Doppelklick auf den Text aktiviert Edit-Modus
        self._browser.viewport().installEventFilter(self)

        # Signale fuer den Edit-Modus EINMAL verbinden (keine
        # disconnect-Tanzerei — _update_format_buttons und _on_doc_changed
        # pruefen self._edit_mode und arbeiten im Read-Modus als No-Op).
        self._browser.currentCharFormatChanged.connect(self._update_format_buttons)
        self._browser.document().contentsChanged.connect(self._on_doc_changed)

        # Strg+S / Esc als Shortcuts (greifen nur im Edit-Modus)
        self._sc_save = QShortcut(QKeySequence("Ctrl+S"), self)
        self._sc_save.setContext(Qt.WidgetWithChildrenShortcut)
        self._sc_save.activated.connect(self._shortcut_save)
        self._sc_cancel = QShortcut(QKeySequence("Esc"), self)
        self._sc_cancel.setContext(Qt.WidgetWithChildrenShortcut)
        self._sc_cancel.activated.connect(self._shortcut_cancel)

    def load_song(self, song):
        """Laedt die Lyrics-Datei fuer den uebergebenen Song.

        Args:
            song: Song-Objekt mit lyrics_file-Attribut
        """
        # Falls aktuell editiert wird: fragen, ob verworfen werden soll
        if self._edit_mode and not self._confirm_discard():
            return
        if self._edit_mode:
            self._leave_edit_mode_silent()
        self._current_song = song
        if not song or not song.lyrics_file:
            self._current_path = None
            self._show_placeholder(_t("lyrics_no_lyrics"))
            return

        full_path = self.paths.find_lyric_file(song.lyrics_file)
        if not full_path:
            self._current_path = None
            self._show_placeholder(
                _t("lyrics_file_not_found", filename=song.lyrics_file)
            )
            return

        self._current_path = full_path
        self._load_file(full_path, song.lyrics_file)

    def load_by_filename(self, filename: str):
        """Laedt eine Lyrics-Datei direkt anhand des Dateinamens (fuer Varianten)."""
        if self._edit_mode and not self._confirm_discard():
            return
        if self._edit_mode:
            self._leave_edit_mode_silent()
        if not filename:
            self._current_path = None
            self._show_placeholder(_t("lyrics_no_lyrics"))
            return
        full_path = self.paths.find_lyric_file(filename)
        if not full_path:
            self._current_path = None
            self._show_placeholder(_t("lyrics_file_not_found", filename=filename))
            return
        self._current_path = full_path
        self._load_file(full_path, filename)

    def _load_file(self, path: str, filename: str):
        """Laedt eine Lyrics-Datei anhand der Dateiendung."""
        # BL-173: Beim Datei-/Songwechsel Dynamic Lyrics sauber verlassen. revert
        # stellt (falls aktiv) das Original-Dokument wieder her und gibt es dem
        # Editor zurueck, sodass es beim gleich folgenden setHtml regulaer
        # aufgeraeumt wird (kein haengendes Dokument). Danach Button/Modus-Buttons
        # in den Ausgangszustand.
        self._revert_dynamic()
        if hasattr(self, "_btn_dynamic"):
            # Button-Haken nur loeschen, wenn Dynamic NICHT gewuenscht ist. Bei
            # gewuenschtem Dynamic bleibt er gesetzt und wird nach dem Laden
            # (set_sync_identity → _reapply_dynamic_if_wanted) neu angewandt.
            if not self._dynamic_wanted:
                self._btn_dynamic.blockSignals(True)
                self._btn_dynamic.setChecked(False)
                self._btn_dynamic.blockSignals(False)
            self._btn_sync.setEnabled(True)
            self._btn_edit.setEnabled(True)
        # Neues Dokument → evtl. getrackte Marker-Spans des alten Docs verwerfen
        # (nicht entfernen — das alte Dokument existiert nicht mehr).
        self._marker_inserts = []
        self._scroll_last_val = -1
        self._band_doc_y = None   # intern#76: Lesebalken erst mit neuer Position
        # BL-173: Position zuruecksetzen, damit ein Auto-Re-Apply von Dynamic
        # nicht vom alten Song-Ende ausgeht (sonst kurzer Sequenz-Fehlstand).
        self._sync_last_pos = 0.0
        ext = os.path.splitext(filename)[1].lower()

        if ext in self._SUPPORTED_HTML:
            self._load_html(path, filename)
        elif ext in self._SUPPORTED_RTF:
            self._load_rtf(path, filename)
        elif ext in self._SUPPORTED_DOCX:
            self._load_docx(path, filename)
        elif ext in self._SUPPORTED_PDF:
            self._load_pdf(path, filename)
        elif ext in self._SUPPORTED_TEXT:
            self._load_text(path, filename)
        else:
            self._show_placeholder(
                _t("lyrics_format_unsupported", ext=ext, filename=filename)
            )

    @staticmethod
    def _read_file(path: str) -> str:
        """Liest eine Datei mit UTF-8/CP1252-Fallback."""
        try:
            with open(path, "r", encoding="utf-8") as f:
                return f.read()
        except UnicodeDecodeError:
            with open(path, "r", encoding="cp1252") as f:
                return f.read()

    # --- Kontrast-Hilfsfunktionen ---

    # Benannte CSS-Farben → RGB (haeufigste)
    _NAMED_COLORS = {
        "black": (0, 0, 0), "white": (255, 255, 255),
        "red": (255, 0, 0), "green": (0, 128, 0), "blue": (0, 0, 255),
        "yellow": (255, 255, 0), "lime": (0, 255, 0), "cyan": (0, 255, 255),
        "magenta": (255, 0, 255), "silver": (192, 192, 192), "gray": (128, 128, 128),
        "grey": (128, 128, 128), "maroon": (128, 0, 0), "olive": (128, 128, 0),
        "navy": (0, 0, 128), "purple": (128, 0, 128), "teal": (0, 128, 128),
        "orange": (255, 165, 0), "brown": (165, 42, 42), "pink": (255, 192, 203),
        "gold": (255, 215, 0), "coral": (255, 127, 80), "aqua": (0, 255, 255),
        "fuchsia": (255, 0, 255), "windowtext": (0, 0, 0),
    }

    @staticmethod
    def _parse_color(color_str: str):
        """Parst CSS-Farbwert zu (r, g, b) oder None."""
        s = color_str.strip().rstrip(';').strip().lower()
        # Benannte Farben
        if s in LyricsWidget._NAMED_COLORS:
            return LyricsWidget._NAMED_COLORS[s]
        # #RGB
        if re.match(r'^#[0-9a-f]{3}$', s):
            return (int(s[1]*2, 16), int(s[2]*2, 16), int(s[3]*2, 16))
        # #RRGGBB
        if re.match(r'^#[0-9a-f]{6}$', s):
            return (int(s[1:3], 16), int(s[3:5], 16), int(s[5:7], 16))
        # rgb(r, g, b)
        m = re.match(r'^rgb\s*\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*\)$', s)
        if m:
            return (int(m.group(1)), int(m.group(2)), int(m.group(3)))
        return None

    @staticmethod
    def _luminance(r, g, b):
        """Relative Luminanz nach WCAG (0.0 = schwarz, 1.0 = weiss)."""
        def _lin(c):
            c = c / 255.0
            return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
        return 0.2126 * _lin(r) + 0.7152 * _lin(g) + 0.0722 * _lin(b)

    @staticmethod
    def _contrast_ratio(lum1, lum2):
        """WCAG-Kontrastverhaltnis (1.0 = kein Kontrast, 21.0 = max)."""
        lighter = max(lum1, lum2)
        darker = min(lum1, lum2)
        return (lighter + 0.05) / (darker + 0.05)

    def _update_default_stylesheet(self):
        """Setzt body-Defaults: schwarz auf weiss (Theme-unabhaengig).

        Lyrics werden immer original dargestellt. Elemente ohne eigene
        Farbangabe erhalten schwarzen Text auf weissem Hintergrund —
        wie ein Browser es anzeigen wuerde.
        """
        # h1-h6 "medium": Qt vergroessert Ueberschriften sonst fest (h1 = 2x)
        # und uebergeht dabei jede Groessenangabe der Datei (intern#152).
        self._browser.document().setDefaultStyleSheet(
            "body { color: #000000; background-color: white; }"
            " h1, h2, h3, h4, h5, h6 { font-size: medium; }"
        )

    @staticmethod
    def _unwrap_style_comments(html: str) -> str:
        """Entfernt die Kommentar-Klammern <!-- --> in <style>-Bloecken.

        Word schreibt sein Stylesheet als <style><!-- ... --></style>. Browser
        ignorieren diese Klammern, Qt verwirft dagegen das GANZE Stylesheet —
        dann fehlen z.B. Groesse, Schrift und Farbe der Ueberschriften
        (intern#152).
        """
        def _unwrap(m):
            css = m.group(2).replace("<!--", "").replace("-->", "")
            return f"{m.group(1)}{css}</style>"
        return re.sub(r'(?si)(<style[^>]*>)(.*?)</style>', _unwrap, html)

    @classmethod
    def _sanitize_html(cls, html: str, lyrics_dir: str = None) -> str:
        """Bereinigt HTML fuer die Anzeige im Lyrics-Widget.

        Klassenmethode, weil der Bulk-Sync-Lauf (lyric_plain_text) exakt
        dieselbe Aufbereitung ohne Widget-Instanz braucht — sonst weichen die
        Zeichenpositionen der Sync-Anker von der Anzeige ab.

        Strategie (As-Is-Rendering):
          - Externe CSS-Links auflösen oder durch Defaults ersetzen
          - font-size entfernen (Auto-Fit uebernimmt die Skalierung)
          - Alle Farben (color, background-color, bgcolor) bleiben ORIGINAL
          - Keine Theme-Anpassung, keine WCAG-Kontrast-Pruefung
          - Hintergrund ist immer weiss → Dateien sehen aus wie im Browser/Word
        """
        # 0) Words <!-- --> um das Stylesheet loesen, sonst ignoriert Qt es
        #    komplett (Farben/Schriften der Ueberschriften fehlen, intern#152)
        html = cls._unwrap_style_comments(html)

        # 1) Externe <link>-CSS auflösen → inline <style>
        def _resolve_link(m):
            href = m.group(1) or m.group(2) or m.group(3)
            if not href:
                return ""
            css_content = None
            if lyrics_dir:
                css_path = os.path.join(lyrics_dir, href)
                if os.path.isfile(css_path):
                    try:
                        with open(css_path, "r", encoding="utf-8") as f:
                            css_content = f.read()
                    except Exception:
                        pass
            if css_content is None and "cuesheet" in href.lower():
                css_content = cls._CUESHEET_CSS
            if css_content:
                return f"<style>{css_content}</style>"
            return ""

        html = re.sub(
            r'''(?i)<link[^>]+href\s*=\s*(?:"([^"]*)"|'([^']*)'|(\S+))[^>]*>''',
            _resolve_link, html
        )

        # 2) font-size NUR aus zentralen <style>-Bloecken entfernen
        #    (z.B. "body { font-size: 12pt; }") — damit Auto-Fit die
        #    Basis-Schrift selbst bestimmen kann.
        #    Inline-Overrides auf <span>/<font>-Elementen bleiben ERHALTEN,
        #    damit per-Wort-Hervorhebungen (z.B. ein groesseres Wort fuer
        #    Betonung im Lyric) sichtbar bleiben. Auto-Fit skaliert dann die
        #    Default-Schrift, die Inline-Groessen behalten ihre relative
        #    Differenz dazu.
        _RE_FONT_SIZE = r'(?i)(?<![a-zA-Z-])font-size\s*:\s*[^;}"\'>\s]+[^;}"\'>;]*;?'

        def _strip_font_size_in_style(m):
            css = m.group(1)
            css = re.sub(_RE_FONT_SIZE, '', css)
            return f'<style>{css}</style>'

        html = re.sub(r'(?si)<style[^>]*>(.*?)</style>', _strip_font_size_in_style, html)

        return html

    @classmethod
    def _find_unclosed_inline_tags(cls, html_text: str) -> list:
        """Findet Inline-Formatierungs-Tags (siehe _INLINE_BALANCE_TAGS), die bis
        Dokumentende offen bleiben - typischerweise ein Fehler in fehlerhaft
        exportiertem Word-HTML (z.B. ein <nobr> ohne </nobr>).

        Toleranter Stack-Abgleich: ein Endtag schliesst das zugehoerige Tag
        UND alle darueber liegenden (wie ein Browser das bei ueberlappenden
        Tags tut) - nur was bis EOF nirgends geschlossen wurde, gilt als Fehler.

        Rueckgabe: Liste von (tagname, insert_offset). insert_offset ist die
        Position direkt hinter dem oeffnenden Tag im Original-String - dort
        muss ein schliessendes Tag eingefuegt werden, um den Fehler zu
        neutralisieren.
        """
        import html.parser as _hp

        tags_ok = cls._INLINE_BALANCE_TAGS

        class _Checker(_hp.HTMLParser):
            def __init__(self):
                super().__init__(convert_charrefs=True)
                self.stack = []
                self.cursor = 0

            def handle_starttag(self, tag, attrs):
                if tag not in tags_ok:
                    return
                raw = self.get_starttag_text() or f"<{tag}>"
                pos = html_text.find(raw, self.cursor)
                if pos < 0:
                    pos = self.cursor
                end = pos + len(raw)
                self.cursor = end
                self.stack.append((tag, end))

            def handle_startendtag(self, tag, attrs):
                pass  # selbstschliessend (z.B. <br/>) - keine Stack-Wirkung

            def handle_endtag(self, tag):
                if tag not in tags_ok:
                    return
                for i in range(len(self.stack) - 1, -1, -1):
                    if self.stack[i][0] == tag:
                        del self.stack[i:]
                        return

        checker = _Checker()
        try:
            checker.feed(html_text)
            checker.close()
        except Exception:
            return []
        return checker.stack

    @staticmethod
    def _fix_unclosed_inline_tags(html_text: str, issues: list) -> str:
        """Schliesst jedes verwaiste Tag direkt nach seinem Start. Neutralisiert
        die Formatierung damit komplett, statt einen vermuteten urspruenglichen
        Endpunkt zu raten - sicherer als eine Position im Text zu erraten."""
        for tag, offset in sorted(issues, key=lambda t: t[1], reverse=True):
            html_text = html_text[:offset] + f"</{tag}>" + html_text[offset:]
        return html_text

    def _check_and_offer_html_fix(self, html_text: str, path: str) -> str:
        """Prueft auf nicht geschlossene Inline-Tags und bietet an, die
        Quelldatei dauerhaft zu reparieren (nur fuer echte HTML-Dateien
        sinnvoll, siehe Aufrufer). Bei 'Ignorieren' wird nur fuer diese
        Anzeige nichts veraendert - die Datei bleibt defekt."""
        issues = self._find_unclosed_inline_tags(html_text)
        if not issues:
            return html_text
        tags = ", ".join(sorted({t for t, _ in issues}))
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Warning)
        box.setWindowTitle(_t("lyrics_html_broken_title"))
        box.setText(_t("lyrics_html_broken_text", tags=tags))
        b_fix = box.addButton(_t("lyrics_html_fix_now"), QMessageBox.AcceptRole)
        box.addButton(_t("lyrics_html_fix_ignore"), QMessageBox.RejectRole)
        box.setDefaultButton(b_fix)
        box.exec()
        if box.clickedButton() is not b_fix:
            return html_text
        fixed = self._fix_unclosed_inline_tags(html_text, issues)
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(fixed)
        except Exception as e:
            print(f"[Lyrics] Reparatur konnte nicht gespeichert werden: {e}")
        return fixed

    def _load_html(self, path: str, filename: str):
        """Laedt HTML/HTM-Lyrics in den Browser."""
        content = self._read_file(path)
        lyrics_dir = os.path.dirname(path)
        content = self._sanitize_html(content, lyrics_dir=lyrics_dir)
        # Echte HTML-Quelldatei: bei defekten Inline-Tags (z.B. verwaistes
        # <nobr> aus fehlerhaftem Word-Export) fragen und die Datei auf
        # Wunsch dauerhaft reparieren (siehe _check_and_offer_html_fix).
        content = self._check_and_offer_html_fix(content, path)
        self._update_default_stylesheet()
        self._browser.setHtml(content)
        self._cache_original_sizes()  # nach setHtml, vor Refit
        self._label_status.setText(filename)
        self._lyrics_loaded = True
        self._schedule_refit_after_load()

    def _load_rtf(self, path: str, filename: str):
        """Laedt RTF: Qt-Primaerpfad, eigener Konverter als Fallback.

        Qt kann viele RTFs nativ parsen (inkl. highlight, background etc.).
        Wenn Qt versagt, greift _rtf_to_html als Fallback (Farben, Bold, Italic).
        In beiden Faellen laeuft das Ergebnis durch _sanitize_html.
        """
        content = self._read_file(path)
        # Word-spezifische Binaer-Bloecke entfernen (z.B. {\*\datastore ...})
        # Diese enthalten Hex-Dumps die Qt als sichtbaren Text rendert
        content = self._strip_rtf_binary_groups(content)
        # 1) Qt-Primaerpfad: QTextDocument kann viele RTFs direkt laden
        doc = QTextDocument()
        doc.setHtml("")  # Reset
        doc.setHtml(content)  # Qt erkennt RTF am {\rtf Header
        qt_worked = (not doc.isEmpty()
                     and not doc.toPlainText().strip().startswith("{\\rtf"))
        if qt_worked:
            # Qt hat RTF erkannt → HTML extrahieren und sanitizen
            html = doc.toHtml()
        else:
            # 2) Fallback: eigener RTF→HTML-Konverter
            html = self._rtf_to_html(content)
        html = self._sanitize_html(html)
        # HTML ist hier nur eine abgeleitete Darstellung (nicht die Quelldatei
        # selbst) - defekte Inline-Tags still neutralisieren statt zu fragen,
        # es gibt nichts Persistentes zu reparieren.
        issues = self._find_unclosed_inline_tags(html)
        if issues:
            html = self._fix_unclosed_inline_tags(html, issues)
        self._update_default_stylesheet()
        self._browser.setHtml(html)
        self._cache_original_sizes()
        self._label_status.setText(filename)
        self._lyrics_loaded = True
        self._schedule_refit_after_load()

    @staticmethod
    def _strip_rtf_binary_groups(rtf: str) -> str:
        """Entfernt optionale RTF-Gruppen die Qt nicht versteht.

        In RTF bedeutet {\\*\\keyword ...} "ignorable destination" —
        der Parser DARF diese Gruppe ueberspringen. Word fuegt viele
        solcher Gruppen ein (themedata, datastore, colorschememapping,
        xmlnstbl, latentstyles etc.) die Hex-Dumps oder XML enthalten.
        Qt rendert deren Inhalt faelschlich als sichtbaren Text.

        Whitelist-Ansatz: Nur bekannte, fuer Lyrics relevante {\\*\\...}
        Gruppen werden behalten. Alles andere wird entfernt.
        """
        # Diese {\*\...} Gruppen werden BEHALTEN (fuer Lyrics relevant)
        _keep = {'\\fonttbl', '\\colortbl', '\\stylesheet', '\\info',
                 '\\generator', '\\falt', '\\panose', '\\cs',
                 '\\pnseclvl', '\\background', '\\shpinst',
                 '\\listtable', '\\listoverridetable', '\\company',
                 '\\defchp', '\\defpap', '\\ud'}
        result = []
        i = 0
        while i < len(rtf):
            if rtf[i] == '{' and i + 2 < len(rtf) and rtf[i + 1:i + 3] == '\\*':
                # {\*\keyword ...} gefunden — Keyword extrahieren
                look = rtf[i + 3:i + 40]
                # Keyword beginnt mit \ gefolgt von Buchstaben
                if look.startswith('\\'):
                    kw_end = 1
                    while kw_end < len(look) and look[kw_end].isalpha():
                        kw_end += 1
                    kw = look[:kw_end]  # z.B. '\datastore'
                    if kw not in _keep:
                        # Ganze Gruppe ueberspringen (inkl. verschachtelte {})
                        depth = 1
                        i += 1
                        while i < len(rtf) and depth > 0:
                            if rtf[i] == '{': depth += 1
                            elif rtf[i] == '}': depth -= 1
                            i += 1
                        continue
            result.append(rtf[i])
            i += 1
        return ''.join(result)

    @staticmethod
    def _rtf_to_html(rtf: str) -> str:
        """Minimaler RTF→HTML-Konverter fuer Lyrics.

        Erzeugt HTML mit Original-Farben als inline color:rgb()-Styles.
        Die Kontrast-Anpassung uebernimmt _sanitize_html (WCAG-basiert).

        Unterstuetzt: colortbl, bold, italic, underline, par, qc/ql/qr,
                      Hex-Escapes, Unicode, Sonderzeichen.
        """
        # --- 1) Colortable extrahieren ---
        colors = [(0, 0, 0)]  # Index 0 = auto/schwarz
        ct_match = re.search(r'\{\\colortbl\s*;?(.*?)\}', rtf, re.DOTALL)
        if ct_match:
            for entry in ct_match.group(1).split(';'):
                entry = entry.strip()
                if not entry:
                    colors.append((0, 0, 0))
                    continue
                r = g = b = 0
                rm = re.search(r'\\red(\d+)', entry)
                gm = re.search(r'\\green(\d+)', entry)
                bm = re.search(r'\\blue(\d+)', entry)
                if rm: r = int(rm.group(1))
                if gm: g = int(gm.group(1))
                if bm: b = int(bm.group(1))
                colors.append((r, g, b))

        # --- 2) Body extrahieren (Header-Gruppen ueberspringen) ---
        body = rtf
        # Aeussere {\rtf1...} Klammer entfernen
        if body.startswith('{\\rtf'):
            first_space = body.index(' ') if ' ' in body[:20] else 5
            body = body[first_space + 1:]
            if body.endswith('}'):
                body = body[:-1]

        # Bekannte Header-Gruppen entfernen (fonttbl, colortbl, stylesheet, info etc.)
        skip_kw = ('\\fonttbl', '\\colortbl', '\\stylesheet', '\\info',
                    '\\*\\generator', '\\*\\pnseclvl', '\\*\\panose',
                    '\\*\\falt', '\\*\\cs', '\\*\\background', '\\*\\shpinst',
                    '\\*\\listtable', '\\*\\listoverridetable', '\\*\\company')

        def _skip_groups(text):
            result = []
            i = 0
            while i < len(text):
                if text[i] == '{':
                    look = text[i + 1:i + 31]
                    if any(look.startswith(kw) for kw in skip_kw):
                        depth = 1
                        i += 1
                        while i < len(text) and depth > 0:
                            if text[i] == '{': depth += 1
                            elif text[i] == '}': depth -= 1
                            i += 1
                        continue
                result.append(text[i])
                i += 1
            return ''.join(result)

        body = _skip_groups(body)

        # --- 3) Tokenizer: RTF → HTML ---
        parts = ['<html><body>']
        bold = italic = underline = False
        color_idx = 0
        highlight_idx = 0  # \highlight → Hintergrundfarbe
        alignment = 'left'
        in_para = False
        text_buf = []
        style_stack = []

        def _open_para():
            nonlocal in_para
            if not in_para:
                align = f' style="text-align:{alignment};"' if alignment != 'left' else ''
                parts.append(f'<p{align}>')
                in_para = True

        def _close_para():
            nonlocal in_para
            if in_para:
                parts.append('</p>')
                in_para = False

        def _flush_text():
            nonlocal text_buf
            if not text_buf:
                return
            _open_para()
            txt = ''.join(text_buf)
            text_buf = []
            # HTML-Escape
            txt = txt.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
            # Inline-Style: Farbe + Highlight (font-size macht Auto-Fit)
            styles = []
            if color_idx > 0 and color_idx < len(colors):
                r, g, b = colors[color_idx]
                styles.append(f'color:rgb({r},{g},{b})')
            if highlight_idx > 0 and highlight_idx < len(colors):
                r, g, b = colors[highlight_idx]
                styles.append(f'background-color:rgb({r},{g},{b})')
            # Tags
            open_t, close_t = '', ''
            if bold:   open_t += '<b>';  close_t = '</b>' + close_t
            if italic: open_t += '<i>';  close_t = '</i>' + close_t
            if underline: open_t += '<u>'; close_t = '</u>' + close_t
            if styles:
                parts.append(f'<span style="{";".join(styles)}">{open_t}{txt}{close_t}</span>')
            elif open_t:
                parts.append(f'{open_t}{txt}{close_t}')
            else:
                parts.append(txt)

        i = 0
        while i < len(body):
            ch = body[i]

            if ch == '{':
                _flush_text()
                style_stack.append((bold, italic, underline, color_idx, highlight_idx, alignment))
                i += 1
            elif ch == '}':
                _flush_text()
                if style_stack:
                    bold, italic, underline, color_idx, highlight_idx, alignment = style_stack.pop()
                i += 1
            elif ch == '\\':
                _flush_text()
                i += 1
                if i >= len(body):
                    break
                # Escaped Sonderzeichen
                if body[i] in ('{', '}', '\\'):
                    text_buf.append(body[i])
                    i += 1
                    continue
                # Hex-Escape \'xx
                if body[i] == "'":
                    i += 1
                    if i + 1 < len(body):
                        try:
                            text_buf.append(bytes.fromhex(body[i:i+2]).decode('cp1252'))
                        except Exception:
                            text_buf.append('?')
                        i += 2
                    continue
                # Control Word
                word = ''
                while i < len(body) and body[i].isalpha():
                    word += body[i]
                    i += 1
                param_str = ''
                if i < len(body) and (body[i] == '-' or body[i].isdigit()):
                    if body[i] == '-':
                        param_str += '-'
                        i += 1
                    while i < len(body) and body[i].isdigit():
                        param_str += body[i]
                        i += 1
                param = int(param_str) if param_str else None
                # Trailing Space
                if i < len(body) and body[i] == ' ':
                    i += 1
                # Verarbeitung
                if word == 'par':
                    _close_para()
                elif word == 'b':
                    bold = (param != 0) if param is not None else True
                elif word == 'i':
                    italic = (param != 0) if param is not None else True
                elif word == 'ul':
                    underline = True
                elif word == 'ulnone':
                    underline = False
                elif word == 'cf':
                    color_idx = param if param is not None else 0
                elif word == 'highlight':
                    highlight_idx = param if param is not None else 0
                elif word == 'qc':
                    alignment = 'center'
                elif word == 'ql':
                    alignment = 'left'
                elif word == 'qr':
                    alignment = 'right'
                elif word == 'line':
                    _open_para()
                    parts.append('<br>')
                elif word == 'tab':
                    text_buf.append('    ')
                elif word == 'endash':
                    text_buf.append('\u2013')
                elif word == 'emdash':
                    text_buf.append('\u2014')
                elif word == 'lquote':
                    text_buf.append('\u2018')
                elif word == 'rquote':
                    text_buf.append('\u2019')
                elif word == 'ldblquote':
                    text_buf.append('\u201C')
                elif word == 'rdblquote':
                    text_buf.append('\u201D')
                elif word == 'bullet':
                    text_buf.append('\u2022')
                # Alles andere ignorieren (loch, hich, dbch, lang, etc.)
            elif ch in ('\n', '\r'):
                i += 1  # RTF-Zeilenumbrueche ignorieren, nur \par zaehlt
            else:
                text_buf.append(ch)
                i += 1

        _flush_text()
        _close_para()
        parts.append('</body></html>')
        html = ''.join(parts)
        # Kompakte Absatz-Margins (RTF-Absaetze sind enger als HTML-Defaults)
        html = html.replace('<html><body>',
            '<html><head><style>p { margin: 2px 0; }</style></head><body>')
        return html

    def _load_text(self, path: str, filename: str):
        """Laedt Plaintext-Lyrics."""
        content = self._read_file(path)
        self._browser.setPlainText(content)
        self._cache_original_sizes()
        self._label_status.setText(filename)
        self._lyrics_loaded = True
        self._schedule_refit_after_load()

    # ============================================================
    # DOCX / PDF: reine Anzeige (BL-146)
    # ============================================================

    def _load_docx(self, path: str, filename: str):
        """Laedt DOCX als reine Anzeige.

        DOCX ist ein ZIP mit word/document.xml. Wir parsen es selbst zu HTML
        (kein python-docx noetig) mit Erhalt von Fett/Kursiv/Unterstrichen und
        Schrift-/Hintergrundfarben (Tag-/Break-Markierungen). Das Ergebnis
        laeuft wie HTML/RTF durch _sanitize_html.
        """
        try:
            html = self._docx_to_html(path)
        except Exception as e:
            self._show_placeholder(
                _t("lyrics_docx_error", error=str(e), filename=filename)
            )
            return
        html = self._sanitize_html(html)
        issues = self._find_unclosed_inline_tags(html)
        if issues:
            html = self._fix_unclosed_inline_tags(html, issues)
        self._update_default_stylesheet()
        self._browser.setHtml(html)
        self._cache_original_sizes()
        self._label_status.setText(filename)
        self._lyrics_loaded = True
        self._schedule_refit_after_load()

    # Word-Highlight-Namen (w:highlight) -> CSS-Farbe
    _DOCX_HIGHLIGHTS = {
        "yellow": "#ffff00", "green": "#00ff00", "cyan": "#00ffff",
        "magenta": "#ff00ff", "blue": "#0000ff", "red": "#ff0000",
        "darkBlue": "#000080", "darkCyan": "#008080", "darkGreen": "#008000",
        "darkMagenta": "#800080", "darkRed": "#800000", "darkYellow": "#808000",
        "darkGray": "#808080", "lightGray": "#c0c0c0", "black": "#000000",
        "white": "#ffffff",
    }

    # w:jc-Werte -> CSS text-align
    _DOCX_JC = {
        "center": "center", "right": "right", "end": "right",
        "both": "justify", "distribute": "justify",
        "left": "left", "start": "left",
    }

    @staticmethod
    def _docx_parse_rpr(rpr, W) -> dict:
        """Liest Run-Eigenschaften aus einem rPr-Element.

        Schluessel (nur gesetzte): size(pt), bold/italic/underline(bool),
        color(hex), highlight(name), shd(hex). Fehlt ein Attribut, fehlt der
        Key -> wird beim Mergen vom Style/Default geerbt.
        """
        out = {}
        if rpr is None:
            return out
        b = rpr.find(f"{W}b")
        if b is not None:
            out['bold'] = b.get(f"{W}val", "true") not in ("0", "false")
        i = rpr.find(f"{W}i")
        if i is not None:
            out['italic'] = i.get(f"{W}val", "true") not in ("0", "false")
        u = rpr.find(f"{W}u")
        if u is not None:
            out['underline'] = u.get(f"{W}val", "single") != "none"
        sz = rpr.find(f"{W}sz")
        if sz is not None:
            try:
                out['size'] = float(sz.get(f"{W}val", "")) / 2.0  # Halbpunkt -> pt
            except ValueError:
                pass
        color = rpr.find(f"{W}color")
        if color is not None:
            v = color.get(f"{W}val", "")
            if v and v.lower() != "auto":
                out['color'] = v
        hl = rpr.find(f"{W}highlight")
        if hl is not None:
            out['highlight'] = hl.get(f"{W}val", "")
        shd = rpr.find(f"{W}shd")
        if shd is not None:
            fill = shd.get(f"{W}fill", "")
            if fill and fill.lower() not in ("auto", "ffffff"):
                out['shd'] = fill
        return out

    @classmethod
    def _docx_parse_ppr(cls, ppr, W) -> dict:
        """Liest Absatz-Eigenschaften: jc (Ausrichtung), indent_px (Einrueckung)."""
        out = {}
        if ppr is None:
            return out
        jc = ppr.find(f"{W}jc")
        if jc is not None:
            v = cls._DOCX_JC.get(jc.get(f"{W}val", ""))
            if v:
                out['jc'] = v
        ind = ppr.find(f"{W}ind")
        if ind is not None:
            left = ind.get(f"{W}left") or ind.get(f"{W}start")
            if left:
                try:
                    out['indent_px'] = max(0, round(int(left) / 15))  # Twips -> px
                except ValueError:
                    pass
        return out

    @classmethod
    def _docx_build_styles(cls, styles_root, W):
        """Loest styles.xml zu (default_rpr, default_ppr, style_map) auf.

        style_map[styleId] enthaelt die voll aufgeloesten rpr/ppr-Dicts
        (inkl. basedOn-Vererbung). docDefaults bilden die Basis.
        """
        default_rpr, default_ppr = {}, {}
        raw = {}
        if styles_root is not None:
            dd = styles_root.find(f"{W}docDefaults")
            if dd is not None:
                rprd = dd.find(f"{W}rPrDefault")
                if rprd is not None:
                    default_rpr = cls._docx_parse_rpr(rprd.find(f"{W}rPr"), W)
                pprd = dd.find(f"{W}pPrDefault")
                if pprd is not None:
                    default_ppr = cls._docx_parse_ppr(pprd.find(f"{W}pPr"), W)
            for st in styles_root.findall(f"{W}style"):
                sid = st.get(f"{W}styleId")
                if not sid:
                    continue
                based = st.find(f"{W}basedOn")
                raw[sid] = {
                    'basedOn': based.get(f"{W}val") if based is not None else None,
                    'rpr': cls._docx_parse_rpr(st.find(f"{W}rPr"), W),
                    'ppr': cls._docx_parse_ppr(st.find(f"{W}pPr"), W),
                }
        resolved = {}

        def resolve(sid, seen):
            if sid in resolved:
                return resolved[sid]
            if sid not in raw or sid in seen:
                return {'rpr': {}, 'ppr': {}}
            seen.add(sid)
            node = raw[sid]
            if node['basedOn']:
                base = resolve(node['basedOn'], seen)
                merged = {'rpr': {**base['rpr'], **node['rpr']},
                          'ppr': {**base['ppr'], **node['ppr']}}
            else:
                merged = {'rpr': dict(node['rpr']), 'ppr': dict(node['ppr'])}
            resolved[sid] = merged
            return merged

        for sid in raw:
            resolve(sid, set())
        return default_rpr, default_ppr, resolved

    @classmethod
    def _docx_to_html(cls, path: str) -> str:
        """Konvertiert eine DOCX-Datei zu HTML.

        Beruecksichtigt Run-Format (Fett/Kursiv/Unterstrichen, Schriftgroesse,
        Schrift-/Hintergrundfarben) sowie Absatz-Format (Ausrichtung,
        Einrueckung). Absatz-Styles aus styles.xml werden inkl. basedOn-
        Vererbung aufgeloest (z.B. der grosse zentrierte Titel-Style).
        Word-Tabstopp-Spalten werden NICHT nachgebildet (BL-146).
        """
        import zipfile
        import xml.etree.ElementTree as ET

        W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
        with zipfile.ZipFile(path) as zf:
            xml_bytes = zf.read("word/document.xml")
            try:
                styles_root = ET.fromstring(zf.read("word/styles.xml"))
            except (KeyError, ET.ParseError):
                styles_root = None
        root = ET.fromstring(xml_bytes)
        body = root.find(f"{W}body")
        if body is None:
            return "<html><body></body></html>"

        default_rpr, default_ppr, style_map = cls._docx_build_styles(styles_root, W)

        def esc(s: str) -> str:
            return (s.replace('&', '&amp;')
                     .replace('<', '&lt;').replace('>', '&gt;'))

        def fmt_size(pt: float) -> str:
            return f"{int(pt)}" if pt == int(pt) else f"{pt:g}"

        parts = ['<html><head><style>p { margin: 2px 0; }</style></head><body>']
        for para in body.iter(f"{W}p"):
            ppr_el = para.find(f"{W}pPr")
            style_id = None
            if ppr_el is not None:
                ps = ppr_el.find(f"{W}pStyle")
                if ps is not None:
                    style_id = ps.get(f"{W}val")
            style = style_map.get(style_id, {'rpr': {}, 'ppr': {}})
            # Effektives Absatz-Format: docDefault <- Style <- direkter pPr
            eff_ppr = {**default_ppr, **style['ppr'],
                       **cls._docx_parse_ppr(ppr_el, W)}
            # Basis-Run-Format des Absatzes: docDefault <- Style-rPr
            base_rpr = {**default_rpr, **style['rpr']}

            run_html = []
            for run in para.findall(f"{W}r"):
                eff = {**base_rpr, **cls._docx_parse_rpr(run.find(f"{W}rPr"), W)}
                styles = []
                if eff.get('size'):
                    styles.append(f"font-size:{fmt_size(eff['size'])}pt")
                if eff.get('color'):
                    styles.append(f"color:#{eff['color']}")
                if eff.get('highlight'):
                    css = cls._DOCX_HIGHLIGHTS.get(eff['highlight'])
                    if css:
                        styles.append(f"background-color:{css}")
                if eff.get('shd'):
                    styles.append(f"background-color:#{eff['shd']}")
                # Text + Umbrueche/Tabs des Runs einsammeln
                seg = []
                for node in run:
                    tag = node.tag
                    if tag == f"{W}t":
                        seg.append(esc(node.text or ""))
                    elif tag == f"{W}br":
                        seg.append("<br>")
                    elif tag == f"{W}tab":
                        seg.append("&nbsp;&nbsp;&nbsp;&nbsp;")
                text = "".join(seg)
                if not text:
                    continue
                if eff.get('bold') is True:
                    text = f"<b>{text}</b>"
                if eff.get('italic') is True:
                    text = f"<i>{text}</i>"
                if eff.get('underline') is True:
                    text = f"<u>{text}</u>"
                if styles:
                    text = f'<span style="{";".join(styles)}">{text}</span>'
                run_html.append(text)

            pstyle = []
            if eff_ppr.get('jc'):
                pstyle.append(f"text-align:{eff_ppr['jc']}")
            if eff_ppr.get('indent_px'):
                pstyle.append(f"margin-left:{eff_ppr['indent_px']}px")
            attr = f' style="{";".join(pstyle)}"' if pstyle else ''
            parts.append(f"<p{attr}>{''.join(run_html) if run_html else '&nbsp;'}</p>")
        parts.append("</body></html>")
        return "".join(parts)

    def _load_pdf(self, path: str, filename: str):
        """Laedt PDF als reine Anzeige (Textextraktion via pypdf).

        Lazy-Import: pypdf wird erst hier geladen, damit der App-Start nicht
        belastet wird. Reine Anzeige — Formatierung/Farben gehen verloren,
        der Call-Text bleibt erhalten.
        """
        try:
            from pypdf import PdfReader
        except ImportError:
            self._show_placeholder(_t("lyrics_pdf_missing"))
            return
        try:
            reader = PdfReader(path)
            pages = [(p.extract_text() or "") for p in reader.pages]
        except Exception as e:
            self._show_placeholder(
                _t("lyrics_pdf_error", error=str(e), filename=filename)
            )
            return
        text = "\n\n".join(pages).strip()
        if not text:
            # z.B. gescanntes PDF ohne Textebene
            self._show_placeholder(_t("lyrics_pdf_no_text", filename=filename))
            return
        esc = (text.replace('&', '&amp;')
                   .replace('<', '&lt;').replace('>', '&gt;'))
        html = (f'<html><head><style>pre {{ white-space: pre-wrap; '
                f'font-family: inherit; margin: 0; }}</style></head>'
                f'<body><pre>{esc}</pre></body></html>')
        self._update_default_stylesheet()
        self._browser.setHtml(html)
        self._cache_original_sizes()
        self._label_status.setText(filename)
        self._lyrics_loaded = True
        self._schedule_refit_after_load()

    # ============================================================
    # Edit-Modus: Rich-Text-Bearbeitung der Lyrics
    # ============================================================
    #
    # Konzept:
    # - Zielformat ist immer HTML (deckt Headings, Bold/Italic/Underline,
    #   Schriftgroessen, Schrift- und Hintergrundfarben ab).
    # - HTML-Originale werden ueberschrieben, beim ersten Save wird eine
    #   .bak-Sicherung angelegt.
    # - RTF/TXT-Originale werden NIE veraendert. Stattdessen wird eine
    #   .html-Kopie neben dem Original angelegt und der lyrics_file-Eintrag
    #   des Songs in der DB auf die neue Datei umgezogen.
    # - Auto-Fit/Auto-Scroll sind im Edit-Modus deaktiviert (sonst springt
    #   die Schriftgroesse waehrend des Tippens).

    def _build_format_toolbar(self) -> QWidget:
        """Baut die zweite Toolbar mit Format-Buttons (Bold/Italic/...).

        Buttons nutzen SVG-Icons aus dem aktuellen Skin (gleiches Pattern
        wie zoom-in/zoom-out), Fallback-Text nur wenn kein Skin gesetzt ist.
        """
        wrap = QWidget()
        hl = QHBoxLayout(wrap)
        hl.setContentsMargins(0, 0, 0, 0)
        hl.setSpacing(4)

        skin_dir = ""
        if self._skin_mgr and getattr(self._skin_mgr, "icon_dir", None):
            skin_dir = self._skin_mgr.icon_dir.replace("\\", "/")

        def _mk_icon_btn(icon_name, fallback_text, tooltip_key,
                        slot, checkable=False, width=28):
            b = QPushButton()
            b.setFixedSize(width, 28)
            b.setToolTip(_t(tooltip_key))
            if skin_dir:
                b.setIcon(QIcon(f"{skin_dir}/{icon_name}.svg"))
            else:
                b.setText(fallback_text)
            if checkable:
                mark_toggle(b, active=False)
            b.clicked.connect(slot)
            hl.addWidget(b)
            return b

        # Absatz-Format
        self._cmb_heading = QComboBox()
        self._cmb_heading.addItem(_t("lyrics_heading_body"), "p")
        self._cmb_heading.addItem(_t("lyrics_heading_h1"), "h1")
        self._cmb_heading.addItem(_t("lyrics_heading_h2"), "h2")
        self._cmb_heading.addItem(_t("lyrics_heading_h3"), "h3")
        self._cmb_heading.setToolTip(_t("tooltip_lyrics_heading"))
        self._cmb_heading.setFixedWidth(110)
        self._cmb_heading.activated.connect(self._on_heading_changed)
        hl.addWidget(self._cmb_heading)

        # Schriftgroesse
        self._spn_font_size = QSpinBox()
        self._spn_font_size.setRange(6, 96)
        self._spn_font_size.setValue(12)
        self._spn_font_size.setSuffix(" pt")
        self._spn_font_size.setFixedWidth(86)
        self._spn_font_size.setToolTip(_t("tooltip_lyrics_font_size"))
        # valueChanged fuer Live-Update (Pfeiltasten + Eingabe), editingFinished
        # als Sicherung damit getippte Werte ohne Enter trotzdem ankommen.
        self._spn_font_size.valueChanged.connect(self._on_font_size_changed)
        self._spn_font_size.editingFinished.connect(self._on_font_size_changed)
        hl.addWidget(self._spn_font_size)

        self._btn_fmt_bold = _mk_icon_btn(
            "bold", "B", "tooltip_lyrics_bold",
            self._on_fmt_bold, checkable=True)
        self._btn_fmt_italic = _mk_icon_btn(
            "italic", "I", "tooltip_lyrics_italic",
            self._on_fmt_italic, checkable=True)
        self._btn_fmt_underline = _mk_icon_btn(
            "underline", "U", "tooltip_lyrics_underline",
            self._on_fmt_underline, checkable=True)
        _mk_icon_btn("text-color", "A", "tooltip_lyrics_color",
                     self._on_fmt_color, width=32)
        _mk_icon_btn("highlight", "abc", "tooltip_lyrics_highlight",
                     self._on_fmt_highlight, width=32)

        hl.addStretch(1)

        # Speichern / Verwerfen
        self._btn_save = _mk_icon_btn(
            "save", "OK", "tooltip_lyrics_save",
            self._on_save_clicked, width=32)
        self._btn_cancel = _mk_icon_btn(
            "close", "X", "tooltip_lyrics_cancel",
            self._on_cancel_clicked, width=28)

        return wrap

    # ---- Edit-Mode Lifecycle ----

    def eventFilter(self, obj, event):
        # BL-171: Viewport-Groesse geaendert → Overlay nachziehen. Kein return:
        # das Resize muss weiterlaufen, wir haengen uns nur dran.
        try:
            if (obj is self._browser.viewport()
                    and event.type() == QEvent.Resize):
                self.refresh_section_overlay()
                # intern#76: Lesebalken deckt immer den ganzen Viewport ab
                self._reading_band.sync_geometry()
        except Exception:
            pass
        # BL-160: Im Sync-Modus faengt das Widget Maus-Klicks ab
        try:
            if (self._sync_mode and self._lyrics_loaded
                    and obj is self._browser.viewport()
                    and event.type() == QEvent.MouseButtonPress):
                self._handle_sync_click(event)
                return True  # Event konsumieren — keine Cursor-/Auswahl-Aktion
        except Exception:
            pass
        # Doppelklick auf Browser-Viewport schaltet in Edit-Modus
        try:
            if (not self._sync_mode and not self._edit_mode and self._lyrics_loaded
                    and self._current_path
                    and event.type() == QEvent.MouseButtonDblClick
                    and obj is self._browser.viewport()):
                self._enter_edit_mode()
                return False  # Event nicht konsumieren — Cursor positionieren
        except Exception:
            pass
        return super().eventFilter(obj, event)

    # ---- BL-171: Abschnitts-Overlay ----

    def _sections_key_prefix(self) -> str:
        """Praefix der Abschnitts-Keys in song_properties.

        Haengt nur am LYRIC-Slot, nicht zusaetzlich am Musik-Slot wie die
        Sync-Anker: die Abschnitte sind eine Eigenschaft des TEXTES und gelten
        damit fuer jede Aufnahme desselben Lyrics.
        """
        return f"lyric_sections_l{self._sync_lyric_slot}_"

    def _rebuild_line_offsets(self, text: str = None):
        """Zeile -> Zeichenposition im AKTUELL angezeigten Text.

        Bewusst ohne pristine<->display-Umrechnung: die Sync-Marken werden
        INNERHALB einer Zeile eingefuegt und enthalten keinen Zeilenumbruch.
        Zeichenpositionen verschieben sie damit, Zeilennummern nicht. Wer hier
        zusaetzlich umrechnet, zaehlt den Marker-Versatz doppelt und die
        Flaechen wandern gegenueber dem Text (genau dieser Fehler war da).
        Deshalb ist die Zeilennummer die stabile Waehrung — nicht das Zeichen.
        """
        if text is None:
            text = self._browser.document().toPlainText()
        offsets, pos = [], 0
        for raw in text.split("\n"):
            offsets.append(pos)
            pos += len(raw) + 1
        self._line_offsets = offsets

    def _char_to_line(self, char_pos: int) -> int:
        """Groesste Zeile, deren Anfang <= char_pos liegt."""
        import bisect
        if not self._line_offsets:
            return 0
        i = bisect.bisect_right(self._line_offsets, int(char_pos)) - 1
        return max(0, i)

    def store_sections_from_result(self, res, text: str = None):
        """Uebernimmt ein SectionResult (7er-Raster + extras) als Zeilenbereiche
        und schreibt sie an den Song. Quelle der Wahrheit fuer das Overlay.

        `text` MUSS derselbe Text sein, auf dem parse_sections gelaufen ist —
        sonst zeigen dessen Zeichenpositionen auf einen anderen Zustand des
        Dokuments und die Zeilen kommen verschoben heraus.
        """
        if text is None:
            text = self._browser.document().toPlainText()
        self._rebuild_line_offsets(text)
        self._lyric_sections = lyric_section_lines(res, text)
        self._persist_lyric_sections()
        self._section_overlay.update()

    def _persist_lyric_sections(self):
        if not (self._db and self._sync_song_id):
            return
        try:
            prefix = self._sections_key_prefix()
            props = self._db.get_properties(self._sync_song_id)
            for key in list(props.keys()):
                if key.startswith(prefix):
                    self._db.set_property(self._sync_song_id, key, "")
            for name, (l0, l1) in self._lyric_sections.items():
                self._db.set_property(self._sync_song_id,
                                      f"{prefix}{name}", f"{int(l0)}|{int(l1)}")
        except Exception as e:
            print(f"[BL-171] Abschnitte speichern fehlgeschlagen: {e}")

    def _load_lyric_sections(self):
        """Laedt die gespeicherten Abschnitte des aktuellen Lyric-Slots."""
        self._lyric_sections = {}
        self._rebuild_line_offsets()
        self._load_figure_cuts()  # BL-200: Schnitt-Overrides mitladen
        if not (self._db and self._sync_song_id):
            return
        try:
            props = self._db.get_properties(self._sync_song_id)
        except Exception:
            return
        prefix = self._sections_key_prefix()
        for key, value in (props or {}).items():
            if not key.startswith(prefix):
                continue
            name = key[len(prefix):]
            try:
                l0, l1 = value.split("|", 1)
                self._lyric_sections[name] = (int(l0), int(l1))
            except (ValueError, AttributeError):
                continue

    def section_rects(self) -> list:
        """[(name, y_oben, y_unten)] je EINZELNEM Abschnitt, nach oben sortiert.

        Rechnet Zeile -> Zeichenposition im angezeigten Text -> Cursor-Rechteck.
        cursorRect() liefert bereits scroll-korrigierte Viewport-Koordinaten.

        Bewusst ohne Gruppierung: die Aufteilung in Spalten macht das Overlay
        anhand tatsaechlicher Ueberlappung. Frueher wurden nur Abschnitte mit
        IDENTISCHEM Bereich zusammengefasst — sobald man einen davon verschob,
        ueberlappten sie nur noch teilweise und malten uebereinander.
        """
        if not self._lyric_sections or not self._line_offsets:
            return []
        doc = self._browser.document()
        last_line = len(self._line_offsets) - 1
        out = []
        for name in LYRIC_SECTION_ORDER:
            rng = self._lyric_sections.get(name)
            if not rng:
                continue
            l0, l1 = max(0, min(rng[0], last_line)), max(0, min(rng[1], last_line))
            if l1 < l0:
                l0, l1 = l1, l0
            try:
                c0 = QTextCursor(doc)
                c0.setPosition(min(self._line_offsets[l0],
                                   doc.characterCount() - 1))
                c1 = QTextCursor(doc)
                c1.setPosition(min(self._line_offsets[l1],
                                   doc.characterCount() - 1))
                c1.movePosition(QTextCursor.EndOfLine)
                r0 = self._browser.cursorRect(c0)
                r1 = self._browser.cursorRect(c1)
            except Exception:
                continue
            out.append((name, r0.top(), r1.bottom()))
        out.sort(key=lambda e: (e[1], LYRIC_SECTION_ORDER.index(e[0])))
        return out

    def line_at_viewport_y(self, y: int):
        """Textzeile an einer y-Position im Browser-Viewport (fuers Ziehen)."""
        if not self._line_offsets:
            return None
        try:
            cur = self._browser.cursorForPosition(QPoint(4, int(y)))
            cur.movePosition(QTextCursor.StartOfLine)
            return self._char_to_line(cur.position())
        except Exception:
            return None

    def refresh_section_overlay(self):
        """Nach Laden/Zoom/Resize/Marker-Wechsel: neu vermessen und zeichnen.

        Die Zeilentabelle wird mitgezogen, weil das Ein- und Ausblenden der
        Sync-Marken die Zeichenpositionen aller Zeilen verschiebt.
        """
        try:
            self._rebuild_line_offsets()
            self._section_overlay.sync_geometry()
            self._section_overlay.update()
        except Exception:
            pass

    # ---- BL-160: Lyrics-Sync-Punkte ----

    def set_sync_identity(self, song_id, music_slot: int, lyric_slot: int):
        """Setzt die Identitaet (Song + Musik-/Lyric-Variante) fuer Sync-Punkte
        und laedt die zugehoerigen Anker neu. Wird vom Hauptfenster nach jedem
        Lyrics-Laden aufgerufen.
        """
        self._sync_song_id = song_id
        self._sync_music_slot = int(music_slot) if music_slot else 1
        self._sync_lyric_slot = int(lyric_slot) if lyric_slot else 1
        self._load_sync_anchors()
        # BL-171: Abschnitte gehoeren zum Lyric-Slot → mit der Identitaet laden
        self._load_lyric_sections()
        self.refresh_section_overlay()
        # Falls gerade im Sync-Modus: Marker fuer die neue Datei neu zeichnen
        if self._sync_mode:
            self._render_sync_markers()
        # BL-173: Verfuegbarkeit des Dynamic-Lyrics-Buttons neu bewerten. Bei
        # zuletzt gewuenschtem Dynamic wendet update_dynamic_button_state() es
        # fuer den neuen Song automatisch wieder an (liest die Auswahl neu).
        self.update_dynamic_button_state()

    # ---- BL-173: Dynamic Lyrics ----

    _DYNAMIC_FIGURES = ("figure1", "figure2", "figure3", "figure4")

    # BL-200: Sentinel in _figure_cuts — vom Nutzer bewusst geloeschter Trenner.
    # Unterdrueckt den (auch automatisch erkannten) Schnitt: kein Strich im
    # Overlay, und bei Dynamic wird der ganze Figurenblock ersetzt (kein Tail).
    _FIGURE_CUT_SUPPRESSED = -1

    def _figures_present(self) -> list:
        """Vorhandene Figuren-Abschnitte, nach Textzeile (l0) sortiert."""
        figs = [(n, self._lyric_sections[n]) for n in self._DYNAMIC_FIGURES
                if n in self._lyric_sections]
        figs.sort(key=lambda e: e[1][0])
        return figs

    # ---- BL-200: Schnitt-Zeile (Call-Ende → Gesangstext) je Figur ----

    def _block_default_cut(self, l0: int, l1: int, lines: list = None) -> int:
        """Algorithmus-Default fuer die letzte Tanz-Call-Zeile eines Figuren-
        Blocks (l0 = Kopfzeile, l1 = letzte Blockzeile). `lines` optional, sonst
        aus dem aktuell angezeigten Dokument."""
        if lines is None:
            lines = self._browser.document().toPlainText().split("\n")
        return singing_sections.figure_call_end_line(lines, l0 + 1, l1)

    def _figure_cut_line(self, name: str):
        """Effektive Schnitt-Zeile einer Figur: User-Override falls vorhanden,
        sonst Algorithmus-Default. None, wenn die Figur nicht existiert."""
        rng = self._lyric_sections.get(name)
        if not rng:
            return None
        l0, l1 = int(rng[0]), int(rng[1])
        if name in self._figure_cuts:
            ov = int(self._figure_cuts[name])
            if ov == self._FIGURE_CUT_SUPPRESSED:
                return l1   # bewusst geloescht: kein Strich, kein Tail
            return max(l0 + 1, min(ov, l1))
        return self._block_default_cut(l0, l1)

    def _resolve_block_cut(self, l0: int, l1: int, lines: list,
                           sections_map: dict = None) -> int:
        """Schnitt-Zeile fuer einen Figuren-Block bei der Ersetzung: honoriert
        einen User-Override (Figur mit exakt diesem Bereich), sonst Default.

        `sections_map` ist der Bereich, gegen den der Override gematcht wird — bei
        der Ersetzung MUSS das die ORIGINAL-Abschnitte sein (`base_sections`),
        nicht das bereits auf Anzeige-Koordinaten remappte self._lyric_sections;
        sonst faende ein Override ab dem zweiten Sequenzwechsel keinen Block mehr.
        """
        sections_map = sections_map if sections_map is not None \
            else self._lyric_sections
        for name in self._DYNAMIC_FIGURES:
            rng = sections_map.get(name)
            if rng and int(rng[0]) == l0 and int(rng[1]) == l1 \
                    and name in self._figure_cuts:
                ov = int(self._figure_cuts[name])
                if ov == self._FIGURE_CUT_SUPPRESSED:
                    return l1   # geloescht: ganzen Block ersetzen (kein Tail)
                return max(l0 + 1, min(ov, l1))
        return self._block_default_cut(l0, l1, lines)

    def figure_cut_y(self, name: str):
        """Browser-Viewport-y (Unterkante der Schnitt-Zeile) fuer den Strich im
        Overlay. None, wenn der Schnitt nicht echt INNERHALB des Blocks liegt
        (dann gibt es keinen geschuetzten Gesangs-Tail zum Abgrenzen)."""
        rng = self._lyric_sections.get(name)
        if not rng or not self._line_offsets:
            return None
        cut = self._figure_cut_line(name)
        if cut is None:
            return None
        l0, l1 = int(rng[0]), int(rng[1])
        if not (l0 < cut < l1):
            return None
        doc = self._browser.document()
        try:
            c = QTextCursor(doc)
            c.setPosition(min(self._line_offsets[cut], doc.characterCount() - 1))
            c.movePosition(QTextCursor.EndOfLine)
            return self._browser.cursorRect(c).bottom()
        except Exception:
            return None

    def _figure_cuts_key_prefix(self) -> str:
        """Praefix der Schnitt-Zeilen-Keys in song_properties. Wie die Abschnitte
        am LYRIC-Slot (Eigenschaft des Textes, nicht der Aufnahme)."""
        return f"lyric_figcut_l{self._sync_lyric_slot}_"

    def _persist_figure_cuts(self):
        if not (self._db and self._sync_song_id):
            return
        try:
            prefix = self._figure_cuts_key_prefix()
            props = self._db.get_properties(self._sync_song_id)
            for key in list(props.keys()):
                if key.startswith(prefix):
                    self._db.set_property(self._sync_song_id, key, "")
            for name, cut in self._figure_cuts.items():
                self._db.set_property(self._sync_song_id,
                                      f"{prefix}{name}", str(int(cut)))
        except Exception as e:
            print(f"[BL-200] Schnitt-Zeilen speichern fehlgeschlagen: {e}")

    def _load_figure_cuts(self):
        """Laedt die gespeicherten Schnitt-Overrides des aktuellen Lyric-Slots."""
        self._figure_cuts = {}
        if not (self._db and self._sync_song_id):
            return
        try:
            props = self._db.get_properties(self._sync_song_id)
        except Exception:
            return
        prefix = self._figure_cuts_key_prefix()
        for key, value in (props or {}).items():
            if not key.startswith(prefix):
                continue
            name = key[len(prefix):]
            try:
                self._figure_cuts[name] = int(value)
            except (ValueError, TypeError):
                continue

    def _place_figure_cut(self, name: str, line):
        """BL-200: Trenner per Kontextmenue an der angeklickten Zeile setzen.
        Auf den Block-Innenraum geklemmt, damit der Strich echt sichtbar ist."""
        rng = self._lyric_sections.get(name)
        if not rng or line is None:
            return
        l0, l1 = int(rng[0]), int(rng[1])
        self._figure_cuts[name] = max(l0 + 1, min(int(line), l1 - 1))
        self._persist_figure_cuts()
        self._section_overlay.update()

    def _suppress_figure_cut(self, name: str):
        """BL-200: Trenner per Kontextmenue loeschen — auch einen automatisch
        erkannten. Der Sentinel unterdrueckt ihn dauerhaft (persistiert)."""
        self._figure_cuts[name] = self._FIGURE_CUT_SUPPRESSED
        self._persist_figure_cuts()
        self._section_overlay.update()

    def _dynamic_gating_reason(self):
        """None wenn Dynamic Lyrics nutzbar ist, sonst ein i18n-Grund-Key.

        Reihenfolge = Prioritaet der Meldung. Deckt die vier Bedingungen aus
        der Spezifikation ab: Lyric geladen, SyncPoints gesetzt, Figuren
        erkannt, mind. eine Sequenz im Sequence-View vorhanden.
        """
        if not self._lyrics_loaded or not self._current_path:
            return "dynamic_reason_no_lyrics"
        if not self._sync_anchors:
            return "dynamic_reason_no_sync"
        if not self._figures_present():
            return "dynamic_reason_no_figures"
        if not self._current_sequence_calls():
            return "dynamic_reason_no_sequences"
        return None

    def _current_sequence_calls(self) -> list:
        """Call-Zeilen der AKTUELL im Sequence-View gezeigten Sequenz (via
        Callback). Leer, wenn dort keine Sequenz aktiv ist."""
        if not callable(self.get_current_sequence_calls):
            return []
        try:
            return list(self.get_current_sequence_calls() or [])
        except Exception:
            return []

    def update_dynamic_button_state(self):
        """Graut den Dynamic-Button aus, wenn die Voraussetzungen fehlen, und
        setzt einen erklaerenden Tooltip. Ist Dynamic gerade aktiv und faellt
        eine Voraussetzung weg (z.B. Songwechsel), wird sauber zurueckgesetzt."""
        if not hasattr(self, "_btn_dynamic"):
            return
        reason = self._dynamic_gating_reason()
        # Sync-/Edit-Modus schliesst Dynamic aus (Text wird dort veraendert)
        if reason is None and (self._sync_mode or self._edit_mode):
            reason = "dynamic_reason_busy"
        if reason is None:
            self._btn_dynamic.setEnabled(True)
            self._btn_dynamic.setToolTip(_t("tooltip_dynamic_lyrics"))
            # War Dynamic zuletzt gewuenscht und ist gerade aus (Songwechsel,
            # Verlassen von Sync-/Edit-Modus), automatisch wieder anwenden.
            self._reapply_dynamic_if_wanted()
            return
        # Voraussetzung fehlt → falls gerade aktiv, sauber zuruecksetzen.
        # _dynamic_wanted bleibt bestehen: ist die Bedingung nur voruebergehend
        # weg (z.B. Song ohne SyncPoints), greift Dynamic beim naechsten
        # passenden Song automatisch wieder.
        if self._dynamic_enabled:
            self._revert_dynamic()
        self._btn_dynamic.blockSignals(True)
        self._btn_dynamic.setChecked(False)
        self._btn_dynamic.blockSignals(False)
        self._btn_dynamic.setEnabled(False)
        self._btn_dynamic.setToolTip(_t(reason))

    def _on_dynamic_toggled(self, checked: bool):
        """Toggle: Text tauschen (an) bzw. Originaltext wiederherstellen (aus)."""
        if checked:
            reason = self._dynamic_gating_reason()
            if reason is not None or self._sync_mode or self._edit_mode:
                # Nicht nutzbar → Toggle stumm zuruecknehmen
                self._btn_dynamic.blockSignals(True)
                self._btn_dynamic.setChecked(False)
                self._btn_dynamic.blockSignals(False)
                return
            # Modus frisch aus der INI lesen (koennte ueber Settings geaendert sein)
            settings = self._settings
            try:
                self._dynamic_mode = str(settings.value("lyrics/dynamic_mode") or "")
            except Exception:
                pass
            # Erstaufruf: Modus abfragen und in der INI speichern
            if self._dynamic_mode not in ("1", "2"):
                mode = self._ask_dynamic_mode_first_time()
                if mode not in ("1", "2"):
                    self._btn_dynamic.blockSignals(True)
                    self._btn_dynamic.setChecked(False)
                    self._btn_dynamic.blockSignals(False)
                    return
                self._dynamic_mode = mode
                try:
                    settings.setValue("lyrics/dynamic_mode", mode)
                    settings.sync()   # sofort in die INI schreiben
                except Exception:
                    pass
            self._dynamic_wanted = True   # bleibt ueber Songwechsel aktiv
            self._persist_dynamic_enabled(True)
            self._apply_dynamic()
        else:
            self._dynamic_wanted = False
            self._persist_dynamic_enabled(False)
            self._revert_dynamic()

    def _persist_dynamic_enabled(self, enabled: bool):
        """Speichert die An/Aus-Praeferenz in der App-INI (lyrics/dynamic_enabled),
        damit sie beim naechsten Start wiederhergestellt werden kann."""
        settings = self._settings
        try:
            settings.setValue("lyrics/dynamic_enabled", bool(enabled))
            settings.sync()
        except Exception:
            pass

    def init_dynamic_preference(self):
        """Beim Start (nach dem Setzen von self._settings) die gespeicherte
        Dynamic-Lyrics-Praeferenz laden: An/Aus-Wunsch + Modus. Angewandt wird
        Dynamic dann automatisch, sobald ein passender Song geladen ist
        (set_sync_identity → _reapply_dynamic_if_wanted)."""
        if self._settings is None:
            return
        try:
            self._dynamic_wanted = self._settings.value(
                "lyrics/dynamic_enabled", False, type=bool)
        except Exception:
            self._dynamic_wanted = False
        try:
            self._dynamic_mode = str(self._settings.value("lyrics/dynamic_mode") or "")
        except Exception:
            pass
        # Button-Haken den Wunsch widerspiegeln lassen (Apply folgt beim Song).
        if hasattr(self, "_btn_dynamic"):
            self._btn_dynamic.blockSignals(True)
            self._btn_dynamic.setChecked(bool(self._dynamic_wanted))
            self._btn_dynamic.blockSignals(False)
        self.reload_invert_settings()   # intern#127
        self.reload_timing_settings()   # intern#115
        self.update_dynamic_button_state()

    def set_dynamic_wanted(self, enabled: bool):
        """Settings-Live-Apply der An/Aus-Praeferenz (ohne erneut in die INI zu
        schreiben — das hat der Settings-Dialog schon getan)."""
        enabled = bool(enabled)
        self._dynamic_wanted = enabled
        if not enabled:
            if self._dynamic_enabled:
                self._revert_dynamic()
            self._btn_dynamic.blockSignals(True)
            self._btn_dynamic.setChecked(False)
            self._btn_dynamic.blockSignals(False)
        # ok-Zweig von update_dynamic_button_state ruft bei Wunsch _reapply…
        self.update_dynamic_button_state()

    def set_dynamic_mode_live(self, mode: str):
        """Settings-Live-Apply des Modus. Ist Dynamic gerade aktiv, wird es mit
        dem neuen Modus sofort neu angewandt."""
        mode = str(mode)
        if mode not in ("1", "2") or mode == self._dynamic_mode:
            return
        self._dynamic_mode = mode
        if self._dynamic_enabled:
            self._revert_dynamic()
            self._reapply_dynamic_if_wanted()

    def _reapply_dynamic_if_wanted(self):
        """Nach einem Songwechsel Dynamic Lyrics automatisch wieder anwenden,
        wenn der Nutzer es zuletzt aktiv hatte und der neue Song die
        Voraussetzungen erfuellt. Liest dabei die AKTUELLE Sequenz-Auswahl neu
        (neuer Pointer aus dem Sequence-View)."""
        if not self._dynamic_wanted or self._dynamic_enabled:
            return
        if self._dynamic_gating_reason() is not None or self._sync_mode or self._edit_mode:
            return
        self._btn_dynamic.blockSignals(True)
        self._btn_dynamic.setChecked(True)
        self._btn_dynamic.blockSignals(False)
        self._apply_dynamic()

    def _ask_dynamic_mode_first_time(self):
        """Einmaliger Dialog: Option 1 vs. Option 2. Rueckgabe '1'/'2' oder None."""
        box = QMessageBox(self)
        box.setWindowTitle(_t("dynamic_mode_title"))
        box.setIcon(QMessageBox.Question)
        box.setText(_t("dynamic_mode_intro"))
        btn1 = box.addButton(_t("dynamic_mode_opt1"), QMessageBox.AcceptRole)
        btn2 = box.addButton(_t("dynamic_mode_opt2"), QMessageBox.AcceptRole)
        box.addButton(QMessageBox.Cancel)
        box.exec()
        clicked = box.clickedButton()
        if clicked is btn1:
            return "1"
        if clicked is btn2:
            return "2"
        return None

    # ---- intern#127: Heads / Sides invertieren ----

    def _invert_active(self) -> bool:
        return self._invert_enabled and bool(
            heads_sides.inverted_figures(self._invert_mode))

    def _dyn_block_figure(self, figs: tuple):
        """Figur (1..4), die ein Block gerade darstellt. Ein eigener Block je
        Figur steht fest; ein gemeinsamer FIGURE-Block zeigt die laufende Figur
        (aus der Teil-Zeitachse), vorher die naechste. Ohne verlaessliche
        Zeitachse (nicht genau 4 Teile) None -> nicht tauschen."""
        if len(figs) == 1:
            return figs[0]
        if len(self._dyn_part_starts) != 4:
            return None
        cur = self._dynamic_current_part(self._sync_last_pos) + 1
        if cur in figs:
            return cur
        upcoming = [f for f in figs if f > cur]
        return upcoming[0] if upcoming else figs[-1]

    def _dyn_invert_flags(self) -> tuple:
        """Je Figuren-Block: soll dort invertiert angezeigt werden?"""
        if not self._invert_active():
            return tuple(False for _ in self._dyn_block_keys)
        swap = heads_sides.inverted_figures(self._invert_mode)
        return tuple(self._dyn_block_figure(figs) in swap
                     for figs in self._dyn_block_figs)

    def _invert_tick(self):
        """Im Scroll-Takt: wechselt die Tauschrichtung eines gemeinsamen
        Blocks an einer Figuren-Grenze, wird deferred neu gerendert (auch in
        Modus 1, wo sonst nichts neu gerendert wird). Billig ohne Wechsel."""
        if not self._dynamic_enabled or not self._invert_active():
            return
        flags = self._dyn_invert_flags()
        if flags != self._dyn_invert_state:
            # Vorab merken: ohne Sequenz setzt der Render den Zustand nicht,
            # sonst liefe hier jeder Tick einen neuen Render an.
            self._dyn_invert_state = flags
            self.refresh_dynamic_from_sequence()

    def _on_invert_clicked(self, checked: bool):
        """Spiegel-Button. Ohne gewaehlte Art: in die Einstellungen an die
        Art-Auswahl (Button bleibt aus). Sonst An/Aus-Toggle, synchron mit
        lyrics/dynamic_invert_enabled."""
        if not heads_sides.inverted_figures(self._invert_mode):
            self._btn_invert.blockSignals(True)
            self._btn_invert.setChecked(False)
            self._btn_invert.blockSignals(False)
            if callable(self.open_settings_at):
                self.open_settings_at("lyrics/dynamic_invert_mode")
            return
        self._invert_enabled = bool(checked)
        settings = self._settings
        try:
            settings.setValue("lyrics/dynamic_invert_enabled", bool(checked))
            settings.sync()
        except Exception:
            pass
        self._update_invert_tooltip()
        self.refresh_dynamic_from_sequence()

    def reload_invert_settings(self):
        """Art und An/Aus aus der INI lesen (Start und Settings-Live-Apply) und
        Button + Anzeige nachziehen."""
        if self._settings is None:
            return
        try:
            self._invert_enabled = self._settings.value(
                "lyrics/dynamic_invert_enabled", False, type=bool)
            self._invert_mode = str(
                self._settings.value("lyrics/dynamic_invert_mode") or "").upper()
        except Exception:
            return
        if hasattr(self, "_btn_invert"):
            self._btn_invert.blockSignals(True)
            self._btn_invert.setChecked(self._invert_active())
            self._btn_invert.blockSignals(False)
            self._update_invert_tooltip()
        self.refresh_dynamic_from_sequence()

    def _update_invert_tooltip(self):
        if not heads_sides.inverted_figures(self._invert_mode):
            tip = _t("tooltip_dynamic_invert_choose")
        else:
            tip = _t("tooltip_dynamic_invert", mode=self._invert_mode)
        self._btn_invert.setToolTip(tip)

    # Grenzen und Vorgabe der Timing-Parameter (Sekunden), siehe SETTINGS_META.
    # intern#156: Vorgabe gilt auch ohne INI-Eintrag (Update, Neuinstallation).
    _TIMING_OFFSET_LIMIT = 10
    _TIMING_OFFSET_DEFAULT = -4

    def reload_timing_settings(self):
        """intern#115: "Textsprung timen" und "Texttausch timen" aus der INI
        lesen (Start und Settings-Live-Apply). Fehlt der Schluessel, gilt die
        Vorgabe wie im Einstellungsdialog; unlesbare Werte gelten als 0."""
        if self._settings is None:
            return
        lim = self._TIMING_OFFSET_LIMIT
        for attr, key in (("_text_jump_offset", "lyrics/text_jump_offset"),
                          ("_dynamic_swap_offset", "lyrics/dynamic_swap_offset")):
            try:
                val = int(float(self._settings.value(
                    key, self._TIMING_OFFSET_DEFAULT) or 0))
            except (TypeError, ValueError):
                val = 0
            setattr(self, attr, max(-lim, min(lim, val)))

    def reload_reading_settings(self):
        """intern#76: Leseposition und Lesebalken aus der INI lesen (Start und
        Settings-Live-Apply). Unlesbare Werte gelten als Standard."""
        def _num(key, default, lo, hi):
            try:
                val = float(self._settings.value(key, default))
            except (TypeError, ValueError):
                val = default
            return max(lo, min(hi, val))
        self._SYNC_ANCHOR_VIEWPORT_FRAC = _num(
            "lyrics/reading_position_pct", 30, 0, 100) / 100.0
        raw = self._settings.value("lyrics/reading_band_enabled", True)
        self._reading_band_enabled = str(raw).strip().lower() not in (
            "false", "0", "no", "off", "")
        self._reading_band_height_pct = _num("lyrics/reading_band_height", 20, 2, 60)
        self._reading_band_opacity_pct = _num("lyrics/reading_band_opacity", 30, 5, 100)
        self._scroll_last_val = -1
        if getattr(self, "_reading_band", None) is not None:
            self._reading_band.update()

    def _dynamic_current_part(self, pos: float) -> int:
        """Index des gerade laufenden Figuren-Teils (letzter Teil, dessen
        Startzeit <= pos). 0, solange noch kein Teil begonnen hat.

        intern#115: Die Grenzen wirken um "Texttausch timen" verschoben
        (negativ = frueher). Daran haengen Sequenzwechsel und Heads/Sides-
        Tausch gleichermassen."""
        pos = pos - self._dynamic_swap_offset
        cur = 0
        for i, t in enumerate(self._dyn_part_starts):
            if t <= pos:
                cur = i
        return cur

    def _dynamic_tick(self, pos: float):
        """Im Scroll-Takt aufgerufen (Option 2): erreicht die Wiedergabe einen
        neuen Figuren-Teil, wird im Sequence-View EINE Sequenz weitergeblaettert
        (deferred, audio-sicher). Das Sequence-View meldet die Aenderung zurueck
        und das Lyric-Feld spiegelt sie (refresh_dynamic_from_sequence).
        Nach dem letzten Figuren-Teil wird nicht weiter geblaettert."""
        self._invert_tick()
        if (not self._dynamic_enabled or self._dynamic_mode != "2"
                or self._dyn_advance_pending or not self._dyn_part_starts):
            return
        k = self._dynamic_current_part(pos)
        if k <= self._dyn_rendered_part:
            return
        self._dyn_advance_pending = True
        QTimer.singleShot(0, lambda target=k: self._do_dynamic_advance(target))

    def _do_dynamic_advance(self, target_part: int):
        """Deferter Schritt: blaettert das Sequence-View bis zum Ziel-Teil weiter.
        Jeder Schritt loest ueber das Sequence-View refresh_dynamic_from_sequence
        aus, wodurch das Lyric-Feld die neue Sequenz spiegelt."""
        self._dyn_advance_pending = False
        if not self._dynamic_enabled:
            return
        steps = target_part - self._dyn_rendered_part
        if steps <= 0:
            return
        self._dyn_rendered_part = target_part
        if callable(self.advance_sequence_view):
            for _ in range(steps):
                self.advance_sequence_view()

    def refresh_dynamic_from_sequence(self):
        """Schnittstelle Sequence-View → Lyric: die im Sequence-View gezeigte
        Sequenz hat sich geaendert (Auto-Blaettern ODER — kuenftig — Nutzer).
        Plant einen deferten Re-Render des Figuren-Textes. Billiger No-Op, wenn
        Dynamic aus ist."""
        if not self._dynamic_enabled or self._dyn_render_pending:
            return
        self._dyn_render_pending = True
        QTimer.singleShot(0, self._render_current_sequence_now)

    def _render_current_sequence_now(self):
        """Deferter Re-Render: spiegelt die AKTUELLE Sequenz des Sequence-Views
        in die Figuren-Bloecke."""
        self._dyn_render_pending = False
        if not self._dynamic_enabled or not self._pre_dynamic:
            return
        self._dynamic_build_document(self._current_sequence_calls())

    def _dynamic_build_document(self, calls: list):
        """Spiegelt die AKTUELLE Sequenz (`calls` = Call-Zeilen) in ALLE
        Figuren-Bloecke. Baut dazu aus dem PRISTINE Original (kein Drift) ein
        neues Dokument und blendet es ein; Sections/SyncPoints/Zoom werden
        nachgefuehrt. Kein Reload der Datei — die Quelle bleibt unberuehrt."""
        if not self._dynamic_enabled or not self._pre_dynamic:
            return
        if not calls:
            return  # keine Sequenz → nichts zu spiegeln, Zustand bleibt
        old_offsets = self._pre_dynamic["offsets"]
        base_sections = self._pre_dynamic["sections"]
        pristine = self._pre_dynamic["document"]

        # Zu ersetzen ist der INHALT jeder Figur AB DER ZEILE NACH der Ueberschrift
        # (l0 ist die "FIGURE"-Kopfzeile, die bewusst stehen bleibt). Der
        # Inhaltsbereich (l0+1 .. l1) wird durch die Sequenz-Calls getauscht.
        #
        # BL-200: Endet ein FIGURE-Block nicht mit dem letzten Tanz-Call, sondern
        # mit angehaengtem Gesangstext (laeuft, waehrend die Taenzer nach Hause
        # promenieren), soll dieser Text erhalten bleiben. Wir ersetzen daher nur
        # bis zur letzten "...promenade"-Zeile (call_end); die Zeilen danach bis
        # key[1] bleiben stehen. Blockgrenzen und Sync-Anker aendern sich NICHT —
        # der Ende-Anker liegt weiter auf key[1] (jetzt hinter dem Ersetzungs-
        # bereich) und wird nur um den Zeilenversatz verschoben. Dadurch ruht die
        # Anzeige waehrend des Schluss-Gesangs unveraendert an ihrer Stelle
        # (Option B: nur der ersetzte Textbereich wird kuerzer, nicht das Timing).
        base_lines = pristine.toPlainText().split("\n")  # alte Zeilen == old_offsets
        edits = []  # (content_l0, call_end, calls) — Original-Zeilen
        # intern#127: je Block normal oder mit getauschten Heads/Sides
        flags = self._dyn_invert_flags()
        self._dyn_invert_state = flags
        inverted = heads_sides.invert_sequence(calls) if any(flags) else calls
        for key, inv in zip(self._dyn_block_keys, flags):
            cl0 = key[0] + 1
            if cl0 > key[1]:
                continue  # Block ist nur die Ueberschrift → nichts zu ersetzen
            call_end = self._resolve_block_cut(key[0], key[1], base_lines,
                                               base_sections)
            edits.append((cl0, call_end, inverted if inv else calls))

        clone = pristine.clone(self._browser)
        for cl0, l1, calls in sorted(edits, key=lambda e: e[0], reverse=True):
            if not calls:
                continue
            start = old_offsets[cl0] if cl0 < len(old_offsets) else clone.characterCount() - 1
            end = (old_offsets[l1 + 1] - 1 if l1 + 1 < len(old_offsets)
                   else clone.characterCount() - 1)
            start = max(0, min(start, clone.characterCount() - 1))
            end = max(start, min(end, clone.characterCount() - 1))
            cur = QTextCursor(clone)
            cur.setPosition(start)
            # Format der Einfuegestelle uebernehmen (Font/Farbe passen zum Lyric),
            # aber die HINTERGRUNDFARBE entfernen: sonst erbt die Sequenz einen
            # Highlight-/Marker-Hintergrund (z.B. rosa), wo im File eine Faerbung
            # beginnt. So wird der eingefuegte Text immer ohne Hintergrund gezeigt.
            ins_fmt = QTextCharFormat(cur.charFormat())
            ins_fmt.clearBackground()
            cur.setPosition(end, QTextCursor.KeepAnchor)
            cur.insertText("\n".join(calls), ins_fmt)

        self._browser.setDocument(clone)
        self._dynamic_document = clone

        # Zeilentabelle + Zeilen-Nachfuehrung. Die Kopfzeile l0 liegt VOR dem
        # Ersetzungsbereich und wird darum wie normaler Text verschoben — dadurch
        # bleibt sie in Sections wie Ankern korrekt erhalten, ohne Sonderfall.
        self._rebuild_line_offsets()
        reps = [(cl0, l1, len(calls)) for (cl0, l1, calls) in edits]
        remap = self._make_line_remap(reps)

        new_sections = {sname: (remap(a), remap(b))
                        for sname, (a, b) in base_sections.items()}
        self._lyric_sections = new_sections

        last_line = len(self._line_offsets) - 1
        dyn = []
        for sec, p in self._sync_anchors:
            old_line = self._char_to_line_in(old_offsets, p)
            new_line = min(remap(old_line), last_line)
            dyn.append([sec, self._line_offsets[new_line]])
        self._dynamic_anchors = dyn

        self._recache_original_sizes_scaled(self._dyn_factor)
        # Groessen-Stabilisator: der Klon traegt die Schriftgroesse vom
        # Einschalt-Zeitpunkt. Hat sich der Zoom seitdem geaendert (Auto-Size,
        # Auto-Breite, manuell), die AKTUELLE Groesse wieder anwenden, sonst
        # springt der Text bei jedem Neu-Rendern (Sequenz-/Tauschwechsel).
        self._set_font_size(self._current_font_size)
        self._scroll_last_val = -1
        try:
            vp = self._browser.viewport().height()
            self._auto_scroll_active = self._browser.document().size().height() > vp
        except Exception:
            pass
        self.refresh_section_overlay()
        self._refresh_band_after_render()

    @staticmethod
    def _char_to_line_in(offsets: list, char_pos: int) -> int:
        import bisect
        if not offsets:
            return 0
        return max(0, bisect.bisect_right(offsets, int(char_pos)) - 1)

    def _apply_dynamic(self):
        """Schaltet Dynamic Lyrics ein: baut die Figuren-Teil-Zeitachse aus den
        SyncPoints auf, merkt das PRISTINE Original als Basis und spiegelt die
        AKTUELLE Sequenz des Sequence-Views. Ab dann blaettert _dynamic_tick()
        (Option 2) das Sequence-View an jeder Figuren-Teil-Grenze weiter, und der
        Lyric-Text folgt ueber refresh_dynamic_from_sequence()."""
        figures = self._figures_present()
        if not figures:
            return
        # BL-182: Ist im Sequence-View der Zufallsmodus an, auch die ERSTE Sequenz
        # mischen (sonst startet Dynamic Lyrics immer auf der deterministischen Nr. 1).
        # No-Op, wenn Shuffle aus. Muss VOR dem Lesen der aktuellen Sequenz laufen.
        if callable(self.randomize_start_sequence_view):
            self.randomize_start_sequence_view()
        calls = self._current_sequence_calls()
        if not calls:
            return

        old_offsets = list(self._line_offsets)
        self._dyn_factor = (self._current_font_size / self._base_font_size
                            if self._base_font_size > 0 else 1.0)

        # Qt loescht das bisherige Dokument bei setDocument(), wenn es Kind des
        # Editors ist. Vorher umhaengen, damit das PRISTINE Original als Basis
        # fuer alle spaeteren Rebuilds erhalten bleibt.
        orig_doc = self._browser.document()
        orig_doc.setParent(self)
        self._pre_dynamic = {
            "document": orig_doc,
            "sizes": list(self._original_sizes),
            "sections": dict(self._lyric_sections),
            "offsets": old_offsets,
        }

        # Eindeutige Figuren-Bloecke (Doppelungen aus einem gemeinsamen
        # FIGURE-Block zusammenfassen), Reihenfolge nach Textzeile.
        self._dyn_block_keys = []
        figs_by_key = {}
        for name, rng in figures:
            key = (int(rng[0]), int(rng[1]))
            if key not in figs_by_key:
                figs_by_key[key] = []
                self._dyn_block_keys.append(key)
            figs_by_key[key].append(self._DYNAMIC_FIGURES.index(name) + 1)
        # intern#127: welche Figuren (1..4) ein Block darstellt
        self._dyn_block_figs = [tuple(sorted(figs_by_key[k]))
                                for k in self._dyn_block_keys]

        # Figuren-Teil-Startzeiten aus den SyncPoints ableiten. Der Auto-Sync
        # legt pro Teil ZWEI Anker an (Block-Anfang bei s_char, Block-Ende bei
        # e_char, siehe _finish_auto_calc). Nur der Anker auf der ERSTEN
        # Blockzeile (== key[0]) ist ein Teil-START — der Ende-Anker liegt auf
        # der letzten Blockzeile. So zaehlen wir vier Durchgaenge statt acht.
        part_list = []  # (start_time,)
        for sec, p in self._sync_anchors:
            line = self._char_to_line_in(old_offsets, p)
            for key in self._dyn_block_keys:
                if line == key[0]:
                    part_list.append(float(sec))
                    break
        self._dyn_part_starts = sorted(part_list)

        self._dyn_render_pending = False
        self._dyn_advance_pending = False
        # Kein rueckwirkendes Vorblaettern: der aktuelle Teil zaehlt als "schon
        # erreicht", weitergeblaettert wird erst beim naechsten Teil.
        self._dyn_rendered_part = self._dynamic_current_part(self._sync_last_pos)
        self._dynamic_enabled = True

        # Edit-Button sperren, solange getauschter Text sichtbar ist. Der
        # Sync-Button bleibt bewusst klickbar (Issue #63): beim Einschalten des
        # Sync-Modus wird Dynamic in _on_sync_toggled sauber abgeschaltet und
        # nach dem Verlassen automatisch wieder angewandt.
        self._btn_edit.setEnabled(False)

        # Aktuelle Sequenz sofort spiegeln (nicht deferred — beim Klick sichtbar).
        self._dynamic_build_document(calls)

    def _revert_dynamic(self):
        """Stellt das Original-Dokument samt Sections/Anker/Zoom-Cache wieder her."""
        if not self._dynamic_enabled or not self._pre_dynamic:
            self._reset_dynamic_state()
            return
        snap = self._pre_dynamic
        self._browser.setDocument(snap["document"])
        # Original wieder dem Editor unterstellen, damit es beim naechsten
        # Laden reguelaer aufgeraeumt wird (kein haengendes Kind an self).
        snap["document"].setParent(self._browser)
        self._original_sizes = snap["sizes"]
        self._lyric_sections = snap["sections"]
        self._line_offsets = snap["offsets"]
        # Aktuellen Zoom behalten statt auf den Stand beim Einschalten zu springen
        self._set_font_size(self._current_font_size)
        self._reset_dynamic_state()
        self._scroll_last_val = -1
        try:
            self._btn_sync.setEnabled(True)
            self._btn_edit.setEnabled(True)
        except Exception:
            pass
        self.refresh_section_overlay()
        self._refresh_band_after_render()

    def _reset_dynamic_state(self):
        """Setzt nur die Dynamic-Flags/Referenzen zurueck (ohne Dokumentwechsel).

        Wird beim Datei-/Songwechsel aufgerufen: das getauschte Dokument wird
        dort ohnehin durch das frisch geladene ersetzt.
        """
        self._dynamic_enabled = False
        self._dynamic_document = None
        self._dynamic_anchors = None
        self._pre_dynamic = None
        self._dyn_part_starts = []
        self._dyn_block_keys = []
        self._dyn_block_figs = []
        self._dyn_invert_state = ()
        self._dyn_rendered_part = 0
        self._dyn_render_pending = False
        self._dyn_advance_pending = False
        # _dynamic_wanted bewusst NICHT zuruecksetzen — es ueberlebt den
        # Songwechsel, damit Dynamic beim naechsten Song automatisch wieder greift.

    def _make_line_remap(self, reps: list):
        """Erzeugt eine Funktion alte_Zeile → neue_Zeile fuer die getauschten
        Figuren. Zeilen vor einer Figur bleiben (bis auf den kumulierten
        Versatz) gleich; figur-interne Zeilen werden proportional auf den neuen
        (evtl. laengeren/kuerzeren) Block verteilt — damit ein Ende-SyncPoint
        auch ans neue Blockende zeigt und lange Sequenzen im Zeitfenster
        durchscrollen statt oben festzukleben."""
        ordered = sorted(reps, key=lambda r: r[0])

        def remap(line: int) -> int:
            delta = 0
            for (l0, l1, newcount) in ordered:
                oldcount = l1 - l0 + 1
                if line < l0:
                    return line + delta
                if l0 <= line <= l1:
                    span = l1 - l0
                    frac = (line - l0) / span if span > 0 else 0.0
                    return (l0 + delta) + int(round(frac * max(0, newcount - 1)))
                delta += newcount - oldcount
            return line + delta

        return remap

    def _recache_original_sizes_scaled(self, factor: float):
        """Wie _cache_original_sizes, rechnet aber den aktuellen Zoom-Faktor
        heraus, damit die Basis wieder die UNskalierten Groessen enthaelt."""
        if not factor or factor <= 0:
            factor = 1.0
        self._original_sizes = []
        doc = self._browser.document()
        block = doc.begin()
        while block.isValid():
            it = block.begin()
            while not it.atEnd():
                frag = it.fragment()
                if frag.isValid():
                    pt = frag.charFormat().fontPointSize()
                    if pt and pt > 0:
                        self._original_sizes.append(
                            (frag.position(), frag.length(), float(pt) / factor))
                it += 1
            block = block.next()

    def _active_anchors(self) -> list:
        """SyncPoints, die das Auto-Scroll gerade nutzt (dynamisch oder Original)."""
        if self._dynamic_enabled and self._dynamic_anchors is not None:
            return self._dynamic_anchors
        return self._sync_anchors

    def _sync_key_prefix(self) -> str:
        return f"lyric_sync_m{self._sync_music_slot}_l{self._sync_lyric_slot}_"

    def _load_sync_anchors(self):
        """Laedt die Anker der aktuellen (Musik x Lyric)-Kombi aus song_properties
        in den Cache. Kein DB-Zugriff im Scroll-Hotpath — nur hier beim Laden."""
        self._sync_anchors = []
        if self._db and self._sync_song_id:
            try:
                props = self._db.get_properties(self._sync_song_id)
            except Exception:
                props = None
            if props:
                prefix = self._sync_key_prefix()
                for key, value in props.items():
                    if not key.startswith(prefix):
                        continue
                    try:
                        sec_s, block_s = value.split("|", 1)
                        self._sync_anchors.append([float(sec_s), int(block_s)])
                    except (ValueError, AttributeError):
                        continue
                self._sync_anchors.sort(key=lambda a: a[0])
        self._apply_sync_button_style()

    def _persist_sync_anchors(self):
        """Schreibt den Anker-Cache als durchnummerierte song_properties-Keys."""
        if self._db and self._sync_song_id:
            try:
                props = self._db.get_properties(self._sync_song_id)
                prefix = self._sync_key_prefix()
                # Alte Keys dieser Kombi entfernen
                for key in list(props.keys()):
                    if key.startswith(prefix):
                        self._db.set_property(self._sync_song_id, key, "")
                # Neu durchnummeriert schreiben (Zeit-sortiert)
                for idx, (sec, block) in enumerate(
                        sorted(self._sync_anchors, key=lambda a: a[0]), start=1):
                    self._db.set_property(
                        self._sync_song_id, f"{prefix}{idx}", f"{sec:.2f}|{int(block)}")
            except Exception as e:
                print(f"[BL-160] Sync-Punkte speichern fehlgeschlagen: {e}")
        # Songstart bleibt an den fruehesten SyncPoint gekoppelt (siehe unten).
        self._couple_song_start_to_anchor()
        self._apply_sync_button_style()

    def _couple_song_start_to_anchor(self):
        """Haelt den Musik-Startpunkt (singing_start) an den fruehesten SyncPoint
        gekoppelt: Beginn des Openers und Songstart wandern gemeinsam — auch fuer
        Singing Calls korrekt. Wird nach jeder Anker-Aenderung aus
        _persist_sync_anchors aufgerufen (Shift, Einzel-Move, Loeschen, Zeit-Edit,
        Catch). Nur wenn fuer diese Musik-Variante bereits ein Startpunkt gesetzt
        ist — ohne Start (z. B. Patter ohne Body) wird keiner erfunden."""
        if not self._db or not self._sync_song_id or not self._sync_anchors:
            return
        key = f"singing_start_m{self._sync_music_slot}"
        try:
            props = self._db.get_properties(self._sync_song_id)
        except Exception:
            return
        if not props.get(key):          # nicht gesetzt/leer → nichts koppeln
            return
        first = min(a[0] for a in self._sync_anchors)
        try:
            if abs(float(props[key]) - first) < 0.005:
                return                  # schon deckungsgleich → kein Write/Refresh
        except (ValueError, TypeError):
            pass
        try:
            self._db.set_property(self._sync_song_id, key, f"{first:.2f}")
        except Exception as e:
            print(f"[sync] Songstart koppeln fehlgeschlagen: {e}")
            return
        # Start-Countdown zieht mit: Cache aktiv invalidieren.
        if callable(getattr(self, "on_singing_marks_changed", None)):
            self.on_singing_marks_changed()

    def _shift_song_end(self, delta: float):
        """Verschiebt den gespeicherten Musik-Endpunkt (singing_end) um delta
        Sekunden — das Gegenstueck zum gekoppelten Start beim 'Alle verschieben'.
        Nur wenn ein Ende gesetzt ist; nie unter 0."""
        if not self._db or not self._sync_song_id:
            return
        key = f"singing_end_m{self._sync_music_slot}"
        try:
            props = self._db.get_properties(self._sync_song_id)
            cur = props.get(key)
            if not cur:
                return
            new_end = max(0.0, float(cur) + delta)
            self._db.set_property(self._sync_song_id, key, f"{new_end:.2f}")
        except Exception as e:
            print(f"[sync] Song-Ende verschieben fehlgeschlagen: {e}")

    def _shift_all_anchors(self, delta: float):
        """Verschiebt ALLE SyncPoints gemeinsam um delta Sekunden (nie unter 0).
        Das Song-Ende wandert parallel mit; der Songstart wird von
        _persist_sync_anchors selbst an den fruehesten Anker gekoppelt — Start,
        alle SyncPoints und Ende bewegen sich also gemeinsam.

        Gemeinsame Logik fuer das Kontextmenue 'Alle verschieben' UND die
        Sync-Toolbar-Buttons '−1 s' / '+1 s' (BL-171) — keine Redundanz."""
        if not self._sync_anchors:
            return
        for a in self._sync_anchors:
            a[0] = max(0.0, a[0] + delta)
        self._shift_song_end(delta)
        self._persist_sync_anchors()
        self._render_sync_markers()

    @staticmethod
    def _fmt_mmss(sec: float) -> str:
        sec = max(0, int(round(sec)))
        return f"{sec // 60}:{sec % 60:02d}"

    def _on_sync_toggled(self, checked: bool):
        if checked and not self._lyrics_loaded:
            # Kein Lyric geladen → Toggle zuruecknehmen
            self._btn_sync.blockSignals(True)
            self._btn_sync.setChecked(False)
            self._btn_sync.blockSignals(False)
            return

        # Issue #63: Dynamic Lyrics und Sync-Bearbeitung schliessen sich aus.
        # Beim Einschalten Dynamic VOR dem Sync-Dialog sauber abschalten, damit
        # die Erkennung/Bearbeitung auf dem Originaltext laeuft. Der Wunsch
        # (_dynamic_wanted) bleibt erhalten → nach Verlassen des Sync-Modus wird
        # Dynamic via update_dynamic_button_state automatisch wieder angewandt.
        if checked and self._dynamic_enabled:
            self._revert_dynamic()
            self._btn_dynamic.blockSignals(True)
            self._btn_dynamic.setChecked(False)
            self._btn_dynamic.blockSignals(False)

        # BL-161: Erster Sync an diesem Song (noch keine Punkte) → Methode abfragen
        auto = False
        auto_saved_start = None
        auto_saved_end = None
        request_detect = False
        if checked and not self._sync_anchors:
            saved = self._load_saved_start_end()
            if saved:
                choice = self._ask_sync_method_with_saved(*saved)
            else:
                choice = self._ask_sync_method()
            if choice == "cancel":
                self._btn_sync.blockSignals(True)
                self._btn_sync.setChecked(False)
                self._btn_sync.blockSignals(False)
                # Sync doch nicht betreten → zuvor abgeschaltetes Dynamic
                # (Issue #63) wieder anwenden, falls weiterhin gewuenscht.
                self._reapply_dynamic_if_wanted()
                return
            if choice == "auto_saved":
                auto_saved_start, auto_saved_end = saved
            elif choice == "detect":
                request_detect = True
            else:
                auto = (choice == "auto")

        self._sync_mode = checked
        self._sync_move_anchor = None
        self._apply_sync_button_style()
        # BL-171: ±1-Sekunde-Buttons nur im Sync-Modus zeigen.
        self._btn_sync_shift_earlier.setVisible(checked)
        self._btn_sync_shift_later.setVisible(checked)
        # Rules + History im Sync-Modus abschalten (Testlauf ohne Nebenwirkungen)
        if self.on_sync_mode_changed:
            self.on_sync_mode_changed(checked)
        if checked:
            if auto_saved_start is not None:
                self._finish_auto_calc(auto_saved_start, auto_saved_end)
            elif request_detect:
                # Automatische Erkennung anfordern (laeuft im Worker-Thread des
                # Hauptfensters; Ergebnis kommt via apply_detected_body zurueck).
                if self.on_request_body_detect:
                    self._label_status.setText(_t("lyric_sync_detecting"))
                    self.on_request_body_detect()
                else:
                    self._enter_auto_calc()   # Fallback: manuelle 2-Klick-Methode
            elif auto:
                self._enter_auto_calc()
            else:
                self._render_sync_markers()
                self._label_status.setText(_t("lyric_sync_hint"))
        else:
            self._exit_auto_calc()
            self._clear_sync_markers()
        # BL-171: Der Abschnittsstreifen haengt am Sync-Modus. Sichtbarkeit und
        # Positionen nach JEDEM Umschalten neu setzen — unabhaengig davon, ueber
        # welchen Zweig (Auto-Erkennung, manuelles Setzen, Verlassen).
        self.refresh_section_overlay()
        # BL-173: Dynamic Lyrics ist im Sync-Modus nicht nutzbar → Button-Status
        self.update_dynamic_button_state()

    # --- BL-161: Automatische Abschnitts-Berechnung (2 Klicks → 7 Teile) ---

    def _load_saved_start_end(self):
        """Laedt gespeicherte singing_start/singing_end fuer die aktuelle Musik-Variante.
        Gibt (start_sec, end_sec) zurueck oder None wenn nicht vorhanden."""
        if not self._db or not self._sync_song_id:
            return None
        try:
            props = self._db.get_properties(self._sync_song_id)
        except Exception:
            return None
        k_start = f"singing_start_m{self._sync_music_slot}"
        k_end = f"singing_end_m{self._sync_music_slot}"
        if k_start not in props or k_end not in props:
            return None
        try:
            return float(props[k_start]), float(props[k_end])
        except (ValueError, TypeError):
            return None

    def _ask_sync_method_with_saved(self, start: float, end: float) -> str:
        """Dialog wenn bereits Start/Ende gespeichert sind.
        Rueckgabe: 'auto_saved' | 'auto' | 'manual' | 'cancel'."""
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Question)
        box.setWindowTitle(_t("lyric_sync_choice_title"))
        box.setText(_t("lyric_sync_choice_text_saved").format(
            start=self._fmt_mmss(start), end=self._fmt_mmss(end)))
        b_saved = box.addButton(_t("lyric_sync_choice_use_saved"), QMessageBox.AcceptRole)
        b_detect = box.addButton(_t("lyric_sync_choice_detect"), QMessageBox.ActionRole)
        b_remeasure = box.addButton(_t("lyric_sync_choice_remeasure"), QMessageBox.ActionRole)
        box.addButton(_t("lyric_sync_choice_manual"), QMessageBox.ActionRole)
        b_cancel = box.addButton(QMessageBox.Cancel)
        box.setDefaultButton(b_saved)
        box.exec()
        clicked = box.clickedButton()
        if clicked is b_saved:
            return "auto_saved"
        if clicked is b_detect:
            return "detect"
        if clicked is b_remeasure:
            return "auto"
        if clicked is b_cancel or clicked is None:
            return "cancel"
        return "manual"

    def _ask_sync_method(self) -> str:
        """Fragt beim ersten Sync, ob die Abschnitte automatisch berechnet werden
        sollen. Rueckgabe: 'auto' | 'manual' | 'cancel'."""
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Question)
        box.setWindowTitle(_t("lyric_sync_choice_title"))
        box.setText(_t("lyric_sync_choice_text"))
        b_detect = box.addButton(_t("lyric_sync_choice_detect"), QMessageBox.AcceptRole)
        b_auto = box.addButton(_t("lyric_sync_choice_auto"), QMessageBox.ActionRole)
        box.addButton(_t("lyric_sync_choice_manual"), QMessageBox.ActionRole)
        b_cancel = box.addButton(QMessageBox.Cancel)
        box.setDefaultButton(b_detect)
        box.exec()
        clicked = box.clickedButton()
        if clicked is b_detect:
            return "detect"
        if clicked is b_auto:
            return "auto"
        if clicked is b_cancel or clicked is None:
            return "cancel"
        return "manual"

    # Ein Singing-Call-Body ist starr 7×64 = 448 Beats. Damit ist das Ende durch
    # Startpunkt + BPM determiniert — der Ende-Klick ist nur noch optionaler
    # Feinschliff (Tempo-Drift / ungenaue BPM), keine Pflicht mehr.
    _SINGING_BODY_BEATS = 448

    def _sync_song_bpm(self) -> float:
        """Base-BPM des gerade gesyncten Songs (fuer die Ende-Ableitung)."""
        if not self._db or not self._sync_song_id:
            return 0.0
        try:
            song = self._db.get_by_id(self._sync_song_id)
            return float(getattr(song, "base_bpm", 0) or 0)
        except Exception:
            return 0.0

    def _enter_auto_calc(self):
        """Startet die Erfassung. Mit hinterlegter BPM genuegt der Startpunkt
        (Beat 1) — das Ende wird aus 448 Beats abgeleitet. Ohne BPM Fallback auf
        die alte 2-Klick-Methode (Start + Ende manuell)."""
        self._auto_calc_active = True
        self._auto_refine_mode = False
        self._auto_start_sec = None
        self._auto_end_sec = None
        has_bpm = self._sync_song_bpm() > 0
        self._btn_sync_start.setVisible(True)
        self._btn_sync_end.setVisible(not has_bpm)   # Ende nur im BPM-losen Fallback
        self._label_sync_time.setVisible(True)
        self._update_auto_buttons()
        self._label_status.setText(_t("lyric_sync_auto_hint" if has_bpm
                                      else "lyric_sync_auto_hint_manual"))

    def _enter_refine_end(self, start: float):
        """Optionaler Feinschliff nach der 1-Klick-Ableitung: nur das Ende manuell
        markieren, um den aus der BPM berechneten Wert zu ersetzen (praeziser bei
        Tempo-Drift oder ungenauer BPM)."""
        self._auto_calc_active = True
        self._auto_refine_mode = True
        self._auto_start_sec = start
        self._auto_end_sec = None
        self._btn_sync_start.setVisible(False)
        self._btn_sync_end.setVisible(True)
        self._label_sync_time.setVisible(True)
        self._update_auto_buttons()
        self._label_status.setText(_t("lyric_sync_refine_hint"))

    def _exit_auto_calc(self):
        """Blendet die Erfassungs-Bedienelemente wieder aus."""
        self._auto_calc_active = False
        self._btn_sync_start.setVisible(False)
        self._btn_sync_end.setVisible(False)
        self._label_sync_time.setVisible(False)

    def _update_auto_buttons(self):
        """Zeigt gesetzte Start/Ende-Werte als Haken am jeweiligen Button."""
        s, e = self._auto_start_sec, self._auto_end_sec
        self._btn_sync_start.setText(
            _t("btn_sync_set_start") + (f"  ✓ {self._fmt_mmss(s)}" if s is not None else ""))
        self._btn_sync_end.setText(
            _t("btn_sync_set_end") + (f"  ✓ {self._fmt_mmss(e)}" if e is not None else ""))

    def _on_auto_set_start(self):
        self._auto_start_sec = float(self._sync_last_pos)
        self._update_auto_buttons()
        if getattr(self, "_auto_refine_mode", False):
            return   # im Feinschliff-Modus zaehlt nur der Ende-Klick
        bpm = self._sync_song_bpm()
        if bpm > 0:
            # Ende deterministisch aus 448 Beats (7×64) ableiten → ein Klick reicht.
            end = self._auto_start_sec + self._SINGING_BODY_BEATS * (60.0 / bpm)
            self._finish_auto_calc(self._auto_start_sec, end, derived=True)
        else:
            self._maybe_finish_auto_calc()   # Fallback ohne BPM: manuelles Ende

    def _on_auto_set_end(self):
        self._auto_end_sec = float(self._sync_last_pos)
        self._update_auto_buttons()
        if getattr(self, "_auto_refine_mode", False) and \
                self._auto_start_sec is not None:
            # Feinschliff: manuelles Ende ersetzt den berechneten Wert.
            start, end = self._auto_start_sec, self._auto_end_sec
            self._auto_refine_mode = False
            self._finish_auto_calc(min(start, end), max(start, end), derived=False)
            return
        self._maybe_finish_auto_calc()

    def _maybe_finish_auto_calc(self):
        """Sobald Start UND Ende gesetzt sind: validieren und berechnen."""
        if self._auto_start_sec is None or self._auto_end_sec is None:
            return
        start = min(self._auto_start_sec, self._auto_end_sec)
        end = max(self._auto_start_sec, self._auto_end_sec)
        if end - start < 7.0:
            # < 1 s pro Teil ist unrealistisch → Eingabe verwerfen
            QMessageBox.warning(self, _t("lyric_sync_choice_title"),
                                _t("lyric_sync_auto_invalid"))
            self._auto_start_sec = None
            self._auto_end_sec = None
            self._update_auto_buttons()
            return
        self._finish_auto_calc(start, end)

    def _finish_auto_calc(self, start: float, end: float, derived: bool = False):
        """Speichert Start/Ende am Song und berechnet die 7 Abschnitts-Grenzen.

        derived=True: das Ende wurde aus 448 Beats abgeleitet (1-Klick-Weg); der
        Ergebnisdialog bietet dann optional eine Ende-Feinjustierung an.

        Stufe A (BL-161): Zeitraster + Persistenz + Verifikation. Die Zuordnung
        der 14 Zeit↔Zeile-Anker (Anfang/Ende je Block) folgt in Stufe B, sobald
        der Keyword-Scan die Block-Positionen im Text liefert.
        """
        # Start/Ende als Song-Info sichern — an die Musik-Variante gebunden,
        # da es eine Eigenschaft dieser Aufnahme ist (nicht der Lyric-Variante).
        if self._db and self._sync_song_id:
            try:
                self._db.set_property(
                    self._sync_song_id,
                    f"singing_start_m{self._sync_music_slot}", f"{start:.2f}")
                self._db.set_property(
                    self._sync_song_id,
                    f"singing_end_m{self._sync_music_slot}", f"{end:.2f}")
                # To-Do-Marker abraeumen: hat der Batch diesen Song als unsicher
                # mit dem Genre "CHECK: START" geflaggt, ist er jetzt manuell
                # bestaetigt/korrigiert → Marker entfernen (Liste leert sich).
                gid = self._db.get_genre_id_by_name(CHECK_START_GENRE_NAME)
                if gid and gid > 0:
                    self._db.remove_song_genre(self._sync_song_id, gid)
            except Exception as e:
                print(f"[BL-161] Start/Ende speichern fehlgeschlagen: {e}")

        # Der Start-Countdown im Hauptfenster cached singing_start und leert den
        # Cache nur bei Song-Wechsel. Nach dem Neusetzen (ohne Songwechsel) wuerde
        # er sonst weiter zum ALTEN Start zaehlen → Cache aktiv invalidieren.
        if callable(getattr(self, "on_singing_marks_changed", None)):
            self.on_singing_marks_changed()

        # 7 gleich lange Abschnitte (64 Beats je Teil)
        seg = (end - start) / 7.0

        # Stufe B: Textbloecke je Teil aus den Ueberschriften ermitteln.
        text = self._browser.document().toPlainText()
        try:
            sections = singing_sections.load_sections(self._section_lists_path())
        except Exception:
            sections = None
        res = singing_sections.parse_sections(text, sections)

        self._exit_auto_calc()

        if not res.ok:
            # Keine belastbaren Abschnitte erkannt → ehrlich melden, manuell weiter.
            print(f"[BL-161] Auto-Sync: keine Abschnitte erkannt ({res.reason})")
            QMessageBox.information(self, _t("lyric_sync_auto_done_title"),
                                    _t("lyric_sync_auto_fail_msg"))
            self._label_status.setText(_t("lyric_sync_hint"))
            return

        # 14 Anker bauen (Anfang + Ende je Teil). Teile ohne eigenen Textblock
        # bekommen keine eigene Marke: die Anzeige bleibt an der zuletzt
        # erreichten Position stehen ("kein Sprung"), bis die naechste Marke kommt.
        anchors = []
        last_end = None
        held = []
        for k in range(7):
            part = k + 1
            t0 = start + k * seg
            t1 = start + (k + 1) * seg
            blk = res.parts.get(part)
            if blk:
                s_char, e_char = blk
                anchors.append([t0, int(s_char)])
                anchors.append([max(t0, t1 - 1.0), int(e_char)])
                last_end = int(e_char)
            elif last_end is not None:
                anchors.append([t0, last_end])
                anchors.append([t1, last_end])
                held.append(part)
            else:
                held.append(part)

        # BL-171: Tag ist das Outro — er beginnt dort, wo der Closer endet.
        # Additional Lyrics bekommen bewusst KEINEN Anker: sie laufen nicht im
        # Zeitraster mit, sondern grenzen nur den Block davor ab.
        tag_blk = (res.extras or {}).get("tag")
        if tag_blk:
            anchors.append([end, int(tag_blk[0])])

        self._sync_anchors = anchors
        self._persist_sync_anchors()
        # Abschnitte dauerhaft am Song sichern — Quelle fuer das Overlay.
        # `text` ist derselbe Plain-Text, auf dem parse_sections lief.
        self.store_sections_from_result(res, text)
        if self._sync_mode:
            self._render_sync_markers()

        held_str = ", ".join(str(p) for p in held) if held else "—"
        print(f"[BL-161] Auto-Sync ok: Start={start:.2f}s Ende={end:.2f}s "
              f"detected={sorted(res.detected)} filled={sorted(res.filled)} "
              f"held={held} anker={len(anchors)}")
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Information)
        box.setWindowTitle(_t("lyric_sync_auto_done_title"))
        box.setText(_t("lyric_sync_auto_ok_msg").format(
            start=self._fmt_mmss(start), end=self._fmt_mmss(end),
            detected=len(res.detected), held=held_str))
        box.addButton(QMessageBox.Ok)
        # Nur beim abgeleiteten Ende: optionaler Feinschliff (echtes Ende setzen).
        b_refine = (box.addButton(_t("lyric_sync_refine_end"), QMessageBox.ActionRole)
                    if derived else None)
        box.exec()
        if b_refine is not None and box.clickedButton() is b_refine:
            self._enter_refine_end(start)
            return
        self._label_status.setText(_t("lyric_sync_hint"))

    def apply_detected_body(self, result: dict):
        """Empfaengt das Ergebnis der automatischen Body-Erkennung (Worker,
        vom Hauptfenster gestartet) und zeigt es als VORSCHLAG zur Bestaetigung.
        Kein stilles Schreiben — der Nutzer uebernimmt, korrigiert selbst oder
        bricht ab."""
        if not self._sync_mode:
            return   # Nutzer hat den Sync-Modus inzwischen verlassen
        if not result or not result.get("ok"):
            reason = (result or {}).get("reason", "")
            QMessageBox.information(self, _t("lyric_sync_choice_title"),
                                    _t("lyric_sync_detect_failed").format(reason=reason))
            self._enter_auto_calc()   # Fallback: manuelle 2-Klick-Methode
            return

        start = float(result["start_sec"])
        end = float(result["end_sec"])
        # Mehrdeutigkeits-Flag aus dem Detektor: zeigen drei unabhaengige
        # Verfahren (Kamm-Kante, Timbre-Kohaerenz, Break/Figur-Kontrast) auf
        # weit auseinanderliegende Offsets, ist die Stelle mehrdeutig. Der
        # fruehere Kamm-Margin taugte dafuer NICHT (bei Fehlern selbstsicher).
        ambiguous = bool(result.get("ambiguous", False))
        text = _t("lyric_sync_detect_result").format(
            start=self._fmt_mmss(start), end=self._fmt_mmss(end))
        # Dem Nutzer immer ehrlich melden, ob die Erkennung sicher oder
        # unsicher war (Davids Wunsch).
        text += "\n\n" + _t("lyric_sync_detect_lowconf" if ambiguous
                            else "lyric_sync_detect_confident")

        box = QMessageBox(self)
        box.setIcon(QMessageBox.Warning if ambiguous else QMessageBox.Question)
        box.setWindowTitle(_t("lyric_sync_choice_title"))
        box.setText(text)
        b_use = box.addButton(_t("lyric_sync_detect_use"), QMessageBox.AcceptRole)
        b_manual = box.addButton(_t("lyric_sync_detect_manual"), QMessageBox.ActionRole)
        b_cancel = box.addButton(QMessageBox.Cancel)
        # Bei Mehrdeutigkeit ist "Selbst setzen" der sicherere Default.
        box.setDefaultButton(b_manual if ambiguous else b_use)
        box.exec()
        clicked = box.clickedButton()
        if clicked is b_use:
            self._finish_auto_calc(start, end)
        elif clicked is b_manual:
            self._enter_auto_calc()
        else:
            self._btn_sync.setChecked(False)   # Abbrechen → Sync-Modus zuruecknehmen

    def _section_lists_path(self) -> str:
        """Pfad zur pflegbaren Keyword-Liste der Abschnitts-Erkennung (BL-161)."""
        return os.path.join(perf.app_dir(), "config", "singing_sections.json")

    def _sync_has_start_end(self) -> bool:
        """True wenn fuer die aktuelle Musik-Variante Start UND Ende gesetzt sind."""
        return self._load_saved_start_end() is not None

    def _apply_sync_button_style(self):
        """Faerbt den Sync-Button je nach Fortschritt der aktuellen (Musik x
        Lyric)-Kombi: rot = noch kein einziger Sync-Punkt gesetzt, normal =
        Sync-Modus gerade aktiv (Erfassung laeuft) ODER nur teilweise erfasst,
        gruen = Start+Ende UND mind. 1 Sync-Punkt vorhanden (nichts mehr zu tun)."""
        if not self._skin_mgr:
            self._btn_sync.setStyleSheet("")
            return
        if self._sync_mode:
            self._btn_sync.setStyleSheet("")
            return
        if not self._sync_anchors:
            c = self._skin_mgr.color("warning", "#ef4444")
            ch = self._skin_mgr.color("warning_hover", c)
        elif self._sync_has_start_end():
            c = self._skin_mgr.color("success", "#22c55e")
            ch = self._skin_mgr.color("success_hover", c)
        else:
            # Sync-Punkte vorhanden, aber (noch) kein Start/Ende erfasst
            # (z.B. manueller Modus ohne Auto-Berechnung) — kein Alarm, aber
            # auch nicht "fertig".
            self._btn_sync.setStyleSheet("")
            return
        self._btn_sync.setStyleSheet(
            f"QPushButton {{ background-color: {c}; color: #ffffff; "
            f"font-weight: bold; border: none; }} "
            f"QPushButton:hover {{ background-color: {ch}; }}")

    def _remap_sync_anchors_after_edit(self, old_text: str, new_text: str):
        """Rechnet Sync-Anker nach einem In-App-Text-Edit (Stift-Button) auf die
        neuen Zeichenpositionen um, statt sie beim naechsten Rendern stumpf zu
        verlieren (BL-165). Anker in unveraendert gebliebenen Textabschnitten
        bleiben exakt erhalten, nur Anker auf geloeschten/geaenderten Zeilen
        entfallen — die lassen sich nicht sinnvoll zuordnen."""
        if not self._sync_anchors or old_text == new_text:
            return
        opcodes = difflib.SequenceMatcher(None, old_text, new_text, autojunk=False).get_opcodes()

        def _map_pos(pos):
            for tag, i1, i2, j1, j2 in opcodes:
                if i1 <= pos < i2:
                    return (j1 + (pos - i1)) if tag == "equal" else None
                if pos == i2 == len(old_text):
                    return j2 if tag == "equal" else None
            return None

        remapped = []
        dropped = 0
        for sec, pos in self._sync_anchors:
            new_pos = _map_pos(int(pos))
            if new_pos is None:
                dropped += 1
            else:
                remapped.append([sec, new_pos])
        self._sync_anchors = remapped
        self._persist_sync_anchors()
        if dropped:
            print(f"[BL-165] Sync-Anker nach Edit: {dropped} auf geaenderten/"
                  f"geloeschten Zeilen entfernt, {len(remapped)} erhalten.")

    # --- Umrechnung pristine-Textposition <-> aktuell angezeigte Position ---
    # Die Anker speichern Zeichenpositionen im ORIGINAL-Text (ohne Marker).
    # Marker sind eingefuegter Text, der alle nachfolgenden Positionen nach
    # hinten schiebt. Daher die Umrechnung. Block-Indizes taugen NICHT, weil
    # manche Lyrics (z.B. RTF mit <br>) ein einziger Block mit vielen Zeilen sind.

    def _pristine_to_display(self, p: int) -> int:
        shift = 0
        for mp, ml in sorted(self._marker_inserts):
            if mp <= p:
                shift += ml
            else:
                break
        return p + shift

    def _display_to_pristine(self, d: int) -> int:
        shift = 0
        for mp, ml in sorted(self._marker_inserts):
            disp_start = mp + shift
            if disp_start < d:
                if d < disp_start + ml:
                    return mp  # Klick liegt im Marker → Zeile dieses Markers
                shift += ml
            else:
                break
        return d - shift

    def _line_pos_at(self, event) -> int:
        """Pristine-Zeichenposition des Zeilenanfangs an der Klickposition."""
        try:
            pt = event.position().toPoint()
        except AttributeError:
            pt = event.pos()
        cursor = self._browser.cursorForPosition(pt)
        cursor.movePosition(QTextCursor.StartOfLine)
        return self._display_to_pristine(cursor.position())

    def _anchor_indices_for_pos(self, pos: int) -> list:
        return [i for i, (_sec, p) in enumerate(self._sync_anchors)
                if int(p) == int(pos)]

    def _handle_sync_click(self, event):
        pos = self._line_pos_at(event)
        btn = event.button()

        # Verschiebe-Modus aktiv: naechster Linksklick setzt neue Textzeile
        if btn == Qt.LeftButton and self._sync_move_anchor is not None:
            mv = self._sync_move_anchor
            self._sync_move_anchor = None
            mv[1] = int(pos)
            self._persist_sync_anchors()
            self._render_sync_markers()
            self._label_status.setText(_t("lyric_sync_hint"))
            return

        if btn == Qt.RightButton:
            # Menue immer zeigen — auch auf leerer Stelle (fuer "Alle loeschen")
            self._sync_context_menu(event, self._anchor_indices_for_pos(pos))
            return

        if btn == Qt.LeftButton:
            # Immer einen neuen Anker setzen — auch wenn die Zeile schon welche
            # hat. Wiederholte Sequenzen (4x gesungen, 1x notiert) brauchen
            # mehrere Zeitstempel auf derselben Zeile.
            self._sync_anchors.append([float(self._sync_last_pos), int(pos)])
            self._persist_sync_anchors()
            self._render_sync_markers()

    def _sync_context_menu(self, event, idxs: list):
        menu = QMenu(self)
        actmap = {}

        def _add_actions(target, idx):
            a_time = target.addAction(_t("lyric_sync_set_time"))
            actmap[a_time] = ("time", idx)
            a_catch = target.addAction(_t("lyric_sync_catch_now"))
            actmap[a_catch] = ("catch", idx)
            a_move = target.addAction(_t("lyric_sync_move_line"))
            actmap[a_move] = ("move", idx)
            target.addSeparator()
            a_del = target.addAction(_t("lyric_sync_delete"))
            actmap[a_del] = ("del", idx)

        idxs_sorted = sorted(idxs, key=lambda i: self._sync_anchors[i][0])
        if len(idxs_sorted) == 1:
            _add_actions(menu, idxs_sorted[0])
        elif len(idxs_sorted) > 1:
            # Mehrere Zeitstempel auf einer Zeile → je Zeitstempel ein Untermenue
            for idx in idxs_sorted:
                sub = menu.addMenu(f"⟨{self._fmt_mmss(self._sync_anchors[idx][0])}⟩")
                _add_actions(sub, idx)

        # "Alle verschieben" / "Alle loeschen" — immer verfuegbar, wenn ueberhaupt welche da
        if self._sync_anchors:
            if not menu.isEmpty():
                menu.addSeparator()
            shift_menu = menu.addMenu(_t("lyric_sync_shift_all"))
            a_earlier = shift_menu.addAction(_t("lyric_sync_shift_all_earlier"))
            actmap[a_earlier] = ("shift_all", -1.0)
            a_later = shift_menu.addAction(_t("lyric_sync_shift_all_later"))
            actmap[a_later] = ("shift_all", 1.0)
            a_clear = menu.addAction(_t("lyric_sync_clear_all"))
            actmap[a_clear] = ("clear_all", -1)

        if menu.isEmpty():
            return

        try:
            gpos = event.globalPosition().toPoint()
        except AttributeError:
            gpos = event.globalPos()
        chosen = menu.exec(gpos)
        if chosen is None:
            return
        op, idx = actmap[chosen]
        if op == "clear_all":
            reply = QMessageBox.question(
                self, _t("lyric_sync_clear_all"),
                _t("lyric_sync_clear_all_confirm", count=len(self._sync_anchors)),
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if reply != QMessageBox.Yes:
                return
            self._sync_anchors = []
            self._persist_sync_anchors()
            self._render_sync_markers()
        elif op == "shift_all":
            # idx traegt hier das Delta in Sekunden (-1.0 / +1.0).
            self._shift_all_anchors(float(idx))
        elif op == "del":
            del self._sync_anchors[idx]
            self._persist_sync_anchors()
            self._render_sync_markers()
        elif op == "catch":
            self._sync_anchors[idx][0] = float(self._sync_last_pos)
            self._persist_sync_anchors()
            self._render_sync_markers()
        elif op == "time":
            self._edit_anchor_time(idx)
        elif op == "move":
            self._sync_move_anchor = self._sync_anchors[idx]
            self._label_status.setText(_t("lyric_sync_move_prompt"))

    def _edit_anchor_time(self, anchor_idx: int):
        """Direktes mm:ss-Edit der Ankerzeit."""
        anchor = self._sync_anchors[anchor_idx]
        cur_text = self._fmt_mmss(anchor[0])
        text, ok = QInputDialog.getText(
            self, _t("lyric_sync_set_time"),
            _t("lyric_sync_time_prompt"), text=cur_text)
        if not ok or not text.strip():
            return
        secs = self._parse_mmss(text.strip())
        if secs is None:
            QMessageBox.warning(self, _t("lyric_sync_set_time"),
                                _t("lyric_sync_time_invalid"))
            return
        anchor[0] = float(secs)
        self._persist_sync_anchors()
        self._render_sync_markers()

    @staticmethod
    def _parse_mmss(text: str):
        """'1:23' oder '83' → Sekunden (float). None bei Fehler."""
        text = text.strip()
        try:
            if ":" in text:
                m, s = text.split(":", 1)
                return int(m) * 60 + int(s)
            return int(float(text))
        except (ValueError, TypeError):
            return None

    # ---- Marker-Darstellung (nur im Sync-Modus, nicht persistent) ----

    def _times_for_pos(self, pos: int) -> list:
        return sorted(sec for sec, p in self._sync_anchors if int(p) == int(pos))

    def _marker_text(self, times: list) -> str:
        """Kombinierter Marker fuer eine Zeile, z.B. ' ⟨0:31⟩⟨2:11⟩ '."""
        return " " + "".join(f"⟨{self._fmt_mmss(t)}⟩" for t in times) + " "

    def _render_sync_markers(self):
        """Zeichnet alle Marker frisch: erst alle entfernen, dann je Zeile einen
        kombinierten Marker an der pristine-Position einfuegen. Schiebt dabei die
        Folgepositionen — der akkumulierte Shift wird mitgefuehrt."""
        self._clear_sync_markers()
        if not self._sync_mode or not self._lyrics_loaded:
            # BL-171: Marken sind jetzt weg → Zeichenpositionen haben sich
            # verschoben. Ohne dieses Neuvermessen behielte das Overlay die
            # Positionen MIT Marken und saesse zu tief.
            self.refresh_section_overlay()
            return
        doc = self._browser.document()
        fmt = QTextCharFormat()
        fmt.setBackground(QColor(self._SYNC_MARKER_BG))
        fmt.setForeground(QColor(self._SYNC_MARKER_FG))
        fmt.setFontWeight(QFont.Bold)
        doc_len = doc.characterCount()
        shift = 0
        for pos in sorted(set(int(p) for _s, p in self._sync_anchors)):
            # Gueltigkeit gegen die pristine-Laenge pruefen, NICHT gegen die
            # verschobene Position (#65): doc_len wurde vor der Schleife gemessen,
            # das Dokument waechst aber mit jedem eingefuegten Marker (shift). Ein
            # Vergleich von (pos+shift) gegen das alte doc_len wirft sonst die
            # hintersten Anker faelschlich raus — die Marker der letzten Zeilen
            # langer Songs fehlten dadurch (Anker vorhanden, nur nicht gezeichnet).
            if pos >= doc_len:
                continue  # pristine-Position jenseits des Dokuments — ueberspringen
            actual = pos + shift
            text = self._marker_text(self._times_for_pos(pos))
            cursor = QTextCursor(doc)
            cursor.setPosition(actual)
            cursor.insertText(text, fmt)
            self._marker_inserts.append((int(pos), len(text)))
            shift += len(text)
        # BL-171: eingefuegte Marker verschieben den Text → Flaechen neu setzen
        self.refresh_section_overlay()

    def _clear_sync_markers(self):
        """Entfernt alle Inline-Marker anhand der getrackten Spans (robust ohne
        Fragment-Iteration). Reihenfolge: hinterste Anzeige-Position zuerst."""
        doc = self._browser.document()
        # Anzeige-Positionen aus den pristine-Spans rekonstruieren
        shift = 0
        disp_spans = []
        for mp, ml in sorted(self._marker_inserts):
            disp_spans.append((mp + shift, ml))
            shift += ml
        for d, length in sorted(disp_spans, reverse=True):
            cursor = QTextCursor(doc)
            cursor.setPosition(d)
            cursor.setPosition(d + length, QTextCursor.KeepAnchor)
            cursor.removeSelectedText()
        self._marker_inserts = []
        self._purge_marker_orphans()

    def _purge_marker_orphans(self):
        """Sicherheitsnetz: entfernt alle verbleibenden Marker-formatierten Zeichen,
        die durch fruehere Fehler im Dokument verblieben sind."""
        doc = self._browser.document()
        marker_bg = QColor(self._SYNC_MARKER_BG)
        # Alle zusammenhaengenden Runs mit Marker-Hintergrundfarbe als Spans sammeln
        spans = []
        block = doc.begin()
        while block.isValid():
            it = block.begin()
            while not it.atEnd():
                frag = it.fragment()
                if frag.isValid():
                    if frag.charFormat().background().color() == marker_bg:
                        spans.append((frag.position(), frag.length()))
                it += 1
            block = block.next()
        # Rueckwaerts loeschen, damit Positionen stabil bleiben
        for pos, length in sorted(spans, reverse=True):
            cursor = QTextCursor(doc)
            cursor.setPosition(pos)
            cursor.setPosition(pos + length, QTextCursor.KeepAnchor)
            cursor.removeSelectedText()

    def check_offer_copy_sync(self):
        """Bietet an, Sync-Punkte einer anderen Variante zu uebernehmen, wenn
        die aktuelle (Musik x Lyric)-Kombi noch keine hat. Wird vom Hauptfenster
        nach dem Laden aufgerufen."""
        if not self._db or not self._sync_song_id or not self._lyrics_loaded:
            return
        if self._sync_anchors:
            return  # aktuelle Kombi hat schon Punkte
        try:
            props = self._db.get_properties(self._sync_song_id)
        except Exception:
            return
        import re as _re
        # Andere Kombis mit Sync-Punkten sammeln: (ms, ls) -> Anzahl
        others = {}
        cur = (self._sync_music_slot, self._sync_lyric_slot)
        for key in props:
            m = _re.match(r'^lyric_sync_m(\d+)_l(\d+)_\d+$', key)
            if not m:
                continue
            pair = (int(m.group(1)), int(m.group(2)))
            if pair == cur:
                continue
            others[pair] = others.get(pair, 0) + 1
        if not others:
            return
        # Quelle waehlen: bei genau einer direkt fragen, sonst Auswahl
        pairs = sorted(others.keys())
        if len(pairs) == 1:
            src = pairs[0]
            reply = QMessageBox.question(
                self, _t("lyric_sync_copy_title"),
                _t("lyric_sync_copy_msg",
                   variant=self._variant_label(src), count=others[src]),
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if reply != QMessageBox.Yes:
                return
        else:
            labels = [self._variant_label(p) for p in pairs]
            choice, ok = QInputDialog.getItem(
                self, _t("lyric_sync_copy_title"),
                _t("lyric_sync_copy_choose"), labels, 0, False)
            if not ok:
                return
            src = pairs[labels.index(choice)]
        self._copy_sync_from(props, src)

    def _copy_sync_from(self, props: dict, src):
        """Kopiert die Sync-Keys der Quell-Kombi src=(ms,ls) auf die aktuelle."""
        src_prefix = f"lyric_sync_m{src[0]}_l{src[1]}_"
        self._sync_anchors = []
        for key, value in props.items():
            if not key.startswith(src_prefix):
                continue
            try:
                sec_s, block_s = value.split("|", 1)
                self._sync_anchors.append([float(sec_s), int(block_s)])
            except (ValueError, AttributeError):
                continue
        self._sync_anchors.sort(key=lambda a: a[0])
        self._persist_sync_anchors()
        if self._sync_mode:
            self._render_sync_markers()

    def _variant_label(self, pair) -> str:
        """Lesbares Label fuer eine (Musik-Slot, Lyric-Slot)-Kombi."""
        ms, ls = pair

        def _name(kind, slot):
            if slot <= 1:
                return _t("variant_standard")
            try:
                props = self._db.get_properties(self._sync_song_id)
                return props.get(f"{kind}_{slot}_name", f"#{slot}") or f"#{slot}"
            except Exception:
                return f"#{slot}"

        return _t("lyric_sync_variant_label",
                  music=_name("music", ms), lyric=_name("lyric", ls))

    def _on_edit_toggled(self, checked: bool):
        """Stift-Toggle: Read ↔ Edit. Bei Toggle-Off wird gespeichert."""
        if checked and not self._edit_mode:
            if not self._current_path:
                # Kein Lyric geladen → Toggle zuruecknehmen
                self._btn_edit.blockSignals(True)
                self._btn_edit.setChecked(False)
                self._btn_edit.blockSignals(False)
                return
            self._enter_edit_mode()
        elif not checked and self._edit_mode:
            # User klickt Stift → speichern, dann Read-Modus
            self._save_and_exit()
        # BL-173: Dynamic Lyrics ist im Edit-Modus nicht nutzbar → Button-Status
        self.update_dynamic_button_state()

    def _reset_edit_button(self):
        """Setzt den Stift-Toggle zurueck (ohne Signal)."""
        self._btn_edit.blockSignals(True)
        self._btn_edit.setChecked(False)
        self._btn_edit.blockSignals(False)

    def _offer_convert_display_to_html(self):
        """Bietet fuer DOCX/PDF an, eine bearbeitbare HTML-Kopie anzulegen.

        DOCX/PDF werden nur angezeigt (BL-146). Will der User editieren, wird
        aus der aktuellen Anzeige eine .html-Datei daneben erzeugt, der DB-
        Eintrag umgezogen (gleicher Migrationspfad wie RTF/TXT) und danach in
        den normalen Edit-Modus auf der HTML-Kopie gewechselt.
        """
        reply = QMessageBox.question(
            self, _t("lyrics_convert_offer_title"),
            _t("lyrics_convert_offer_msg",
               filename=os.path.basename(self._current_path)),
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply != QMessageBox.Yes:
            self._reset_edit_button()
            return
        old_basename = os.path.basename(self._current_path)
        try:
            new_path, new_basename = self._convert_display_to_html()
        except Exception as e:
            QMessageBox.warning(self, _t("lyrics_save_error_title"),
                                _t("lyrics_save_error_msg",
                                   path=self._current_path, error=str(e)))
            self._reset_edit_button()
            return
        # Auf die neue HTML-Kopie umschalten und direkt editieren.
        self._current_path = new_path
        self._load_file(new_path, new_basename)
        self._reset_edit_button()  # _enter_edit_mode setzt ihn gleich wieder
        self._enter_edit_mode()
        QMessageBox.information(
            self, _t("lyrics_migrated_title"),
            _t("lyrics_migrated_msg", new=new_basename, old=old_basename))

    def _convert_display_to_html(self):
        """Schreibt die aktuelle Anzeige als neue .html-Datei und zieht die DB um.

        Returns:
            (new_path, new_basename)
        """
        src_path = self._current_path
        src_basename = os.path.basename(src_path)
        stem = os.path.splitext(src_basename)[0]
        new_basename = stem + ".html"
        new_path = os.path.join(os.path.dirname(src_path), new_basename)
        n = 1
        while os.path.exists(new_path):
            new_basename = f"{stem}_edit{n}.html"
            new_path = os.path.join(os.path.dirname(src_path), new_basename)
            n += 1
        html = self._browser.document().toHtml()
        with open(new_path, "w", encoding="utf-8") as f:
            f.write(html)
        # Song-Eintrag in der DB auf die neue Datei umziehen (Original bleibt).
        if self._db and self._current_song and getattr(self._current_song, "id", None):
            try:
                self._db.update_lyrics_file(self._current_song.id, new_basename)
                self._current_song.lyrics_file = new_basename
            except Exception as e:
                print(f"[LyricsWidget] DB-Update fehlgeschlagen: {e}")
        return (new_path, new_basename)

    def _enter_edit_mode(self):
        """Aktiviert die Bearbeitung des aktuell geladenen Lyric-Dokuments."""
        if self._edit_mode or not self._current_path:
            return
        # Original-Datei NEU laden (ohne Sanitize/Strip), damit Schriftgroessen
        # erhalten bleiben. Fuer .rtf nutzen wir das Ergebnis des Konverters.
        ext = os.path.splitext(self._current_path)[1].lower()
        # DOCX/PDF sind reine Anzeige-Formate (BL-146) und koennen nicht direkt
        # editiert werden. Stattdessen eine bearbeitbare HTML-Kopie anbieten.
        if ext in self._DISPLAY_ONLY:
            self._offer_convert_display_to_html()
            return
        # Aktuell angezeigten (sanitized) Text merken — Basis fuer den Diff
        # nach dem Speichern, um Sync-Anker nachzufuehren statt zu verlieren.
        self._pre_edit_text = self._browser.document().toPlainText()
        try:
            content = self._read_file(self._current_path)
        except Exception as e:
            QMessageBox.warning(self, _t("lyrics_save_error_title"),
                                _t("lyrics_save_error_msg",
                                   path=self._current_path, error=str(e)))
            self._btn_edit.blockSignals(True)
            self._btn_edit.setChecked(False)
            self._btn_edit.blockSignals(False)
            self._pre_edit_text = None
            return

        if ext in self._SUPPORTED_HTML:
            # Original-HTML (ohne Sanitize) editieren; nur Words
            # Kommentar-Klammern um das Stylesheet loesen, sonst ignoriert Qt es
            html = self._unwrap_style_comments(content)
        elif ext in self._SUPPORTED_RTF:
            # RTF → HTML konvertieren (gleiche Logik wie _load_rtf)
            content = self._strip_rtf_binary_groups(content)
            doc = QTextDocument()
            doc.setHtml("")
            doc.setHtml(content)
            if not doc.isEmpty() and not doc.toPlainText().strip().startswith("{\\rtf"):
                html = doc.toHtml()
            else:
                html = self._rtf_to_html(content)
        elif ext in self._SUPPORTED_TEXT:
            # Plaintext → minimales HTML
            esc = (content.replace('&', '&amp;')
                          .replace('<', '&lt;').replace('>', '&gt;')
                          .replace('\n', '<br>'))
            html = f"<html><body>{esc}</body></html>"
        else:
            return

        # Auto-Modi pausieren
        self._edit_mode = True
        self._dirty = False
        self._browser.setReadOnly(False)
        self._browser.setHtml(html)
        # Zoom-Cache leeren — Positionen aendern sich beim Tippen,
        # eine Skalierung wuerde sonst falsche Fragmente treffen.
        # Nach dem Speichern wird der Cache beim Reload neu gefuellt.
        self._original_sizes = []
        self._set_font_size(self._base_font_size)  # Bearbeiten = 100 %
        # Signale sind bereits im __init__ einmal verbunden — Slots pruefen
        # self._edit_mode und sind im Read-Modus No-Ops.

        # Format-Toolbar zeigen.
        # Auto-Scroll und Auto-Size waehrend des Editierens sperren
        # (wuerden den Cursor verschieben bzw. die Default-Schrift dauernd
        # umschalten). Zoom und Auto-Width ebenfalls: Bearbeiten zeigt die
        # Datei immer in Originalgroesse (intern#152).
        self._format_toolbar_widget.setVisible(True)
        self._set_edit_locked_buttons_enabled(False)
        self._update_zoom_label()

        # Stift-Icon → Speichern-Hint
        self._btn_edit.blockSignals(True)
        self._btn_edit.setChecked(True)
        self._btn_edit.blockSignals(False)
        skin_dir = ""
        if self._skin_mgr and getattr(self._skin_mgr, "icon_dir", None):
            skin_dir = self._skin_mgr.icon_dir.replace("\\", "/")
        if skin_dir:
            self._btn_edit.setIcon(QIcon(f"{skin_dir}/save.svg"))
        else:
            self._btn_edit.setText("OK")
        self._btn_edit.setToolTip(_t("tooltip_lyrics_save"))

        self._update_format_buttons()
        self._browser.setFocus()

    def _leave_edit_mode_silent(self):
        """Verlaesst den Edit-Modus ohne Speichern (Reset der UI)."""
        if not self._edit_mode:
            return
        self._browser.setReadOnly(True)
        self._edit_mode = False
        self._dirty = False
        self._set_font_size(self._current_font_size)  # Zoom wieder anwenden
        self._format_toolbar_widget.setVisible(False)
        self._set_edit_locked_buttons_enabled(True)
        self._update_zoom_label()
        self._btn_edit.blockSignals(True)
        self._btn_edit.setChecked(False)
        self._btn_edit.blockSignals(False)
        skin_dir = ""
        if self._skin_mgr and getattr(self._skin_mgr, "icon_dir", None):
            skin_dir = self._skin_mgr.icon_dir.replace("\\", "/")
        if skin_dir:
            self._btn_edit.setIcon(QIcon(f"{skin_dir}/pencil.svg"))
            self._btn_edit.setText("")
        else:
            self._btn_edit.setText("✎")
        self._btn_edit.setToolTip(_t("tooltip_lyrics_edit"))

    def _set_edit_locked_buttons_enabled(self, enabled: bool):
        """Buttons, die im Bearbeiten-Modus gesperrt sind."""
        for btn in (self._btn_auto_scroll, self._btn_auto_size,
                    self._btn_auto_width, self._btn_zoom_in,
                    self._btn_zoom_out):
            btn.setEnabled(enabled)

    def _on_doc_changed(self):
        # Wird auch durch setHtml() im Read-Modus getriggert — dort ignorieren.
        if self._edit_mode:
            self._dirty = True

    def _confirm_discard(self) -> bool:
        """Bestaetigung holen, falls Edit-Modus mit ungespeicherten Aenderungen."""
        if not self._edit_mode or not self._dirty:
            return True
        res = QMessageBox.question(
            self,
            _t("lyrics_discard_title"),
            _t("lyrics_discard_msg"),
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        return res == QMessageBox.Yes

    def _on_cancel_clicked(self):
        if not self._confirm_discard():
            return
        # Reload originale Datei (sanitized) und Edit-Modus verlassen
        path = self._current_path
        filename = os.path.basename(path) if path else ""
        self._leave_edit_mode_silent()
        self._pre_edit_text = None  # verworfen, kein Diff noetig (nichts gespeichert)
        if path:
            self._load_file(path, filename)

    def _shortcut_cancel(self):
        if self._edit_mode:
            self._on_cancel_clicked()

    def _shortcut_save(self):
        if self._edit_mode:
            self._on_save_clicked()

    def _on_save_clicked(self):
        self._save_and_exit()

    def _save_and_exit(self):
        """Speichert das Dokument und kehrt in den Read-Modus zurueck."""
        if not self._edit_mode:
            return
        if not self._current_path:
            QMessageBox.warning(self, _t("lyrics_save_error_title"),
                                _t("lyrics_no_song_loaded"))
            self._leave_edit_mode_silent()
            return
        try:
            new_path, was_migrated, old_basename = self._save_html_to_disk()
        except Exception as e:
            QMessageBox.warning(self, _t("lyrics_save_error_title"),
                                _t("lyrics_save_error_msg",
                                   path=self._current_path, error=str(e)))
            return

        old_text = self._pre_edit_text
        self._current_path = new_path
        self._leave_edit_mode_silent()
        self._pre_edit_text = None
        # Datei neu laden (mit Sanitize, fuer den Read-Modus)
        self._load_file(new_path, os.path.basename(new_path))
        if old_text is not None:
            self._remap_sync_anchors_after_edit(
                old_text, self._browser.document().toPlainText())

        if was_migrated:
            QMessageBox.information(
                self, _t("lyrics_migrated_title"),
                _t("lyrics_migrated_msg",
                   new=os.path.basename(new_path), old=old_basename),
            )

    def _save_html_to_disk(self):
        """Schreibt den aktuellen Dokumentinhalt als HTML auf Platte.

        Returns:
            (new_path, was_migrated, old_basename):
                new_path: absoluter Pfad der gespeicherten Datei
                was_migrated: True wenn von RTF/TXT auf neue HTML-Datei migriert
                old_basename: Dateiname der Originaldatei (relevant fuer Hinweis)
        """
        # Anzeige-Skalierung NICHT in die Datei schreiben: Auto-Width/Zoom
        # skalieren den Default-Font des Dokuments (setDefaultFont), und
        # toHtml() brennt den als <body style="font-size:...pt"> ein — beim
        # Neuladen waeren dann alle Spans ohne eigene Groesse veraendert. Vor
        # der Serialisierung also den Default-Font auf die Basisgroesse
        # zuruecksetzen. Der Editor wird danach ohnehin neu geladen (kein
        # Restore noetig). Per-Zeichen-Groessen sind unberuehrt: im Edit-Modus
        # ist _original_sizes leer, _apply_zoom_factor also ein No-Op.
        _base_font = self._browser.document().defaultFont()
        _base_font.setPointSizeF(self._base_font_size * 0.75)  # px -> pt (96dpi)
        self._browser.document().setDefaultFont(_base_font)
        html = self._browser.document().toHtml()
        src_path = self._current_path
        src_ext = os.path.splitext(src_path)[1].lower()
        src_basename = os.path.basename(src_path)

        if src_ext in self._SUPPORTED_HTML:
            # HTML → ueberschreiben, .bak-Sicherung anlegen (einmal)
            bak_path = src_path + ".bak"
            if not os.path.exists(bak_path):
                try:
                    import shutil
                    shutil.copy2(src_path, bak_path)
                except Exception:
                    pass  # Sicherung ist nice-to-have, kein Showstopper
            with open(src_path, "w", encoding="utf-8") as f:
                f.write(html)
            return (src_path, False, src_basename)

        # RTF/TXT → neue .html-Datei daneben anlegen
        stem = os.path.splitext(src_basename)[0]
        new_basename = stem + ".html"
        new_path = os.path.join(os.path.dirname(src_path), new_basename)
        # Falls schon eine .html existiert: durchnummerieren
        n = 1
        while os.path.exists(new_path):
            new_basename = f"{stem}_edit{n}.html"
            new_path = os.path.join(os.path.dirname(src_path), new_basename)
            n += 1
        with open(new_path, "w", encoding="utf-8") as f:
            f.write(html)

        # Song-Eintrag in der DB auf die neue Datei umziehen
        if self._db and self._current_song and getattr(self._current_song, "id", None):
            try:
                self._db.update_lyrics_file(self._current_song.id, new_basename)
                # Auch das Song-Objekt selbst aktualisieren
                try:
                    self._current_song.lyrics_file = new_basename
                except Exception:
                    pass
            except Exception as e:
                print(f"[LyricsWidget] DB-Update fehlgeschlagen: {e}")

        return (new_path, True, src_basename)

    # ---- Format-Aktionen ----

    def _on_fmt_bold(self):
        if not self._edit_mode:
            return
        weight = QFont.Bold if self._btn_fmt_bold.isChecked() else QFont.Normal
        self._browser.setFontWeight(weight)

    def _on_fmt_italic(self):
        if not self._edit_mode:
            return
        self._browser.setFontItalic(self._btn_fmt_italic.isChecked())

    def _on_fmt_underline(self):
        if not self._edit_mode:
            return
        self._browser.setFontUnderline(self._btn_fmt_underline.isChecked())

    def _on_font_size_changed(self, *_):
        """Wendet die neue Schriftgroesse an.

        Mit Selektion: nur die Selektion aendern.
        Ohne Selektion: ganzes Dokument aendern (intuitiver — sichtbares Feedback).
        """
        if not self._edit_mode:
            return
        pt = self._spn_font_size.value()
        fmt = QTextCharFormat()
        fmt.setFontPointSize(float(pt))
        cursor = self._browser.textCursor()
        if cursor.hasSelection():
            cursor.mergeCharFormat(fmt)
            return
        # Keine Selektion → ganzes Dokument
        all_cur = QTextCursor(self._browser.document())
        all_cur.select(QTextCursor.Document)
        all_cur.mergeCharFormat(fmt)
        # Auch das Default-Format aktualisieren, damit neu getippter Text
        # die Groesse uebernimmt
        self._browser.mergeCurrentCharFormat(fmt)

    def _on_fmt_color(self):
        if not self._edit_mode:
            return
        col = QColorDialog.getColor(
            self._browser.textColor(), self, _t("tooltip_lyrics_color")
        )
        if col.isValid():
            self._browser.setTextColor(col)

    def _on_fmt_highlight(self):
        if not self._edit_mode:
            return
        cursor = self._browser.textCursor()
        current_bg = cursor.charFormat().background().color()
        col = QColorDialog.getColor(
            current_bg, self, _t("tooltip_lyrics_highlight"),
            QColorDialog.ShowAlphaChannel,
        )
        if col.isValid():
            fmt = QTextCharFormat()
            fmt.setBackground(QBrush(col))
            if cursor.hasSelection():
                cursor.mergeCharFormat(fmt)
            else:
                self._browser.mergeCurrentCharFormat(fmt)

    def _on_heading_changed(self, idx: int):
        if not self._edit_mode:
            return
        tag = self._cmb_heading.itemData(idx)
        cursor = self._browser.textCursor()
        block_fmt = QTextBlockFormat()
        char_fmt = QTextCharFormat()
        sizes = {"h1": 20.0, "h2": 16.0, "h3": 13.5, "p": 11.0}
        bolds = {"h1": True, "h2": True, "h3": True, "p": False}
        char_fmt.setFontPointSize(sizes.get(tag, 11.0))
        char_fmt.setFontWeight(QFont.Bold if bolds.get(tag, False) else QFont.Normal)
        cursor.beginEditBlock()
        cursor.mergeBlockFormat(block_fmt)
        # Auf den ganzen aktuellen Block anwenden
        cursor.movePosition(QTextCursor.StartOfBlock)
        cursor.movePosition(QTextCursor.EndOfBlock, QTextCursor.KeepAnchor)
        cursor.mergeCharFormat(char_fmt)
        cursor.endEditBlock()

    def _update_format_buttons(self):
        """Synchronisiert Bold/Italic/Underline/Size-Buttons mit Cursor-Position."""
        if not self._edit_mode:
            return
        try:
            fmt = self._browser.currentCharFormat()
            self._btn_fmt_bold.blockSignals(True)
            self._btn_fmt_bold.setChecked(fmt.fontWeight() >= QFont.Bold)
            self._btn_fmt_bold.blockSignals(False)
            self._btn_fmt_italic.blockSignals(True)
            self._btn_fmt_italic.setChecked(fmt.fontItalic())
            self._btn_fmt_italic.blockSignals(False)
            self._btn_fmt_underline.blockSignals(True)
            self._btn_fmt_underline.setChecked(fmt.fontUnderline())
            self._btn_fmt_underline.blockSignals(False)
            pt = fmt.fontPointSize()
            if pt and pt > 0:
                self._spn_font_size.blockSignals(True)
                self._spn_font_size.setValue(int(round(pt)))
                self._spn_font_size.blockSignals(False)
        except Exception:
            pass

    # ---- Toolbar-Callbacks ----

    def _on_auto_scroll_toggled(self, checked: bool):
        self._auto_scroll_enabled = checked

    def _on_auto_size_toggled(self, checked: bool):
        self._auto_size_enabled = checked
        if checked:
            # Exklusiv: Auto-Width abschalten ohne Re-Trigger
            if self._auto_width_enabled or self._btn_auto_width.isChecked():
                self._auto_width_enabled = False
                self._btn_auto_width.blockSignals(True)
                self._btn_auto_width.setChecked(False)
                self._btn_auto_width.blockSignals(False)
            if self._lyrics_loaded:
                QTimer.singleShot(0, self._auto_fit_font_size)

    def _on_auto_width_toggled(self, checked: bool):
        self._auto_width_enabled = checked
        if checked:
            # Exklusiv: Auto-Size abschalten ohne Re-Trigger
            if self._auto_size_enabled or self._btn_auto_size.isChecked():
                self._auto_size_enabled = False
                self._btn_auto_size.blockSignals(True)
                self._btn_auto_size.setChecked(False)
                self._btn_auto_size.blockSignals(False)
            if self._lyrics_loaded:
                QTimer.singleShot(0, self.auto_fit_width)

    def _on_zoom_in(self):
        self._manual_zoom(+2)

    def _on_zoom_out(self):
        self._manual_zoom(-2)

    def _manual_zoom(self, delta_px: float):
        """Manueller Zoom: Aendert Schriftgroesse und deaktiviert Auto-Size."""
        new_size = max(6, self._current_font_size + delta_px)
        self._set_font_size(new_size)
        self._current_font_size = new_size
        self._update_zoom_label()
        # Manueller Zoom → Auto-Size und Auto-Width deaktivieren
        if self._btn_auto_size.isChecked():
            self._btn_auto_size.setChecked(False)
        if self._btn_auto_width.isChecked():
            self._btn_auto_width.setChecked(False)
        # Auto-Scroll neu bewerten: braucht Text Scrollbar?
        if self._lyrics_loaded:
            viewport_h = self._browser.viewport().height()
            doc_h = self._browser.document().size().height()
            self._auto_scroll_active = doc_h > viewport_h

    def _update_zoom_label(self):
        """Aktualisiert die Zoom-Prozentanzeige."""
        size = self._base_font_size if self._edit_mode else self._current_font_size
        pct = int(round(size / self._base_font_size * 100))
        self._label_zoom.setText(f"{pct}%")

    # ---- Auto-Fit: Schriftgroesse anpassen ----

    def _auto_fit_font_size(self):
        """Passt die Schriftgroesse an, damit Lyrics den Viewport fuellen.

        Wenn der Inhalt auf eine Seite passt: Schrift vergroessern bis
        der Viewport gefuellt ist. Wenn der Inhalt zu lang ist: Schrift
        bei Standard belassen und Auto-Scroll aktivieren.
        """
        if not self._lyrics_loaded or not self._auto_size_enabled:
            return

        viewport_h = self._browser.viewport().height()
        if viewport_h <= 0:
            return

        # Zurueck auf Basis-Groesse fuer Messung
        self._set_font_size(self._base_font_size)

        doc_h = self._browser.document().size().height()
        if doc_h <= 0:
            return

        if doc_h <= viewport_h:
            # Inhalt passt → Schrift vergroessern (binaere Suche)
            self._auto_scroll_active = False
            lo = self._base_font_size
            hi = self._base_font_size * 5  # Max 5x Vergroesserung
            best = lo

            for _ in range(15):  # Max 15 Iterationen
                mid = (lo + hi) / 2.0
                self._set_font_size(mid)
                h = self._browser.document().size().height()
                if h <= viewport_h:
                    best = mid
                    lo = mid + 0.5
                else:
                    hi = mid - 0.5
                if hi - lo < 0.5:
                    break

            # Etwas Puffer lassen (95% des Viewports)
            self._set_font_size(best * 0.95)
            self._current_font_size = best * 0.95
            self._update_zoom_label()
            print(f"[Lyrics] Auto-Fit: {self._base_font_size}px -> "
                  f"{self._current_font_size:.1f}px "
                  f"(viewport={viewport_h}px)")
        else:
            # Inhalt zu lang → Standard-Groesse, Auto-Scroll aktivieren
            self._auto_scroll_active = True
            self._current_font_size = self._base_font_size
            self._update_zoom_label()
            print(f"[Lyrics] Auto-Scroll aktiviert "
                  f"(doc={doc_h:.0f}px > viewport={viewport_h}px)")

    def auto_fit_width(self):
        """Passt die Schriftgroesse so an, dass der Text ohne horizontales
        Scrollen in die Breite passt. Deaktiviert Auto-Size."""
        if not self._lyrics_loaded:
            return

        viewport_w = self._browser.viewport().width()
        if viewport_w <= 0:
            return

        # Bei Basis-Groesse starten
        self._set_font_size(self._base_font_size)
        doc = self._browser.document()
        doc.setTextWidth(-1)  # Kein Wrapping fuer Breitenmessung
        ideal_w = doc.idealWidth()
        doc.setTextWidth(viewport_w)  # Wrapping wiederherstellen

        if ideal_w <= 0:
            return

        if ideal_w <= viewport_w:
            # Text passt schon → hochskalieren
            ratio = viewport_w / ideal_w
            new_size = min(self._base_font_size * ratio * 0.95,
                           self._base_font_size * 5)
        else:
            # Text zu breit → runterskalieren
            ratio = viewport_w / ideal_w
            new_size = max(self._base_font_size * ratio * 0.95, 6)

        self._set_font_size(new_size)
        self._current_font_size = new_size
        self._update_zoom_label()

        # Auto-Scroll bewerten
        viewport_h = self._browser.viewport().height()
        doc_h = doc.size().height()
        self._auto_scroll_active = doc_h > viewport_h

    def _set_font_size(self, size_px: float):
        """Setzt die Schriftgroesse des QTextBrowser.

        Skaliert zusaetzlich alle Inline-Schriftgroessen relativ zur Basis,
        damit Zoom/Auto-Width auch Dokumente mit per-Span font-size verkleinern
        oder vergroessern koennen.
        """
        if self._edit_mode:
            # Bearbeiten zeigt die Datei in Originalgroesse (100 %): Die
            # Groessen der Datei werden dort nicht gezoomt, also auch der Rest
            # (Ueberschriften, Leerraum) nicht (intern#152).
            size_px = self._base_font_size
        font = self._browser.font()
        font.setPointSizeF(size_px * 0.75)  # px → pt Naeherung (96dpi)
        self._browser.setFont(font)
        # Auch Default-Font des Dokuments anpassen (wirkt auf Spans ohne
        # eigene font-size)
        self._browser.document().setDefaultFont(font)
        # Inline-font-size proportional skalieren (Spans MIT eigener Groesse)
        factor = size_px / self._base_font_size if self._base_font_size > 0 else 1.0
        self._apply_zoom_factor(factor)

    def _cache_original_sizes(self):
        """Speichert die initialen pointSize-Werte aller Fragmente.

        Nach jedem setHtml/setPlainText aufrufen — die Liste ist die
        Basis fuer relative Zoom-Skalierung in _apply_zoom_factor.
        """
        self._original_sizes = []
        doc = self._browser.document()
        block = doc.begin()
        while block.isValid():
            it = block.begin()
            while not it.atEnd():
                frag = it.fragment()
                if frag.isValid():
                    pt = frag.charFormat().fontPointSize()
                    if pt and pt > 0:
                        self._original_sizes.append(
                            (frag.position(), frag.length(), float(pt))
                        )
                it += 1
            block = block.next()

    def _apply_zoom_factor(self, factor: float):
        """Skaliert alle gecachten Inline-Schriftgroessen um factor."""
        if not self._original_sizes:
            return
        doc = self._browser.document()
        cursor = QTextCursor(doc)
        cursor.beginEditBlock()
        for (pos, length, orig_pt) in self._original_sizes:
            cursor.setPosition(pos)
            cursor.setPosition(pos + length, QTextCursor.KeepAnchor)
            fmt = QTextCharFormat()
            fmt.setFontPointSize(orig_pt * factor)
            cursor.mergeCharFormat(fmt)
        cursor.endEditBlock()
        # BL-171: Zoom aendert den Textfluss → Abschnittsflaechen neu vermessen
        self.refresh_section_overlay()

    # ---- Auto-Scroll ----

    def _on_manual_scroll(self, _action=None):
        """Manuelles Scrollen (Rad, Scrollbalken ziehen, Tasten) setzt den
        Auto-Scroll kurz aus. So kann man waehrend der Wiedergabe zu einer Zeile
        blaettern und dort einen Set Point setzen, ohne dass der naechste Timer-
        Tick sofort zurueckreisst. Nach Ablauf laeuft der Auto-Scroll wieder an."""
        self._manual_scroll_until = time.monotonic() + self._MANUAL_SCROLL_PAUSE_SEC

    def update_scroll(self, pos: float, dur: float):
        """Scrollt zum Song-Fortschritt.

        Ohne Sync-Punkte: rein proportional (Songzeit -> Scrollbalken).
        Mit Sync-Punkten (BL-160): stueckweise lineare Interpolation zwischen
        den Ankern, sodass die Anzeige der Musik folgt. In den Randsegmenten
        (vor dem ersten / nach dem letzten Anker) wird linear zu den impliziten
        Endpunkten (Songanfang -> 0, Songende -> Maximum) interpoliert, nicht
        extrapoliert.

        Args:
            pos: aktuelle Wiedergabeposition in Sekunden
            dur: Songdauer in Sekunden
        """
        # Position auch im Sync-Modus merken (fuers Setzen neuer Anker)
        self._sync_last_pos = pos

        # BL-173: Bei Option 2 an Figuren-Teil-Grenzen im Sequence-View
        # weiterblaettern (deferred, audio-sicher). Der Lyric-Text folgt ueber
        # refresh_dynamic_from_sequence(). Billiger No-Op ohne Teilwechsel.
        if self._dynamic_enabled:
            self._dynamic_tick(pos)

        # BL-161: Im Erfassungs-Modus die Live-Laufzeit anzeigen
        if self._auto_calc_active:
            self._label_sync_time.setText(self._fmt_mmss(pos))

        # Bewusst NICHT auf self._auto_scroll_active gaten: dieser Flag wird beim
        # Laden evtl. mit noch falscher Viewport-Hoehe berechnet, sodass Auto-Scroll
        # nach dem Start erst anspringt, wenn ein Zoom/Toggle ihn neu berechnet.
        # Ob es ueberhaupt etwas zu scrollen gibt, sagt die Live-Scrollbar weiter
        # unten (max_val <= 0) verlaesslich — das heilt den Start-Fall selbst.
        if not self._lyrics_loaded or dur <= 0:
            return
        self._last_dur = dur
        # Ankerberechnung laeuft je Takt: sparen, wenn niemand sie braucht.
        if not (self._reading_band_enabled or self._auto_scroll_enabled):
            return
        anchors = self._anchor_doc_points() if self._active_anchors() else []
        # intern#76: Lesebalken folgt dem gesungenen Text (ohne Textsprung-
        # Verschiebung), auch waehrend manuellen Scrollens; gemalt wird relativ
        # zum Scroll-Wert.
        if self._reading_band_enabled:
            self._update_reading_band(self._sung_doc_y(pos, dur, anchors))

        if not self._auto_scroll_enabled:
            return

        # Manuelles Scrollen hat Vorrang: waehrend des Pausenfensters nicht
        # gegenlenken (Set-Point-Suche waehrend der Wiedergabe).
        if time.monotonic() < self._manual_scroll_until:
            return

        scrollbar = self._browser.verticalScrollBar()
        max_val = scrollbar.maximum()
        if max_val <= 0:
            return

        snapping = False
        if anchors:
            target = self._sync_scroll_target(pos, dur, max_val, anchors)
            snapping = self._interp_snapping
        else:
            # Ohne Anker proportional, der gesungene Text steht dabei auf der
            # Leseposition (intern#76; vorher lief er oben am Fenster).
            target = int(self._sung_doc_y(pos, dur, anchors) - self._read_offset())

        target = max(0, min(max_val, target))
        # Kleines Rueckwaerts-Zittern durch Audio-Positions-Jitter unterdruecken.
        # Echter Ruecksprung (Figur-Wiederholung, Loop) ist groesser als 5 % des
        # Scrollbereichs und wird durchgelassen.
        # intern#76: Beim gewollten Ruecksprung (Figur-Wiederholung) nicht
        # bremsen, sonst ruckelt der Text in Stuecken, waehrend der Lesebalken
        # glatt zurueckgleitet.
        if (not snapping and target < self._scroll_last_val
                and self._scroll_last_val - target < max_val * 0.05):
            return
        self._scroll_last_val = target
        scrollbar.setValue(target)

    def _refresh_band_after_render(self):
        """intern#76: Nach einem Neuaufbau des Dokuments (Dynamic Lyrics) den
        Lesebalken sofort am neuen Layout ausrichten, statt ihn bis zum
        naechsten Takt an der alten Stelle stehen zu lassen (Huepfen)."""
        dur = self._last_dur or 0
        if not (self._lyrics_loaded and self._reading_band_enabled and dur > 0):
            self._update_reading_band(None)
            return
        anchors = self._anchor_doc_points() if self._active_anchors() else []
        self._update_reading_band(self._sung_doc_y(self._sync_last_pos, dur, anchors))

    def _update_reading_band(self, doc_y):
        """intern#76: Neue Position des Lesebalkens, neu malen nur bei Aenderung."""
        new = None if doc_y is None else int(doc_y)
        if new != self._band_doc_y:
            self._band_doc_y = new
            self._reading_band.update()

    # Folgt der naechste SyncPoint innerhalb dieser Zeit, beendet der Anker
    # einen Abschnitt (danach springt der Text woanders hin), intern#76.
    _SECTION_END_GAP_SEC = 2.0

    def _line_geom(self, pristine_pos: int, doc, layout, max_pos: int):
        """(block, Zeilenindex im Block) der sichtbaren Zeile an pristine_pos."""
        dpos = self._pristine_to_display(int(pristine_pos))
        dpos = max(0, min(dpos, max_pos))
        cursor = QTextCursor(doc)
        cursor.setPosition(dpos)
        block = cursor.block()
        if not block.isValid():
            return None
        blay = block.layout()
        idx = 0
        if blay is not None:
            line = blay.lineForTextPosition(dpos - block.position())
            if line.isValid():
                idx = line.lineNumber()
        return block, idx

    @staticmethod
    def _line_box(block, idx, layout):
        """(Dokument-Y oben, Hoehe, Text) der Zeile idx im Block."""
        top = layout.blockBoundingRect(block).top()
        blay = block.layout()
        if blay is None or blay.lineCount() == 0:
            return top, layout.blockBoundingRect(block).height(), block.text()
        line = blay.lineAt(idx)
        text = block.text()[line.textStart():line.textStart() + line.textLength()]
        return top + line.y(), line.height(), text

    @staticmethod
    def _next_line(block, idx):
        """Naechste Zeile (block, idx) im Dokument oder None."""
        blay = block.layout()
        if blay is not None and idx + 1 < blay.lineCount():
            return block, idx + 1
        nxt = block.next()
        return (nxt, 0) if nxt.isValid() else None

    def _is_heading_text(self, text: str) -> bool:
        """Abschnitts-Ueberschrift ohne Inhalt auf derselben Zeile (OPENER,
        FIGURE, ...). "(Opener): Calls" zaehlt nicht, dort steht schon Text."""
        import singing_sections as _ss
        if self._heading_kw is None:
            self._heading_kw = _ss._keyword_words(_ss.DEFAULT_SECTIONS)
        raw = (text or "").strip()
        if not raw or _ss.PAREN_LABEL_RE.match(raw.upper()):
            return False
        return _ss.classify_heading(raw, _ss.DEFAULT_SECTIONS, self._heading_kw) is not None

    def _anchor_doc_points(self):
        """Anker als [(Sekunde, Dokument-Y der gesungenen Stelle)], nach Zeit.

        Echte Zeiten, ohne "Textsprung timen" und ohne Leseposition. Die
        gespeicherten SyncPoints bleiben unveraendert; nur fuer Scroll und
        Lesebalken gilt (intern#76, Regel David): Ein Abschnitt laeuft von der
        ersten Zeile NACH dem Schluesselwort bis zum Ende der Zeile VOR dem
        naechsten Schluesselwort.
        - Anker auf einer Ueberschrift -> Mitte der ersten Textzeile danach
        - Anker, der einen Abschnitt beendet (naechster Anker folgt binnen
          _SECTION_END_GAP_SEC, oder letzter Anker) -> Unterkante seiner Zeile
        - sonst -> Mitte seiner Zeile (dort wird gerade gesungen)
        Der Lesebalken ist um diesen Punkt zentriert.
        """
        doc = self._browser.document()
        layout = doc.documentLayout()
        max_pos = doc.characterCount() - 1
        raw = sorted(((float(a[0]), int(a[1])) for a in self._active_anchors()),
                     key=lambda a: a[0])
        out = []
        for i, (sec, p) in enumerate(raw):
            geom = self._line_geom(p, doc, layout, max_pos)
            if geom is None:
                continue
            block, idx = geom
            top, height, text = self._line_box(block, idx, layout)
            if self._is_heading_text(text):
                nxt = self._next_line(block, idx)
                for _ in range(5):       # Leerzeilen nach der Ueberschrift ueberspringen
                    if nxt is None:
                        break
                    n_top, n_h, n_text = self._line_box(nxt[0], nxt[1], layout)
                    if n_text.strip():
                        top, height = n_top, n_h
                        break
                    nxt = self._next_line(*nxt)
                out.append((sec, float(top + height / 2)))
                continue
            is_end = (i == len(raw) - 1
                      or raw[i + 1][0] - sec <= self._SECTION_END_GAP_SEC)
            out.append((sec, float(top + height) if is_end else float(top + height / 2)))
        return out

    def _interpolate(self, pos: float, points) -> float:
        """Stueckweise lineare Interpolation ueber (Zeit, Y)-Stuetzpunkte.

        Rueckwaerts-Segmente (Sprung zu frueherer Textzeile) halten die
        Position und springen erst kurz vor dem Ziel schnell zurueck.
        """
        points = sorted(points, key=lambda p: p[0])
        self._interp_snapping = False
        for i in range(len(points) - 1):
            t0, y0 = points[i]
            t1, y1 = points[i + 1]
            if pos <= t1:
                if t1 <= t0:
                    return float(y1)
                if y1 < y0:
                    snap = min(self._SYNC_BACK_SNAP_SECONDS, t1 - t0)
                    snap_start = t1 - snap
                    if pos <= snap_start:
                        return float(y0)
                    self._interp_snapping = True
                    frac = max(0.0, min(1.0, (pos - snap_start) / snap))
                    return y0 + frac * (y1 - y0)
                frac = max(0.0, min(1.0, (pos - t0) / (t1 - t0)))
                return y0 + frac * (y1 - y0)
        return float(points[-1][1])

    def _read_offset(self) -> int:
        """Leseposition in Pixeln von der Viewport-Oberkante (intern#76)."""
        return int(self._browser.viewport().height() * self._SYNC_ANCHOR_VIEWPORT_FRAC)

    def _sync_scroll_target(self, pos: float, dur: float, max_val: int,
                            anchors=None) -> int:
        """Berechnet die Ziel-Scrollposition per stueckweiser Interpolation.

        Stuetzpunkte: (0s -> 0px), die sortierten Anker (Sekunde -> Zeilen-Y,
        so verschoben, dass die Ankerzeile auf der Leseposition steht),
        (dur -> max_val). Das Zeilen-Y wird zur Laufzeit aus der Zeichenposition
        bestimmt, damit es bei Zoom/Auto-Size stabil bleibt.
        """
        if anchors is None:
            anchors = self._anchor_doc_points()
        read_offset = self._read_offset()
        # intern#115: "Textsprung timen" verschiebt die Anker zeitlich (nur fuer
        # die Anzeige, gespeichert bleibt die echte Zeit). Innerhalb des Songs
        # halten, sonst ueberholt ein Anker die festen Endpunkte. Im SyncPoint-
        # Modus nicht: Dort prueft und setzt man SyncPoints gegen die echte Zeit.
        shift = 0.0 if self._sync_mode else float(self._text_jump_offset)
        points = [(0.0, 0)]
        for sec, y in anchors:
            t = max(0.0, min(float(dur), sec + shift))
            points.append((t, max(0, y - read_offset)))
        points.append((float(dur), max_val))
        return int(self._interpolate(pos, points))

    def _sung_doc_y(self, pos: float, dur: float, anchors) -> float:
        """intern#76: Dokument-Y des gerade gesungenen Texts, OHNE "Textsprung
        timen". Mit Ankern: Interpolation Songanfang (0) -> Anker -> Songende
        (Dokumenthoehe). Ohne Anker: proportional zur Songzeit."""
        doc_h = float(self._browser.document().size().height())
        if not anchors:
            return (pos / dur) * doc_h if dur > 0 else 0.0
        points = [(0.0, 0.0)] + list(anchors) + [(float(dur), doc_h)]
        return self._interpolate(pos, points)

    # ---- Refit nach Song-Wechsel ----

    def _schedule_refit_after_load(self):
        """Triggert den aktiven Auto-Fit-Modus (Size oder Width) sobald
        QTextBrowser das Document-Layout berechnet hat.

        Statt fester Verzoegerung wird auf documentSizeChanged gewartet
        — robust gegen langsames HTML/RTF-Layout. 250 ms Fallback-Timer
        falls das Signal nicht (mehr) feuert (z.B. leeres Document).
        """
        # setHtml() hat die Inline-Groessen auf die Originalwerte zurueckgesetzt.
        # Die aktuelle/gespeicherte Groesse (aus der INI beim Start) sofort neu
        # anwenden — in JEDEM Modus. Sonst passt das Dokument bis zum Auto-Fit
        # nicht zu _current_font_size, und wer in dieser Luecke den Zoom-Faktor
        # herausrechnet (Dynamic Lyrics direkt nach dem Laden), halbiert die
        # Inline-Groessen, waehrend Ueberschriften ohne eigene Groesse riesig
        # wirken (intern#152).
        self._set_font_size(self._current_font_size)
        if not (self._auto_size_enabled or self._auto_width_enabled):
            return

        doc_layout = self._browser.document().documentLayout()

        # Alte Verbindung aus vorherigem Load aufraeumen
        if self._refit_conn is not None:
            try:
                doc_layout.documentSizeChanged.disconnect(self._refit_conn)
            except (TypeError, RuntimeError):
                pass
            self._refit_conn = None

        def _do_refit():
            # Nur einmal ausloesen
            if self._refit_conn is None:
                return
            try:
                doc_layout.documentSizeChanged.disconnect(self._refit_conn)
            except (TypeError, RuntimeError):
                pass
            self._refit_conn = None
            if not self._lyrics_loaded:
                return
            if self._auto_width_enabled:
                self.auto_fit_width()
            elif self._auto_size_enabled:
                self._auto_fit_font_size()

        def _on_size_changed(_size):
            # In den naechsten Event-Loop-Tick verschieben, damit der
            # Layout-Engine-Aufruf zu Ende ist, bevor wir neu setzen
            QTimer.singleShot(0, _do_refit)

        self._refit_conn = _on_size_changed
        doc_layout.documentSizeChanged.connect(_on_size_changed)
        # Fallback falls documentSizeChanged nicht (mehr) feuert
        QTimer.singleShot(250, _do_refit)

    # ---- Resize-Event: Auto-Fit neu berechnen ----

    def resizeEvent(self, event):
        """Bei Groessenaenderung den aktiven Auto-Fit neu berechnen."""
        super().resizeEvent(event)
        if not self._lyrics_loaded:
            return
        if self._auto_width_enabled:
            QTimer.singleShot(100, self.auto_fit_width)
        elif self._auto_size_enabled:
            QTimer.singleShot(100, self._auto_fit_font_size)

    # ---- Platzhalter / Clear ----

    def _show_placeholder(self, msg: str):
        """Zeigt einen Platzhalter-Text (kein Lyrics vorhanden)."""
        self._lyrics_loaded = False
        self._auto_scroll_active = False
        self._marker_inserts = []
        self._band_doc_y = None
        self._set_font_size(self._base_font_size)
        self._browser.setPlainText("")
        self._label_status.setText(msg)

    def clear(self):
        """Leert die Anzeige."""
        self._lyrics_loaded = False
        self._auto_scroll_active = False
        self._marker_inserts = []
        self._band_doc_y = None
        self._set_font_size(self._base_font_size)
        self._browser.clear()
        self._label_status.setText("\u2014")


def lyric_plain_text(path: str, filename: str) -> str:
    """Plain-Text einer Lyric-Datei OHNE Widget und ohne Rueckfragen.

    Spiegelt LyricsWidget._load_file() Format fuer Format wider und benutzt
    dessen eigene Konverter (_sanitize_html, _rtf_to_html, _docx_to_html) \u2014
    NICHT nachbauen: Sync-Anker sind Zeichenpositionen im QTextDocument, jede
    Abweichung von der Anzeige-Pipeline setzt sie auf die falsche Zeile.

    Laeuft im Bulk-Worker-Thread (QTextDocument ist dort erlaubt, QTextBrowser
    waere es nicht). Leerer String = kein verwertbarer Text (Aufrufer skippt).
    """
    W = LyricsWidget
    ext = os.path.splitext(filename)[1].lower()
    doc = QTextDocument()

    if ext in W._SUPPORTED_TEXT:
        doc.setPlainText(W._read_file(path))
        return doc.toPlainText()

    if ext in W._SUPPORTED_PDF:
        from pypdf import PdfReader
        reader = PdfReader(path)
        text = "\n\n".join((p.extract_text() or "") for p in reader.pages).strip()
        if not text:
            return ""   # z.B. gescanntes PDF ohne Textebene
        esc = (text.replace('&', '&amp;')
                   .replace('<', '&lt;').replace('>', '&gt;'))
        html = (f'<html><head><style>pre {{ white-space: pre-wrap; '
                f'font-family: inherit; margin: 0; }}</style></head>'
                f'<body><pre>{esc}</pre></body></html>')
        doc.setHtml(html)
        return doc.toPlainText()

    if ext in W._SUPPORTED_HTML:
        html = W._sanitize_html(W._read_file(path), lyrics_dir=os.path.dirname(path))
    elif ext in W._SUPPORTED_RTF:
        content = W._strip_rtf_binary_groups(W._read_file(path))
        probe = QTextDocument()
        probe.setHtml("")
        probe.setHtml(content)   # Qt erkennt RTF am {\rtf-Header
        qt_worked = (not probe.isEmpty()
                     and not probe.toPlainText().strip().startswith("{\\rtf"))
        html = W._sanitize_html(probe.toHtml() if qt_worked
                                else W._rtf_to_html(content))
    elif ext in W._SUPPORTED_DOCX:
        html = W._sanitize_html(W._docx_to_html(path))
    else:
        return ""   # Format wird auch in der Anzeige nicht unterstuetzt

    # Verwaiste Inline-Tags still schliessen. Im Widget fragt der HTML-Pfad hier
    # nach (_check_and_offer_html_fix) \u2014 fuer den Plain-Text ist das egal:
    # ein eingefuegtes </tag> erzeugt kein einziges Textzeichen, die Positionen
    # bleiben also identisch, egal wie der Caller die Rueckfrage beantwortet.
    issues = W._find_unclosed_inline_tags(html)
    if issues:
        html = W._fix_unclosed_inline_tags(html, issues)
    doc.setHtml(html)
    return doc.toPlainText()
