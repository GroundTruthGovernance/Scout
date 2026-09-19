from unittest.mock import MagicMock

import pytest

from scout.app.project_context import ProjectContext


@pytest.fixture
def context(qapp):
    ctx = ProjectContext(ee_backend=MagicMock())
    yield ctx
    ctx.close()


def test_new_project_creates_db_and_row(context, tmp_path):
    logged = []
    context.activity_logged.connect(lambda level, message: logged.append((level, message)))

    project = context.new_project(
        tmp_path / "sol_rug_crk.scout.db", "SOL", "RUG", "CRK", project_name="Calibration"
    )

    assert project.project_key == "SOL-RUG-CRK"
    assert context.is_open is True
    row = context.conn.execute(
        "SELECT * FROM projects WHERE project_key = ?", (project.project_key,)
    ).fetchone()
    assert row["project_name"] == "Calibration"
    assert any("created" in message for _, message in logged)


def test_new_project_requires_full_hierarchy(context, tmp_path):
    with pytest.raises(ValueError):
        context.new_project(tmp_path / "bad.scout.db", "SOL", "", "CRK")
    assert context.is_open is False


def test_open_project_reads_existing(context, tmp_path):
    db_path = tmp_path / "reopen.scout.db"
    context.new_project(db_path, "SOL", "RUG", "CRK")
    context.close()

    reopened = ProjectContext(ee_backend=MagicMock())
    project = reopened.open_project(db_path)
    assert project.project_key == "SOL-RUG-CRK"
    reopened.close()


def test_open_project_rejects_non_project_db(context, tmp_path):
    empty_db = tmp_path / "empty.scout.db"
    from scout.core import db as db_module
    conn = db_module.connect(empty_db)
    conn.close()

    with pytest.raises(ValueError):
        context.open_project(empty_db)


def test_close_resets_exploration_state(context, tmp_path):
    context.new_project(tmp_path / "p.scout.db", "SOL", "RUG", "CRK")
    context.exploration.reference_geometry_geojson = '{"type": "Polygon", "coordinates": []}'
    context.close()
    assert context.is_open is False
    assert context.exploration.reference_geometry_geojson is None


def test_log_without_open_project_still_emits_signal(context):
    received = []
    context.activity_logged.connect(lambda level, message: received.append((level, message)))
    context.log("info", "exploring without a project")
    assert received == [("info", "exploring without a project")]
