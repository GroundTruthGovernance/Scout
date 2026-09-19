import json
from unittest.mock import MagicMock

import pytest

from scout.app.main_window import MainWindow
from scout.app.project_context import ProjectContext
from scout.core.ee_backend import EarthEngineBackend


@pytest.fixture
def window(qapp):
    context = ProjectContext(ee_backend=EarthEngineBackend(ee_module=MagicMock()))
    win = MainWindow(context=context)
    win.show()  # dock/toolbar visibility is hierarchical in Qt — an unshown
    # top-level window makes every child report isVisible() == False
    # regardless of its own setVisible() calls, which would make the clean
    # map mode test pass vacuously rather than actually exercising it.
    yield win
    win.close()


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


def test_draw_polygon_and_add_pin_are_mutually_exclusive(window):
    window.map_panel = MagicMock()
    window.action_draw_polygon.setChecked(True)
    assert window.action_add_pin.isChecked() is False

    window.action_add_pin.setChecked(True)
    assert window.action_draw_polygon.isChecked() is False
