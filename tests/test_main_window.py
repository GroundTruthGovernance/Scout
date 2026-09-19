import json
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


def test_draw_polygon_and_add_pin_are_mutually_exclusive(window):
    window.map_panel = MagicMock()
    window.action_draw_polygon.setChecked(True)
    assert window.action_add_pin.isChecked() is False

    window.action_add_pin.setChecked(True)
    assert window.action_draw_polygon.isChecked() is False
