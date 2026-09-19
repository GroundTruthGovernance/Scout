from PySide6.QtCore import QEventLoop, QTimer

from scout.app.panels.map_panel import MapBridge, MapPanel


def test_bridge_forwards_polygon_drawn_as_signal(qapp):
    bridge = MapBridge()
    received = []
    bridge.polygon_drawn.connect(received.append)
    bridge.on_polygon_drawn('{"type": "Polygon", "coordinates": []}')
    assert received == ['{"type": "Polygon", "coordinates": []}']


def test_bridge_forwards_point_clicked_as_signal(qapp):
    bridge = MapBridge()
    received = []
    bridge.point_clicked.connect(lambda lon, lat: received.append((lon, lat)))
    bridge.on_point_clicked(-2.95, 53.79)
    assert received == [(-2.95, 53.79)]


def test_bridge_forwards_map_clicked_as_signal(qapp):
    bridge = MapBridge()
    received = []
    bridge.map_clicked.connect(lambda lon, lat: received.append((lon, lat)))
    bridge.on_map_clicked(0.0, 0.0)
    assert received == [(0.0, 0.0)]


def test_map_panel_loads_html_without_error(qapp):
    panel = MapPanel()

    loop = QEventLoop()
    result = {}

    def on_load_finished(ok: bool):
        result["ok"] = ok
        loop.quit()

    panel.view.loadFinished.connect(on_load_finished)
    QTimer.singleShot(15000, loop.quit)  # safety timeout — no network needed for the page itself
    loop.exec()

    assert result.get("ok") is True, "map.html failed to load (see webmap/map.html + vendor/ assets)"
    panel.deleteLater()
