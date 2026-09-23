"""
evening_planner_widget.py — Abendplanung mit emotionalem Spannungsbogen.

Erstellt einen ERR-basierten Tipp-Plan für einen Square-Dance-Clubabend:
  - Bezier-Kurve als emotionales Ziel über den Abend
  - Blöcke aus je 3–5 Tipps mit Sägezahn-Muster (3→4→2→1)
  - Songvorschläge nach Score = quality × days_factor × err_match
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass
from datetime import date
from typing import Optional

from i18n import _t
from ui_helpers import mark_toggle
from zoom_wheel import install_ctrl_wheel_zoom
from PySide6.QtCore import Qt, Signal, QSize, QRect, QPoint, QTimer
from PySide6.QtGui import (
    QColor, QFont, QIcon, QPainter, QPainterPath, QPen, QBrush, QPolygon,
    QMouseEvent, QPixmap,
)
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QDialog, QDialogButtonBox,
    QFormLayout, QGroupBox, QHBoxLayout, QHeaderView,
    QLabel, QMenu, QMessageBox, QPushButton, QScrollArea, QSizePolicy, QSpinBox,
    QTableWidget, QTableWidgetItem, QVBoxLayout,
    QWidget, QFrame,
)

# ─── Konstanten ────────────────────────────────────────────────────────────────

_TIP_MIN_DEFAULT = 15      # Standard-Tipp-Länge in Minuten
_BASE_PX_MIN     = 5.0     # Pixel pro Minute bei Skala 1.0
_CANVAS_H        = 170     # Canvas-Höhe gesamt
_PAD_L           = 26      # Links: Platz für ERR-Labels
_PAD_T           = 14      # Oben
_PAD_B           = 26      # Unten: Tipp-Nummern
_HANDLE_R        = 6       # Drag-Handle-Radius
_DEFAULT_DAYS_FALLBACK = 730  # Fallback wenn kein start_date gesetzt (2 Jahre)
_BLOCK_DIV_W     = 5       # Breite des Block-Trennstreifens (px)

_ERR_COL = {
    0: QColor("#808080"),
    1: QColor("#d9441c"),
    2: QColor("#c8901a"),
    3: QColor("#2e8b3e"),
    4: QColor("#2a5bbf"),
}

_STRATEGY_LABELS = [
    (1, "ep_strat_1"),
    (2, "ep_strat_2"),
    (3, "ep_strat_3"),
    (4, "ep_strat_4"),
]

# ─── SVG-Icon-Templates ────────────────────────────────────────────────────────

_SVG_ZOOM_OUT = (
    '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 16 16">'
    '<circle cx="6.5" cy="6.5" r="4.5" stroke="{c}" stroke-width="1.5" fill="none"/>'
    '<line x1="4" y1="6.5" x2="9" y2="6.5" stroke="{c}" stroke-width="1.5" stroke-linecap="round"/>'
    '<line x1="10.2" y1="10.2" x2="14" y2="14" stroke="{c}" stroke-width="2" stroke-linecap="round"/>'
    '</svg>'
)
_SVG_ZOOM_IN = (
    '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 16 16">'
    '<circle cx="6.5" cy="6.5" r="4.5" stroke="{c}" stroke-width="1.5" fill="none"/>'
    '<line x1="4" y1="6.5" x2="9" y2="6.5" stroke="{c}" stroke-width="1.5" stroke-linecap="round"/>'
    '<line x1="6.5" y1="4" x2="6.5" y2="9" stroke="{c}" stroke-width="1.5" stroke-linecap="round"/>'
    '<line x1="10.2" y1="10.2" x2="14" y2="14" stroke="{c}" stroke-width="2" stroke-linecap="round"/>'
    '</svg>'
)
_SVG_ZOOM_FIT = (
    '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 16 16">'
    '<polyline points="1,5 1,1 5,1" stroke="{c}" stroke-width="1.5" fill="none" '
    'stroke-linecap="round" stroke-linejoin="round"/>'
    '<polyline points="11,1 15,1 15,5" stroke="{c}" stroke-width="1.5" fill="none" '
    'stroke-linecap="round" stroke-linejoin="round"/>'
    '<polyline points="15,11 15,15 11,15" stroke="{c}" stroke-width="1.5" fill="none" '
    'stroke-linecap="round" stroke-linejoin="round"/>'
    '<polyline points="5,15 1,15 1,11" stroke="{c}" stroke-width="1.5" fill="none" '
    'stroke-linecap="round" stroke-linejoin="round"/>'
    '</svg>'
)
_SVG_RESET = (
    '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 16 16">'
    '<path d="M4,7 A5,5,0,1,1,6.5,12.5" stroke="{c}" stroke-width="1.5" fill="none" stroke-linecap="round"/>'
    '<polyline points="1,4 4,7 7,4" stroke="{c}" stroke-width="1.5" fill="none" '
    'stroke-linecap="round" stroke-linejoin="round"/>'
    '</svg>'
)
_SVG_ADD_PAUSE = (
    '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 16 16">'
    '<rect x="2" y="3" width="3" height="9" rx="1" fill="{c}"/>'
    '<rect x="7" y="3" width="3" height="9" rx="1" fill="{c}"/>'
    '<line x1="13" y1="1" x2="13" y2="7" stroke="{c}" stroke-width="1.5" stroke-linecap="round"/>'
    '<line x1="10.5" y1="4" x2="15.5" y2="4" stroke="{c}" stroke-width="1.5" stroke-linecap="round"/>'
    '</svg>'
)
_SVG_RULES = (
    '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 16 16">'
    '<circle cx="8" cy="8" r="6" stroke="{c}" stroke-width="1.5" fill="none"/>'
    '<circle cx="8" cy="8" r="2" fill="{c}"/>'
    '<line x1="8" y1="1" x2="8" y2="3.5" stroke="{c}" stroke-width="1.5" stroke-linecap="round"/>'
    '<line x1="8" y1="12.5" x2="8" y2="15" stroke="{c}" stroke-width="1.5" stroke-linecap="round"/>'
    '<line x1="1" y1="8" x2="3.5" y2="8" stroke="{c}" stroke-width="1.5" stroke-linecap="round"/>'
    '<line x1="12.5" y1="8" x2="15" y2="8" stroke="{c}" stroke-width="1.5" stroke-linecap="round"/>'
    '</svg>'
)
_SVG_FILL_ALL = (
    '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 16 16">'
    '<polyline points="2,8 6,12 14,4" stroke="{c}" stroke-width="2" fill="none" '
    'stroke-linecap="round" stroke-linejoin="round"/>'
    '</svg>'
)
_SVG_CLEAR = (
    '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 16 16">'
    '<line x1="3" y1="3" x2="13" y2="13" stroke="{c}" stroke-width="2" stroke-linecap="round"/>'
    '<line x1="13" y1="3" x2="3" y2="13" stroke="{c}" stroke-width="2" stroke-linecap="round"/>'
    '</svg>'
)
_ALL_BTNS_SVGS = [
    ("_btn_zoom_out", _SVG_ZOOM_OUT),
    ("_btn_zoom_in",  _SVG_ZOOM_IN),
    ("_btn_zoom_fit", _SVG_ZOOM_FIT),   # Icon only (kein Text)
]


def _label_code(label: str) -> str:
    """Extrahiert das Label-Kürzel (Buchstaben-Präfix vor Katalognummer).

    Beispiele: 'SIR 504a' → 'SIR', 'AR 999' → 'AR', 'c-c605' → 'C'
    Vergleich case-insensitiv via .upper().
    """
    import re
    m = re.match(r'[A-Za-z]+', label.strip())
    return m.group(0).upper() if m else ""


def _make_icon(svg_template: str, color: str) -> QIcon:
    svg_bytes = svg_template.format(c=color).encode("utf-8")
    pixmap = QPixmap()
    pixmap.loadFromData(svg_bytes, "SVG")
    return QIcon(pixmap)


# ─── Datenklassen ──────────────────────────────────────────────────────────────

@dataclass
class TipSlot:
    number: int
    target_err: int = 3
    elapsed_min: int = 0
    patter_id:        Optional[int] = None
    patter_title:     str = ""
    patter_label:     str = ""
    patter_err:       int = 0
    patter_confirmed: bool = False
    singer_id:        Optional[int] = None
    singer_title:     str = ""
    singer_label:     str = ""
    singer_err:       int = 0
    singer_confirmed: bool = False
    singer_genres:    tuple = ()   # Genres des bestätigten/gewählten Singings


@dataclass
class PauseBlock:
    after_tip:    int
    duration_min: int = 20
    elapsed_min:  int = 0


@dataclass
class _Candidate:
    song_id:    int
    title:      str
    label:      str
    err:        int
    score:      float
    is_pattern: bool
    is_singing: bool
    days:       int   = 0
    genres:     tuple = ()   # Tuple von Genre-Namen


# ─── Curve Engine ──────────────────────────────────────────────────────────────

class CurveEngine:
    _SAW = {
        1: [1],
        2: [3, 1],
        3: [3, 3, 1],
        4: [3, 4, 2, 1],
        5: [3, 4, 3, 2, 1],
    }

    def compute(self, n_tips, pauses_after, block_min=3, block_max=5,
                overrides=None) -> list:
        if n_tips <= 0:
            return []
        blocks  = self._build_blocks(n_tips, pauses_after, block_min, block_max)
        targets = {}
        for block in blocks:
            pattern = self._pattern(len(block))
            for tip_num, err in zip(block, pattern):
                targets[tip_num] = err
        if overrides:
            for tip_num, err in overrides.items():
                if 1 <= tip_num <= n_tips:
                    targets[tip_num] = max(1, min(4, err))
        return [targets.get(t, 3) for t in range(1, n_tips + 1)]

    def get_block_starts(self, n_tips, pauses_after, block_min=3, block_max=5) -> set:
        if n_tips <= 0:
            return set()
        blocks = self._build_blocks(n_tips, pauses_after, block_min, block_max)
        return {block[0] for block in blocks[1:]}

    def _build_blocks(self, n, pauses_after, mn, mx):
        boundaries = sorted(t for t in pauses_after if 1 <= t < n) + [n]
        result, start = [], 1
        for end in boundaries:
            seg = list(range(start, end + 1))
            result.extend(self._split(seg, mn, mx))
            start = end + 1
        return result

    def _split(self, tips, mn, mx):
        n = len(tips)
        if n <= mx:
            return [tips]
        k = 2
        while k <= n:
            if mn <= n / k <= mx:
                break
            k += 1
        else:
            k = math.ceil(n / mx)
        base, extra = divmod(n, k)
        result, i = [], 0
        for b in range(k):
            sz = base + (1 if b < extra else 0)
            result.append(tips[i:i + sz])
            i += sz
        return result

    def _pattern(self, size):
        if size in self._SAW:
            return list(self._SAW[size])
        mid = [3] * max(0, size - 4)
        p   = [3, 4] + mid + [2, 1]
        return p[:size] if len(p) >= size else p + [1] * (size - len(p))


# ─── Song Scorer ───────────────────────────────────────────────────────────────

class SongScorer:
    def __init__(self, db, tiebreaker=None):
        self._db = db
        # Optionaler Zufalls-Tiebreaker (wie BL-113 im Planner): callable(song_id)
        # → float. Bei Gleichstand entscheidet er statt der DB-Reihenfolge.
        self._tiebreaker = tiebreaker

    def candidates(self, target_err, location_id, want_pattern, want_singing,
                   exclude_ids=None, limit=8, days_fallback=_DEFAULT_DAYS_FALLBACK,
                   genre_filter=None) -> list:
        rows = self._db.get_planner_candidates(target_err, location_id, days_fallback)
        gf = frozenset(genre_filter) if genre_filter else frozenset()
        results = []
        for row in rows:
            sid, title, label, err, quality, isp, iss, days, genres_str = row
            genres = tuple(genres_str.split(',')) if genres_str else ()
            if exclude_ids and sid in exclude_ids:
                continue
            if want_pattern and not want_singing and not isp:
                continue
            if want_singing and not want_pattern and not iss:
                continue
            # Genre-Filter anwenden
            if gf and not (gf & frozenset(genres)):
                continue
            score = self._score(quality, days, err, target_err)
            if score > 0:
                results.append(_Candidate(
                    song_id=sid, title=title, label=label, err=err,
                    score=score, is_pattern=bool(isp), is_singing=bool(iss),
                    days=int(days), genres=genres,
                ))
        tb = self._tiebreaker
        if tb is not None:
            results.sort(key=lambda c: (-c.score, tb(c.song_id)))
        else:
            results.sort(key=lambda c: -c.score)
        return results if limit is None else results[:limit]

    @staticmethod
    def _score(quality, days, err, target_err):
        if err == 0:
            err_match = 0.25          # ERR nicht gepflegt → niedrige Gewichtung
        else:
            diff = abs(err - target_err)
            err_match = 1.0 / (diff + 1)   # diff=0→1.0, diff=1→0.5, diff=2→0.33, …
        return quality * int(days) * err_match


# ─── Curve Canvas ──────────────────────────────────────────────────────────────

class CurveCanvas(QWidget):
    """
    Zeichnet den Abendüberblick: Balken + Bezier-Kurve + Drag-Handles.
    Liegt in einem QScrollArea für horizontales Panning.
    Unterstützt:
      - ERR-Handle-Drag (Kurve ziehen)
      - Pause-Drag (Pause im Zeitstrahl verschieben)
    """
    sig_tip_selected   = Signal(int)       # tip.number
    sig_target_changed = Signal(int, int)  # tip.number, new_err
    sig_pause_moved    = Signal(int, int)  # old_after_tip, new_after_tip
    sig_slot_requested = Signal(int, str)  # tip.number, 'pattern'|'singing'

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(_CANVAS_H)
        self.setMaximumHeight(_CANVAS_H)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setMouseTracking(True)

        self._tip_min      = _TIP_MIN_DEFAULT
        self._scale        = 1.0
        self._tips:  list  = []
        self._pauses: list = []
        self._block_starts: set = set()
        self._selected     = 0

        # ERR-Handle-Drag
        self._drag_tip     = 0
        self._drag_start_y = 0.0

        # Pause-Drag
        self._drag_pause_after = 0   # after_tip der gezogenen Pause (0 = kein Drag)
        self._drag_pause_drop  = 0   # Ziel-after_tip während Drag
        self._drag_pause_x     = 0.0 # aktuelle Maus-X während Pause-Drag

        self._timeline: list = []
        self._tip_cx:   dict = {}

        # Skin-Farben (Defaults = dunkles Theme)
        self._col_bg        = QColor("#1e2229")
        self._col_grid      = QColor("#333a45")
        self._col_fg        = QColor("#e8e8e8")
        self._col_fg_dim    = QColor("#888ea0")
        self._col_pause_bg  = QColor("#2e3440")
        self._col_pause_bd  = QColor("#606878")
        self._col_block_div = QColor("#3a4a6a")
        self._col_drop      = QColor("#0078d4")
        self._col_tip_div   = QColor("#626872")

    # ── Public API ─────────────────────────────────────────────────────────────

    def set_plan(self, tips, pauses, block_starts=None):
        self._tips         = tips
        self._pauses       = pauses
        self._block_starts = block_starts or set()
        self._rebuild_timeline()
        self.resize(self.sizeHint())
        self.update()

    def set_scale(self, scale: float):
        self._scale = max(0.25, min(4.0, scale))
        self._rebuild_timeline()
        self.resize(self.sizeHint())
        self.update()

    def set_tip_min(self, minutes: int):
        self._tip_min = max(5, minutes)
        self._rebuild_timeline()
        self.resize(self.sizeHint())
        self.update()

    def select_tip(self, number: int):
        self._selected = number
        self.update()

    def set_skin_colors(self, bg, fg, fg_dim, grid, pause_bg, pause_bd,
                        block_div, drop, tip_div=None):
        self._col_bg        = bg
        self._col_fg        = fg
        self._col_fg_dim    = fg_dim
        self._col_grid      = grid
        self._col_pause_bg  = pause_bg
        self._col_pause_bd  = pause_bd
        self._col_block_div = block_div
        self._col_drop      = drop
        if tip_div is not None:
            self._col_tip_div = tip_div
        self.update()

    # ── Layout ─────────────────────────────────────────────────────────────────

    def sizeHint(self) -> QSize:
        total_min = sum(
            (self._tip_min if isinstance(item, TipSlot) else item.duration_min)
            for item in self._timeline
        )
        w = _PAD_L + int(total_min * _BASE_PX_MIN * self._scale) + 20
        return QSize(max(w, 400), _CANVAS_H)

    def minimumSizeHint(self) -> QSize:
        return self.sizeHint()

    # ── Coordinate helpers ─────────────────────────────────────────────────────

    def _err_to_y(self, err: float) -> float:
        usable = _CANVAS_H - _PAD_T - _PAD_B
        return _PAD_T + (err - 1) * usable / 4.0   # 5 Stufen, ERR 5 = fiktiver Boden

    def _y_to_err(self, y: float) -> int:
        usable = _CANVAS_H - _PAD_T - _PAD_B
        err = 1.0 + (y - _PAD_T) * 4.0 / usable
        return max(1, min(4, round(err)))

    def _rebuild_timeline(self):
        self._timeline = []
        self._tip_cx   = {}
        pause_map = {p.after_tip: p for p in self._pauses}
        for tip in self._tips:
            self._timeline.append(tip)
            if tip.number in pause_map:
                self._timeline.append(pause_map[tip.number])

        px_per_min = _BASE_PX_MIN * self._scale
        x = float(_PAD_L)
        for item in self._timeline:
            if isinstance(item, TipSlot):
                w = self._tip_min * px_per_min
                self._tip_cx[item.number] = x + w / 2
                x += w
            else:
                x += item.duration_min * px_per_min

    def _tip_rect(self, tip: TipSlot) -> tuple:
        px_per_min = _BASE_PX_MIN * self._scale
        cx = self._tip_cx.get(tip.number, 0)
        w  = self._tip_min * px_per_min
        return cx - w / 2, w

    def _find_pause_at(self, x: float) -> int:
        """Gibt after_tip der Pause an Position x zurück (0 = keine Pause dort)."""
        px_per_min = _BASE_PX_MIN * self._scale
        cx = float(_PAD_L)
        for item in self._timeline:
            iw = (self._tip_min if isinstance(item, TipSlot)
                  else item.duration_min) * px_per_min
            if isinstance(item, PauseBlock) and cx <= x < cx + iw:
                return item.after_tip
            cx += iw
        return 0

    def _find_gap_at(self, x: float) -> int:
        """Findet die Tipp-Nummer nach der eine Pause bei x-Koordinate einzufügen wäre."""
        n = len(self._tips)
        if n <= 1:
            return 1
        px_per_min = _BASE_PX_MIN * self._scale
        best_num, best_dist = 1, float('inf')
        cx = float(_PAD_L)
        for item in self._timeline:
            if isinstance(item, TipSlot):
                iw = self._tip_min * px_per_min
                right_x = cx + iw
                if item.number < n:   # Einfügen nach letztem Tipp nicht erlaubt
                    dist = abs(x - right_x)
                    if dist < best_dist:
                        best_dist = dist
                        best_num  = item.number
                cx = right_x
            else:
                cx += item.duration_min * px_per_min
        return best_num

    def _gap_x(self, after_tip: int) -> float:
        """X-Koordinate der Grenze nach tip with number=after_tip."""
        for tip in self._tips:
            if tip.number == after_tip:
                tx, tw = self._tip_rect(tip)
                return tx + tw
        return float(_PAD_L)

    # ── Paint ──────────────────────────────────────────────────────────────────

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()

        p.fillRect(0, 0, w, h, self._col_bg)

        grid_pen   = QPen(self._col_grid, 1, Qt.DotLine)
        label_font = QFont()
        label_font.setPointSize(8)
        p.setFont(label_font)
        for err in range(1, 5):
            y = int(self._err_to_y(err))
            p.setPen(grid_pen)
            p.drawLine(_PAD_L, y, w, y)
            p.setPen(_ERR_COL[err])
            p.drawText(2, y + 4, str(err))

        if not self._timeline:
            p.end()
            return

        px_per_min      = _BASE_PX_MIN * self._scale
        pause_after_set = {pb.after_tip for pb in self._pauses}

        # Pausen-Blöcke
        x = float(_PAD_L)
        for item in self._timeline:
            iw = (self._tip_min if isinstance(item, TipSlot)
                  else item.duration_min) * px_per_min
            if isinstance(item, PauseBlock):
                r   = QRect(int(x), _PAD_T, int(iw), h - _PAD_T - _PAD_B)
                alpha = 80 if item.after_tip == self._drag_pause_after else 255
                bg  = QColor(self._col_pause_bg.red(), self._col_pause_bg.green(),
                             self._col_pause_bg.blue(), alpha)
                p.fillRect(r, bg)
                p.setPen(self._col_pause_bd)
                p.drawRect(r)
                p.setPen(self._col_fg_dim)
                p.setFont(label_font)
                p.drawText(r, Qt.AlignCenter, f"PAUSE\n{item.duration_min} min")
            x += iw

        # Block-Trennstreifen
        for tip in self._tips:
            if (tip.number in self._block_starts
                    and tip.number - 1 not in pause_after_set):
                tx, _ = self._tip_rect(tip)
                p.fillRect(int(tx) - _BLOCK_DIV_W // 2, _PAD_T,
                           _BLOCK_DIV_W, h - _PAD_T - _PAD_B,
                           self._col_block_div)

        # ERR-Balken
        y_floor = _CANVAS_H - _PAD_B
        _UNRATED_COL = QColor("#808080")

        def _draw_bar(bx, bw, err, confirmed, fallback_err=0):
            # Song zugewiesen aber ERR=0 (nicht bewertet) → Balken grau auf Ziel-ERR-Höhe
            unrated = (err == 0 and fallback_err > 0)
            display_err = err if err > 0 else fallback_err
            if display_err <= 0:
                return
            base = _UNRATED_COL if unrated else _ERR_COL[display_err]
            col  = base   # Vollfarbe für bestätigte wie unbestätigte Balken
            y_top = self._err_to_y(display_err)
            p.fillRect(int(bx), int(y_top), int(bw), int(y_floor - y_top), col)

        lbl_font = QFont()
        lbl_font.setPointSize(7)
        lbl_font.setBold(True)

        for tip in self._tips:
            tx, tw = self._tip_rect(tip)
            bw     = max(2.0, tw * 0.36)
            p_fallback = tip.target_err if tip.patter_id else 0
            s_fallback = tip.target_err if tip.singer_id else 0
            _draw_bar(tx + tw * 0.06, bw, tip.patter_err, tip.patter_confirmed, p_fallback)
            _draw_bar(tx + tw * 0.58, bw, tip.singer_err, tip.singer_confirmed, s_fallback)

            # P/S-Label in Balken (nur wenn breit genug)
            if bw >= 12:
                p.setFont(lbl_font)
                p.setPen(QColor(255, 255, 255, 200))
                for lbl, bx_off, err in (
                    ("P", tw * 0.06, tip.patter_err or (tip.target_err if tip.patter_id else 0)),
                    ("S", tw * 0.58, tip.singer_err or (tip.target_err if tip.singer_id else 0)),
                ):
                    if err > 0:
                        bar_top = self._err_to_y(err)
                        bar_h   = y_floor - bar_top
                        if bar_h >= 10:
                            p.drawText(
                                QRect(int(tx + bx_off), int(bar_top),
                                      int(bw), int(bar_h)),
                                Qt.AlignHCenter | Qt.AlignTop, lbl,
                            )

            if tip.number == self._selected:
                p.setPen(QPen(self._col_fg, 1))
                p.setBrush(Qt.NoBrush)
                p.drawRect(int(tx) + 1, _PAD_T, int(tw) - 2,
                           h - _PAD_T - _PAD_B - 1)

            p.setPen(self._col_fg_dim)
            p.setFont(label_font)
            p.drawText(int(tx), h - _PAD_B + 2, int(tw), _PAD_B - 2,
                       Qt.AlignHCenter | Qt.AlignTop, str(tip.number))

        # Tipp-Trennlinien (1px, zwischen je zwei Tips ohne Pause dazwischen)
        tip_div_pen = QPen(self._col_tip_div, 1, Qt.SolidLine)
        for tip in self._tips[:-1]:
            if tip.number not in pause_after_set:
                tx, tw = self._tip_rect(tip)
                lx = int(tx + tw)
                p.setPen(tip_div_pen)
                p.drawLine(lx, _PAD_T, lx, h - _PAD_B)

        # Bezier-Kurve
        pts = [(self._tip_cx[t.number], self._err_to_y(t.target_err))
               for t in self._tips if t.number in self._tip_cx]
        if len(pts) >= 2:
            self._draw_catmull_rom(p, pts)

        # Drag-Handles (jeder Tipp)
        for tip in self._tips:
            cx = self._tip_cx.get(tip.number)
            if cx is None:
                continue
            cy  = self._err_to_y(tip.target_err)
            col = _ERR_COL.get(tip.target_err, self._col_fg)
            p.setPen(QPen(self._col_fg, 1))
            p.setBrush(QBrush(col))
            p.drawEllipse(int(cx - _HANDLE_R), int(cy - _HANDLE_R),
                          _HANDLE_R * 2, _HANDLE_R * 2)

        # Drop-Indikator während Pause-Drag
        if self._drag_pause_after > 0 and self._drag_pause_drop > 0:
            drop_x = self._gap_x(self._drag_pause_drop)
            ind_pen = QPen(self._col_drop, 3, Qt.SolidLine)
            ind_pen.setCapStyle(Qt.RoundCap)
            p.setPen(ind_pen)
            p.drawLine(int(drop_x), _PAD_T, int(drop_x), h - _PAD_B)
            # Kleines Dreieck oben als Pfeil
            p.setBrush(QBrush(self._col_drop))
            p.setPen(Qt.NoPen)
            tri_x = int(drop_x)
            p.drawPolygon(QPolygon([
                QPoint(tri_x - 5, _PAD_T),
                QPoint(tri_x + 5, _PAD_T),
                QPoint(tri_x,     _PAD_T + 8),
            ]))

        p.end()

    def _draw_catmull_rom(self, painter, pts):
        n    = len(pts)
        path = QPainterPath()
        path.moveTo(pts[0][0], pts[0][1])
        for i in range(n - 1):
            p0   = pts[max(0, i - 1)]
            p1   = pts[i]
            p2   = pts[i + 1]
            p3   = pts[min(n - 1, i + 2)]
            cp1x = p1[0] + (p2[0] - p0[0]) / 6
            cp1y = p1[1] + (p2[1] - p0[1]) / 6
            cp2x = p2[0] - (p3[0] - p1[0]) / 6
            cp2y = p2[1] - (p3[1] - p1[1]) / 6
            path.cubicTo(cp1x, cp1y, cp2x, cp2y, p2[0], p2[1])
        pen = QPen(self._col_fg, 2, Qt.SolidLine)
        pen.setCapStyle(Qt.RoundCap)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawPath(path)

    # ── Mouse ──────────────────────────────────────────────────────────────────

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() != Qt.LeftButton:
            return
        x, y = event.position().x(), event.position().y()

        # Pause-Drag prüfen (hat Vorrang)
        after = self._find_pause_at(x)
        if after:
            self._drag_pause_after = after
            self._drag_pause_drop  = after
            self._drag_pause_x     = x
            self.update()
            return

        # ERR-Handle-Drag
        for tip in self._tips:
            cx = self._tip_cx.get(tip.number, -999)
            cy = self._err_to_y(tip.target_err)
            if (x - cx) ** 2 + (y - cy) ** 2 <= (_HANDLE_R + 3) ** 2:
                self._drag_tip     = tip.number
                self._drag_start_y = y
                return

        # Tipp-Auswahl
        num = self._find_tip_at(x)
        if num:
            self._selected = num
            self.update()
            self.sig_tip_selected.emit(num)

    def mouseMoveEvent(self, event: QMouseEvent):
        x, y = event.position().x(), event.position().y()

        if self._drag_pause_after > 0:
            self._drag_pause_x    = x
            self._drag_pause_drop = self._find_gap_at(x)
            self.update()
            return

        if self._drag_tip:
            new_err = self._y_to_err(y)
            for tip in self._tips:
                if tip.number == self._drag_tip:
                    tip.target_err = new_err
                    break
            self.update()

    def mouseReleaseEvent(self, event: QMouseEvent):
        if event.button() != Qt.LeftButton:
            return

        if self._drag_pause_after > 0:
            old = self._drag_pause_after
            new = self._drag_pause_drop
            self._drag_pause_after = 0
            self._drag_pause_drop  = 0
            self.update()
            if new > 0 and new != old:
                self.sig_pause_moved.emit(old, new)
            return

        if self._drag_tip:
            for tip in self._tips:
                if tip.number == self._drag_tip:
                    self.sig_target_changed.emit(self._drag_tip, tip.target_err)
                    break
            self._drag_tip = 0

    def mouseDoubleClickEvent(self, event: QMouseEvent):
        if event.button() != Qt.LeftButton:
            return
        x, y = event.position().x(), event.position().y()
        y_floor = _CANVAS_H - _PAD_B
        if not (_PAD_T <= y <= y_floor):
            return
        for tip in self._tips:
            tx, tw = self._tip_rect(tip)
            bw = max(2.0, tw * 0.36)
            # Pattern-Balken: linke Seite
            p_l = tx + tw * 0.06
            if p_l <= x <= p_l + bw and tip.patter_err > 0:
                self.sig_slot_requested.emit(tip.number, 'pattern')
                return
            # Singing-Balken: rechte Seite
            s_l = tx + tw * 0.58
            if s_l <= x <= s_l + bw and tip.singer_err > 0:
                self.sig_slot_requested.emit(tip.number, 'singing')
                return

    def _find_tip_at(self, x: float) -> int:
        px_per_min = _BASE_PX_MIN * self._scale
        cx = float(_PAD_L)
        for item in self._timeline:
            iw = (self._tip_min if isinstance(item, TipSlot)
                  else item.duration_min) * px_per_min
            if isinstance(item, TipSlot) and cx <= x < cx + iw:
                return item.number
            cx += iw
        return 0


# ─── Planner Table ─────────────────────────────────────────────────────────────

class PlannerTable(QTableWidget):
    """Detailansicht; Pausen können per Drag & Drop verschoben werden."""

    sig_pause_moved    = Signal(int, int)   # (old_after_tip, new_after_tip)
    sig_pause_deleted  = Signal(int)        # after_tip der gelöschten Pause
    sig_slot_requested = Signal(int, str)   # (tip_number, 'pattern'|'singing')

    _COLS = ["ep_col_time", "ep_col_num", "ep_col_pattern_title", "ep_col_pattern_label",
             "ep_col_pattern_err", "ep_col_singing_title", "ep_col_singing_label", "ep_col_singing_err"]
    # UserRole auf Spalte 0: after_tip (Pausenzeile) oder 0 (Tippzeile)
    # UserRole auf Spalte 1: tip.number (Tippzeile) oder None (Pausenzeile)

    def __init__(self, parent=None):
        super().__init__(0, len(self._COLS), parent)
        self.setHorizontalHeaderLabels([_t(k) for k in self._COLS])
        self.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.setSelectionMode(QAbstractItemView.SingleSelection)
        self.setAlternatingRowColors(True)
        self.verticalHeader().setVisible(False)
        hdr = self.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(2, QHeaderView.Stretch)
        hdr.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(4, QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(5, QHeaderView.Stretch)
        hdr.setSectionResizeMode(6, QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(7, QHeaderView.ResizeToContents)

        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDragDropMode(QAbstractItemView.InternalMove)
        self.setDropIndicatorShown(True)
        self._dragging_pause_after = 0
        self._block_starts: set = set()
        # Theme-Farben (Defaults dunkel; via set_skin_colors überschrieben).
        # Der Rest der Tabelle folgt bewusst der globalen QSS-Palette
        # (Alternating Rows, Text) — Farbe nur wo sie Bedeutung trägt.
        self._col_block_sep = QColor("#3a4a6a")
        self._col_text_dim  = QColor("#888ea0")
        self._col_pause_bg  = QColor("#2e3440")
        self._col_pause_fg  = QColor("#99a0ae")
        self.itemDoubleClicked.connect(self._on_item_double_clicked)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._on_context_menu)

    # ── Theme ──────────────────────────────────────────────────────────────────

    def set_skin_colors(self, block_sep, text_dim, pause_bg, pause_fg):
        self._col_block_sep = block_sep
        self._col_text_dim  = text_dim
        self._col_pause_bg  = pause_bg
        self._col_pause_fg  = pause_fg

    # ── Rebuild ────────────────────────────────────────────────────────────────

    def rebuild(self, tips, pauses, block_starts=None):
        self._block_starts = block_starts or set()
        self.setUpdatesEnabled(False)
        self.setRowCount(0)
        pause_map = {p.after_tip: p for p in pauses}
        for tip in tips:
            if tip.number in self._block_starts:
                self._add_block_sep_row()
            self._add_tip_row(tip)
            if tip.number in pause_map:
                self._add_pause_row(pause_map[tip.number])
        self.setUpdatesEnabled(True)

    def select_tip(self, number: int):
        for row in range(self.rowCount()):
            item = self.item(row, 1)
            if item and item.data(Qt.UserRole) == number:
                self.selectRow(row)
                self.scrollToItem(item)
                return

    def _on_item_double_clicked(self, item):
        row = item.row()
        col = item.column()
        tip_item = self.item(row, 1)
        if not tip_item:
            return
        tip_num = tip_item.data(Qt.UserRole)
        if not isinstance(tip_num, int) or tip_num <= 0:
            return  # Pausenzeile
        if 2 <= col <= 4:
            self.sig_slot_requested.emit(tip_num, 'pattern')
        elif 5 <= col <= 7:
            self.sig_slot_requested.emit(tip_num, 'singing')

    def _on_context_menu(self, pos):
        """Rechtsklick-Kontextmenü — zeigt 'Pause löschen' für Pausenzeilen."""
        row = self.rowAt(pos.y())
        if row < 0:
            return
        after_tip = self._pause_after_for_row(row)
        if after_tip == 0:
            return   # Tipp- oder Trennzeile — kein Menü
        menu = QMenu(self)
        act = menu.addAction(_t("ep_ctx_delete_pause"))
        chosen = menu.exec(self.viewport().mapToGlobal(pos))
        if chosen is act:
            self.sig_pause_deleted.emit(after_tip)

    # ── Drag & Drop ────────────────────────────────────────────────────────────

    def startDrag(self, supported_actions):
        row = self.currentRow()
        after_tip = self._pause_after_for_row(row)
        if after_tip == 0:
            return   # Tipp-Zeilen nicht draggbar
        self._dragging_pause_after = after_tip
        super().startDrag(supported_actions)

    def dropEvent(self, event):
        if self._dragging_pause_after == 0:
            event.ignore()
            return

        y = int(event.position().toPoint().y())
        target_row = self.rowAt(y)
        if target_row < 0:
            target_row = self.rowCount() - 1

        old_after = self._dragging_pause_after
        new_after = self._tip_above_row(target_row)
        self._dragging_pause_after = 0

        event.ignore()   # Zeile nicht physisch verschieben — rebuild folgt
        if new_after > 0 and new_after != old_after:
            self.sig_pause_moved.emit(old_after, new_after)

    # ── Hilfsmethoden ──────────────────────────────────────────────────────────

    def _pause_after_for_row(self, row) -> int:
        """Gibt after_tip zurück wenn row eine Pausenzeile ist, sonst 0."""
        item = self.item(row, 0)
        return item.data(Qt.UserRole) if item else 0

    def _tip_above_row(self, target_row) -> int:
        """Tipp-Nummer der letzten Tipp-Zeile bis einschließlich target_row."""
        last = 0
        for r in range(min(target_row + 1, self.rowCount())):
            item = self.item(r, 1)
            if item:
                num = item.data(Qt.UserRole)
                if isinstance(num, int) and num > 0:
                    last = num
        return last

    # ── Zeilen aufbauen ────────────────────────────────────────────────────────

    def _add_tip_row(self, tip: TipSlot):
        row = self.rowCount()
        self.insertRow(row)

        def cell(text, confirmed=True):
            """Titel-/Label-Zelle: folgt dem Theme (normale Textfarbe).
            Unbestätigte Vorschläge nur kursiv — so bleiben sie auch im
            dunklen Theme gut lesbar."""
            it = QTableWidgetItem(text)
            it.setTextAlignment(Qt.AlignVCenter | Qt.AlignLeft)
            if not confirmed:
                font = it.font()
                font.setItalic(True)
                it.setFont(font)
            return it

        def err_badge(err):
            """ERR-Wert als satter Badge: weiße fette Zahl auf voller ERR-Farbe.
            Deckend in beiden Themes; ob Vorschlag/fix zeigt die Titelspalte.
            Leerer Wert = dezenter Strich in Theme-Farbe."""
            if err <= 0:
                it = QTableWidgetItem("—")
                it.setTextAlignment(Qt.AlignCenter)
                it.setForeground(self._col_text_dim)
                return it
            it = QTableWidgetItem(str(err))
            it.setTextAlignment(Qt.AlignCenter)
            it.setBackground(_ERR_COL.get(err, QColor("#808080")))
            it.setForeground(QColor("#ffffff"))
            font = it.font()
            font.setBold(True)
            it.setFont(font)
            return it

        h        = tip.elapsed_min
        time_str = f"{h // 60}:{h % 60:02d}"
        time_it  = QTableWidgetItem(time_str)
        time_it.setData(Qt.UserRole, 0)   # 0 = Tipp-Zeile
        time_it.setTextAlignment(Qt.AlignVCenter | Qt.AlignLeft)
        num_item = QTableWidgetItem(str(tip.number))
        num_item.setData(Qt.UserRole, tip.number)
        num_item.setTextAlignment(Qt.AlignCenter)

        self.setItem(row, 0, time_it)
        self.setItem(row, 1, num_item)
        self.setItem(row, 2, cell(tip.patter_title or "—", tip.patter_confirmed))
        self.setItem(row, 3, cell(tip.patter_label or "",  tip.patter_confirmed))
        self.setItem(row, 4, err_badge(tip.patter_err))
        self.setItem(row, 5, cell(tip.singer_title or "—", tip.singer_confirmed))
        self.setItem(row, 6, cell(tip.singer_label or "",  tip.singer_confirmed))
        self.setItem(row, 7, err_badge(tip.singer_err))

    def _add_block_sep_row(self):
        """Dünne farbige Linie als Block-Trenner."""
        row = self.rowCount()
        self.insertRow(row)
        self.setRowHeight(row, 3)
        for col in range(self.columnCount()):
            it = QTableWidgetItem("")
            it.setBackground(self._col_block_sep)
            it.setFlags(Qt.NoItemFlags)
            it.setData(Qt.UserRole, None)
            self.setItem(row, col, it)

    def _add_pause_row(self, pause: PauseBlock):
        row = self.rowCount()
        self.insertRow(row)
        h        = pause.elapsed_min
        time_str = f"{h // 60}:{h % 60:02d}"
        time_it  = QTableWidgetItem(time_str)
        time_it.setData(Qt.UserRole, pause.after_tip)   # after_tip für Drag
        self.setItem(row, 0, time_it)

        time_it.setBackground(self._col_pause_bg)
        label  = _t("ep_pause_row", dur=pause.duration_min)
        merged = QTableWidgetItem(label)
        merged.setTextAlignment(Qt.AlignCenter)
        merged.setForeground(self._col_pause_fg)
        merged.setBackground(self._col_pause_bg)
        font = merged.font()
        font.setBold(True)
        merged.setFont(font)
        self.setItem(row, 1, merged)
        for col in range(2, self.columnCount()):
            it = QTableWidgetItem("")
            it.setBackground(self._col_pause_bg)
            self.setItem(row, col, it)
        self.setSpan(row, 1, 1, self.columnCount() - 1)


# ─── Evening Planner Widget ────────────────────────────────────────────────────

class EveningPlannerWidget(QWidget):
    """Hauptwidget: Toolbar (2 Zeilen) + CurveCanvas + PlannerTable."""

    sig_export_to_playlist = Signal(list)  # list of (song_id, mode) tuples, mode='P'/'S' (confirmed, in tip-order)
    sig_export_to_notes    = Signal(list)  # list of song-titles (Strings)

    def __init__(self, db, settings=None, parent=None):
        super().__init__(parent)
        self._db          = db
        self._settings    = settings
        self._location_id: Optional[int] = None
        self._start_date:  Optional[date] = None
        self._tips:  list  = []
        self._pauses: list = []
        self._overrides: dict = {}
        self._strategy    = 1
        self._block_min   = 3
        self._block_max   = 5
        self._tip_min     = _TIP_MIN_DEFAULT
        self._block_starts: set = set()
        self._curve_eng   = CurveEngine()
        # Zufalls-Tiebreaker (wie BL-113 im Planner): stabile Zufallswerte pro
        # Song fuer die Session; geteilter INI-Eintrag sort/random_tiebreaker
        # (derselbe wie die Tiebreaker-Checkbox in Songliste + Planner)
        self._sort_random: dict = {}   # {song_id: float}
        self._shuffle_tb = True
        if settings is not None:
            self._shuffle_tb = str(settings.value(
                "sort/random_tiebreaker", "true")).lower() == "true"
        self._scorer      = SongScorer(db, tiebreaker=self._tb_value)
        self._selected_tip = 0
        self._rules = {
            'balance':           True,
            'same_genre_tip':    False,
            'same_genre_factor': 3,
            'same_label_tip':    False,
            'same_label_factor': 3,
            'first_tip_soft':    True,
            'last_tip_strong':   True,
        }
        self._genre_filter:     frozenset = frozenset()  # Aktiver Genre-Filter
        self._genres_available: list      = []           # Alle bekannten Genres
        self._build_ui()
        self._rebuild_plan()

    # ── UI-Aufbau ──────────────────────────────────────────────────────────────

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(4, 4, 4, 4)
        root.setSpacing(3)

        # ── Zeile 1: Parameter ─────────────────────────────────────────────────
        row1 = QHBoxLayout()
        row1.setSpacing(6)

        row1.addWidget(QLabel(_t("ep_label_tips")))
        self._spin_tips = QSpinBox()
        self._spin_tips.setRange(1, 40)
        self._spin_tips.setValue(12)
        self._spin_tips.setMaximumWidth(68)
        self._spin_tips.setToolTip(_t("ep_tooltip_tips"))
        self._spin_tips.valueChanged.connect(self._on_param_changed)
        row1.addWidget(self._spin_tips)

        row1.addWidget(_vline())

        row1.addWidget(QLabel(_t("ep_label_tip_len")))
        self._spin_tip_len = QSpinBox()
        self._spin_tip_len.setRange(5, 30)
        self._spin_tip_len.setValue(self._tip_min)
        self._spin_tip_len.setSingleStep(5)
        self._spin_tip_len.setSuffix(" min")
        self._spin_tip_len.setMaximumWidth(86)
        self._spin_tip_len.setToolTip(_t("ep_tooltip_tip_len"))
        self._spin_tip_len.valueChanged.connect(self._on_tip_len_changed)
        row1.addWidget(self._spin_tip_len)

        row1.addWidget(_vline())

        row1.addWidget(QLabel(_t("ep_label_block")))
        self._spin_min = QSpinBox()
        self._spin_min.setRange(2, 8)
        self._spin_min.setValue(self._block_min)
        self._spin_min.setMaximumWidth(56)
        self._spin_min.setToolTip(_t("ep_tooltip_block_min"))
        self._spin_min.valueChanged.connect(self._on_param_changed)
        row1.addWidget(self._spin_min)
        row1.addWidget(QLabel("-"))
        self._spin_max = QSpinBox()
        self._spin_max.setRange(2, 10)
        self._spin_max.setValue(self._block_max)
        self._spin_max.setMaximumWidth(56)
        self._spin_max.setToolTip(_t("ep_tooltip_block_max"))
        self._spin_max.valueChanged.connect(self._on_param_changed)
        row1.addWidget(self._spin_max)

        row1.addWidget(_vline())

        row1.addWidget(QLabel(_t("ep_label_strategy")))
        self._combo_strat = QComboBox()
        for val, key in _STRATEGY_LABELS:
            self._combo_strat.addItem(_t(key), val)
        self._combo_strat.currentIndexChanged.connect(self._on_param_changed)
        row1.addWidget(self._combo_strat)

        row1.addWidget(_vline())

        self._chk_genre_active = QCheckBox(_t("ep_label_genre"))
        self._chk_genre_active.setToolTip(_t("ep_tooltip_genre"))
        self._chk_genre_active.toggled.connect(self._on_genre_toggle)
        row1.addWidget(self._chk_genre_active)

        self._btn_genre = QPushButton(_t("ep_btn_genre_none"))
        self._btn_genre.setToolTip(_t("ep_tooltip_genre"))
        self._btn_genre.setMaximumWidth(120)
        self._btn_genre.clicked.connect(self._open_genre_dialog)
        row1.addWidget(self._btn_genre)

        row1.addWidget(_vline())

        self._btn_shuffle = QPushButton(_t("ep_btn_shuffle"))
        mark_toggle(self._btn_shuffle, active=True)
        self._btn_shuffle.setChecked(self._shuffle_tb)
        self._btn_shuffle.setToolTip(_t("ep_tooltip_shuffle"))
        self._btn_shuffle.toggled.connect(self._on_shuffle_toggled)
        row1.addWidget(self._btn_shuffle)

        row1.addStretch()

        self._lbl_duration = QLabel("")
        self._lbl_duration.setToolTip(_t("ep_tooltip_duration"))
        row1.addWidget(self._lbl_duration)

        root.addLayout(row1)

        # ── Zeile 2: Aktions-Buttons ────────────────────────────────────────────
        row2 = QHBoxLayout()
        row2.setSpacing(4)

        self._btn_zoom_out = QPushButton("-")
        self._btn_zoom_out.setToolTip(_t("ep_tooltip_zoom_out"))
        self._btn_zoom_out.clicked.connect(lambda: self._zoom(-0.25))
        row2.addWidget(self._btn_zoom_out)

        self._btn_zoom_in = QPushButton("+")
        self._btn_zoom_in.setToolTip(_t("ep_tooltip_zoom_in"))
        self._btn_zoom_in.clicked.connect(lambda: self._zoom(0.25))
        row2.addWidget(self._btn_zoom_in)

        self._btn_zoom_fit = QPushButton("")          # Icon only — kein Text
        self._btn_zoom_fit.setToolTip(_t("ep_tooltip_zoom_fit"))
        self._btn_zoom_fit.clicked.connect(self._zoom_fit)
        row2.addWidget(self._btn_zoom_fit)

        row2.addWidget(_vline())

        self._btn_reset = QPushButton(_t("ep_btn_reset"))   # kein Icon
        self._btn_reset.setToolTip(_t("ep_tooltip_reset"))
        self._btn_reset.clicked.connect(self._reset_curve)
        row2.addWidget(self._btn_reset)

        row2.addWidget(_vline())

        self._btn_add_pause = QPushButton(_t("ep_btn_add_pause"))  # kein Icon
        self._btn_add_pause.setToolTip(_t("ep_tooltip_add_pause"))
        self._btn_add_pause.clicked.connect(self._add_pause)
        row2.addWidget(self._btn_add_pause)

        row2.addWidget(_vline())

        self._btn_rules = QPushButton(_t("ep_btn_rules"))   # kein Icon
        self._btn_rules.setToolTip(_t("ep_tooltip_rules"))
        self._btn_rules.clicked.connect(self._show_rules)
        row2.addWidget(self._btn_rules)

        row2.addWidget(_vline())

        self._btn_fill_all = QPushButton(_t("ep_btn_fill_all"))  # kein Icon
        self._btn_fill_all.setToolTip(_t("ep_tooltip_fill_all"))
        self._btn_fill_all.clicked.connect(self._fill_all)
        row2.addWidget(self._btn_fill_all)

        self._btn_clear = QPushButton(_t("ep_btn_clear"))   # kein Icon
        self._btn_clear.setToolTip(_t("ep_tooltip_clear"))
        self._btn_clear.clicked.connect(self._clear_all)
        row2.addWidget(self._btn_clear)

        row2.addStretch()

        root.addLayout(row2)

        # ── Canvas in ScrollArea ───────────────────────────────────────────────
        self._canvas = CurveCanvas()
        self._canvas.sig_tip_selected.connect(self._on_tip_selected)
        self._canvas.sig_target_changed.connect(self._on_target_changed)
        self._canvas.sig_pause_moved.connect(self._on_pause_moved)
        self._canvas.sig_slot_requested.connect(self._open_candidate_dialog)

        self._scroll = QScrollArea()
        self._scroll.setWidget(self._canvas)
        self._scroll.setWidgetResizable(False)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self._scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._scroll.setFrameShape(QFrame.NoFrame)
        self._scroll.setFixedHeight(_CANVAS_H + 4)
        root.addWidget(self._scroll)

        # BL-166: STRG + Mausrad zoomt wie die +/- Buttons
        install_ctrl_wheel_zoom(self._scroll,
                                lambda: self._zoom(0.25),
                                lambda: self._zoom(-0.25))

        # ── Tabelle ────────────────────────────────────────────────────────────
        self._table = PlannerTable()
        self._table.itemSelectionChanged.connect(self._on_table_selection)
        self._table.sig_pause_moved.connect(self._on_pause_moved)
        self._table.sig_pause_deleted.connect(self._on_pause_deleted)
        self._table.sig_slot_requested.connect(self._open_candidate_dialog)
        root.addWidget(self._table, 1)

        # ── Transfer-Buttons (unter der Tabelle, zentriert) ────────────────────
        transfer_row = QHBoxLayout()
        transfer_row.addStretch()
        self._btn_to_playlist = QPushButton(_t("ep_btn_to_playlist"))
        self._btn_to_playlist.setToolTip(_t("ep_tooltip_to_playlist"))
        self._btn_to_playlist.clicked.connect(self._transfer_to_playlist)
        transfer_row.addWidget(self._btn_to_playlist)
        self._btn_to_notes = QPushButton(_t("ep_btn_to_notes"))
        self._btn_to_notes.setToolTip(_t("ep_tooltip_to_notes"))
        self._btn_to_notes.clicked.connect(self._transfer_to_notes)
        transfer_row.addWidget(self._btn_to_notes)
        transfer_row.addStretch()
        root.addLayout(transfer_row)

    # ── Skin ───────────────────────────────────────────────────────────────────

    def apply_skin(self, skin_mgr):
        icon_col = skin_mgr.color("button_text", "#ffffff") if skin_mgr else "#ffffff"
        for attr, svg in _ALL_BTNS_SVGS:
            btn = getattr(self, attr, None)
            if btn:
                btn.setIcon(_make_icon(svg, icon_col))

        for btn in (self._btn_zoom_out, self._btn_zoom_in, self._btn_zoom_fit,
                    self._btn_reset, self._btn_add_pause, self._btn_rules,
                    self._btn_fill_all, self._btn_clear):
            btn.setMinimumWidth(btn.sizeHint().width() + 4)

        if skin_mgr:
            bg       = QColor(skin_mgr.color("widget_bg",    "#1e2229"))
            fg       = QColor(skin_mgr.color("text",         "#e8e8e8"))
            fg_dim   = QColor(skin_mgr.color("text_dim",     "#888ea0"))
            grid     = QColor(skin_mgr.color("border",       "#333a45"))
            pause_bg = QColor(skin_mgr.color("muted_bg",     "#2e3440"))
            pause_bd = QColor(skin_mgr.color("border",       "#606878"))
            drop     = QColor(skin_mgr.color("selection_bg", "#0078d4"))
            sel      = drop
            block_div = QColor(
                int(bg.red()   * 0.72 + sel.red()   * 0.28),
                int(bg.green() * 0.72 + sel.green()  * 0.28),
                int(bg.blue()  * 0.72 + sel.blue()   * 0.28),
            )
            tip_div = QColor(
                int(bg.red()   * 0.5 + fg.red()   * 0.5),
                int(bg.green() * 0.5 + fg.green() * 0.5),
                int(bg.blue()  * 0.5 + fg.blue()  * 0.5),
            )
        else:
            bg        = QColor("#1e2229")
            fg        = QColor("#e8e8e8")
            fg_dim    = QColor("#888ea0")
            grid      = QColor("#333a45")
            pause_bg  = QColor("#2e3440")
            pause_bd  = QColor("#606878")
            block_div = QColor("#3a4a6a")
            drop      = QColor("#0078d4")
            tip_div   = QColor("#626872")

        self._canvas.set_skin_colors(bg, fg, fg_dim, grid, pause_bg, pause_bd,
                                     block_div, drop, tip_div)
        self._table.set_skin_colors(block_sep=block_div, text_dim=fg_dim,
                                    pause_bg=pause_bg, pause_fg=fg_dim)
        if self._tips:   # Farben sofort anwenden (z.B. bei Theme-Wechsel)
            self._refresh_views()

    # ── Resize ─────────────────────────────────────────────────────────────────

    def resizeEvent(self, event):
        super().resizeEvent(event)
        QTimer.singleShot(0, self._zoom_fit)

    # ── Planlogik ──────────────────────────────────────────────────────────────

    def set_planned_tips(self, n: int):
        """Setzt die Tips-Anzahl aus der Lokation als Voreinstellung."""
        if n and n > 0:
            self._spin_tips.setValue(n)

    def set_location(self, location_id: Optional[int]):
        self._location_id = location_id
        # Genres aus DB laden (einmalig bei Lokationswechsel)
        try:
            self._genres_available = self._db.get_genres()
        except Exception:
            self._genres_available = []
        self._rebuild_suggestions()
        self._refresh_views()

    def set_start_date(self, start_date: Optional[date]):
        self._start_date = start_date

    def _days_fallback(self) -> int:
        if self._start_date:
            return max(1, (date.today() - self._start_date).days)
        return _DEFAULT_DAYS_FALLBACK

    def _on_param_changed(self):
        self._block_min = self._spin_min.value()
        self._block_max = max(self._block_min, self._spin_max.value())
        self._spin_max.setMinimum(self._block_min)
        self._strategy  = self._combo_strat.currentData()
        self._rebuild_plan()

    def _on_tip_len_changed(self):
        self._tip_min = self._spin_tip_len.value()
        self._canvas.set_tip_min(self._tip_min)
        self._rebuild_plan()

    def _rebuild_plan(self):
        n  = self._spin_tips.value()
        mn = self._spin_min.value()
        mx = max(mn, self._spin_max.value())
        pauses_after  = {p.after_tip for p in self._pauses}
        targets       = self._curve_eng.compute(n, pauses_after, mn, mx, self._overrides)
        block_starts  = self._curve_eng.get_block_starts(n, pauses_after, mn, mx)

        old = {t.number: t for t in self._tips}
        self._tips  = []
        elapsed     = 0
        pause_map   = {p.after_tip: p for p in self._pauses}

        for i, target_err in enumerate(targets):
            num = i + 1
            if num in old:
                tip = old[num]
                tip.target_err  = target_err
                tip.elapsed_min = elapsed
            else:
                tip = TipSlot(number=num, target_err=target_err, elapsed_min=elapsed)
            self._tips.append(tip)
            elapsed += self._tip_min
            if num in pause_map:
                pm = pause_map[num]
                pm.elapsed_min = elapsed
                elapsed += pm.duration_min

        self._block_starts = block_starts
        self._rebuild_suggestions()
        self._refresh_views()
        self._update_duration_label()
        QTimer.singleShot(0, self._zoom_fit)

    def _rebuild_suggestions(self):
        if not self._tips:
            return
        strat   = self._strategy
        n       = len(self._tips)
        rules   = self._rules
        days_fb = self._days_fallback()

        # Bestätigte Songs sofort sperren
        used_ids: set = (
            {t.patter_id for t in self._tips if t.patter_confirmed and t.patter_id}
            | {t.singer_id for t in self._tips if t.singer_confirmed and t.singer_id}
        )

        # Unbestätigte Slots leeren, die die aktuelle Strategie nicht mehr will
        for tip in self._tips:
            want_p = strat in (1, 2, 3)
            want_s = strat in (1, 2, 4) and (strat != 2 or tip.number in (1, n))
            if not want_s and not tip.singer_confirmed:
                tip.singer_id = None; tip.singer_title = ""
                tip.singer_label = ""; tip.singer_err = 0; tip.singer_genres = ()
            if not want_p and not tip.patter_confirmed:
                tip.patter_id = None; tip.patter_title = ""
                tip.patter_label = ""; tip.patter_err = 0

        # Optimale Zuweisung (Ungarischer Algorithmus) — Fallback: greedy
        try:
            self._fill_optimal(used_ids, strat, n, rules, days_fb)
        except ImportError:
            self._fill_greedy(used_ids, strat, n, rules, days_fb)

    # ── Optimale Zuweisung (scipy) ────────────────────────────────────────────

    def _fill_optimal(self, used_ids, strat, n, rules, days_fb):
        """Zwei-Phasen-Optimierung via Ungarischem Algorithmus (scipy).

        Phase 1: Singing-Slots → maximaler Gesamt-Score über alle Tipps.
        Phase 2: Pattern-Slots → maximaler Gesamt-Score, Balance/Genre/Label-Boost
                 bereits bekannt durch die Singing-Zuweisung aus Phase 1.
        """
        import numpy as np
        from scipy.optimize import linear_sum_assignment

        # Alle Songs einmal laden (eine DB-Abfrage für beide Phasen)
        all_rows = self._db.get_planner_candidates(0, self._location_id, days_fb)

        singing_pool, pattern_pool = [], []
        gf = self._active_genre_filter()   # frozenset, leer = kein Filter
        for row in all_rows:
            sid, title, label, err, quality, isp, iss, days, genres_str = row
            if sid in used_ids:
                continue
            genres = tuple(genres_str.split(',')) if genres_str else ()
            # Genre-Filter: nur Songs berücksichtigen, die mind. ein gewähltes Genre haben
            if gf and not (gf & frozenset(genres)):
                continue
            entry  = (sid, title, label, err, quality, int(days), genres)
            if iss: singing_pool.append(entry)
            if isp: pattern_pool.append(entry)

        def _singing_target(tip):
            t = tip.target_err
            if rules.get('first_tip_soft')  and tip.number == 1: t = min(t, 3)
            if rules.get('last_tip_strong') and tip.number == n: t = min(t, 2)
            return t

        def _pattern_target(tip):
            if rules.get('balance') and tip.singer_err > 0:
                return max(1, min(4, 5 - tip.singer_err))
            t = tip.target_err
            if rules.get('first_tip_soft')  and tip.number == 1: t = min(t, 3)
            if rules.get('last_tip_strong') and tip.number == n: t = min(t, 2)
            return t

        def _assign(slots, pool, is_singing):
            if not slots or not pool:
                for tip in slots:
                    if is_singing:
                        tip.singer_id = None; tip.singer_title = ""
                        tip.singer_label = ""; tip.singer_err = 0; tip.singer_genres = ()
                    else:
                        tip.patter_id = None; tip.patter_title = ""
                        tip.patter_label = ""; tip.patter_err = 0
                return

            ns, nc = len(slots), len(pool)
            mat = np.zeros((ns, nc))

            for i, tip in enumerate(slots):
                target = _singing_target(tip) if is_singing else _pattern_target(tip)
                sg_set  = frozenset(tip.singer_genres) if not is_singing else frozenset()
                s_code  = _label_code(tip.singer_label) if not is_singing else ""
                for j, (sid, title, label, err, quality, days, genres) in enumerate(pool):
                    score = SongScorer._score(quality, days, err, target)
                    if not is_singing and score > 0:
                        boost = 1
                        if rules.get('same_genre_tip') and sg_set & frozenset(genres):
                            boost *= rules.get('same_genre_factor', 3)
                        if rules.get('same_label_tip') and s_code and _label_code(label) == s_code:
                            boost *= rules.get('same_label_factor', 3)
                        score *= boost
                    if score > 0:
                        # Zufalls-Tiebreaker: winzige Streuung (≪ kleinster
                        # echter Score-Abstand) entscheidet Gleichstaende
                        score += 1e-6 * self._tb_value(sid)
                    mat[i, j] = score

            row_ind, col_ind = linear_sum_assignment(-mat)
            assigned = set(row_ind)

            for i, j in zip(row_ind, col_ind):
                tip = slots[i]
                if mat[i, j] <= 0:
                    assigned.discard(i)
                    continue
                sid, title, label, err, quality, days, genres = pool[j]
                if is_singing:
                    tip.singer_id = sid; tip.singer_title = title
                    tip.singer_label = label; tip.singer_err = err
                    tip.singer_genres = genres
                else:
                    tip.patter_id = sid; tip.patter_title = title
                    tip.patter_label = label; tip.patter_err = err
                used_ids.add(sid)

            # Nicht zugewiesene Slots leeren
            for i, tip in enumerate(slots):
                if i not in assigned:
                    if is_singing:
                        tip.singer_id = None; tip.singer_title = ""
                        tip.singer_label = ""; tip.singer_err = 0; tip.singer_genres = ()
                    else:
                        tip.patter_id = None; tip.patter_title = ""
                        tip.patter_label = ""; tip.patter_err = 0

        # Phase 1: Singing
        singing_slots = [t for t in self._tips
                         if strat in (1, 2, 4) and not t.singer_confirmed
                         and (strat != 2 or t.number in (1, n))]
        _assign(singing_slots, singing_pool, is_singing=True)

        # Phase 2: Pattern (Pool um neu verwendete Singings bereinigen)
        pattern_pool = [e for e in pattern_pool if e[0] not in used_ids]
        pattern_slots = [t for t in self._tips
                         if strat in (1, 2, 3) and not t.patter_confirmed]
        _assign(pattern_slots, pattern_pool, is_singing=False)

    # ── Greedy-Fallback ───────────────────────────────────────────────────────

    def _fill_greedy(self, used_ids, strat, n, rules, days_fb):
        """Sequentielle Greedy-Zuweisung — wird genutzt wenn scipy nicht verfügbar."""
        for tip in self._tips:
            want_p = strat in (1, 2, 3)
            want_s = strat in (1, 2, 4) and (strat != 2 or tip.number in (1, n))
            curve_target = tip.target_err

            gf = self._active_genre_filter() or None

            if want_s and not tip.singer_confirmed:
                s_target = curve_target
                if rules.get('first_tip_soft')  and tip.number == 1: s_target = min(s_target, 3)
                if rules.get('last_tip_strong') and tip.number == n: s_target = min(s_target, 2)
                cands = self._scorer.candidates(
                    s_target, self._location_id,
                    want_pattern=False, want_singing=True,
                    exclude_ids=used_ids, days_fallback=days_fb,
                    genre_filter=gf)
                if cands:
                    best = cands[0]
                    tip.singer_id = best.song_id; tip.singer_title = best.title
                    tip.singer_label = best.label; tip.singer_err = best.err
                    tip.singer_genres = best.genres
                    used_ids.add(best.song_id)
                else:
                    tip.singer_id = None; tip.singer_title = ""
                    tip.singer_label = ""; tip.singer_err = 0; tip.singer_genres = ()

            if want_p and not tip.patter_confirmed:
                if rules.get('balance') and tip.singer_err > 0:
                    p_target = max(1, min(4, 5 - tip.singer_err))
                else:
                    p_target = curve_target
                    if rules.get('first_tip_soft')  and tip.number == 1: p_target = min(p_target, 3)
                    if rules.get('last_tip_strong') and tip.number == n: p_target = min(p_target, 2)
                cands = self._scorer.candidates(
                    p_target, self._location_id,
                    want_pattern=True, want_singing=False,
                    exclude_ids=used_ids, days_fallback=days_fb,
                    genre_filter=gf)
                cands = self._apply_match_boost(cands, tip, rules)
                if cands:
                    best = cands[0]
                    tip.patter_id = best.song_id; tip.patter_title = best.title
                    tip.patter_label = best.label; tip.patter_err = best.err
                    used_ids.add(best.song_id)
                else:
                    tip.patter_id = None; tip.patter_title = ""
                    tip.patter_label = ""; tip.patter_err = 0

    @staticmethod
    def _apply_match_boost(cands: list, tip: TipSlot, rules: dict) -> list:
        """Multipliziert den Score von Pattern-Kandidaten, die zum Singing passen.

        Genre-Match:  Schnittmenge Pattern-Genres ∩ Singing-Genres nicht leer → ×Faktor
        Label-Match:  Pattern-Label == Singing-Label (beide nicht leer)        → ×Faktor
        Addiert sich multiplikativ, kein Ausschluss, nur Bevorzugung.
        """
        genre_active  = rules.get('same_genre_tip')
        label_active  = rules.get('same_label_tip')
        if not (genre_active or label_active):
            return cands   # Regelwerk inaktiv — nichts tun

        genre_factor  = rules.get('same_genre_factor', 3)
        label_factor  = rules.get('same_label_factor', 3)
        singer_genres = frozenset(tip.singer_genres)
        singer_code   = _label_code(tip.singer_label)  # Kürzel z.B. "AR", "SIR"

        scored = []
        for c in cands:
            boost = 1.0
            if genre_active and singer_genres and frozenset(c.genres) & singer_genres:
                boost *= genre_factor
            if label_active and singer_code and _label_code(c.label) == singer_code:
                boost *= label_factor
            scored.append((c.score * boost, c))

        scored.sort(key=lambda x: -x[0])
        return [c for _, c in scored]

    def _refresh_views(self):
        self._canvas.set_plan(self._tips, self._pauses, self._block_starts)
        self._table.rebuild(self._tips, self._pauses, self._block_starts)
        if self._selected_tip:
            self._canvas.select_tip(self._selected_tip)
            self._table.select_tip(self._selected_tip)

    def _update_duration_label(self):
        total = len(self._tips) * self._tip_min
        total += sum(p.duration_min for p in self._pauses)
        h, m  = divmod(total, 60)
        self._lbl_duration.setText(_t("ep_total", h=h, m=f"{m:02d}"))

    # ── Interaktion ────────────────────────────────────────────────────────────

    def _on_tip_selected(self, number: int):
        self._selected_tip = number
        self._table.select_tip(number)

    def _on_target_changed(self, tip_num: int, new_err: int):
        self._overrides[tip_num] = new_err
        for tip in self._tips:
            if tip.number == tip_num:
                tip.target_err       = new_err
                tip.patter_confirmed = False
                tip.singer_confirmed = False
                break
        self._rebuild_suggestions()
        self._refresh_views()

    def _on_pause_moved(self, old_after: int, new_after: int):
        for pause in self._pauses:
            if pause.after_tip == old_after:
                pause.after_tip = new_after
                break
        self._rebuild_plan()

    def _on_pause_deleted(self, after_tip: int):
        self._pauses = [p for p in self._pauses if p.after_tip != after_tip]
        self._rebuild_plan()

    def _on_table_selection(self):
        rows = self._table.selectedItems()
        if not rows:
            return
        item = self._table.item(self._table.currentRow(), 1)
        if item:
            num = item.data(Qt.UserRole)
            if isinstance(num, int) and num > 0 and num != self._selected_tip:
                self._selected_tip = num
                self._canvas.select_tip(num)

    def _open_candidate_dialog(self, tip_num: int, slot_type: str):
        tip = next((t for t in self._tips if t.number == tip_num), None)
        if tip is None:
            return

        days_fb  = self._days_fallback()
        n        = len(self._tips)
        rules    = self._rules

        if slot_type == 'pattern':
            current_id = tip.patter_id
            # Alle bestätigten Songs anderer Tipps sperren
            exclude = (
                {t.patter_id for t in self._tips
                 if t.patter_confirmed and t.patter_id and t.number != tip_num}
                | {t.singer_id for t in self._tips
                   if t.singer_confirmed and t.singer_id}
            )
            # Ziel-ERR: Balance gegenüber vorhandenem Singing, sonst Kurve
            if rules.get('balance') and tip.singer_err > 0:
                target = max(1, min(4, 5 - tip.singer_err))
            else:
                target = tip.target_err
                if rules.get('first_tip_soft') and tip.number == 1:
                    target = min(target, 3)
                if rules.get('last_tip_strong') and tip.number == n:
                    target = min(target, 2)
            cands = self._scorer.candidates(
                target, self._location_id,
                want_pattern=True, want_singing=False,
                exclude_ids=exclude, days_fallback=days_fb,
                limit=None, genre_filter=self._active_genre_filter() or None)

        else:  # singing
            current_id = tip.singer_id
            exclude = (
                {t.singer_id for t in self._tips
                 if t.singer_confirmed and t.singer_id and t.number != tip_num}
                | {t.patter_id for t in self._tips
                   if t.patter_confirmed and t.patter_id}
            )
            target = tip.target_err
            if rules.get('first_tip_soft') and tip.number == 1:
                target = min(target, 3)
            if rules.get('last_tip_strong') and tip.number == n:
                target = min(target, 2)
            cands = self._scorer.candidates(
                target, self._location_id,
                want_pattern=False, want_singing=True,
                exclude_ids=exclude, days_fallback=days_fb,
                limit=None, genre_filter=self._active_genre_filter() or None)

        dlg = CandidateDialog(
            tip_num, slot_type, cands, current_id,
            rules=self._rules,
            singer_genres=tip.singer_genres,
            singer_label=tip.singer_label,
            parent=self,
        )
        if not dlg.exec():
            return
        chosen = dlg.get_selected()
        if not chosen:
            return

        if slot_type == 'pattern':
            tip.patter_id        = chosen.song_id
            tip.patter_title     = chosen.title
            tip.patter_label     = chosen.label
            tip.patter_err       = chosen.err
            tip.patter_confirmed = True
        else:
            tip.singer_id        = chosen.song_id
            tip.singer_title     = chosen.title
            tip.singer_label     = chosen.label
            tip.singer_err       = chosen.err
            tip.singer_confirmed = True

        self._rebuild_suggestions()
        self._refresh_views()

    def _tb_value(self, song_id) -> float:
        """Session-stabiler Zufalls-Tiebreaker je Song (BL-113-Muster).
        Liefert 0, wenn Shuffle aus ist → Sortierung bleibt deterministisch."""
        if song_id not in self._sort_random:
            self._sort_random[song_id] = random.random()
        return self._sort_random[song_id] if self._shuffle_tb else 0.0

    def _on_shuffle_toggled(self, checked: bool):
        self._shuffle_tb = bool(checked)
        if self._settings is not None:
            self._settings.setValue(
                "sort/random_tiebreaker", self._shuffle_tb)
        self._rebuild_suggestions()
        self._refresh_views()

    def _show_rules(self):
        dlg = PlannerRulesDialog(self._rules, parent=self)
        if dlg.exec():
            self._rules = dlg.get_rules()
            self._rebuild_suggestions()
            self._refresh_views()

    def _add_pause(self):
        dlg = PauseDialog(len(self._tips), parent=self)
        if dlg.exec():
            after, dur = dlg.get_values()
            self._pauses = [p for p in self._pauses if p.after_tip != after]
            self._pauses.append(PauseBlock(after_tip=after, duration_min=dur))
            self._rebuild_plan()

    def _reset_curve(self):
        """Setzt alle manuellen ERR-Korrekturen zurück."""
        self._overrides.clear()
        for tip in self._tips:
            tip.patter_confirmed = False
            tip.singer_confirmed = False
        self._rebuild_plan()

    def _fill_all(self):
        for tip in self._tips:
            tip.patter_confirmed = bool(tip.patter_id)
            tip.singer_confirmed = bool(tip.singer_id)
        self._refresh_views()

    def _clear_all(self):
        for tip in self._tips:
            tip.patter_id    = tip.singer_id    = None
            tip.patter_title = tip.singer_title = ""
            tip.patter_label = tip.singer_label = ""
            tip.patter_err   = tip.singer_err   = 0
            tip.patter_confirmed = tip.singer_confirmed = False
        self._overrides.clear()
        self._rebuild_plan()

    # ── Genre-Filter ───────────────────────────────────────────────────────────

    def _active_genre_filter(self) -> frozenset:
        """Gibt den aktiven Genre-Filter zurück.

        Leer (frozenset()) wenn der Toggle deaktiviert ist oder keine Genres gewählt wurden.
        """
        if self._chk_genre_active.isChecked() and self._genre_filter:
            return self._genre_filter
        return frozenset()

    def _on_genre_toggle(self, checked: bool):
        """Schaltet den Genre-Filter an/aus ohne den Dialog zu öffnen."""
        self._rebuild_suggestions()
        self._refresh_views()

    def _update_genre_btn(self):
        """Aktualisiert den Genre-Button-Text anhand der gespeicherten Genres."""
        if not self._genre_filter:
            self._btn_genre.setText(_t("ep_btn_genre_none"))
        else:
            names = sorted(self._genre_filter)
            label = ", ".join(names[:2])
            if len(names) > 2:
                label += f" +{len(names) - 2}"
            self._btn_genre.setText(label)

    def _open_genre_dialog(self):
        """Öffnet den Genre-Filter-Dialog."""
        if not self._genres_available:
            try:
                self._genres_available = self._db.get_genres()
            except Exception:
                self._genres_available = []

        dlg = GenreFilterDialog(
            self._genres_available, self._genre_filter, parent=self)
        if dlg.exec():
            self._genre_filter = dlg.get_selected()
            # Genres gewählt → Toggle automatisch aktivieren
            if self._genre_filter:
                self._chk_genre_active.setChecked(True)
            self._update_genre_btn()
            self._rebuild_suggestions()
            self._refresh_views()

    # ── Export ─────────────────────────────────────────────────────────────────

    def _ask_export_mode(self, confirmed: int, unconfirmed: int) -> str | None:
        """Fragt den Nutzer, ob alle oder nur bestätigte Songs übertragen werden sollen.
        Gibt 'all', 'confirmed' oder None (Abbrechen) zurück.
        Wenn confirmed == 0, wird nur 'Alle / Abbrechen' angeboten."""
        msg = QMessageBox(self)
        msg.setWindowTitle(_t("ep_export_title"))
        if confirmed == 0:
            msg.setText(_t("ep_export_none_confirmed_ask").format(n=unconfirmed))
            btn_all    = msg.addButton(_t("ep_export_btn_all"),
                                       QMessageBox.ButtonRole.AcceptRole)
            msg.addButton(_t("ep_export_btn_cancel"),
                          QMessageBox.ButtonRole.RejectRole)
            msg.exec()
            return "all" if msg.clickedButton() is btn_all else None
        else:
            msg.setText(_t("ep_export_partial_ask").format(
                confirmed=confirmed, unconfirmed=unconfirmed))
            btn_all  = msg.addButton(_t("ep_export_btn_all"),
                                     QMessageBox.ButtonRole.AcceptRole)
            btn_conf = msg.addButton(_t("ep_export_btn_confirmed_only"),
                                     QMessageBox.ButtonRole.AcceptRole)
            msg.addButton(_t("ep_export_btn_cancel"),
                          QMessageBox.ButtonRole.RejectRole)
            msg.exec()
            clicked = msg.clickedButton()
            if clicked is btn_all:
                return "all"
            elif clicked is btn_conf:
                return "confirmed"
            return None

    def _transfer_to_playlist(self):
        """Button 'Übernehmen zur Playliste': Songs in Tip-Reihenfolge
        (je Tip: erst Patter, dann Singing) an die Playlist übergeben.
        Enthält nicht bestätigte Songs → Sicherheitsabfrage.
        Jeder Eintrag ist ein Tupel (song_id, mode) mit mode='P'/'S', damit Songs
        mit beiden Tags (P+S) den Typ ihrer Slot-Rolle behalten."""
        confirmed_ids: list[tuple[int, str]] = []
        all_ids:       list[tuple[int, str]] = []
        for tip in self._tips:
            if tip.patter_id:
                all_ids.append((tip.patter_id, "P"))
                if tip.patter_confirmed:
                    confirmed_ids.append((tip.patter_id, "P"))
            if tip.singer_id:
                all_ids.append((tip.singer_id, "S"))
                if tip.singer_confirmed:
                    confirmed_ids.append((tip.singer_id, "S"))

        unconfirmed = len(all_ids) - len(confirmed_ids)
        if unconfirmed > 0:
            mode = self._ask_export_mode(len(confirmed_ids), unconfirmed)
            if mode is None:
                return
            song_ids = all_ids if mode == "all" else confirmed_ids
        else:
            song_ids = confirmed_ids

        self.sig_export_to_playlist.emit(song_ids)

    def _transfer_to_notes(self):
        """Button 'Übernehmen zu Notizen': Song-Titel in Tip-Reihenfolge emittieren.
        Enthält nicht bestätigte Songs → Sicherheitsabfrage.
        Reihenfolge wird UNVERAENDERT (Tip 1 zuerst) emittiert — main.py baut die
        Shortcode-Texte in genau dieser Reihenfolge und uebergibt sie an
        notes_widget.add_notes(), das die End-Reihenfolge samt Toggle-Position
        (Oben/Unten) garantiert. Ein zusaetzliches reversed() hier wuerde das
        wieder umdrehen (war ein Ueberbleibsel aus der Zeit vor Issue #93).
        Jeder Eintrag ist ein Tupel (title, mode) mit mode='P' oder 'S',
        damit der Shortcode die Rolle des Songs dokumentiert."""
        # Tupel (title, mode_char) — 'P' fuer Patter, 'S' fuer Singing
        confirmed_entries: list[tuple[str, str]] = []
        all_entries:       list[tuple[str, str]] = []
        for tip in self._tips:
            if tip.patter_title:
                all_entries.append((tip.patter_title, "P"))
                if tip.patter_confirmed:
                    confirmed_entries.append((tip.patter_title, "P"))
            if tip.singer_title:
                all_entries.append((tip.singer_title, "S"))
                if tip.singer_confirmed:
                    confirmed_entries.append((tip.singer_title, "S"))

        unconfirmed = len(all_entries) - len(confirmed_entries)
        if unconfirmed > 0:
            mode = self._ask_export_mode(len(confirmed_entries), unconfirmed)
            if mode is None:
                return
            entries = all_entries if mode == "all" else confirmed_entries
        else:
            entries = confirmed_entries

        self.sig_export_to_notes.emit(entries)

    # ── Zoom ───────────────────────────────────────────────────────────────────

    def _zoom(self, delta: float):
        self._canvas.set_scale(self._canvas._scale + delta)

    def _zoom_fit(self):
        available = self._scroll.viewport().width() - _PAD_L - 20
        total_min = sum(
            (self._tip_min if isinstance(item, TipSlot) else item.duration_min)
            for item in self._canvas._timeline
        )
        if total_min > 0 and available > 0:
            self._canvas.set_scale(available / (total_min * _BASE_PX_MIN))


# ─── Dialoge ──────────────────────────────────────────────────────────────────

class CandidateDialog(QDialog):
    """Zeigt alle Kandidaten für einen Tipp-Slot; Doppelklick oder OK übernimmt.

    Beim Pattern-Slot werden aktive Genre/Label-Regeln als eigene Bonus-Spalten
    aufgeführt und die Liste nach dem Gesamt-Score sortiert.
    """

    def __init__(self, tip_number: int, slot_type: str,
                 candidates: list, current_id: Optional[int],
                 rules: Optional[dict] = None,
                 singer_genres: tuple = (),
                 singer_label: str = "",
                 parent=None):
        super().__init__(parent)
        slot_lbl = _t("ep_cand_singing") if slot_type == "singing" else _t("ep_cand_pattern")
        self.setWindowTitle(_t("ep_cand_dialog_title", num=tip_number, slot=slot_lbl))
        self.setMinimumSize(620, 440)

        rules = rules or {}
        is_pattern = (slot_type == "pattern")

        # Bestimme welche Bonus-Spalten gezeigt werden
        show_genre = is_pattern and rules.get("same_genre_tip", False)
        show_label = is_pattern and rules.get("same_label_tip", False)
        genre_factor = int(rules.get("same_genre_factor", 3))
        label_factor = int(rules.get("same_label_factor", 3))
        singer_genres_set = frozenset(singer_genres)
        singer_code = _label_code(singer_label)  # Kürzel z.B. "AR", "SIR"

        # Berechne Gesamt-Score je Kandidat und sortiere danach
        def _total(c: _Candidate):
            boost = 1
            if show_genre and singer_genres_set & frozenset(c.genres):
                boost *= genre_factor
            if show_label and singer_code and _label_code(c.label) == singer_code:
                boost *= label_factor
            return c.score * boost

        sorted_cands = sorted(candidates, key=lambda c: -_total(c))
        self._candidates = sorted_cands
        self._selected: Optional[_Candidate] = None

        layout = QVBoxLayout(self)
        info = QLabel(_t("ep_cand_info", slot=slot_lbl))
        info.setWordWrap(True)
        layout.addWidget(info)

        # Spalten dynamisch aufbauen
        headers = [
            _t("ep_cand_col_title"),
            _t("ep_cand_col_label"),
            _t("ep_cand_col_err"),
            _t("ep_cand_col_score"),
        ]
        if show_genre:
            headers.append(f"Genre ×{genre_factor}")
        if show_label:
            headers.append(f"Label ×{label_factor}")
        headers += [_t("ep_cand_col_total"), _t("ep_cand_col_days")]

        # Spaltenindizes merken
        col_title  = 0
        col_label  = 1
        col_err    = 2
        col_score  = 3
        col_genre  = 4 if show_genre else None
        col_lbl_b  = (5 if show_genre else 4) if show_label else None
        col_total  = len(headers) - 2
        col_days   = len(headers) - 1

        self._tbl = QTableWidget(0, len(headers))
        self._tbl.setHorizontalHeaderLabels(headers)
        self._tbl.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._tbl.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._tbl.setSelectionMode(QAbstractItemView.SingleSelection)
        self._tbl.setAlternatingRowColors(True)
        self._tbl.verticalHeader().setVisible(False)
        hdr = self._tbl.horizontalHeader()
        hdr.setSectionResizeMode(col_title, QHeaderView.Stretch)
        for c in range(1, len(headers)):
            hdr.setSectionResizeMode(c, QHeaderView.ResizeToContents)

        self._tbl.setUpdatesEnabled(False)
        self._tbl.setRowCount(len(sorted_cands))
        preselect_row = 0

        for row, cand in enumerate(sorted_cands):
            is_current = (cand.song_id == current_id)
            if is_current:
                preselect_row = row

            total = _total(cand)
            genre_match = show_genre and bool(singer_genres_set & frozenset(cand.genres))
            label_match = show_label and bool(singer_code and _label_code(cand.label) == singer_code)

            cells: dict[int, str] = {
                col_title: cand.title,
                col_label: cand.label or "",
                col_err:   str(cand.err) if cand.err else "—",
                col_score: f"{cand.score:.0f}",
                col_total: f"{total:.0f}",
                col_days:  str(cand.days) if cand.days else "—",
            }
            if col_genre is not None:
                cells[col_genre] = f"×{genre_factor}" if genre_match else "—"
            if col_lbl_b is not None:
                cells[col_lbl_b] = f"×{label_factor}" if label_match else "—"

            for col, val in cells.items():
                it = QTableWidgetItem(val)
                it.setTextAlignment(Qt.AlignVCenter | Qt.AlignLeft)
                # ERR als satter Badge (wie im Evening Planner): weiße fette
                # Zahl auf voller ERR-Farbe; leerer Wert dezent zentriert.
                if col == col_err:
                    it.setTextAlignment(Qt.AlignCenter)
                    if cand.err > 0:
                        it.setBackground(_ERR_COL.get(cand.err, QColor("#808080")))
                        it.setForeground(QColor("#ffffff"))
                        f = it.font()
                        f.setBold(True)
                        it.setFont(f)
                # Bonus-Spalten: Match grün, kein Match gedimmt
                if col == col_genre:
                    it.setForeground(QColor("#2e8b3e") if genre_match else QColor("#666666"))
                if col == col_lbl_b:
                    it.setForeground(QColor("#2e8b3e") if label_match else QColor("#666666"))
                if is_current:
                    font = it.font()
                    font.setBold(True)
                    it.setFont(font)
                self._tbl.setItem(row, col, it)

        self._tbl.setUpdatesEnabled(True)
        self._tbl.selectRow(preselect_row)
        self._tbl.itemDoubleClicked.connect(lambda _: self._accept_selection())
        layout.addWidget(self._tbl)

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self._accept_selection)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def _accept_selection(self):
        row = self._tbl.currentRow()
        if 0 <= row < len(self._candidates):
            self._selected = self._candidates[row]
            self.accept()

    def get_selected(self) -> Optional[_Candidate]:
        return self._selected


class PlannerRulesDialog(QDialog):
    # (key, label_key, factor_key_or_None)
    _RULES = [
        ('balance',         "ep_rule_balance",      None),
        ('same_genre_tip',  "ep_rule_same_genre",   'same_genre_factor'),
        ('same_label_tip',  "ep_rule_same_label",   'same_label_factor'),
        ('first_tip_soft',  "ep_rule_first_soft",   None),
        ('last_tip_strong', "ep_rule_last_strong",  None),
    ]

    def __init__(self, rules: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle(_t("ep_rules_dialog_title"))
        self.setMinimumWidth(480)
        layout = QVBoxLayout(self)
        grp    = QGroupBox(_t("ep_rules_group"))
        grp_l  = QVBoxLayout(grp)
        self._checks  = {}
        self._factors = {}

        for key, lbl_key, factor_key in self._RULES:
            row = QHBoxLayout()
            cb  = QCheckBox(_t(lbl_key))
            cb.setChecked(rules.get(key, False))
            row.addWidget(cb, 1)
            self._checks[key] = cb

            if factor_key:
                row.addWidget(QLabel(_t("ep_rule_factor")))
                spin = QSpinBox()
                spin.setRange(1, 20)
                spin.setSingleStep(1)
                spin.setValue(int(rules.get(factor_key, 3)))
                spin.setFixedWidth(56)
                spin.setEnabled(cb.isChecked())
                cb.toggled.connect(spin.setEnabled)
                row.addWidget(spin)
                self._factors[factor_key] = spin

            grp_l.addLayout(row)

        layout.addWidget(grp)
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def get_rules(self) -> dict:
        result = {key: cb.isChecked() for key, cb in self._checks.items()}
        result.update({key: spin.value() for key, spin in self._factors.items()})
        return result


class PauseDialog(QDialog):
    def __init__(self, max_tip: int, parent=None):
        super().__init__(parent)
        self.setWindowTitle(_t("ep_pause_dialog_title"))
        layout = QFormLayout(self)

        self._spin_after = QSpinBox()
        self._spin_after.setRange(1, max(1, max_tip - 1))
        self._spin_after.setValue(min(4, max_tip))
        self._spin_after.setSuffix("  (nach Tipp)")
        layout.addRow(_t("ep_pause_after"), self._spin_after)

        self._spin_dur = QSpinBox()
        self._spin_dur.setRange(5, 60)
        self._spin_dur.setValue(20)
        self._spin_dur.setSingleStep(5)
        self._spin_dur.setSuffix(" min")
        layout.addRow(_t("ep_pause_duration"), self._spin_dur)

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addRow(btns)

    def get_values(self) -> tuple:
        return self._spin_after.value(), self._spin_dur.value()


# ─── Genre-Filter-Dialog ──────────────────────────────────────────────────────

class GenreFilterDialog(QDialog):
    """Multi-Select-Dialog für den Genre-Filter der Abendplanung.

    Zeigt alle vorhandenen Genres als Checkboxen. Leere Auswahl = kein Filter (alle Genres).
    """

    def __init__(self, genres: list, active: frozenset, parent=None):
        super().__init__(parent)
        self.setWindowTitle(_t("ep_genre_dialog_title"))
        self.setMinimumWidth(300)

        layout = QVBoxLayout(self)

        info = QLabel(_t("ep_genre_dialog_info"))
        info.setWordWrap(True)
        layout.addWidget(info)

        self._checks: dict[str, QCheckBox] = {}

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        inner = QWidget()
        inner_layout = QVBoxLayout(inner)
        inner_layout.setSpacing(2)

        for name in genres:
            cb = QCheckBox(name)
            cb.setChecked(name in active)
            inner_layout.addWidget(cb)
            self._checks[name] = cb

        inner_layout.addStretch()
        scroll.setWidget(inner)
        layout.addWidget(scroll, 1)

        # Alle/Keine Buttons
        btn_row = QHBoxLayout()
        btn_all  = QPushButton("Alle")
        btn_none = QPushButton("Keine")
        btn_all.clicked.connect(lambda: [cb.setChecked(True)  for cb in self._checks.values()])
        btn_none.clicked.connect(lambda: [cb.setChecked(False) for cb in self._checks.values()])
        btn_row.addWidget(btn_all)
        btn_row.addWidget(btn_none)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def get_selected(self) -> frozenset:
        """Gibt die gewählten Genre-Namen als frozenset zurück. Leer = kein Filter."""
        return frozenset(name for name, cb in self._checks.items() if cb.isChecked())


# ─── Hilfsfunktionen ──────────────────────────────────────────────────────────

def _vline() -> QFrame:
    line = QFrame()
    line.setFrameShape(QFrame.VLine)
    line.setFrameShadow(QFrame.Sunken)
    return line
