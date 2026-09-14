"""SQLite-Writer fuer Callers Caddy 2.0 Migration.

Erzeugt die Ziel-Datenbank mit dem identischen Schema wie song_db.py
und schreibt die konvertierten Daten hinein.
"""

import sqlite3


class DbWriter:
    """Schreibt migrierte Daten in eine Callers Caddy 2.0 SQLite-DB."""

    def __init__(self, db_path: str):
        self._path = db_path
        self._conn = sqlite3.connect(db_path)
        self._conn.execute("PRAGMA journal_mode=WAL;")
        self._conn.execute("PRAGMA foreign_keys=ON;")

    def create_tables(self):
        """Erzeugt alle Tabellen (identisch mit song_db.py)."""
        cur = self._conn.cursor()

        cur.execute("""
            CREATE TABLE IF NOT EXISTS songs (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                filename        TEXT    NOT NULL UNIQUE,
                title           TEXT    NOT NULL DEFAULT '',
                artist          TEXT    NOT NULL DEFAULT '',
                label           TEXT    NOT NULL DEFAULT '',
                quality         INTEGER NOT NULL DEFAULT 0,
                base_bpm        REAL    NOT NULL DEFAULT 0.0,
                standard_tempo  REAL    NOT NULL DEFAULT 1.0,
                pitch           REAL    NOT NULL DEFAULT 0.0,
                volume          REAL    NOT NULL DEFAULT 1.0,
                loop_in         REAL    NOT NULL DEFAULT 0.0,
                loop_out        REAL    NOT NULL DEFAULT 0.0,
                lyrics_file     TEXT    NOT NULL DEFAULT '',
                is_pattern      INTEGER NOT NULL DEFAULT 1,
                is_singing      INTEGER NOT NULL DEFAULT 1
            );
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS locations (
                id   INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT    NOT NULL UNIQUE
            );
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS play_history (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                song_id     INTEGER NOT NULL,
                location_id INTEGER,
                played_at   TEXT    NOT NULL DEFAULT (datetime('now', 'localtime')),
                FOREIGN KEY (song_id)     REFERENCES songs(id),
                FOREIGN KEY (location_id) REFERENCES locations(id)
            );
        """)

        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_play_history_loc_song
                ON play_history (location_id, song_id, played_at DESC);
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS song_location_stats (
                song_id     INTEGER NOT NULL,
                location_id INTEGER NOT NULL,
                last_played TEXT    NOT NULL,
                play_count  INTEGER NOT NULL DEFAULT 1,
                PRIMARY KEY (song_id, location_id),
                FOREIGN KEY (song_id)     REFERENCES songs(id),
                FOREIGN KEY (location_id) REFERENCES locations(id)
            );
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS genres (
                id   INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT    NOT NULL UNIQUE
            );
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS song_genres (
                song_id  INTEGER NOT NULL,
                genre_id INTEGER NOT NULL,
                PRIMARY KEY (song_id, genre_id),
                FOREIGN KEY (song_id)  REFERENCES songs(id),
                FOREIGN KEY (genre_id) REFERENCES genres(id)
            );
        """)

        # BL-094 / BL-122: Generische Song-Properties (Key/Value)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS song_properties (
                song_id INTEGER NOT NULL,
                key     TEXT    NOT NULL,
                value   TEXT    NOT NULL DEFAULT '',
                PRIMARY KEY (song_id, key),
                FOREIGN KEY (song_id) REFERENCES songs(id) ON DELETE CASCADE
            );
        """)

        self._conn.commit()

    def insert_genre(self, name: str) -> int:
        """Fuegt ein Genre ein und gibt die ID zurueck."""
        cur = self._conn.cursor()
        try:
            cur.execute("INSERT INTO genres (name) VALUES (?)", (name,))
            self._conn.commit()
            return cur.lastrowid
        except sqlite3.IntegrityError:
            cur.execute("SELECT id FROM genres WHERE name = ?", (name,))
            row = cur.fetchone()
            return row[0] if row else -1

    def link_song_genre(self, song_id: int, genre_id: int):
        """Verknuepft einen Song mit einem Genre."""
        try:
            self._conn.execute(
                "INSERT OR IGNORE INTO song_genres (song_id, genre_id) VALUES (?, ?)",
                (song_id, genre_id)
            )
        except sqlite3.IntegrityError:
            pass

    def commit(self):
        """Expliziter Commit (fuer Batch-Operationen)."""
        self._conn.commit()

    def insert_song(self, song: dict) -> int:
        """Fuegt einen Song ein und gibt die neue ID zurueck.

        Bei Duplikat (gleicher filename): Update statt Insert.
        """
        cur = self._conn.cursor()
        try:
            cur.execute("""
                INSERT INTO songs (filename, title, artist, label, quality, base_bpm,
                    standard_tempo, pitch, volume, loop_in, loop_out,
                    lyrics_file, is_pattern, is_singing)
                VALUES (:filename, :title, :artist, :label, :quality, :base_bpm,
                    :standard_tempo, :pitch, :volume, :loop_in, :loop_out,
                    :lyrics_file, :is_pattern, :is_singing)
            """, song)
            self._conn.commit()
            return cur.lastrowid
        except sqlite3.IntegrityError:
            # Duplikat → bestehenden zurueckgeben
            cur.execute(
                "SELECT id FROM songs WHERE filename = :filename", song
            )
            row = cur.fetchone()
            return row[0] if row else -1

    def insert_location(self, name: str) -> int:
        """Fuegt eine Lokation ein und gibt die ID zurueck."""
        cur = self._conn.cursor()
        try:
            cur.execute(
                "INSERT INTO locations (name) VALUES (?)", (name,)
            )
            self._conn.commit()
            return cur.lastrowid
        except sqlite3.IntegrityError:
            cur.execute(
                "SELECT id FROM locations WHERE name = ?", (name,)
            )
            row = cur.fetchone()
            return row[0] if row else -1

    def insert_play(self, song_id: int, location_id: int, played_at: str):
        """Fuegt einen Historie-Eintrag ein (mit explizitem Zeitstempel)."""
        self._conn.execute("""
            INSERT INTO play_history (song_id, location_id, played_at)
            VALUES (?, ?, ?)
        """, (song_id, location_id, played_at))

    def bulk_insert_history(self, entries: list[tuple]):
        """Bulk-Insert fuer Historie: [(song_id, location_id, played_at), ...]"""
        self._conn.executemany("""
            INSERT INTO play_history (song_id, location_id, played_at)
            VALUES (?, ?, ?)
        """, entries)
        self._conn.commit()

    def rebuild_stats(self):
        """Baut song_location_stats komplett aus play_history auf."""
        cur = self._conn.cursor()
        cur.execute("DELETE FROM song_location_stats;")
        cur.execute("""
            INSERT INTO song_location_stats (song_id, location_id, last_played, play_count)
            SELECT song_id, location_id, MAX(played_at), COUNT(*)
            FROM play_history
            WHERE location_id IS NOT NULL
            GROUP BY song_id, location_id;
        """)
        self._conn.commit()

    def set_property(self, song_id: int, key: str, value: str):
        """Setzt einen song_properties-Key (INSERT OR REPLACE)."""
        self._conn.execute(
            "INSERT OR REPLACE INTO song_properties (song_id, key, value) VALUES (?, ?, ?)",
            (song_id, key, value),
        )

    def add_variant(self, song_id: int, kind: str, name: str, filename: str):
        """Fuegt eine neue Variante (music oder lyric) mit dem naechsten freien Index ein.

        Index beginnt bei 2 (Index 1 = Primaerdatei in der songs-Tabelle).
        Sucht den ersten unbelegten Index und schreibt name + file.
        """
        rows = self._conn.execute(
            "SELECT key FROM song_properties WHERE song_id = ? AND key LIKE ?",
            (song_id, f"{kind}_%"),
        ).fetchall()
        existing_keys = {r[0] for r in rows}
        idx = 2
        while (f"{kind}_{idx}_name" in existing_keys
               or f"{kind}_{idx}_file" in existing_keys):
            idx += 1
        self.set_property(song_id, f"{kind}_{idx}_name", name)
        self.set_property(song_id, f"{kind}_{idx}_file", filename)

    def get_song_count(self) -> int:
        cur = self._conn.execute("SELECT COUNT(*) FROM songs;")
        return cur.fetchone()[0]

    def get_location_count(self) -> int:
        cur = self._conn.execute("SELECT COUNT(*) FROM locations;")
        return cur.fetchone()[0]

    def get_history_count(self) -> int:
        cur = self._conn.execute("SELECT COUNT(*) FROM play_history;")
        return cur.fetchone()[0]

    def close(self):
        if self._conn:
            self._conn.close()
            self._conn = None
