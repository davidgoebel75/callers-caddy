"""Uhr fuer Callers Caddy: aktuelle Uhrzeit gross als Digitaluhr (intern#235).

Text und Takt stehen ohne Qt in clock_format.py; das Widget liest die
Systemzeit, malt mit Theme-Farben und skaliert die Schrift mit der Dock-Groesse.
Rechtsklick: Sekunden, 12 h (AM/PM) und Datum ein-/ausschalten (in der INI
gemerkt). Zirkelfrei: keine Rueckbezuege auf main.py.
"""

from PySide6.QtWidgets import QWidget, QMenu
from PySide6.QtCore import Qt, QTimer, QTime, QDate, QLocale, QRectF
from PySide6.QtGui import QPainter, QColor, QPen, QFont, QFontMetricsF

from caddy.clock.clock_format import format_clock, ms_until_change
from caddy.settings import ini_keys
from i18n import _t, get_language

# Sprache der App -> Locale fuer Wochentag/Monatsnamen im Datum
_LOCALES = {
    "de": QLocale(QLocale.German, QLocale.Germany),
    "en": QLocale(QLocale.English, QLocale.UnitedStates),
    "ja": QLocale(QLocale.Japanese, QLocale.Japan),
}

_KEY_SECONDS = ini_keys.CLOCK_SHOW_SECONDS
_KEY_12H = ini_keys.CLOCK_TWELVE_HOUR
_KEY_DATE = ini_keys.CLOCK_SHOW_DATE


class ClockWidget(QWidget):
    """Digitaluhr im Dock. Zeichnet sich nur neu, wenn sich der Text aendert
    (zur vollen Minute bzw. Sekunde) und laeuft nur, solange sie sichtbar ist."""

    _PAD = 6            # Rand in Pixeln
    _DATE_FRAC = 0.22   # Anteil der Hoehe fuer die Datumszeile
    _SUFFIX_FRAC = 0.38  # AM/PM relativ zur Zeitschrift

    def __init__(self, skin_mgr=None, settings=None, parent=None):
        super().__init__(parent)
        self._skin_mgr = skin_mgr
        self._settings = settings
        self._load_options()
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setTimerType(Qt.PreciseTimer)
        self._timer.timeout.connect(self._tick)
        self.setMinimumSize(80, 40)
        self.setContextMenuPolicy(Qt.DefaultContextMenu)

    # --- Einstellungen ---------------------------------------------------

    def _load_options(self):
        self._show_seconds = self._read_bool(_KEY_SECONDS)
        self._twelve_hour = self._read_bool(_KEY_12H)
        self._show_date = self._read_bool(_KEY_DATE)

    def reload_settings(self):
        """Nach Aenderung im Einstellungsdialog: Optionen neu lesen."""
        self._load_options()
        if self.isVisible():
            self._tick()  # Takt haengt an den Sekunden

    def _read_bool(self, key):
        if self._settings is None:
            return bool(ini_keys.default(key))
        return bool(ini_keys.get(self._settings, key, type=bool))

    def _write_bool(self, key, value):
        if self._settings is not None:
            self._settings.setValue(key, value)

    def set_skin(self, skin_mgr):
        self._skin_mgr = skin_mgr
        self.update()

    def _color(self, key, fallback):
        return QColor(self._skin_mgr.color(key, fallback) if self._skin_mgr else fallback)

    # --- Takt ------------------------------------------------------------

    def showEvent(self, event):
        super().showEvent(event)
        self._tick()

    def hideEvent(self, event):
        super().hideEvent(event)
        self._timer.stop()

    def _tick(self):
        now = QTime.currentTime()
        self.update()
        self._timer.start(ms_until_change(
            now.second(), now.msec(), seconds=self._show_seconds))

    # --- Kontextmenue ----------------------------------------------------

    def contextMenuEvent(self, event):
        menu = QMenu(self)
        for label, attr, key in (
            (_t("clock_menu_seconds"), "_show_seconds", _KEY_SECONDS),
            (_t("clock_menu_12h"), "_twelve_hour", _KEY_12H),
            (_t("clock_menu_date"), "_show_date", _KEY_DATE),
        ):
            act = menu.addAction(label)
            act.setCheckable(True)
            act.setChecked(getattr(self, attr))
            act.toggled.connect(
                lambda on, a=attr, k=key: self._set_option(a, k, on))
        menu.exec(event.globalPos())
        menu.deleteLater()
        event.accept()

    def _set_option(self, attr, key, on):
        setattr(self, attr, on)
        self._write_bool(key, on)
        if self.isVisible():
            self._tick()  # Takt haengt an den Sekunden

    # --- Zeichnen --------------------------------------------------------

    @staticmethod
    def _fit_font(base, text, width, height):
        """Schrift, mit der `text` in width x height passt (Pixelgroesse >= 6)."""
        f = QFont(base)
        f.setBold(True)
        f.setPixelSize(max(6, int(height)))
        fm = QFontMetricsF(f)
        w = fm.horizontalAdvance(text)
        if w > width > 0:
            f.setPixelSize(max(6, int(f.pixelSize() * width / w)))
        return f

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.TextAntialiasing)
        pad = self._PAD
        w = self.width() - 2 * pad
        h = self.height() - 2 * pad
        if w <= 0 or h <= 0:
            p.end()
            return

        now = QTime.currentTime()
        text, suffix = format_clock(
            now.hour(), now.minute(), now.second(),
            seconds=self._show_seconds, twelve_hour=self._twelve_hour)

        date_h = h * self._DATE_FRAC if self._show_date else 0.0
        time_h = h - date_h

        # Ziffernhoehe ~0.72 der Pixelgroesse -> Faktor 1.3 nutzt die Hoehe
        # besser aus, die Breitenbegrenzung faengt es wieder ein.
        f_time = self._fit_font(p.font(), text, w, time_h * 1.3)
        fm = QFontMetricsF(f_time)
        if suffix:
            # Platz fuer AM/PM: Zusatz (_SUFFIX_FRAC) und Abstand (halbes
            # Leerzeichen) in der Groesse messen, in der sie gezeichnet werden.
            f_s = QFont(f_time)
            f_s.setPixelSize(max(6, int(f_time.pixelSize() * self._SUFFIX_FRAC)))
            need = (fm.horizontalAdvance(text) + fm.horizontalAdvance(" ") * 0.5
                    + QFontMetricsF(f_s).horizontalAdvance(suffix))
            if need > w:
                f_time.setPixelSize(max(6, int(f_time.pixelSize() * w / need)))
                fm = QFontMetricsF(f_time)
        if fm.height() > time_h * 1.25:
            f_time.setPixelSize(max(6, int(f_time.pixelSize() * time_h * 1.25 / fm.height())))
            fm = QFontMetricsF(f_time)

        f_suffix = QFont(f_time)
        f_suffix.setPixelSize(max(6, int(f_time.pixelSize() * self._SUFFIX_FRAC)))
        fm_s = QFontMetricsF(f_suffix)
        gap = fm.horizontalAdvance(" ") * 0.5 if suffix else 0.0
        tw = fm.horizontalAdvance(text)
        sw = fm_s.horizontalAdvance(suffix) if suffix else 0.0
        x0 = pad + (w - (tw + gap + sw)) / 2
        # Grundlinie so, dass die Ziffern (capHeight) vertikal mittig sitzen
        baseline = pad + (time_h + fm.capHeight()) / 2

        p.setPen(QPen(self._color("text", "#f0f0f0")))
        p.setFont(f_time)
        p.drawText(int(x0), int(baseline), text)
        if suffix:
            p.setFont(f_suffix)
            p.drawText(int(x0 + tw + gap), int(baseline), suffix)

        if self._show_date:
            loc = _LOCALES.get(get_language(), QLocale())
            date_text = loc.toString(QDate.currentDate(), QLocale.LongFormat)
            f_date = QFont(p.font())
            f_date.setBold(False)
            f_date.setPixelSize(max(6, int(date_h * 0.75)))
            fm_d = QFontMetricsF(f_date)
            dw = fm_d.horizontalAdvance(date_text)
            if dw > w:
                f_date.setPixelSize(max(6, int(f_date.pixelSize() * w / dw)))
            p.setFont(f_date)
            p.setPen(QPen(self._color("text_dim", "#999999")))
            p.drawText(QRectF(pad, pad + time_h, w, date_h),
                       Qt.AlignHCenter | Qt.AlignTop, date_text)
        p.end()
