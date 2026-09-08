"""SqView-Datenbank-Reader fuer Callers Caddy Migration.

Liest Daten aus sqview.db (Benutzer-Daten) und optional utility.db (Referenzdaten).
SqView speichert Texte teilweise in CP1252-Encoding.
"""

import os
import re
import sqlite3


class SqViewReader:
    """Liest Song-Einstellungen, Abspielhistorie und Lyrics-Zuordnungen aus SqView."""

    # SqView kodiert den Apostroph (') literal als die drei Zeichen [¤]
    # (Byte 0xA4 = ¤ in CP1252, eingerahmt von eckigen Klammern).
    APOSTROPHE_ESCAPE = "[¤]"

    @staticmethod
    def clean_text(s: str) -> str:
        """Wandelt SqView-Escapes in lesbare Zeichen (Apostroph) um."""
        if not s:
            return s
        return s.replace(SqViewReader.APOSTROPHE_ESCAPE, "'")

    def __init__(self, sqview_db_path: str):
        self._db_path = sqview_db_path
        self._base_dir = os.path.dirname(sqview_db_path)
        self._conn = sqlite3.connect(sqview_db_path)
        self._conn.text_factory = lambda b: b.decode('cp1252', errors='replace')

    def get_summary(self) -> dict:
        """Gibt eine Uebersicht der verfuegbaren Daten zurueck."""
        all_songs = self.read_all_song_paths()
        cur = self._conn.cursor()
        # Lokationen = distinct track.name, aber "track music" (Default) zaehlt
        # als eine, da CaRo nie Tanznamen eingegeben hat
        cur.execute("SELECT COUNT(DISTINCT name) FROM track WHERE name IS NOT NULL AND name != ''")
        locations = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM track")
        history = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM cuesheet")
        lyrics = cur.fetchone()[0]
        return {
            "songs": len(all_songs),
            "locations": locations,
            "history": history,
            "lyrics": lyrics,
        }

    def read_songs(self) -> list[dict]:
        """Liest Songs MIT expliziten Einstellungen aus der music-Tabelle (oft nur ~10).

        Jeder Dict hat: path, speed, pitch, tempo, volume, loopset, loopstop,
        rate, comment, date, length, keypitch, keytime, pitchfloat
        """
        cur = self._conn.cursor()
        cur.execute("""
            SELECT path, speed, pitch, tempo, volume, loopset, loopstop,
                   rate, comment, date, length, keypitch, keytime, pitchfloat
            FROM music
            WHERE path != 'dummydb'
        """)
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]

    def read_all_song_paths(self) -> list[dict]:
        """Liest ALLE Songs der Quelle: music-Tabelle (volle Bibliothek inkl.
        Loop/Pitch) plus zusaetzliche Songs aus markext1/2/3 und track.fullpath.

        Die music-Tabelle ist die eigentliche Song-Bibliothek (kann mehrere
        tausend Eintraege haben). markext (aktuelle Listen) und track
        (Abspielhistorie) liefern ergaenzend Songs, die (noch) keinen
        music-Eintrag haben.

        Die Klassifizierung (is_pattern/is_singing) ist hier nur vorlaeufig
        anhand des Pfades (path_is_*). Die endgueltige Einstufung erfolgt im
        Worker, sobald Loop- und Lyrics-Informationen bekannt sind.
        """
        cur = self._conn.cursor()
        songs = {}  # {filename_lower: dict}

        # 1. music-Tabelle = vollstaendige Song-Bibliothek (mit Loop/Pitch)
        for raw in self.read_songs():
            p = str(raw.get('path', '') or '')
            if not p or p == 'dummydb':
                continue
            fname = os.path.basename(p)
            if not fname.lower().endswith('.mp3'):
                continue
            key = fname.lower()
            if key in songs:
                continue
            d = self._make_song_dict(fname, p)
            d['loop_in'] = float(raw.get('loopset', 0) or 0)
            d['loop_out'] = float(raw.get('loopstop', 0) or 0)
            d['pitch'] = int(raw.get('pitch', 0) or 0)
            d['comment'] = str(raw.get('comment', '') or '').strip()
            songs[key] = d

        # 2. markext-Tabellen (aktuelle Listen) — Songs ohne music-Eintrag
        for table in ('markext1', 'markext2', 'markext3'):
            try:
                cur.execute(f'SELECT path FROM "{table}"')
                for (path,) in cur.fetchall():
                    if not path:
                        continue
                    fname = os.path.basename(path)
                    if not fname.lower().endswith('.mp3'):
                        continue
                    key = fname.lower()
                    if key not in songs:
                        songs[key] = self._make_song_dict(fname, path)
            except Exception:
                pass

        # 3. track.fullpath (Abspielhistorie) — Songs ohne music-/markext-Eintrag
        try:
            cur.execute(
                "SELECT fullpath FROM track "
                "WHERE fullpath IS NOT NULL AND fullpath != ''"
            )
            for (fullpath,) in cur.fetchall():
                if not fullpath:
                    continue
                fname = os.path.basename(fullpath)
                if not fname.lower().endswith('.mp3'):
                    continue
                key = fname.lower()
                if key not in songs:
                    songs[key] = self._make_song_dict(fname, fullpath)
        except Exception:
            pass

        return list(songs.values())

    def _make_song_dict(self, filename: str, fullpath: str) -> dict:
        """Erstellt ein Song-Basis-Dict aus Dateiname und vollstaendigem Pfad.

        Der Pfad liefert nur Indizien (path_is_singing/path_is_patter) — die
        endgueltige P/S/PS-Einstufung trifft der Worker anhand von Loops und
        Lyrics. is_pattern/is_singing bleiben hier vorlaeufig 0.
        """
        title = SqViewReader.clean_text(os.path.splitext(filename)[0])
        path_lower = fullpath.lower()
        path_is_singing = any(
            k in path_lower for k in ('singer', 'vocal', 'karaoke', 'singing')
        )
        path_is_patter = any(
            k in path_lower for k in ('patter', 'hoedown')
        )
        return {
            'filename': filename,        # roh (fuer Datei-Matching auf Platte)
            'fullpath': fullpath,
            'title': title,              # bereinigt (Apostroph) fuer Anzeige
            'path_is_singing': 1 if path_is_singing else 0,
            'path_is_patter': 1 if path_is_patter else 0,
            'is_pattern': 0,             # vorlaeufig — Worker finalisiert
            'is_singing': 0,
            'loop_in': 0.0,
            'loop_out': 0.0,
            'pitch': 0,
            'comment': '',
        }

    @staticmethod
    def match_lyrics(title: str, lyrics_map: dict) -> str:
        """Sucht eine passende Lyrics-Datei fuer einen Song-Titel.

        lyrics_map: {dateiname_ohne_ext_lower: original_dateiname}

        Strategien (in Reihenfolge):
        1. Exakter Match (title_lower == key)
        2. Label am Ende abschneiden: "Song - LABEL 123" → "Song"
        3. Normalisiert (nur Alphanumerisch, case-insensitiv)
        4. Normalisiert + ohne Label
        """
        def norm(s: str) -> str:
            return re.sub(r'[^a-z0-9]', '', s.lower())

        title_lower = title.lower().strip()

        # 1. Exakter Match
        if title_lower in lyrics_map:
            return lyrics_map[title_lower]

        # 2. Label vom Ende abschneiden: letztes " - ..." entfernen
        short = title
        if ' - ' in title:
            short = title.rsplit(' - ', 1)[0].strip()
            short_lower = short.lower()
            if short_lower in lyrics_map:
                return lyrics_map[short_lower]

        # 3. Normalisiert
        title_norm = norm(title_lower)
        for key, fname in lyrics_map.items():
            if norm(key) == title_norm:
                return fname

        # 4. Normalisiert + ohne Label
        if short != title:
            short_norm = norm(short.lower())
            for key, fname in lyrics_map.items():
                if norm(key) == short_norm:
                    return fname

        return ""

    def read_marriages(self) -> dict:
        """Liest Song-Lyrics-Zuordnungen (marry-Tabelle).

        Returns: {mp3_fullpath_lower: lyrics_fullpath}
        """
        cur = self._conn.cursor()
        cur.execute("SELECT path, html FROM marry")
        result = {}
        for mp3_path, html_path in cur.fetchall():
            if mp3_path and html_path:
                result[mp3_path.lower()] = html_path
        return result

    def read_track(self) -> list[dict]:
        """Liest die Abspielhistorie (track-Tabelle).

        Jeder Dict hat: date, time, path (Dateiname), name (Dance/Event),
        list (Listennummer 1-3), fullpath, level
        """
        cur = self._conn.cursor()
        cur.execute("SELECT date, time, path, name, list, fullpath, level FROM track")
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]

    def read_ini(self, prefix: str = None) -> dict:
        """Liest INI-Einstellungen. Optional gefiltert nach Prefix.

        Returns: {name: value}
        """
        cur = self._conn.cursor()
        if prefix:
            cur.execute("SELECT name, value FROM ini WHERE name LIKE ?",
                        (f"{prefix}%",))
        else:
            cur.execute("SELECT name, value FROM ini")
        return {row[0]: row[1] for row in cur.fetchall()}

    def get_music_dirs(self) -> list[str]:
        """Liest die konfigurierten Musik-Verzeichnisse aus der INI."""
        ini = self.read_ini("music - dirpath")
        dirs = []
        seen = set()
        for key in sorted(ini.keys()):
            val = ini[key].strip()
            if val and val.lower() not in seen:
                seen.add(val.lower())
                dirs.append(val)
        return dirs

    def get_lyrics_dir(self) -> str:
        """Liest das konfigurierte Lyrics-Verzeichnis aus der INI."""
        ini = self.read_ini("lyrics - pathglobal")
        return ini.get("lyrics - pathglobal", "").strip()

    def close(self):
        if self._conn:
            self._conn.close()
            self._conn = None
