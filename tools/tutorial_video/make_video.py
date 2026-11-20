"""Tutorial-Video aus einem Szenario erzeugen (Prototyp).

Aufruf aus dem Projektstamm:
    python tools/tutorial_video/make_video.py player
    python tools/tutorial_video/make_video.py player --app-dir ../2_Test
    python tools/tutorial_video/make_video.py player --drehbuch   # nur Tabelle
    python tools/tutorial_video/make_video.py player --stellprobe # Layout einrichten

Vor jedem Dreh zeigt das Werkzeug Drehbuch und Layout und fragt nach der
Freigabe (--freigegeben ueberspringt die Frage). Das Layout kommt aus der
Stellprobe (scenarios/<name>/layout.ini), sonst aus LAYOUT im Szenario, sonst
gilt das Arbeitslayout des App-Ordners.

Jedes Tutorial hat einen eigenen Ordner, benannt nach dem englischen
Begriff: scenarios/<name>/scenario.py (Drehbuch, im Git), Ergebnis in
out/<name>/<name>_<sprache>.mp4 und .srt (lokal). Ein Szenario ist eine Liste von Schritten: Sprechtext,
Element zum Zeigen, Bedienung. Ablauf: Edge-TTS spricht die Texte -> die App
startet und wird im Takt der Tonlaengen bedient -> ffmpeg filmt das Fenster,
die Musik der App wird mitgeschnitten -> Stimme, Musik und Untertitel kommen
dazu. Ergebnis: out/<name>/<name>_<sprache>.mp4 und .srt.

Braucht: pip install edge-tts imageio-ffmpeg, dazu einen Bildschirm, auf den
das Fenster in Videogroesse (SIZE, per --size) samt Titelleiste passt. Die Sprechtexte
gehen an den Vorlese-Dienst von Microsoft. Die App darf nicht schon laufen, Maus und
Bildschirmbereich gehoeren waehrend der Aufnahme dem Skript. INI und DB werden
gesichert und danach zurueckgespielt. Ausnahme: Ohne eigenes Layout im Szenario
bleibt gespeichert, was dessen SETUP am Arbeitslayout aendert (Dock schliessen).
"""
import argparse
import hashlib
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import time
import traceback
import wave
from pathlib import Path

HERE = Path(__file__).resolve().parent
SRC = HERE.parents[1] / "src"
OUT = HERE / "out"
# Sprache der Oberflaeche -> (Name in der Abfrage, Stimme); Standard Englisch
# (erreicht alle). Angeboten wird nur, wofuer das Szenario Texte hat.
LANGUAGES = {
    "en": ("English", "en-US-ChristopherNeural"),
    "de": ("Deutsch", "de-DE-SeraphinaMultilingualNeural"),   # spricht englische Begriffe englisch
    "ja": ("日本語", "ja-JP-NanamiNeural"),
}
DEFAULT_LANG = "en"
# Vor jedem Dreh fest gesetzt, egal wie die Testumgebung gerade steht
# (die INI wird nach dem Lauf zurueckgespielt).
RECORDING_SETTINGS = {
    "feedback/enabled": False,   # Feedback-Dialog nach Songende (BL-119)
    # Start-Countdown vor dem Liedstart; ein Szenario dazu schaltet ihn per
    # SETTINGS = {"display/countdown_enabled": True} wieder ein.
    "display/countdown_enabled": False,
}
SIZE = (1920, 1080)   # Fensterinhalt = Videobild; per --size aenderbar
FPS = 15
SETTLE_MS = 4000      # App-Start abwarten (Docks, Sequenzen, Start-Hinweise)
LEAD = 1.0            # Sekunden Stille vor dem ersten Satz
GAP = 0.7             # Sekunden Pause nach einem Schritt (Schritt-Feld "hold")
CLICK_MARK_MS = 800   # Dauer der Klick-Markierung
CLICK_MARK_COLOR = "#ffd54a"
MENU_OPEN_MS = 900    # Rechtsklick -> Zeiger faehrt zum Eintrag
MENU_SHOW_MS = 1400   # Eintrag hervorgehoben, dann Klick
ZOOM_SECONDS = 0.8    # Dauer der Zoom-Fahrt
MUSIC_VOLUME = 0.4  # Musik der App im Video, unter der Stimme zusaetzlich leiser
GLIDE_STEPS = 20      # Zeigerfahrt: Zwischenschritte ...
GLIDE_STEP_MS = 25    # ... und ihr Abstand


def say_text(step, lang):
    """Sprechtext eines Schritts: str fuer alle Sprachen oder {"en": ..., "de": ...}."""
    say = step["say"]
    if isinstance(say, dict):
        if lang not in say:
            sys.exit(f"[Video] Kein Sprechtext fuer Sprache '{lang}': {say}")
        return say[lang]
    return say


def scenario_languages(steps):
    """Sprachen, fuer die jeder Schritt einen Sprechtext hat (str gilt fuer alle)."""
    return [lang for lang in LANGUAGES
            if all(not isinstance(s["say"], dict) or lang in s["say"] for s in steps)]


def ask_language(available):
    """Fragt vor der Aufnahme nach der Sprache der Oberflaeche (Enter = Standard)."""
    default = DEFAULT_LANG if DEFAULT_LANG in available else available[0]
    options = "  ".join(f"[{k}] {LANGUAGES[k][0]}" for k in available)
    while True:
        answer = input(f"Sprache der Oberflaeche? {options}  (Enter = {default}): ")
        answer = answer.strip().lower() or default
        if answer in available:
            return answer
        print(f"  Bitte eine von: {', '.join(available)}")


def scenario_layout(name):
    """Layout aus der Stellprobe: scenarios/<name>/layout.ini (im Git)."""
    return HERE / "scenarios" / name / "layout.ini"


def layout_source(name, scenario):
    """Welches Layout der Dreh nimmt: ("stellprobe", Pfad), ("skins", Name)
    fuer LAYOUT im Szenario oder ("arbeitslayout", None)."""
    if scenario_layout(name).exists():
        return "stellprobe", scenario_layout(name)
    if getattr(scenario, "LAYOUT", None):
        return "skins", scenario.LAYOUT
    return "arbeitslayout", None


def describe_layout(name, scenario, app_dir):
    kind, where = layout_source(name, scenario)
    if kind == "stellprobe":
        stamp = time.strftime("%d.%m.%Y %H:%M", time.localtime(where.stat().st_mtime))
        return f"Layout aus der Stellprobe: {where.relative_to(HERE)} (vom {stamp})"
    if kind == "skins":
        return f"Layout aus LAYOUT im Szenario: skins/{where}.ini im App-Ordner"
    return (f"KEIN eigenes Layout: es gilt das Arbeitslayout von {app_dir}. "
            f"Vorher einrichten mit: make_video.py {name} --stellprobe")


def confirm_release(name, lang, app_dir):
    """Vor dem Dreh Drehbuch und Layout zeigen und die Freigabe abfragen."""
    scenario = load_scenario(name)
    print(screenplay(scenario.STEPS, [lang]))
    print()
    print(describe_layout(name, scenario, app_dir))
    picture = scenario_layout(name).with_suffix(".png")
    if layout_source(name, scenario)[0] == "stellprobe" and picture.exists():
        print(f"Bild des Layouts geoeffnet: {picture.relative_to(HERE)}")
        os.startfile(picture)   # Windows-Bildanzeige
    try:
        answer = input("Drehbuch und Layout freigegeben? [j/N] ")
    except EOFError:   # ohne Konsole: nur mit --freigegeben
        answer = ""
    if answer.strip().lower() not in ("j", "ja", "y", "yes"):
        sys.exit("[Video] Nicht freigegeben, kein Dreh. Drehbuch: --drehbuch, "
                 "Layout: --stellprobe")


def plain(text):
    """Menuetext ohne Kuerzel-Markierung: "&Ansicht" -> "Ansicht"."""
    return (text or "").replace("&", "")


def action_text(do):
    """Bedienung eines Schritts als Quelltext: lambda a: a.click(X) -> "a.click(X)"."""
    import inspect
    # ponytail: liest die Quelltextzeile der lambda; eine ueber mehrere Zeilen
    # umbrochene lambda erscheint gekuerzt, dann benannte Funktion nehmen.
    try:
        line = inspect.getsource(do).strip()
    except (OSError, TypeError):
        return getattr(do, "__name__", "?")
    m = re.search(r"lambda\s+\w+\s*:\s*(.*)", line)
    if not m:
        return getattr(do, "__name__", line)
    # Ausdruck endet am ersten "," oder ")" ausserhalb von Klammern und Strings
    # (danach folgen weitere Schritt-Felder wie hold=3).
    depth, quote = 0, None
    for n, ch in enumerate(m[1]):
        if quote:
            quote = None if ch == quote else quote
        elif ch in "\"'":
            quote = ch
        elif ch in "([{":
            depth += 1
        elif ch in ")]}" and depth:
            depth -= 1
        elif ch in ",)]}" and not depth:
            return m[1][:n].strip()
    return m[1].strip()


def screenplay(steps, langs):
    """Drehbuch als Markdown-Tabelle: Nr., Sprechtext je Sprache, Element, Aktion."""
    def cell(value):
        return str(value).replace("|", "\\|").replace("\n", " ")

    def element(step):
        parts = []
        if "point" in step:
            point = step["point"]
            parts.append(f"{point[0]} Zeile {point[1]}" if isinstance(point, tuple)
                         else str(point))
        if "zoom" in step:
            parts.append(f"Zoom: {step['zoom'] or 'ganzes Fenster'}")
        return "; ".join(parts) or "-"

    def action(step):
        text = action_text(step["do"]) if "do" in step else "-"
        return f"{text} (stehen {step['hold']} s)" if "hold" in step else text

    head = ["Nr."] + [LANGUAGES[k][0] for k in langs] + ["Element", "Aktion"]
    rows = ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
    for n, step in enumerate(steps, 1):
        row = [str(n)] + [say_text(step, k) for k in langs] + [element(step), action(step)]
        rows.append("| " + " | ".join(cell(c) for c in row) + " |")
    return "\n".join(rows)


def parse_size(text):
    """argparse-Typ fuer --size: "1600x900" -> (1600, 900)."""
    m = re.fullmatch(r"(\d+)x(\d+)", text.strip().lower())
    if not m or int(m[1]) == 0 or int(m[2]) == 0:
        raise argparse.ArgumentTypeError(
            f"'{text}' ist keine Videogroesse, erwartet BxH, z. B. 1600x900")
    return int(m[1]), int(m[2])


def scenario_file(name):
    return HERE / "scenarios" / name / "scenario.py"


def load_scenario(name):
    spec = importlib.util.spec_from_file_location(name, scenario_file(name))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def fit_rect(x, y, w, h, full_w, full_h, pad=40):
    """Bildausschnitt im Seitenverhaeltnis des Videos um ein Rechteck,
    innerhalb des Bildes: [x, y, breite]."""
    x, y, w, h = x - pad, y - pad, w + 2 * pad, h + 2 * pad
    cx, cy = x + w / 2, y + h / 2
    w = min(full_w, max(w, h * full_w / full_h))
    h = w * full_h / full_w
    x = min(max(cx - w / 2, 0), full_w - w)
    y = min(max(cy - h / 2, 0), full_h - h)
    return [round(x), round(y), round(w)]


def zoom_filter(events, full_w, full_h):
    """ffmpeg-Filter aus [(videozeit, [x, y, breite])]: gleitet bei jedem
    Ereignis in ZOOM_SECONDS weich zum neuen Ausschnitt."""
    # ponytail: zoompan rundet auf ganze Pixel, waehrend der Fahrt kann das Bild
    # minimal zittern; bei langsamen Fahrten vorher hochskalieren.
    exprs = ["0", "0", str(full_w)]
    state = [0, 0, full_w]
    for t, target in events:
        u = f"((it-{t:.3f})/{ZOOM_SECONDS})"
        ease = f"({u}*{u}*(3-2*{u}))"
        exprs = [f"if(lt(it,{t:.3f}),{old},if(lt(it,{t + ZOOM_SECONDS:.3f}),"
                 f"{a}+({b}-{a})*{ease},{b}))"
                 for old, a, b in zip(exprs, state, target)]
        state = target
    x, y, w = exprs
    return (f"zoompan=z='{full_w}/({w})':x='{x}':y='{y}':d=1:"
            f"s={full_w}x{full_h}:fps={FPS}")


def ffmpeg(*args, **kw):
    import imageio_ffmpeg
    return subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-loglevel", "error",
                           *map(str, args)], check=True, **kw)


def speak_all(steps, lang):
    """Spricht jeden Text in eine WAV-Datei, liefert [(wav, dauer)]."""
    import edge_tts
    clip_dir = OUT / "clips"
    clip_dir.mkdir(parents=True, exist_ok=True)
    clips = []
    voice = LANGUAGES[lang][1]
    for step in steps:
        text = say_text(step, lang)
        # Dateiname aus Stimme und Text: ein unveraenderter Satz wird nicht neu geholt.
        digest = hashlib.sha1(f"{voice}|{text}".encode("utf-8")).hexdigest()[:16]
        wav = clip_dir / f"{digest}.wav"
        if not wav.exists():
            mp3 = wav.with_suffix(".mp3")
            edge_tts.Communicate(text, voice).save_sync(str(mp3))
            ffmpeg("-i", mp3, "-ar", "24000", "-ac", "1", wav)
            mp3.unlink()
        with wave.open(str(wav)) as w:
            clips.append((wav, w.getnframes() / w.getframerate()))
    return clips


def video_duration(path):
    import imageio_ffmpeg
    err = subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-i", str(path)],
                         capture_output=True, text=True).stderr
    h, m, s = re.search(r"Duration: (\d+):(\d+):([\d.]+)", err).groups()
    return int(h) * 3600 + int(m) * 60 + float(s)


def build_voice_track(timeline, total, path):
    """Legt die Clips an ihren Startzeiten in eine durchgehende WAV-Datei."""
    with wave.open(str(timeline[0][1])) as w:
        params = w.getparams()
    frame = params.sampwidth * params.nchannels
    buf = bytearray(int(total * params.framerate) * frame)
    for start, wav, _dur, _text in timeline:
        with wave.open(str(wav)) as w:
            data = w.readframes(w.getnframes())
        pos = int(start * params.framerate) * frame
        buf[pos:pos + len(data)] = data
    with wave.open(str(path), "wb") as w:
        w.setparams(params)
        w.writeframes(bytes(buf))


def srt_time(sec):
    ms = int(round(sec * 1000))
    return (f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:"
            f"{ms // 1000 % 60:02d},{ms % 1000:03d}")


def write_srt(timeline, path):
    # ponytail: ein Untertitel je Schritt, bei langen Texten nach Saetzen teilen
    blocks = [f"{i}\n{srt_time(start)} --> {srt_time(start + dur)}\n{text}\n"
              for i, (start, _wav, dur, text) in enumerate(timeline, 1)]
    path.write_text("\n".join(blocks), encoding="utf-8")


def audio_filter(music_starts):
    """ffmpeg-Filter: Musik an ihre Startzeiten, unter der Stimme leiser, dann mischen.

    Eingang 1 ist die Stimme, Eingaenge ab 3 sind die Musik-Mitschnitte.
    """
    fmt = "aformat=sample_rates=48000:channel_layouts=stereo"
    parts = [f"[1:a]{fmt},asplit=2[voice][key]"]
    for n, start in enumerate(music_starts):
        parts.append(f"[{n + 3}:a]{fmt},volume={MUSIC_VOLUME},"
                     f"adelay={int(start * 1000)}:all=1[m{n}]")
    inputs = "".join(f"[m{n}]" for n in range(len(music_starts)))
    parts.append(f"{inputs}amix=inputs={len(music_starts)}:normalize=0[music]")
    parts.append("[music][key]sidechaincompress=threshold=0.03:ratio=8:"
                 "attack=50:release=600[ducked]")
    parts.append("[voice][ducked]amix=inputs=2:normalize=0:duration=longest[a]")
    return ";".join(parts)


def finish_video(name, steps, clips, work, lang):
    """Setzt aus Aufnahme, Clips und Musik-Mitschnitt das fertige Video zusammen."""
    raw = work / "raw.mp4"
    log = json.loads((work / "marks.json").read_text())
    total = video_duration(raw)

    def video_time(wall):
        # Videozeit = Videolaenge - Abstand zum Aufnahmeende. Rechnet vom Ende
        # her, weil ffmpeg beim Start unbestimmt lange braucht.
        return max(0.0, total - (log["end"] - wall))

    timeline = [(video_time(t), clips[i][0], clips[i][1], say_text(steps[i], lang))
                for t, i in log["marks"]]
    voice = work / "voice.wav"
    srt = OUT / name / f"{name}_{lang}.srt"
    mp4 = OUT / name / f"{name}_{lang}.mp4"
    build_voice_track(timeline, total, voice)
    write_srt(timeline, srt)

    args = ["-i", raw, "-i", voice, "-i", srt]
    for _t, wav in log["music"]:
        args += ["-i", work / wav]
    filters, video, audio = [], "0:v", "1:a"
    codec = ["-c:v", "copy"]
    if log["zoom"]:
        events = [(video_time(t), rect) for t, rect in log["zoom"]]
        filters.append(f"[0:v]{zoom_filter(events, *log['size'])}[v]")
        video = "[v]"
        codec = ["-c:v", "libx264", "-preset", "medium", "-crf", "18",
                 "-pix_fmt", "yuv420p"]
    if log["music"]:
        filters.append(audio_filter([video_time(t) for t, _w in log["music"]]))
        audio = "[a]"
    if filters:
        args += ["-filter_complex", ";".join(filters)]
    ffmpeg(*args, "-map", video, "-map", audio, "-map", "2:s", *codec,
           "-c:a", "aac", "-b:a", "160k", "-c:s", "mov_text",
           "-t", f"{total:.3f}", mp4)
    print(f"[Video] fertig: {mp4}")


def produce(name, app_dir, lang):
    """Elternprozess: sprechen, App-Lauf als Kindprozess, aufraeumen, schneiden."""
    work = OUT / name / f"{name}_{lang}.work"
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir(parents=True)
    steps = load_scenario(name).STEPS
    clips = speak_all(steps, lang)
    (work / "durations.json").write_text(json.dumps([d for _w, d in clips]))
    code = run_stage(name, app_dir, lang, work)
    if code != 0:
        sys.exit(f"[Video] App-Lauf gescheitert (Code {code}), kein Video erzeugt")
    finish_video(name, steps, clips, work, lang)


def stellprobe(name, app_dir, lang):
    """Elternprozess der Stellprobe: App ohne Aufnahme starten; beim Schliessen
    speichert sie ihr Layout nach scenarios/<name>/layout.ini."""
    work = OUT / name / f"{name}_{lang}.stellprobe"
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir(parents=True)
    target = scenario_layout(name)
    before = target.stat().st_mtime if target.exists() else None
    print("[Stellprobe] Die App startet in Videogroesse. Docks und Widgets so "
          "einrichten, wie sie im Video stehen sollen (auch die, die das Video "
          "erst einblendet). Dann das Fenster schliessen.")
    run_stage(name, app_dir, lang, work, "--stellprobe")
    if target.exists() and target.stat().st_mtime != before:
        print(f"[Stellprobe] Layout gespeichert: {target.relative_to(HERE)} "
              f"und {target.with_suffix('.png').name}. Der naechste Dreh nimmt es "
              "und zeigt das Bild vor der Freigabe.")
    else:
        sys.exit("[Stellprobe] Kein Layout gespeichert.")


def run_stage(name, app_dir, lang, work, *extra):
    """App-Lauf als Kindprozess; INI und DB davor sichern, danach zurueckspielen."""
    # ponytail: sichert nur INI und Standard-DB im App-Ordner; liegt die DB
    # woanders, eigenen Demo-Ordner per --app-dir nehmen.
    ini = app_dir / "callers_caddy.ini"
    files = (ini, app_dir / "callers_caddy.db")
    keep = [f for f in files if f.exists()]
    # Gab es sie vorher nicht (frischer --app-dir), danach wieder loeschen,
    # sonst bleiben Dreh-Werte (crash/last_notified, Countdown aus, SETTINGS)
    # dauerhaft stehen.
    fresh = [f for f in files if not f.exists()]
    for f in keep:
        shutil.copy2(f, work / f.name)
    try:
        code = subprocess.run([sys.executable, __file__, name, "--stage",
                               "--app-dir", str(app_dir),
                               "--lang", lang,
                               "--size", f"{SIZE[0]}x{SIZE[1]}", *extra]).returncode
    finally:
        for f in keep:
            shutil.copy2(work / f.name, f)
        for f in fresh:
            f.unlink(missing_ok=True)
        for leftover in ("callers_caddy.db-wal", "callers_caddy.db-shm"):
            (app_dir / leftover).unlink(missing_ok=True)
        kept_layout = work / "layout_keep.ini"
        if kept_layout.exists() and ini not in fresh:
            # Das Arbeitslayout nach SETUP in die zurueckgespielte INI uebernehmen.
            from PySide6.QtCore import QSettings
            source = QSettings(str(kept_layout), QSettings.IniFormat)
            target = QSettings(str(app_dir / "callers_caddy.ini"), QSettings.IniFormat)
            for key in source.allKeys():
                target.setValue(key, source.value(key))
            target.sync()
    return code


# ---------------------------------------------------------------------------
# Kindprozess: App starten und bedienen
# ---------------------------------------------------------------------------

def stage(name, app_dir, lang, probe=False):
    """Startet die App, spielt das Szenario ab, filmt mit. Kehrt nicht zurueck.
    probe: Stellprobe, ohne SETUP, Aufnahme und Schritte; beim Schliessen des
    Fensters wird das Layout nach scenarios/<name>/layout.ini gespeichert."""
    work = OUT / name / f"{name}_{lang}.work"
    scenario = load_scenario(name)
    steps = scenario.STEPS
    durations = None if probe else json.loads((work / "durations.json").read_text())
    os.chdir(app_dir)   # Dev-Modus: app_dir = CWD, vor dem Import von main
    sys.path.insert(0, str(SRC))

    from PySide6.QtCore import (QEvent, QObject, QPoint, QPointF, QSettings,
                                QTimer, QVariantAnimation, Qt)
    from PySide6.QtGui import (QColor, QContextMenuEvent, QCursor, QMouseEvent,
                               QPainter, QPen)
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication, QDockWidget, QWidget

    def glide(start, target, delay=0, steps=GLIDE_STEPS, step_ms=GLIDE_STEP_MS):
        """Mauszeiger gleitet ab delay (ms) von start nach target. Liefert den
        Zeitpunkt (ms ab jetzt), zu dem er angekommen ist."""
        for n in range(1, steps + 1):
            QTimer.singleShot(delay + n * step_ms, lambda n=n: QCursor.setPos(
                start + (target - start) * (n / steps)))
        return delay + steps * step_ms + 60

    settings = QSettings(str(app_dir / "callers_caddy.ini"), QSettings.IniFormat)
    settings.setValue("display/language", lang)
    # Fehlerprotokolle von frueher (z. B. ein abgebrochener Dreh) als gemeldet
    # markieren, sonst legt sich beim Start der Hinweis darauf ueber die App.
    # Vergleich wie in src/crash_handler.py: Dateiname crash_<Zeitstempel>.log.
    settings.setValue("crash/last_notified", time.strftime("crash_%Y%m%d_%H%M%S_999999.log"))
    # Szenario-eigene Werte (SETTINGS) nach den festen: z. B. eine Funktion
    # ausschalten, die das Video dann in den Einstellungen einschaltet.
    for key, value in {**RECORDING_SETTINGS, **getattr(scenario, "SETTINGS", {})}.items():
        settings.setValue(key, value)
    skin = getattr(scenario, "SKIN", None)
    if skin:
        if not (app_dir / "skins" / skin).is_dir():
            sys.exit(f"[Video] Farbtheme nicht gefunden: skins/{skin}")
        settings.setValue("display/skin", skin)
    settings.sync()
    del settings

    import audio_engine
    import main
    import update_check
    from tutorial_engine import _HighlightFrame

    # Keine Update-Pruefung beim Dreh: in einem frischen --app-dir ohne Snooze
    # legt sich sonst der Hinweis auf eine neue Version ueber die App und
    # faengt die Klicks ab. Der manuelle Weg ueber das Menue bleibt.
    update_check.UpdateChecker.start = lambda self, *args, **kwargs: None

    # Musik der App mitschneiden: genau das, was an die Soundkarte geht, also
    # mit Tempo, Tonhoehe und Fade Out. Ein Abschnitt je Wiedergabe.
    music = []   # [startzeit, rate, kanaele, [bloecke]]
    original_callback = audio_engine.AudioEngine._callback

    def tapped_callback(self, outdata, frames, time_info, status):
        original_callback(self, outdata, frames, time_info, status)
        if self.playing and not self.paused:
            now = time.monotonic()
            if not music or now - music[-1][4] > 0.25:
                music.append([now, self.sample_rate, outdata.shape[1], [], now])
            music[-1][3].append(outdata.tobytes())
            music[-1][4] = now

    # MUSIC = False im Szenario: Musik nicht ins Video (z. B. Song mit
    # Urheberrecht); die App spielt sie trotzdem, Ton nur aus den Lautsprechern.
    if getattr(scenario, "MUSIC", True):
        audio_engine.AudioEngine._callback = tapped_callback

    # marks: (Wanduhr, Schritt-Index), zoom: (Wanduhr, [x, y, breite])
    state = {"ffmpeg": None, "marks": [], "zoom": [], "size": None}

    def finish(ok):
        end = time.monotonic()
        proc = state["ffmpeg"]
        if proc:
            try:
                proc.stdin.write(b"q")
                proc.stdin.flush()
                proc.wait(timeout=30)
            except (OSError, ValueError, subprocess.TimeoutExpired):
                # ffmpeg laeuft nicht mehr (oder haengt): nicht daran haengen
                # bleiben, sonst friert die App ein, statt sich zu beenden.
                proc.kill()
                ok = False
        if not ok:
            os._exit(1)
        if ok:
            import numpy as np
            import soundfile
            files = []
            for n, (start, rate, channels, blocks, _last) in enumerate(music):
                data = np.frombuffer(b"".join(blocks), dtype=np.float32)
                soundfile.write(str(work / f"music_{n}.wav"),
                                data.reshape(-1, channels), rate)
                files.append((start, f"music_{n}.wav"))
            (work / "marks.json").write_text(json.dumps(
                {"end": end, "marks": state["marks"], "music": files,
                 "zoom": state["zoom"], "size": state["size"]}))
        # Hart beenden: kein closeEvent, die App speichert nichts mehr.
        os._exit(0 if ok else 1)

    def guarded(fn):
        def run():
            try:
                fn()
            except Exception:
                traceback.print_exc()
                finish(False)
        return run

    class ClickMark(QWidget):
        """Klick-Markierung: Punkt am Mauszeiger, darum ein Ring, der waechst
        und verblasst. Eigenes Fenster ueber der App, nimmt keine Maus an."""

        SIZE = 140

        def __init__(self, owner, center):
            super().__init__(owner)
            self.setWindowFlags(Qt.FramelessWindowHint | Qt.Tool)
            for attr in (Qt.WA_TranslucentBackground, Qt.WA_ShowWithoutActivating,
                         Qt.WA_TransparentForMouseEvents, Qt.WA_DeleteOnClose):
                self.setAttribute(attr)
            half = self.SIZE // 2
            self.setGeometry(center.x() - half, center.y() - half, self.SIZE, self.SIZE)
            self._anim = QVariantAnimation(self)
            self._anim.setStartValue(0.0)
            self._anim.setEndValue(1.0)
            self._anim.setDuration(CLICK_MARK_MS)
            self._anim.valueChanged.connect(lambda _v: self.update())
            self._anim.finished.connect(self.close)
            self.show()
            self._anim.start()

        def paintEvent(self, _event):
            t = self._anim.currentValue() or 0.0
            mid = QPointF(self.SIZE / 2, self.SIZE / 2)
            painter = QPainter(self)
            painter.setRenderHint(QPainter.Antialiasing)
            color = QColor(CLICK_MARK_COLOR)
            color.setAlphaF(0.55 * (1.0 - t))
            painter.setPen(Qt.NoPen)
            painter.setBrush(color)
            painter.drawEllipse(mid, 16, 16)
            color.setAlphaF(1.0 - t)
            painter.setPen(QPen(color, 6))
            painter.setBrush(Qt.NoBrush)
            radius = 16 + t * (self.SIZE / 2 - 22)
            painter.drawEllipse(mid, radius, radius)
            painter.end()

    class Stage:
        """Bedienung fuer die Szenarien. Elemente heissen wie in den Touren
        ('player.btn_play'), eine Zeile in einer Tabelle kommt als row dazu."""

        def __init__(self, win):
            self.win = win
            # Elemente loest die TutorialEngine auf (interne Methode), damit die
            # App selbst unveraendert bleibt.
            self._engine = win.tutorial_engine
            self._frame = None

        def widget(self, path):
            w = self._engine._resolve_single(path)
            if w is None or not w.isVisible():
                raise LookupError(f"Element nicht sichtbar: {path}")
            return w

        def _spot(self, path, row=None, at=None):
            """(Widget fuer Maus-Ereignisse, Punkt darin). at = fester Punkt im
            Element (QPoint), z. B. ein Taenzer auf einer Zeichenflaeche."""
            w = self.widget(path)
            if at is not None:
                return w, at
            if row is None:
                return w, w.rect().center()
            return w.viewport(), w.visualRect(w.model().index(row, 0)).center()

        def point(self, path=None, row=None):
            """Rahmen um das Element, Mauszeiger gleitet hin. Ohne path: Rahmen weg."""
            if self._frame:
                self._frame.close()
                self._frame = None
            if path is None:
                return
            self._frame = _HighlightFrame([self.widget(path)], self.win.skin_mgr,
                                          owner=self.win)
            w, p = self._spot(path, row)
            glide(QCursor.pos(), w.mapToGlobal(p), steps=30, step_ms=20)

        def hide_dock(self, name):
            """Schliesst ein Dock, z. B. hide_dock("dock_notes")."""
            self.win.findChild(QDockWidget, name).hide()

        def zoom_rect(self, path, scale):
            """Bildausschnitt um ein Element in Videopixeln, ohne path das volle Bild."""
            full_w, full_h = state["size"]
            if path is None:
                return [0, 0, full_w]
            w = self.widget(path)
            pos = w.mapTo(self.win, QPoint(0, 0))
            return fit_rect(pos.x() * scale, pos.y() * scale, w.width() * scale,
                            w.height() * scale, full_w, full_h)

        def _mark(self, global_pos):
            ClickMark(self.win, global_pos)

        def click(self, path, row=None):
            w, p = self._spot(path, row)
            QCursor.setPos(w.mapToGlobal(p))
            self._mark(w.mapToGlobal(p))
            QTest.mousePress(w, Qt.LeftButton, Qt.NoModifier, p)
            # Kurz gedrueckt halten, damit man den Klick sieht.
            QTimer.singleShot(150, guarded(lambda: QTest.mouseRelease(
                w, Qt.LeftButton, Qt.NoModifier, p)))

        def double_click(self, path, row=None, at=None):
            """Doppelklick, asynchron: die Ereignisse kommen erst im naechsten
            Takt an. Ein Schritt, der das Ergebnis braucht, gehoert also in den
            naechsten STEPS-Eintrag, nicht direkt dahinter in dasselbe do."""
            # Ereignisfolge wie in tests/songs/test_playlist_doppelklick.py, nur
            # das letzte Release vor dem DblClick: oeffnet der einen modalen
            # Dialog, bliebe ein spaeteres Release in dessen exec() haengen und
            # kaeme nach close_dialog() verwaist auf dem Element an.
            w, p = self._spot(path, row, at)
            spot = w.mapToGlobal(p)
            QCursor.setPos(spot)
            self._mark(spot)   # zwei Ringe kurz nacheinander = Doppelklick

            def events():
                QTest.mousePress(w, Qt.LeftButton, Qt.NoModifier, p)
                QTest.mouseRelease(w, Qt.LeftButton, Qt.NoModifier, p)
                QTest.mousePress(w, Qt.LeftButton, Qt.NoModifier, p)
                QTest.mouseRelease(w, Qt.LeftButton, Qt.NoModifier, p)
                QApplication.sendEvent(w, QMouseEvent(
                    QEvent.MouseButtonDblClick, QPointF(p), QPointF(spot),
                    Qt.LeftButton, Qt.LeftButton, Qt.NoModifier))

            QTimer.singleShot(220, guarded(lambda: self._mark(spot)))
            # Per Timer: oeffnet der Doppelklick einen modalen Dialog, blockiert
            # dessen exec() sonst den Ablauf, und der naechste Schritt kaeme nie.
            QTimer.singleShot(0, guarded(events))

        def _zoom_global(self, rect):
            """Bild auf ein Rechteck in Bildschirmkoordinaten zoomen (QRect)."""
            origin = self.win.mapToGlobal(QPoint(0, 0))
            scale = self.win.devicePixelRatioF()
            full_w, full_h = state["size"]
            state["zoom"].append((time.monotonic(), fit_rect(
                (rect.left() - origin.x()) * scale, (rect.top() - origin.y()) * scale,
                rect.width() * scale, rect.height() * scale, full_w, full_h)))

        def _wait_for(self, find, then, what, timeout_ms=8000):
            """Ruft then(ergebnis) auf, sobald find() etwas liefert (alle 100 ms)."""
            deadline = time.monotonic() + timeout_ms / 1000

            def poll():
                found = find()
                if found is not None:
                    then(found)
                elif time.monotonic() > deadline:
                    raise LookupError(f"Nicht erschienen: {what}")
                else:
                    QTimer.singleShot(100, guarded(poll))

            QTimer.singleShot(100, guarded(poll))

        def _glide_click(self, w, local, after=None):
            """Zeiger gleitet zu local in w, klickt dort, dann after()."""
            spot = w.mapToGlobal(local)
            arrived = glide(QCursor.pos(), spot)

            def press():
                self._mark(spot)
                QTest.mouseClick(w, Qt.LeftButton, Qt.NoModifier, local)
                if after:
                    after()

            QTimer.singleShot(arrived + 300, guarded(press))

        def close_dialog(self, accept=True, zoom_back=True):
            """Klickt im offenen modalen Dialog OK (accept) bzw. Abbrechen.
            zoom_back: danach wieder das ganze Bild."""
            from PySide6.QtWidgets import QDialogButtonBox, QMessageBox
            want = (QDialogButtonBox.AcceptRole, QDialogButtonBox.YesRole) if accept else (
                QDialogButtonBox.RejectRole, QDialogButtonBox.NoRole)

            def button_of(dlg):
                if isinstance(dlg, QMessageBox):
                    pairs = [(b, dlg.buttonRole(b)) for b in dlg.buttons()]
                else:
                    pairs = [(b, box.buttonRole(b))
                             for box in dlg.findChildren(QDialogButtonBox)
                             for b in box.buttons()]
                hit = [b for b, role in pairs if role in want]
                # Nur ein Knopf (Hinweis-Fenster): der schliesst in jedem Fall.
                return hit[0] if hit else (pairs[0][0] if len(pairs) == 1 else None)

            def press(dlg):
                btn = button_of(dlg)
                if btn is None:
                    raise LookupError(f"Kein {'OK' if accept else 'Abbrechen'} im Dialog")
                done = (lambda: state["zoom"].append(
                    (time.monotonic(), self.zoom_rect(None, 1)))) if zoom_back else None
                self._glide_click(btn, btn.rect().center(), done)

            self._wait_for(QApplication.activeModalWidget, press, "Dialog")

        def show_dialog(self):
            """Zoomt auf den gerade offenen modalen Dialog (wartet, bis er da ist)."""
            self._wait_for(QApplication.activeModalWidget,
                           lambda dlg: self._zoom_global(dlg.frameGeometry()), "Dialog")

        def setting(self, key):
            """Allgemeine Einstellungen ueber das Menue oeffnen, zur Zeile key
            springen (z. B. "square_flow/enabled"), ihre Checkbox umschalten und
            mit OK schliessen. Danach wieder ganzes Bild. Nur fuer Checkbox-
            Zeilen: eine Combobox oeffnete ein Popup, das den OK-Klick schluckt."""
            # Benutzt vom Einstellungsdialog (src/settings_dialog.py) das
            # oeffentliche focus_row() und die Zeilenliste _rows.
            self.open_menu("menu_design", "menu_general_settings")

            def settings_dialog():
                dlg = QApplication.activeModalWidget()
                rows = getattr(dlg, "_rows", None)
                # Der Dialog baut seine Zeilen erst im naechsten Takt auf.
                return dlg if rows and hasattr(dlg, "focus_row") else None

            def in_dialog(dlg):
                if not dlg.focus_row(key):
                    raise LookupError(f"Einstellung nicht im Dialog: {key}")
                self._zoom_global(dlg.frameGeometry())
                row = next(r for r in dlg._rows if r.full_key == key)
                from PySide6.QtWidgets import QCheckBox
                if not isinstance(row.widget, QCheckBox):
                    raise LookupError(f"setting() kann nur Checkboxen, {key} ist "
                                      f"{type(row.widget).__name__}")

                def pick():
                    w = row.widget
                    self._glide_click(w, w.rect().center(),
                                      lambda: QTimer.singleShot(1200, guarded(self.close_dialog)))

                QTimer.singleShot(int(ZOOM_SECONDS * 1000) + 600, guarded(pick))

            self._wait_for(settings_dialog, in_dialog, "Einstellungen")

        def context_menu(self, path, item):
            """Rechtsklick auf das Element, dann im echten Kontextmenue der App auf
            den Eintrag zeigen und klicken. item = Uebersetzungsschluessel
            (z. B. "clock_menu_seconds"), passt so in jeder Sprache."""
            from i18n import _t
            label = _t(item)
            w, p = self._spot(path)
            spot = w.mapToGlobal(p)
            QCursor.setPos(spot)
            self._mark(spot)

            def pick():
                menu = QApplication.activePopupWidget()
                act = (next((a for a in menu.actions() if plain(a.text()) == label), None)
                       if menu else None)
                if act is None:
                    if menu:
                        menu.close()
                    raise LookupError(f"Menueeintrag nicht gefunden: {label}")
                local = menu.actionGeometry(act).center()
                target = menu.mapToGlobal(local)
                arrived = glide(QCursor.pos(), target)
                QTimer.singleShot(arrived, lambda: menu.setActiveAction(act))

                def press():
                    self._mark(target)
                    QTest.mouseClick(menu, Qt.LeftButton, Qt.NoModifier, local)

                QTimer.singleShot(MENU_SHOW_MS, guarded(press))

            # Menue erst zeigen lassen; exec() laeuft in eigener Ereignisschleife,
            # die Timer laufen darin weiter.
            QTimer.singleShot(MENU_OPEN_MS, guarded(pick))
            QTimer.singleShot(150, guarded(lambda: QApplication.sendEvent(
                w, QContextMenuEvent(QContextMenuEvent.Mouse, p, spot))))

        def open_menu(self, menu, item, click=True):
            """Menue der Menueleiste oeffnen, ins Bild zoomen, auf einen Eintrag
            zeigen und (click=True) anklicken. menu/item = Uebersetzungsschluessel,
            z. B. open_menu("menu_view", "dock_clock")."""
            from i18n import _t
            from PySide6.QtWidgets import QCheckBox, QWidgetAction
            bar = self.win.menuBar()
            title, label = _t(menu), _t(item)
            top = next((a for a in bar.actions() if plain(a.text()) == title), None)
            if top is None or top.menu() is None:
                raise LookupError(f"Menue nicht gefunden: {title}")
            local = bar.actionGeometry(top).center()
            target = bar.mapToGlobal(local)
            arrived = glide(QCursor.pos(), target)

            def press_title():
                self._mark(target)
                QTest.mouseClick(bar, Qt.LeftButton, Qt.NoModifier, local)
                QTimer.singleShot(MENU_OPEN_MS, guarded(show_item))

            def show_item():
                popup = top.menu()
                act = next((a for a in popup.actions()
                            if plain(a.data() if isinstance(a.data(), str) else a.text()) == label),
                           None)
                if act is None:
                    popup.close()
                    raise LookupError(f"Menueeintrag nicht gefunden: {label}")
                # Zoom auf Menuetitel + aufgeklapptes Menue (Fensterkoordinaten).
                origin = self.win.mapToGlobal(QPoint(0, 0))
                g = popup.geometry()
                x0 = min(g.left(), target.x() - 30) - origin.x()
                y0 = bar.mapToGlobal(QPoint(0, 0)).y() - origin.y()
                x1, y1 = g.right() - origin.x(), g.bottom() - origin.y()
                scale = self.win.devicePixelRatioF()
                full_w, full_h = state["size"]
                state["zoom"].append((time.monotonic(), fit_rect(
                    x0 * scale, y0 * scale, (x1 - x0) * scale, (y1 - y0) * scale,
                    full_w, full_h)))
                rect = popup.actionGeometry(act)
                spot_local = rect.center()
                box = (act.defaultWidget().findChild(QCheckBox)
                       if isinstance(act, QWidgetAction) and act.defaultWidget() else None)
                if box is not None:   # Ansicht-Menue: Zeile mit Checkbox
                    spot_local = box.mapTo(popup, box.rect().center())
                s1 = popup.mapToGlobal(spot_local)
                # Erst den Zoom laufen lassen, dann zum Eintrag gleiten: zuerst
                # senkrecht ins Menue, dann hin. Schraeg ueber die Menueleiste
                # wuerde der Zeiger einen Nachbartitel streifen, und Qt klappt
                # dann dessen Menue auf.
                s0 = QCursor.pos()
                inside = QPoint(s0.x(), max(s0.y(), g.top() + 12))
                on_item = glide(s0, inside, delay=int(ZOOM_SECONDS * 1000) + 200,
                                steps=8)
                on_item = glide(inside, s1, delay=on_item)
                QTimer.singleShot(on_item, lambda: popup.setActiveAction(act))

                def press_item():
                    if click:
                        self._mark(s1)
                        if box is not None:
                            QTest.mouseClick(box, Qt.LeftButton, Qt.NoModifier,
                                             box.rect().center())
                        else:
                            QTest.mouseClick(popup, Qt.LeftButton, Qt.NoModifier,
                                             spot_local)
                    QTimer.singleShot(700, lambda: popup.isVisible() and popup.close())

                QTimer.singleShot(int(ZOOM_SECONDS * 1000) + MENU_SHOW_MS,
                                  guarded(press_item))

            QTimer.singleShot(arrived, guarded(press_title))

        def type_text(self, path, text):
            """In ein Eingabefeld klicken und Text Zeichen fuer Zeichen tippen
            (alle 0,12 s), z. B. type_text("song_list._filter_bar.edit_search", "YRR")."""
            self.click(path)
            w = self.widget(path)
            w.setFocus()
            for n, ch in enumerate(text):
                QTimer.singleShot(400 + n * 120, guarded(
                    lambda ch=ch: QTest.keyClicks(w, ch)))

        def keys(self, path, key, count=1):
            """Tastendruecke im Abstand von 0,3 s, z. B. keys(..., "Up", 4)."""
            w = self.widget(path)
            w.setFocus()
            for n in range(count):
                QTimer.singleShot(n * 300, guarded(lambda: QTest.keyClick(
                    w, getattr(Qt, f"Key_{key}"))))

    def start():
        win = next(w for w in QApplication.topLevelWidgets()
                   if isinstance(w, main.P29MainWindow))
        win.tutorial_engine.complete_all()   # raeumt ein offenes Tour-Angebot weg
        kind, where = layout_source(name, scenario)
        layout = None
        if kind == "stellprobe":
            layout = str(where)
        elif kind == "skins":
            layout = os.path.join(win.skin_mgr.skins_dir, f"{where}.ini")
        if layout and not win._apply_layout_file(layout):
            raise LookupError(f"Layout nicht ladbar: {layout}")
        actor = Stage(win)
        if hasattr(scenario, "SETUP") and not probe:
            scenario.SETUP(actor)   # Vorbereitung vor der Aufnahme
        if not layout and not probe:
            # Arbeitslayout: was SETUP daran aendert, bleibt gespeichert. Vor
            # dem Umstellen auf Aufnahmegroesse, die Fenstergroesse bleibt also.
            keep = QSettings(str(work / "layout_keep.ini"), QSettings.IniFormat)
            win._write_layout_state(keep)
            win._save_float_geoms(keep)
            keep.sync()
        win.showNormal()
        win.resize(*SIZE)
        avail = win.screen().availableGeometry()
        win.move(avail.left(), avail.bottom() - win.frameGeometry().height() + 1)
        QApplication.processEvents()
        win.raise_()
        win.activateWindow()
        QApplication.processEvents()
        frame = win.frameGeometry()
        if not avail.contains(frame):
            # Sonst liegt die Menueleiste ausserhalb des Bildschirms, und ffmpeg
            # kann den Bereich nicht aufnehmen.
            print(f"[Video] Fenster {frame.width()}x{frame.height()} (Videogroesse "
                  f"{SIZE[0]}x{SIZE[1]} plus Titelleiste) passt nicht auf den "
                  f"Bildschirm ({avail.width()}x{avail.height()} frei). Kleinere "
                  f"--size waehlen, z. B. 1600x900.", file=sys.stderr)
            finish(False)

        if probe:
            # Beim Schliessen das Layout speichern und sofort beenden: die App
            # selbst speichert dann nichts mehr (INI wird ohnehin zurueckgespielt).
            class SaveOnClose(QObject):
                def eventFilter(self, obj, event):
                    if obj is win and event.type() == QEvent.Close:
                        target = scenario_layout(name)
                        out = QSettings(str(target), QSettings.IniFormat)
                        out.clear()
                        win._write_layout_state(out)
                        win._save_float_geoms(out)
                        out.sync()
                        # Bild dazu, fuer die Freigabe vor dem Dreh (und im PR)
                        win.grab().save(str(target.with_suffix(".png")))
                        print(f"[Stellprobe] Layout geschrieben: {target}")
                        sys.stdout.flush()
                        os._exit(0)
                    return False

            state["probe_filter"] = SaveOnClose(win)
            win.installEventFilter(state["probe_filter"])
            return

        area = win.geometry()   # Fensterinhalt ohne Titelleiste
        scale = win.devicePixelRatioF()
        w, h = (int(v * scale) // 2 * 2 for v in (area.width(), area.height()))
        state["size"] = (w, h)
        import imageio_ffmpeg
        progress = work / "progress.txt"
        state["ffmpeg"] = subprocess.Popen(
            [imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-loglevel", "error",
             "-f", "gdigrab", "-framerate", str(FPS), "-draw_mouse", "1",
             "-offset_x", str(int(area.x() * scale)),
             "-offset_y", str(int(area.y() * scale)),
             "-video_size", f"{w}x{h}", "-i", "desktop",
             "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
             "-pix_fmt", "yuv420p",
             # Bildzaehler (frame=N) laufend in eine Datei, fuer check_recording.
             "-progress", str(progress), "-stats_period", "1",
             str(work / "raw.mp4")],
            stdin=subprocess.PIPE)

        # Lebenszeichen ist der Bildzaehler, nicht die Groesse von raw.mp4:
        # bei ruhigem Bild puffert ffmpeg so wenig Daten, dass die Datei lange
        # nicht waechst, gezaehlt wird trotzdem jedes Bild.
        STALL_S = 10
        counted = {"frame": -1, "at": time.monotonic()}

        def frames_so_far():
            try:
                text = progress.read_text(errors="replace")
            except OSError:
                return -1
            hits = re.findall(r"^frame=(\d+)", text, re.M)
            return int(hits[-1]) if hits else -1

        def check_recording():
            """Alle 2 s: laeuft ffmpeg noch, und zaehlt es Bilder? Sonst gleich
            abbrechen statt erst am Ende in finish()."""
            if state["ffmpeg"].poll() is not None:
                print("[Video] ffmpeg hat die Aufnahme beendet (siehe Meldung "
                      "darueber), Abbruch.", file=sys.stderr)
                finish(False)
            now = time.monotonic()
            frame = frames_so_far()
            if frame > counted["frame"]:
                counted.update(frame=frame, at=now)
            elif now - counted["at"] > STALL_S:
                print(f"[Video] ffmpeg laeuft, nimmt aber seit {STALL_S} s kein "
                      "Bild mehr auf, Abbruch.", file=sys.stderr)
                finish(False)
            QTimer.singleShot(2000, check_recording)

        QTimer.singleShot(1500, check_recording)

        def show(i):
            if i >= len(steps):
                finish(True)
                return
            step = steps[i]
            point = step.get("point")
            actor.point(*(point if isinstance(point, tuple) else (point,)))
            state["marks"].append((time.monotonic(), i))
            if "zoom" in step:
                state["zoom"].append((time.monotonic(),
                                      actor.zoom_rect(step["zoom"], scale)))

            def act():
                # Erst sagen, dann tun: die Bedienung folgt auf den Satz.
                if "do" in step:
                    step["do"](actor)
                QTimer.singleShot(int(step.get("hold", GAP) * 1000),
                                  guarded(lambda: show(i + 1)))

            QTimer.singleShot(int(durations[i] * 1000) + 200, guarded(act))

        QTimer.singleShot(int(LEAD * 1000) + 1000, guarded(lambda: show(0)))

    original_exec = QApplication.exec

    def exec_with_driver(*_args):
        QTimer.singleShot(SETTLE_MS, guarded(start))
        return original_exec()

    QApplication.exec = exec_with_driver
    main.main()


def demo():
    """Selbsttest ohne App: Tonspur-Versatz, Untertitel, Ausschnitt, Filter."""
    work = OUT / "selftest"
    work.mkdir(parents=True, exist_ok=True)
    clip = work / "clip.wav"
    with wave.open(str(clip), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(1000)
        w.writeframes(b"\x01\x00" * 500)          # 0,5 s
    track = work / "track.wav"
    build_voice_track([(1.0, clip, 0.5, "a")], 3.0, track)
    with wave.open(str(track)) as w:
        data = w.readframes(w.getnframes())
    assert len(data) == 6000
    assert data[:2000] == bytes(2000) and data[2000:3000] == b"\x01\x00" * 500
    assert data[3000:] == bytes(3000)
    assert srt_time(3723.5) == "01:02:03,500"
    # Ausschnitt: Seitenverhaeltnis des Videos, am Bildrand festgehalten.
    assert fit_rect(0, 0, 400, 500, 1920, 1080, pad=20) == [0, 0, 960]
    assert fit_rect(1800, 1000, 100, 60, 1920, 1080, pad=10) == [1778, 990, 142]
    assert fit_rect(0, 0, 1920, 1080, 1920, 1080) == [0, 0, 1920]
    # --size: nur BxH mit Zahlen > 0.
    assert parse_size("1600x900") == (1600, 900) and parse_size(" 800X600 ") == (800, 600)
    for bad in ("1600", "1600x900x1", "abc", "0x900", "1600x"):
        try:
            parse_size(bad)
        except argparse.ArgumentTypeError:
            continue
        raise AssertionError(f"--size {bad} haette abgelehnt werden muessen")
    # Sprachen: dict-Texte begrenzen die Auswahl, str gilt fuer alle.
    steps = [dict(say={"en": "Hi", "de": "Hallo"}), dict(say="Callers Caddy")]
    assert scenario_languages(steps) == ["en", "de"]
    assert say_text(steps[0], "de") == "Hallo" and say_text(steps[1], "ja") == "Callers Caddy"
    assert plain("&Ansicht") == "Ansicht"
    # Drehbuch: Aktion aus dem Quelltext der lambda, | im Text maskiert.
    steps = [dict(say={"en": "A | B", "de": "C"}, point=("x", 2), zoom=None,
                  do=lambda a: a.click("x.btn", 2), hold=3),
             dict(say="Ende")]
    table = screenplay(steps, ["en", "de"]).splitlines()
    assert table[0] == "| Nr. | English | Deutsch | Element | Aktion |"
    assert table[2] == ('| 1 | A \\| B | C | x Zeile 2; Zoom: ganzes Fenster '
                        '| a.click("x.btn", 2) (stehen 3 s) |'), table[2]
    assert table[3] == "| 2 | Ende | Ende | - | - |"
    # Layout: Stellprobe vor LAYOUT vor Arbeitslayout.
    import types
    probe_name = "_selftest_layout"
    probe_file = scenario_layout(probe_name)
    with_layout = types.SimpleNamespace(LAYOUT="demo")
    assert layout_source(probe_name, types.SimpleNamespace()) == ("arbeitslayout", None)
    assert layout_source(probe_name, with_layout) == ("skins", "demo")
    probe_file.parent.mkdir(parents=True)
    try:
        probe_file.write_text("[General]\n")
        assert layout_source(probe_name, with_layout) == ("stellprobe", probe_file)
    finally:
        shutil.rmtree(probe_file.parent)
    # Jedes Szenario laesst sich aus scenarios/<name>/scenario.py laden.
    for folder in sorted((HERE / "scenarios").iterdir()):
        if scenario_file(folder.name).exists():
            module = load_scenario(folder.name)
            assert module.STEPS and scenario_languages(module.STEPS), folder.name
            screenplay(module.STEPS, scenario_languages(module.STEPS))
    # Der Filter muss von ffmpeg angenommen werden (Stimme + zwei Musik-Stuecke).
    # Hinein und wieder heraus zoomen: ffmpeg muss auch diesen Filter annehmen.
    zoom = zoom_filter([(0.5, [0, 0, 160]), (2.0, [0, 0, 320])], 320, 180)
    ffmpeg("-f", "lavfi", "-i", f"testsrc=s=320x180:r={FPS}:d=3", "-i", track,
           "-f", "lavfi", "-i", "anullsrc=d=1", "-i", clip, "-i", clip,
           "-filter_complex", f"[0:v]{zoom}[v];{audio_filter([0.5, 2.0])}",
           "-map", "[v]", "-map", "[a]", "-t", "3", work / "mix.mp4")
    shutil.rmtree(work)
    print("ok")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("name", help="Tutorial-Ordner aus scenarios/, z. B. clock, oder 'selftest'")
    ap.add_argument("--app-dir", default=str(SRC), type=Path,
                    help="Ordner mit DB und INI (Standard: src/)")
    ap.add_argument("--lang", choices=sorted(LANGUAGES),
                    help="Sprache der Oberflaeche und Stimme; ohne Angabe wird gefragt")
    ap.add_argument("--size", default=SIZE, type=parse_size,
                    help="Videogroesse BxH, z. B. 1600x900 fuer Bildschirme mit "
                         "1920x1080 (das Fenster samt Titelleiste muss draufpassen)")
    ap.add_argument("--drehbuch", action="store_true",
                    help="Nur das Drehbuch als Markdown-Tabelle ausgeben, ohne App "
                         "und ohne Vorlese-Dienst (mit --lang nur diese Sprache)")
    ap.add_argument("--stellprobe", action="store_true",
                    help="App ohne Aufnahme in Videogroesse starten, Layout einrichten; "
                         "beim Schliessen wird es als scenarios/<name>/layout.ini "
                         "gespeichert und vom Dreh verwendet")
    ap.add_argument("--freigegeben", action="store_true",
                    help="Drehbuch und Layout sind abgenommen: keine Rueckfrage vor dem Dreh")
    ap.add_argument("--stage", action="store_true", help=argparse.SUPPRESS)
    args = ap.parse_args()
    SIZE = args.size
    app_directory = Path(args.app_dir).resolve()
    if args.name == "selftest":
        demo()
    elif args.stage:
        stage(args.name, app_directory, args.lang, probe=args.stellprobe)
    else:
        # Erst das Szenario pruefen, dann fragen: ein Tippfehler faellt sofort auf.
        if not scenario_file(args.name).exists():
            known = sorted(f.name for f in (HERE / "scenarios").iterdir()
                           if scenario_file(f.name).exists())
            ap.error(f"Szenario '{args.name}' nicht gefunden, vorhanden: {', '.join(known)}")
        available = scenario_languages(load_scenario(args.name).STEPS)
        if not available:
            ap.error(f"Szenario '{args.name}': keine Sprache hat in jedem Schritt einen Text")
        if args.lang and args.lang not in available:
            ap.error(f"Szenario '{args.name}' hat keine Texte fuer '{args.lang}', "
                     f"vorhanden: {', '.join(available)}")
        if args.drehbuch:
            print(screenplay(load_scenario(args.name).STEPS,
                             [args.lang] if args.lang else available))
            sys.exit(0)
        lang = args.lang or ask_language(available)
        if args.stellprobe:
            stellprobe(args.name, app_directory, lang)
            sys.exit(0)
        if not args.freigegeben:
            confirm_release(args.name, lang, app_directory)
        produce(args.name, app_directory, lang)
