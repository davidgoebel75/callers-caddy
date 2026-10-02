CREATE TABLE call_text_mappings (
        call_text TEXT PRIMARY KEY, entity_id TEXT,
        mapped_by TEXT NOT NULL DEFAULT 'auto',
        FOREIGN KEY (entity_id) REFERENCES teaching_order_calls(entity_id));

CREATE TABLE dance_programs (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    code                TEXT    NOT NULL UNIQUE,
    label               TEXT    NOT NULL DEFAULT '',
    sort_order          INTEGER NOT NULL DEFAULT 0,
    target_duration_min REAL    NOT NULL DEFAULT 7.0
);

CREATE TABLE genres (
                id   INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT    NOT NULL UNIQUE
            );

CREATE TABLE locations (
                id   INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT    NOT NULL UNIQUE
            , dance_program_id INTEGER, temp_tempo REAL, planned_tips INTEGER);

CREATE TABLE notes (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    text        TEXT    NOT NULL DEFAULT '',
    status      TEXT    NOT NULL DEFAULT 'open',
    location_id INTEGER,
    sort_order  INTEGER NOT NULL DEFAULT 0,
    note_type   TEXT    NOT NULL DEFAULT 'normal',
    created_at  TEXT    NOT NULL DEFAULT (datetime('now', 'localtime')),
    done_at     TEXT,
    source      TEXT    NOT NULL DEFAULT 'manual',
    source_ref  TEXT,
    FOREIGN KEY (location_id) REFERENCES locations(id)
);

CREATE TABLE photos (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    location_id INTEGER,
    taken_at    TEXT    NOT NULL DEFAULT (datetime('now', 'localtime')),
    filename    TEXT    NOT NULL,
    note        TEXT    NOT NULL DEFAULT '',
    FOREIGN KEY (location_id) REFERENCES locations(id) ON DELETE SET NULL
);

CREATE TABLE play_history (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                song_id     INTEGER NOT NULL,
                location_id INTEGER,
                played_at   TEXT    NOT NULL DEFAULT (datetime('now', 'localtime')),
                FOREIGN KEY (song_id)     REFERENCES songs(id),
                FOREIGN KEY (location_id) REFERENCES locations(id)
            );

CREATE TABLE potential_ignored (
    check_type  TEXT    NOT NULL,
    entity_id   INTEGER NOT NULL,
    ignored_at  TEXT    NOT NULL DEFAULT (datetime('now', 'localtime')),
    PRIMARY KEY (check_type, entity_id)
);

CREATE TABLE sequence_calls (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    sequence_id     INTEGER NOT NULL,
    position        INTEGER NOT NULL,
    call_text       TEXT    NOT NULL,
    entity_id       TEXT,
    teaching_order  REAL,
    FOREIGN KEY (sequence_id) REFERENCES sequences(id)
);

CREATE TABLE sequences (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    field_1             TEXT,
    field_2             TEXT,
    field_3             TEXT,
    field_4             TEXT,
    field_5             TEXT,
    field_6             TEXT,
    field_7             TEXT,
    field_8             TEXT,
    field_9             TEXT,
    field_10            TEXT,
    field_11            TEXT,
    field_12            TEXT,
    field_13            TEXT,
    field_14            TEXT,
    field_15            TEXT,
    level_original      TEXT,
    max_teaching_order  REAL
, type TEXT NOT NULL DEFAULT '', difficulty TEXT NOT NULL DEFAULT '');

CREATE TABLE song_genres (
                song_id  INTEGER NOT NULL,
                genre_id INTEGER NOT NULL,
                PRIMARY KEY (song_id, genre_id),
                FOREIGN KEY (song_id)  REFERENCES songs(id),
                FOREIGN KEY (genre_id) REFERENCES genres(id)
            );

CREATE TABLE song_location_stats (
                song_id     INTEGER NOT NULL,
                location_id INTEGER NOT NULL,
                last_played TEXT    NOT NULL,
                play_count  INTEGER NOT NULL DEFAULT 1,
                PRIMARY KEY (song_id, location_id),
                FOREIGN KEY (song_id)     REFERENCES songs(id),
                FOREIGN KEY (location_id) REFERENCES locations(id)
            );

CREATE TABLE song_properties (
        song_id INTEGER NOT NULL,
        key     TEXT    NOT NULL,
        value   TEXT    NOT NULL DEFAULT '',
        PRIMARY KEY (song_id, key),
        FOREIGN KEY (song_id) REFERENCES songs(id) ON DELETE CASCADE
    );

CREATE TABLE songs (
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
            , loop_offset_ms REAL NOT NULL DEFAULT 0.0, date_added TEXT NOT NULL DEFAULT '', err INTEGER NOT NULL DEFAULT 0);

CREATE TABLE teaching_order_calls (
        entity_id TEXT PRIMARY KEY, canonical_name TEXT NOT NULL,
        teaching_order REAL, program TEXT);

CREATE INDEX idx_ctm_entity
        ON call_text_mappings (entity_id);

CREATE INDEX idx_play_history_loc_song
                ON play_history (location_id, song_id, played_at DESC);

CREATE INDEX idx_sequence_calls_entity
    ON sequence_calls (entity_id);

CREATE INDEX idx_sequences_max_to
    ON sequences (max_teaching_order);

