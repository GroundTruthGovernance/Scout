"""The Scout main window: menu bar, toolbars, dock panels, embedded map.

Menu/toolbar/panel structure follows docs/ARCHITECTURE.md exactly —
File, Edit, View, Layer, Sample, Run, Batch, Tools, Window, Help; a main
toolbar plus specialist toolbars independently hideable via
View > Toolbars; every dock panel listed (never destroyed) under
View > Panels.
"""

from __future__ import annotations

import json
import uuid

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QDockWidget,
    QFileDialog,
    QLabel,
    QMainWindow,
    QMessageBox,
    QStatusBar,
    QToolBar,
)

from scout.core import repository as repo
from scout.core.util import get_ae_vis, utc_now_iso
from scout._version import SCOUT_VERSION

from scout.app.panels.activity_log_panel import ActivityLogPanel
from scout.app.panels.attribute_table_panel import AttributeTablePanel
from scout.app.panels.batch_queue_panel import BatchQueuePanel
from scout.app.panels.layers_panel import LayersPanel
from scout.app.panels.map_panel import MapPanel
from scout.app.panels.python_console_panel import PythonConsolePanel
from scout.app.project_context import ProjectContext
from scout.app.ee_auth_worker import EarthEngineSignInWorker


class MainWindow(QMainWindow):
    def __init__(self, context: ProjectContext | None = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Scout {SCOUT_VERSION}")
        self.resize(1400, 900)

        self.context = context or ProjectContext()
        self._current_response_layer_id: str | None = None
        self._ee_sign_in_worker: EarthEngineSignInWorker | None = None

        self.map_panel = MapPanel(self)
        self.setCentralWidget(self.map_panel)

        self._build_docks()
        self._build_status_bar()
        self._build_actions()
        self._build_menus()
        self._build_toolbars()
        self._wire_signals()

    # -- Construction -----------------------------------------------------

    def _build_docks(self) -> None:
        self.layers_panel = LayersPanel(self)
        self.layers_dock = self._make_dock("Layers", self.layers_panel, Qt.LeftDockWidgetArea)

        self.activity_log_panel = ActivityLogPanel(self)
        self.activity_log_dock = self._make_dock(
            "Activity Log", self.activity_log_panel, Qt.BottomDockWidgetArea
        )

        self.attribute_table_panel = AttributeTablePanel(self)
        self.attribute_table_dock = self._make_dock(
            "Attribute Table", self.attribute_table_panel, Qt.BottomDockWidgetArea
        )

        self.batch_queue_panel = BatchQueuePanel(self)
        self.batch_queue_dock = self._make_dock(
            "Batch Queue", self.batch_queue_panel, Qt.RightDockWidgetArea
        )

        self.python_console_panel = PythonConsolePanel(
            namespace={"project_context": self.context}, parent=self
        )
        self.python_console_dock = self._make_dock(
            "Python Console", self.python_console_panel, Qt.BottomDockWidgetArea
        )
        self.python_console_dock.hide()  # power-user tool, out of the way by default

        self.tabifyDockWidget(self.activity_log_dock, self.attribute_table_dock)
        self.tabifyDockWidget(self.activity_log_dock, self.python_console_dock)

    def _make_dock(self, title: str, widget, area) -> QDockWidget:
        dock = QDockWidget(title, self)
        dock.setObjectName(title.replace(" ", "") + "Dock")
        dock.setWidget(widget)
        dock.setFeatures(
            QDockWidget.DockWidgetMovable | QDockWidget.DockWidgetFloatable | QDockWidget.DockWidgetClosable
        )
        self.addDockWidget(area, dock)
        return dock

    def _build_status_bar(self) -> None:
        self.status_bar = QStatusBar(self)
        self.setStatusBar(self.status_bar)
        self.coordinate_label = QLabel("", self)
        self.status_bar.addPermanentWidget(self.coordinate_label)
        self.ee_auth_label = QLabel("", self)
        self.status_bar.addPermanentWidget(self.ee_auth_label)
        self._refresh_ee_auth_label()
        self.set_status("Ready.")

    def _build_actions(self) -> None:
        # File
        self.action_new_project = QAction("&New Project…", self)
        self.action_open_project = QAction("&Open Project…", self)
        self.action_close_project = QAction("&Close Project", self)
        self.action_exit = QAction("E&xit", self)

        # Sample / drawing
        self.action_draw_polygon = QAction("Draw &Polygon", self, checkable=True)
        self.action_add_pin = QAction("Add &Pin", self, checkable=True)
        self.action_clear_geometry = QAction("&Clear Drawn Geometry", self)

        # Run
        self.action_run_ae = QAction("&Run AE Similarity", self)
        self.action_run_ae.setEnabled(False)  # enabled once a polygon exists

        # Batch
        self.action_add_to_queue = QAction("&Add Current Run to Queue", self)

        # Tools
        self.action_sign_in_ee = QAction("&Sign in to Earth Engine…", self)
        self.action_sign_out_ee = QAction("Sign &out of Earth Engine", self)

        # View
        self.action_clean_map = QAction("&Clean Map Mode", self, checkable=True)

        # Help
        self.action_about = QAction("&About Scout", self)

    def _build_menus(self) -> None:
        menu_bar = self.menuBar()

        file_menu = menu_bar.addMenu("&File")
        file_menu.addAction(self.action_new_project)
        file_menu.addAction(self.action_open_project)
        file_menu.addAction(self.action_close_project)
        file_menu.addSeparator()
        file_menu.addAction(self.action_exit)

        edit_menu = menu_bar.addMenu("&Edit")
        edit_menu.addAction("Preferences…")

        view_menu = menu_bar.addMenu("&View")
        panels_menu = view_menu.addMenu("&Panels")
        for dock in (
            self.layers_dock, self.activity_log_dock, self.attribute_table_dock,
            self.batch_queue_dock, self.python_console_dock,
        ):
            panels_menu.addAction(dock.toggleViewAction())
        view_menu.addMenu(panels_menu)
        self.toolbars_menu = view_menu.addMenu("&Toolbars")
        view_menu.addSeparator()
        view_menu.addAction(self.action_clean_map)

        layer_menu = menu_bar.addMenu("&Layer")
        layer_menu.addAction("Zoom to Layer")
        layer_menu.addAction("Layer Properties…")

        sample_menu = menu_bar.addMenu("&Sample")
        sample_menu.addAction(self.action_draw_polygon)
        sample_menu.addAction(self.action_add_pin)
        sample_menu.addAction(self.action_clear_geometry)

        run_menu = menu_bar.addMenu("&Run")
        run_menu.addAction(self.action_run_ae)

        batch_menu = menu_bar.addMenu("&Batch")
        batch_menu.addAction(self.action_add_to_queue)

        tools_menu = menu_bar.addMenu("&Tools")
        tools_menu.addAction(self.python_console_dock.toggleViewAction())
        tools_menu.addSeparator()
        tools_menu.addAction(self.action_sign_in_ee)
        tools_menu.addAction(self.action_sign_out_ee)

        window_menu = menu_bar.addMenu("&Window")
        window_menu.addAction("Reset Layout")

        help_menu = menu_bar.addMenu("&Help")
        help_menu.addAction(self.action_about)

    def _build_toolbars(self) -> None:
        self.main_toolbar = QToolBar("Main", self)
        self.main_toolbar.setObjectName("MainToolbar")
        self.main_toolbar.addAction(self.action_draw_polygon)
        self.main_toolbar.addAction(self.action_add_pin)
        self.main_toolbar.addAction(self.action_run_ae)
        self.addToolBar(self.main_toolbar)
        self.toolbars_menu.addAction(self.main_toolbar.toggleViewAction())

        # Specialist toolbars: empty for now beyond a label, populated as
        # their features are wired up (Task #9). Present in the menu
        # structure now so hiding/showing them is already a supported,
        # persisted action rather than a later UI change.
        for name in ("HSV", "Latent Inspection", "Batch", "Compare"):
            toolbar = QToolBar(name, self)
            toolbar.setObjectName(name.replace(" ", "") + "Toolbar")
            toolbar.setVisible(False)
            self.addToolBar(toolbar)
            self.toolbars_menu.addAction(toolbar.toggleViewAction())

    def _wire_signals(self) -> None:
        self.action_new_project.triggered.connect(self._prompt_new_project)
        self.action_open_project.triggered.connect(self._prompt_open_project)
        self.action_close_project.triggered.connect(self.context.close)
        self.action_exit.triggered.connect(self.close)

        self.action_draw_polygon.toggled.connect(self._on_draw_polygon_toggled)
        self.action_add_pin.toggled.connect(self._on_add_pin_toggled)
        self.action_clear_geometry.triggered.connect(self._on_clear_geometry)
        self.action_run_ae.triggered.connect(self.run_ae_similarity)
        self.action_clean_map.toggled.connect(self._on_clean_map_toggled)
        self.action_about.triggered.connect(self._show_about)
        self.action_sign_in_ee.triggered.connect(self._sign_in_to_earth_engine)
        self.action_sign_out_ee.triggered.connect(self._sign_out_of_earth_engine)

        self.map_panel.bridge.polygon_drawn.connect(self._on_polygon_drawn)
        self.map_panel.bridge.point_clicked.connect(self._on_point_clicked)
        self.map_panel.bridge.map_clicked.connect(self._on_map_clicked)

        self.context.activity_logged.connect(self._on_activity_logged)
        self.layers_panel.layer_visibility_changed.connect(self.map_panel.set_layer_visible)

    # -- File menu handlers -------------------------------------------------

    def _prompt_new_project(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "New Scout Project", "", "Scout project (*.scout.db)")
        if not path:
            return
        # A dedicated project-identity dialog belongs here; deferred so the
        # golden path (draw -> run -> see a result) isn't blocked on it.
        # Auto-fill placeholder request; real UI is a follow-up.
        self.set_status(f"New project file selected: {path} (identity dialog not yet built).")

    def _prompt_open_project(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Open Scout Project", "", "Scout project (*.scout.db)")
        if not path:
            return
        try:
            project = self.context.open_project(path)
            self.set_status(f"Opened {project.project_key}.")
            self.refresh_activity_log()
            self.refresh_attribute_table()
        except ValueError as exc:
            QMessageBox.critical(self, "Open Project", str(exc))

    # -- Drawing / map interaction -------------------------------------

    def _on_draw_polygon_toggled(self, checked: bool) -> None:
        if checked:
            self.action_add_pin.setChecked(False)
            self.map_panel.enable_draw_polygon()
        else:
            self.map_panel.disable_drawing()

    def _on_add_pin_toggled(self, checked: bool) -> None:
        if checked:
            self.action_draw_polygon.setChecked(False)
            self.map_panel.enable_pin_drop()
        else:
            self.map_panel.disable_drawing()

    def _on_clear_geometry(self) -> None:
        self.map_panel.clear_drawn_geometry()
        self.context.exploration.reference_geometry_geojson = None
        self.action_run_ae.setEnabled(False)

    def _on_polygon_drawn(self, geojson_text: str) -> None:
        self.context.exploration.reference_geometry_geojson = geojson_text
        self.action_draw_polygon.setChecked(False)
        self.action_run_ae.setEnabled(True)
        self.context.log("info", "Reference polygon drawn.")

    def _on_point_clicked(self, lon: float, lat: float) -> None:
        self.action_add_pin.setChecked(False)
        self.context.log("info", f"Pin location selected at {lon:.6f}, {lat:.6f}.")

    def _on_map_clicked(self, lon: float, lat: float) -> None:
        self.coordinate_label.setText(f"Lon {lon:.6f}  Lat {lat:.6f}")

    def _on_clean_map_toggled(self, checked: bool) -> None:
        for dock in self.findChildren(QDockWidget):
            dock.setVisible(not checked)
        for toolbar in self.findChildren(QToolBar):
            toolbar.setVisible(not checked and toolbar is self.main_toolbar)
        self.status_bar.setVisible(not checked)

    # -- Run AE (the golden path) ---------------------------------------

    def run_ae_similarity(self) -> None:
        geojson_text = self.context.exploration.reference_geometry_geojson
        if not geojson_text:
            self.set_status("Draw a reference polygon first.", error=True)
            return
        if not self.context.ee_auth.is_authenticated():
            self.set_status("Sign in to Earth Engine first (Tools > Sign in to Earth Engine…).", error=True)
            return

        ee = self.context.ee.ee
        try:
            reference_geometry = ee.Geometry(json.loads(geojson_text))
            exploration = self.context.exploration
            search_geometry = self.context.ee.get_search_geometry(
                exploration.search_extent, reference_geometry
            )

            self.set_status("Calculating AE similarity…")
            result = self.context.ee.run_similarity(
                exploration.reference_year, exploration.target_year,
                reference_geometry, search_geometry,
            )

            if exploration.threshold_mode == "percentile":
                threshold_value = self.context.ee.resolve_percentile_threshold(
                    result.similarity, search_geometry, exploration.threshold * 100
                )
                masked = self.context.ee.apply_percentile_threshold(result.similarity, threshold_value)
                cutoff_for_vis = threshold_value.getInfo()
            else:
                masked = self.context.ee.apply_absolute_threshold(result.similarity, exploration.threshold)
                cutoff_for_vis = exploration.threshold

            vis_params = get_ae_vis(cutoff_for_vis, exploration.mask_display_style, exploration.mask_color)
            map_id = ee.Image(masked).getMapId(vis_params)
            tile_url_template = map_id["tile_fetcher"].url_format

            layer_id = f"response-preview-{uuid.uuid4().hex[:8]}"
            if self._current_response_layer_id:
                self.map_panel.remove_layer(self._current_response_layer_id)
                self.layers_panel.remove_layer(self._current_response_layer_id)
            self.map_panel.add_raster_layer(layer_id, tile_url_template, exploration.mask_opacity)
            self.layers_panel.add_layer("Responses", layer_id, "Current AE response (unsaved)")
            self._current_response_layer_id = layer_id

            self.set_status("AE response added.")
            self.context.log("info", "AE similarity run completed.")
        except Exception as exc:  # noqa: BLE001 — surfaced to the user, not swallowed
            self.set_status(f"AE run failed: {exc}", error=True)
            self.context.log("error", f"AE run failed: {exc}")

    # -- Status / logging -------------------------------------------------

    def set_status(self, message: str, error: bool = False) -> None:
        self.status_bar.showMessage(message)
        if error:
            self.context.log("error", message)

    def _on_activity_logged(self, level: str, message: str) -> None:
        self.activity_log_panel.append(utc_now_iso(), level, message)

    def refresh_activity_log(self) -> None:
        if self.context.conn is None:
            return
        rows = repo.list_activity(self.context.conn, project_key=self.context.project.project_key)
        self.activity_log_panel.load_rows(rows)

    def refresh_attribute_table(self) -> None:
        if self.context.conn is None or self.context.project is None:
            return
        rows = repo.list_samples(self.context.conn, self.context.project.project_key)
        self.attribute_table_panel.load_samples(rows)

    # -- Earth Engine sign-in ---------------------------------------------

    def _refresh_ee_auth_label(self) -> None:
        signed_in = self.context.ee_auth.is_authenticated()
        self.ee_auth_label.setText("EE: signed in" if signed_in else "EE: not signed in")

    def _sign_in_to_earth_engine(self) -> None:
        if self._ee_sign_in_worker is not None and self._ee_sign_in_worker.isRunning():
            self.set_status("Earth Engine sign-in already in progress.")
            return

        self.set_status("Opening browser for Earth Engine sign-in…")
        self._ee_sign_in_worker = EarthEngineSignInWorker(self.context.ee_auth)
        self._ee_sign_in_worker.succeeded.connect(self._on_ee_sign_in_succeeded)
        self._ee_sign_in_worker.failed.connect(self._on_ee_sign_in_failed)
        self._ee_sign_in_worker.start()

    def _on_ee_sign_in_succeeded(self) -> None:
        self._refresh_ee_auth_label()
        self.set_status("Signed in to Earth Engine.")
        self.context.log("info", "Earth Engine sign-in succeeded.")

    def _on_ee_sign_in_failed(self, message: str) -> None:
        self._refresh_ee_auth_label()
        self.set_status(f"Earth Engine sign-in failed: {message}", error=True)

    def _sign_out_of_earth_engine(self) -> None:
        self.context.ee_auth.sign_out()
        self._refresh_ee_auth_label()
        self.set_status("Signed out of Earth Engine.")
        self.context.log("info", "Earth Engine sign-out.")

    def _show_about(self) -> None:
        QMessageBox.about(
            self, "About Scout",
            f"AlphaEarth Scout {SCOUT_VERSION}\n\n"
            "A standalone research workbench for AlphaEarth similarity scouting.",
        )
