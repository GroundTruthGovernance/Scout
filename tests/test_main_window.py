import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from PySide6.QtCore import QEventLoop, QTimer

from scout.app.main_window import MainWindow
from scout.app.project_context import ProjectContext
from scout.core.ee_backend import EarthEngineBackend


def _pump_until_thread_done(worker, timeout_ms=5000):
    """QThread.wait() blocks the calling thread but does not process Qt's
    event queue, so a cross-thread queued signal (succeeded/failed) can
    still be undelivered right after wait() returns. Run a real event loop
    instead, quitting as soon as either signal fires."""
    loop = QEventLoop()
    worker.succeeded.connect(loop.quit)
    worker.failed.connect(loop.quit)
    QTimer.singleShot(timeout_ms, loop.quit)
    loop.exec()


@pytest.fixture
def window(qapp, qt_cleanup):
    fake_auth = MagicMock()
    fake_auth.is_authenticated.return_value = True
    context = ProjectContext(ee_backend=EarthEngineBackend(ee_module=MagicMock()), ee_auth=fake_auth)
    win = MainWindow(context=context)
    win.show()  # dock/toolbar visibility is hierarchical in Qt — an unshown
    # top-level window makes every child report isVisible() == False
    # regardless of its own setVisible() calls, which would make the clean
    # map mode test pass vacuously rather than actually exercising it.
    yield win
    win.close()
    win.deleteLater()
    qt_cleanup.flush()


def test_window_title_and_menu_structure(window):
    assert "Scout" in window.windowTitle()
    menu_titles = [action.text().replace("&", "") for action in window.menuBar().actions()]
    assert menu_titles == [
        "File", "Edit", "View", "Layer", "Sample", "Run", "Batch", "Tools", "Window", "Help",
    ]


def test_all_docks_present_and_listed_in_view_panels(window):
    expected_docks = {
        "LayersDock", "ActivityLogDock", "AttributeTableDock",
        "BatchQueueDock", "PythonConsoleDock",
    }
    actual_docks = {dock.objectName() for dock in window.findChildren(type(window.layers_dock))}
    assert expected_docks <= actual_docks


def test_specialist_toolbars_exist_and_hidden_by_default(window):
    toolbar_names = {tb.objectName() for tb in window.findChildren(type(window.main_toolbar))}
    for name in ("HSVToolbar", "LatentInspectionToolbar", "BatchToolbar", "CompareToolbar"):
        assert name in toolbar_names
    hsv_toolbar = next(tb for tb in window.findChildren(type(window.main_toolbar))
                        if tb.objectName() == "HSVToolbar")
    assert hsv_toolbar.isVisible() is False


def test_run_ae_disabled_until_polygon_drawn(window):
    assert window.action_run_ae.isEnabled() is False
    geojson = json.dumps({"type": "Polygon", "coordinates": [[[0, 0], [0, 1], [1, 1], [0, 0]]]})
    window._on_polygon_drawn(geojson)
    assert window.action_run_ae.isEnabled() is True
    assert window.context.exploration.reference_geometry_geojson == geojson


def test_run_ae_similarity_without_geometry_reports_status(window):
    window.run_ae_similarity()
    assert "polygon" in window.status_bar.currentMessage().lower()


def test_run_ae_similarity_adds_layer_on_success(window, monkeypatch):
    geojson = json.dumps({"type": "Polygon", "coordinates": [[[0, 0], [0, 1], [1, 1], [0, 0]]]})
    window._on_polygon_drawn(geojson)

    fake_map_id = {"tile_fetcher": MagicMock(url_format="https://example.com/{z}/{x}/{y}")}
    mock_ee = window.context.ee.ee
    mock_ee.Image.return_value.getMapId.return_value = fake_map_id

    window.map_panel = MagicMock()
    window.layers_panel = MagicMock()

    window.run_ae_similarity()

    window.map_panel.add_raster_layer.assert_called_once()
    args, _ = window.map_panel.add_raster_layer.call_args
    assert args[1] == "https://example.com/{z}/{x}/{y}"
    window.layers_panel.add_layer.assert_called_once()
    assert "Responses" in window.layers_panel.add_layer.call_args[0]


def test_run_ae_similarity_surfaces_backend_errors(window):
    geojson = json.dumps({"type": "Polygon", "coordinates": [[[0, 0], [0, 1], [1, 1], [0, 0]]]})
    window._on_polygon_drawn(geojson)

    window.context.ee.run_similarity = MagicMock(side_effect=RuntimeError("not authenticated"))
    window.run_ae_similarity()
    assert "not authenticated" in window.status_bar.currentMessage()


def test_clean_map_mode_hides_docks_and_status_bar(window):
    window.action_clean_map.setChecked(True)
    assert window.layers_dock.isVisible() is False
    assert window.status_bar.isVisible() is False

    window.action_clean_map.setChecked(False)
    assert window.layers_dock.isVisible() is True
    assert window.status_bar.isVisible() is True


def test_run_ae_similarity_requires_sign_in(window):
    geojson = json.dumps({"type": "Polygon", "coordinates": [[[0, 0], [0, 1], [1, 1], [0, 0]]]})
    window._on_polygon_drawn(geojson)
    window.context.ee_auth.is_authenticated.return_value = False

    window.run_ae_similarity()
    assert "sign in" in window.status_bar.currentMessage().lower()


def test_ee_auth_label_reflects_state(window):
    window.context.ee_auth.is_authenticated.return_value = True
    window._refresh_ee_auth_label()
    assert "signed in" in window.ee_auth_label.text().lower()
    assert "not" not in window.ee_auth_label.text().lower()

    window.context.ee_auth.is_authenticated.return_value = False
    window._refresh_ee_auth_label()
    assert "not signed in" in window.ee_auth_label.text().lower()


def test_sign_out_calls_auth_and_updates_label(window):
    window._sign_out_of_earth_engine()
    window.context.ee_auth.sign_out.assert_called_once()


def test_sign_in_worker_success_updates_status(window):
    window.context.ee_auth.is_authenticated.return_value = False
    window._sign_in_to_earth_engine()
    assert window._ee_sign_in_worker is not None
    _pump_until_thread_done(window._ee_sign_in_worker)
    assert "signed in" in window.status_bar.currentMessage().lower()


def test_sign_in_worker_failure_updates_status(window):
    window.context.ee_auth.authenticate_interactive.side_effect = RuntimeError("no browser available")
    window._sign_in_to_earth_engine()
    _pump_until_thread_done(window._ee_sign_in_worker)
    assert "no browser available" in window.status_bar.currentMessage()


def test_pin_drop_refused_without_open_project(window):
    window.action_add_pin.setChecked(True)
    assert window.action_add_pin.isChecked() is False
    assert "project" in window.status_bar.currentMessage().lower()


def test_pin_drop_creates_pin_row_and_marker(window, tmp_path):
    from scout.core import repository as repo

    window.context.new_project(tmp_path / "p.scout.db", "SOL", "RUG", "CRK")
    window.map_panel = MagicMock()
    window.layers_panel = MagicMock()

    window._on_point_clicked(-2.7, 53.7)

    pins = repo.list_pins(window.context.conn, "SOL-RUG-CRK")
    assert len(pins) == 1
    assert pins[0]["pin_id"] == "SOL-RUG-CRK-OBS-001"
    assert pins[0]["lon"] == -2.7
    assert pins[0]["lat"] == 53.7

    window.map_panel.add_marker.assert_called_once_with(
        "SOL-RUG-CRK-OBS-001", -2.7, 53.7, popup_text="SOL-RUG-CRK-OBS-001"
    )
    window.layers_panel.add_pin_marker.assert_called_once_with(
        "SOL-RUG-CRK-OBS-001", "SOL-RUG-CRK-OBS-001"
    )


def test_pin_numbers_do_not_collide_across_drops(window, tmp_path):
    from scout.core import repository as repo

    window.context.new_project(tmp_path / "p.scout.db", "SOL", "RUG", "CRK")
    window.map_panel = MagicMock()
    window.layers_panel = MagicMock()

    window._on_point_clicked(0.0, 0.0)
    window._on_point_clicked(1.0, 1.0)

    pins = repo.list_pins(window.context.conn, "SOL-RUG-CRK")
    assert {p["pin_id"] for p in pins} == {
        "SOL-RUG-CRK-OBS-001", "SOL-RUG-CRK-OBS-002",
    }


def test_layer_visibility_dispatches_by_kind(window):
    window.map_panel = MagicMock()
    window._on_layer_visibility_changed("resp-1", True, "raster")
    window.map_panel.set_layer_visible.assert_called_once_with("resp-1", True)
    window.map_panel.set_marker_visible.assert_not_called()

    window.map_panel.reset_mock()
    window._on_layer_visibility_changed("pin-1", False, "marker")
    window.map_panel.set_marker_visible.assert_called_once_with("pin-1", False)
    window.map_panel.set_layer_visible.assert_not_called()


def test_add_current_run_to_queue_requires_geometry(window, tmp_path):
    window.context.new_project(tmp_path / "p.scout.db", "SOL", "RUG", "CRK")
    window._add_current_run_to_queue()
    assert "polygon" in window.status_bar.currentMessage().lower()


def test_add_current_run_to_queue_requires_project(window):
    geojson = json.dumps({"type": "Polygon", "coordinates": [[[0, 0], [0, 1], [1, 1], [0, 0]]]})
    window._on_polygon_drawn(geojson)
    window._add_current_run_to_queue()
    assert "project" in window.status_bar.currentMessage().lower()


def test_add_current_run_to_queue_inserts_job(window, tmp_path):
    from scout.core import repository as repo

    window.context.new_project(tmp_path / "p.scout.db", "SOL", "RUG", "CRK")
    geojson = json.dumps({"type": "Polygon", "coordinates": [[[0, 0], [0, 1], [1, 1], [0, 0]]]})
    window._on_polygon_drawn(geojson)

    window._add_current_run_to_queue()

    jobs = repo.list_batch_jobs(window.context.conn, "SOL-RUG-CRK")
    assert len(jobs) == 1
    assert jobs[0]["job_kind"] == "ae_response"
    assert jobs[0]["status"] == "queued"


def test_run_batch_queue_empty_reports_status(window, tmp_path):
    window.context.new_project(tmp_path / "p.scout.db", "SOL", "RUG", "CRK")
    window.run_batch_queue("None")
    assert "empty" in window.status_bar.currentMessage().lower()


def test_run_batch_queue_requires_sign_in(window, tmp_path):
    window.context.new_project(tmp_path / "p.scout.db", "SOL", "RUG", "CRK")
    window.context.ee_auth.is_authenticated.return_value = False
    window.run_batch_queue("None")
    assert "sign in" in window.status_bar.currentMessage().lower()


def test_run_batch_queue_processes_all_jobs(window, tmp_path):
    from scout.core import repository as repo

    window.context.new_project(tmp_path / "p.scout.db", "SOL", "RUG", "CRK")
    geojson = json.dumps({"type": "Polygon", "coordinates": [[[0, 0], [0, 1], [1, 1], [0, 0]]]})
    window._on_polygon_drawn(geojson)
    window._add_current_run_to_queue()
    window._add_current_run_to_queue()

    fake_map_id = {"tile_fetcher": MagicMock(url_format="https://example.com/{z}/{x}/{y}")}
    window.context.ee.ee.Image.return_value.getMapId.return_value = fake_map_id

    window.run_batch_queue("None")

    jobs = repo.list_batch_jobs(window.context.conn, "SOL-RUG-CRK")
    assert all(j["status"] == "done" for j in jobs)
    assert "2 succeeded, 0 failed" in window.status_bar.currentMessage()


def test_run_batch_queue_records_per_job_failure_and_continues(window, tmp_path):
    from scout.core import repository as repo

    window.context.new_project(tmp_path / "p.scout.db", "SOL", "RUG", "CRK")
    geojson = json.dumps({"type": "Polygon", "coordinates": [[[0, 0], [0, 1], [1, 1], [0, 0]]]})
    window._on_polygon_drawn(geojson)
    window._add_current_run_to_queue()

    window.context.ee.run_similarity = MagicMock(side_effect=RuntimeError("EE quota exceeded"))
    window.run_batch_queue("None")

    jobs = repo.list_batch_jobs(window.context.conn, "SOL-RUG-CRK")
    assert jobs[0]["status"] == "failed"
    assert "EE quota exceeded" in jobs[0]["error_message"]
    assert "1 succeeded, 1 failed" not in window.status_bar.currentMessage()  # sanity: only 1 job total
    assert "0 succeeded, 1 failed" in window.status_bar.currentMessage()


def test_run_batch_queue_asks_before_sleeping_and_respects_no(window, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    window.context.new_project(tmp_path / "p.scout.db", "SOL", "RUG", "CRK")
    geojson = json.dumps({"type": "Polygon", "coordinates": [[[0, 0], [0, 1], [1, 1], [0, 0]]]})
    window._on_polygon_drawn(geojson)
    window._add_current_run_to_queue()

    fake_map_id = {"tile_fetcher": MagicMock(url_format="https://example.com/{z}/{x}/{y}")}
    window.context.ee.ee.Image.return_value.getMapId.return_value = fake_map_id

    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.No))
    power_calls = []
    monkeypatch.setattr("scout.app.main_window.perform_power_action", power_calls.append)

    window.run_batch_queue("Sleep")
    assert power_calls == []  # user said No


def test_run_batch_queue_sleeps_when_confirmed(window, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    window.context.new_project(tmp_path / "p.scout.db", "SOL", "RUG", "CRK")
    geojson = json.dumps({"type": "Polygon", "coordinates": [[[0, 0], [0, 1], [1, 1], [0, 0]]]})
    window._on_polygon_drawn(geojson)
    window._add_current_run_to_queue()

    fake_map_id = {"tile_fetcher": MagicMock(url_format="https://example.com/{z}/{x}/{y}")}
    window.context.ee.ee.Image.return_value.getMapId.return_value = fake_map_id

    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.Yes))
    power_calls = []
    monkeypatch.setattr("scout.app.main_window.perform_power_action", power_calls.append)

    window.run_batch_queue("Sleep")
    assert power_calls == ["Sleep"]


def test_save_latent_signature_requires_prior_run(window, tmp_path):
    window.context.new_project(tmp_path / "p.scout.db", "SOL", "RUG", "CRK")
    window._save_as_latent_signature()
    assert "run ae" in window.status_bar.currentMessage().lower()


def test_save_latent_signature_requires_project(window):
    window._last_similarity_result = MagicMock()
    window._save_as_latent_signature()
    assert "project" in window.status_bar.currentMessage().lower()


def test_save_latent_signature_cancelled_dialog_saves_nothing(window, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QInputDialog
    from scout.core import repository as repo

    window.context.new_project(tmp_path / "p.scout.db", "SOL", "RUG", "CRK")
    window._last_similarity_result = MagicMock()
    monkeypatch.setattr(QInputDialog, "getText", staticmethod(lambda *a, **k: ("", False)))

    window._save_as_latent_signature()
    assert repo.list_latent_signatures(window.context.conn, "SOL-RUG-CRK") == []


def test_save_latent_signature_creates_row(window, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QInputDialog
    from scout.core import repository as repo

    window.context.new_project(tmp_path / "p.scout.db", "SOL", "RUG", "CRK")
    window._last_reference_geometry_geojson = json.dumps(
        {"type": "Polygon", "coordinates": [[[0, 0], [0, 1], [1, 1], [0, 0]]]}
    )
    fake_result = MagicMock()
    fake_result.raw_vector_list.getInfo.return_value = [0.01 * i for i in range(64)]
    fake_result.vector_norm.getInfo.return_value = 1.23456
    window._last_similarity_result = fake_result

    monkeypatch.setattr(QInputDialog, "getText", staticmethod(lambda *a, **k: ("Panel core", True)))

    window._save_as_latent_signature()

    sigs = repo.list_latent_signatures(window.context.conn, "SOL-RUG-CRK")
    assert len(sigs) == 1
    assert sigs[0]["signature_id"] == "SOL-RUG-CRK-SIG-001"
    assert sigs[0]["label"] == "Panel core"
    assert sigs[0]["source_type"] == "drawn"
    assert sigs[0]["vector_norm"] == 1.23456
    assert json.loads(sigs[0]["vector_json"]) == [0.01 * i for i in range(64)]
    assert "signature" in window.status_bar.currentMessage().lower() or "saved" in window.status_bar.currentMessage().lower()


def test_new_project_wiring_creates_project_from_dialog_values(window, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QFileDialog
    from scout.app.dialogs.new_project_dialog import NewProjectDialog

    monkeypatch.setattr(NewProjectDialog, "exec", lambda self: NewProjectDialog.Accepted)
    monkeypatch.setattr(NewProjectDialog, "values", lambda self: {
        "project_code": "SOL", "location_code": "RUG", "sublocation_code": "CRK",
        "project_name": "Calibration",
    })
    db_path = str(tmp_path / "new.scout.db")
    monkeypatch.setattr(QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: (db_path, "")))

    window._prompt_new_project()

    assert window.context.project is not None
    assert window.context.project.project_key == "SOL-RUG-CRK"
    assert "created" in window.status_bar.currentMessage().lower()


def test_new_project_wiring_cancelled_dialog_creates_nothing(window, monkeypatch):
    from scout.app.dialogs.new_project_dialog import NewProjectDialog

    monkeypatch.setattr(NewProjectDialog, "exec", lambda self: NewProjectDialog.Rejected)

    window._prompt_new_project()
    assert window.context.project is None


def test_add_probe_refused_without_open_project(window):
    window.action_add_probe.setChecked(True)
    assert window.action_add_probe.isChecked() is False
    assert "project" in window.status_bar.currentMessage().lower()


def test_add_probe_refused_without_sign_in(window, tmp_path):
    window.context.new_project(tmp_path / "p.scout.db", "SOL", "RUG", "CRK")
    window.context.ee_auth.is_authenticated.return_value = False
    window.action_add_probe.setChecked(True)
    assert window.action_add_probe.isChecked() is False
    assert "sign in" in window.status_bar.currentMessage().lower()


def test_draw_pin_and_probe_actions_are_mutually_exclusive(window, tmp_path):
    window.context.new_project(tmp_path / "p.scout.db", "SOL", "RUG", "CRK")
    window.map_panel = MagicMock()

    window.action_draw_polygon.setChecked(True)
    window.action_add_pin.setChecked(True)
    assert window.action_draw_polygon.isChecked() is False
    assert window.action_add_probe.isChecked() is False

    window.action_add_probe.setChecked(True)
    assert window.action_add_pin.isChecked() is False
    assert window.action_draw_polygon.isChecked() is False


def test_point_click_in_probe_mode_saves_a_probe_pin(window, tmp_path):
    from scout.core import repository as repo

    window.context.new_project(tmp_path / "p.scout.db", "SOL", "RUG", "CRK")
    window.action_add_probe.setChecked(True)
    assert window._armed_pin_mode == "probe"

    mock_ee = window.context.ee.ee
    mock_ee.Reducer.mean.return_value = "MEAN_REDUCER"
    # AE sampling goes through build_reference_vector, which calls
    # reduceRegion + Array math on the mock; only the final .getInfo()
    # calls need real-ish values.
    fake_mean_dict = mock_ee.ImageCollection.return_value.filterDate.return_value.filterBounds.return_value \
        .mosaic.return_value.select.return_value.reduceRegion.return_value
    fake_mean_dict.get.return_value = 0.01
    array_chain = mock_ee.Array.return_value
    array_chain.pow.return_value.reduce.return_value.sqrt.return_value.get.return_value.getInfo.return_value = 1.23
    mock_ee.List.return_value.getInfo.return_value = [0.01] * 64

    dw_reduce = mock_ee.ImageCollection.return_value.filterDate.return_value.filterBounds.return_value \
        .select.return_value.mean.return_value.reduceRegion.return_value
    dw_reduce.getInfo.return_value = {"crops": 0.5, "built": 0.1}

    # No Sentinel-2 scenes available for this probe's date range.
    mock_ee.ImageCollection.return_value.filterBounds.return_value.filterDate.return_value \
        .filter.return_value.map.return_value.size.return_value.getInfo.return_value = 0

    window._on_point_clicked(-2.7, 53.7)

    pins = repo.list_pins(window.context.conn, "SOL-RUG-CRK", pin_type="probe")
    assert len(pins) == 1
    assert pins[0]["pin_id"] == "SOL-RUG-CRK-PRB-001"
    assert pins[0]["s2_scene_count"] == 0
    assert window.action_add_probe.isChecked() is False


def test_point_click_in_probe_mode_includes_s2_when_scenes_exist(window, tmp_path):
    from scout.core import repository as repo

    window.context.new_project(tmp_path / "p.scout.db", "SOL", "RUG", "CRK")
    window.action_add_probe.setChecked(True)

    mock_ee = window.context.ee.ee
    ae_reduce = mock_ee.ImageCollection.return_value.filterDate.return_value.filterBounds.return_value \
        .mosaic.return_value.select.return_value.reduceRegion.return_value
    ae_reduce.get.return_value = 0.01
    array_chain = mock_ee.Array.return_value
    array_chain.pow.return_value.reduce.return_value.sqrt.return_value.get.return_value.getInfo.return_value = 1.0
    mock_ee.List.return_value.getInfo.return_value = [0.01] * 64

    dw_reduce = mock_ee.ImageCollection.return_value.filterDate.return_value.filterBounds.return_value \
        .select.return_value.mean.return_value.reduceRegion.return_value
    dw_reduce.getInfo.return_value = {"crops": 0.5}

    s2_map_chain = mock_ee.ImageCollection.return_value.filterBounds.return_value.filterDate.return_value \
        .filter.return_value.map.return_value
    s2_map_chain.size.return_value.getInfo.return_value = 3  # scenes found this time

    # get_s2_feature_image composes several .select()/.normalizedDifference()/.expression()
    # calls on the median composite; only the final reduceRegion().getInfo() matters here.
    composite = s2_map_chain.median.return_value
    s2_feature_reduce = composite.select.return_value.addBands.return_value.addBands.return_value \
        .addBands.return_value.addBands.return_value.addBands.return_value.addBands.return_value \
        .addBands.return_value.reduceRegion.return_value
    s2_feature_reduce.getInfo.return_value = {"NDVI": 0.42}

    window._on_point_clicked(-2.7, 53.7)

    pins = repo.list_pins(window.context.conn, "SOL-RUG-CRK", pin_type="probe")
    assert len(pins) == 1
    assert pins[0]["s2_scene_count"] == 3
    assert json.loads(pins[0]["s2_json"]) == {"NDVI": 0.42}


def test_probe_sampling_failure_is_surfaced_not_swallowed(window, tmp_path):
    window.context.new_project(tmp_path / "p.scout.db", "SOL", "RUG", "CRK")
    window.action_add_probe.setChecked(True)
    window.context.ee.build_reference_vector = MagicMock(side_effect=RuntimeError("EE quota exceeded"))

    window._on_point_clicked(0.0, 0.0)
    assert "EE quota exceeded" in window.status_bar.currentMessage()


def test_new_pin_group_requires_project(window):
    window._prompt_new_pin_group()
    assert "project" in window.status_bar.currentMessage().lower()


def test_new_pin_group_creates_row_and_layers_panel_node(window, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QInputDialog
    from scout.core import repository as repo

    window.context.new_project(tmp_path / "p.scout.db", "SOL", "RUG", "CRK")
    monkeypatch.setattr(QInputDialog, "getText", staticmethod(lambda *a, **k: ("Seep line", True)))

    window._prompt_new_pin_group()

    groups = repo.list_pin_groups(window.context.conn, "SOL-RUG-CRK")
    assert [g["name"] for g in groups] == ["Seep line"]
    assert window.layers_panel._groups["Pins"].childCount() == 1
    window.layers_panel.ensure_pin_group("Seep line")  # calling again must reuse, not duplicate
    assert window.layers_panel._groups["Pins"].childCount() == 1


def test_new_pin_group_cancelled_dialog_creates_nothing(window, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QInputDialog
    from scout.core import repository as repo

    window.context.new_project(tmp_path / "p.scout.db", "SOL", "RUG", "CRK")
    monkeypatch.setattr(QInputDialog, "getText", staticmethod(lambda *a, **k: ("", False)))

    window._prompt_new_pin_group()
    assert repo.list_pin_groups(window.context.conn, "SOL-RUG-CRK") == []


def test_move_pin_to_group_updates_db_and_panel(window, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QInputDialog
    from scout.core import repository as repo

    window.context.new_project(tmp_path / "p.scout.db", "SOL", "RUG", "CRK")
    window.action_add_pin.setChecked(True)
    window._on_point_clicked(0.0, 0.0)
    pin_id = "SOL-RUG-CRK-OBS-001"
    repo.create_pin_group(window.context.conn, "SOL-RUG-CRK", "Seep line")

    monkeypatch.setattr(QInputDialog, "getItem", staticmethod(lambda *a, **k: ("Seep line", True)))
    window._prompt_move_pin_to_group(pin_id)

    pin_row = repo.list_pins(window.context.conn, "SOL-RUG-CRK")[0]
    group_row = repo.get_pin_group(window.context.conn, pin_row["group_id"])
    assert group_row["name"] == "Seep line"
    item = window.layers_panel._find_layer_item(pin_id)
    assert item.parent().text(0) == "Seep line"


def test_move_pin_to_group_none_option_clears_group(window, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QInputDialog
    from scout.core import repository as repo

    window.context.new_project(tmp_path / "p.scout.db", "SOL", "RUG", "CRK")
    window.action_add_pin.setChecked(True)
    window._on_point_clicked(0.0, 0.0)
    pin_id = "SOL-RUG-CRK-OBS-001"

    monkeypatch.setattr(QInputDialog, "getItem", staticmethod(lambda *a, **k: ("(no group)", True)))
    window._prompt_move_pin_to_group(pin_id)

    pin_row = repo.list_pins(window.context.conn, "SOL-RUG-CRK")[0]
    assert pin_row["group_id"] is None


def test_edit_pin_tags_replaces_tags(window, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QInputDialog
    from scout.core import repository as repo

    window.context.new_project(tmp_path / "p.scout.db", "SOL", "RUG", "CRK")
    window.action_add_pin.setChecked(True)
    window._on_point_clicked(0.0, 0.0)
    pin_id = "SOL-RUG-CRK-OBS-001"

    monkeypatch.setattr(QInputDialog, "getText", staticmethod(lambda *a, **k: ("panel-edge, calibration", True)))
    window._prompt_edit_pin_tags(pin_id)

    assert repo.get_pin_tags(window.context.conn, pin_id) == ["calibration", "panel-edge"]


def test_pin_context_menu_dispatches_to_move_or_tags(window, monkeypatch):
    calls = []
    monkeypatch.setattr(window, "_prompt_move_pin_to_group", lambda pin_id: calls.append(("move", pin_id)))
    monkeypatch.setattr(window, "_prompt_edit_pin_tags", lambda pin_id: calls.append(("tags", pin_id)))

    # "Move to group…" is the first action added — exercise that branch.
    monkeypatch.setattr(window, "_exec_menu", lambda menu, pos: menu.actions()[0])
    window._on_pin_context_menu("pin-1", None)
    assert calls == [("move", "pin-1")]

    # "Edit tags…" is the second action added — exercise that branch too.
    calls.clear()
    monkeypatch.setattr(window, "_exec_menu", lambda menu, pos: menu.actions()[1])
    window._on_pin_context_menu("pin-1", None)
    assert calls == [("tags", "pin-1")]


def test_refresh_pins_reloads_saved_pins_after_reopen(window, tmp_path):
    from scout.core import repository as repo

    db_path = tmp_path / "p.scout.db"
    window.context.new_project(db_path, "SOL", "RUG", "CRK")
    window.action_add_pin.setChecked(True)
    window._on_point_clicked(-2.7, 53.7)
    window.context.close()

    window.context.open_project(db_path)
    window.map_panel = MagicMock()
    window.refresh_pins()

    item = window.layers_panel._find_layer_item("SOL-RUG-CRK-OBS-001")
    assert item is not None
    window.map_panel.add_marker.assert_called_once_with(
        "SOL-RUG-CRK-OBS-001", -2.7, 53.7, popup_text="SOL-RUG-CRK-OBS-001"
    )


def test_compose_session_report_requires_project(window):
    window._compose_session_report()
    assert "project" in window.status_bar.currentMessage().lower()


def test_compose_session_report_writes_file(window, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QFileDialog

    window.context.new_project(tmp_path / "p.scout.db", "SOL", "RUG", "CRK")
    output_path = str(tmp_path / "out.md")
    monkeypatch.setattr(QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: (output_path, "")))

    window._compose_session_report()

    assert Path(output_path).exists()
    assert "SOL-RUG-CRK" in Path(output_path).read_text()
    assert "written to" in window.status_bar.currentMessage().lower()


def test_compose_session_report_cancelled_dialog_writes_nothing(window, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QFileDialog

    window.context.new_project(tmp_path / "p.scout.db", "SOL", "RUG", "CRK")
    monkeypatch.setattr(QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: ("", "")))

    window._compose_session_report()
    assert not (tmp_path / "p_report.md").exists()


def test_draw_polygon_and_add_pin_are_mutually_exclusive(window, tmp_path):
    window.context.new_project(tmp_path / "p.scout.db", "SOL", "RUG", "CRK")  # add-pin now requires one
    window.map_panel = MagicMock()
    window.action_draw_polygon.setChecked(True)
    assert window.action_add_pin.isChecked() is False

    window.action_add_pin.setChecked(True)
    assert window.action_draw_polygon.isChecked() is False
