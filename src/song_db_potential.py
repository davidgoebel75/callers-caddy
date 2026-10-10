"""Potential-Checks (Datenqualitaet) von SongDatabase, intern#165.

Mixin: SongDatabase erbt die Methoden, Aufrufer schreiben weiter
db.potential_no_bpm() usw. Braucht nur self._conn.

Die acht Methoden ohne potential_-Praefix (z. B. songs_bpm_empty,
singing_no_start) sind kein eigener Check, sondern liefern die Songlisten fuer
die Stapel-Aktionen im Potential-Dock. Sie gehoeren deshalb trotzdem hierher.
"""


class PotentialMixin:
    """Datenqualitaets-Checks fuer den Potential-Dock."""

    def potential_singing_no_lyrics(self) -> list:
        """Singing Calls ohne verknuepfte Lyrics-Datei."""
        cur = self._conn.execute("""
            SELECT s.id, s.title, s.filename
            FROM songs s
            LEFT JOIN potential_ignored pi
                ON pi.check_type = 'singing_no_lyrics' AND pi.entity_id = s.id
            WHERE s.is_singing = 1
              AND (s.lyrics_file IS NULL OR s.lyrics_file = '')
              AND pi.entity_id IS NULL
            ORDER BY s.title;
        """)
        return cur.fetchall()

    def potential_singing_no_lyrics_full(self) -> list:
        """Wie potential_singing_no_lyrics, aber mit Label.

        Rueckgabe: (id, title, label, filename). Die Krabbelkiste-Suche
        vergleicht Titel + Label + Plattennummer und braucht deshalb das
        Label-Feld zusaetzlich zum Titel.
        """
        cur = self._conn.execute("""
            SELECT s.id, s.title, s.label, s.filename
            FROM songs s
            LEFT JOIN potential_ignored pi
                ON pi.check_type = 'singing_no_lyrics' AND pi.entity_id = s.id
            WHERE s.is_singing = 1
              AND (s.lyrics_file IS NULL OR s.lyrics_file = '')
              AND pi.entity_id IS NULL
            ORDER BY s.title;
        """)
        return cur.fetchall()

    def potential_singing_no_song_points(self) -> list:
        """Singing Calls mit Lyrics, aber ohne gesetzten Liedstart UND -ende.

        Start/Ende liegen als song_properties 'singing_start_m<slot>' /
        'singing_end_m<slot>' vor (pro Musik-Variante). Ein Song gilt als versorgt,
        wenn er fuer irgendeine Variante BEIDE Werte hat. Ohne Lyrics ist das Setzen
        nicht moeglich — solche Songs stehen bereits unter 'Ohne Lyrics'.
        """
        cur = self._conn.execute("""
            SELECT s.id, s.title, s.filename
            FROM songs s
            LEFT JOIN potential_ignored pi
                ON pi.check_type = 'singing_no_song_points' AND pi.entity_id = s.id
            WHERE s.is_singing = 1
              AND s.lyrics_file IS NOT NULL AND s.lyrics_file != ''
              AND pi.entity_id IS NULL
              AND s.id NOT IN (
                  SELECT sp1.song_id FROM song_properties sp1
                  WHERE sp1.key LIKE 'singing_start_m%' AND sp1.value != ''
                  INTERSECT
                  SELECT sp2.song_id FROM song_properties sp2
                  WHERE sp2.key LIKE 'singing_end_m%' AND sp2.value != ''
              )
            ORDER BY s.title;
        """)
        return cur.fetchall()

    def potential_singing_no_sync_points(self) -> list:
        """Singing Calls mit Lyrics, aber ohne einen einzigen Sync-Punkt.

        Sync-Anker liegen als song_properties mit Prefix 'lyric_sync_' vor
        (Schluessel 'lyric_sync_m<musik>_l<lyric>_<index>'). Ohne Lyrics nicht
        moeglich — solche Songs stehen bereits unter 'Ohne Lyrics'.
        """
        cur = self._conn.execute("""
            SELECT s.id, s.title, s.filename
            FROM songs s
            LEFT JOIN potential_ignored pi
                ON pi.check_type = 'singing_no_sync_points' AND pi.entity_id = s.id
            WHERE s.is_singing = 1
              AND s.lyrics_file IS NOT NULL AND s.lyrics_file != ''
              AND pi.entity_id IS NULL
              AND s.id NOT IN (
                  SELECT sp.song_id FROM song_properties sp
                  WHERE sp.key LIKE 'lyric_sync_%'
              )
            ORDER BY s.title;
        """)
        return cur.fetchall()

    def singing_with_lyrics(self) -> list:
        """ALLE Singing Calls mit Lyrics — auch die, die schon Sync-Punkte haben.

        Gegenstueck zu potential_singing_no_sync_points(): dort geht es um die
        offene Arbeitsliste, hier um einen bewussten Komplettlauf ueber den
        ganzen Bestand. Deshalb auch ohne potential_ignored-Filter: "ignorieren"
        heisst "nicht mehr anmahnen", nicht "nie wieder anfassen".
        """
        cur = self._conn.execute("""
            SELECT s.id, s.title, s.filename
            FROM songs s
            WHERE s.is_singing = 1
              AND s.lyrics_file IS NOT NULL AND s.lyrics_file != ''
            ORDER BY s.title;
        """)
        return cur.fetchall()

    def songs_with_sync_anchors(self, song_ids) -> set:
        """Teilmenge von song_ids, die bereits Sync-Anker hat (Slot m1/l1).

        Grundlage fuer die Rueckfrage vor einem Komplettlauf: nur so laesst sich
        beziffern, wie viel bestehende Arbeit ueberschrieben wuerde.
        """
        ids = [int(i) for i in song_ids]
        if not ids:
            return set()
        out = set()
        CHUNK = 500   # SQLite-Grenze fuer Platzhalter nicht ausreizen
        for i in range(0, len(ids), CHUNK):
            part = ids[i:i + CHUNK]
            q = ",".join("?" * len(part))
            rows = self._conn.execute(
                f"SELECT DISTINCT song_id FROM song_properties "
                f"WHERE key LIKE 'lyric_sync_m1_l1_%' AND song_id IN ({q});",
                part).fetchall()
            out.update(r[0] for r in rows)
        return out

    def potential_pattern_no_loop(self) -> list:
        """Pattern ohne gesetzte Loop-Marken (beide auf Default 0.0)."""
        cur = self._conn.execute("""
            SELECT s.id, s.title, s.filename
            FROM songs s
            LEFT JOIN potential_ignored pi
                ON pi.check_type = 'pattern_no_loop' AND pi.entity_id = s.id
            WHERE s.is_pattern = 1
              AND s.loop_in = 0.0 AND s.loop_out = 0.0
              AND pi.entity_id IS NULL
            ORDER BY s.title;
        """)
        return cur.fetchall()

    def potential_no_bpm(self) -> list:
        """Songs mit fehlender oder unplausibler BPM: base_bpm < 100 oder > 150.
        base_bpm = 0 (nie gesetzt) faellt unter < 100 → ebenfalls Kandidat.
        Liefert (id, title, filename, base_bpm) — die BPM wird fuer die
        Problem-Spalte gebraucht; Aufrufer nutzen sonst nur row[0..2]."""
        cur = self._conn.execute("""
            SELECT s.id, s.title, s.filename, s.base_bpm
            FROM songs s
            WHERE s.base_bpm < 100 OR s.base_bpm > 150
            ORDER BY s.title;
        """)
        return cur.fetchall()

    def songs_bpm_empty(self) -> list:
        """Songs ganz ohne BPM (base_bpm <= 0) — fuer 'Alle leere ermitteln'."""
        cur = self._conn.execute("""
            SELECT s.id, s.title, s.filename
            FROM songs s
            WHERE s.base_bpm <= 0
            ORDER BY s.title;
        """)
        return cur.fetchall()

    def songs_all_for_bpm(self) -> list:
        """Alle Songs (id, title, filename) — fuer 'ALLE ermitteln'."""
        cur = self._conn.execute("""
            SELECT s.id, s.title, s.filename
            FROM songs s
            ORDER BY s.title;
        """)
        return cur.fetchall()

    def singing_no_start(self) -> list:
        """Singing Calls ohne gesetzten Musik-Startpunkt (kein
        'singing_start_m<slot>' fuer irgendeine Variante).

        Die Auto-Erkennung (detect_singing_body) arbeitet rein auf Audio und
        braucht KEINE Lyrics — daher werden hier bewusst ALLE is_singing-Songs
        ohne Start gelistet (auch solche ohne Lyrics), anders als
        potential_singing_no_song_points. base_bpm dient als Tempo-Anker fuer
        den Detektor und als Info-Spalte.
        """
        cur = self._conn.execute("""
            SELECT s.id, s.title, s.filename, s.base_bpm
            FROM songs s
            WHERE s.is_singing = 1
              AND s.id NOT IN (
                  SELECT sp.song_id FROM song_properties sp
                  WHERE sp.key LIKE 'singing_start_m%' AND sp.value != ''
              )
            ORDER BY s.title;
        """)
        return cur.fetchall()

    def singing_all_for_start(self) -> list:
        """Alle Singing Calls (id, title, filename, base_bpm) — fuer 'ALLE
        analysieren' (ueberschreibt ggf. bereits gesetzte Startpunkte)."""
        cur = self._conn.execute("""
            SELECT s.id, s.title, s.filename, s.base_bpm
            FROM songs s
            WHERE s.is_singing = 1
            ORDER BY s.title;
        """)
        return cur.fetchall()

    def potential_loop_no_beatsnap(self) -> list:
        """Songs mit Loop-Marken aber ohne Beat Snap Optimierung (Offset = 0).

        Songs mit dem Marker-Genre 'CHECK: BEATSNAP' (Bulk-Beat-Snap konnte
        keinen Offset finden) sind ausgeschlossen — sonst taeten sie mit
        loop_offset_ms=0.0 endlos wieder auftauchen."""
        from song_db import CHECK_BEATSNAP_GENRE_NAME  # zirkelfrei: erst zur Laufzeit
        cur = self._conn.execute(f"""
            SELECT s.id, s.title, s.filename
            FROM songs s
            LEFT JOIN potential_ignored pi
                ON pi.check_type = 'loop_no_beatsnap' AND pi.entity_id = s.id
            WHERE (s.loop_in > 0.0 OR s.loop_out > 0.0)
              AND s.loop_offset_ms = 0.0
              AND pi.entity_id IS NULL
              AND NOT EXISTS (
                  SELECT 1 FROM song_genres sg
                  JOIN genres g ON g.id = sg.genre_id
                  WHERE sg.song_id = s.id
                    AND g.name = '{CHECK_BEATSNAP_GENRE_NAME}')
            ORDER BY s.title;
        """)
        return cur.fetchall()

    def patter_with_loop(self) -> list:
        """Patter-Songs mit gesetzter Sprungmarke — Basis fuer die Loop-Optimierung.

        Nur Songs mit gueltigem Loop (loop_out > loop_in, loop_out > 0); ohne
        vorhandene Marken gibt es nichts zu optimieren.
        """
        cur = self._conn.execute("""
            SELECT s.id, s.title, s.filename
            FROM songs s
            WHERE s.is_pattern = 1
              AND s.loop_out > 0.0
              AND s.loop_out > s.loop_in
            ORDER BY s.title;
        """)
        return cur.fetchall()

    def potential_location_no_history(self) -> list:
        """Lokationen ohne Abspielhistorie."""
        cur = self._conn.execute("""
            SELECT l.id, l.name
            FROM locations l
            LEFT JOIN play_history ph ON ph.location_id = l.id
            LEFT JOIN potential_ignored pi
                ON pi.check_type = 'location_no_history' AND pi.entity_id = l.id
            WHERE ph.id IS NULL
              AND pi.entity_id IS NULL
            ORDER BY l.name;
        """)
        return cur.fetchall()

    def potential_history_orphaned(self) -> list:
        """Historieneintraege mit geloeschten Lokationen."""
        cur = self._conn.execute("""
            SELECT DISTINCT ph.location_id,
                   COUNT(*) as cnt
            FROM play_history ph
            LEFT JOIN locations l ON l.id = ph.location_id
            WHERE ph.location_id IS NOT NULL
              AND l.id IS NULL
            GROUP BY ph.location_id
            ORDER BY cnt DESC;
        """)
        return cur.fetchall()

    def potential_no_quality(self) -> list:
        """Songs ohne Qualitaetsbewertung (quality = 0 = Default = nicht gesetzt)."""
        cur = self._conn.execute("""
            SELECT s.id, s.title, s.filename
            FROM songs s
            LEFT JOIN potential_ignored pi
                ON pi.check_type = 'no_quality' AND pi.entity_id = s.id
            WHERE s.quality = 0
              AND pi.entity_id IS NULL
            ORDER BY s.title;
        """)
        return cur.fetchall()

    def potential_no_genre(self) -> list:
        """Songs ohne Genre-Zuweisung."""
        cur = self._conn.execute("""
            SELECT s.id, s.title, s.filename
            FROM songs s
            LEFT JOIN song_genres sg ON sg.song_id = s.id
            LEFT JOIN potential_ignored pi
                ON pi.check_type = 'no_genre' AND pi.entity_id = s.id
            WHERE sg.song_id IS NULL
              AND pi.entity_id IS NULL
            ORDER BY s.title;
        """)
        return cur.fetchall()

    def potential_no_err(self) -> list:
        """Songs ohne ERR-Bewertung (err = 0 = Default = nicht gesetzt)."""
        cur = self._conn.execute("""
            SELECT s.id, s.title, s.filename
            FROM songs s
            LEFT JOIN potential_ignored pi
                ON pi.check_type = 'no_err' AND pi.entity_id = s.id
            WHERE s.err = 0
              AND pi.entity_id IS NULL
            ORDER BY s.title;
        """)
        return cur.fetchall()

    def get_songs_for_qe_filler(self) -> list:
        """Songs wo Quality=0 ODER ERR=0.
        Gibt (id, title, filename, quality, err, is_pattern, is_singing) zurueck."""
        cur = self._conn.execute("""
            SELECT s.id, s.title, s.filename, s.quality, s.err, s.is_pattern, s.is_singing
            FROM songs s
            WHERE s.quality = 0 OR s.err = 0
            ORDER BY s.title;
        """)
        return cur.fetchall()

    def potential_no_mp3_candidates(self) -> list:
        """Alle Songs (nicht ignorierte) als Kandidaten fuer den MP3-Datei-Check.

        Der eigentliche Datei-Check (os.path.isfile) erfolgt im Widget via PathManager.
        """
        cur = self._conn.execute("""
            SELECT s.id, s.title, s.filename
            FROM songs s
            LEFT JOIN potential_ignored pi
                ON pi.check_type = 'no_mp3' AND pi.entity_id = s.id
            WHERE pi.entity_id IS NULL
            ORDER BY s.title;
        """)
        return cur.fetchall()

    def potential_bad_mp3_candidates(self) -> list:
        """Alle Songs (nicht ignorierte) als Kandidaten fuer den Kompatibilitaets-Check.

        Prueft ob soundfile/libsndfile die Datei lesen kann. Erfordert PathManager im Widget.
        """
        cur = self._conn.execute("""
            SELECT s.id, s.title, s.filename
            FROM songs s
            LEFT JOIN potential_ignored pi
                ON pi.check_type = 'bad_mp3' AND pi.entity_id = s.id
            WHERE pi.entity_id IS NULL
            ORDER BY s.title;
        """)
        return cur.fetchall()

    def potential_cleanup_orphaned_history(self) -> int:
        """Loescht alle Historieneintraege mit geloeschten Lokationen.

        Returns: Anzahl geloeschter Eintraege.
        """
        cur = self._conn.execute("""
            DELETE FROM play_history
            WHERE location_id IS NOT NULL
              AND location_id NOT IN (SELECT id FROM locations);
        """)
        self._conn.commit()
        deleted = cur.rowcount
        if deleted > 0:
            print(f"[SongDB] Verwaiste Historie bereinigt: {deleted} Eintraege")
        return deleted

    def potential_ignore(self, check_type: str, entity_id: int):
        """Markiert einen Eintrag als ignoriert."""
        self._conn.execute("""
            INSERT OR IGNORE INTO potential_ignored (check_type, entity_id)
            VALUES (?, ?);
        """, (check_type, entity_id))
        self._conn.commit()

    def potential_unignore(self, check_type: str, entity_id: int):
        """Entfernt die Ignorieren-Markierung."""
        self._conn.execute("""
            DELETE FROM potential_ignored
            WHERE check_type = ? AND entity_id = ?;
        """, (check_type, entity_id))
        self._conn.commit()

    def potential_count(self, check_type: str) -> int:
        """Zaehlt die Eintraege fuer einen Check-Typ (ohne ignorierte)."""
        method_map = {
            'singing_no_lyrics': self.potential_singing_no_lyrics,
            # Cue-Sheet-Suche arbeitet auf derselben Grundmenge wie "ohne Lyrics"
            'singing_no_lyrics_fill': self.potential_singing_no_lyrics,
            'singing_no_song_points': self.potential_singing_no_song_points,
            'singing_no_sync_points': self.potential_singing_no_sync_points,
            'pattern_no_loop': self.potential_pattern_no_loop,
            'no_bpm': self.potential_no_bpm,
            'loop_no_beatsnap': self.potential_loop_no_beatsnap,
            'location_no_history': self.potential_location_no_history,
            'history_orphaned': self.potential_history_orphaned,
            'no_quality': self.potential_no_quality,
            'no_genre': self.potential_no_genre,
            'no_err': self.potential_no_err,
            # 'no_mp3' fehlt absichtlich — Datei-Check braucht PathManager (Widget)
        }
        fn = method_map.get(check_type)
        if fn:
            return len(fn())
        return 0

