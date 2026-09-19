import pytest

from scout.core import db, repository as repo
from scout.core.models import Figure, Pin, Project, Sample
from scout.core.report_composer import compose_session_report
from scout.core.util import utc_now_iso


@pytest.fixture
def conn(tmp_path):
    connection = db.connect(tmp_path / "test.scout.db")
    yield connection
    connection.close()


@pytest.fixture
def project(conn):
    p = Project(
        project_key="SOL-RUG-CRK", project_code="SOL", location_code="RUG",
        sublocation_code="CRK", project_name="Calibration",
    )
    repo.upsert_project(conn, p)
    return p


def test_report_with_no_figures_or_locations_still_produces_valid_markdown(conn, project, tmp_path):
    output = tmp_path / "report.md"
    markdown = compose_session_report(conn, project.project_key, output)

    assert output.exists()
    assert "SOL-RUG-CRK" in markdown
    assert "No figures saved yet" in markdown
    assert "No saved samples or pins" in markdown


def test_report_includes_figures_in_order(conn, project, tmp_path):
    repo.insert_figure(conn, Figure(
        figure_id="FIG-2", project_key=project.project_key, figure_title="Second",
        caption="second caption", order_index=2,
    ))
    repo.insert_figure(conn, Figure(
        figure_id="FIG-1", project_key=project.project_key, figure_title="First",
        caption="first caption", image_path="figures/fig1.png", order_index=1,
    ))

    markdown = compose_session_report(conn, project.project_key, tmp_path / "report.md")

    first_pos = markdown.index("First")
    second_pos = markdown.index("Second")
    assert first_pos < second_pos
    assert "figures/fig1.png" in markdown
    assert "first caption" in markdown


def test_report_filters_to_requested_figure_ids(conn, project, tmp_path):
    repo.insert_figure(conn, Figure(figure_id="FIG-A", project_key=project.project_key, figure_title="A"))
    repo.insert_figure(conn, Figure(figure_id="FIG-B", project_key=project.project_key, figure_title="B"))

    markdown = compose_session_report(
        conn, project.project_key, tmp_path / "report.md", figure_ids=["FIG-B"]
    )
    assert "## B" in markdown
    assert "## A" not in markdown


def test_report_locations_table_includes_samples_and_pins(conn, project, tmp_path):
    repo.insert_sample(conn, Sample(
        sample_id="SOL-RUG-CRK-F01-S01", sample_uid="UID-1", project_key=project.project_key,
        field_code="F01", sample_code="S01", geometry_geojson="{}",
        centroid_lon=-2.7, centroid_lat=53.7, sample_role="TARGET",
        created_utc=utc_now_iso(), modified_utc=utc_now_iso(),
    ))
    repo.insert_pin(conn, Pin(
        pin_id="SOL-RUG-CRK-OBS-001", pin_type="observation", project_key=project.project_key,
        lon=-2.71, lat=53.71, note="edge case", created_utc=utc_now_iso(), modified_utc=utc_now_iso(),
    ))

    markdown = compose_session_report(conn, project.project_key, tmp_path / "report.md")

    assert "SOL-RUG-CRK-F01-S01" in markdown
    assert "-2.7" in markdown
    assert "SOL-RUG-CRK-OBS-001" in markdown
    assert "edge case" in markdown


def test_report_note_with_pipe_character_does_not_break_table(conn, project, tmp_path):
    repo.insert_pin(conn, Pin(
        pin_id="SOL-RUG-CRK-OBS-001", pin_type="observation", project_key=project.project_key,
        lon=0.0, lat=0.0, note="edge | of panel", created_utc=utc_now_iso(), modified_utc=utc_now_iso(),
    ))
    markdown = compose_session_report(conn, project.project_key, tmp_path / "report.md")
    assert "edge / of panel" in markdown


def test_figure_order_index_auto_increments_when_not_specified(conn, project):
    repo.insert_figure(conn, Figure(figure_id="FIG-1", project_key=project.project_key))
    repo.insert_figure(conn, Figure(figure_id="FIG-2", project_key=project.project_key))
    figures = repo.list_figures(conn, project.project_key)
    assert [f["order_index"] for f in figures] == [1, 2]
