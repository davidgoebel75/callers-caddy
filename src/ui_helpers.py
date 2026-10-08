"""UI-Helfer + reine Hilfsfunktionen fuer Callers Caddy.

Blatt-Modul (BL-201, Stufe 2): aus main.py ausgelagerte, wiederverwendbare
Helfer ohne Rueckgriff auf main — Zeitformatierung, Loop-Rechnung, der
Loop-Count-Dialog, Transport-/Icon-SVGs samt _make_icon, _make_dock und die
_PlayBarrier. Abhaengigkeiten nur auf Blatt-/Fremdmodule (perf, i18n, song_types, PySide6).
"""

import math
from datetime import date

from PySide6.QtCore import Qt, QTimer, QEvent, QSize
from PySide6.QtGui import QIcon, QColor
from PySide6.QtWidgets import (
    QDialog, QDockWidget, QDoubleSpinBox, QFormLayout,
    QHBoxLayout, QLabel, QMessageBox, QPushButton, QRadioButton, QButtonGroup,
    QVBoxLayout, QWidget, QSizePolicy,
)

from i18n import _t
from perf import perf_start, perf_split
from song_types import PlayMode


# BL-170: Ersatz-Qualitaet fuer unbewertete Songs beim gewichteten Zufall.
# quality 0 = "noch nicht bewertet" (s. song_db.py), nicht "schlecht".
_UNRATED_QUALITY = 5


# --- Reine Hilfsfunktionen + Loop-Dialog -------------------------------------

def fmt_time(s):
    return f"{int(s)//60:02d}:{int(s)%60:02d}"

def fmt_precise(s):
    m = int(s) // 60
    sec = s - m * 60
    return f"{m:02d}:{sec:05.2f}"


def parse_time_offset(text):
    """Parst 'mm:ss.cs' (optionales Vorzeichen) zu Sekunden (float, signed).

    Akzeptiert Minuten:Sekunden ('0:20', '1:05.5') und reine Sekunden
    ('20', '20.5'). Dezimaltrenner Punkt ODER Komma. Gibt None zurueck bei
    ungueltiger Eingabe.
    Beispiele: '-0:20' -> -20.0, '1:05.5' -> 65.5, '-12,3' -> -12.3
    """
    if text is None:
        return None
    s = str(text).strip().replace(",", ".")
    if not s:
        return None
    sign = 1.0
    if s[0] in "+-":
        if s[0] == "-":
            sign = -1.0
        s = s[1:].strip()
    if not s:
        return None
    try:
        if ":" in s:
            mm, ss = s.split(":", 1)
            minutes = int(mm) if mm.strip() else 0
            seconds = float(ss) if ss.strip() else 0.0
            if seconds < 0 or seconds >= 60:
                return None
            total = minutes * 60 + seconds
        else:
            total = float(s)
    except (ValueError, TypeError):
        return None
    return sign * total


def _clear_layout(layout):
    """Alle Widgets aus einem QLayout entfernen und loeschen."""
    while layout.count():
        item = layout.takeAt(0)
        w = item.widget()
        if w:
            w.deleteLater()


def calc_loop_count(desired_seconds, loop_in, loop_out, song_duration):
    """Berechnet die Loop-Anzahl fuer eine gewuenschte Gesamtdauer.

    Returns:
        list of (n, total_seconds) Tupel — aufsteigend sortiert.
        Normalerweise 2 Optionen (abrunden/aufrunden), bei exaktem Treffer nur 1.
        Leere Liste wenn Loop ungueltig oder gewuenschte Zeit nicht erreichbar.
    """
    pre_loop = loop_in
    loop_dur = loop_out - loop_in
    post_loop = song_duration - loop_out
    if loop_dur <= 0:
        return []
    n_exact = (desired_seconds - pre_loop - post_loop) / loop_dur
    if n_exact < 0:
        return [(1, pre_loop + loop_dur + post_loop)]
    n_low = max(1, int(n_exact))
    n_high = n_low + 1
    total_low = pre_loop + n_low * loop_dur + post_loop
    total_high = pre_loop + n_high * loop_dur + post_loop
    # Exakter Treffer?
    if abs(n_exact - n_low) < 0.001:
        return [(n_low, total_low)]
    return [(n_low, total_low), (n_high, total_high)]


# BL-164: Toleranz fuer die Patter-Ziellaenge. Liegt eine ganzzahlige
# Loop-Variante bereits innerhalb dieses Fensters, wird KEIN Cut angeboten —
# ganze Loops sind immer die musikalisch sauberste Wahl (kein Extra-Sprung).
LOOP_CUT_TOLERANCE_S = 20.0


def calc_loop_cut(desired_seconds, loop_in, loop_out, song_duration, bpm,
                  cut_beats=64):
    """Feinjustierte Loop-Variante (BL-164): aufgerundete Loop-Zahl minus k*cut_beats.

    Kernidee: Man startet bei der aufgerundeten ganzzahligen Loop-Zahl (die knapp
    UEBER der Wunschzeit liegt) und kuerzt EINEN Durchlauf um k*cut_beats Beats
    (ganze Phrasen), bis die Gesamtdauer moeglichst nah an die Wunschzeit kommt.
    Der Ausstieg (loop_out -> Tail) bleibt unangetastet; nur ein Ruecksprung
    erfolgt frueher (bei loop_out - k*cut_beats zurueck zu loop_in).

    Weil der Ueberschuss der aufgerundeten Variante per Definition < einer
    Loop-Laenge ist, ist der noetige Cut IMMER < loop_dur → genau ein
    verkuerzter Durchlauf, nie mehr.

    Args:
        cut_beats: Rasterweite in Beats (Default 64 = ganze Phrasen; 32 als
                   feinerer Fallback fuer die letzten Prozent).

    Returns:
        (n, k, total_seconds) — n = ganze Loop-Durchlaeufe, k = abgeschnittene
        cut_beats-Bloecke bei einem Durchlauf, total = resultierende Gesamtdauer.
        None, wenn nicht anwendbar (kein BPM, Cut-Schritt >= Loop-Laenge).
    """
    loop_dur = loop_out - loop_in
    pre = loop_in
    post = song_duration - loop_out
    if loop_dur <= 0 or not bpm or bpm <= 0:
        return None

    beat = 60.0 / bpm
    cut_step = cut_beats * beat
    if cut_step <= 0 or cut_step >= loop_dur:
        return None  # Cut-Schritt groesser als der Loop selbst → sinnlos

    n_exact = (desired_seconds - pre - post) / loop_dur
    n_high = max(1, math.ceil(n_exact))
    if n_high < 2:
        return None  # Cut braucht einen INNEREN Durchlauf; sonst wuerde der
                     # Ausstieg (loop_out -> Tail) vorgezogen. Bei n=1 kein Cut.
    total_high = pre + n_high * loop_dur + post

    overshoot = total_high - desired_seconds
    if overshoot <= 0:
        return (n_high, 0, total_high)  # schon exakt/darunter, kein Cut noetig

    # Anzahl 64er-Bloecke, die den Ueberschuss am besten wegschneiden
    k = round(overshoot / cut_step)
    max_k = int((loop_dur - 1e-6) // cut_step)  # ein Durchlauf muss > 0 bleiben
    k = max(0, min(k, max_k))
    total = total_high - k * cut_step
    return (n_high, k, total)


def calc_auto_loop(loop_in, loop_out, song_duration, bpm, desired_seconds):
    """Waehlt automatisch die beste Loop-Einstellung fuer eine Zielzeit (headless).

    Gleiche Priorisierung wie die Default-Auswahl im manuellen Loop-Dialog
    (show_loop_count_dialog / BL-164):
      1. Liegt eine ganzzahlige Loop-Variante innerhalb LOOP_CUT_TOLERANCE_S an
         der Zielzeit, wird die naehere ganze Variante genommen (kein Cut —
         ganze Loops sind musikalisch am saubersten).
      2. Sonst die praezise Cut-Variante (64er-, ersatzweise 32er-Raster),
         sofern BPM bekannt und anwendbar.
      3. Fallback: die naeheste ganze Variante. Ist gar keine berechenbar
         (ungueltiger Loop), (0, 0) = endlos.

    Returns (loop_count, cut_beats). loop_count=0 heisst endlos.
    """
    options = calc_loop_count(desired_seconds, loop_in, loop_out, song_duration)
    if not options:
        return (0, 0)
    best_whole = min(options, key=lambda o: abs(o[1] - desired_seconds))
    # 1. Ganze Variante nah genug → kein Cut
    if abs(best_whole[1] - desired_seconds) <= LOOP_CUT_TOLERANCE_S:
        return (best_whole[0], 0)
    # 2. Cut-Variante versuchen (identisch zur _best_cut-Logik des Dialogs)
    if bpm and bpm > 0:
        best_cut = None
        for raster in (64, 32):
            r = calc_loop_cut(desired_seconds, loop_in, loop_out,
                              song_duration, bpm, raster)
            if r is None:
                continue
            n, k, total = r
            if k <= 0:
                continue  # ganze Variante schon exakt → kein Cut noetig
            if best_cut is None or abs(total - desired_seconds) < abs(best_cut[2] - desired_seconds):
                best_cut = (n, k * raster, total)
        if best_cut is not None:
            return (best_cut[0], best_cut[1])
    # 3. Fallback: naeheste ganze Variante
    return (best_whole[0], 0)


def show_loop_count_dialog(parent, song, paths, default_minutes=7.0,
                           current_count=None, current_cut=0,
                           current_target_min=0.0, current_play_mode=PlayMode.LOOP):
    """Zeigt den Loop-Count-Berechnungsdialog.

    Args:
        current_count/current_cut/current_target_min: bisherige Wahl des
            Playlist-Eintrags. Wenn current_target_min>0, startet der Dialog mit
            dieser Wunschzeit und stellt die zuletzt gewaehlte Option wieder her
            (BL-164 — sonst saehe man beim Wiederoeffnen nur die Default-Werte).
        current_play_mode: Abspielart des Eintrags; ONCE waehlt "Einmal durchspielen" vor.

    Returns: (loop_count, loop_cut_beats, target_min, play_mode)-Tupel, oder None bei
      Abbruch. loop_count=0 → Endlos; loop_cut_beats>0 nur bei der
      BL-164-Cut-Variante. play_mode ist ONCE nur bei "Einmal durchspielen" (intern#179).
    """
    import soundfile as sf

    if song.loop_in <= 0 and song.loop_out <= 0:
        QMessageBox.information(parent, _t("dock_playlist"), _t("loop_count_no_loop"))
        return None

    filepath = paths.find_song_file(song.filename)
    if not filepath:
        QMessageBox.warning(parent, _t("error"), _t("file_not_found"))
        return None
    try:
        info = sf.info(filepath)
        song_duration = info.duration
    except Exception:
        return None

    loop_in = song.loop_in
    loop_out = song.loop_out if song.loop_out > 0 else song_duration
    loop_dur = loop_out - loop_in
    pre_loop = loop_in
    post_loop = song_duration - loop_out

    dlg = QDialog(parent)
    dlg.setWindowTitle(_t("loop_count_title"))
    dlg.setMinimumWidth(350)
    dlg_layout = QVBoxLayout(dlg)

    info_label = QLabel(f"<b>{song.title or song.filename}</b>")
    dlg_layout.addWidget(info_label)
    details = QLabel(
        f"Loop: {fmt_time(loop_in)} – {fmt_time(loop_out)} "
        f"({fmt_time(loop_dur)} {_t('loop_count_per_loop')})\n"
        f"{_t('loop_count_before')}: {fmt_time(pre_loop)}, "
        f"{_t('loop_count_after')}: {fmt_time(post_loop)}"
    )
    details.setStyleSheet("color: gray;")
    dlg_layout.addWidget(details)

    form = QFormLayout()
    spin_minutes = QDoubleSpinBox()
    spin_minutes.setRange(0.5, 30.0)
    spin_minutes.setSingleStep(0.5)
    spin_minutes.setDecimals(1)
    spin_minutes.setSuffix(" min")
    # BL-164: gespeicherte Wunschzeit bevorzugen, sonst Programm-Default
    spin_minutes.setValue(
        current_target_min if current_target_min and current_target_min > 0
        else default_minutes)
    form.addRow(_t("loop_count_desired_time"), spin_minutes)
    dlg_layout.addLayout(form)

    result_label = QLabel("")
    result_label.setStyleSheet("font-family: monospace; margin: 8px 0;")
    dlg_layout.addWidget(result_label)

    bpm = float(getattr(song, 'base_bpm', 0) or 0)

    radio_group = QButtonGroup(dlg)
    radio_low = QRadioButton()
    radio_high = QRadioButton()
    radio_cut = QRadioButton()   # BL-164: feinjustierte Variante (64-Beat-Cut)
    radio_infinite = QRadioButton(_t("loop_count_infinite"))
    radio_once = QRadioButton(_t("loop_count_once"))   # intern#179: Abspielart ONCE
    radio_group.addButton(radio_low, 0)
    radio_group.addButton(radio_high, 1)
    radio_group.addButton(radio_cut, 3)
    radio_group.addButton(radio_infinite, 2)
    radio_group.addButton(radio_once, 4)
    dlg_layout.addWidget(radio_low)
    dlg_layout.addWidget(radio_high)
    dlg_layout.addWidget(radio_cut)      # unter den ganzzahligen Optionen
    dlg_layout.addWidget(radio_infinite)
    dlg_layout.addWidget(radio_once)

    def _best_cut(desired, options):
        """BL-164: beste Cut-Variante, naeher von 64/32-Beat-Raster.

        Liegt bereits eine ganzzahlige Variante innerhalb der Toleranz,
        wird KEIN Cut angeboten (ganze Loops = kein Extra-Sprung = sauberer).
        Returns (n, cut_abs_beats, total_seconds) oder None wenn kein Cut sinnvoll."""
        for _n, _sec in options:
            if abs(_sec - desired) <= LOOP_CUT_TOLERANCE_S:
                return None
        if bpm <= 0:
            return None
        best = None
        for raster in (64, 32):
            r = calc_loop_cut(desired, loop_in, loop_out, song_duration, bpm, raster)
            if r is None:
                continue
            n, k, total = r
            if k <= 0:
                continue  # kein Cut noetig (ganzzahlige Variante schon exakt)
            if best is None or abs(total - desired) < abs(best[2] - desired):
                best = (n, k * raster, total)
        return best

    def _update_options():
        keep_once = radio_once.isChecked()   # Wahl "Einmal" ueberlebt Minuten-Aenderung
        desired = spin_minutes.value() * 60.0
        options = calc_loop_count(desired, loop_in, loop_out, song_duration)
        cut = _best_cut(desired, options)
        if cut is not None:
            n_c, cut_beats, t_c = cut
            radio_cut.setText(
                f"{n_c} Loops − {cut_beats} Beats → {fmt_time(t_c)} ({t_c/60:.1f} min)")
            radio_cut.setVisible(True)
        else:
            radio_cut.setVisible(False)
        if len(options) >= 2:
            n_lo, t_lo = options[0]
            n_hi, t_hi = options[1]
            radio_low.setText(f"{n_lo} Loops → {fmt_time(t_lo)} ({t_lo/60:.1f} min)")
            radio_high.setText(f"{n_hi} Loops → {fmt_time(t_hi)} ({t_hi/60:.1f} min)")
            radio_low.setVisible(True)
            radio_high.setVisible(True)
            # Default A: praezise Cut-Variante vorselektieren, sonst naechstbeste
            if cut is not None:
                radio_cut.setChecked(True)
            elif abs(t_lo - desired) <= abs(t_hi - desired):
                radio_low.setChecked(True)
            else:
                radio_high.setChecked(True)
            result_label.setText("")
        elif len(options) == 1:
            n, t = options[0]
            radio_low.setText(f"{n} Loops → {fmt_time(t)} ({t/60:.1f} min)")
            radio_low.setChecked(True)
            radio_low.setVisible(True)
            radio_high.setVisible(False)
            result_label.setText(_t("loop_count_exact"))
        else:
            radio_low.setVisible(False)
            radio_high.setVisible(False)
            result_label.setText(_t("loop_count_error"))
        if keep_once:
            radio_once.setChecked(True)

    spin_minutes.valueChanged.connect(_update_options)
    _update_options()

    # BL-164: Bei Wiederoeffnen die zuletzt getroffene Wahl wiederherstellen
    # (statt der automatischen Default-Selektion aus _update_options).
    if current_target_min and current_target_min > 0:
        if current_cut and current_cut > 0 and radio_cut.isVisible():
            radio_cut.setChecked(True)
        elif current_count == 0:
            radio_infinite.setChecked(True)
        elif current_count is not None:
            _opts = calc_loop_count(spin_minutes.value() * 60.0,
                                    loop_in, loop_out, song_duration)
            if len(_opts) >= 1 and current_count == _opts[0][0]:
                radio_low.setChecked(True)
            elif len(_opts) >= 2 and current_count == _opts[1][0]:
                radio_high.setChecked(True)
    if current_play_mode is PlayMode.ONCE:
        radio_once.setChecked(True)

    btn_box = QHBoxLayout()
    btn_ok = QPushButton(_t("btn_ok"))
    btn_ok.setDefault(True)
    btn_cancel = QPushButton(_t("btn_cancel"))
    btn_ok.clicked.connect(dlg.accept)
    btn_cancel.clicked.connect(dlg.reject)
    btn_box.addStretch()
    btn_box.addWidget(btn_ok)
    btn_box.addWidget(btn_cancel)
    dlg_layout.addLayout(btn_box)

    if dlg.exec() == QDialog.Accepted:
        target_min = spin_minutes.value()
        checked_id = radio_group.checkedId()
        if checked_id == 4:
            return (0, 0, target_min, PlayMode.ONCE)
        if checked_id == 2:
            return (0, 0, target_min, PlayMode.LOOP)  # Endlos
        desired = target_min * 60.0
        options = calc_loop_count(desired, loop_in, loop_out, song_duration)
        if checked_id == 3:
            cut = _best_cut(desired, options)
            if cut is not None:
                return (cut[0], cut[1], target_min, PlayMode.LOOP)   # (loop_count, cut_abs_beats, min, play_mode)
        if checked_id == 0 and len(options) >= 1:
            return (options[0][0], 0, target_min, PlayMode.LOOP)
        elif checked_id == 1 and len(options) >= 2:
            return (options[1][0], 0, target_min, PlayMode.LOOP)
    return None


# --- Transport-/Icon-SVGs + _make_icon --------------------------------------

# SVG-Templates fuer Transport-Icons — eine Definition, Farbe kommt aus dem Skin
_SVG_PLAY  = '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24"><polygon points="5,3 20,12 5,21" fill="{c}"/></svg>'
_SVG_PAUSE = '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24"><rect x="4" y="3" width="5" height="18" rx="1" fill="{c}"/><rect x="15" y="3" width="5" height="18" rx="1" fill="{c}"/></svg>'
_SVG_STOP  = '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24"><rect x="4" y="4" width="16" height="16" rx="1" fill="{c}"/></svg>'
_SVG_FADE  = '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24"><polygon points="3,9 14,9 14,5 21,12 14,19 14,15 3,15" fill="{c}"/></svg>'
_SVG_AUTOFILL = '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24"><rect x="11" y="4" width="2" height="8" rx="1" fill="{c}"/><rect x="4" y="11" width="8" height="2" rx="1" fill="{c}"/><rect x="12" y="11" width="8" height="2" rx="1" fill="{c}"/><rect x="11" y="12" width="2" height="8" rx="1" fill="{c}"/><circle cx="5.5" cy="5.5" r="1.5" fill="{c}"/><circle cx="18.5" cy="5.5" r="1.5" fill="{c}"/><circle cx="5.5" cy="18.5" r="1.5" fill="{c}"/><circle cx="18.5" cy="18.5" r="1.5" fill="{c}"/></svg>'
# BL-178: X-Symbol fuer den "Termin entfernen"-Button. Gezeichnetes SVG (kein
# Font-Glyph -> rendert zuverlaessig) in neutralem Grau (auf hell wie dunkel sichtbar).
_SVG_REMOVE_X = '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24"><path d="M6 6 L18 18 M18 6 L6 18" stroke="{c}" stroke-width="2.4" stroke-linecap="round"/></svg>'
# BL-185: Bleistift (Caption bearbeiten) + Uhr (Zeit bearbeiten) — gezeichnete SVGs,
# damit sie unabhaengig vom Font zuverlaessig rendern (neutrales Grau).
_SVG_PENCIL = '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24"><path d="M4 20h4L18.5 9.5l-4-4L4 16v4z" fill="none" stroke="{c}" stroke-width="2" stroke-linejoin="round"/><path d="M14.5 5.5l4 4" stroke="{c}" stroke-width="2" stroke-linecap="round"/></svg>'
_SVG_CLOCK = '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24"><circle cx="12" cy="12" r="8.5" fill="none" stroke="{c}" stroke-width="2"/><path d="M12 7v5.5l3.5 2" fill="none" stroke="{c}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>'


# BL-204: Hufeisen-Magnet fuer den "Wieder andocken"-Button (dezent, oben rechts
# im Widget, sichtbar nur wenn ein Dock frei schwebt). Gefuelltes SVG, Oeffnung
# nach rechts, mit zwei Pol-Flaechen. Farbe kommt aus dem Skin ({c}); die Pole
# sind transparente Aussparungen (fill-rule evenodd) -> sie zeigen den Widget-
# Hintergrund und kontrastieren so in hellem wie dunklem Theme automatisch.
_SVG_MAGNET = (
    '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" '
    'viewBox="0 0 24 24">'
    '<path fill="{c}" fill-rule="evenodd" d="'
    'M21 3 L12 3 A9 9 0 0 0 12 21 L21 21 L21 15 L12 15 A3 3 0 0 1 12 9 L21 9 Z'
    'M16 4.5 h4 v3.2 h-4 Z'
    'M16 16.3 h4 v3.2 h-4 Z'
    '"/></svg>'
)


def _make_icon(svg_template: str, color: str) -> QIcon:
    """Erzeugt ein QIcon aus einem SVG-Template mit eingefuegter Farbe."""
    from PySide6.QtGui import QPixmap
    svg_bytes = svg_template.format(c=color).encode("utf-8")
    pixmap = QPixmap()
    pixmap.loadFromData(svg_bytes, "SVG")
    return QIcon(pixmap)


# Kaffeetasse von der Seite, einfarbig/flach (kein 3D): Tasse, Henkel, Untertasse.
_COFFEE_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" '
    'viewBox="0 0 24 24" fill="none" stroke="{c}" stroke-width="1.6" '
    'stroke-linecap="round" stroke-linejoin="round">'
    '<path d="M6 7 L16.5 7 L15 15 L7.5 15 Z"/>'        # Tasse (Seitenansicht)
    '<path d="M16.5 8.5 C20 9 20 13.5 16.5 14"/>'      # Henkel
    '<path d="M4.5 17.5 L18 17.5"/>'                   # Untertassen-Rand
    '<path d="M6.5 17.5 Q11.25 20.5 16 17.5"/>'        # Untertassen-Boden
    '</svg>'
)


# --- Dock-Fabrik -----------------------------------------------------------

def _make_dock(parent, title, widget, area, all_areas=None):
    """Erstellt ein QDockWidget mit einheitlichen Einstellungen.

    ACHTUNG: Qt's restoreState() ueberschreibt die hier gesetzten Features!
    Nach JEDEM restoreState()-Aufruf muss _reapply_dock_features() aufgerufen
    werden, damit Movable/Floatable/Closable erhalten bleiben.
    Siehe _reapply_dock_features() in P29MainWindow.
    """
    _md0 = perf_start()
    dock = QDockWidget(title, parent)
    _md1 = perf_split(f"      _make_dock({title}): QDockWidget()", _md0)
    if all_areas is None:
        all_areas = (Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea
                     | Qt.TopDockWidgetArea | Qt.BottomDockWidgetArea)
    dock.setAllowedAreas(all_areas)
    dock.setFeatures(
        QDockWidget.DockWidgetMovable
        | QDockWidget.DockWidgetFloatable
        | QDockWidget.DockWidgetClosable
    )
    # WA_StyledBackground: Custom QWidget-Subklassen malen ihren
    # Stylesheet-Hintergrund nur mit diesem Attribut. Ohne es
    # scheint bei Floating-Docks der helle System-Hintergrund durch.
    widget.setAttribute(Qt.WA_StyledBackground, True)
    # Kleine Mindestgroesse: Qt verweigert Andocken wenn Docks
    # ihre minimumSizeHint nicht unterschreiten koennen.
    widget.setMinimumSize(50, 50)
    _md2 = perf_split(f"      _make_dock({title}): setWidget()", _md1)
    dock.setWidget(widget)
    _md3 = perf_split(f"      _make_dock({title}): addDockWidget()", _md2)
    parent.addDockWidget(area, dock)
    perf_split(f"      _make_dock({title}): done", _md3)
    return dock


class _PlayBarrier:
    """Haelt den HOERBAREN Audio-Start zurueck, bis alle stream-gefaehrdenden
    bzw. asynchronen Rule-Aktionen fertig sind (Layout-Wechsel, Loop-Finder).

    Hintergrund: Rules auf 'song_started'/'song_resumed' koennen teure
    Qt-Layout-Operationen (restoreState/setFloating, ~100 ms GIL-Block) oder
    asynchrone Worker (Loop-Finder) ausloesen. Feuert der Trigger NACH
    engine.play(), trifft der Block einen bereits laufenden Audio-Callback ->
    hoerbares Ruckeln. Loesung: Trigger zuerst feuern (bei Stille), Audio erst
    starten, wenn die Aktionen 'fertig' melden.

    EIN gemeinsamer Mechanismus fuer ALLE 'erst-fertig-dann-Play'-Faelle —
    bewusst kein zweiter paralleler Pfad. Ablauf:
      1. begin_collecting()  vor fire_trigger()
      2. deferrte/asynchrone Aktionen holen add_token_if_collecting() und
         rufen release(token) bei Fertigstellung
      3. arm(on_ready)  scharfschalten; feuert on_ready sobald alle Tokens
         zurueck sind (oder nach Timeout als Notbremse gegen haengende Tokens)
    """

    # Notbremse: Loop-Finder darf einige Sekunden brauchen; Layout ist in ~100 ms
    # durch. Feuert ein Token wegen eines Bugs nie zurueck, startet Audio spaetestens
    # nach diesem Timeout trotzdem (statt Play komplett zu schlucken).
    _DEFAULT_TIMEOUT_MS = 8000

    def __init__(self):
        self._collecting = False
        self._pending = 0
        self._armed = False
        self._on_ready = None
        self._fired = False
        self._next_id = 0

    def is_busy(self) -> bool:
        """True, solange ein Play-Gate sammelt oder auf Tokens wartet."""
        return self._collecting or self._armed

    def begin_collecting(self):
        """Startet das Sammeln von Tokens (vor dem Trigger-Feuern)."""
        self._collecting = True
        self._pending = 0
        self._armed = False
        self._on_ready = None
        self._fired = False

    def add_token_if_collecting(self):
        """Registriert eine noch offene Aktion. Gibt ein Token zurueck (an
        release() zurueckzugeben) oder None, wenn gerade nicht gesammelt wird —
        dann verhaelt sich die Aktion exakt wie frueher (release(None) = no-op).
        """
        if not self._collecting:
            return None
        self._pending += 1
        self._next_id += 1
        return self._next_id

    def release(self, token):
        """Meldet eine Aktion als fertig. token None wird ignoriert."""
        if token is None:
            return
        if self._pending > 0:
            self._pending -= 1
        self._maybe_fire()

    def arm(self, on_ready, timeout_ms: int = None):
        """Scharfschalten: on_ready wird aufgerufen, sobald alle Tokens zurueck
        sind (oder spaetestens nach timeout_ms als Notbremse)."""
        self._collecting = False
        self._armed = True
        self._on_ready = on_ready
        QTimer.singleShot(timeout_ms or self._DEFAULT_TIMEOUT_MS,
                          self._on_timeout)
        self._maybe_fire()

    def _maybe_fire(self):
        if self._armed and not self._fired and self._pending <= 0:
            self._fire()

    def _on_timeout(self):
        if self._armed and not self._fired:
            print(f"[PlayBarrier] Timeout — {self._pending} Token(s) offen, "
                  f"starte Audio trotzdem")
            self._fire()

    def _fire(self):
        self._fired = True
        self._armed = False
        cb = self._on_ready
        self._on_ready = None
        if cb:
            cb()


# --- Umbrechende Button-Leiste ---------------------------------------------

class _WrapButtonBar(QWidget):
    """Button-Leiste, die bei zu wenig Breite in die naechste Zeile umbricht."""
    def __init__(self, spacing=4, parent=None):
        super().__init__(parent)
        self._widgets = []
        self._trailing = set()
        self._sp = spacing
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

    def add(self, widget):
        widget.setParent(self)
        self._widgets.append(widget)
        # Sichtbarkeitswechsel (z. B. Sync-Buttons im Auto-Sync-Modus) muss die
        # Leiste neu umbrechen — sonst bleiben Luecken/Ueberlappungen stehen.
        widget.installEventFilter(self)

    def add_trailing(self, widget):
        """Wie add(), aber das Widget wird in seiner Zeile rechtsbuendig ans Ende
        gesetzt (nutzt den freien Platz rechts, statt links an das vorige Widget
        anzuschliessen). Bricht wie alle anderen bei Platzmangel um."""
        self.add(widget)
        self._trailing.add(widget)

    def eventFilter(self, obj, event):
        if event.type() in (QEvent.Show, QEvent.Hide):
            self._relayout(self.width())
        return super().eventFilter(obj, event)

    @staticmethod
    def _w(widget):
        # Feste Breite (setFixedSize/setFixedWidth) direkt verwenden
        mn, mx = widget.minimumWidth(), widget.maximumWidth()
        if 0 < mn == mx:
            return mn
        return widget.sizeHint().width()

    @staticmethod
    def _h(widget):
        mn, mx = widget.minimumHeight(), widget.maximumHeight()
        if 0 < mn == mx:
            return mn
        return widget.sizeHint().height()

    def _relayout(self, avail_w):
        sp = self._sp
        # Zeilen berechnen
        rows = []
        current = []
        x = row_h = 0
        for w in self._widgets:
            # Versteckte Widgets reservieren keinen Platz (sonst Luecken/Versatz).
            if not w.isVisibleTo(self):
                continue
            bw, bh = self._w(w), self._h(w)
            if x > 0 and x + bw > avail_w:
                rows.append((current, row_h))
                current = []
                x = row_h = 0
            current.append((w, x, bw))
            x += bw + sp
            row_h = max(row_h, bh)
        if current:
            rows.append((current, row_h))
        # Geometrie setzen — alle Buttons einer Zeile gleich hoch
        y = 0
        for row_items, rh in rows:
            for w, rx, bw in row_items:
                # Trailing-Widgets rechtsbuendig ans Zeilenende (nur wenn rechts
                # noch Platz ist — max() verhindert Ueberlappung nach links).
                if w in self._trailing:
                    rx = max(rx, avail_w - bw)
                w.setGeometry(rx, y, bw, rh)
            y += rh + sp
        total_h = (y - sp) if rows else 0
        self.setMinimumHeight(max(total_h, 0))

    def relayout(self):
        """Oeffentlicher Neuaufbau — z. B. wenn sich der Text eines Trailing-
        Widgets (und damit dessen Breite) nachtraeglich aendert. Ein setText()
        loest von sich aus kein Resize/Show-Event aus, deshalb explizit."""
        self._relayout(self.width())

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._relayout(self.width())

    def showEvent(self, event):
        super().showEvent(event)
        self._relayout(self.width())

    def sizeHint(self):
        sp = self._sp
        vis = [b for b in self._widgets if b.isVisibleTo(self)]
        w = sum(self._w(b) for b in vis) + sp * max(0, len(vis) - 1)
        h = max((self._h(b) for b in vis), default=26)
        return QSize(w, h)


# --- SectionBarWidget: aus main.py hierher (BL-201, Stufe 6) — von Player
# UND LoopFinder genutzt, daher im gemeinsamen Blatt-Modul.
class SectionBarWidget(QWidget):
    """7 farbige Pill-Buttons fuer Singing-Call-Abschnitte (O,1,2,M,3,4,C).

    O/M/C = Rot (Gestaltgesetz: gleiche Rolle),
    1/3   = Hellgrau, 2/4 = Dunkleres Grau.
    """

    _LABELS   = ["O",      "1",       "2",       "M",      "3",       "4",       "C"]
    _SEC_KEYS = ["sec_o",  "sec_1",   "sec_2",   "sec_m",  "sec_3",   "sec_4",   "sec_c"]
    _FALLBACK = ["#9e3a3a","#6b7280", "#4a5568", "#9e3a3a","#6b7280", "#4a5568", "#9e3a3a"]

    def __init__(self, skin_mgr=None, parent=None):
        super().__init__(parent)
        self._skin_mgr = skin_mgr
        self._buttons: list = []
        self._build()

    def _build(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        for label in self._LABELS:
            btn = QPushButton(label)
            btn.setFixedHeight(26)
            btn.setCheckable(True)
            btn.setEnabled(False)   # Klick noch nicht implementiert
            btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            self._buttons.append(btn)
            layout.addWidget(btn)
        self.update_colors()

    def update_colors(self):
        """Sektionsfarben aus Skin laden — nach Skin-Wechsel aufrufen."""
        for i, btn in enumerate(self._buttons):
            color = (self._skin_mgr.color(self._SEC_KEYS[i], self._FALLBACK[i])
                     if self._skin_mgr else self._FALLBACK[i])
            btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {color};
                    color: #ffffff;
                    border: none;
                    border-radius: 4px;
                    font-size: 11px;
                    font-weight: bold;
                    padding: 1px 2px;
                }}
                QPushButton:checked  {{ border: 2px solid #ffffff; }}
                QPushButton:disabled {{ background-color: {color}; color: #ffffff; }}
            """)

    def set_active(self, index: int):
        """Markiert Abschnitt 0–6 als aktiv (fuer spaetere Verwendung)."""
        for i, btn in enumerate(self._buttons):
            btn.setChecked(i == index)

    def clear_active(self):
        for btn in self._buttons:
            btn.setChecked(False)


# --- Song-Reco/Random/Datums-Helfer: aus main.py (BL-201, Stufe 7) — von
# Songdata, Playlist und Hauptfenster genutzt.
def _reco_days_since(song_id, last_played_map, fallback_date):
    """Tage seit dem letzten Spielen dieses Songs.

    Nie gespielt -> gemessen ab fallback_date (Erstaufnahme-Grenze aus der INI),
    NICHT ab heute. Gemeinsame Quelle fuer die Empfehlungs-Sortierung UND die
    Score-Anzeige, damit die angezeigte Zahl exakt der Sortierung entspricht.
    """
    today = date.today()
    lp = last_played_map.get(song_id)
    if lp:
        try:
            return (today - date.fromisoformat(lp[:10])).days
        except (ValueError, TypeError):
            pass
    return (today - fallback_date).days


def _reco_score(song, last_played_map, fallback_date) -> int:
    """Empfehlungs-Score = Qualitaet x Tage-seit-gespielt (Ganzzahl)."""
    return int(song.quality * _reco_days_since(song.id, last_played_map, fallback_date))


def _weighted_random_order(songs, weight_of, draw_of):
    """Gewichtete Zufalls-Reihenfolge (BL-170, Roulette-Wheel-Selection).

    Ergebnis ist verteilungsgleich zu dem von Hand beschriebenen Verfahren
    ("Scores aufsummieren, Zufallszahl im Summenbereich ziehen, von vorne
    kumulativ zaehlen, Treffer entnehmen, wiederholen"), braucht aber nur
    einen Sortierdurchlauf statt n Durchlaeufe ueber die Restliste:
    O(n log n) statt O(n^2).

    Verfahren nach Efraimidis/Spirakis: zu jedem Song mit Gewicht w wird aus
    einer Gleichverteilung u in (0,1) der Schluessel -ln(u)/w gebildet;
    aufsteigend sortiert entspricht das exakt dem wiederholten Ziehen ohne
    Zuruecklegen. Songs mit hohem Gewicht bekommen im Mittel kleinere
    Schluessel und landen vorne, ohne dass ein niedriges Gewicht chancenlos
    waere.

    Args:
        songs: Liste der Songs.
        weight_of: Callable(song) -> Gewicht > 0.
        draw_of: Callable(song_id) -> gecachte Zufallszahl u aus (0,1).
                 Ueber den Cache bleibt die Reihenfolge stabil, solange nur
                 gefiltert wird (Tippen im Suchfeld sortiert nicht um).
    """
    keys = []
    for s in songs:
        w = weight_of(s)
        u = draw_of(s.id)
        keys.append((-math.log(u) / w, s))
    keys.sort(key=lambda x: x[0])
    return [s for _, s in keys]


def _style_date_cell(item, inherited: bool):
    """Formatiert eine Zelle der Datumsspalte im Einfuegedatum-Modus.

    Songs ohne gespeichertes date_added erben das Erstaufnahme-Datum der
    Bibliothek. Das wird grau/kursiv gezeigt, damit ein geerbtes Datum nicht wie
    ein echtes aussieht — dieselbe Sprache wie die Vorschlaege im Evening Planner.
    """
    if not inherited:
        return
    f = item.font()
    f.setItalic(True)
    item.setFont(f)
    item.setForeground(QColor("#888"))
    item.setToolTip(_t("tooltip_added_inherited"))


def mark_toggle(btn, active=False):
    """Einheitliche Toggle-Semantik fuer das Theme-QSS (gemeinsamer Code fuer
    alle umschaltbaren Buttons).

    Setzt IMMER die Property ``checkable="true"`` — dafuer greifen die generischen
    QSS-Regeln (AN = normal, AUS = gedimmt). Mit ``active=True`` kommt zusaetzlich
    ``activeState="true"`` dazu; die themebare Regel ``[activeState="true"]:checked``
    faerbt den Button dann bei AN gruen (Skin-Token ``success``). So gilt fuer alle
    Buttons gleicher Bedeutung dieselbe Farbe (Gestaltprinzip), rein ueber das Theme.

    Gibt den Button zurueck (verkettbar).
    """
    btn.setCheckable(True)
    btn.setProperty("checkable", "true")
    if active:
        btn.setProperty("activeState", "true")
    return btn


def widen_combo_popup(combo):
    """Aufklappliste einer Combobox so breit wie ihr laengster Eintrag, auch wenn
    das Control selbst schmal ist (schmale Laptop-Aufloesung schrumpft die Combo,
    die Eintraege waren dann in der Mitte abgeschnitten).

    Qt nimmt die Mindestbreite der View als Untergrenze fuer das Popup und
    schiebt es selbst in den Bildschirm. Ist die Combo breiter als ihr Inhalt,
    aendert sich nichts.
    """
    view = combo.view()
    width = (view.sizeHintForColumn(combo.modelColumn())
             + view.verticalScrollBar().sizeHint().width() + 2 * view.frameWidth())
    # Deckel: Popup (View + Rahmen des Containers drumherum) nie breiter als
    # der Bildschirm, sonst ragt es bei Riesen-Eintraegen raus
    screen = (combo.screen().availableGeometry().width()
              - 2 * view.parentWidget().frameWidth())
    view.setMinimumWidth(min(width, screen))


def opens_combo_popup(event):
    """True fuer die Ereignisse, mit denen Qt eine Combobox aufklappt
    (QComboBox::mousePressEvent/keyPressEvent, nachgemessen mit Qt 6.11):
    Mausklick, F4, Alt+Runter, Leertaste, Select.

    Leertaste/Select klappen editierbare Comboboxen nicht auf — dort kostet der
    Treffer nur ein ueberfluessiges Nachmessen. Blaettern (Runter ohne Alt)
    misst bewusst nicht, das waere bei langen Listen pro Tastendruck teuer.
    """
    if event.type() == QEvent.MouseButtonPress:
        return True
    if event.type() != QEvent.KeyPress:
        return False
    key, mods = event.key(), event.modifiers()
    return ((key == Qt.Key_F4 and mods == Qt.NoModifier)
            or (key == Qt.Key_Down and bool(mods & Qt.AltModifier))
            or key in (Qt.Key_Space, Qt.Key_Select))
