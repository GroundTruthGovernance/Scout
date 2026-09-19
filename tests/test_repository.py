import sqlite3

import pytest

from scout.core import db, repository as repo
from scout.core.models import (
    AEVector,
    DynamicWorldRecord,
    LatentSignature,
    Pin,
    Project,
    Response,
    Sample,
    project_key as make_project_key,
    sample_id as make_sample_id,
)
from scout.core.util import utc_now_iso


@pytest.fixture
def conn(tmp_path) -> sqlite3.Connection:
    connection = db.connect(tmp_path / "test_project.scout.db")
    yield connection
    connection.close()


@pytest.fixture
def project(conn) -> Project:
    p = Project(
        project_key=make_project_key("SOL", "RUG", "CRK"),
        project_code="SOL", location_code="RUG", sublocation_code="CRK",
        project_name="Solar farm calibration",
    )
    repo.upsert_project(conn, p)
    return p


def test_schema_applies_and_stamps_version(conn):
    assert db.get_schema_version(conn) is not None
    tables = {
        r["name"]
        for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    }
    for expected in ("projects", "samples", "ae_vectors", "dynamic_world", "responses",
                      "pins", "pin_groups", "pin_tags", "latent_signatures", "activity_log"):
        assert expected in tables


def test_project_key_requires_all_three_parts():
    assert make_project_key("SOL", "RUG", "CRK") == "SOL-RUG-CRK"
    assert make_project_key("SOL", "", "CRK") is None
    assert make_project_key("", "", "") is None


def test_project_upsert_and_get(conn, project):
    row = repo.get_project(conn, project.project_key)
    assert row["project_key"] == "SOL-RUG-CRK"
    assert row["project_name"] == "Solar farm calibration"

    # upsert again with a new name should update, not duplicate
    project.project_name = "Renamed"
    repo.upsert_project(conn, project)
    row = repo.get_project(conn, project.project_key)
    assert row["project_name"] == "Renamed"
    count = conn.execute("SELECT COUNT(*) c FROM projects").fetchone()["c"]
    assert count == 1


def test_sample_duplicate_protection(conn, project):
    sid = make_sample_id(project.project_key, "F01", "S01")
    sample = Sample(
        sample_id=sid, sample_uid="SAMPLE-ABC123", project_key=project.project_key,
        field_code="F01", sample_code="S01", geometry_geojson='{"type":"Polygon","coordinates":[]}',
        created_utc=utc_now_iso(), modified_utc=utc_now_iso(),
    )
    assert repo.sample_exists(conn, sid) is False
    repo.insert_sample(conn, sample)
    assert repo.sample_exists(conn, sid) is True

    # Mirrors the JS guard: caller checks sample_exists() before inserting,
    # but the DB itself also refuses a literal duplicate primary key.
    with pytest.raises(sqlite3.IntegrityError):
        repo.insert_sample(conn, sample)


def test_ae_vector_round_trip_requires_64_values(conn, project):
    sid = make_sample_id(project.project_key, "F01", "S01")
    repo.insert_sample(conn, Sample(
        sample_id=sid, sample_uid="SAMPLE-XYZ", project_key=project.project_key,
        field_code="F01", sample_code="S01", geometry_geojson="{}",
        created_utc=utc_now_iso(), modified_utc=utc_now_iso(),
    ))

    with pytest.raises(ValueError):
        repo.upsert_ae_vector(conn, AEVector(sample_id=sid, year=2023, vector=[0.1] * 10, vector_norm=1.0))

    vector = [i / 64 for i in range(64)]
    repo.upsert_ae_vector(conn, AEVector(sample_id=sid, year=2023, vector=vector, vector_norm=1.23))
    conn.commit()
    fetched = repo.get_ae_vector(conn, sid, 2023)
    assert fetched.vector == vector
    assert fetched.vector_norm == 1.23

    # upsert on conflict updates rather than duplicating
    repo.upsert_ae_vector(conn, AEVector(sample_id=sid, year=2023, vector=vector, vector_norm=9.99))
    conn.commit()
    fetched = repo.get_ae_vector(conn, sid, 2023)
    assert fetched.vector_norm == 9.99
    count = conn.execute(
        "SELECT COUNT(*) c FROM ae_vectors WHERE sample_id = ? AND year = ?", (sid, 2023)
    ).fetchone()["c"]
    assert count == 1


def test_dynamic_world_upsert(conn, project):
    sid = make_sample_id(project.project_key, "F01", "S01")
    repo.insert_sample(conn, Sample(
        sample_id=sid, sample_uid="SAMPLE-DW1", project_key=project.project_key,
        field_code="F01", sample_code="S01", geometry_geojson="{}",
        created_utc=utc_now_iso(), modified_utc=utc_now_iso(),
    ))
    repo.upsert_dynamic_world(conn, DynamicWorldRecord(sample_id=sid, year=2023, crops=0.7, built=0.1))
    conn.commit()
    row = conn.execute(
        "SELECT * FROM dynamic_world WHERE sample_id = ? AND year = ?", (sid, 2023)
    ).fetchone()
    assert row["crops"] == 0.7
    assert row["built"] == 0.1


def test_response_fingerprint_duplicate_lookup(conn, project):
    response = Response(
        response_id="SOL-RUG-CRK-F01-S01-r2023-t2023-SC001",
        project_key=project.project_key,
        reference_year=2023, target_year=2023,
        threshold_mode="absolute", threshold=0.9,
        recipe_fingerprint="RF-DEADBEEF",
        created_utc=utc_now_iso(), modified_utc=utc_now_iso(),
    )
    assert repo.find_response_by_fingerprint(conn, project.project_key, "RF-DEADBEEF") == []
    repo.insert_response(conn, response)
    matches = repo.find_response_by_fingerprint(conn, project.project_key, "RF-DEADBEEF")
    assert matches == [response.response_id]

    responses = repo.list_responses(conn, project.project_key)
    assert len(responses) == 1

    repo.set_response_status(conn, response.response_id, "archived")
    responses = repo.list_responses(conn, project.project_key)
    assert len(responses) == 0  # archived is hidden from the default 'active' listing
    responses = repo.list_responses(conn, project.project_key, include_archived=True)
    assert len(responses) == 1


def test_pin_groups_and_tags(conn, project):
    root = repo.create_pin_group(conn, project.project_key, "Fylde manifestations")
    child = repo.create_pin_group(conn, project.project_key, "Seep line", parent_group_id=root)

    groups = repo.list_pin_groups(conn, project.project_key)
    assert {g["name"] for g in groups} == {"Fylde manifestations", "Seep line"}
    child_row = next(g for g in groups if g["group_id"] == child)
    assert child_row["parent_group_id"] == root

    pin = Pin(
        pin_id="SOL-RUG-CRK-PRB-001", pin_type="probe", project_key=project.project_key,
        lon=-2.7, lat=53.7, note="edge pixel", group_id=child, tags=["panel-edge", "calibration"],
        ae_vector=[0.01] * 64, ae_vector_norm=0.5,
        dw_values={"crops": 0.2, "built": 0.1},
        created_utc=utc_now_iso(), modified_utc=utc_now_iso(),
    )
    repo.insert_pin(conn, pin)

    fetched = repo.list_pins(conn, project.project_key, group_id=child)
    assert len(fetched) == 1
    assert fetched[0]["note"] == "edge pixel"

    tag_rows = conn.execute("SELECT tag FROM pin_tags WHERE pin_id = ?", (pin.pin_id,)).fetchall()
    assert {r["tag"] for r in tag_rows} == {"panel-edge", "calibration"}

    repo.set_pin_status(conn, pin.pin_id, "deleted")
    assert repo.list_pins(conn, project.project_key) == []
    assert repo.list_pins(conn, project.project_key, include_archived=True) == []  # deleted never returns


def test_latent_signature_nullable_origin(conn, project):
    imported = LatentSignature(
        signature_id="SOL-RUG-CRK-SIG-001", project_key=project.project_key,
        label="Mean of S01-S04 panel centres", source_type="derived",
        vector=[0.02] * 64, origin_sample_id=None, origin_geometry_geojson=None,
        caption="Derived in Python from four calibration samples",
    )
    repo.insert_latent_signature(conn, imported)

    with pytest.raises(ValueError):
        repo.insert_latent_signature(conn, LatentSignature(
            signature_id="BAD", project_key=project.project_key, label="bad",
            source_type="imported", vector=[0.1, 0.2],
        ))

    sigs = repo.list_latent_signatures(conn, project.project_key)
    assert len(sigs) == 1
    assert sigs[0]["origin_geometry_geojson"] is None


def test_activity_log_records_and_filters(conn, project):
    repo.log_activity(conn, "Sample SOL-RUG-CRK-F01-S01 saved.", project_key=project.project_key)
    repo.log_activity(conn, "Unrelated project event.", project_key="OTHER-PROJ")

    scoped = repo.list_activity(conn, project_key=project.project_key)
    assert len(scoped) == 1
    assert "S01 saved" in scoped[0]["message"]

    everything = repo.list_activity(conn)
    assert len(everything) == 2
