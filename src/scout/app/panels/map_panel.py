"""The embedded map: one QWebEngineView hosting MapLibre GL JS.

See docs/ARCHITECTURE.md ("Map" row of the tech stack table) for why this
is a single Chromium process with JS-side pane management rather than
multiple QWebEngineView widgets. Today only the "main" pane exists — Run
Compare / Tiled Product View add more pane ids to the same page later.
"""

from __future__ import annotations

import json
from importlib import resources

from PySide6.QtCore import QObject, QUrl, Signal, Slot
from PySide6.QtWebChannel import QWebChannel
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QVBoxLayout, QWidget


class MapBridge(QObject):
    """Exposed to JS as `window.bridge` via QWebChannel. JS calls the
    `on_*` slots directly (see webmap/map.js); Python code listens on the
    plain Qt signals instead of the slots themselves.
    """

    polygon_drawn = Signal(str)     # GeoJSON Polygon, as text
    point_clicked = Signal(float, float)   # lon, lat — used for pin placement
    map_clicked = Signal(float, float)     # lon, lat — coordinate readout / eyedropper
    map_ready = Signal()

    @Slot(str)
    def on_polygon_drawn(self, geojson_text: str) -> None:
        self.polygon_drawn.emit(geojson_text)

    @Slot(float, float)
    def on_point_clicked(self, lon: float, lat: float) -> None:
        self.point_clicked.emit(lon, lat)

    @Slot(float, float)
    def on_map_clicked(self, lon: float, lat: float) -> None:
        self.map_clicked.emit(lon, lat)

    @Slot()
    def on_map_ready(self) -> None:
        self.map_ready.emit()


class MapPanel(QWidget):
    """Python-side API for the "main" map pane. Every method here is a
    thin `runJavaScript` call into webmap/map.js's `window.scoutMap`."""

    PANE_ID = "main"

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)

        self.bridge = MapBridge()
        self.view = QWebEngineView(self)
        self.channel = QWebChannel(self.view.page())
        self.channel.registerObject("bridge", self.bridge)
        self.view.page().setWebChannel(self.channel)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.view)

        html_path = resources.files("scout.webmap").joinpath("map.html")
        self.view.load(QUrl.fromLocalFile(str(html_path)))

    def _run_js(self, code: str) -> None:
        self.view.page().runJavaScript(code)

    def enable_draw_polygon(self) -> None:
        self._run_js(f'window.scoutMap.enableDrawPolygon("{self.PANE_ID}");')

    def enable_pin_drop(self) -> None:
        self._run_js(f'window.scoutMap.enablePinDrop("{self.PANE_ID}");')

    def disable_drawing(self) -> None:
        self._run_js(f'window.scoutMap.disableDrawing("{self.PANE_ID}");')

    def clear_drawn_geometry(self) -> None:
        self._run_js(f'window.scoutMap.clearDrawnGeometry("{self.PANE_ID}");')

    def set_base_style(self, style_name: str) -> None:
        """style_name: 'osm' | 'satellite'."""
        self._run_js(f'window.scoutMap.setBaseStyle("{self.PANE_ID}", {json.dumps(style_name)});')

    def add_raster_layer(self, layer_id: str, tile_url_template: str, opacity: float = 1.0) -> None:
        """tile_url_template is an EE `getMapId()` tile URL containing
        literal {z}/{x}/{y} placeholders — json.dumps is used (not raw
        string interpolation) so the URL's braces and any special
        characters can't break the generated JS."""
        self._run_js(
            "window.scoutMap.addRasterLayer(%s, %s, %s, %s);"
            % (json.dumps(self.PANE_ID), json.dumps(layer_id), json.dumps(tile_url_template), opacity)
        )

    def set_layer_opacity(self, layer_id: str, opacity: float) -> None:
        self._run_js(
            "window.scoutMap.setLayerOpacity(%s, %s, %s);"
            % (json.dumps(self.PANE_ID), json.dumps(layer_id), opacity)
        )

    def set_layer_visible(self, layer_id: str, visible: bool) -> None:
        self._run_js(
            "window.scoutMap.setLayerVisible(%s, %s, %s);"
            % (json.dumps(self.PANE_ID), json.dumps(layer_id), "true" if visible else "false")
        )

    def remove_layer(self, layer_id: str) -> None:
        self._run_js(
            "window.scoutMap.removeLayer(%s, %s);" % (json.dumps(self.PANE_ID), json.dumps(layer_id))
        )

    def fly_to(self, lon: float, lat: float, zoom: float) -> None:
        self._run_js(f'window.scoutMap.flyTo("{self.PANE_ID}", {lon}, {lat}, {zoom});')

    def add_marker(self, marker_id: str, lon: float, lat: float, color: str = "#00FFFF",
                    popup_text: str = "") -> None:
        self._run_js(
            "window.scoutMap.addMarker(%s, %s, %s, %s, %s, %s);"
            % (json.dumps(self.PANE_ID), json.dumps(marker_id), lon, lat,
               json.dumps(color), json.dumps(popup_text))
        )

    def remove_marker(self, marker_id: str) -> None:
        self._run_js(
            "window.scoutMap.removeMarker(%s, %s);" % (json.dumps(self.PANE_ID), json.dumps(marker_id))
        )

    def set_marker_visible(self, marker_id: str, visible: bool) -> None:
        self._run_js(
            "window.scoutMap.setMarkerVisible(%s, %s, %s);"
            % (json.dumps(self.PANE_ID), json.dumps(marker_id), "true" if visible else "false")
        )

    def clear_markers(self) -> None:
        self._run_js(f'window.scoutMap.clearMarkers("{self.PANE_ID}");')
