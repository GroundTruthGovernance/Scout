"""Data-access functions for the Scout project database.

Each function takes an open sqlite3.Connection as its first argument
(connections are cheap and owned by the caller — the Qt app holds one
per open project). No function commits internally except where noted;
callers wrap related writes in a single transaction where it matters
(see repository.transaction()).
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager

from scout.core.models import (
    AEVector,
    DW_FIELDS,
    DynamicWorldRecord,
    Figure,
    LatentSignature,
    Pin,
    Project,
    Response,
    Sample,
)
from scout.core.util import utc_now_iso


@contextmanager
def transaction(conn: sqlite3.Connection):
    """Group several writes into one commit/rollback."""
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise


# ---------------------------------------------------------------------
# Projects
# ---------------------------------------------------------------------

def upsert_project(conn: sqlite3.Connection, project: Project) -> None:
    now = utc_now_iso()
    existing = conn.execute(
        "SELECT project_key FROM projects WHERE project_key = ?", (project.project_key,)
    ).fetchone()
    if existing:
        conn.execute(
            """UPDATE projects SET project_name = ?, modified_utc = ?
               WHERE project_key = ?""",
            (project.project_name, now, project.project_key),
        )
    else:
        conn.execute(
            """INSERT INTO projects
               (project_key, project_code, location_code, sublocation_code,
                project_name, created_utc, modified_utc)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                project.project_key, project.project_code, project.location_code,
                project.sublocation_code, project.project_name, now, now,
            ),
        )
    conn.commit()


def get_project(conn: sqlite3.Connection, proj_key: str) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM projects WHERE project_key = ?", (proj_key,)
    ).fetchone()


# ---------------------------------------------------------------------
# Extensible vocabulary (replaces the JS customVocabulary object)
# ---------------------------------------------------------------------

def add_vocabulary_value(conn: sqlite3.Connection, vocab_key: str, value: str) -> None:
    conn.execute(
        "INSERT OR IGNORE INTO vocabulary (vocab_key, value) VALUES (?, ?)",
        (vocab_key, value),
    )
    conn.commit()


def list_vocabulary(conn: sqlite3.Connection, vocab_key: str) -> list[str]:
    rows = conn.execute(
        "SELECT value FROM vocabulary WHERE vocab_key = ? ORDER BY value", (vocab_key,)
    ).fetchall()
    return [r["value"] for r in rows]


# ---------------------------------------------------------------------
# Samples
# ---------------------------------------------------------------------

def sample_exists(conn: sqlite3.Connection, sample_id: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM samples WHERE sample_id = ? AND record_status != 'deleted'",
        (sample_id,),
    ).fetchone()
    return row is not None


def insert_sample(conn: sqlite3.Connection, sample: Sample) -> None:
    """Raises sqlite3.IntegrityError if sample_id already exists — callers
    should check sample_exists() first for a friendlier duplicate message,
    matching the JS "already exists; sample data were not duplicated" flow.
    """
    conn.execute(
        """INSERT INTO samples
           (sample_id, sample_uid, project_key, field_code, sample_code,
            sample_name, experiment_id, session_id, geometry_geojson,
            centroid_lon, centroid_lat, area_m2, perimeter_m,
            sample_role, sample_type, selection_origin, reason,
            classification_confidence, tags, qa_note, record_status,
            created_utc, modified_utc)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            sample.sample_id, sample.sample_uid, sample.project_key, sample.field_code,
            sample.sample_code, sample.sample_name, sample.experiment_id, sample.session_id,
            sample.geometry_geojson, sample.centroid_lon, sample.centroid_lat,
            sample.area_m2, sample.perimeter_m, sample.sample_role, sample.sample_type,
            sample.selection_origin, sample.reason, sample.classification_confidence,
            sample.tags, sample.qa_note, sample.record_status,
            sample.created_utc, sample.modified_utc,
        ),
    )
    conn.commit()


def get_sample(conn: sqlite3.Connection, sample_id: str) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM samples WHERE sample_id = ?", (sample_id,)).fetchone()


def list_samples(
    conn: sqlite3.Connection,
    project_key: str,
    experiment_id: str | None = None,
    field_code: str | None = None,
    include_archived: bool = False,
) -> list[sqlite3.Row]:
    """Default listing shows only 'active' records — 'archived' is a
    deliberate hide-from-working-view state (not a synonym for deleted),
    and 'deleted' is never returned here regardless of include_archived."""
    query = "SELECT * FROM samples WHERE project_key = ?"
    params: list = [project_key]
    query += " AND record_status = 'active'" if not include_archived else " AND record_status != 'deleted'"
    if experiment_id:
        query += " AND experiment_id = ?"
        params.append(experiment_id)
    if field_code:
        query += " AND field_code = ?"
        params.append(field_code)
    query += " ORDER BY created_utc"
    return conn.execute(query, params).fetchall()


def set_sample_status(conn: sqlite3.Connection, sample_id: str, status: str) -> None:
    """status: 'active' | 'archived' | 'deleted' — the delete/archive
    control the GEE prototype never had (see bug list: "no remove/archive
    pin control yet")."""
    conn.execute(
        "UPDATE samples SET record_status = ?, modified_utc = ? WHERE sample_id = ?",
        (status, utc_now_iso(), sample_id),
    )
    conn.commit()


# ---------------------------------------------------------------------
# Annual extraction: AE vectors + Dynamic World
# ---------------------------------------------------------------------

def upsert_ae_vector(conn: sqlite3.Connection, record: AEVector) -> None:
    if len(record.vector) != 64:
        raise ValueError(f"AE vector must have 64 values, got {len(record.vector)}")
    conn.execute(
        """INSERT INTO ae_vectors (sample_id, year, vector_json, vector_norm, created_utc)
           VALUES (?, ?, ?, ?, ?)
           ON CONFLICT(sample_id, year) DO UPDATE SET
             vector_json = excluded.vector_json,
             vector_norm = excluded.vector_norm""",
        (record.sample_id, record.year, json.dumps(record.vector), record.vector_norm,
         record.created_utc or utc_now_iso()),
    )


def get_ae_vector(conn: sqlite3.Connection, sample_id: str, year: int) -> AEVector | None:
    row = conn.execute(
        "SELECT * FROM ae_vectors WHERE sample_id = ? AND year = ?", (sample_id, year)
    ).fetchone()
    if row is None:
        return None
    return AEVector(
        sample_id=row["sample_id"], year=row["year"],
        vector=json.loads(row["vector_json"]), vector_norm=row["vector_norm"],
        created_utc=row["created_utc"],
    )


def upsert_dynamic_world(conn: sqlite3.Connection, record: DynamicWorldRecord) -> None:
    columns = ["sample_id", "year", *DW_FIELDS, "created_utc"]
    values = [record.sample_id, record.year, *(getattr(record, f) for f in DW_FIELDS),
              record.created_utc or utc_now_iso()]
    placeholders = ", ".join("?" for _ in columns)
    update_clause = ", ".join(f"{f} = excluded.{f}" for f in DW_FIELDS)
    conn.execute(
        f"""INSERT INTO dynamic_world ({', '.join(columns)}) VALUES ({placeholders})
            ON CONFLICT(sample_id, year) DO UPDATE SET {update_clause}""",
        values,
    )


# ---------------------------------------------------------------------
# Responses (AE similarity runs)
# ---------------------------------------------------------------------

def find_response_by_fingerprint(
    conn: sqlite3.Connection, project_key: str, fingerprint: str
) -> list[str]:
    """Returns response_ids matching this recipe fingerprint — used for
    the duplicate-recipe warning ("same recipe already exists as ...")."""
    rows = conn.execute(
        """SELECT response_id FROM responses
           WHERE project_key = ? AND recipe_fingerprint = ? AND record_status != 'deleted'""",
        (project_key, fingerprint),
    ).fetchall()
    return [r["response_id"] for r in rows]


def insert_response(conn: sqlite3.Connection, response: Response) -> None:
    conn.execute(
        """INSERT INTO responses
           (response_id, sample_id, sample_uid, project_key, experiment_id,
            reference_year, target_year, threshold_mode, threshold,
            requested_percentile, resolved_similarity_cutoff, search_extent,
            search_extent_geojson, reference_geometry_geojson,
            reference_mean_vector_norm, prediction, result_class, result_confidence,
            recipe_fingerprint, duplicate_of, mask_display_style, mask_color,
            mask_opacity, cached_raster_path, tags, qa_note, record_status,
            created_utc, modified_utc)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            response.response_id, response.sample_id, response.sample_uid,
            response.project_key, response.experiment_id, response.reference_year,
            response.target_year, response.threshold_mode, response.threshold,
            response.requested_percentile, response.resolved_similarity_cutoff,
            response.search_extent, response.search_extent_geojson,
            response.reference_geometry_geojson, response.reference_mean_vector_norm,
            response.prediction, response.result_class, response.result_confidence,
            response.recipe_fingerprint, response.duplicate_of, response.mask_display_style,
            response.mask_color, response.mask_opacity, response.cached_raster_path,
            response.tags, response.qa_note, response.record_status,
            response.created_utc, response.modified_utc,
        ),
    )
    conn.commit()


def list_responses(
    conn: sqlite3.Connection, project_key: str, include_archived: bool = False
) -> list[sqlite3.Row]:
    status_clause = "record_status != 'deleted'" if include_archived else "record_status = 'active'"
    return conn.execute(
        f"SELECT * FROM responses WHERE project_key = ? AND {status_clause} ORDER BY created_utc",
        (project_key,),
    ).fetchall()


def set_response_status(conn: sqlite3.Connection, response_id: str, status: str) -> None:
    conn.execute(
        "UPDATE responses SET record_status = ?, modified_utc = ? WHERE response_id = ?",
        (status, utc_now_iso(), response_id),
    )
    conn.commit()


# ---------------------------------------------------------------------
# Pins (observations + probes), with folders and tags
# ---------------------------------------------------------------------

def create_pin_group(
    conn: sqlite3.Connection, project_key: str, name: str, parent_group_id: int | None = None
) -> int:
    cur = conn.execute(
        "INSERT INTO pin_groups (project_key, parent_group_id, name, created_utc) VALUES (?, ?, ?, ?)",
        (project_key, parent_group_id, name, utc_now_iso()),
    )
    conn.commit()
    return cur.lastrowid


def list_pin_groups(conn: sqlite3.Connection, project_key: str) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM pin_groups WHERE project_key = ? ORDER BY name", (project_key,)
    ).fetchall()


def insert_pin(conn: sqlite3.Connection, pin: Pin) -> None:
    with transaction(conn):
        conn.execute(
            """INSERT INTO pins
               (pin_id, pin_type, project_key, sample_id, response_id, group_id,
                lon, lat, note, probe_year, probe_radius_m, probe_neighbourhood,
                probe_reducer, ae_vector_json, ae_vector_norm, dw_json, s2_json,
                s2_scene_count, record_status, created_utc, modified_utc)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                pin.pin_id, pin.pin_type, pin.project_key, pin.sample_id, pin.response_id,
                pin.group_id, pin.lon, pin.lat, pin.note, pin.probe_year, pin.probe_radius_m,
                pin.probe_neighbourhood, pin.probe_reducer,
                json.dumps(pin.ae_vector) if pin.ae_vector is not None else None,
                pin.ae_vector_norm,
                json.dumps(pin.dw_values) if pin.dw_values is not None else None,
                json.dumps(pin.s2_values) if pin.s2_values is not None else None,
                pin.s2_scene_count, pin.record_status, pin.created_utc, pin.modified_utc,
            ),
        )
        for tag in pin.tags:
            conn.execute(
                "INSERT OR IGNORE INTO pin_tags (pin_id, tag) VALUES (?, ?)", (pin.pin_id, tag)
            )


def list_pins(
    conn: sqlite3.Connection,
    project_key: str,
    pin_type: str | None = None,
    group_id: int | None = None,
    include_archived: bool = False,
) -> list[sqlite3.Row]:
    query = "SELECT * FROM pins WHERE project_key = ?"
    params: list = [project_key]
    query += " AND record_status = 'active'" if not include_archived else " AND record_status != 'deleted'"
    if pin_type:
        query += " AND pin_type = ?"
        params.append(pin_type)
    if group_id is not None:
        query += " AND group_id = ?"
        params.append(group_id)
    query += " ORDER BY created_utc"
    return conn.execute(query, params).fetchall()


def count_all_pins(conn: sqlite3.Connection, project_key: str, pin_type: str | None = None) -> int:
    """Counts every pin ever inserted regardless of record_status, so a
    deleted pin's number is never reused — used to derive the next
    OBS-NNN/PRB-NNN sequence number."""
    query = "SELECT COUNT(*) c FROM pins WHERE project_key = ?"
    params: list = [project_key]
    if pin_type:
        query += " AND pin_type = ?"
        params.append(pin_type)
    return conn.execute(query, params).fetchone()["c"]


def set_pin_status(conn: sqlite3.Connection, pin_id: str, status: str) -> None:
    conn.execute(
        "UPDATE pins SET record_status = ?, modified_utc = ? WHERE pin_id = ?",
        (status, utc_now_iso(), pin_id),
    )
    conn.commit()


# ---------------------------------------------------------------------
# Latent signatures
# ---------------------------------------------------------------------

def insert_latent_signature(conn: sqlite3.Connection, sig: LatentSignature) -> None:
    if len(sig.vector) != 64:
        raise ValueError(f"Latent signature vector must have 64 values, got {len(sig.vector)}")
    conn.execute(
        """INSERT INTO latent_signatures
           (signature_id, project_key, label, source_type, vector_json, vector_norm,
            origin_sample_id, origin_geometry_geojson, caption, tags,
            derivation_note, record_status, created_utc)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            sig.signature_id, sig.project_key, sig.label, sig.source_type,
            json.dumps(sig.vector), sig.vector_norm, sig.origin_sample_id, sig.origin_geometry_geojson,
            sig.caption, sig.tags, sig.derivation_note, sig.record_status,
            sig.created_utc or utc_now_iso(),
        ),
    )
    conn.commit()


def count_all_latent_signatures(conn: sqlite3.Connection, project_key: str) -> int:
    """Counts every signature ever inserted regardless of status, for the
    same collision-avoidance reason as count_all_pins."""
    return conn.execute(
        "SELECT COUNT(*) c FROM latent_signatures WHERE project_key = ?", (project_key,)
    ).fetchone()["c"]


def list_latent_signatures(
    conn: sqlite3.Connection, project_key: str, include_archived: bool = False
) -> list[sqlite3.Row]:
    status_clause = "record_status != 'deleted'" if include_archived else "record_status = 'active'"
    return conn.execute(
        f"SELECT * FROM latent_signatures WHERE project_key = ? AND {status_clause} ORDER BY created_utc",
        (project_key,),
    ).fetchall()


# ---------------------------------------------------------------------
# Figures (feeds the session report composer)
# ---------------------------------------------------------------------

def insert_figure(conn: sqlite3.Connection, figure: Figure) -> None:
    if figure.order_index == 0:
        figure.order_index = conn.execute(
            "SELECT COALESCE(MAX(order_index), 0) + 1 n FROM figures WHERE project_key = ?",
            (figure.project_key,),
        ).fetchone()["n"]
    conn.execute(
        """INSERT INTO figures
           (figure_id, project_key, sample_id, response_id, figure_title, caption,
            image_path, order_index, created_utc)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            figure.figure_id, figure.project_key, figure.sample_id, figure.response_id,
            figure.figure_title, figure.caption, figure.image_path, figure.order_index,
            figure.created_utc or utc_now_iso(),
        ),
    )
    conn.commit()


def list_figures(
    conn: sqlite3.Connection, project_key: str, figure_ids: list[str] | None = None
) -> list[sqlite3.Row]:
    if figure_ids:
        placeholders = ", ".join("?" for _ in figure_ids)
        return conn.execute(
            f"""SELECT * FROM figures WHERE project_key = ? AND figure_id IN ({placeholders})
                ORDER BY order_index""",
            [project_key, *figure_ids],
        ).fetchall()
    return conn.execute(
        "SELECT * FROM figures WHERE project_key = ? ORDER BY order_index", (project_key,)
    ).fetchall()


# ---------------------------------------------------------------------
# Batch queue
# ---------------------------------------------------------------------

def insert_batch_job(
    conn: sqlite3.Connection, job_id: str, project_key: str, job_kind: str,
    geometry_geojson: str, recipe: dict,
) -> None:
    next_order = conn.execute(
        "SELECT COALESCE(MAX(queue_order), 0) + 1 n FROM batch_jobs WHERE project_key = ?",
        (project_key,),
    ).fetchone()["n"]
    conn.execute(
        """INSERT INTO batch_jobs
           (job_id, project_key, job_kind, status, geometry_geojson, recipe_json,
            queue_order, created_utc)
           VALUES (?, ?, ?, 'queued', ?, ?, ?, ?)""",
        (job_id, project_key, job_kind, geometry_geojson, json.dumps(recipe),
         next_order, utc_now_iso()),
    )
    conn.commit()


def list_batch_jobs(conn: sqlite3.Connection, project_key: str) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM batch_jobs WHERE project_key = ? ORDER BY queue_order",
        (project_key,),
    ).fetchall()


def list_queued_batch_jobs(conn: sqlite3.Connection, project_key: str) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM batch_jobs WHERE project_key = ? AND status = 'queued' ORDER BY queue_order",
        (project_key,),
    ).fetchall()


def update_batch_job_status(
    conn: sqlite3.Connection, job_id: str, status: str,
    result_id: str | None = None, error_message: str | None = None,
) -> None:
    now = utc_now_iso()
    if status == "running":
        conn.execute(
            "UPDATE batch_jobs SET status = ?, started_utc = ? WHERE job_id = ?",
            (status, now, job_id),
        )
    else:
        conn.execute(
            """UPDATE batch_jobs SET status = ?, result_id = ?, error_message = ?, finished_utc = ?
               WHERE job_id = ?""",
            (status, result_id, error_message, now, job_id),
        )
    conn.commit()


# ---------------------------------------------------------------------
# Activity log (the automated logger)
# ---------------------------------------------------------------------

def log_activity(
    conn: sqlite3.Connection,
    message: str,
    level: str = "info",
    related_object_id: str | None = None,
    project_key: str | None = None,
) -> None:
    conn.execute(
        """INSERT INTO activity_log (timestamp_utc, level, message, related_object_id, project_key)
           VALUES (?, ?, ?, ?, ?)""",
        (utc_now_iso(), level, message, related_object_id, project_key),
    )
    conn.commit()


def list_activity(
    conn: sqlite3.Connection, project_key: str | None = None, limit: int = 500
) -> list[sqlite3.Row]:
    if project_key:
        return conn.execute(
            """SELECT * FROM activity_log WHERE project_key = ?
               ORDER BY timestamp_utc DESC LIMIT ?""",
            (project_key, limit),
        ).fetchall()
    return conn.execute(
        "SELECT * FROM activity_log ORDER BY timestamp_utc DESC LIMIT ?", (limit,)
    ).fetchall()
