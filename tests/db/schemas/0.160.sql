CREATE TABLE _band_cache_ver (v INTEGER NOT NULL);

CREATE TABLE _band_cover (cache_key TEXT PRIMARY KEY, ver INTEGER NOT NULL, ids TEXT NOT NULL);

CREATE TABLE app_meta (
    key   TEXT PRIMARY KEY,
    value TEXT
);

CREATE TABLE call_programs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_id       TEXT NOT NULL,
    teaching_order  REAL,
    program         TEXT,
    UNIQUE(entity_id, teaching_order),
    FOREIGN KEY (entity_id) REFERENCES calls(entity_id)
);

CREATE TABLE call_text_figures_extra (
    call_text  TEXT NOT NULL,
    entity_id  TEXT NOT NULL,
    PRIMARY KEY (call_text, entity_id),
    FOREIGN KEY (entity_id) REFERENCES calls(entity_id)
);

CREATE TABLE call_text_mappings (
    call_text   TEXT PRIMARY KEY,
    entity_id   TEXT,
    mapped_by   TEXT NOT NULL DEFAULT 'auto',
    FOREIGN KEY (entity_id) REFERENCES calls(entity_id)
);

CREATE TABLE calls (
    entity_id       TEXT PRIMARY KEY,
    canonical_name  TEXT NOT NULL
);

CREATE TABLE dance_programs (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    code                TEXT    NOT NULL UNIQUE,
    label               TEXT    NOT NULL DEFAULT '',
    sort_order          INTEGER NOT NULL DEFAULT 0,
    target_duration_min REAL    NOT NULL DEFAULT 7.0,
    sequence_limit_to   REAL,
    origin              TEXT    NOT NULL DEFAULT 'builtin'
);

CREATE TABLE genres (
    id   INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT    NOT NULL UNIQUE
);

CREATE TABLE location_programs (
    location_id       INTEGER NOT NULL,
    dance_program_id  INTEGER NOT NULL,
    PRIMARY KEY (location_id, dance_program_id),
    FOREIGN KEY (location_id) REFERENCES locations(id) ON DELETE CASCADE,
    FOREIGN KEY (dance_program_id) REFERENCES dance_programs(id)
);

CREATE TABLE locations (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    name              TEXT    NOT NULL UNIQUE,
    dance_program_id  INTEGER,
    temp_tempo        REAL,
    target_bpm        REAL,
    tempo_mode        TEXT,
    planned_tips      INTEGER,
    break_minutes     INTEGER,
    weekdays          TEXT,
    time_from         TEXT,
    time_to           TEXT,
    schedules         TEXT,
    shared_history_with INTEGER
);

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
    max_teaching_order  REAL,
    type                TEXT NOT NULL DEFAULT '',
    difficulty          TEXT NOT NULL DEFAULT '',
    -- Volle Callliste als JSON-Array (Source of Truth, hebt die 15-Grenze auf).
    -- field_1..15 bleiben als Rueckwaerts-Mirror der ersten 15 Calls befuellt,
    -- damit AELTERE App-Versionen die DB weiter lesen koennen (calls_json ist
    -- fuer sie eine unbekannte, ignorierte Spalte). Siehe docs/seq_calls_json_umbau.md.
    calls_json          TEXT,
    -- Herkunft: '' = User-eigen/Alt, 'ceder' = ausgelieferter Referenz-Satz.
    -- Erlaubt, den Referenz-Satz sauber zu ersetzen, ohne User-Sequenzen anzufassen.
    source              TEXT NOT NULL DEFAULT '',
    -- BL-191: frei vergebbarer Tag/Kategorie je Sequenz (z.B. "Once and a half",
    -- "Asymmetrische Choreo"). Freitext mit Auto-Vervollstaendigung im Editor,
    -- exakter Filter im Sequences-Widget.
    tags                TEXT NOT NULL DEFAULT ''
);

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
    loop_offset_ms  REAL    NOT NULL DEFAULT 0.0,
    lyrics_file     TEXT    NOT NULL DEFAULT '',
    is_pattern      INTEGER NOT NULL DEFAULT 1,
    is_singing      INTEGER NOT NULL DEFAULT 1,
    date_added      TEXT    NOT NULL DEFAULT '',
    err             INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX idx_ctfe_entity
    ON call_text_figures_extra (entity_id);

CREATE INDEX idx_ctm_entity
    ON call_text_mappings (entity_id);

CREATE INDEX idx_play_history_loc_song
    ON play_history (location_id, song_id, played_at DESC);

CREATE INDEX idx_seqcalls_calltext
    ON sequence_calls (call_text);

CREATE INDEX idx_sequences_max_to
    ON sequences (max_teaching_order);

CREATE VIEW call_text_figures AS
    SELECT call_text, entity_id FROM call_text_mappings WHERE entity_id IS NOT NULL
    UNION ALL
    SELECT call_text, entity_id FROM call_text_figures_extra;

CREATE VIEW teaching_order_calls AS
    SELECT cp.entity_id, c.canonical_name, cp.teaching_order, cp.program
    FROM call_programs cp
    JOIN calls c ON c.entity_id = cp.entity_id;

CREATE TRIGGER _bcv_call_programs_del AFTER DELETE ON call_programs BEGIN UPDATE _band_cache_ver SET v = v + 1; END;

CREATE TRIGGER _bcv_call_programs_ins AFTER INSERT ON call_programs BEGIN UPDATE _band_cache_ver SET v = v + 1; END;

CREATE TRIGGER _bcv_call_programs_upd AFTER UPDATE ON call_programs BEGIN UPDATE _band_cache_ver SET v = v + 1; END;

CREATE TRIGGER _bcv_call_text_figures_extra_del AFTER DELETE ON call_text_figures_extra BEGIN UPDATE _band_cache_ver SET v = v + 1; END;

CREATE TRIGGER _bcv_call_text_figures_extra_ins AFTER INSERT ON call_text_figures_extra BEGIN UPDATE _band_cache_ver SET v = v + 1; END;

CREATE TRIGGER _bcv_call_text_figures_extra_upd AFTER UPDATE ON call_text_figures_extra BEGIN UPDATE _band_cache_ver SET v = v + 1; END;

CREATE TRIGGER _bcv_call_text_mappings_del AFTER DELETE ON call_text_mappings BEGIN UPDATE _band_cache_ver SET v = v + 1; END;

CREATE TRIGGER _bcv_call_text_mappings_ins AFTER INSERT ON call_text_mappings BEGIN UPDATE _band_cache_ver SET v = v + 1; END;

CREATE TRIGGER _bcv_call_text_mappings_upd AFTER UPDATE ON call_text_mappings BEGIN UPDATE _band_cache_ver SET v = v + 1; END;

CREATE TRIGGER _bcv_sequence_calls_del AFTER DELETE ON sequence_calls BEGIN UPDATE _band_cache_ver SET v = v + 1; END;

CREATE TRIGGER _bcv_sequence_calls_ins AFTER INSERT ON sequence_calls BEGIN UPDATE _band_cache_ver SET v = v + 1; END;

CREATE TRIGGER _bcv_sequence_calls_upd AFTER UPDATE ON sequence_calls BEGIN UPDATE _band_cache_ver SET v = v + 1; END;

