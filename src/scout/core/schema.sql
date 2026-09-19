-- Scout project database schema.
-- Deliberately flat/denormalized in the same spirit as the GEE prototype's
-- FeatureCollection property bags: project_key/experiment_id/etc. are
-- carried as text on each row rather than deep foreign-keyed hierarchy,
-- because the vocabulary they're drawn from is itself extensible free text.
-- Real object relations (sample -> ae_vector, response -> sample, ...) do
-- use foreign keys.

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS schema_meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

-- ---------------------------------------------------------------------
-- Project / experiment / session / extensible vocabulary
-- ---------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS projects (
    project_key      TEXT PRIMARY KEY,   -- e.g. SOL-RUG-CRK
    project_code     TEXT NOT NULL,
    location_code    TEXT NOT NULL,
    sublocation_code TEXT NOT NULL,
    project_name     TEXT,
    created_utc      TEXT NOT NULL,
    modified_utc     TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS experiments (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    project_key     TEXT NOT NULL REFERENCES projects(project_key),
    experiment_code TEXT NOT NULL,
    experiment_name TEXT,
    hypothesis_id   TEXT,
    created_utc     TEXT NOT NULL,
    UNIQUE (project_key, experiment_code)
);

CREATE TABLE IF NOT EXISTS sessions (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    project_key  TEXT NOT NULL REFERENCES projects(project_key),
    session_code TEXT NOT NULL UNIQUE,
    created_utc  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS vocabulary (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    vocab_key TEXT NOT NULL,   -- sample_role | sample_type | reason | event_type |
                               -- project_code | location_code | sublocation_code |
                               -- field_code | sample_prefix
    value     TEXT NOT NULL,
    UNIQUE (vocab_key, value)
);

-- ---------------------------------------------------------------------
-- Samples + annual extraction
-- ---------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS samples (
    sample_id               TEXT PRIMARY KEY,   -- e.g. SOL-RUG-CRK-F01-S01
    sample_uid              TEXT NOT NULL UNIQUE,
    project_key             TEXT NOT NULL,
    field_code              TEXT NOT NULL,
    sample_code             TEXT NOT NULL,
    sample_name             TEXT,
    experiment_id           TEXT,
    session_id              TEXT,
    geometry_geojson        TEXT NOT NULL,
    centroid_lon            REAL,
    centroid_lat            REAL,
    area_m2                 REAL,
    perimeter_m             REAL,
    sample_role             TEXT,
    sample_type             TEXT,
    selection_origin        TEXT,
    reason                  TEXT,
    classification_confidence TEXT,
    tags                    TEXT,
    qa_note                 TEXT,
    record_status           TEXT NOT NULL DEFAULT 'active', -- active | archived | deleted
    created_utc             TEXT NOT NULL,
    modified_utc            TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_samples_project ON samples(project_key);
CREATE INDEX IF NOT EXISTS idx_samples_status ON samples(record_status);

CREATE TABLE IF NOT EXISTS ae_vectors (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    sample_id   TEXT NOT NULL REFERENCES samples(sample_id) ON DELETE CASCADE,
    year        INTEGER NOT NULL,
    vector_json TEXT NOT NULL,   -- JSON array of 64 floats, A00..A63
    vector_norm REAL,
    created_utc TEXT NOT NULL,
    UNIQUE (sample_id, year)
);

CREATE TABLE IF NOT EXISTS dynamic_world (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    sample_id          TEXT NOT NULL REFERENCES samples(sample_id) ON DELETE CASCADE,
    year               INTEGER NOT NULL,
    water              REAL,
    trees              REAL,
    grass              REAL,
    flooded_vegetation REAL,
    crops              REAL,
    shrub_and_scrub    REAL,
    built              REAL,
    bare               REAL,
    snow_and_ice       REAL,
    created_utc        TEXT NOT NULL,
    UNIQUE (sample_id, year)
);

-- ---------------------------------------------------------------------
-- Responses (AE similarity runs) + HSV masks
-- ---------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS responses (
    response_id                TEXT PRIMARY KEY,
    sample_id                  TEXT REFERENCES samples(sample_id),
    sample_uid                 TEXT,
    project_key                TEXT NOT NULL,
    experiment_id              TEXT,
    reference_year             INTEGER NOT NULL,
    target_year                INTEGER NOT NULL,
    threshold_mode             TEXT NOT NULL,   -- 'absolute' | 'percentile'
    threshold                  REAL NOT NULL,
    requested_percentile       REAL,
    resolved_similarity_cutoff REAL,
    search_extent              TEXT,
    search_extent_geojson      TEXT,
    reference_geometry_geojson TEXT,
    reference_mean_vector_norm REAL,
    sentinel_product           TEXT,
    sentinel_year              INTEGER,
    sentinel_season            TEXT,
    sentinel_start             TEXT,
    sentinel_end               TEXT,
    latent_year                INTEGER,
    latent_dimension           TEXT,
    latent_rgb_r               TEXT,
    latent_rgb_g               TEXT,
    latent_rgb_b               TEXT,
    prediction                 TEXT,
    result_class               TEXT,
    result_confidence          TEXT,
    recipe_fingerprint         TEXT,
    duplicate_of               TEXT,
    mask_display_style         TEXT,
    mask_color                 TEXT,
    mask_opacity                REAL,
    cached_raster_path         TEXT,   -- local cache for reload/recolour without re-hitting EE
    tags                       TEXT,
    qa_note                    TEXT,
    record_status              TEXT NOT NULL DEFAULT 'active',
    created_utc                TEXT NOT NULL,
    modified_utc               TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_responses_project ON responses(project_key);
CREATE INDEX IF NOT EXISTS idx_responses_fingerprint ON responses(recipe_fingerprint);
CREATE INDEX IF NOT EXISTS idx_responses_sample ON responses(sample_id);

CREATE TABLE IF NOT EXISTS hsv_masks (
    mask_id        TEXT PRIMARY KEY,
    sample_id      TEXT REFERENCES samples(sample_id),
    response_id    TEXT REFERENCES responses(response_id),
    start_date     TEXT,
    end_date       TEXT,
    h_min          REAL, h_max REAL,
    s_min          REAL, s_max REAL,
    v_min          REAL, v_max REAL,
    search_extent  TEXT,
    sentinel_year  INTEGER,
    sentinel_season TEXT,
    mask_color     TEXT,
    mask_opacity   REAL,
    record_status  TEXT NOT NULL DEFAULT 'active',
    created_utc    TEXT NOT NULL
);

-- ---------------------------------------------------------------------
-- Sample sets
-- ---------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS sample_sets (
    set_id        TEXT PRIMARY KEY,
    project_key   TEXT NOT NULL,
    field_code    TEXT,
    set_code      TEXT NOT NULL,
    set_name      TEXT,
    member_count  INTEGER NOT NULL DEFAULT 0,
    record_status TEXT NOT NULL DEFAULT 'active',
    created_utc   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sample_set_members (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    set_id           TEXT NOT NULL REFERENCES sample_sets(set_id) ON DELETE CASCADE,
    sample_id        TEXT,   -- may reference samples(sample_id), or be member-only
    member_index     INTEGER NOT NULL,
    geometry_geojson TEXT NOT NULL,
    sample_name      TEXT
);

-- ---------------------------------------------------------------------
-- Pins (observations + probes): folders AND tags
-- ---------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS pin_groups (
    group_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    project_key     TEXT NOT NULL,
    parent_group_id INTEGER REFERENCES pin_groups(group_id) ON DELETE CASCADE,
    name            TEXT NOT NULL,
    created_utc     TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS pins (
    pin_id             TEXT PRIMARY KEY,
    pin_type           TEXT NOT NULL CHECK (pin_type IN ('observation', 'probe')),
    project_key        TEXT NOT NULL,
    sample_id          TEXT,
    response_id        TEXT,
    group_id           INTEGER REFERENCES pin_groups(group_id) ON DELETE SET NULL,
    lon                REAL NOT NULL,
    lat                REAL NOT NULL,
    note               TEXT,
    probe_year         INTEGER,
    probe_radius_m     REAL,
    probe_neighbourhood TEXT,
    probe_reducer      TEXT,
    ae_vector_json     TEXT,
    ae_vector_norm     REAL,
    dw_json            TEXT,
    s2_json            TEXT,
    s2_scene_count     INTEGER,
    record_status      TEXT NOT NULL DEFAULT 'active',
    created_utc        TEXT NOT NULL,
    modified_utc       TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_pins_project ON pins(project_key);
CREATE INDEX IF NOT EXISTS idx_pins_group ON pins(group_id);

CREATE TABLE IF NOT EXISTS pin_tags (
    pin_id TEXT NOT NULL REFERENCES pins(pin_id) ON DELETE CASCADE,
    tag    TEXT NOT NULL,
    PRIMARY KEY (pin_id, tag)
);

-- ---------------------------------------------------------------------
-- Latent signatures
-- ---------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS latent_signatures (
    signature_id            TEXT PRIMARY KEY,
    project_key             TEXT NOT NULL,
    label                   TEXT NOT NULL,
    source_type             TEXT NOT NULL CHECK (source_type IN ('drawn', 'imported', 'derived')),
    vector_json             TEXT NOT NULL,
    vector_norm             REAL,
    origin_sample_id        TEXT REFERENCES samples(sample_id),
    origin_geometry_geojson TEXT,   -- nullable: imported/derived signatures may have no location
    caption                 TEXT,
    tags                    TEXT,
    derivation_note         TEXT,
    record_status           TEXT NOT NULL DEFAULT 'active',
    created_utc             TEXT NOT NULL
);

-- ---------------------------------------------------------------------
-- Figures + session reports (the Obsidian-facing composer)
-- ---------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS figures (
    figure_id      TEXT PRIMARY KEY,
    project_key    TEXT NOT NULL,
    sample_id      TEXT,
    response_id    TEXT,
    figure_title   TEXT,
    caption        TEXT,
    image_path     TEXT,
    dimensions_px  INTEGER,
    recipe_json    TEXT,
    bounds_west    REAL, bounds_south REAL, bounds_east REAL, bounds_north REAL,
    order_index    INTEGER,
    created_utc    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS session_reports (
    report_id           TEXT PRIMARY KEY,
    project_key         TEXT NOT NULL,
    title                TEXT NOT NULL,
    figure_ids_json      TEXT NOT NULL,   -- ordered JSON array of figure_id
    include_overview_map INTEGER NOT NULL DEFAULT 1,
    overview_scope       TEXT,             -- project | experiment | field
    output_path          TEXT,
    created_utc          TEXT NOT NULL
);

-- ---------------------------------------------------------------------
-- Generic context: events / measurements / relationships / references
-- ---------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS events (
    event_id          TEXT PRIMARY KEY,
    project_key       TEXT NOT NULL,
    event_type        TEXT,
    event_start       TEXT,
    event_end         TEXT,
    description       TEXT,
    event_confidence  TEXT,
    related_object_id TEXT,
    geometry_geojson  TEXT,
    created_utc       TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS measurements (
    measurement_id    TEXT PRIMARY KEY,
    project_key       TEXT NOT NULL,
    related_object_id TEXT,
    variable          TEXT NOT NULL,
    value             TEXT,
    unit              TEXT,
    method            TEXT,
    measurement_date  TEXT,
    source            TEXT,
    created_utc       TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS relationships (
    relationship_id   TEXT PRIMARY KEY,
    project_key       TEXT NOT NULL,
    source_object_id  TEXT NOT NULL,
    target_object_id  TEXT NOT NULL,
    relationship_type TEXT NOT NULL,
    note              TEXT,
    created_utc       TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS "references" (
    reference_id      TEXT PRIMARY KEY,
    project_key       TEXT NOT NULL,
    related_object_id TEXT,
    reference_type    TEXT,
    locator           TEXT NOT NULL,
    note              TEXT,
    created_utc       TEXT NOT NULL
);

-- ---------------------------------------------------------------------
-- Workspaces (window/pane layouts) + bookmarks (named views)
-- ---------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS workspaces (
    workspace_id  TEXT PRIMARY KEY,
    project_key   TEXT,
    name          TEXT NOT NULL,
    layout_json   TEXT NOT NULL,
    created_utc   TEXT NOT NULL,
    modified_utc  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS bookmarks (
    bookmark_id  TEXT PRIMARY KEY,
    project_key  TEXT,
    name         TEXT NOT NULL,
    center_lon   REAL NOT NULL,
    center_lat   REAL NOT NULL,
    zoom         REAL NOT NULL,
    scope        TEXT,
    created_utc  TEXT NOT NULL
);

-- ---------------------------------------------------------------------
-- Batch queue
-- ---------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS batch_jobs (
    job_id        TEXT PRIMARY KEY,
    project_key   TEXT NOT NULL,
    job_kind      TEXT NOT NULL,   -- 'ae_response' | 'sample_extraction'
    status        TEXT NOT NULL DEFAULT 'queued',  -- queued | running | done | failed | cancelled
    geometry_geojson TEXT NOT NULL,
    recipe_json   TEXT NOT NULL,
    result_id     TEXT,            -- response_id or sample_id once complete
    error_message TEXT,
    queue_order   INTEGER NOT NULL,
    created_utc   TEXT NOT NULL,
    started_utc   TEXT,
    finished_utc  TEXT
);

-- ---------------------------------------------------------------------
-- Activity log (the automated logger)
-- ---------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS activity_log (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp_utc     TEXT NOT NULL,
    level             TEXT NOT NULL,   -- info | working | error
    message           TEXT NOT NULL,
    related_object_id TEXT,
    project_key       TEXT
);

CREATE INDEX IF NOT EXISTS idx_activity_log_time ON activity_log(timestamp_utc);
