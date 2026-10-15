"""Potential-/Song-Pool-UI fuer Callers Caddy (BL-201, aus main.py ausgelagert).

Enthaelt PotentialWidget (Song-Pool/Kandidaten) samt Bulk-Worker-Threads,
Meta-Import/CSV-Match-, Ceder- und Krabbelkiste-Dialogen sowie Beautify.
Zirkelfrei: keine Import-Zeit-Rueckbezuege auf main.py (Version lazy).
"""

import os
import re
import json
import shutil
from datetime import date

from PySide6.QtWidgets import (
    QApplication, QWidget, QHBoxLayout, QVBoxLayout,
    QPushButton, QLabel, QFileDialog, QFrame, QCheckBox,
    QTableWidget, QTableWidgetItem, QHeaderView, QComboBox,
    QMessageBox, QDialog, QDialogButtonBox, QInputDialog,
    QAbstractItemView, QRadioButton, QButtonGroup,
    QTextEdit, QScrollArea, QProgressDialog, QTabWidget, QProgressBar,
)
from PySide6.QtCore import Qt, QTimer, QThread, Signal
from PySide6.QtGui import QColor

import perf
from perf import perf_log, perf_split
from song_db import CHECK_START_GENRE_NAME, CHECK_BEATSNAP_GENRE_NAME
from i18n import _t
from lyrics_widget import LyricsWidget, lyric_plain_text, lyric_section_lines
import zip_import
import singing_sections
import ceder_lookup
import song_data_io
import song_match
import song_catalog
import loop_windows


def _app_version():
    """App-Version lazy aus main lesen (vermeidet Import-Zirkel)."""
    try:
        import main
        return getattr(main, "__version__", "?")
    except Exception:
        return "?"


class _BulkTimingWorker(QThread):
    """Misst die durchschnittliche Laufzeit fuer Loop-Finder oder Beat-Snap."""
    progress = Signal(int, int)          # current, total
    finished = Signal(float)             # seconds_per_song (Durchschnitt)
    error = Signal(str)

    def __init__(self, jobs, mode='loop', parent=None):
        """jobs: list of (song_id, filepath, bpm); mode: 'loop', 'beatsnap' oder 'mp3_check'"""
        super().__init__(parent)
        self._jobs = jobs
        self._mode = mode
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        import time
        times = []
        for i, (sid, fp, bpm) in enumerate(self._jobs):
            if self._cancelled:
                return
            self.progress.emit(i + 1, len(self._jobs))
            t0 = time.perf_counter()
            try:
                if self._mode == 'beatsnap':
                    from bpm_detector import detect_beat_grid
                    detect_beat_grid(fp, bpm=bpm or None)
                elif self._mode == 'bpm':
                    from bpm_detector import detect_bpm
                    detect_bpm(fp)
                elif self._mode == 'mp3_check':
                    import soundfile as sf
                    sf.read(fp, frames=1024, dtype='float32')
                else:
                    from loop_finder import find_loop_candidates
                    find_loop_candidates(fp, bpm=bpm or None)
            except Exception:
                pass
            times.append(time.perf_counter() - t0)
        avg = sum(times) / len(times) if times else 5.0
        self.finished.emit(avg)


class _BulkAutoLoopWorker(QThread):
    """Fuehrt Auto-Loop fuer eine Liste von Songs durch (Hintergrundthread).

    Schreibt nicht selbst in die Datenbank: jeder gefundene Loop geht per
    loop_found an den Hauptthread, der ihn ueber song_db speichert (intern#207).
    """
    progress = Signal(int, int, str)     # current, total, song_name
    loop_found = Signal(int, float, float)  # song_id, loop_in, loop_out
    finished = Signal(int, int)          # done, skipped
    error = Signal(str)

    def __init__(self, jobs, preset=None, parent=None):
        """jobs: list of (song_id, filepath, bpm, name)

        preset: Loop-Finder-Preset (intern#207), bestimmt Suchfenster,
        Vergleichsfenster und Auswahlstrategie. None = Singing.
        """
        super().__init__(parent)
        self._jobs = jobs
        self._preset = preset or loop_windows.singing_preset()
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        import soundfile as _sf
        from loop_finder import find_loop_candidates, apply_selection_strategy
        compare_beats = int(self._preset.get("compare_beats", 16))
        strategy = str(self._preset.get("selection_strategy", "best_64"))
        done = skipped = 0
        for i, (sid, fp, bpm, name) in enumerate(self._jobs):
            if self._cancelled:
                break
            self.progress.emit(i + 1, len(self._jobs), name)
            try:
                windows = loop_windows.resolve_windows(
                    self._preset, _sf.info(fp).duration)
                if windows is None:
                    # Fenster passen nicht zur Songlaenge -> uebersprungen
                    skipped += 1
                    continue
                in_s, in_e, out_s, out_e = windows
                candidates = find_loop_candidates(
                    fp, bpm=bpm or None, compare_beats=compare_beats,
                    in_start=in_s, in_end=in_e, out_start=out_s, out_end=out_e)
                chosen = apply_selection_strategy(candidates, strategy)
                if chosen:
                    self.loop_found.emit(sid, chosen.loop_in, chosen.loop_out)
                    done += 1
                else:
                    skipped += 1
            except Exception as e:
                print(f"[BulkAutoLoop] Fehler bei Song #{sid}: {e}")
                skipped += 1
        self.finished.emit(done, skipped)


class _BulkBpmWorker(QThread):
    """Ermittelt die BPM einer Liste von Songs und schreibt base_bpm (Hintergrund)."""
    progress = Signal(int, int, str)     # current, total, song_name
    finished = Signal(int, int)          # done, skipped
    error = Signal(str)

    def __init__(self, jobs, db_path, parent=None):
        """jobs: list of (song_id, filepath, name)"""
        super().__init__(parent)
        self._jobs = jobs
        self._db_path = db_path
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        import sqlite3 as _sql
        from bpm_detector import detect_bpm
        conn = _sql.connect(self._db_path)
        done = skipped = 0
        try:
            for i, (sid, fp, name) in enumerate(self._jobs):
                if self._cancelled:
                    break
                self.progress.emit(i + 1, len(self._jobs), name)
                try:
                    bpm = detect_bpm(fp)
                    if bpm and bpm > 0:
                        conn.execute(
                            "UPDATE songs SET base_bpm=? WHERE id=?", (bpm, sid))
                        conn.commit()
                        done += 1
                    else:
                        skipped += 1
                except Exception as e:
                    print(f"[BulkBpm] Fehler bei Song #{sid}: {e}")
                    skipped += 1
        finally:
            conn.close()
        self.finished.emit(done, skipped)


class _BulkSingingStartWorker(QThread):
    """Ermittelt Songanfang+Ende (Singing-Body) einer Liste und schreibt fuer
     JEDEN erkennbaren Song singing_start_m1/singing_end_m1 (Hintergrund,
    Audio-Prioritaet). Ende = Start + 448 Beats (aus dem Detektor).

    Unsichere (mehrdeutige) Treffer werden trotzdem gesetzt — so ist jeder
    Singing ausgestattet — bekommen aber zusaetzlich das Marker-Genre
    'CHECK: START' als To-Do fuer den Caller. Sichere Treffer raeumen einen ggf.
    vorhandenen Marker wieder ab (relevant bei erneutem 'ALLE analysieren')."""
    progress = Signal(int, int, str)          # current, total, song_name
    finished = Signal(int, int, object)       # done, skipped, marked_names(list)
    error = Signal(str)

    def __init__(self, jobs, db_path, check_genre_id, parent=None):
        """jobs: list of (song_id, filepath, name, bpm_hint).
        check_genre_id: ID des 'CHECK: START'-Genres (im Main-Thread aufgeloest)."""
        super().__init__(parent)
        self._jobs = jobs
        self._db_path = db_path
        self._check_genre_id = check_genre_id
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        import sqlite3 as _sql
        from singing_body_detect import detect_singing_body
        conn = _sql.connect(self._db_path)
        gid = self._check_genre_id
        done = skipped = 0
        marked = []
        try:
            for i, (sid, fp, name, hint) in enumerate(self._jobs):
                if self._cancelled:
                    break
                self.progress.emit(i + 1, len(self._jobs), name)
                try:
                    res = detect_singing_body(fp, bpm_hint=hint)
                    if not res or not res.get("ok"):
                        skipped += 1
                        continue
                    start = float(res["start_sec"])
                    end = float(res["end_sec"])
                    conn.execute(
                        "INSERT OR REPLACE INTO song_properties (song_id, key, value) "
                        "VALUES (?, ?, ?)", (sid, "singing_start_m1", f"{start:.2f}"))
                    conn.execute(
                        "INSERT OR REPLACE INTO song_properties (song_id, key, value) "
                        "VALUES (?, ?, ?)", (sid, "singing_end_m1", f"{end:.2f}"))
                    if gid and gid > 0:
                        if res.get("ambiguous"):
                            # unsicher → gesetzt, aber als To-Do markieren
                            conn.execute(
                                "INSERT OR IGNORE INTO song_genres (song_id, genre_id) "
                                "VALUES (?, ?)", (sid, gid))
                            marked.append(name)
                        else:
                            # sicher → evtl. alten Marker abraeumen
                            conn.execute(
                                "DELETE FROM song_genres WHERE song_id = ? "
                                "AND genre_id = ?", (sid, gid))
                    conn.commit()
                    done += 1
                except Exception as e:
                    print(f"[BulkSingingStart] Fehler bei Song #{sid}: {e}")
                    skipped += 1
        finally:
            conn.close()
        self.finished.emit(done, skipped, marked)


class _BulkSyncPointsWorker(QThread):
    """Setzt die Lyric-Sync-Punkte einer Liste von Songs (Hintergrund).

    Rechnet exakt wie LyricsWidget._finish_auto_calc(): Body in 7 gleiche
    Abschnitte teilen, die Textbloecke der 7 Teile im Lyric-Plain-Text suchen
    und je Teil Anfangs- und Ende-Anker setzen (max. 14). Teile ohne eigenen
    Textblock bekommen keinen Anker — die Anzeige haelt dann an der letzten
    Marke, statt falschen Text einzublenden.

    Reine Text-/Datei-Arbeit, keine Audio-Analyse: langsam sind hier nur
    grosse PDF/DOCX. Songs ohne verwertbaren Text oder ohne erkennbare
    Abschnitts-Ueberschriften werden uebersprungen und namentlich gemeldet.
    """
    progress = Signal(int, int, str)          # current, total, song_name
    finished = Signal(int, int, object)       # done, skipped, skipped_names(list)
    error = Signal(str)

    def __init__(self, jobs, db_path, sections, parent=None):
        """jobs: list of (song_id, path, lyrics_file, name, start, end).
        sections: Keyword-Listen (im Main-Thread via load_sections geholt)."""
        super().__init__(parent)
        self._jobs = jobs
        self._db_path = db_path
        self._sections = sections
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        import sqlite3 as _sql
        conn = _sql.connect(self._db_path)
        done = skipped = 0
        skipped_names = []
        try:
            for i, (sid, path, lf, name, start, end) in enumerate(self._jobs):
                if self._cancelled:
                    break
                self.progress.emit(i + 1, len(self._jobs), name)
                try:
                    text = lyric_plain_text(path, lf)
                    if not text.strip():
                        skipped += 1
                        skipped_names.append(f"{name} ({_t('pot_sync_skip_notext')})")
                        continue
                    res = singing_sections.parse_sections(text, self._sections)
                    if not res.ok:
                        skipped += 1
                        skipped_names.append(
                            f"{name} ({_t('pot_sync_skip_nosections')})")
                        continue
                    seg = (end - start) / 7.0
                    anchors = []
                    last_end = None
                    for k in range(7):
                        t0 = start + k * seg
                        t1 = start + (k + 1) * seg
                        blk = res.parts.get(k + 1)
                        if blk:
                            s_char, e_char = blk
                            anchors.append((t0, int(s_char)))
                            anchors.append((max(t0, t1 - 1.0), int(e_char)))
                            last_end = int(e_char)
                        elif last_end is not None:
                            anchors.append((t0, last_end))
                            anchors.append((t1, last_end))
                    # Tag ist das Outro: er beginnt, wo der Closer endet.
                    # Additional Lyrics bekommen bewusst keinen Anker — sie
                    # laufen nicht im Zeitraster mit (wie in _finish_auto_calc).
                    tag_blk = (res.extras or {}).get("tag")
                    if tag_blk:
                        anchors.append((end, int(tag_blk[0])))
                    if not anchors:
                        skipped += 1
                        skipped_names.append(
                            f"{name} ({_t('pot_sync_skip_nosections')})")
                        continue
                    # Alte Anker dieses Slots ERST loeschen. Frueher stand hier
                    # die Annahme "Bulk-Kandidaten haben per Definition keinen
                    # Anker". Die gilt seit dem Komplettlauf ueber alle Songs
                    # nicht mehr: haette ein Song 20 Anker und wir schreiben 15
                    # per INSERT OR REPLACE, blieben die Anker 16-20 als Reste
                    # aus der alten Synchronisation stehen.
                    conn.execute(
                        "DELETE FROM song_properties WHERE song_id = ? "
                        "AND key LIKE 'lyric_sync_m1_l1_%'", (sid,))
                    conn.execute(
                        "DELETE FROM song_properties WHERE song_id = ? "
                        "AND key LIKE 'lyric_sections_l1_%'", (sid,))
                    # NUR nach Zeit sortieren (stabil), exakt wie
                    # _persist_sync_anchors: bei zeitgleichen Ankern — die
                    # entstehen, wenn ein Teil keinen eigenen Textblock hat und
                    # das Ende von Teil k auf den Anfang von k+1 faellt — zaehlt
                    # die Einfuegereihenfolge. Ein Sortieren nach dem ganzen
                    # Tupel wuerde sie nach Textposition umdrehen.
                    for idx, (sec, block) in enumerate(
                            sorted(anchors, key=lambda a: a[0]), start=1):
                        conn.execute(
                            "INSERT OR REPLACE INTO song_properties "
                            "(song_id, key, value) VALUES (?, ?, ?)",
                            (sid, f"lyric_sync_m1_l1_{idx}", f"{sec:.2f}|{int(block)}"))
                    # BL-171: Abschnitte als Zeilenbereiche mitschreiben, sonst
                    # bliebe der Abschnittsstreifen im Lyric-Fenster leer und
                    # der Bulk-Lauf haette die Analyse umsonst gemacht.
                    for name, (l0, l1) in lyric_section_lines(res, text).items():
                        conn.execute(
                            "INSERT OR REPLACE INTO song_properties "
                            "(song_id, key, value) VALUES (?, ?, ?)",
                            (sid, f"lyric_sections_l1_{name}", f"{l0}|{l1}"))
                    conn.commit()
                    done += 1
                except Exception as e:
                    print(f"[BulkSyncPoints] Fehler bei Song #{sid}: {e}")
                    skipped += 1
                    skipped_names.append(f"{name} ({e})")
        finally:
            conn.close()
        self.finished.emit(done, skipped, skipped_names)


class _BulkBeatSnapWorker(QThread):
    """Snapped Loop-Marker aller Songs auf den naechsten Beat.

    Bleibt der Offset 0.0 (zu schwache Korrelation, Datei nicht dekodierbar oder
    Loop schon exakt auf dem Beat), wird der Song mit dem Marker-Genre
    'CHECK: BEATSNAP' geflaggt und faellt so aus der Kandidatenliste — sonst
    taeten diese Songs endlos wieder als 'ohne BeatSnap' auftauchen. Findet der
    Lauf doch einen Offset (!= 0), wird ein ggf. vorhandener Marker abgeraeumt."""
    progress = Signal(int, int, str)     # current, total, song_name
    finished = Signal(int, int)          # done, skipped
    error = Signal(str)

    def __init__(self, jobs, db_path, check_genre_id=None, parent=None):
        """jobs: list of (song_id, filepath, bpm, loop_in, loop_out, name).
        check_genre_id: ID des 'CHECK: BEATSNAP'-Genres (im Main-Thread aufgeloest)."""
        super().__init__(parent)
        self._jobs = jobs
        self._db_path = db_path
        self._check_genre_id = check_genre_id
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        import sqlite3 as _sql
        import numpy as np
        from bpm_detector import detect_beat_grid
        # timeout=30: unter DB-Last (paralleler Worker/Play) nicht sofort
        # "database is locked" werfen, sondern warten.
        conn = _sql.connect(self._db_path, timeout=30)
        gid = self._check_genre_id
        done = skipped = 0

        def _mark(song_id):
            if gid and gid > 0:
                conn.execute("INSERT OR IGNORE INTO song_genres (song_id, genre_id) "
                             "VALUES (?, ?)", (song_id, gid))

        def _unmark(song_id):
            if gid and gid > 0:
                conn.execute("DELETE FROM song_genres WHERE song_id = ? "
                             "AND genre_id = ?", (song_id, gid))

        try:
            for i, (sid, fp, bpm, loop_in, loop_out, name) in enumerate(self._jobs):
                if self._cancelled:
                    break
                self.progress.emit(i + 1, len(self._jobs), name)
                try:
                    _, beat_times = detect_beat_grid(fp, bpm=bpm or None)
                    beats = np.array(beat_times)
                    new_in = float(beats[np.argmin(np.abs(beats - loop_in))])
                    new_out = float(beats[np.argmin(np.abs(beats - loop_out))])
                    if new_out <= new_in + 1.0:
                        candidates = beats[beats > new_in + 1.0]
                        if len(candidates) > 0:
                            new_out = float(candidates[0])
                        else:
                            # Kein sinnvoller Loop → als geprueft markieren
                            _mark(sid)
                            conn.commit()
                            skipped += 1
                            continue
                    # BL-172: zusaetzlich den Loop-Offset messen — genau wie der
                    # Einzel-Song-BeatSnap. Sonst bliebe loop_offset_ms=0 und der
                    # Song zaehlte in potential_loop_no_beatsnap weiter als
                    # "ohne BeatSnap". Bei zu schwacher Korrelation bleibt 0.0.
                    offset_ms = 0.0
                    try:
                        import soundfile as _sf
                        from audio_engine import compute_loop_offset
                        adata, asr = _sf.read(fp, dtype='float32')
                        res = compute_loop_offset(
                            adata, asr, int(new_in * asr), int(new_out * asr))
                        if res and res[2] >= 0.1:
                            offset_ms = float(res[1])
                    except Exception as e:
                        print(f"[BulkBeatSnap] Offset-Messung Song #{sid}: {e}")
                    conn.execute(
                        "UPDATE songs SET loop_in=?, loop_out=?, loop_offset_ms=? "
                        "WHERE id=?", (new_in, new_out, offset_ms, sid))
                    # Offset gefunden → sauber; Offset 0.0 → als geprueft markieren,
                    # damit der Song nicht endlos wieder auftaucht.
                    if offset_ms != 0.0:
                        _unmark(sid)
                    else:
                        _mark(sid)
                    conn.commit()
                    done += 1
                except Exception as e:
                    print(f"[BulkBeatSnap] Fehler bei Song #{sid}: {e}")
                    # Nicht dekodierbar o.ae. → als geprueft markieren
                    try:
                        _mark(sid)
                        conn.commit()
                    except Exception:
                        pass
                    skipped += 1
        finally:
            conn.close()
        self.finished.emit(done, skipped)


class _BulkLoopOptimizeWorker(QThread):
    """Optimiert die vorhandenen Loop-Marken einer Liste von Songs.

    Statt den ganzen Song zu durchsuchen (wie _BulkAutoLoopWorker), wird nur
    in einem Fenster um die bestehenden Marken gesucht (+-margin_pct % der
    Songdauer). Das entspricht dem interaktiven "Optimize"-Preset und ist
    fuer SqView-Umsteiger gedacht, die schon Loops haben, aber nicht perfekt.
    """
    progress = Signal(int, int, str)     # current, total, song_name
    finished = Signal(int, int)          # done, skipped
    error = Signal(str)

    def __init__(self, jobs, db_path, margin_pct, parent=None):
        """jobs: list of (song_id, filepath, bpm, loop_in, loop_out, name)"""
        super().__init__(parent)
        self._jobs = jobs
        self._db_path = db_path
        self._margin_pct = margin_pct
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        import sqlite3 as _sql
        import soundfile as sf
        import time as _time
        from loop_finder import find_loop_candidates, apply_selection_strategy
        conn = _sql.connect(self._db_path)
        done = skipped = 0
        try:
            for i, (sid, fp, bpm, loop_in, loop_out, name) in enumerate(self._jobs):
                if self._cancelled:
                    break
                self.progress.emit(i + 1, len(self._jobs), name)
                # Per-Song-Timing fuer den Perf-Log (nur aktiv wenn Perf-Log an)
                t0 = _time.perf_counter()
                outcome = "skip"
                try:
                    info = sf.info(fp)
                    dur = info.frames / info.samplerate if info.samplerate else 0.0
                    if dur <= 0 or loop_out <= loop_in:
                        skipped += 1
                        continue
                    margin = dur * self._margin_pct / 100.0
                    candidates = find_loop_candidates(
                        fp, bpm=bpm or None,
                        in_start=max(0.0, loop_in - margin),
                        in_end=loop_in + margin,
                        out_start=loop_out - margin,
                        out_end=min(dur, loop_out + margin))
                    chosen = apply_selection_strategy(candidates, 'best_64')
                    if chosen:
                        conn.execute(
                            "UPDATE songs SET loop_in=?, loop_out=? WHERE id=?",
                            (chosen.loop_in, chosen.loop_out, sid))
                        conn.commit()
                        done += 1
                        outcome = "ok"
                    else:
                        skipped += 1
                except Exception as e:
                    print(f"[BulkLoopOptimize] Fehler bei Song #{sid}: {e}")
                    skipped += 1
                    outcome = "error"
                finally:
                    perf_log(
                        f"  BulkLoopOptimize #{sid} '{name}' "
                        f"(±{self._margin_pct}%, {outcome})", t0)
        finally:
            conn.close()
        self.finished.emit(done, skipped)


class _BulkDeleteWorker(QThread):
    """Loescht eine Liste von Songs aus der DB im Hintergrund (BL-148).

    Eiserne Regel: Ein Massen-DELETE (potenziell tausende Zeilen) darf den
    Main-Thread nicht blockieren, solange evtl. Audio laeuft. Eigene Connection,
    eine Transaktion. Nutzt SongDB.bulk_delete_on_connection (keine SQL-Duplikate).
    """
    finished = Signal(int)    # Anzahl geloeschter Songs
    error = Signal(str)

    def __init__(self, song_ids, db_path, delete_history, parent=None):
        super().__init__(parent)
        self._song_ids = list(song_ids)
        self._db_path = db_path
        self._delete_history = delete_history

    def run(self):
        import sqlite3 as _sql
        import time as _time
        from song_db import SongDatabase
        t0 = _time.perf_counter()
        conn = _sql.connect(self._db_path)
        deleted = 0
        try:
            deleted = SongDatabase.bulk_delete_on_connection(
                conn, self._song_ids, self._delete_history)
        except Exception as e:
            print(f"[BulkDelete] Fehler: {e}")
            self.error.emit(str(e))
            conn.close()
            return
        finally:
            conn.close()
        perf_log(f"  BulkDelete {len(self._song_ids)} Songs "
                 f"(Historie {'mit' if self._delete_history else 'behalten'})", t0)
        self.finished.emit(deleted)


class _NoMp3Worker(QThread):
    """Prueft fuer alle Song-Kandidaten ob die MP3-Datei in einem Musik-Verzeichnis liegt."""
    progress = Signal(int, int)   # current, total
    finished = Signal(list)       # list of (song_id, display_name)

    def __init__(self, candidates, music_dirs, parent=None):
        """candidates: list of (song_id, title, filename)
        music_dirs:  list of absoluter Verzeichnis-Pfade (main-thread-seitig aufgeloest)
        """
        super().__init__(parent)
        self._candidates = candidates
        self._music_dirs = music_dirs
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        import os as _os
        import time as _time
        result = []
        total = len(self._candidates)
        last_emit = 0.0
        for i, (song_id, title, filename) in enumerate(self._candidates):
            if self._cancelled:
                break
            found = any(
                _os.path.isfile(_os.path.join(d, filename))
                for d in self._music_dirs
            )
            if not found:
                result.append((song_id, title or filename))
            # Max. 10 Progress-Updates/Sek — verhindert Event-Queue-Overflow
            now = _time.monotonic()
            if now - last_emit >= 0.1:
                self.progress.emit(i + 1, total)
                last_emit = now
        if not self._cancelled:
            self.progress.emit(total, total)
            self.finished.emit(result)


class _BadMp3Worker(QThread):
    """Prueft ob Audiodateien von soundfile/libsndfile gelesen werden koennen."""
    progress = Signal(int, int)   # current, total
    finished = Signal(list)       # list of (song_id, display_name)

    def __init__(self, candidates, music_dirs, parent=None):
        """candidates: list of (song_id, title, filename)
        music_dirs:  list of absoluter Verzeichnis-Pfade (main-thread-seitig aufgeloest)
        """
        super().__init__(parent)
        self._candidates = candidates
        self._music_dirs = music_dirs
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        import os as _os
        import time as _time
        import soundfile as sf
        result = []
        total = len(self._candidates)
        last_emit = 0.0
        for i, (song_id, title, filename) in enumerate(self._candidates):
            if self._cancelled:
                break
            # Dateipfad in konfigurierten Musik-Ordnern suchen
            fp = None
            for d in self._music_dirs:
                candidate = _os.path.join(d, filename)
                if _os.path.isfile(candidate):
                    fp = candidate
                    break
            if fp:
                try:
                    sf.read(fp, frames=1024, dtype='float32')
                except Exception:
                    result.append((song_id, title or filename))
            # Max. 10 Progress-Updates/Sek — verhindert Event-Queue-Overflow
            now = _time.monotonic()
            if now - last_emit >= 0.1:
                self.progress.emit(i + 1, total)
                last_emit = now
        if not self._cancelled:
            self.progress.emit(total, total)
            self.finished.emit(result)


_META_EXPORT_FIELDS = [
    ('artist',          'Interpret (Caller)', 'songs_field'),
    ('label',           'Label + Nr.',        'songs_field'),
    ('original_artist', 'Original Artist',    'property'),
    ('release_year',    'Erscheinungsjahr',   'property'),
    ('genre',           'Genre',              'genre'),
    ('quality',         'Quality (0–10)',     'rating'),
    ('err',             'ERR (0–4)',          'rating'),
]


class _FlowWidget(QWidget):
    """Container-Widget das seine Kinder nebeneinander platziert und
    automatisch in die naechste Zeile umbricht wenn kein Platz mehr ist."""

    def __init__(self, h_spacing=6, v_spacing=6, parent=None):
        super().__init__(parent)
        self._h_spacing = h_spacing
        self._v_spacing = v_spacing
        self._widgets = []

    def addWidget(self, widget):
        widget.setParent(self)
        self._widgets.append(widget)
        widget.show()
        self._relayout()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._relayout()

    def _relayout(self):
        w = self.width() or 400
        x, y, line_h = 0, 0, 0
        for btn in self._widgets:
            hint = btn.sizeHint()
            # Mindestgroessen beruecksichtigen: resize() clamped auf
            # minimumSize, sizeHint tut das nicht → sonst rechnet die
            # Zeilenhoehe zu klein und die Zeilen ueberlappen.
            bw = max(hint.width(), btn.minimumWidth())
            bh = max(hint.height(), btn.minimumHeight())
            if x + bw > w and line_h > 0:
                x = 0
                y += line_h + self._v_spacing
                line_h = 0
            btn.move(x, y)
            btn.resize(bw, bh)
            x += bw + self._h_spacing
            line_h = max(line_h, bh)
        self.setFixedHeight(y + line_h)


class _MetaFieldSelectDialog(QDialog):
    """Feldauswahl fuer den Metadaten-Export."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(_t('pot_meta_export'))
        self.setMinimumWidth(280)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(_t('pot_meta_select_fields')))
        self._checks = {}
        for key, label, _ in _META_EXPORT_FIELDS:
            cb = QCheckBox(label)
            cb.setChecked(True)
            layout.addWidget(cb)
            self._checks[key] = cb
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_ok = QPushButton(_t('btn_ok'))
        btn_ok.setDefault(True)
        btn_cancel = QPushButton(_t('btn_cancel'))
        btn_ok.clicked.connect(self.accept)
        btn_cancel.clicked.connect(self.reject)
        btn_row.addWidget(btn_ok)
        btn_row.addWidget(btn_cancel)
        layout.addLayout(btn_row)

    def selected(self):
        return [(k, lbl, src) for (k, lbl, src), (key, cb)
                in zip(_META_EXPORT_FIELDS, self._checks.items()) if cb.isChecked()]


class _MetaImportPreviewDialog(QDialog):
    """Preview-Tabelle vor dem Metadaten-Import."""

    def __init__(self, rows, parent=None, notice=""):
        # rows: [(song_id, title, field_label, value_str, warning)]
        # notice: optionaler Hinweis ueber der Tabelle (intern#108)
        super().__init__(parent)
        self.setWindowTitle(_t('pot_meta_import'))
        self.setMinimumSize(600, 400)
        layout = QVBoxLayout(self)

        # rows hat eine Zeile je Feld -> Songs einzeln zaehlen
        info = QLabel(_t('pot_meta_import_preview_info',
                         count=len({r[0] for r in rows})))
        info.setWordWrap(True)
        layout.addWidget(info)
        if notice:
            notice_lbl = QLabel(notice)
            notice_lbl.setWordWrap(True)
            notice_lbl.setStyleSheet("color: #d04040; font-weight: 600;")
            layout.addWidget(notice_lbl)

        self._table = QTableWidget(len(rows), 5)
        self._table.setHorizontalHeaderLabels([
            '', _t('pot_col_name'), 'Feld', 'Wert', 'Hinweis'
        ])
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self._table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self._table.verticalHeader().setVisible(False)
        self._table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._table.setSelectionBehavior(QTableWidget.SelectRows)

        self._checkboxes = []
        for i, (song_id, title, field_lbl, value_str, warning) in enumerate(rows):
            cb = QCheckBox()
            cb.setChecked(not warning)
            cb_w = QWidget()
            cb_l = QHBoxLayout(cb_w)
            cb_l.setContentsMargins(4, 0, 4, 0)
            cb_l.addWidget(cb)
            self._table.setCellWidget(i, 0, cb_w)
            self._table.setItem(i, 1, QTableWidgetItem(title))
            self._table.setItem(i, 2, QTableWidgetItem(field_lbl))
            self._table.setItem(i, 3, QTableWidgetItem(value_str))
            warn_item = QTableWidgetItem(warning or "")
            if warning:
                warn_item.setForeground(Qt.red)
            self._table.setItem(i, 4, warn_item)
            self._checkboxes.append((cb, song_id, field_lbl, value_str))

        layout.addWidget(self._table, 1)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_ok = QPushButton(_t('btn_ok'))
        btn_ok.setDefault(True)
        btn_cancel = QPushButton(_t('btn_cancel'))
        btn_ok.clicked.connect(self.accept)
        btn_cancel.clicked.connect(self.reject)
        btn_row.addWidget(btn_ok)
        btn_row.addWidget(btn_cancel)
        layout.addLayout(btn_row)

    def confirmed(self):
        """Gibt [(song_id, field_label, value_str)] fuer gecheckte Zeilen zurueck."""
        return [(sid, lbl, val) for cb, sid, lbl, val in self._checkboxes if cb.isChecked()]


class _CsvMatchDialog(QDialog):
    """Preview-Tabelle fuer den CSV-Abgleich mit farblicher Markierung und Auswahl."""

    # Hintergrundfarben fuer vorgeschlagene Zellen
    _GREEN = QColor(180, 230, 180)
    _YELLOW = QColor(255, 230, 120)

    def __init__(self, match_rows, selected_fields, db, parent=None):
        """
        match_rows: list of dicts {
            'song_id': int,
            'title': str,          # DB-Titel
            'label_db': str,       # DB-Label-Feld (Kontext)
            'match_score': float,  # 1.0 = exakt, <1.0 = fuzzy
            'fields': {            # key -> {'values': [str], 'chosen': str or None}
                'artist': {'values': ['Tom Jones'], 'chosen': 'Tom Jones'},
                'genre':  {'values': ['Country', 'Country, Pop'], 'chosen': None},  # None = mehrdeutig
            }
        }
        selected_fields: [(key, label, source), ...]
        db: SongDb-Instanz (fuer Genre-Lookup)
        """
        super().__init__(parent)
        self.setWindowTitle(_t('pot_meta_csv_title'))
        self.setMinimumSize(820, 500)
        self._match_rows = match_rows
        self._selected_fields = selected_fields
        self._db = db
        self._field_keys = [k for k, _, _ in selected_fields]
        self._field_labels = {k: lbl for k, lbl, _ in selected_fields}
        self._checkboxes = []   # (QCheckBox, row_idx)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        info = QLabel(_t("pot_qe_match_info", count=len(self._match_rows)))
        info.setWordWrap(True)
        layout.addWidget(info)

        # Spalten: ✓ | Titel | Label/Nr. | Match% | Feld1 | Feld2 | ...
        fixed_cols = 4
        total_cols = fixed_cols + len(self._field_keys)
        self._table = QTableWidget(len(self._match_rows), total_cols)
        headers = ['', _t('pot_meta_csv_col_title'), _t('pot_meta_csv_col_label'),
                   _t('pot_meta_csv_match_quality')]
        headers += [self._field_labels[k] for k in self._field_keys]
        self._table.setHorizontalHeaderLabels(headers)
        hdr = self._table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(1, QHeaderView.Stretch)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        for ci in range(len(self._field_keys)):
            hdr.setSectionResizeMode(fixed_cols + ci, QHeaderView.ResizeToContents)
        self._table.verticalHeader().setVisible(False)
        self._table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._table.setSelectionBehavior(QTableWidget.SelectRows)
        self._table.doubleClicked.connect(self._on_double_click)

        for ri, row in enumerate(self._match_rows):
            cb = QCheckBox()
            cb.setChecked(True)
            cb_w = QWidget()
            cb_l = QHBoxLayout(cb_w)
            cb_l.setContentsMargins(4, 0, 4, 0)
            cb_l.addWidget(cb)
            self._table.setCellWidget(ri, 0, cb_w)
            self._checkboxes.append((cb, ri))

            self._table.setItem(ri, 1, QTableWidgetItem(row['title']))
            self._table.setItem(ri, 2, QTableWidgetItem(row['label_db'] or ''))
            pct = f"{row['match_score']*100:.0f}%"
            self._table.setItem(ri, 3, QTableWidgetItem(pct))

            for ci, key in enumerate(self._field_keys):
                col = fixed_cols + ci
                fd = row['fields'].get(key)
                if fd is None:
                    item = QTableWidgetItem('')
                    self._table.setItem(ri, col, item)
                    continue
                if fd['chosen'] is not None:
                    item = QTableWidgetItem(fd['chosen'])
                    item.setBackground(self._GREEN)
                    item.setToolTip(fd['chosen'])
                else:
                    # Mehrdeutig: mehrere CSV-Zeilen mit unterschiedlichen Werten
                    item = QTableWidgetItem(_t('pot_meta_csv_ambiguous'))
                    item.setBackground(self._YELLOW)
                    item.setToolTip("\n".join(fd['values']))
                self._table.setItem(ri, col, item)

        layout.addWidget(self._table, 1)

        # Selektions-Buttons
        sel_row = QHBoxLayout()
        btn_all = QPushButton(_t('pot_meta_csv_select_all'))
        btn_none = QPushButton(_t('pot_meta_csv_select_none'))
        btn_all.clicked.connect(lambda: self._set_all(True))
        btn_none.clicked.connect(lambda: self._set_all(False))
        sel_row.addWidget(btn_all)
        sel_row.addWidget(btn_none)
        sel_row.addStretch()
        layout.addLayout(sel_row)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_ok = QPushButton(_t('btn_ok'))
        btn_ok.setDefault(True)
        btn_cancel = QPushButton(_t('btn_cancel'))
        btn_ok.clicked.connect(self.accept)
        btn_cancel.clicked.connect(self.reject)
        btn_row.addWidget(btn_ok)
        btn_row.addWidget(btn_cancel)
        layout.addLayout(btn_row)

    def _set_all(self, state):
        for cb, _ in self._checkboxes:
            cb.setChecked(state)

    def _on_double_click(self, index):
        """Doppelklick auf mehrdeutige Zelle: Auswahl-Dialog zeigen."""
        col = index.column()
        fixed_cols = 4
        if col < fixed_cols:
            return
        ri = index.row()
        key = self._field_keys[col - fixed_cols]
        fd = self._match_rows[ri]['fields'].get(key)
        if fd is None or len(fd['values']) <= 1:
            return
        # Auswahl anbieten
        chosen, ok = QInputDialog.getItem(
            self, _t('pot_meta_csv_title'),
            f"Welchen Wert für '{self._field_labels[key]}' übernehmen?",
            fd['values'], 0, False
        )
        if ok and chosen:
            fd['chosen'] = chosen
            item = self._table.item(ri, col)
            item.setText(chosen)
            item.setBackground(self._GREEN)

    def confirmed_changes(self):
        """Gibt Liste von (song_id, key, source, value) fuer alle gecheckte Zeilen."""
        source_map = {k: src for k, _, src in self._selected_fields}
        result = []
        for cb, ri in self._checkboxes:
            if not cb.isChecked():
                continue
            row = self._match_rows[ri]
            for key in self._field_keys:
                fd = row['fields'].get(key)
                if fd and fd['chosen'] is not None and fd['chosen'] != '':
                    result.append((row['song_id'], key, source_map[key], fd['chosen']))
        return result


class _CederLookupWorker(QThread):
    """Sucht ein Cue Sheet auf ceder.net — im Thread, nie im Main-Thread.

    Netzwerkaufrufe gehoeren zwingend hierher: ein haengender Socket wuerde den
    Main-Thread blockieren und damit ueber den GIL den Audio-Callback aushungern
    (siehe Audio-Prioritaet in CLAUDE.md). Timeouts stecken zusaetzlich in
    ceder_lookup.
    """
    finished_ok = Signal(object, object)   # (kandidatenliste, info-dict)
    failed = Signal(str)

    def __init__(self, title, label_field, labels_path, parent=None):
        super().__init__(parent)
        self._title = title
        self._label = label_field
        self._labels_path = labels_path

    def run(self):
        try:
            labels = ceder_lookup.load_labels(
                self._labels_path, version=_app_version())
            cands, info = ceder_lookup.find_candidates(
                self._title, self._label, labels, version=_app_version())
            self.finished_ok.emit(cands, info)
        except ceder_lookup.CederError as e:
            self.failed.emit(str(e))
        except Exception as e:
            self.failed.emit(f"{type(e).__name__}: {e}")


class _CederDownloadWorker(QThread):
    """Holt das Cue Sheet eines Datensatzes und liefert fertiges HTML."""
    finished_ok = Signal(str, str)   # (html, record_id)
    failed = Signal(str)

    def __init__(self, record_id, title, parent=None):
        super().__init__(parent)
        self._rid = str(record_id)
        self._title = title

    def run(self):
        try:
            frag = ceder_lookup.fetch_cuesheet(
                self._rid, version=_app_version())
            if not frag or len(frag.strip()) < 40:
                self.failed.emit(_t('ceder_empty_sheet'))
                return
            url = f"{ceder_lookup.BASE}viewsingle.php?RecordId={self._rid}"
            self.finished_ok.emit(
                ceder_lookup.to_lyric_html(frag, self._title, url), self._rid)
        except ceder_lookup.CederError as e:
            self.failed.emit(str(e))
        except Exception as e:
            self.failed.emit(f"{type(e).__name__}: {e}")


class _CederCandidateDialog(QDialog):
    """Trefferliste mit Treffersicherheit — der Nutzer entscheidet.

    Bewusst keine stille Uebernahme des besten Treffers: derselbe Titel
    erscheint beim selben Label mehrfach mit verschiedenen Nummern, und ein
    falsches Cue Sheet faellt im Live-Betrieb erst auf der Buehne auf.
    """

    def __init__(self, cands, info, song_title, song_label, parent=None):
        super().__init__(parent)
        self.setWindowTitle(_t('ceder_dialog_title'))
        self.resize(760, 420)
        self._cands = cands
        lay = QVBoxLayout(self)

        head = _t('ceder_searched_for').format(
            title=song_title or "—", label=song_label or "—")
        if info.get("fallback_title_only"):
            head += "\n" + _t('ceder_fallback_title')
        elif not info.get("label_id") and info.get("label_name"):
            head += "\n" + _t('ceder_label_unknown').format(
                label=info.get("label_name"))
        lbl = QLabel(head)
        lbl.setWordWrap(True)
        lay.addWidget(lbl)

        self._table = QTableWidget()
        self._table.setColumnCount(6)
        self._table.setHorizontalHeaderLabels([
            _t('ceder_col_confidence'), _t('ceder_col_title'),
            _t('ceder_col_label'), _t('ceder_col_artist'),
            _t('ceder_col_year'), _t('ceder_col_why')])
        self._table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SingleSelection)
        self._table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._table.setRowCount(len(cands))
        for i, c in enumerate(cands):
            vals = [f"{c.score} % ({c.confidence})", c.title, c.label_full,
                    c.artist or c.sd_artist, c.year, ", ".join(c.reasons)]
            for col, v in enumerate(vals):
                self._table.setItem(i, col, QTableWidgetItem(str(v)))
        self._table.resizeColumnsToContents()
        self._table.horizontalHeader().setStretchLastSection(True)
        if cands:
            self._table.selectRow(0)
        self._table.doubleClicked.connect(self.accept)
        lay.addWidget(self._table, 1)

        box = QDialogButtonBox()
        self._btn_ok = box.addButton(_t('ceder_btn_download'),
                                     QDialogButtonBox.AcceptRole)
        box.addButton(QDialogButtonBox.Cancel)
        self._btn_ok.setEnabled(bool(cands))
        box.accepted.connect(self.accept)
        box.rejected.connect(self.reject)
        lay.addWidget(box)

    def selected(self):
        rows = self._table.selectionModel().selectedRows()
        if not rows:
            return None
        idx = rows[0].row()
        return self._cands[idx] if 0 <= idx < len(self._cands) else None


class _KrabbelkisteWorker(QThread):
    """Durchsucht einen Ordner nach Lyric-Dateien und ordnet sie den Singing
    Calls ohne Lyrics zu (Titel + Label + Plattennummer).

    Datei-I/O und Text-Extraktion (auch langsame PDF/DOCX) laufen bewusst hier
    im Thread — nie im Main-Thread, der sonst ueber den GIL den Audio-Callback
    aushungern wuerde (siehe Audio-Prioritaet in CLAUDE.md). Die Match-Logik
    selbst liegt in song_match, damit dieselbe Basis wie bei der Ceder-Suche
    greift.
    """
    progress = Signal(int, int)     # (aktuell, gesamt)  — Datei-Parsing-Phase
    finished_ok = Signal(object)    # Liste von Ergebnis-Dicts
    failed = Signal(str)

    # Nur die Kopfzeilen eines Cue Sheets tragen Titel/Label/Nummer; der Body
    # (die Lyrics selbst) wird nicht geparst — dort steht kein Label.
    _HEAD_LINES = 20
    _MAX_HEAD_LEN = 80   # laengere Zeilen sind Fliesstext, kein Kopf

    def __init__(self, folder, recursive, songs, lists, parent=None):
        super().__init__(parent)
        self._folder = folder
        self._recursive = recursive
        # Liste (id, title, label, filename[, such_label]); such_label = Label
        # fuer den Abgleich (ggf. aus dem Katalog), label bleibt die Anzeige
        self._songs = songs
        self._lists = lists
        self._cancel = False

    def cancel(self):
        self._cancel = True

    def run(self):
        try:
            files = self._gather_files()
            if not files:
                self.finished_ok.emit([])
                return

            # Jede Datei einmalig parsen: Name + Inhaltskopf + billiger Heuhaufen
            # fuers Vorfiltern.
            parsed = []
            total = len(files)
            for i, path in enumerate(files):
                if self._cancel:
                    self.finished_ok.emit([])
                    return
                self.progress.emit(i + 1, total)
                fn = os.path.basename(path)
                stem = os.path.splitext(fn)[0]
                head_lines = self._header_lines(path, fn)
                haystack = song_match._norm(" ".join([fn, stem] + head_lines))
                parsed.append((path, fn, stem, head_lines, haystack))

            # Pro Song besten Treffer ueber alle Dateien. Ein billiger
            # Wort-/Nummern-Vorfilter spart die teure Aehnlichkeitsrechnung fuer
            # die grosse Mehrheit klar unpassender Dateien (grosse Krabbelkiste x
            # viele No-Lyrics-Songs waere sonst quadratisch teuer).
            results = []
            for sid, title, label, filename, *extra in self._songs:
                if self._cancel:
                    break
                search_label = extra[0] if extra else label
                words = self._title_words(title)
                _lname, wnumber = song_match.split_label_number(search_label or "")
                wnumber = (wnumber or "").lstrip("0").lower()
                best, best_file = None, None
                for (path, fn, stem, head_lines, haystack) in parsed:
                    if not self._passes_gate(words, wnumber, haystack):
                        continue
                    m = song_match.best_match(title or "", search_label or "",
                                              stem, head_lines, self._lists)
                    if best is None or m.score > best.score:
                        best, best_file = m, (path, fn)
                if best is None or best.score < song_match.MIN_SCORE:
                    continue
                results.append({
                    "song_id": sid, "song_title": title or "",
                    "song_label": label or "", "song_filename": filename or "",
                    "file_path": best_file[0], "file_name": best_file[1],
                    "match": best,
                })
            results.sort(key=lambda r: r["match"].score, reverse=True)
            self.finished_ok.emit(results)
        except Exception as e:  # noqa: BLE001
            self.failed.emit(f"{type(e).__name__}: {e}")

    def _gather_files(self):
        exts = zip_import.LYRICS_EXTENSIONS
        out = []
        if self._recursive:
            for root, _dirs, names in os.walk(self._folder):
                for nm in names:
                    if os.path.splitext(nm)[1].lower() in exts:
                        out.append(os.path.join(root, nm))
        else:
            try:
                for nm in sorted(os.listdir(self._folder)):
                    p = os.path.join(self._folder, nm)
                    if os.path.isfile(p) \
                            and os.path.splitext(nm)[1].lower() in exts:
                        out.append(p)
            except OSError:
                pass
        return out

    def _header_lines(self, path, filename):
        """Die ersten kurzen Kopfzeilen der Datei als Rohtext (Titel/Label steht
        bei Cue Sheets oben; SqView-Lyrics tragen den Titel als erste Zeile)."""
        try:
            text = lyric_plain_text(path, filename)
        except Exception:  # noqa: BLE001 — eine kaputte Datei darf den Lauf nicht kippen
            return []
        if not text:
            return []
        lines, seen, count = [], set(), 0
        for line in text.splitlines():
            line = line.strip()
            if not line or len(line) > self._MAX_HEAD_LEN:
                continue
            count += 1
            if count > self._HEAD_LINES:
                break
            key = line.lower()
            if key in seen:
                continue
            seen.add(key)
            lines.append(line)
        return lines

    @staticmethod
    def _title_words(title):
        return [w for w in song_match._norm(title).split() if len(w) >= 3]

    @staticmethod
    def _passes_gate(words, wnumber, haystack):
        """Billiger Vorfilter: gemeinsames Titelwort ODER passende Nummer.

        Ohne verwertbare Titelworte (sehr kurze Titel) faellt der Filter offen
        aus, damit nichts stumm verloren geht. Ein seltener Fuzzy-Treffer ohne
        gemeinsames Wort kann so entgehen — fuer eine Wuehlkisten-Heuristik mit
        Review-Dialog akzeptabel; die praezise Ceder-Suche bleibt der Fallback.
        """
        if not words:
            return True
        for w in words:
            if w in haystack:
                return True
        if wnumber and wnumber in haystack.replace(" ", ""):
            return True
        return False


class _ScoreItem(QTableWidgetItem):
    """Tabellen-Item, das nach einem hinterlegten Zahlenwert sortiert (nicht
    lexikalisch) — sonst stuende '100 %' vor '85 %'."""

    def __init__(self, score: int, text: str):
        super().__init__(text)
        self._score = score

    def __lt__(self, other):
        try:
            return self._score < other._score
        except AttributeError:
            return super().__lt__(other)


class _KrabbelkisteOptionsDialog(QDialog):
    """Kurze Aufklaerung + Auswahl „nur Ordner" / „rekursiv" vor dem Scan."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(_t('krabbel_btn_search'))
        self.setMinimumWidth(440)
        lay = QVBoxLayout(self)

        info = QLabel(_t('krabbel_info_text'))
        info.setWordWrap(True)
        lay.addWidget(info)

        self._grp = QButtonGroup(self)
        self._rb_folder = QRadioButton(_t('krabbel_opt_folder'))
        self._rb_recursive = QRadioButton(_t('krabbel_opt_recursive'))
        self._rb_folder.setChecked(True)
        self._grp.addButton(self._rb_folder)
        self._grp.addButton(self._rb_recursive)
        lay.addWidget(self._rb_folder)
        lay.addWidget(self._rb_recursive)

        box = QDialogButtonBox()
        ok = box.addButton(_t('krabbel_btn_choose'), QDialogButtonBox.AcceptRole)
        box.addButton(QDialogButtonBox.Cancel)
        ok.setDefault(True)
        box.accepted.connect(self.accept)
        box.rejected.connect(self.reject)
        lay.addWidget(box)

    def recursive(self) -> bool:
        return self._rb_recursive.isChecked()


class _KrabbelkisteResultDialog(QDialog):
    """Gegenueberstellung Song <-> gefundene Lyric-Datei mit Wahrscheinlichkeit.

    Alle Zeilen sind vorausgewaehlt (durchwinken), die Tabelle ist sortierbar
    (Score in Spalte 1) — so entscheidet der Nutzer selbst, wie weit er geht.
    """

    _COLS = ('krabbel_col_score', 'krabbel_col_song_title', 'krabbel_col_song_label',
             'krabbel_col_song_num', 'krabbel_col_found_file', 'krabbel_col_found_title',
             'krabbel_col_found_label', 'krabbel_col_found_num', 'krabbel_col_source',
             'krabbel_col_why')

    def __init__(self, results, parent=None):
        super().__init__(parent)
        self.setWindowTitle(_t('krabbel_result_title'))
        self.resize(1020, 500)
        self._results = results
        lay = QVBoxLayout(self)

        intro = QLabel(_t('krabbel_result_intro', count=len(results)))
        intro.setWordWrap(True)
        lay.addWidget(intro)

        self._table = QTableWidget()
        self._table.setColumnCount(len(self._COLS))
        self._table.setHorizontalHeaderLabels([_t(k) for k in self._COLS])
        self._table.verticalHeader().setVisible(False)
        self._table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._table.setSortingEnabled(False)
        self._table.setRowCount(len(results))
        for i, r in enumerate(results):
            m = r["match"]
            s_lname, s_num = song_match.split_label_number(r["song_label"])
            # Spalte 0: Score + Checkbox (vorausgewaehlt), sortiert nach Zahl.
            score_txt = f"{m.score} % ({song_match.confidence_word(m.score)})"
            it = _ScoreItem(m.score, score_txt)
            it.setFlags(it.flags() | Qt.ItemIsUserCheckable)
            it.setCheckState(Qt.Checked)
            it.setData(Qt.UserRole + 1, i)   # Index ins Ergebnis (sortstabil)
            self._table.setItem(i, 0, it)
            src = _t('krabbel_source_content') if m.source == 'content' \
                else _t('krabbel_source_filename')
            vals = [r["song_title"], s_lname, s_num, r["file_name"],
                    m.found_title, m.found_label, m.found_number, src,
                    ", ".join(m.reasons)]
            for col, v in enumerate(vals, start=1):
                self._table.setItem(i, col, QTableWidgetItem(str(v)))
        self._table.resizeColumnsToContents()
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.setSortingEnabled(True)
        self._table.sortItems(0, Qt.DescendingOrder)
        lay.addWidget(self._table, 1)

        btn_row = QHBoxLayout()
        btn_all = QPushButton(_t('krabbel_btn_all'))
        btn_none = QPushButton(_t('krabbel_btn_none'))
        btn_all.clicked.connect(lambda: self._set_all(Qt.Checked))
        btn_none.clicked.connect(lambda: self._set_all(Qt.Unchecked))
        btn_row.addWidget(btn_all)
        btn_row.addWidget(btn_none)
        btn_row.addStretch()
        lay.addLayout(btn_row)

        box = QDialogButtonBox()
        ok = box.addButton(_t('krabbel_btn_apply'), QDialogButtonBox.AcceptRole)
        box.addButton(QDialogButtonBox.Cancel)
        ok.setDefault(True)
        box.accepted.connect(self.accept)
        box.rejected.connect(self.reject)
        lay.addWidget(box)

    def _set_all(self, state):
        for row in range(self._table.rowCount()):
            it = self._table.item(row, 0)
            if it is not None:
                it.setCheckState(state)

    def selected(self):
        """Angehakte Ergebnis-Dicts (Reihenfolge egal)."""
        out = []
        for row in range(self._table.rowCount()):
            it = self._table.item(row, 0)
            if it is not None and it.checkState() == Qt.Checked:
                idx = it.data(Qt.UserRole + 1)
                if isinstance(idx, int) and 0 <= idx < len(self._results):
                    out.append(self._results[idx])
        return out


class _BeautifyDialog(QDialog):
    """BL-172: Auswahl-Dialog fuer den „Mach alles schoen"-Lauf.

    Zeigt alle Heilungsaktionen mit der Anzahl gefundener Faelle. Auffuellende
    Aktionen sind vorausgewaehlt; loeschende (destruktive) Aktionen bewusst
    nicht. Aktionen ohne Faelle sind deaktiviert."""

    def __init__(self, specs, parent=None, loop_preset_names=None):
        super().__init__(parent)
        self.setWindowTitle(_t('pot_beautify_title'))
        self.setMinimumWidth(440)
        self._specs = specs
        layout = QVBoxLayout(self)

        intro = QLabel(_t('pot_beautify_intro'))
        intro.setWordWrap(True)
        intro.setStyleSheet("font-size: 11px; color: #888;")
        layout.addWidget(intro)

        table = QTableWidget(len(specs), 2)
        table.setHorizontalHeaderLabels(
            [_t('pot_beautify_col_action'), _t('pot_beautify_col_count')])
        table.verticalHeader().setVisible(False)
        table.setEditTriggers(QTableWidget.NoEditTriggers)
        table.setSelectionMode(QTableWidget.NoSelection)
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        for row, spec in enumerate(specs):
            has_cases = spec['count'] > 0
            item = QTableWidgetItem(spec['label'])
            item.setFlags(Qt.ItemIsUserCheckable | (Qt.ItemIsEnabled if has_cases else Qt.NoItemFlags))
            # Auffuellend + Faelle vorhanden → an; destruktiv oder leer → aus
            checked = has_cases and not spec['destructive']
            item.setCheckState(Qt.Checked if checked else Qt.Unchecked)
            table.setItem(row, 0, item)
            cnt = QTableWidgetItem(str(spec['count']))
            cnt.setTextAlignment(Qt.AlignCenter)
            if not has_cases:
                cnt.setForeground(Qt.gray)
            table.setItem(row, 1, cnt)
        table.itemChanged.connect(lambda *_: None)  # Platzhalter, verhindert Read-only-Warnung
        self._table = table
        layout.addWidget(table)

        # intern#207: Loop-Finder-Preset fuer „Loops fehlen“
        self._loop_preset_combo = None
        if loop_preset_names and any(
                sp['key'] == 'loop' and sp['count'] > 0 for sp in specs):
            row = QHBoxLayout()
            row.addWidget(QLabel(_t('pot_bf_loop_preset')))
            self._loop_preset_combo = QComboBox()
            self._loop_preset_combo.addItems(loop_preset_names)
            self._loop_preset_combo.setToolTip(_t('pot_loop_preset_tooltip'))
            row.addWidget(self._loop_preset_combo, 1)
            layout.addLayout(row)

        btns = QDialogButtonBox()
        self._run_btn = btns.addButton(_t('pot_beautify_run'), QDialogButtonBox.AcceptRole)
        btns.addButton(QDialogButtonBox.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def loop_preset_name(self):
        """Gewaehltes Loop-Finder-Preset oder None (keine Combo)."""
        if self._loop_preset_combo is None:
            return None
        return self._loop_preset_combo.currentText()

    def selected_keys(self):
        keys = set()
        for row, spec in enumerate(self._specs):
            item = self._table.item(row, 0)
            if item is not None and item.checkState() == Qt.Checked:
                keys.add(spec['key'])
        return keys


class _BeautifyProgressDialog(QDialog):
    """BL-172: Fortschrittsanzeige des „Mach alles schoen"-Laufs.

    Bewusst nicht-linear: ein Busy-Balken plus eine ToDo-Checkliste, in der der
    aktuelle Schritt markiert wird. Keine Zeitschaetzung."""

    def __init__(self, step_labels, on_cancel, parent=None):
        super().__init__(parent)
        self.setWindowTitle(_t('pot_beautify_progress_title'))
        self.setMinimumWidth(420)
        self._labels = list(step_labels)
        self._status = ['pending'] * len(step_labels)  # pending | running | done | empty
        self._detail = ''
        self._on_cancel = on_cancel
        layout = QVBoxLayout(self)

        self._list_lbl = QLabel("")
        self._list_lbl.setTextFormat(Qt.RichText)
        layout.addWidget(self._list_lbl)

        self._detail_lbl = QLabel("")
        self._detail_lbl.setStyleSheet("font-size: 11px; color: #888;")
        self._detail_lbl.setWordWrap(True)
        layout.addWidget(self._detail_lbl)

        self._bar = QProgressBar()
        self._bar.setRange(0, 0)   # indeterminate (busy)
        layout.addWidget(self._bar)

        btns = QDialogButtonBox(QDialogButtonBox.Cancel)
        btns.rejected.connect(self._cancel)
        layout.addWidget(btns)
        self._render()

    def _cancel(self):
        if self._on_cancel:
            self._on_cancel()

    def _render(self):
        icons = {'pending': '⏳', 'running': '▶', 'done': '✓', 'empty': '–'}
        lines = []
        for lbl, st in zip(self._labels, self._status):
            mark = icons.get(st, '⏳')
            if st == 'running':
                lines.append(f"<b>{mark} {lbl}</b>")
            elif st in ('done', 'empty'):
                lines.append(f'<span style="color:#888;">{mark} {lbl}</span>')
            else:
                lines.append(f"{mark} {lbl}")
        self._list_lbl.setText("<br>".join(lines))
        self._detail_lbl.setText(self._detail)
        QApplication.processEvents()

    def set_running(self, i):
        if 0 <= i < len(self._status):
            self._status[i] = 'running'
        self._detail = ''
        self._render()

    def set_done(self, i, empty=False):
        if 0 <= i < len(self._status):
            self._status[i] = 'empty' if empty else 'done'
        self._detail = ''
        self._render()

    def set_detail(self, text):
        self._detail = text
        self._render()


class PotentialWidget(QWidget):
    """Datenqualitaets-Dashboard: Zeigt Optimierungspotential in der Songdatenbank."""

    # Callbacks: Navigation + externe Ressourcen
    on_navigate_song = None       # fn(song_id)
    on_navigate_sync = None       # fn(song_id) → Lyric-Widget + Sync-Button ansteuern
    on_navigate_beatsnap = None   # fn(song_id)
    on_navigate_location = None   # fn(location_id)
    on_play_song = None           # fn(song_id) → laden + abspielen
    on_stop_song = None           # fn() → stoppen
    on_bulk_done = None           # fn() → einmaliger Hauptfenster-Refresh nach Bulk
    on_songs_deleted = None       # fn(ids) → Hauptfenster raeumt nach Massen-Loeschen auf
    get_running_song = None       # fn() → Song, der laeuft oder pausiert, sonst None
    paths = None                  # PathManager (von aussen setzen)

    # Check-Definitionen: (check_type, translation_key, description_key)
    _CHECKS = [
        ('singing_no_lyrics', 'pot_singing_no_lyrics', 'pot_desc_singing_no_lyrics'),
        # Cue-Sheet-Suche auf ceder.net. Der Tab laesst sich ueber
        # network/ceder_lookup_enabled ausblenden — bis die Erlaubnis von
        # Vic Ceder vorliegt, soll er nicht in einem Release auftauchen.
        ('singing_no_lyrics_fill', 'pot_lyrics_fill', 'pot_desc_lyrics_fill'),
        ('singing_no_song_points', 'pot_singing_no_song_points', 'pot_desc_singing_no_song_points'),
        ('singing_no_sync_points', 'pot_singing_no_sync_points', 'pot_desc_singing_no_sync_points'),
        ('pattern_no_loop', 'pot_pattern_no_loop', 'pot_desc_pattern_no_loop'),
        ('loop_no_beatsnap', 'pot_loop_no_beatsnap', 'pot_desc_loop_no_beatsnap'),
        ('location_no_history', 'pot_location_no_history', 'pot_desc_location_no_history'),
        ('history_orphaned', 'pot_history_orphaned', 'pot_desc_history_orphaned'),
        ('no_mp3', 'pot_no_mp3', 'pot_desc_no_mp3'),
        ('bad_mp3', 'pot_bad_mp3', 'pot_desc_bad_mp3'),
        ('no_quality', 'pot_no_quality', 'pot_desc_no_quality'),
        ('no_err', 'pot_no_err', 'pot_desc_no_err'),
        ('no_genre', 'pot_no_genre', 'pot_desc_no_genre'),
    ]

    def __init__(self, db, paths=None, settings=None, parent=None):
        super().__init__(parent)
        self.db = db
        self.paths = paths          # fuer Lyrics-Ordner und config/
        self._settings = settings   # fuer den Ceder-Schalter
        self._ceder_worker = None
        self._ceder_dl_worker = None
        self._krabbel_worker = None
        self._current_check = None
        self._current_data = []  # [(entity_id, display_name, description), ...]
        self._bulk_worker = None
        self._bulk_delete_worker = None   # BL-148: Massen-Loesch-Worker
        self._bulk_delete_ids = []        # IDs des laufenden Massen-Loeschens
        self._timing_worker = None
        self._progress_dlg = None
        self._no_mp3_cached_count = None   # None = noch nicht geprueft (Lazy)
        self._bad_mp3_cached_count = None  # None = noch nicht geprueft (Lazy)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(0)

        self._tabs = QTabWidget()
        self._tab_widgets = {}   # check_type → widget-dict
        self._tab_indices = {}   # check_type → tab index

        # --- Alle Check-Tab-Widgets vorab erstellen (Reihenfolge unabhaengig
        #     von der Erstellung — sie wird unten beim addTab festgelegt) ---
        check_defs = {ct: (label_key, desc_key) for ct, label_key, desc_key in self._CHECKS}
        check_tabs = {}   # check_type → (widget, tw)
        for check_type, label_key, desc_key in self._CHECKS:
            tab_w, tw = self._make_check_tab(check_type, desc_key)
            check_tabs[check_type] = tab_w
            self._tab_widgets[check_type] = tw

        # --- Werkzeug-Tab-Widgets vorab erstellen ---
        start_w = self._build_start_tab()
        qe_w = self._build_qe_tab()
        lo_w = self._build_loop_optimize_tab()
        nobpm_w = self._build_no_bpm_tab()
        nosstart_w = self._build_no_singing_start_tab()
        meta_w = self._build_meta_tab()
        import_w = self._build_songdata_import_tab()
        bulk_w = self._build_bulk_delete_tab()

        # --- Hilfsfunktion: Check-Tab an aktueller Position einfuegen ---
        def _add_check(ct):
            idx = self._tabs.addTab(check_tabs[ct], _t(check_defs[ct][0]))
            self._tab_indices[ct] = idx
            return idx

        # --- Reihenfolge: Uebersicht + 4 Workflow-Gruppen (BL: Potential-Struktur) ---
        # Start / Uebersicht ganz vorne
        self._start_idx = self._tabs.addTab(start_w, _t('pot_tab_start'))

        # ① Basis — gilt fuer jeden Song (Patter UND Singing), Grundlage fuer alles
        _add_check('no_mp3')
        _add_check('bad_mp3')
        self._no_bpm_idx = self._tabs.addTab(nobpm_w, _t('pot_no_bpm'))
        _add_check('no_genre')
        _add_check('no_quality')
        _add_check('no_err')
        self._tabs.addTab(qe_w, _t('pot_qe_filler'))
        self._tab_indices['qe_filler'] = self._tabs.count() - 1
        self._meta_idx = self._tabs.addTab(meta_w, _t('pot_tab_metadata'))

        # ② Patter-Kette: Loop ▸ BeatSnap ▸ Loop optimieren
        _add_check('pattern_no_loop')
        _add_check('loop_no_beatsnap')
        self._loop_opt_idx = self._tabs.addTab(lo_w, _t('pot_loop_optimize'))

        # ③ Singing-Kette: Lyrics ▸ Liedpunkte ▸ Songanfang ▸ SyncPunkte
        _add_check('singing_no_lyrics')
        if self._ceder_enabled():
            _add_check('singing_no_lyrics_fill')
        _add_check('singing_no_song_points')
        self._no_sstart_idx = self._tabs.addTab(nosstart_w, _t('pot_no_sstart'))
        _add_check('singing_no_sync_points')

        # ④ Wartung
        _add_check('location_no_history')
        _add_check('history_orphaned')
        self._import_idx = self._tabs.addTab(import_w, _t('sdio_io_tab'))
        self._bulk_idx = self._tabs.addTab(bulk_w, _t('pot_bulk_delete'))

        self._tabs.currentChanged.connect(self._on_tab_changed)
        # WICHTIG: Der Skin stylt QTabBar::tab → die Tableiste ist im
        # Stylesheet-Modus. Dann MUSS die Breite des ::scroller (Container der
        # beiden ‹ ›-Scroll-Buttons) gesetzt werden, sonst quetscht Qt die
        # Pfeile in einen 0-Pixel-Bereich (nicht klickbar). NICHT die einzelnen
        # QToolButton per min-width stylen — das verdraengt nur den rechten Pfeil.
        self._tabs.tabBar().setStyleSheet("QTabBar::scroller { width: 48px; }")
        # Sticky Home-Button (nur Haus-Symbol) ganz vorne — Corner-Widget
        # scrollt nicht mit und bleibt so immer erreichbar
        home_btn = QPushButton(_t('pot_home_btn'))
        home_btn.setToolTip(_t('pot_home_btn_tip'))
        home_btn.setStyleSheet(
            "QPushButton { padding: 4px 10px; font-size: 16px; font-weight: bold; }")
        home_btn.clicked.connect(
            lambda checked=False: self._tabs.setCurrentIndex(self._start_idx))
        self._tabs.setCornerWidget(home_btn, Qt.TopLeftCorner)
        layout.addWidget(self._tabs)
        # Beim Oeffnen die Uebersicht zeigen; Badges via refresh() fuellen
        self._current_check = None
        self._tabs.setCurrentIndex(self._start_idx)
        QTimer.singleShot(0, self.refresh)

    # ---- Start / Uebersicht (Cockpit) ----

    def _build_start_tab(self):
        """Uebersicht mit Buttons zu allen Reitern, nach Workflow gruppiert.
        Die beiden Abhaengigkeitsketten (Patter, Singing) werden mit Pfeilen
        zwischen den Schritten dargestellt, damit die sinnvolle Reihenfolge
        sichtbar ist. Buttons tragen ein Badge mit der Anzahl offener Punkte;
        teure Pruefungen (MP3-Dateien) zeigen '?' bis sie beim Oeffnen des
        Reiters tatsaechlich ermittelt werden."""
        self._start_buttons = {}   # key → QPushButton
        self._start_labels = {}    # key → Basis-Label (ohne Badge)
        self._start_flows = []     # alle _FlowWidget-Zeilen (fuer Relayout nach Badge-Update)

        outer = QWidget()
        root = QVBoxLayout(outer)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(8)

        title = QLabel(_t('pot_start_title'))
        title.setStyleSheet("font-size: 15px; font-weight: bold;")
        root.addWidget(title)
        intro = QLabel(_t('pot_start_intro'))
        intro.setWordWrap(True)
        intro.setStyleSheet("font-size: 11px; color: #888;")
        root.addWidget(intro)

        # ① Basis
        root.addWidget(self._start_group_label('pot_start_group_basis'))
        basis = _FlowWidget(h_spacing=8, v_spacing=8)
        for key, label_key in [
                ('no_mp3', 'pot_no_mp3'), ('bad_mp3', 'pot_bad_mp3'),
                ('no_bpm', 'pot_no_bpm'),
                ('no_genre', 'pot_no_genre'), ('no_quality', 'pot_no_quality'),
                ('no_err', 'pot_no_err'), ('qe_filler', 'pot_qe_filler'),
                ('meta', 'pot_tab_metadata')]:
            basis.addWidget(self._start_button(key, label_key))
        root.addWidget(basis)
        self._start_flows.append(basis)

        # ② Patter-Kette (mit Pfeilen)
        root.addWidget(self._start_group_label('pot_start_group_patter'))
        root.addWidget(self._start_chain([
            ('pattern_no_loop', 'pot_pattern_no_loop'),
            ('loop_no_beatsnap', 'pot_loop_no_beatsnap'),
            ('loop_optimize', 'pot_loop_optimize')]))

        # ③ Singing-Kette (mit Pfeilen)
        root.addWidget(self._start_group_label('pot_start_group_singing'))
        root.addWidget(self._start_chain([
            ('singing_no_lyrics', 'pot_singing_no_lyrics'),
            ('singing_no_song_points', 'pot_singing_no_song_points'),
            ('no_sstart', 'pot_no_sstart'),
            ('singing_no_sync_points', 'pot_singing_no_sync_points')]))

        # ④ Wartung
        root.addWidget(self._start_group_label('pot_start_group_maintenance'))
        maint = _FlowWidget(h_spacing=8, v_spacing=8)
        for key, label_key in [
                ('location_no_history', 'pot_location_no_history'),
                ('history_orphaned', 'pot_history_orphaned'),
                ('bulk', 'pot_bulk_delete')]:
            maint.addWidget(self._start_button(key, label_key))
        root.addWidget(maint)
        self._start_flows.append(maint)

        # BL-172: „Mach alles schoen" — fuehrt die Heilungsfunktionen verkettet aus
        root.addSpacing(10)
        beautify_btn = QPushButton(_t('pot_beautify_btn'))
        beautify_btn.setMinimumHeight(46)
        beautify_btn.setStyleSheet(
            "QPushButton { padding: 8px 16px; font-size: 14px; font-weight: bold; }")
        beautify_btn.setToolTip(_t('pot_beautify_intro'))
        beautify_btn.clicked.connect(self._on_beautify_clicked)
        root.addWidget(beautify_btn)

        root.addStretch()

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(outer)
        scroll.setFrameShape(QScrollArea.NoFrame)
        # Kein horizontales Scrollen → Inhalt muss umbrechen statt abzuschneiden
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        return scroll

    def _start_group_label(self, key):
        lbl = QLabel(_t(key))
        lbl.setStyleSheet("font-size: 12px; font-weight: bold; margin-top: 6px;")
        return lbl

    def _start_button(self, key, label_key):
        base = _t(label_key)
        self._start_labels[key] = base
        btn = QPushButton(base)
        btn.setMinimumHeight(38)
        btn.setStyleSheet("QPushButton { padding: 6px 12px; text-align: left; }")
        btn.clicked.connect(lambda checked=False, k=key: self._start_goto(k))
        self._start_buttons[key] = btn
        return btn

    def _start_chain(self, items):
        """Button-Kette mit Pfeilen dazwischen. Als Flow gebaut, damit sie
        beim Verkleinern des Fensters genauso umbricht wie die anderen
        Gruppen (eine feste QHBoxLayout-Reihe wuerde die ganze Seite auf
        ihre Mindestbreite aufblasen und den Umbruch verhindern)."""
        flow = _FlowWidget(h_spacing=8, v_spacing=8)
        for i, (key, label_key) in enumerate(items):
            if i > 0:
                arrow = QLabel("→")
                arrow.setAlignment(Qt.AlignCenter)
                arrow.setMinimumHeight(38)
                arrow.setMinimumWidth(24)
                arrow.setStyleSheet(
                    "font-size: 22px; font-weight: bold; color: #3a9a6a;")
                flow.addWidget(arrow)
            flow.addWidget(self._start_button(key, label_key))
        self._start_flows.append(flow)
        return flow

    def _nav_target(self, key):
        """Aktueller Tab-Index fuer einen Start-Button-Key (Indizes sind
        beweglich → immer frisch aufloesen, nie beim Bau festhalten)."""
        if key == 'no_bpm':
            return getattr(self, '_no_bpm_idx', -1)
        if key == 'no_sstart':
            return getattr(self, '_no_sstart_idx', -1)
        if key == 'loop_optimize':
            return getattr(self, '_loop_opt_idx', -1)
        if key == 'meta':
            return getattr(self, '_meta_idx', -1)
        if key == 'bulk':
            return getattr(self, '_bulk_idx', -1)
        return self._tab_indices.get(key, -1)

    def _start_goto(self, key):
        idx = self._nav_target(key)
        if idx is not None and idx >= 0:
            self._tabs.setCurrentIndex(idx)

    def _update_start_badge(self, key, count):
        """Setzt das Badge eines Start-Buttons. count=None → '?' (noch nicht
        ermittelt), 0 → Haken (erledigt), sonst die Zahl."""
        btn = getattr(self, '_start_buttons', {}).get(key)
        if btn is None:
            return
        base = self._start_labels.get(key, btn.text())
        if count is None:
            btn.setText(f"{base}   [ ? ]")
        elif count:
            btn.setText(f"{base}   ({count})")
        else:
            btn.setText(f"{base}   ✓")

    def _make_check_tab(self, check_type, desc_key):
        """Erstellt einen Standard-Check-Tab mit Beschreibung, Tabelle und Aktionsbuttons."""
        w = QWidget()
        tab_layout = QVBoxLayout(w)
        tab_layout.setContentsMargins(4, 6, 4, 4)
        tab_layout.setSpacing(4)

        desc = QLabel(_t(desc_key))
        desc.setWordWrap(True)
        desc.setStyleSheet("font-size: 11px; color: #888;")
        tab_layout.addWidget(desc)

        table = QTableWidget()
        table.setEditTriggers(QTableWidget.NoEditTriggers)
        table.setSelectionBehavior(QTableWidget.SelectRows)
        table.setAlternatingRowColors(True)
        table.verticalHeader().setVisible(False)
        table.setColumnCount(2)
        table.setHorizontalHeaderLabels([_t('pot_col_name'), _t('pot_col_problem')])
        table.horizontalHeader().setStretchLastSection(True)
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        tab_layout.addWidget(table, 1)

        action_layout = QHBoxLayout()
        action_layout.setSpacing(4)

        btn_ignore = QPushButton(_t('pot_ignore'))
        btn_ignore.setEnabled(False)
        btn_ignore.setVisible(False)
        action_layout.addWidget(btn_ignore)

        btn_cleanup = QPushButton(_t('pot_cleanup'))
        btn_cleanup.setEnabled(False)
        btn_cleanup.setVisible(False)
        action_layout.addWidget(btn_cleanup)

        # Massenlauf nur fuer die markierten Zeilen (Text setzt _load_check)
        btn_fix_sel = QPushButton("")
        btn_fix_sel.setEnabled(False)
        btn_fix_sel.setVisible(False)
        action_layout.addWidget(btn_fix_sel)

        btn_fix_all = QPushButton("")
        btn_fix_all.setEnabled(False)
        btn_fix_all.setVisible(False)
        action_layout.addWidget(btn_fix_all)

        # Komplettlauf ueber ALLE Singing Calls mit Lyrics — auch die, die nicht
        # in dieser Liste stehen, weil sie schon Sync-Punkte haben.
        btn_fix_every = QPushButton("")
        btn_fix_every.setEnabled(False)
        btn_fix_every.setVisible(False)
        action_layout.addWidget(btn_fix_every)

        action_layout.addStretch()
        tab_layout.addLayout(action_layout)

        tw = {
            'table': table,
            'btn_ignore': btn_ignore,
            'btn_cleanup': btn_cleanup,
            'btn_fix_sel': btn_fix_sel,
            'btn_fix_all': btn_fix_all,
            'btn_fix_every': btn_fix_every,
            'data': [],
        }

        table.itemSelectionChanged.connect(
            lambda ct=check_type, t=tw: self._on_selection_changed(ct, t))
        table.doubleClicked.connect(
            lambda idx, ct=check_type, t=tw: self._on_double_click(ct, t, idx))
        btn_ignore.clicked.connect(
            lambda checked=False, ct=check_type, t=tw: self._on_ignore(ct, t))
        btn_cleanup.clicked.connect(
            lambda checked=False, ct=check_type: self._on_cleanup(ct))
        btn_fix_sel.clicked.connect(
            lambda checked=False, ct=check_type, t=tw: self._on_fix_selected(ct, t))
        btn_fix_all.clicked.connect(
            lambda checked=False, ct=check_type: self._on_fix_all(ct))
        btn_fix_every.clicked.connect(
            lambda checked=False: self._syncpts_start_every())

        return w, tw

    def _build_qe_tab(self):
        """Erstellt den 'Quality + ERR Füllen'-Tab."""
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        # Beschreibung
        desc = QLabel(_t('pot_qe_desc'))
        desc.setWordWrap(True)
        desc.setStyleSheet("font-size: 11px; color: #888;")
        layout.addWidget(desc)

        # Zähler + Navigation
        nav_row = QHBoxLayout()
        self._qe_btn_prev = QPushButton(_t("pot_qe_btn_prev"))
        self._qe_btn_prev.setFixedHeight(30)
        self._qe_btn_prev.setMinimumWidth(80)
        self._qe_lbl_counter = QLabel("")
        self._qe_lbl_counter.setAlignment(Qt.AlignCenter)
        self._qe_btn_next = QPushButton(_t("pot_qe_btn_next"))
        self._qe_btn_next.setFixedHeight(30)
        self._qe_btn_next.setMinimumWidth(80)
        self._qe_btn_prev.clicked.connect(self._qe_prev)
        self._qe_btn_next.clicked.connect(self._qe_next)
        nav_row.addWidget(self._qe_btn_prev)
        nav_row.addWidget(self._qe_lbl_counter, 1)
        nav_row.addWidget(self._qe_btn_next)
        layout.addLayout(nav_row)

        # Song-Info: Titel + Play/Stop-Button
        title_row = QHBoxLayout()
        self._qe_lbl_title = QLabel("")
        self._qe_lbl_title.setWordWrap(True)
        self._qe_lbl_title.setStyleSheet("font-size: 13px; font-weight: bold;")
        self._qe_btn_play = QPushButton(_t("pot_qe_btn_preview"))
        self._qe_btn_play.setFixedHeight(30)
        self._qe_btn_play.setMinimumWidth(100)
        self._qe_btn_play.clicked.connect(self._qe_toggle_play)
        self._qe_preview_id = None   # song_id des aktuell vorgehörten Songs
        title_row.addWidget(self._qe_lbl_title, 1)
        title_row.addWidget(self._qe_btn_play)
        layout.addLayout(title_row)

        self._qe_lbl_label = QLabel("")
        self._qe_lbl_label.setStyleSheet("font-size: 11px; color: #888;")
        layout.addWidget(self._qe_lbl_label)

        # Trennlinie
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setFrameShadow(QFrame.Sunken)
        layout.addWidget(line)

        # Quality-Zeile
        self._qe_quality_row = QWidget()
        q_row_layout = QHBoxLayout(self._qe_quality_row)
        q_row_layout.setContentsMargins(0, 0, 0, 0)
        q_row_layout.setSpacing(3)
        q_row_layout.addWidget(QLabel(_t('pot_qe_quality_row')))
        self._qe_btn_quality = []
        for v in range(1, 11):
            btn = QPushButton(str(v))
            btn.setFixedHeight(30)
            btn.setMinimumWidth(30)
            btn.setStyleSheet("QPushButton { padding: 0px 6px; }")
            btn.clicked.connect(lambda checked=False, val=v: self._qe_set_quality(val))
            q_row_layout.addWidget(btn)
            self._qe_btn_quality.append(btn)
        q_row_layout.addStretch()
        layout.addWidget(self._qe_quality_row)

        # ERR-Zeile
        self._qe_err_row = QWidget()
        e_row_layout = QHBoxLayout(self._qe_err_row)
        e_row_layout.setContentsMargins(0, 0, 0, 0)
        e_row_layout.setSpacing(6)
        e_row_layout.addWidget(QLabel(_t('pot_qe_err_row')))
        self._qe_btn_err = []
        _ERR_COLORS = {1: "#d9441c", 2: "#c8901a", 3: "#2e8b3e", 4: "#2a5bbf"}
        for v in range(1, 5):
            btn = QPushButton(str(v))
            btn.setFixedHeight(30)
            btn.setMinimumWidth(44)
            btn.setStyleSheet(
                f"QPushButton {{ background: {_ERR_COLORS[v]}; color: white; "
                f"border-radius: 3px; padding: 0px 8px; }}"
            )
            btn.clicked.connect(lambda checked=False, val=v: self._qe_set_err(val))
            e_row_layout.addWidget(btn)
            self._qe_btn_err.append(btn)
        e_row_layout.addStretch()
        layout.addWidget(self._qe_err_row)

        layout.addStretch()

        # Interner Zustand
        self._qe_songs = []      # [(id, title, filename, quality, err), ...]
        self._qe_idx = 0

        return w

    def _qe_load(self):
        """Lädt Songs für den QE-Filler und zeigt den aktuellen Song."""
        cur_id = self._qe_songs[self._qe_idx][0] if self._qe_songs else None
        self._qe_songs = self.db.get_songs_for_qe_filler()
        if not self._qe_songs:
            self._qe_lbl_counter.setText(_t('pot_qe_none'))
            self._qe_lbl_title.setText("")
            self._qe_lbl_label.setText("")
            self._qe_quality_row.hide()
            self._qe_err_row.hide()
            self._qe_btn_prev.setEnabled(False)
            self._qe_btn_next.setEnabled(False)
            return
        # Nach Reload versuchen, beim gleichen Song zu bleiben
        if cur_id is not None:
            for i, row in enumerate(self._qe_songs):
                if row[0] == cur_id:
                    self._qe_idx = i
                    break
            else:
                self._qe_idx = 0
        self._qe_idx = max(0, min(self._qe_idx, len(self._qe_songs) - 1))
        self._qe_show_current()

    def _qe_show_current(self):
        """Zeigt den aktuellen Song-Datensatz mit den passenden Buttons."""
        if not self._qe_songs:
            return
        n = len(self._qe_songs)
        sid, title, filename, quality, err, is_pattern, is_singing = self._qe_songs[self._qe_idx]
        self._qe_lbl_counter.setText(_t('pot_qe_counter', pos=self._qe_idx + 1, total=n))
        self._qe_lbl_title.setText(title or filename)

        # Label-Feld aus DB laden
        song = self.db.get_by_id(sid)
        label_txt = (song.label or "") if song else ""
        q_txt = str(quality) if quality else "—"
        e_txt = str(err) if err else "—"
        # Patter / Singing Kennzeichnung
        if is_pattern and is_singing:
            type_txt = "Patter + Singing"
        elif is_pattern:
            type_txt = "Patter"
        elif is_singing:
            type_txt = "Singing"
        else:
            type_txt = "Other"
        self._qe_lbl_label.setText(
            f"{type_txt}   |   Label: {label_txt or '—'}   |   Quality: {q_txt}   |   ERR: {e_txt}"
        )

        # Play-Button: zeigt Stopp wenn dieser Song gerade vorgehört wird
        is_previewing = (self._qe_preview_id == sid)
        self._qe_btn_play.setText(_t("pot_qe_btn_stop") if is_previewing else _t("pot_qe_btn_preview"))

        # Quality-Zeile nur anzeigen wenn quality=0
        self._qe_quality_row.setVisible(quality == 0)
        for i, btn in enumerate(self._qe_btn_quality):
            val = i + 1
            is_current = (val == quality)
            btn.setStyleSheet(
                "QPushButton { font-weight: bold; border: 2px solid #fff; }" if is_current
                else ""
            )

        # ERR-Zeile nur anzeigen wenn err=0
        self._qe_err_row.setVisible(err == 0)
        _ERR_COLORS = {1: "#d9441c", 2: "#c8901a", 3: "#2e8b3e", 4: "#2a5bbf"}
        for i, btn in enumerate(self._qe_btn_err):
            val = i + 1
            is_current = (val == err)
            border = "border: 3px solid white;" if is_current else ""
            btn.setStyleSheet(
                f"QPushButton {{ background: {_ERR_COLORS[val]}; color: white; "
                f"border-radius: 3px; {border} }}"
            )

        self._qe_btn_prev.setEnabled(self._qe_idx > 0)
        self._qe_btn_next.setEnabled(self._qe_idx < n - 1)

    def _qe_set_quality(self, val):
        if not self._qe_songs:
            return
        sid, title, filename, quality, err, isp, iss = self._qe_songs[self._qe_idx]
        self.db.update_song_simple_field(sid, 'quality', val)
        self._qe_songs[self._qe_idx] = (sid, title, filename, val, err, isp, iss)
        self._qe_advance_if_done()

    def _qe_set_err(self, val):
        if not self._qe_songs:
            return
        sid, title, filename, quality, err, isp, iss = self._qe_songs[self._qe_idx]
        self.db.update_song_simple_field(sid, 'err', val)
        self._qe_songs[self._qe_idx] = (sid, title, filename, quality, val, isp, iss)
        self._qe_advance_if_done()

    def _qe_advance_if_done(self):
        """Wenn Quality UND ERR jetzt gesetzt → nächsten Song zeigen und Liste neu laden."""
        sid, title, filename, quality, err, isp, iss = self._qe_songs[self._qe_idx]
        if quality > 0 and err > 0:
            # Song ist vollständig — aus lokaler Liste entfernen und Badges updaten
            self._qe_songs.pop(self._qe_idx)
            if self._qe_idx >= len(self._qe_songs):
                self._qe_idx = max(0, len(self._qe_songs) - 1)
            # Tab-Badge aktualisieren
            qe_count = len(self._qe_songs)
            qe_idx = self._tab_indices.get('qe_filler')
            if qe_idx is not None:
                base = _t('pot_qe_filler')
                self._tabs.setTabText(qe_idx, f"{base} ({qe_count})" if qe_count else base)
            if self._qe_songs:
                self._qe_show_current()
            else:
                self._qe_load()
        else:
            self._qe_show_current()

    def _qe_toggle_play(self):
        if not self._qe_songs:
            return
        sid = self._qe_songs[self._qe_idx][0]
        if self._qe_preview_id == sid:
            # Läuft gerade → stoppen
            self._qe_preview_id = None
            if self.on_stop_song:
                self.on_stop_song()
        else:
            # Starten
            self._qe_preview_id = sid
            if self.on_play_song:
                self.on_play_song(sid)
        self._qe_show_current()

    def _qe_prev(self):
        if self._qe_idx > 0:
            self._qe_idx -= 1
            self._qe_show_current()

    def _qe_next(self):
        if self._qe_idx < len(self._qe_songs) - 1:
            self._qe_idx += 1
            self._qe_show_current()

    def _build_meta_tab(self):
        """Erstellt den 'Metadaten füllen'-Tab (BL-114)."""
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        desc = QLabel(_t('pot_meta_desc'))
        desc.setWordWrap(True)
        layout.addWidget(desc)

        # Buttons im FlowWidget — umbrechen automatisch in naechste Zeile
        flow = _FlowWidget(h_spacing=6, v_spacing=6)

        self._btn_meta_csv = QPushButton(_t('pot_meta_csv'))
        self._btn_meta_csv.clicked.connect(self._on_meta_csv)
        flow.addWidget(self._btn_meta_csv)

        self._btn_meta_export = QPushButton(_t('pot_meta_export'))
        self._btn_meta_export.clicked.connect(self._on_meta_export)
        flow.addWidget(self._btn_meta_export)

        self._btn_meta_prompt = QPushButton(_t('pot_meta_prompt'))
        self._btn_meta_prompt.clicked.connect(self._on_meta_prompt)
        flow.addWidget(self._btn_meta_prompt)

        self._btn_meta_import = QPushButton(_t('pot_meta_import'))
        self._btn_meta_import.clicked.connect(self._on_meta_import)
        flow.addWidget(self._btn_meta_import)

        layout.addWidget(flow)

        self._lbl_meta_stats = QLabel("")
        self._lbl_meta_stats.setWordWrap(True)
        self._lbl_meta_stats.setStyleSheet("font-size: 11px; color: #888;")
        layout.addWidget(self._lbl_meta_stats)

        layout.addStretch()
        return w

    # ---- BL-206: Songdaten-Export/-Import (JSON) ----

    def _build_songdata_import_tab(self):
        """Export und Import der Songdaten-JSON (BL-206).

        Der Import kann bestehende Daten ueberschreiben und gehoert daher an
        eine ruhige, absichtsvolle Stelle (hier statt im Listen-Widget). Es
        werden NIE neue Songs angelegt; die Zuordnung laeuft ueber den Songnamen,
        vor dem Schreiben steht ein Feld-Diff mit Vetorecht. Der Export hier
        umfasst ALLE Songs (das Listen-Widget exportiert die gefilterte Liste)."""
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        # Export (alle Songs)
        exp_desc = QLabel(_t('sdio_export_tab_desc'))
        exp_desc.setWordWrap(True)
        layout.addWidget(exp_desc)

        btn_exp = QPushButton(_t('sdio_export_all_btn'))
        btn_exp.setToolTip(_t('sdio_export_all_btn_tip'))
        btn_exp.clicked.connect(self._on_songdata_export)
        exp_row = QHBoxLayout()
        exp_row.addWidget(btn_exp)
        exp_row.addStretch()
        layout.addLayout(exp_row)

        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setFrameShadow(QFrame.Sunken)
        layout.addWidget(sep)

        # Import
        desc = QLabel(_t('sdio_import_tab_desc'))
        desc.setWordWrap(True)
        layout.addWidget(desc)

        btn = QPushButton(_t('sdio_import_btn'))
        btn.setToolTip(_t('sdio_import_btn_tip'))
        btn.clicked.connect(self._on_songdata_import)
        row = QHBoxLayout()
        row.addWidget(btn)
        row.addStretch()
        layout.addLayout(row)

        layout.addStretch()
        return w

    def _on_songdata_export(self):
        """Exportiert ALLE Songs als JSON (Feld-Auswahl im Dialog)."""
        song_data_io.export_songs_interactive(self, self.db, self.db.get_all())

    def _on_songdata_import(self):
        changed = song_data_io.import_songs_interactive(self, self.db)
        if changed:
            # Aenderungen koennen Filter/Statistiken beruehren -> Hauptfenster
            # einmalig auffrischen lassen (wie nach Bulk-Aktionen).
            if self.on_bulk_done:
                self.on_bulk_done()
            self.refresh()

    # ---- BL-148: Massen-Loeschen ----

    def _build_bulk_delete_tab(self):
        """Reiter zum Loeschen grosser Songmengen (z.B. Fehl-Import).

        Mehrfach sortierbare Tabelle + Shift/Strg-Mehrfachauswahl. Die Liste
        wird erst beim Oeffnen des Reiters geladen (Lazy, Performance)."""
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(4, 6, 4, 4)
        layout.setSpacing(4)

        desc = QLabel(_t('pot_bulk_desc'))
        desc.setWordWrap(True)
        desc.setStyleSheet("font-size: 11px; color: #888;")
        layout.addWidget(desc)

        table = QTableWidget()
        table.setEditTriggers(QTableWidget.NoEditTriggers)
        table.setSelectionBehavior(QTableWidget.SelectRows)
        # Shift+Klick = Bereich, Strg+Klick = Einzelzeilen, Strg+A = alles
        table.setSelectionMode(QTableWidget.ExtendedSelection)
        table.setAlternatingRowColors(True)
        table.verticalHeader().setVisible(False)
        table.setSortingEnabled(True)
        table.setColumnCount(7)
        table.setHorizontalHeaderLabels([
            _t('pot_bulk_col_type'), _t('pot_bulk_col_added'),
            _t('pot_bulk_col_title'), _t('pot_bulk_col_label'),
            _t('pot_bulk_col_genre'), _t('pot_bulk_col_err'),
            _t('pot_bulk_col_quality')])
        table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        table.itemSelectionChanged.connect(self._on_bulk_selection_changed)
        layout.addWidget(table, 1)
        self._bulk_table = table

        action_row = QHBoxLayout()
        self._bulk_lbl_count = QLabel("")
        self._bulk_lbl_count.setStyleSheet("font-size: 11px; color: #888;")
        action_row.addWidget(self._bulk_lbl_count)
        action_row.addStretch()
        self._bulk_btn_delete = QPushButton(_t('pot_bulk_delete_btn'))
        self._bulk_btn_delete.setEnabled(False)
        self._bulk_btn_delete.clicked.connect(self._on_bulk_delete_clicked)
        action_row.addWidget(self._bulk_btn_delete)
        layout.addLayout(action_row)
        return w

    def _load_bulk_table(self):
        """Befuellt die Massen-Loesch-Tabelle. Perf-Messpunkte an den
        Meilensteinen (DB-Query, Genre-Map, Tabellenaufbau)."""
        import time as _time
        t0 = _time.perf_counter()
        table = self._bulk_table
        rows = self.db.get_all_songs_for_bulk()
        t1 = perf_split("    BulkDelete: DB-Query songs", t0)
        genre_map = self.db.get_song_genre_names()   # {song_id: [names]}
        t2 = perf_split("    BulkDelete: Genre-Map", t1)

        # Sortierung waehrend des Fuellens aus (sonst O(n log n) pro setItem)
        table.setSortingEnabled(False)
        table.setUpdatesEnabled(False)
        table.setRowCount(0)
        table.setRowCount(len(rows))
        for r, (sid, is_pat, is_sing, added, title, label, quality, err) \
                in enumerate(rows):
            if is_pat and is_sing:
                typ = "PS"
            elif is_pat:
                typ = "P"
            elif is_sing:
                typ = "S"
            else:
                typ = "—"
            it_type = QTableWidgetItem(typ)
            it_type.setData(Qt.UserRole, sid)   # song_id an Spalte 0 haengen
            table.setItem(r, 0, it_type)
            table.setItem(r, 1, QTableWidgetItem(added or ""))
            table.setItem(r, 2, QTableWidgetItem(title or ""))
            table.setItem(r, 3, QTableWidgetItem(label or ""))
            genres = genre_map.get(sid)
            table.setItem(r, 4, QTableWidgetItem(genres[0] if genres else ""))
            # ERR + Quality numerisch sortierbar (DisplayRole = int)
            it_err = QTableWidgetItem()
            it_err.setData(Qt.DisplayRole, int(err or 0))
            table.setItem(r, 5, it_err)
            it_q = QTableWidgetItem()
            it_q.setData(Qt.DisplayRole, int(quality or 0))
            table.setItem(r, 6, it_q)
        table.setUpdatesEnabled(True)
        table.setSortingEnabled(True)
        perf_split(f"    BulkDelete: Tabelle fuellen ({len(rows)} Zeilen)", t2)
        perf_log(f"  BulkDelete _load_bulk_table GESAMT ({len(rows)} Songs)", t0)
        self._on_bulk_selection_changed()

    def _bulk_selected_ids(self):
        """song_ids der aktuell selektierten Zeilen (aus Spalte-0-UserRole)."""
        ids = []
        sm = self._bulk_table.selectionModel()
        if sm is None:
            return ids
        for idx in sm.selectedRows():
            it = self._bulk_table.item(idx.row(), 0)
            if it is not None:
                sid = it.data(Qt.UserRole)
                if sid is not None:
                    ids.append(int(sid))
        return ids

    def _on_bulk_selection_changed(self):
        sm = self._bulk_table.selectionModel()
        n = len(sm.selectedRows()) if sm is not None else 0
        total = self._bulk_table.rowCount()
        self._bulk_btn_delete.setEnabled(n > 0 and self._bulk_delete_worker is None)
        if n:
            self._bulk_btn_delete.setText(_t('pot_bulk_delete_btn_n').format(n=n))
        else:
            self._bulk_btn_delete.setText(_t('pot_bulk_delete_btn'))
        self._bulk_lbl_count.setText(
            _t('pot_bulk_count').format(sel=n, total=total))

    def _on_bulk_delete_clicked(self):
        if self._bulk_delete_worker is not None:
            return
        ids = self._bulk_selected_ids()
        if not ids:
            return
        # Eine Sicherheits-Nachfrage fuer den gesamten Bulk
        text = _t('pot_bulk_confirm_text').format(n=len(ids))
        running = self.get_running_song() if self.get_running_song else None
        if running is not None and running.id in ids:
            text += "\n\n" + _t('pot_bulk_confirm_running').format(title=running.title)
        reply = QMessageBox.question(
            self, _t('pot_bulk_confirm_title'), text,
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply != QMessageBox.Yes:
            return
        # Historie pruefen → nur fragen wenn vorhanden, Default Nein
        delete_history = False
        hist_count = self.db.count_songs_with_history(ids)
        if hist_count > 0:
            h = QMessageBox.question(
                self, _t('pot_bulk_hist_title'),
                _t('pot_bulk_hist_text').format(n=hist_count),
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            delete_history = (h == QMessageBox.Yes)
        # Loeschen im Hintergrund-Thread (Eiserne Regel)
        self._bulk_btn_delete.setEnabled(False)
        self._bulk_delete_ids = ids
        self._bulk_delete_worker = _BulkDeleteWorker(
            ids, self.db.db_path, delete_history)
        self._bulk_delete_worker.finished.connect(self._on_bulk_delete_finished)
        self._bulk_delete_worker.error.connect(self._on_bulk_delete_error)
        self._bulk_delete_worker.start()

    def _on_bulk_delete_finished(self, deleted):
        self._bulk_delete_worker = None
        # Hauptfenster raeumt Playlist/Player/Song Data auf und frischt
        # Songliste, Planner und Potential (Badge-Counts) je einmal auf.
        # Vor der Meldung: sonst spielt ein geloeschter Song weiter, solange
        # sie offen ist, und sein Ende brachte Feedback und Rules.
        if self.on_songs_deleted:
            self.on_songs_deleted(self._bulk_delete_ids)
        self._load_bulk_table()   # Tabelle neu laden (geloeschte raus)
        QMessageBox.information(
            self, _t('pot_bulk_done_title'),
            _t('pot_bulk_done_text').format(n=deleted))

    def _on_bulk_delete_error(self, msg):
        self._bulk_delete_worker = None
        self._on_bulk_selection_changed()
        QMessageBox.warning(self, _t('pot_bulk_error_title'), msg)

    def refresh(self):
        """Aktualisiert Tab-Titel mit aktuellen Badge-Counts."""
        for check_type, label_key, _ in self._CHECKS:
            # Nicht jeder Check hat zwingend einen Tab: abschaltbare Checks
            # (z.B. die Cue-Sheet-Suche) stehen in _CHECKS, bekommen aber nur
            # bei gesetztem Schalter einen. Ohne Tab gibt es nichts zu
            # beschriften — und auch kein Badge.
            idx = self._tab_indices.get(check_type)
            if idx is None:
                continue
            if check_type == 'no_mp3':
                count = self._no_mp3_cached_count
            elif check_type == 'bad_mp3':
                count = self._bad_mp3_cached_count
            else:
                count = self.db.potential_count(check_type)
            base = _t(label_key)
            self._tabs.setTabText(idx, f"{base} ({count})" if count else base)
            self._update_start_badge(check_type, count)
        # QE-Filler Tab Badge
        qe_count = len(self.db.get_songs_for_qe_filler())
        qe_idx = self._tab_indices.get('qe_filler')
        if qe_idx is not None:
            base = _t('pot_qe_filler')
            self._tabs.setTabText(qe_idx, f"{base} ({qe_count})" if qe_count else base)
        self._update_start_badge('qe_filler', qe_count)
        # Loop-Optimieren Tab Badge (Anzahl Patter mit Loop)
        lo_idx = getattr(self, '_loop_opt_idx', None)
        if lo_idx is not None:
            lo_count = len(self.db.patter_with_loop())
            base = _t('pot_loop_optimize')
            self._tabs.setTabText(lo_idx, f"{base} ({lo_count})" if lo_count else base)
            self._update_start_badge('loop_optimize', lo_count)
        # No-BPM Tab Badge (Kandidaten: base_bpm < 100 oder > 150)
        nb_idx = getattr(self, '_no_bpm_idx', None)
        if nb_idx is not None:
            nb_count = len(self.db.potential_no_bpm())
            base = _t('pot_no_bpm')
            self._tabs.setTabText(nb_idx, f"{base} ({nb_count})" if nb_count else base)
            self._update_start_badge('no_bpm', nb_count)
        # Ohne-Songanfang Tab Badge (Singing Calls ohne singing_start)
        ns_idx = getattr(self, '_no_sstart_idx', None)
        if ns_idx is not None:
            ns_count = len(self.db.singing_no_start())
            base = _t('pot_no_sstart')
            self._tabs.setTabText(ns_idx, f"{base} ({ns_count})" if ns_count else base)
            self._update_start_badge('no_sstart', ns_count)
        # Nach dem Setzen der Badge-Texte die Start-Flows neu umbrechen, sonst
        # behalten die Buttons ihre alte (schmalere) Breite und das Badge wird
        # abgeschnitten (Text-Aenderung loest von sich aus kein Relayout aus).
        for flow in getattr(self, '_start_flows', []):
            flow._relayout()
        if self._current_check == 'qe_filler':
            self._qe_load()
        elif self._current_check:
            self._load_check(self._current_check)
        # Ist der No-BPM Tab gerade sichtbar, Tabelle mit auffrischen
        if nb_idx is not None and self._tabs.currentIndex() == nb_idx:
            self._load_no_bpm_table()
        # dito Ohne-Songanfang Tab
        if ns_idx is not None and self._tabs.currentIndex() == ns_idx:
            self._load_no_singing_start_table()

    def _on_tab_changed(self, idx):
        # Uebersicht: Badges neu berechnen, damit sie den aktuellen Stand zeigen
        if idx == getattr(self, '_start_idx', -1):
            self._current_check = None
            self.refresh()
            return
        # BL-148: Massen-Loesch-Reiter erst beim Oeffnen befuellen (Lazy-Load)
        if idx == getattr(self, '_bulk_idx', -1):
            self._current_check = None
            self._load_bulk_table()
            return
        if idx == getattr(self, '_no_bpm_idx', -1):
            self._current_check = None
            self._load_no_bpm_table()
            return
        if idx == getattr(self, '_no_sstart_idx', -1):
            self._current_check = None
            self._load_no_singing_start_table()
            return
        for ct, tab_idx in self._tab_indices.items():
            if tab_idx == idx:
                self._current_check = ct
                if ct == 'qe_filler':
                    self._qe_load()
                else:
                    self._load_check(ct)
                return
        self._current_check = None  # Metadaten-Tab

    def _load_check(self, check_type):
        tw = self._tab_widgets[check_type]
        table = tw['table']
        btn_ignore = tw['btn_ignore']
        btn_cleanup = tw['btn_cleanup']
        btn_fix_all = tw['btn_fix_all']

        btn_fix_sel = tw['btn_fix_sel']

        tw['data'] = []
        btn_cleanup.setEnabled(False)
        btn_cleanup.setVisible(False)
        btn_ignore.setEnabled(False)
        btn_fix_all.setEnabled(False)
        btn_fix_all.setVisible(False)
        btn_fix_sel.setEnabled(False)
        btn_fix_sel.setVisible(False)
        _btn_every = tw.get('btn_fix_every')
        if _btn_every is not None:
            _btn_every.setEnabled(False)
            _btn_every.setVisible(False)

        if check_type == 'singing_no_lyrics':
            rows = self.db.potential_singing_no_lyrics()
            desc = _t('pot_desc_singing_no_lyrics')
            tw['data'] = [(r[0], r[1] or r[2], desc) for r in rows]
            if rows:
                # Massenlauf: fehlende Lyrics aus einem Ordner ("Krabbelkiste")
                # zuordnen. Betrifft die ganze Liste, daher der Alle-Button.
                btn_fix_all.setText(_t('krabbel_btn_search'))
                btn_fix_all.setVisible(True)
                btn_fix_all.setEnabled(True)
        elif check_type == 'singing_no_lyrics_fill':
            # Dieselbe Grundmenge wie "Ohne Lyrics" — hier aber mit der
            # Moeglichkeit, das Cue Sheet direkt bei ceder.net zu holen.
            rows = self.db.potential_singing_no_lyrics()
            desc = _t('pot_desc_lyrics_fill')
            tw['data'] = [(r[0], r[1] or r[2], desc) for r in rows]
            if rows:
                btn_fix_sel.setText(_t('ceder_btn_search'))
                btn_fix_sel.setVisible(True)
        elif check_type == 'singing_no_song_points':
            rows = self.db.potential_singing_no_song_points()
            desc = _t('pot_desc_singing_no_song_points')
            tw['data'] = [(r[0], r[1] or r[2], desc) for r in rows]
        elif check_type == 'singing_no_sync_points':
            rows = self.db.potential_singing_no_sync_points()
            desc = _t('pot_desc_singing_no_sync_points')
            tw['data'] = [(r[0], r[1] or r[2], desc) for r in rows]
            # Mehrfachauswahl: hier laesst sich ein Teil der Liste gezielt
            # ergaenzen (Standard-Check-Tabs erlauben nur Einzelauswahl).
            table.setSelectionMode(QTableWidget.ExtendedSelection)
            if rows:
                btn_fix_sel.setText(_t('pot_fix_sel_sync'))
                btn_fix_sel.setVisible(True)
                btn_fix_all.setText(_t('pot_fix_all_sync'))
                btn_fix_all.setVisible(True)
                btn_fix_all.setEnabled(True)
            # Bewusst AUSSERHALB von `if rows`: der Komplettlauf betrifft den
            # ganzen Bestand und bleibt auch dann sinnvoll, wenn diese Liste
            # leer ist — etwa um nach einer Verbesserung der Erkennung alles
            # neu durchzurechnen.
            btn_every = tw.get('btn_fix_every')
            if btn_every is not None:
                btn_every.setText(_t('pot_fix_every_sync'))
                btn_every.setVisible(True)
                btn_every.setEnabled(True)
        elif check_type == 'pattern_no_loop':
            rows = self.db.potential_pattern_no_loop()
            desc = _t('pot_desc_pattern_no_loop')
            tw['data'] = [(r[0], r[1] or r[2], desc) for r in rows]
            if rows:
                btn_fix_all.setText(_t('pot_fix_all_loop'))
                btn_fix_all.setVisible(True)
                btn_fix_all.setEnabled(True)
        elif check_type == 'loop_no_beatsnap':
            rows = self.db.potential_loop_no_beatsnap()
            desc = _t('pot_desc_loop_no_beatsnap')
            tw['data'] = [(r[0], r[1] or r[2], desc) for r in rows]
            if rows:
                btn_fix_all.setText(_t('pot_fix_all_beatsnap'))
                btn_fix_all.setVisible(True)
                btn_fix_all.setEnabled(True)
        elif check_type == 'location_no_history':
            rows = self.db.potential_location_no_history()
            tw['data'] = [(r[0], r[1], _t('pot_desc_location_no_history')) for r in rows]
            if rows:
                btn_fix_all.setText(_t('pot_fix_all_locations'))
                btn_fix_all.setVisible(True)
                btn_fix_all.setEnabled(True)
        elif check_type == 'history_orphaned':
            rows = self.db.potential_history_orphaned()
            tw['data'] = [
                (r[0], _t('pot_desc_history_orphaned', id=r[0]), f"{r[1]} {_t('pot_col_count')}")
                for r in rows
            ]
            btn_cleanup.setVisible(True)
            btn_cleanup.setEnabled(len(rows) > 0)
        elif check_type == 'no_mp3':
            candidates = self.db.potential_no_mp3_candidates()
            if not candidates or not self.paths:
                table.setRowCount(0)
                btn_ignore.setVisible(True)
                return
            music_dirs = self.paths.music_dirs
            table.setRowCount(0)
            self._show_progress(
                _t('pot_checking_mp3', current=0, total=len(candidates)),
                cancel_fn=self._cancel_bulk, title=_t('pot_no_mp3'))
            self._bulk_worker = _NoMp3Worker(candidates, music_dirs)
            self._bulk_worker.progress.connect(
                lambda c, t: self._update_progress(_t('pot_checking_mp3', current=c, total=t)))
            self._bulk_worker.finished.connect(
                lambda rows, ct=check_type: self._on_no_mp3_done(ct, rows))
            self._bulk_worker.start()
            return
        elif check_type == 'bad_mp3':
            candidates = self.db.potential_bad_mp3_candidates()
            if not candidates or not self.paths:
                table.setRowCount(0)
                btn_ignore.setVisible(True)
                return
            sample_n = min(5, len(candidates))
            music_dirs = self.paths.music_dirs
            timing_jobs = []
            for sid, title, filename in candidates[:sample_n]:
                fp = self.paths.find_song_file(filename)
                if fp:
                    timing_jobs.append((sid, fp, None))
            if not timing_jobs:
                table.setRowCount(0)
                btn_ignore.setVisible(True)
                return
            table.setRowCount(0)
            self._show_progress(
                _t('pot_measuring', current=0, total=len(timing_jobs)),
                cancel_fn=self._cancel_bulk, title=_t('pot_bad_mp3'))
            self._timing_worker = _BulkTimingWorker(timing_jobs, mode='mp3_check')
            self._timing_worker.progress.connect(
                lambda c, t: self._update_progress(_t('pot_measuring', current=c, total=t)))
            self._timing_worker.finished.connect(
                lambda avg, ct=check_type: self._on_bad_mp3_timing_done(ct, avg, candidates, music_dirs))
            self._timing_worker.start()
            return
        elif check_type == 'no_quality':
            rows = self.db.potential_no_quality()
            desc = _t('pot_desc_no_quality')
            tw['data'] = [(r[0], r[1] or r[2], desc) for r in rows]
        elif check_type == 'no_err':
            rows = self.db.potential_no_err()
            desc = _t('pot_desc_no_err')
            tw['data'] = [(r[0], r[1] or r[2], desc) for r in rows]
        elif check_type == 'no_genre':
            rows = self.db.potential_no_genre()
            desc = _t('pot_desc_no_genre')
            tw['data'] = [(r[0], r[1] or r[2], desc) for r in rows]

        table.setUpdatesEnabled(False)
        table.setRowCount(0)
        n = len(tw['data'])
        table.setRowCount(n)
        for idx, (entity_id, name, desc) in enumerate(tw['data']):
            table.setItem(idx, 0, QTableWidgetItem(name))
            table.setItem(idx, 1, QTableWidgetItem(desc))
        table.setUpdatesEnabled(True)

        can_ignore = check_type != 'history_orphaned'
        btn_ignore.setVisible(can_ignore)

    def _on_selection_changed(self, check_type, tw):
        has_sel = len(tw['table'].selectedItems()) > 0
        can_ignore = check_type != 'history_orphaned'
        tw['btn_ignore'].setEnabled(has_sel and can_ignore)
        if tw['btn_fix_sel'].isVisible():
            tw['btn_fix_sel'].setEnabled(has_sel)

    def _on_double_click(self, check_type, tw, index):
        row = index.row()
        if row < 0 or row >= len(tw['data']):
            return
        entity_id = tw['data'][row][0]
        if check_type in ('singing_no_song_points', 'singing_no_sync_points'):
            if self.on_navigate_sync:
                self.on_navigate_sync(entity_id)
        elif check_type in ('singing_no_lyrics', 'pattern_no_loop',
                          'no_mp3', 'bad_mp3', 'no_quality', 'no_err', 'no_genre'):
            if self.on_navigate_song:
                self.on_navigate_song(entity_id)
        elif check_type == 'loop_no_beatsnap':
            if self.on_navigate_beatsnap:
                self.on_navigate_beatsnap(entity_id)
        elif check_type == 'location_no_history':
            if self.on_navigate_location:
                self.on_navigate_location(entity_id)

    def _on_ignore(self, check_type, tw):
        rows = sorted(set(idx.row() for idx in tw['table'].selectedIndexes()))
        for row in rows:
            if row < len(tw['data']):
                entity_id = tw['data'][row][0]
                self.db.potential_ignore(check_type, entity_id)
        if check_type == 'no_mp3':
            self._no_mp3_cached_count = None
        elif check_type == 'bad_mp3':
            self._bad_mp3_cached_count = None
        self.refresh()

    def _on_cleanup(self, check_type):
        if check_type != 'history_orphaned':
            return
        rows = self.db.potential_history_orphaned()
        if not rows:
            return
        total = sum(r[1] for r in rows)
        reply = QMessageBox.question(
            self, _t('pot_cleanup'), _t('pot_cleanup_confirm', count=total),
            QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            deleted = self.db.potential_cleanup_orphaned_history()
            QMessageBox.information(self, _t('pot_cleanup'),
                                    _t('pot_cleanup_done', count=deleted))
            self.refresh()

    def _on_bad_mp3_timing_done(self, check_type, seconds_per_song, candidates, music_dirs):
        self._close_progress()
        self._timing_worker = None
        n = len(candidates)
        total_min = (seconds_per_song * n) / 60.0
        reply = QMessageBox.question(
            self, _t('pot_bad_mp3'),
            _t('pot_bad_mp3_timing', minutes=total_min, count=n),
            QMessageBox.Yes | QMessageBox.No)
        if reply != QMessageBox.Yes:
            return
        self._run_bad_mp3_check(check_type, candidates, music_dirs)

    def _run_bad_mp3_check(self, check_type, candidates, music_dirs):
        self._show_progress(
            _t('pot_checking_mp3', current=0, total=len(candidates)),
            cancel_fn=self._cancel_bulk, title=_t('pot_bad_mp3'))
        self._bulk_worker = _BadMp3Worker(candidates, music_dirs)
        self._bulk_worker.progress.connect(
            lambda c, t: self._update_progress(_t('pot_checking_mp3', current=c, total=t)))
        self._bulk_worker.finished.connect(
            lambda rows, ct=check_type: self._on_bad_mp3_done(ct, rows))
        self._bulk_worker.start()

    def _on_bad_mp3_done(self, check_type, rows):
        self._close_progress()
        self._bulk_worker = None
        tw = self._tab_widgets[check_type]
        desc = _t('pot_desc_bad_mp3')
        tw['data'] = [(song_id, name, desc) for song_id, name in rows]
        n = len(tw['data'])
        self._bad_mp3_cached_count = n
        table = tw['table']
        table.setUpdatesEnabled(False)
        table.setRowCount(0)
        table.setRowCount(n)
        for idx, (entity_id, name, desc_) in enumerate(tw['data']):
            table.setItem(idx, 0, QTableWidgetItem(name))
            table.setItem(idx, 1, QTableWidgetItem(desc_))
        table.setUpdatesEnabled(True)
        tab_idx = self._tab_indices[check_type]
        base = _t('pot_bad_mp3')
        self._tabs.setTabText(tab_idx, f"{base} ({n})" if n > 0 else base)
        self._update_start_badge('bad_mp3', n)
        tw['btn_ignore'].setVisible(True)

    def _on_no_mp3_done(self, check_type, rows):
        self._close_progress()
        self._bulk_worker = None
        tw = self._tab_widgets[check_type]
        desc = _t('pot_desc_no_mp3')
        tw['data'] = [(song_id, name, desc) for song_id, name in rows]
        n = len(tw['data'])
        self._no_mp3_cached_count = n
        table = tw['table']
        table.setUpdatesEnabled(False)
        table.setRowCount(0)
        table.setRowCount(n)
        for idx, (entity_id, name, desc_) in enumerate(tw['data']):
            table.setItem(idx, 0, QTableWidgetItem(name))
            table.setItem(idx, 1, QTableWidgetItem(desc_))
        table.setUpdatesEnabled(True)
        tab_idx = self._tab_indices[check_type]
        base = _t('pot_no_mp3')
        self._tabs.setTabText(tab_idx, f"{base} ({n})" if n > 0 else base)
        self._update_start_badge('no_mp3', n)
        tw['btn_ignore'].setVisible(True)

    # ---- Bulk Fix All ----

    def _on_fix_all(self, check_type):
        if check_type == 'singing_no_lyrics':
            self._krabbelkiste_start()
        elif check_type == 'pattern_no_loop':
            self._fix_all_loop()
        elif check_type == 'loop_no_beatsnap':
            self._fix_all_beatsnap()
        elif check_type == 'location_no_history':
            self._fix_all_locations()
        elif check_type == 'singing_no_sync_points':
            self._syncpts_start(self.db.potential_singing_no_sync_points())

    def _on_fix_selected(self, check_type, tw):
        """Massenlauf nur fuer die markierten Zeilen."""
        if check_type == 'singing_no_lyrics_fill':
            self._ceder_start_lookup(tw)
            return
        if check_type != 'singing_no_sync_points':
            return
        rows = sorted(set(idx.row() for idx in tw['table'].selectedIndexes()))
        ids = {tw['data'][r][0] for r in rows if r < len(tw['data'])}
        if not ids:
            return
        self._syncpts_start(
            [r for r in self.db.potential_singing_no_sync_points() if r[0] in ids])

    # ---- Krabbelkiste: fehlende Lyrics aus einem Ordner zuordnen -----------

    def _krabbelkiste_start(self):
        """Ordner nach passenden Lyric-Dateien durchsuchen und zuordnen."""
        if self._krabbel_worker is not None and self._krabbel_worker.isRunning():
            return
        if not self.paths:
            return
        songs = self.db.potential_singing_no_lyrics_full()
        if not songs:
            QMessageBox.information(self, _t('krabbel_btn_search'),
                                    _t('krabbel_no_songs'))
            return
        opt = _KrabbelkisteOptionsDialog(self)
        if opt.exec() != QDialog.Accepted:
            return
        recursive = opt.recursive()
        start_dir = self.paths.lyrics_dir or os.path.expanduser("~")
        folder = QFileDialog.getExistingDirectory(
            self, _t('krabbel_choose_folder'), start_dir)
        if not folder:
            return
        # Dieselben gepflegten Import-Listen wie der ZIP-Import (Labels/Modifier).
        # _zip_lists_path lebt am Hauptfenster, nicht hier — den Pfad daher selbst
        # bauen; bei Problemen still auf die Code-Standards zurueckfallen.
        try:
            lists = zip_import.load_lists(
                os.path.join(perf.app_dir(), "config", "zip_import_lists.json"))
        except Exception:  # noqa: BLE001
            lists = zip_import.ImportLists.defaults()
        self._show_progress(_t('krabbel_scanning'),
                            cancel_fn=self._krabbel_cancel,
                            title=_t('krabbel_btn_search'))
        # intern#126: Songs ohne Label bekommen das eindeutige Katalog-Label als
        # zusaetzliches Kriterium (nur Bonus im 'lyric'-Profil)
        app_dir = self.paths.app_dir if self.paths else ""
        songs = [(sid, t, lbl, fn, song_catalog.label_hint(t or "", lbl or "", app_dir))
                 for sid, t, lbl, fn in songs]
        self._krabbel_worker = _KrabbelkisteWorker(
            folder, recursive, songs, lists)
        self._krabbel_worker.progress.connect(
            lambda c, t: self._update_progress(
                _t('krabbel_scanning_n', current=c, total=t)))
        self._krabbel_worker.finished_ok.connect(self._krabbel_on_results)
        self._krabbel_worker.failed.connect(self._krabbel_on_failed)
        self._krabbel_worker.start()

    def _krabbel_cancel(self):
        if self._krabbel_worker is not None:
            self._krabbel_worker.cancel()
        self._close_progress()

    def _krabbel_on_failed(self, msg):
        self._close_progress()
        self._krabbel_worker = None
        QMessageBox.warning(self, _t('krabbel_btn_search'),
                            _t('krabbel_error', msg=msg))

    def _krabbel_on_results(self, results):
        self._close_progress()
        self._krabbel_worker = None
        if not results:
            QMessageBox.information(self, _t('krabbel_btn_search'),
                                    _t('krabbel_no_matches'))
            return
        dlg = _KrabbelkisteResultDialog(results, self)
        if dlg.exec() != QDialog.Accepted:
            return
        chosen = dlg.selected()
        if chosen:
            self._krabbel_apply(chosen)

    def _krabbel_apply(self, chosen):
        """Kopiert die gewaehlten Lyric-Dateien in den Lyrics-Ordner und
        verknuepft sie mit dem jeweiligen Song (wie beim ZIP-Import/Ceder)."""
        lyrics_dir = self.paths.lyrics_dir

        def _copy_into(src, target_dir):
            os.makedirs(target_dir, exist_ok=True)
            dest = os.path.join(target_dir, os.path.basename(src))
            # Namenskollision mit ANDERER Datei (Groesse weicht ab): eindeutigen
            # Namen waehlen. Gleiche Groesse werten wir als identische Datei.
            if os.path.exists(dest) \
                    and os.path.getsize(dest) != os.path.getsize(src):
                root, ext = os.path.splitext(dest)
                k = 1
                while os.path.exists(dest) \
                        and os.path.getsize(dest) != os.path.getsize(src):
                    dest = f"{root}_{k}{ext}"
                    k += 1
            if not os.path.exists(dest):
                shutil.copy2(src, dest)
            return os.path.basename(dest)

        done, errors = 0, []
        for r in chosen:
            try:
                fn = _copy_into(r["file_path"], lyrics_dir)
                self.db.update_lyrics_file(r["song_id"], fn)
                done += 1
            except Exception as e:  # noqa: BLE001
                errors.append(str(e))
        msg = _t('krabbel_applied', count=done)
        if errors:
            msg += "\n" + _t('krabbel_apply_errors', count=len(errors))
        QMessageBox.information(self, _t('krabbel_btn_search'), msg)
        self.refresh()
        self._load_check('singing_no_lyrics')

    def _fix_all_loop(self):
        rows = self.db.potential_pattern_no_loop()
        if not rows:
            return
        n = len(rows)
        sample_n = min(5, n)
        reply = QMessageBox.question(
            self, _t('pot_fix_all_loop'),
            _t('pot_fix_all_loop_confirm', count=n, sample=sample_n),
            QMessageBox.Yes | QMessageBox.No)
        if reply != QMessageBox.Yes:
            return
        preset = self._ask_loop_preset(_t('pot_fix_all_loop'))
        if preset is None:
            return
        self._bulk_loop_preset = preset

        jobs = []
        for sid, title, filename in rows:
            song = self.db.get_by_id(sid)
            if not song:
                continue
            fp = self.paths.find_song_file(filename) if self.paths else ''
            if not fp:
                continue
            jobs.append((sid, fp, song.base_bpm, title or filename))

        if not jobs:
            QMessageBox.information(self, _t('pot_fix_all_loop'),
                                    _t('pot_fix_all_done', done=0, total=n, skipped=n))
            return

        if len(jobs) <= 5:
            self._run_bulk_autoloop(jobs)
            return

        # Zeitschaetzung: ersten sample_n Songs messen
        timing_jobs = [(sid, fp, bpm) for sid, fp, bpm, _ in jobs[:sample_n]]
        self._show_progress(_t('pot_measuring', current=0, total=sample_n),
                            cancel_fn=self._cancel_bulk)
        self._timing_worker = _BulkTimingWorker(timing_jobs)
        self._timing_worker.progress.connect(
            lambda c, t: self._update_progress(_t('pot_measuring', current=c, total=t)))
        self._timing_worker.finished.connect(
            lambda avg: self._on_timing_done(avg, jobs))
        self._timing_worker.start()

    def _on_timing_done(self, seconds_per_song, jobs):
        """Zeitschaetzung fertig — User zeigen und bestaetigen lassen."""
        self._close_progress()
        self._timing_worker = None
        total_sec = seconds_per_song * len(jobs)
        total_min = total_sec / 60.0
        reply = QMessageBox.question(
            self, _t('pot_fix_all_loop'),
            _t('pot_fix_all_loop_timing', minutes=total_min, count=len(jobs)),
            QMessageBox.Yes | QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return
        self._run_bulk_autoloop(jobs)

    def _run_bulk_autoloop(self, jobs):
        self._show_progress(_t('pot_processing', current=0, total=len(jobs)),
                            cancel_fn=self._cancel_bulk)
        self._bulk_worker = _BulkAutoLoopWorker(
            jobs, preset=getattr(self, '_bulk_loop_preset', None))
        self._bulk_worker.loop_found.connect(self._store_found_loop)
        self._bulk_worker.progress.connect(
            lambda c, t, name: self._update_progress(
                _t('pot_processing', current=c, total=t) + f"\n{name}"))
        self._bulk_worker.finished.connect(self._on_bulk_done)
        self._bulk_worker.start()

    # ---- Loop-Finder-Presets (intern#207) ----

    def _loop_preset_names(self):
        """Dieselbe Liste wie in der Rule „Auto-Set Best Loop“."""
        from loopfinder_widget import LoopFinderWidget
        return LoopFinderWidget.list_preset_names(
            getattr(self.paths, 'loop_presets_dir', None))

    def _load_loop_preset(self, name):
        """Preset per Name fuer Songs OHNE Loop.

        Die Optimize-Stufen haengen an vorhandenen Marken, die diese Songs
        nicht haben; sie fallen deshalb wie im Loop Finder auf Singing zurueck.
        """
        from loopfinder_widget import LoopFinderWidget
        name = LoopFinderWidget.PRESET_ALIASES.get(name, name)
        if name in LoopFinderWidget.OPTIMIZE_PRESETS:
            return loop_windows.singing_preset()
        return loop_windows.load_preset_file(
            name, getattr(self.paths, 'loop_presets_dir', None))

    def _store_found_loop(self, song_id, loop_in, loop_out):
        """Speichert einen Loop aus dem Bulk-Auto-Loop (Hauptthread, ueber song_db)."""
        self.db.save_playback_settings(song_id, loop_in=loop_in, loop_out=loop_out)

    def _ask_loop_preset(self, title):
        """Fragt das Preset vor dem Start ab; None = abgebrochen."""
        names = self._loop_preset_names()
        name, ok = QInputDialog.getItem(
            self, title, _t('pot_loop_preset_prompt'), names, 0, False)
        if not ok or not name:
            return None
        return self._load_loop_preset(name)

    def _fix_all_beatsnap(self):
        """Beat-Snap fuer alle Songs mit Loop aber ohne BeatSnap."""
        rows = self.db.potential_loop_no_beatsnap()
        if not rows:
            return
        n = len(rows)
        sample_n = min(5, n)
        reply = QMessageBox.question(
            self, _t('pot_fix_all_beatsnap'),
            _t('pot_fix_all_beatsnap_confirm', count=n, sample=sample_n),
            QMessageBox.Yes | QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return

        jobs = []
        for sid, title, filename in rows:
            song = self.db.get_by_id(sid)
            if not song:
                continue
            fp = self.paths.find_song_file(filename) if self.paths else ''
            if not fp:
                continue
            jobs.append((sid, fp, song.base_bpm, song.loop_in, song.loop_out,
                         title or filename))

        if not jobs:
            QMessageBox.information(self, _t('pot_fix_all_beatsnap'),
                                    _t('pot_fix_all_done', done=0, total=n, skipped=n))
            return

        if len(jobs) <= 5:
            self._run_bulk_beatsnap(jobs)
            return

        timing_jobs = [(sid, fp, bpm) for sid, fp, bpm, _, _, _ in jobs[:sample_n]]
        self._show_progress(_t('pot_measuring', current=0, total=sample_n),
                            cancel_fn=self._cancel_bulk,
                            title=_t('pot_fix_all_beatsnap'))
        self._timing_worker = _BulkTimingWorker(timing_jobs, mode='beatsnap')
        self._timing_worker.progress.connect(
            lambda c, t: self._update_progress(_t('pot_measuring', current=c, total=t)))
        self._timing_worker.finished.connect(
            lambda avg: self._on_beatsnap_timing_done(avg, jobs))
        self._timing_worker.start()

    def _on_beatsnap_timing_done(self, seconds_per_song, jobs):
        """Zeitschaetzung fertig — User fragen ob Fortfahren."""
        self._close_progress()
        self._timing_worker = None
        total_min = (seconds_per_song * len(jobs)) / 60.0
        reply = QMessageBox.question(
            self, _t('pot_fix_all_beatsnap'),
            _t('pot_fix_all_loop_timing', minutes=total_min, count=len(jobs)),
            QMessageBox.Yes | QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return
        self._run_bulk_beatsnap(jobs)

    def _run_bulk_beatsnap(self, jobs):
        self._show_progress(_t('pot_processing', current=0, total=len(jobs)),
                            cancel_fn=self._cancel_bulk,
                            title=_t('pot_fix_all_beatsnap'))
        self._bulk_worker = _BulkBeatSnapWorker(
            jobs, self.db.db_path, self._check_beatsnap_genre_id())
        self._bulk_worker.progress.connect(
            lambda c, t, name: self._update_progress(
                _t('pot_processing', current=c, total=t) + f"\n{name}"))
        self._bulk_worker.finished.connect(self._on_bulk_done)
        self._bulk_worker.start()

    def _fix_all_locations(self):
        """Loescht alle leeren Lokationen nach Bestaetigung."""
        rows = self.db.potential_location_no_history()
        if not rows:
            return
        n = len(rows)
        reply = QMessageBox.question(
            self, _t('pot_fix_all_locations'),
            _t('pot_fix_all_locations_confirm', count=n),
            QMessageBox.Yes | QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return
        deleted = 0
        for lid, _ in rows:
            try:
                self.db.delete_location(lid, delete_history=False)
                deleted += 1
            except Exception as e:
                print(f"[BulkLocations] Fehler bei Lokation #{lid}: {e}")
        QMessageBox.information(
            self, _t('pot_fix_all_locations'),
            _t('pot_fix_all_locations_done', count=deleted)
        )
        self.refresh()

    # ---- Loop-Optimieren-Tab ----

    def _build_loop_optimize_tab(self):
        """Reiter zum Stapel-Optimieren der Loops aller Patter-Songs mit Loop."""
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        desc = QLabel(_t('pot_loop_optimize_desc'))
        desc.setWordWrap(True)
        desc.setStyleSheet("font-size: 11px; color: #888;")
        layout.addWidget(desc)

        # Suchbereich-Combo (+-2% / +-5%, Default +-2%)
        margin_row = QHBoxLayout()
        margin_row.setSpacing(6)
        margin_row.addWidget(QLabel(_t('pot_loop_optimize_margin')))
        self._lo_margin_combo = QComboBox()
        self._lo_margin_combo.addItem("± 2 %", 2)
        self._lo_margin_combo.addItem("± 5 %", 5)
        self._lo_margin_combo.setCurrentIndex(0)  # Default +-2%
        self._lo_margin_combo.setFixedWidth(90)
        margin_row.addWidget(self._lo_margin_combo)
        margin_row.addStretch()
        layout.addLayout(margin_row)

        self._lo_btn_start = QPushButton(_t('pot_loop_optimize_btn'))
        self._lo_btn_start.clicked.connect(self._fix_all_loop_optimize)
        layout.addWidget(self._lo_btn_start)

        layout.addStretch()
        return w

    def _fix_all_loop_optimize(self):
        """Optimiert die Loops aller Patter-Songs mit vorhandenem Loop."""
        rows = self.db.patter_with_loop()
        if not rows:
            QMessageBox.information(self, _t('pot_loop_optimize'),
                                    _t('pot_loop_optimize_none'))
            return
        n = len(rows)
        sample_n = min(5, n)
        margin = int(self._lo_margin_combo.currentData())
        reply = QMessageBox.question(
            self, _t('pot_loop_optimize'),
            _t('pot_loop_optimize_confirm', count=n, sample=sample_n, margin=margin),
            QMessageBox.Yes | QMessageBox.No)
        if reply != QMessageBox.Yes:
            return

        jobs = []
        for sid, title, filename in rows:
            song = self.db.get_by_id(sid)
            if not song:
                continue
            fp = self.paths.find_song_file(filename) if self.paths else ''
            if not fp:
                continue
            jobs.append((sid, fp, song.base_bpm, song.loop_in, song.loop_out,
                         title or filename))

        if not jobs:
            QMessageBox.information(self, _t('pot_loop_optimize'),
                                    _t('pot_fix_all_done', done=0, total=n, skipped=n))
            return

        if len(jobs) <= 5:
            self._run_bulk_loop_optimize(jobs, margin)
            return

        # Probelauf/Zeitschaetzung mit den ersten sample_n Songs (mode='loop')
        timing_jobs = [(sid, fp, bpm) for sid, fp, bpm, _, _, _ in jobs[:sample_n]]
        self._show_progress(_t('pot_measuring', current=0, total=sample_n),
                            cancel_fn=self._cancel_bulk,
                            title=_t('pot_loop_optimize'))
        self._timing_worker = _BulkTimingWorker(timing_jobs, mode='loop')
        self._timing_worker.progress.connect(
            lambda c, t: self._update_progress(_t('pot_measuring', current=c, total=t)))
        self._timing_worker.finished.connect(
            lambda avg: self._on_loop_optimize_timing_done(avg, jobs, margin))
        self._timing_worker.start()

    def _on_loop_optimize_timing_done(self, seconds_per_song, jobs, margin):
        """Zeitschaetzung fertig — User fragen ob Fortfahren."""
        self._close_progress()
        self._timing_worker = None
        total_min = (seconds_per_song * len(jobs)) / 60.0
        reply = QMessageBox.question(
            self, _t('pot_loop_optimize'),
            _t('pot_fix_all_loop_timing', minutes=total_min, count=len(jobs)),
            QMessageBox.Yes | QMessageBox.No)
        if reply != QMessageBox.Yes:
            return
        self._run_bulk_loop_optimize(jobs, margin)

    def _run_bulk_loop_optimize(self, jobs, margin):
        self._show_progress(_t('pot_processing', current=0, total=len(jobs)),
                            cancel_fn=self._cancel_bulk,
                            title=_t('pot_loop_optimize'))
        self._bulk_worker = _BulkLoopOptimizeWorker(jobs, self.db.db_path, margin)
        self._bulk_worker.progress.connect(
            lambda c, t, name: self._update_progress(
                _t('pot_processing', current=c, total=t) + f"\n{name}"))
        self._bulk_worker.finished.connect(self._on_bulk_done)
        self._bulk_worker.start()

    # ---- No-BPM-Tab (BPM ermitteln) ----

    def _build_no_bpm_tab(self):
        """Reiter fuer Songs ohne/mit unplausibler BPM (< 100 oder > 150).
        Kandidaten-Tabelle + drei Ermittlungs-Buttons (Selektion / alle leeren /
        ALLE). Batch-Muster identisch zu Loop/Beat-Snap (5-Song-Probelauf)."""
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(4, 6, 4, 4)
        layout.setSpacing(4)

        desc = QLabel(_t('pot_no_bpm_desc'))
        desc.setWordWrap(True)
        desc.setStyleSheet("font-size: 11px; color: #888;")
        layout.addWidget(desc)

        table = QTableWidget()
        table.setEditTriggers(QTableWidget.NoEditTriggers)
        table.setSelectionBehavior(QTableWidget.SelectRows)
        table.setSelectionMode(QTableWidget.ExtendedSelection)
        table.setAlternatingRowColors(True)
        table.verticalHeader().setVisible(False)
        table.setColumnCount(2)
        table.setHorizontalHeaderLabels([_t('pot_col_name'), _t('pot_no_bpm_col')])
        table.horizontalHeader().setStretchLastSection(True)
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self._no_bpm_table = table
        layout.addWidget(table, 1)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(4)
        self._nb_btn_selected = QPushButton(_t('pot_no_bpm_selected'))
        self._nb_btn_selected.setEnabled(False)
        self._nb_btn_selected.clicked.connect(self._bpm_selected)
        self._nb_btn_empty = QPushButton(_t('pot_no_bpm_all_empty'))
        self._nb_btn_empty.clicked.connect(self._bpm_all_empty)
        self._nb_btn_all = QPushButton(_t('pot_no_bpm_all'))
        self._nb_btn_all.clicked.connect(self._bpm_all)
        btn_row.addWidget(self._nb_btn_selected)
        btn_row.addWidget(self._nb_btn_empty)
        btn_row.addStretch()
        btn_row.addWidget(self._nb_btn_all)
        layout.addLayout(btn_row)

        table.itemSelectionChanged.connect(
            lambda: self._nb_btn_selected.setEnabled(
                bool(self._no_bpm_table.selectionModel().selectedRows())))
        return w

    def _load_no_bpm_table(self):
        """Fuellt die Kandidaten-Tabelle (base_bpm < 100 oder > 150)."""
        rows = self.db.potential_no_bpm()
        table = self._no_bpm_table
        table.setUpdatesEnabled(False)
        table.setRowCount(0)
        table.setRowCount(len(rows))
        for r, row in enumerate(rows):
            sid, title, filename = row[0], row[1], row[2]
            bpm = row[3] if len(row) > 3 else 0
            name_item = QTableWidgetItem(title or filename)
            name_item.setData(Qt.UserRole, sid)
            table.setItem(r, 0, name_item)
            problem = (_t('pot_no_bpm_empty') if not bpm or bpm <= 0
                       else _t('pot_no_bpm_outofrange', bpm=bpm))
            table.setItem(r, 1, QTableWidgetItem(problem))
        table.setUpdatesEnabled(True)
        self._nb_btn_selected.setEnabled(False)

    def _no_bpm_selected_ids(self):
        ids = []
        sm = self._no_bpm_table.selectionModel()
        if sm is None:
            return ids
        for idx in sm.selectedRows():
            it = self._no_bpm_table.item(idx.row(), 0)
            if it is not None and it.data(Qt.UserRole) is not None:
                ids.append(int(it.data(Qt.UserRole)))
        return ids

    def _bpm_build_jobs(self, rows):
        """rows: Sequenzen mit (sid, title, filename, ...) → (jobs, missing).
        jobs = [(sid, fp, name)] fuer auffindbare Dateien, missing = [name] fuer
        Songs, deren Audiodatei in keinem Musikordner existiert. Robust gegen
        3- und 4-Tupel (Kandidaten liefern zusaetzlich base_bpm)."""
        jobs, missing = [], []
        for row in rows:
            sid, title, filename = row[0], row[1], row[2]
            name = title or filename
            fp = self.paths.find_song_file(filename) if self.paths else ''
            if fp:
                jobs.append((sid, fp, name))
            else:
                missing.append(name)
        return jobs, missing

    def _bpm_selected(self):
        ids = set(self._no_bpm_selected_ids())
        if not ids:
            return
        rows = [r for r in self.db.potential_no_bpm() if r[0] in ids]
        self._bpm_start(rows)

    def _bpm_all_empty(self):
        self._bpm_start(self.db.songs_bpm_empty())

    def _bpm_all(self):
        rows = self.db.songs_all_for_bpm()
        if not rows:
            QMessageBox.information(self, _t('pot_no_bpm'), _t('pot_no_bpm_none'))
            return
        # Extra-Rueckfrage: BPM-Finder wirklich ueber ALLE Songs (ueberschreibt
        # auch bereits gute Werte).
        reply = QMessageBox.warning(
            self, _t('pot_no_bpm_all'),
            _t('pot_no_bpm_all_warn', count=len(rows)),
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply != QMessageBox.Yes:
            return
        self._bpm_start(rows, skip_confirm=True)

    def _bpm_start(self, rows, skip_confirm=False):
        """Gemeinsamer Einstieg aller 3 Buttons.

        Ab TRIAL_MIN Songs wird zur Zeitschaetzung ein Probelauf mit den ersten
        5 gemacht — diese 5 werden dabei GLEICH ermittelt und eingetragen (nicht
        verworfen), der eigentliche Lauf verarbeitet danach nur den Rest. Kein
        doppeltes Rechnen. Darunter laeuft alles direkt ohne Probelauf durch."""
        TRIAL_MIN = 15   # ab so vielen Songs lohnt der Probelauf/die Schaetzung
        if not rows:
            QMessageBox.information(self, _t('pot_no_bpm'), _t('pot_no_bpm_none'))
            return
        jobs, missing = self._bpm_build_jobs(rows)
        self._bpm_missing = missing
        self._bpm_accum = (0, 0)
        if not jobs:
            # Alle Kandidaten ohne auffindbare Datei → nur Existenz-Report
            self._show_bpm_result(0, 0, missing)
            return
        n = len(jobs)
        if not skip_confirm:
            msg = (_t('pot_no_bpm_confirm', count=n, sample=5) if n >= TRIAL_MIN
                   else _t('pot_no_bpm_confirm_direct', count=n))
            if QMessageBox.question(self, _t('pot_no_bpm'), msg,
                                    QMessageBox.Yes | QMessageBox.No) != QMessageBox.Yes:
                return

        if n < TRIAL_MIN:
            # Kein Probelauf noetig — direkt alles verarbeiten
            self._run_bulk_bpm(jobs)
            return

        # Probelauf: erste 5 ECHT ermitteln + eintragen (Ergebnisse behalten),
        # Dauer messen → Rest schaetzen.
        import time as _time
        self._bpm_rest_jobs = jobs[5:]
        self._bpm_sample_t0 = _time.perf_counter()
        self._show_progress(_t('pot_measuring', current=0, total=5),
                            cancel_fn=self._cancel_bulk, title=_t('pot_no_bpm'))
        self._bulk_worker = _BulkBpmWorker(jobs[:5], self.db.db_path)
        self._bulk_worker.progress.connect(
            lambda c, t, name: self._update_progress(
                _t('pot_measuring', current=c, total=5)))
        self._bulk_worker.finished.connect(self._on_bpm_sample_done)
        self._bulk_worker.start()

    def _on_bpm_sample_done(self, done, skipped):
        """Probelauf (erste 5) fertig — deren BPM ist bereits geschrieben.
        Dauer fuer den Rest schaetzen und nachfragen; die 5 zaehlen mit."""
        cancelled = bool(self._bulk_worker
                         and getattr(self._bulk_worker, '_cancelled', False))
        self._close_progress()
        self._bulk_worker = None
        self._bpm_accum = (done, skipped)   # Probelauf-Ergebnisse mitzaehlen
        rest = getattr(self, '_bpm_rest_jobs', [])
        if cancelled or not rest:
            self._finalize_bpm(0, 0)
            return
        import time as _time
        elapsed = _time.perf_counter() - getattr(self, '_bpm_sample_t0',
                                                  _time.perf_counter())
        per_song = elapsed / max(1, done + skipped)
        total_min = (per_song * len(rest)) / 60.0
        reply = QMessageBox.question(
            self, _t('pot_no_bpm'),
            _t('pot_fix_all_loop_timing', minutes=total_min, count=len(rest)),
            QMessageBox.Yes | QMessageBox.No)
        if reply != QMessageBox.Yes:
            # Abbruch — die 5 bleiben trotzdem eingetragen
            self._finalize_bpm(0, 0)
            return
        self._run_bulk_bpm(rest)

    def _run_bulk_bpm(self, jobs):
        self._show_progress(_t('pot_processing', current=0, total=len(jobs)),
                            cancel_fn=self._cancel_bulk, title=_t('pot_no_bpm'))
        self._bulk_worker = _BulkBpmWorker(jobs, self.db.db_path)
        self._bulk_worker.progress.connect(
            lambda c, t, name: self._update_progress(
                _t('pot_processing', current=c, total=t) + f"\n{name}"))
        self._bulk_worker.finished.connect(self._on_bpm_bulk_done)
        self._bulk_worker.start()

    def _on_bpm_bulk_done(self, done, skipped):
        self._close_progress()
        self._bulk_worker = None
        self._finalize_bpm(done, skipped)

    def _finalize_bpm(self, done, skipped):
        """Ergebnis anzeigen (inkl. Probelauf-Anteil) + Tabelle/Badges auffrischen."""
        ad, ask = getattr(self, '_bpm_accum', (0, 0))
        self._show_bpm_result(done + ad, skipped + ask,
                              getattr(self, '_bpm_missing', []) or [])
        self._bpm_missing = []
        self._bpm_accum = (0, 0)
        self._load_no_bpm_table()
        self.refresh()
        if self.on_bulk_done:
            self.on_bulk_done()

    def _show_bpm_result(self, done, skipped, missing):
        """Ergebnis-Dialog nach dem BPM-Lauf. Listet zusaetzlich Songs, deren
        Audiodatei fehlt (Existenz-Check) — sonst blieben sie unerklaert als
        Kandidaten stehen (siehe Tab 'Ohne MP3')."""
        total = done + skipped
        parts = []
        if total > 0:
            parts.append(_t('pot_fix_all_done', done=done, total=total, skipped=skipped))
        if missing:
            names = "\n".join("• " + m for m in missing[:20])
            if len(missing) > 20:
                names += "\n…"
            parts.append(_t('pot_no_bpm_missing_hint', count=len(missing)) + "\n" + names)
        if not parts:
            parts.append(_t('pot_fix_all_done', done=done, total=total, skipped=skipped))
        QMessageBox.information(self, _t('pot_no_bpm'), "\n\n".join(parts))

    # ---- Ohne Songanfang (Singing-Body Auto-Erkennung) ----

    def _build_no_singing_start_tab(self):
        """Reiter fuer Singing Calls ohne gesetzten Musik-Startpunkt.
        Kandidaten-Tabelle + drei Analyse-Buttons (Selektierte / Offene / ALLE).
        Batch-Muster identisch zum No-BPM-Tab (5-Song-Probelauf ab 15 Songs).
        Der Songanfang wird per detect_singing_body (SyncPoints + Song-Analyse)
        ermittelt; unsichere Treffer werden uebersprungen und gemeldet."""
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(4, 6, 4, 4)
        layout.setSpacing(4)

        desc = QLabel(_t('pot_no_sstart_desc'))
        desc.setWordWrap(True)
        desc.setStyleSheet("font-size: 11px; color: #888;")
        layout.addWidget(desc)

        table = QTableWidget()
        table.setEditTriggers(QTableWidget.NoEditTriggers)
        table.setSelectionBehavior(QTableWidget.SelectRows)
        table.setSelectionMode(QTableWidget.ExtendedSelection)
        table.setAlternatingRowColors(True)
        table.verticalHeader().setVisible(False)
        table.setColumnCount(2)
        table.setHorizontalHeaderLabels([_t('pot_col_name'), _t('pot_no_sstart_col')])
        table.horizontalHeader().setStretchLastSection(True)
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self._no_sstart_table = table
        layout.addWidget(table, 1)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(4)
        self._ns_btn_selected = QPushButton(_t('pot_no_sstart_selected'))
        self._ns_btn_selected.setEnabled(False)
        self._ns_btn_selected.clicked.connect(self._sstart_selected)
        self._ns_btn_open = QPushButton(_t('pot_no_sstart_open'))
        self._ns_btn_open.clicked.connect(self._sstart_open)
        self._ns_btn_all = QPushButton(_t('pot_no_sstart_all'))
        self._ns_btn_all.clicked.connect(self._sstart_all)
        btn_row.addWidget(self._ns_btn_selected)
        btn_row.addWidget(self._ns_btn_open)
        btn_row.addStretch()
        btn_row.addWidget(self._ns_btn_all)
        layout.addLayout(btn_row)

        table.itemSelectionChanged.connect(
            lambda: self._ns_btn_selected.setEnabled(
                bool(self._no_sstart_table.selectionModel().selectedRows())))
        return w

    def _load_no_singing_start_table(self):
        """Fuellt die Kandidaten-Tabelle (Singing Calls ohne singing_start)."""
        rows = self.db.singing_no_start()
        table = self._no_sstart_table
        table.setUpdatesEnabled(False)
        table.setRowCount(0)
        table.setRowCount(len(rows))
        for r, row in enumerate(rows):
            sid, title, filename = row[0], row[1], row[2]
            bpm = row[3] if len(row) > 3 else 0
            name_item = QTableWidgetItem(title or filename)
            name_item.setData(Qt.UserRole, sid)
            table.setItem(r, 0, name_item)
            bpm_txt = f"{bpm:.0f}" if bpm and bpm > 0 else _t('pot_no_sstart_no_bpm')
            table.setItem(r, 1, QTableWidgetItem(bpm_txt))
        table.setUpdatesEnabled(True)
        self._ns_btn_selected.setEnabled(False)

    def _no_sstart_selected_ids(self):
        ids = []
        sm = self._no_sstart_table.selectionModel()
        if sm is None:
            return ids
        for idx in sm.selectedRows():
            it = self._no_sstart_table.item(idx.row(), 0)
            if it is not None and it.data(Qt.UserRole) is not None:
                ids.append(int(it.data(Qt.UserRole)))
        return ids

    def _check_start_genre_id(self):
        """ID des 'CHECK: START'-Marker-Genres (legt es bei Bedarf an)."""
        try:
            return self.db.insert_genre(CHECK_START_GENRE_NAME)
        except Exception as e:
            print(f"[CHECK:START] Genre konnte nicht angelegt werden: {e}")
            return -1

    def _check_beatsnap_genre_id(self):
        """ID des 'CHECK: BEATSNAP'-Marker-Genres (legt es bei Bedarf an)."""
        try:
            return self.db.insert_genre(CHECK_BEATSNAP_GENRE_NAME)
        except Exception as e:
            print(f"[CHECK:BEATSNAP] Genre konnte nicht angelegt werden: {e}")
            return -1

    def _singing_build_jobs(self, rows):
        """rows: (sid, title, filename, base_bpm) → (jobs, missing).
        jobs = [(sid, fp, name, bpm_hint)] fuer auffindbare Dateien; base_bpm
        geht als Tempo-Anker mit (None bei <= 0 → Detektor macht Auto-Detect)."""
        jobs, missing = [], []
        for row in rows:
            sid, title, filename = row[0], row[1], row[2]
            bpm = row[3] if len(row) > 3 else 0
            name = title or filename
            fp = self.paths.find_song_file(filename) if self.paths else ''
            if fp:
                hint = bpm if bpm and bpm > 0 else None
                jobs.append((sid, fp, name, hint))
            else:
                missing.append(name)
        return jobs, missing

    def _sstart_selected(self):
        ids = set(self._no_sstart_selected_ids())
        if not ids:
            return
        rows = [r for r in self.db.singing_no_start() if r[0] in ids]
        self._sstart_start(rows)

    def _sstart_open(self):
        self._sstart_start(self.db.singing_no_start())

    def _sstart_all(self):
        rows = self.db.singing_all_for_start()
        if not rows:
            QMessageBox.information(self, _t('pot_no_sstart'), _t('pot_no_sstart_none'))
            return
        # Extra-Rueckfrage: laeuft ueber ALLE Singing Calls und ueberschreibt
        # ggf. bereits gesetzte Startpunkte.
        reply = QMessageBox.warning(
            self, _t('pot_no_sstart_all'),
            _t('pot_no_sstart_all_warn', count=len(rows)),
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply != QMessageBox.Yes:
            return
        self._sstart_start(rows, skip_confirm=True)

    def _sstart_start(self, rows, skip_confirm=False):
        """Gemeinsamer Einstieg aller 3 Buttons (identisches Muster wie BPM).

        Ab TRIAL_MIN Songs Probelauf mit den ersten 5 zur Zeitschaetzung — diese
        5 werden dabei gleich ermittelt und eingetragen (nicht verworfen), der
        eigentliche Lauf verarbeitet danach nur den Rest. Kein Doppelrechnen."""
        TRIAL_MIN = 15
        if not rows:
            QMessageBox.information(self, _t('pot_no_sstart'), _t('pot_no_sstart_none'))
            return
        jobs, missing = self._singing_build_jobs(rows)
        self._sstart_missing = missing
        self._sstart_accum = (0, 0)
        self._sstart_unsure = []
        if not jobs:
            self._show_sstart_result(0, 0, [])
            return
        n = len(jobs)
        if not skip_confirm:
            msg = (_t('pot_no_sstart_confirm', count=n, sample=5) if n >= TRIAL_MIN
                   else _t('pot_no_sstart_confirm_direct', count=n))
            if QMessageBox.question(self, _t('pot_no_sstart'), msg,
                                    QMessageBox.Yes | QMessageBox.No) != QMessageBox.Yes:
                return

        if n < TRIAL_MIN:
            self._run_bulk_sstart(jobs)
            return

        import time as _time
        self._sstart_rest_jobs = jobs[5:]
        self._sstart_sample_t0 = _time.perf_counter()
        self._show_progress(_t('pot_measuring', current=0, total=5),
                            cancel_fn=self._cancel_bulk, title=_t('pot_no_sstart'))
        self._bulk_worker = _BulkSingingStartWorker(
            jobs[:5], self.db.db_path, self._check_start_genre_id())
        self._bulk_worker.progress.connect(
            lambda c, t, name: self._update_progress(
                _t('pot_measuring', current=c, total=5)))
        self._bulk_worker.finished.connect(self._on_sstart_sample_done)
        self._bulk_worker.start()

    def _on_sstart_sample_done(self, done, skipped, unsure):
        """Probelauf (erste 5) fertig — deren Start/Ende ist bereits geschrieben.
        Dauer fuer den Rest schaetzen und nachfragen; die 5 zaehlen mit."""
        cancelled = bool(self._bulk_worker
                         and getattr(self._bulk_worker, '_cancelled', False))
        self._close_progress()
        self._bulk_worker = None
        self._sstart_accum = (done, skipped)
        self._sstart_unsure = list(unsure or [])
        rest = getattr(self, '_sstart_rest_jobs', [])
        if cancelled or not rest:
            self._finalize_sstart(0, 0, [])
            return
        import time as _time
        elapsed = _time.perf_counter() - getattr(self, '_sstart_sample_t0',
                                                  _time.perf_counter())
        # markierte Songs sind bereits in done enthalten → nicht doppelt zaehlen
        per_song = elapsed / max(1, done + skipped)
        total_min = (per_song * len(rest)) / 60.0
        reply = QMessageBox.question(
            self, _t('pot_no_sstart'),
            _t('pot_fix_all_loop_timing', minutes=total_min, count=len(rest)),
            QMessageBox.Yes | QMessageBox.No)
        if reply != QMessageBox.Yes:
            # Abbruch — die 5 bleiben trotzdem eingetragen
            self._finalize_sstart(0, 0, [])
            return
        self._run_bulk_sstart(rest)

    def _run_bulk_sstart(self, jobs):
        self._show_progress(_t('pot_processing', current=0, total=len(jobs)),
                            cancel_fn=self._cancel_bulk, title=_t('pot_no_sstart'))
        self._bulk_worker = _BulkSingingStartWorker(
            jobs, self.db.db_path, self._check_start_genre_id())
        self._bulk_worker.progress.connect(
            lambda c, t, name: self._update_progress(
                _t('pot_processing', current=c, total=t) + f"\n{name}"))
        self._bulk_worker.finished.connect(self._on_sstart_bulk_done)
        self._bulk_worker.start()

    def _on_sstart_bulk_done(self, done, skipped, unsure):
        self._close_progress()
        self._bulk_worker = None
        self._finalize_sstart(done, skipped, list(unsure or []))

    def _finalize_sstart(self, done, skipped, unsure):
        """Ergebnis anzeigen (inkl. Probelauf-Anteil) + Tabelle/Badges auffrischen."""
        ad, ask = getattr(self, '_sstart_accum', (0, 0))
        all_marked = (getattr(self, '_sstart_unsure', []) or []) + (unsure or [])
        self._show_sstart_result(done + ad, skipped + ask, all_marked)
        self._sstart_missing = []
        self._sstart_accum = (0, 0)
        self._sstart_unsure = []
        self._load_no_singing_start_table()
        self.refresh()
        if self.on_bulk_done:
            self.on_bulk_done()

    def _show_sstart_result(self, done, skipped, marked):
        """Ergebnis-Dialog nach dem Anfang/Ende-Lauf. `marked` = Songs, die zwar
        gesetzt, aber als unsicher mit dem Genre 'CHECK: START' markiert wurden
        (To-Do fuer den Caller). `missing` (Audiodatei fehlt) wird aus dem
        gemerkten Zustand ergaenzt."""
        missing = getattr(self, '_sstart_missing', []) or []
        # markierte Songs sind bereits in done enthalten → nicht doppelt zaehlen
        total = done + skipped
        parts = []
        if done or skipped:
            parts.append(_t('pot_no_sstart_done', done=done, total=total, skipped=skipped))
        if marked:
            names = "\n".join("• " + m for m in marked[:20])
            if len(marked) > 20:
                names += "\n…"
            parts.append(_t('pot_no_sstart_marked_hint', count=len(marked)) + "\n" + names)
        if missing:
            names = "\n".join("• " + m for m in missing[:20])
            if len(missing) > 20:
                names += "\n…"
            parts.append(_t('pot_no_bpm_missing_hint', count=len(missing)) + "\n" + names)
        if not parts:
            parts.append(_t('pot_no_sstart_none'))
        QMessageBox.information(self, _t('pot_no_sstart'), "\n\n".join(parts))

    # ---- Sync-Punkte im Bulk setzen (Tab "Ohne SyncPunkte") ----

    def _syncpts_build_jobs(self, rows):
        """rows: (sid, title, filename) → (jobs, missing).

        jobs = [(sid, lyric_path, lyrics_file, name, start, end)]. Zwingende
        Voraussetzungen: BPM und Songanfang gesetzt, Lyric-Datei auffindbar.
        Ende = gespeichertes singing_end_m1, sonst aus 448 Beats abgeleitet —
        wie im Sync-Dialog ("Gespeicherte benutzen"). Wer durchfaellt, landet
        mit Grund in `missing` und wird gar nicht erst eingeplant.
        """
        jobs, missing = [], []
        for sid, title, filename in rows:
            name = title or filename
            song = self.db.get_by_id(sid)
            if not song:
                continue
            bpm = float(getattr(song, 'base_bpm', 0) or 0)
            props = self.db.get_properties(sid)
            try:
                start = float(props.get('singing_start_m1') or 0)
            except (TypeError, ValueError):
                start = 0.0
            if bpm <= 0:
                missing.append(f"{name} ({_t('pot_sync_skip_nobpm')})")
                continue
            if start <= 0:
                missing.append(f"{name} ({_t('pot_sync_skip_nostart')})")
                continue
            path = self.paths.find_lyric_file(song.lyrics_file) if self.paths else ''
            if not path:
                missing.append(f"{name} ({_t('pot_sync_skip_nofile')})")
                continue
            try:
                end = float(props.get('singing_end_m1') or 0)
            except (TypeError, ValueError):
                end = 0.0
            if end <= start:
                end = start + LyricsWidget._SINGING_BODY_BEATS * (60.0 / bpm)
            jobs.append((sid, path, song.lyrics_file, name, start, end))
        return jobs, missing

    # ---- Cue-Sheet-Suche auf ceder.net (Tab "Lyrics ergaenzen") ----

    def _ceder_enabled(self) -> bool:
        """Schalter network/ceder_lookup_enabled. Standard: AUS.

        Bewusst standardmaessig aus: die Funktion greift auf einen fremden
        Server zu, und solange keine Erlaubnis von Vic Ceder vorliegt, soll sie
        in einem Release nicht sichtbar sein. Zum Testen in der INI setzen.
        """
        if self._settings is None:
            return False
        return str(self._settings.value(
            "network/ceder_lookup_enabled", "false")).lower() == "true"

    def _ceder_labels_path(self) -> str:
        base = self.paths.app_dir if self.paths else perf.app_dir()
        return os.path.join(base, "config", "ceder_labels.json")

    def _ceder_start_lookup(self, tw):
        """Startet die Suche fuer die markierte Zeile."""
        if self._ceder_worker is not None and self._ceder_worker.isRunning():
            return
        rows = sorted(set(idx.row() for idx in tw['table'].selectedIndexes()))
        if not rows:
            QMessageBox.information(self, _t('pot_lyrics_fill'),
                                    _t('ceder_select_first'))
            return
        sid = tw['data'][rows[0]][0]
        song = self.db.get_by_id(sid)
        if not song:
            return
        self._ceder_song = song
        title = (song.title or "").strip()
        label = (getattr(song, "label", "") or "").strip()
        if not title:
            QMessageBox.information(self, _t('pot_lyrics_fill'),
                                    _t('ceder_no_title'))
            return
        self._show_progress(_t('ceder_searching').format(title=title),
                            title=_t('pot_lyrics_fill'))
        # intern#126: ohne eigenes Label das eindeutige Katalog-Label mitsuchen
        label = song_catalog.label_hint(
            title, label, self.paths.app_dir if self.paths else "")
        self._ceder_worker = _CederLookupWorker(
            title, label, self._ceder_labels_path())
        self._ceder_worker.finished_ok.connect(self._ceder_on_results)
        self._ceder_worker.failed.connect(self._ceder_on_failed)
        self._ceder_worker.start()

    def _ceder_on_failed(self, msg):
        self._close_progress()
        QMessageBox.warning(self, _t('pot_lyrics_fill'),
                            _t('ceder_error').format(msg=msg))

    def _ceder_on_results(self, cands, info):
        self._close_progress()
        song = getattr(self, "_ceder_song", None)
        if song is None:
            return
        if not cands:
            QMessageBox.information(self, _t('pot_lyrics_fill'),
                                    _t('ceder_no_hits'))
            return
        dlg = _CederCandidateDialog(cands, info, song.title,
                                    getattr(song, "label", ""), self)
        if dlg.exec() != QDialog.Accepted:
            return
        cand = dlg.selected()
        if cand is None:
            return
        self._show_progress(_t('ceder_downloading'),
                            title=_t('pot_lyrics_fill'))
        self._ceder_dl_worker = _CederDownloadWorker(
            cand.record_id, song.title)
        self._ceder_dl_worker.finished_ok.connect(self._ceder_on_downloaded)
        self._ceder_dl_worker.failed.connect(self._ceder_on_failed)
        self._ceder_dl_worker.start()

    def _ceder_on_downloaded(self, html_text, record_id):
        self._close_progress()
        song = getattr(self, "_ceder_song", None)
        if song is None or not self.paths:
            return
        # Dateiname aus Titel + Ceder-RecordId: eindeutig und nachvollziehbar
        safe = re.sub(r"[^A-Za-z0-9 _.-]+", "", (song.title or "cuesheet")).strip()
        safe = re.sub(r"\s+", "", safe) or "cuesheet"
        fname = f"{safe}-ceder{record_id}.html"
        target = os.path.join(self.paths.lyrics_dir, fname)
        try:
            os.makedirs(self.paths.lyrics_dir, exist_ok=True)
            with open(target, "w", encoding="utf-8") as f:
                f.write(html_text)
            self.db.update_lyrics_file(song.id, fname)
        except Exception as e:
            QMessageBox.warning(self, _t('pot_lyrics_fill'),
                                _t('ceder_save_failed').format(msg=str(e)))
            return
        QMessageBox.information(
            self, _t('pot_lyrics_fill'),
            _t('ceder_saved').format(file=fname, title=song.title or ""))
        self._load_check('singing_no_lyrics_fill')

    def _syncpts_start_every(self):
        """Komplettlauf ueber ALLE Singing Calls mit Lyrics.

        Anders als die beiden anderen Knoepfe trifft dieser auch Songs, die
        bereits Sync-Punkte haben — und rechnet sie neu. Das kann handgesetzte
        oder von Hand korrigierte Anker verwerfen, deshalb wird vorher gezaehlt
        und ausdruecklich nachgefragt. Ohne die Zahl waere die Rueckfrage eine
        Formalie: erst sie macht sichtbar, wie viel Arbeit auf dem Spiel steht.
        """
        rows = self.db.singing_with_lyrics()
        if not rows:
            QMessageBox.information(self, _t('pot_singing_no_sync_points'),
                                    _t('pot_sync_none'))
            return
        have = self.db.songs_with_sync_anchors([r[0] for r in rows])
        if have:
            answer = QMessageBox.warning(
                self, _t('pot_fix_every_sync'),
                _t('pot_fix_every_confirm', total=len(rows), existing=len(have)),
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if answer != QMessageBox.Yes:
                return
        self._syncpts_start(rows)

    def _syncpts_start(self, rows):
        """Gemeinsamer Einstieg beider Buttons — Muster wie beim Songanfang.

        Ab TRIAL_MIN Songs erst 5 als Probelauf, Zeit stoppen, Rest hochrechnen
        und nachfragen. Die 5 sind dann bereits geschrieben und laufen nicht
        erneut (jobs[5:])."""
        TRIAL_MIN = 15
        if not rows:
            QMessageBox.information(self, _t('pot_singing_no_sync_points'),
                                    _t('pot_sync_none'))
            return
        jobs, missing = self._syncpts_build_jobs(rows)
        self._syncpts_missing = missing
        self._syncpts_accum = (0, 0)
        self._syncpts_skipped = []
        if not jobs:
            self._show_syncpts_result(0, 0, [])
            return
        n = len(jobs)
        msg = (_t('pot_sync_confirm', count=n, sample=5) if n >= TRIAL_MIN
               else _t('pot_sync_confirm_direct', count=n))
        if QMessageBox.question(self, _t('pot_singing_no_sync_points'), msg,
                                QMessageBox.Yes | QMessageBox.No) != QMessageBox.Yes:
            return

        if n < TRIAL_MIN:
            self._run_bulk_syncpts(jobs)
            return

        import time as _time
        self._syncpts_rest_jobs = jobs[5:]
        self._syncpts_sample_t0 = _time.perf_counter()
        self._show_progress(_t('pot_measuring', current=0, total=5),
                            cancel_fn=self._cancel_bulk,
                            title=_t('pot_singing_no_sync_points'))
        self._bulk_worker = _BulkSyncPointsWorker(
            jobs[:5], self.db.db_path, self._sync_sections())
        self._bulk_worker.progress.connect(
            lambda c, t, name: self._update_progress(
                _t('pot_measuring', current=c, total=5)))
        self._bulk_worker.finished.connect(self._on_syncpts_sample_done)
        self._bulk_worker.start()

    def _sync_sections(self):
        """Keyword-Listen der Abschnitts-Erkennung (im Main-Thread lesen —
        der Worker bekommt sie fertig uebergeben)."""
        try:
            return singing_sections.load_sections(
                os.path.join(perf.app_dir(), "config", "singing_sections.json"))
        except Exception:
            return None

    def _on_syncpts_sample_done(self, done, skipped, skipped_names):
        """Probelauf (erste 5) fertig — deren Anker stehen bereits in der DB."""
        cancelled = bool(self._bulk_worker
                         and getattr(self._bulk_worker, '_cancelled', False))
        self._close_progress()
        self._bulk_worker = None
        self._syncpts_accum = (done, skipped)
        self._syncpts_skipped = list(skipped_names or [])
        rest = getattr(self, '_syncpts_rest_jobs', [])
        if cancelled or not rest:
            self._finalize_syncpts(0, 0, [])
            return
        import time as _time
        elapsed = _time.perf_counter() - getattr(self, '_syncpts_sample_t0',
                                                 _time.perf_counter())
        per_song = elapsed / max(1, done + skipped)
        total_min = (per_song * len(rest)) / 60.0
        reply = QMessageBox.question(
            self, _t('pot_singing_no_sync_points'),
            _t('pot_fix_all_loop_timing', minutes=total_min, count=len(rest)),
            QMessageBox.Yes | QMessageBox.No)
        if reply != QMessageBox.Yes:
            # Abbruch — die 5 bleiben trotzdem eingetragen
            self._finalize_syncpts(0, 0, [])
            return
        self._run_bulk_syncpts(rest)

    def _run_bulk_syncpts(self, jobs):
        self._show_progress(_t('pot_processing', current=0, total=len(jobs)),
                            cancel_fn=self._cancel_bulk,
                            title=_t('pot_singing_no_sync_points'))
        self._bulk_worker = _BulkSyncPointsWorker(
            jobs, self.db.db_path, self._sync_sections())
        self._bulk_worker.progress.connect(
            lambda c, t, name: self._update_progress(
                _t('pot_processing', current=c, total=t) + f"\n{name}"))
        self._bulk_worker.finished.connect(self._on_syncpts_bulk_done)
        self._bulk_worker.start()

    def _on_syncpts_bulk_done(self, done, skipped, skipped_names):
        self._close_progress()
        self._bulk_worker = None
        self._finalize_syncpts(done, skipped, list(skipped_names or []))

    def _finalize_syncpts(self, done, skipped, skipped_names):
        """Ergebnis anzeigen (inkl. Probelauf-Anteil) + Tabelle/Badges auffrischen."""
        ad, ask = getattr(self, '_syncpts_accum', (0, 0))
        all_skipped = (getattr(self, '_syncpts_skipped', []) or []) + (skipped_names or [])
        self._show_syncpts_result(done + ad, skipped + ask, all_skipped)
        self._syncpts_missing = []
        self._syncpts_accum = (0, 0)
        self._syncpts_skipped = []
        self._load_check('singing_no_sync_points')
        self.refresh()
        if self.on_bulk_done:
            self.on_bulk_done()

    def _show_syncpts_result(self, done, skipped, skipped_names):
        """Ergebnis-Dialog. `missing` = an den Voraussetzungen gescheitert
        (BPM/Songanfang/Lyric-Datei), `skipped_names` = im Lauf gescheitert
        (kein Text / keine Abschnitte). Beides mit Grund je Song."""
        missing = getattr(self, '_syncpts_missing', []) or []
        total = done + skipped + len(missing)
        parts = []
        if total:
            parts.append(_t('pot_sync_done', done=done, total=total,
                            skipped=skipped + len(missing)))
        for names, hint_key in ((skipped_names, 'pot_sync_skipped_hint'),
                                (missing, 'pot_sync_missing_hint')):
            if not names:
                continue
            txt = "\n".join("• " + m for m in names[:20])
            if len(names) > 20:
                txt += "\n…"
            parts.append(_t(hint_key, count=len(names)) + "\n" + txt)
        if not parts:
            parts.append(_t('pot_sync_none'))
        QMessageBox.information(self, _t('pot_singing_no_sync_points'),
                                "\n\n".join(parts))

    # ---- Metadaten-Tab Handlers (BL-114) ----

    def _on_meta_export(self):
        dlg = _MetaFieldSelectDialog(self)
        if dlg.exec() != QDialog.Accepted:
            return
        selected = dlg.selected()
        if not selected:
            return

        # Songs mit fehlenden Feldern sammeln
        missing_map = {}  # song_id → entry-dict
        field_counts = {}

        for key, label, source in selected:
            if source == 'songs_field':
                rows = self.db.get_songs_missing_song_field(key)
            elif source == 'property':
                rows = self.db.get_songs_missing_property(key)
            elif source == 'rating':
                rows = self.db.get_songs_missing_rating(key)
            else:
                rows = self.db.get_songs_missing_genre()

            field_counts[label] = len(rows)
            for sid, title, filename in rows:
                if sid not in missing_map:
                    song = self.db.get_by_id(sid)
                    missing_map[sid] = {
                        'id': sid,
                        'title': title or filename,
                        'filename': filename,
                        'artist': song.artist if song else '',
                        'label': song.label if song else '',
                        'missing': [],
                    }
                missing_map[sid]['missing'].append(key)

        if not missing_map:
            QMessageBox.information(self, _t('pot_tab_metadata'),
                                    _t('pot_meta_nothing_missing'))
            return

        genres_available = []
        if any(src == 'genre' for _, _, src in selected):
            genres_available = [name for _, name in self.db.get_all_genres()]

        export_data = {
            'export_date': date.today().isoformat(),
            'fields': [k for k, _, _ in selected],
            'genres_available': genres_available,
            'songs': list(missing_map.values()),
        }

        filepath, _ = QFileDialog.getSaveFileName(
            self, _t('pot_meta_export'), '',
            'JSON (*.json)')
        if not filepath:
            return

        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(export_data, f, ensure_ascii=False, indent=2)

        lines = [_t('pot_meta_export_done', count=len(missing_map),
                     path=os.path.basename(filepath)),
                 _t('pot_meta_export_field_stats_header')]
        for lbl, cnt in field_counts.items():
            lines.append(f"  {lbl}: {cnt}")
        self._lbl_meta_stats.setText("\n".join(lines))
        self._last_export_path = filepath

    def _on_meta_prompt(self):
        all_genres = [name for _, name in self.db.get_all_genres()]
        genre_list = ", ".join(f'"{g}"' for g in all_genres) if all_genres else "(no genres in database)"
        prompt = (
            "You receive a JSON file with square dance songs.\n"
            "For each song, the fields that need to be filled are listed in \"missing\".\n"
            "Please fill in ONLY those fields — leave everything else untouched.\n\n"
            "=== FIELD RULES ===\n\n"
            "• \"original_artist\": Artist of the original (non-square-dance) recording.\n"
            "  If unknown: leave empty (\"\") — do NOT invent.\n\n"
            "• \"release_year\": Year the original song was released (not the square dance version).\n"
            "  If unknown: leave empty (\"\") — do NOT invent.\n\n"
            "• \"genre\": Choose exclusively from this list:\n"
            f"  {genre_list}\n"
            "  Multiple genres as JSON array: [\"Country\", \"Hoedown\"]\n"
            "  If no genre fits: leave empty (\"\").\n\n"
            "• \"quality\" (integer 1–10): How well can the square dance CALLER perform this song?\n"
            "  This is the caller's personal skill assessment — impossible for an AI to know.\n"
            "  ALWAYS output 6 for every song with quality in \"missing\". No exceptions.\n"
            "  The caller will adjust the values themselves afterwards.\n\n"
            "• \"err\" (integer 1–4): Emotional Response Rating — how strongly do DANCERS\n"
            "  connect with this song emotionally?\n"
            "  You MUST fill this field for every song that has \"err\" in \"missing\".\n"
            "  Never omit it, never leave it empty — always pick the most fitting value.\n"
            "  Scale:\n"
            "    1 = Peak      — very well-known, strong sing-along factor, timeless classic,\n"
            "                    creates a special shared moment, dancers will remember it\n"
            "    2 = Build-up  — known and liked, good energy, builds toward a highlight\n"
            "    3 = Baseline  — solid standard song, neutral or moderate dancer response\n"
            "    4 = Cool-down — gentle, relaxing, low emotional intensity, background feel\n"
            "  Ask yourself: Is the original song famous and beloved by a wide audience?\n"
            "  Does it have a catchy chorus people sing along to? Is it a crowd favourite?\n"
            "  When in doubt between two values, pick the lower number (stronger response).\n\n"
            "=== OUTPUT FORMAT ===\n"
            "Return a JSON array — id, title and the fields you filled, no other keys.\n"
            "Copy \"id\" and \"title\" EXACTLY as given in the input, character for\n"
            "character — never change, renumber or reorder them. The title is used to\n"
            "verify that every value lands on the right song.\n"
            "[\n"
            "  {\"id\": 42, \"title\": \"Delilah\", \"original_artist\": \"Tom Jones\", \"release_year\": \"1968\", \"err\": 1},\n"
            "  {\"id\": 71, \"title\": \"Cotton Eye Joe\", \"genre\": [\"Country\", \"Hoedown\"], \"quality\": 6}\n"
            "]"
        )
        dlg = QDialog(self)
        dlg.setWindowTitle(_t('pot_meta_prompt'))
        dlg.setMinimumSize(560, 520)
        layout = QVBoxLayout(dlg)
        txt = QTextEdit()
        txt.setPlainText(prompt)
        txt.setReadOnly(True)
        layout.addWidget(txt)
        btn_row = QHBoxLayout()
        btn_copy = QPushButton(_t('pot_meta_copy_prompt'))
        btn_copy.clicked.connect(lambda: QApplication.clipboard().setText(prompt))
        btn_close = QPushButton(_t('btn_cancel'))
        btn_close.clicked.connect(dlg.accept)
        btn_row.addWidget(btn_copy)
        btn_row.addStretch()
        btn_row.addWidget(btn_close)
        layout.addLayout(btn_row)
        dlg.exec()

    def _on_meta_import(self):
        filepath, _ = QFileDialog.getOpenFileName(
            self, _t('pot_meta_import'), '', 'JSON (*.json)')
        if not filepath:
            return

        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except Exception as e:
            QMessageBox.warning(self, _t('error'), str(e))
            return

        songs = data if isinstance(data, list) else data.get('songs', [])
        known_genres = {name.lower(): (gid, name)
                        for gid, name in self.db.get_all_genres()}

        # Feldschlüssel → Label-Mapping
        field_labels = {k: lbl for k, lbl, _ in _META_EXPORT_FIELDS}

        preview_rows = []
        # intern#108: Zuordnung ueber die id pruefen -- die Datei soll den
        # Titel unveraendert mitliefern (siehe Prompt). Weicht er ab, hat z. B.
        # eine KI Werte an die falsche id gehaengt -> Zeile warnen, nicht
        # vorab anhaken. Ohne Titel ist die Zuordnung nicht pruefbar.
        titles_missing = 0
        for entry in songs:
            sid = entry.get('id')
            if not sid:
                continue
            song = self.db.get_by_id(sid)
            title = (song.title or song.filename) if song else f"ID {sid}"
            file_title = str(entry.get('title') or '').strip()
            id_warning = ''
            if song is None:
                id_warning = _t('pot_meta_import_id_unknown')
            elif not file_title:
                titles_missing += 1
            elif not song_match.same_song_title(file_title, song.title or '',
                                                song.filename or ''):
                id_warning = _t('pot_meta_import_title_mismatch',
                                title=file_title)
            for key, val in entry.items():
                if key in ('id', 'title', 'filename', 'artist', 'label', 'missing'):
                    continue
                # 0 bei quality/err bedeutet "unbewertet" — nicht importieren
                if key in ('quality', 'err'):
                    if not val:
                        continue
                elif not val and val != 0:
                    continue
                lbl = field_labels.get(key, key)
                if key == 'genre':
                    genres = val if isinstance(val, list) else [val]
                    unknown = [g for g in genres if g.lower() not in known_genres]
                    value_str = ', '.join(genres)
                    warning = (f"Unbekannt: {', '.join(unknown)}" if unknown else '')
                else:
                    value_str = str(val)
                    warning = ''
                if id_warning:
                    warning = f"{id_warning} {warning}".strip()
                preview_rows.append((sid, title, lbl, value_str, warning))

        if not preview_rows:
            QMessageBox.information(self, _t('pot_meta_import'),
                                    _t('pot_meta_import_empty'))
            return

        notice = (_t('pot_meta_import_no_titles', count=titles_missing)
                  if titles_missing else '')
        prev_dlg = _MetaImportPreviewDialog(preview_rows, self, notice=notice)
        if prev_dlg.exec() != QDialog.Accepted:
            return

        confirmed = prev_dlg.confirmed()
        field_label_to_key = {lbl: k for k, lbl, _ in _META_EXPORT_FIELDS}
        stats = {}
        skipped = {}

        for sid, field_lbl, value_str in confirmed:
            key = field_label_to_key.get(field_lbl, field_lbl)
            try:
                if key in ('artist', 'label'):
                    self.db.update_song_simple_field(sid, key, value_str)
                    stats[field_lbl] = stats.get(field_lbl, 0) + 1
                elif key in ('quality', 'err'):
                    val_int = int(float(value_str))
                    self.db.update_song_simple_field(sid, key, val_int)
                    stats[field_lbl] = stats.get(field_lbl, 0) + 1
                elif key in ('original_artist', 'release_year'):
                    self.db.set_property(sid, key, value_str)
                    stats[field_lbl] = stats.get(field_lbl, 0) + 1
                elif key == 'genre':
                    genres = [g.strip() for g in value_str.split(',')]
                    existing_ids = {gid for gid, _ in self.db.get_genres_for_song(sid)}
                    added = 0
                    for gname in genres:
                        match = known_genres.get(gname.lower())
                        if match:
                            gid, _ = match
                            if gid not in existing_ids:
                                self.db.set_genres_for_song(
                                    sid, list(existing_ids | {gid}))
                                existing_ids.add(gid)
                                added += 1
                        else:
                            skipped[gname] = skipped.get(gname, 0) + 1
                    if added:
                        stats[field_lbl] = stats.get(field_lbl, 0) + added
            except Exception as e:
                print(f"[MetaImport] Fehler Song #{sid} Feld {key}: {e}")

        lines = [_t('pot_meta_import_done', applied=len(confirmed)),
                 _t('pot_meta_import_field_stats_header')]
        for lbl, cnt in stats.items():
            lines.append(f"  {lbl}: {cnt}")
        if skipped:
            lines.append(_t('pot_meta_unknown_genres', genres=', '.join(skipped)))
        self._lbl_meta_stats.setText("\n".join(lines))
        self.refresh()

    # ---- CSV-Abgleich (BL-114) ----

    def _on_meta_csv(self):
        # 1. Feld-Auswahl
        dlg_fields = _MetaFieldSelectDialog(self)
        if dlg_fields.exec() != QDialog.Accepted:
            return
        selected = dlg_fields.selected()
        if not selected:
            return

        # 2. Quelle: mitgelieferter Song-Katalog (intern#126) oder andere CSV
        app_dir = self.paths.app_dir if self.paths else ""
        catalog = song_catalog.get_catalog(app_dir)
        use_other = catalog is None
        if catalog is not None:
            box = QMessageBox(self)
            box.setWindowTitle(_t('pot_meta_csv_title'))
            box.setText(_t('pot_meta_csv_source_text', count=len(catalog)))
            btn_cat = box.addButton(_t('pot_meta_csv_use_catalog'), QMessageBox.AcceptRole)
            btn_other = box.addButton(_t('pot_meta_csv_other_file'), QMessageBox.ActionRole)
            box.addButton(QMessageBox.Cancel)
            box.setDefaultButton(btn_cat)
            box.exec()
            if box.clickedButton() not in (btn_cat, btn_other):
                return
            use_other = box.clickedButton() is btn_other
        if use_other:
            med_dir = os.path.join(app_dir, song_catalog.CATALOG_DIR) if app_dir else ""
            default_dir = med_dir if os.path.isdir(med_dir) else ""
            filepath, _ = QFileDialog.getOpenFileName(
                self, _t('pot_meta_csv'), default_dir, "CSV-Dateien (*.csv);;Alle Dateien (*)")
            if not filepath:
                return
            # 3. CSV laden und indizieren (Format wie song_catalog.COLUMNS)
            try:
                catalog = song_catalog.SongCatalog.from_csv(filepath)
            except Exception as e:
                QMessageBox.warning(self, _t('error'), str(e))
                return

        # 4. DB-Songs mit fehlenden Feldern laden
        missing_map = {}   # song_id → {title, label_db, missing_keys}
        for key, label, source in selected:
            if source == 'songs_field':
                rows = self.db.get_songs_missing_song_field(key)
            elif source == 'property':
                rows = self.db.get_songs_missing_property(key)
            else:
                rows = self.db.get_songs_missing_genre()
            for sid, title, filename in rows:
                if sid not in missing_map:
                    song = self.db.get_by_id(sid)
                    missing_map[sid] = {
                        'song_id': sid,
                        'title': title or filename,
                        'label_db': (song.label or '') if song else '',
                        'missing_keys': set(),
                    }
                missing_map[sid]['missing_keys'].add(key)

        if not missing_map:
            QMessageBox.information(self, _t('pot_meta_csv_title'),
                                    _t('pot_meta_csv_no_matches'))
            return

        # 5. Matching: exakt → Label/Nummer → Fuzzy
        known_genres = {name.lower(): name for _, name in self.db.get_all_genres()}

        def _csv_field_value(cr, key):
            """Liefert den relevanten Wert eines Katalogeintrags fuer ein Feld."""
            if key == 'artist':
                return cr.caller
            if key == 'genre':
                # Kommaseparierte Genres → nur bekannte behalten
                matched = [known_genres[g.lower()] for g in cr.genres
                           if g.lower() in known_genres]
                return ', '.join(matched)
            if key == 'original_artist':
                return cr.original_artist
            if key == 'release_year':
                return cr.release_year
            if key == 'label':
                return cr.label_field
            return ''

        match_rows = []
        for entry in missing_map.values():
            sid = entry['song_id']
            # Exakter Titel-Treffer
            hits = catalog.by_title(entry['title'])
            score = 1.0

            # Label+Nummer als Alternative, wenn der Titel nicht exakt trifft.
            # intern#108: Nummer UND Label muessen zusammen passen.
            label_hits = catalog.by_label_number(entry['label_db'])
            if label_hits and not hits:
                hits = label_hits
                score = 0.95

            # Fuzzy-Suche falls noch kein Treffer
            if not hits:
                hits, score = catalog.by_title_fuzzy(entry['title'])

            if not hits:
                continue

            # Felder aus CSV zusammenführen (eindeutig vs. mehrdeutig)
            fields = {}
            for key in entry['missing_keys']:
                values_set = []
                seen = []
                for cr in hits:
                    v = _csv_field_value(cr, key)
                    if v and v not in seen:
                        seen.append(v)
                        values_set.append(v)
                if not values_set:
                    continue
                fields[key] = {
                    'values': values_set,
                    'chosen': values_set[0] if len(values_set) == 1 else None,
                }

            if not fields:
                continue

            match_rows.append({
                'song_id': sid,
                'title': entry['title'],
                'label_db': entry['label_db'],
                'match_score': score,
                'fields': fields,
            })

        if not match_rows:
            QMessageBox.information(self, _t('pot_meta_csv_title'),
                                    _t('pot_meta_csv_no_matches'))
            return

        # 6. Preview-Dialog
        dlg = _CsvMatchDialog(match_rows, selected, self.db, self)
        if dlg.exec() != QDialog.Accepted:
            return

        # 7. Änderungen übernehmen
        changes = dlg.confirmed_changes()
        all_genres = {name.lower(): name for _, name in self.db.get_all_genres()}
        stats = {}
        songs_changed = set()

        for sid, key, source, value in changes:
            try:
                if source == 'songs_field':
                    self.db.update_song_simple_field(sid, key, value)
                elif source == 'property':
                    self.db.set_property(sid, key, value)
                elif source == 'genre':
                    genres = [g.strip() for g in value.split(',')]
                    existing_ids = {gid for gid, _ in self.db.get_genres_for_song(sid)}
                    for gname in genres:
                        match = all_genres.get(gname.lower())
                        if match:
                            gid_row = next((gid for gid, n in self.db.get_all_genres()
                                            if n.lower() == gname.lower()), None)
                            if gid_row and gid_row not in existing_ids:
                                self.db.set_genres_for_song(
                                    sid, list(existing_ids | {gid_row}))
                                existing_ids.add(gid_row)
                stats[key] = stats.get(key, 0) + 1
                songs_changed.add(sid)
            except Exception as e:
                print(f"[CsvMatch] Fehler Song #{sid} Feld {key}: {e}")

        field_labels = {k: lbl for k, lbl, _ in selected}
        lines = [_t('pot_meta_csv_done',
                    applied=sum(stats.values()), songs=len(songs_changed)),
                 _t('pot_meta_csv_field_stats_header')]
        for k, cnt in stats.items():
            lines.append(f"  {field_labels.get(k, k)}: {cnt}")
        self._lbl_meta_stats.setText("\n".join(lines))
        self.refresh()

    # ---- Progress-Dialog Helpers ----

    def _show_progress(self, text, cancel_fn=None, title=None):
        dlg = QProgressDialog(text, _t('pot_cancel'), 0, 0, self)
        dlg.setWindowTitle(title or _t('pot_fix_all_loop'))
        dlg.setWindowModality(Qt.WindowModal)
        dlg.setMinimumDuration(0)
        dlg.setAutoClose(False)
        dlg.setAutoReset(False)
        if cancel_fn:
            dlg.canceled.connect(cancel_fn)
        dlg.show()
        self._progress_dlg = dlg

    def _update_progress(self, text):
        if self._progress_dlg:
            self._progress_dlg.setLabelText(text)
            QApplication.processEvents()

    def _close_progress(self):
        if self._progress_dlg:
            self._progress_dlg.close()
            self._progress_dlg = None

    def _cancel_bulk(self):
        if self._timing_worker:
            self._timing_worker.cancel()
        if self._bulk_worker:
            self._bulk_worker.cancel()
        self._close_progress()

    def _on_bulk_done(self, done, skipped):
        self._close_progress()
        self._bulk_worker = None
        total = done + skipped
        QMessageBox.information(
            self, _t('pot_fix_all_loop'),
            _t('pot_fix_all_done', done=done, total=total, skipped=skipped)
        )
        self.refresh()
        # Einmaliger Hauptfenster-Refresh (Song-Liste + aktueller Song), damit
        # die geaenderten Loops sofort sichtbar sind — NICHT pro Song.
        if self.on_bulk_done:
            self.on_bulk_done()

    # ==================================================================
    # BL-172: „Mach alles schoen" — Heilungsfunktionen verkettet ausfuehren
    # ==================================================================

    def _beautify_actions(self):
        """Liste aller verkettbaren Heilungsaktionen mit Fallzahl + Runner.

        Nur gap-basierte Varianten (offene Faelle), NICHT die „ALLE
        neu durchrechnen"-Buttons. Meta/Quality-Filler und Loop-Optimieren sind
        bewusst nicht dabei (interaktiv bzw. reine ALLE-Variante)."""
        specs = []

        def add(key, label, count, runner, destructive=False):
            specs.append({'key': key, 'label': label, 'count': int(count or 0),
                          'runner': runner, 'destructive': destructive})

        add('bpm', _t('pot_bf_bpm'),
            len(self.db.potential_no_bpm()), self._bf_run_bpm)
        add('loop', _t('pot_bf_loop'),
            self.db.potential_count('pattern_no_loop'), self._bf_run_loop)
        add('beatsnap', _t('pot_bf_beatsnap'),
            self.db.potential_count('loop_no_beatsnap'), self._bf_run_beatsnap)
        add('sstart', _t('pot_bf_sstart'),
            len(self.db.singing_no_start()), self._bf_run_sstart)
        add('sync', _t('pot_bf_sync'),
            self.db.potential_count('singing_no_sync_points'), self._bf_run_sync)
        add('locations', _t('pot_bf_locations'),
            self.db.potential_count('location_no_history'),
            self._bf_run_locations, destructive=True)
        add('orphaned', _t('pot_bf_orphaned'),
            self.db.potential_count('history_orphaned'),
            self._bf_run_orphaned, destructive=True)
        return specs

    def _on_beautify_clicked(self):
        """Oeffnet den Auswahl-Dialog und startet danach den Lauf."""
        if getattr(self, '_bf_worker', None) is not None:
            return  # laeuft bereits
        specs = self._beautify_actions()
        if not any(s['count'] > 0 for s in specs):
            QMessageBox.information(self, _t('pot_beautify_title'),
                                    _t('pot_beautify_nothing'))
            return
        dlg = _BeautifyDialog(specs, self,
                              loop_preset_names=self._loop_preset_names())
        if dlg.exec() != QDialog.Accepted:
            return
        name = dlg.loop_preset_name()
        self._bf_loop_preset = self._load_loop_preset(name) if name else None
        keys = dlg.selected_keys()
        selected = [s for s in specs if s['key'] in keys and s['count'] > 0]
        if not selected:
            return
        self._beautify_run(selected)

    def _beautify_run(self, selected):
        self._bf_queue = selected
        self._bf_results = []       # [(label, done, skipped)]
        self._bf_cancelled = False
        self._bf_worker = None
        self._bf_index = -1
        self._bf_dlg = _BeautifyProgressDialog(
            [s['label'] for s in selected], self._beautify_cancel, self)
        self._bf_dlg.show()
        self._beautify_next()

    def _beautify_next(self):
        self._bf_index += 1
        if self._bf_cancelled or self._bf_index >= len(self._bf_queue):
            self._beautify_finish()
            return
        self._bf_dlg.set_running(self._bf_index)
        # Runner ruft garantiert genau einmal _beautify_step_done auf.
        self._bf_queue[self._bf_index]['runner']()

    def _beautify_run_worker(self, worker):
        """Startet einen Bulk-Worker und verdrahtet Fortschritt + Abschluss auf
        den Orchestrator (statt auf die Einzel-Dialoge der Tabs)."""
        self._bf_worker = worker
        worker.progress.connect(
            lambda c, t, name: self._bf_dlg and self._bf_dlg.set_detail(
                f"{c}/{t}  {name}"))
        # finished-Signaturen variieren (done,skipped[,extra]) → *a abfangen
        worker.finished.connect(
            lambda *a: self._beautify_step_done(
                a[0] if len(a) > 0 else 0, a[1] if len(a) > 1 else 0))
        worker.start()

    def _beautify_step_done(self, done, skipped):
        self._bf_worker = None
        spec = self._bf_queue[self._bf_index]
        self._bf_results.append((spec['label'], int(done), int(skipped)))
        if self._bf_dlg:
            self._bf_dlg.set_done(self._bf_index, empty=(done == 0 and skipped == 0))
        self._beautify_next()

    def _beautify_cancel(self):
        self._bf_cancelled = True
        if getattr(self, '_bf_worker', None) is not None:
            self._bf_worker.cancel()
        # Der laufende Worker meldet danach finished → Kette bricht in _beautify_next ab.

    def _beautify_finish(self):
        if self._bf_dlg:
            self._bf_dlg.close()
            self._bf_dlg = None
        lines = [_t('pot_beautify_result_line', label=lbl, done=d, skipped=s)
                 for lbl, d, s in getattr(self, '_bf_results', [])]
        if self._bf_cancelled:
            lines.append("")
            lines.append(_t('pot_beautify_cancelled'))
        QMessageBox.information(self, _t('pot_beautify_result_title'),
                                "\n".join(lines) if lines else _t('pot_beautify_nothing'))
        self._bf_worker = None
        self.refresh()
        if self.on_bulk_done:
            self.on_bulk_done()

    # ---- Einzel-Runner (bauen Jobs, starten Worker bzw. laufen synchron) ----

    def _bf_run_bpm(self):
        jobs, _missing = self._bpm_build_jobs(self.db.potential_no_bpm())
        if not jobs:
            self._beautify_step_done(0, 0)
            return
        self._beautify_run_worker(_BulkBpmWorker(jobs, self.db.db_path))

    def _bf_run_loop(self):
        jobs = []
        for sid, title, filename in self.db.potential_pattern_no_loop():
            song = self.db.get_by_id(sid)
            if not song:
                continue
            fp = self.paths.find_song_file(filename) if self.paths else ''
            if not fp:
                continue
            jobs.append((sid, fp, song.base_bpm, title or filename))
        if not jobs:
            self._beautify_step_done(0, 0)
            return
        worker = _BulkAutoLoopWorker(
            jobs, preset=getattr(self, '_bf_loop_preset', None))
        worker.loop_found.connect(self._store_found_loop)
        self._beautify_run_worker(worker)

    def _bf_run_beatsnap(self):
        jobs = []
        for sid, title, filename in self.db.potential_loop_no_beatsnap():
            song = self.db.get_by_id(sid)
            if not song:
                continue
            fp = self.paths.find_song_file(filename) if self.paths else ''
            if not fp:
                continue
            jobs.append((sid, fp, song.base_bpm, song.loop_in, song.loop_out,
                         title or filename))
        if not jobs:
            self._beautify_step_done(0, 0)
            return
        self._beautify_run_worker(_BulkBeatSnapWorker(
            jobs, self.db.db_path, self._check_beatsnap_genre_id()))

    def _bf_run_sstart(self):
        jobs, _missing = self._singing_build_jobs(self.db.singing_no_start())
        if not jobs:
            self._beautify_step_done(0, 0)
            return
        self._beautify_run_worker(_BulkSingingStartWorker(
            jobs, self.db.db_path, self._check_start_genre_id()))

    def _bf_run_sync(self):
        jobs, _missing = self._syncpts_build_jobs(
            self.db.potential_singing_no_sync_points())
        if not jobs:
            self._beautify_step_done(0, 0)
            return
        self._beautify_run_worker(_BulkSyncPointsWorker(
            jobs, self.db.db_path, self._sync_sections()))

    def _bf_run_locations(self):
        deleted = 0
        for lid, _name in self.db.potential_location_no_history():
            try:
                self.db.delete_location(lid, delete_history=False)
                deleted += 1
            except Exception as e:
                print(f"[Beautify] Fehler bei Lokation #{lid}: {e}")
        self._beautify_step_done(deleted, 0)

    def _bf_run_orphaned(self):
        try:
            deleted = self.db.potential_cleanup_orphaned_history()
        except Exception as e:
            print(f"[Beautify] Fehler beim Historie-Aufraeumen: {e}")
            deleted = 0
        self._beautify_step_done(deleted, 0)
