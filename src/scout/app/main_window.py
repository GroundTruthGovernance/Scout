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
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QDockWidget,
    QFileDialog,
    QInputDialog,
    QLabel,
    QMainWindow,
    QMenu,
    QMessageBox,
    QStatusBar,
    QToolBar,
)

from scout.core import repository as repo
from scout.core.models import Figure, LatentSignature, Pin
from scout.core.power import perform_power_action
from scout.core.report_composer import compose_session_report
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
from scout.app.dialogs.new_project_dialog import NewProjectDialog
from scout.app.dialogs.figure_capture_dialog import FigureCaptureDialog


class MainWindow(QMainWindow):
    def __init__(self, context: ProjectContext | None = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Scout {SCOUT_VERSION}")
        self.resize(1400, 900)

        self.context = context or ProjectContext()
        self._current_response_layer_id: str | None = None
        self._ee_sign_in_worker: EarthEngineSignInWorker | None = None
        self._last_similarity_result = None
        self._last_reference_geometry_geojson: str | None = None
        self._armed_pin_mode: str = "observation"   # "observation" | "probe"

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
        self.action_add_probe = QAction("Add Pro&be", self, checkable=True)
        self.action_clear_geometry = QAction("&Clear Drawn Geometry", self)
        self.action_new_pin_group = QAction("&New Pin Group…", self)

        # Run
        self.action_run_ae = QAction("&Run AE Similarity", self)
        self.action_run_ae.setEnabled(False)  # enabled once a polygon exists
        self.action_save_latent_signature = QAction("Save Run as &Latent Signature…", self)
        self.action_save_latent_signature.setEnabled(False)  # enabled once a run has produced a vector

        # Batch
        self.action_add_to_queue = QAction("&Add Current Run to Queue", self)

        # Tools
        self.action_sign_in_ee = QAction("&Sign in to Earth Engine…", self)
        self.action_sign_out_ee = QAction("Sign &out of Earth Engine", self)
        self.action_capture_figure = QAction("Capture &Figure…", self)
        self.action_compose_report = QAction("&Compose Session Report…", self)

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
        sample_menu.addAction(self.action_add_probe)
        sample_menu.addAction(self.action_clear_geometry)
        sample_menu.addSeparator()
        sample_menu.addAction(self.action_new_pin_group)

        run_menu = menu_bar.addMenu("&Run")
        run_menu.addAction(self.action_run_ae)
        run_menu.addAction(self.action_save_latent_signature)

        batch_menu = menu_bar.addMenu("&Batch")
        batch_menu.addAction(self.action_add_to_queue)

        tools_menu = menu_bar.addMenu("&Tools")
        tools_menu.addAction(self.python_console_dock.toggleViewAction())
        tools_menu.addAction(self.action_capture_figure)
        tools_menu.addAction(self.action_compose_report)
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
        self.main_toolbar.addAction(self.action_add_probe)
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
        self.action_add_probe.toggled.connect(self._on_add_probe_toggled)
        self.action_clear_geometry.triggered.connect(self._on_clear_geometry)
        self.action_run_ae.triggered.connect(self.run_ae_similarity)
        self.action_clean_map.toggled.connect(self._on_clean_map_toggled)
        self.action_about.triggered.connect(self._show_about)
        self.action_sign_in_ee.triggered.connect(self._sign_in_to_earth_engine)
        self.action_sign_out_ee.triggered.connect(self._sign_out_of_earth_engine)
        self.action_add_to_queue.triggered.connect(self._add_current_run_to_queue)
        self.batch_queue_panel.run_queue_requested.connect(self.run_batch_queue)
        self.action_save_latent_signature.triggered.connect(self._save_as_latent_signature)
        self.action_capture_figure.triggered.connect(self._capture_figure)
        self.action_compose_report.triggered.connect(self._compose_session_report)

        self.map_panel.bridge.polygon_drawn.connect(self._on_polygon_drawn)
        self.map_panel.bridge.point_clicked.connect(self._on_point_clicked)
        self.map_panel.bridge.map_clicked.connect(self._on_map_clicked)

        self.context.activity_logged.connect(self._on_activity_logged)
        self.layers_panel.layer_visibility_changed.connect(self._on_layer_visibility_changed)
        self.layers_panel.pin_context_menu_requested.connect(self._on_pin_context_menu)
        self.action_new_pin_group.triggered.connect(self._prompt_new_pin_group)

    # -- File menu handlers -------------------------------------------------

    def _prompt_new_project(self) -> None:
        dialog = NewProjectDialog(self)
        if dialog.exec() != NewProjectDialog.Accepted:
            return
        values = dialog.values()
        if values is None:
            return

        path, _ = QFileDialog.getSaveFileName(self, "New Scout Project", "", "Scout project (*.scout.db)")
        if not path:
            return

        try:
            project = self.context.new_project(
                path, values["project_code"], values["location_code"],
                values["sublocation_code"], project_name=values["project_name"],
            )
            self.set_status(f"Project {project.project_key} created.")
            self.refresh_activity_log()
            self.refresh_attribute_table()
            self.refresh_batch_queue()
            self.refresh_pins()
        except ValueError as exc:
            QMessageBox.critical(self, "New Project", str(exc))

    def _prompt_open_project(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Open Scout Project", "", "Scout project (*.scout.db)")
        if not path:
            return
        try:
            project = self.context.open_project(path)
            self.set_status(f"Opened {project.project_key}.")
            self.refresh_activity_log()
            self.refresh_attribute_table()
            self.refresh_batch_queue()
            self.refresh_pins()
        except ValueError as exc:
            QMessageBox.critical(self, "Open Project", str(exc))

    # -- Drawing / map interaction -------------------------------------

    def _on_draw_polygon_toggled(self, checked: bool) -> None:
        if checked:
            self.action_add_pin.setChecked(False)
            self.action_add_probe.setChecked(False)
            self.map_panel.enable_draw_polygon()
        else:
            self.map_panel.disable_drawing()

    def _on_add_pin_toggled(self, checked: bool) -> None:
        if checked and self.context.project is None:
            self.set_status("Open or create a project before dropping a pin.", error=True)
            self.action_add_pin.setChecked(False)
            return
        if checked:
            self._armed_pin_mode = "observation"
            self.action_draw_polygon.setChecked(False)
            self.action_add_probe.setChecked(False)
            self.map_panel.enable_pin_drop()
        else:
            self.map_panel.disable_drawing()

    def _on_add_probe_toggled(self, checked: bool) -> None:
        if checked and self.context.project is None:
            self.set_status("Open or create a project before dropping a probe.", error=True)
            self.action_add_probe.setChecked(False)
            return
        if checked and not self.context.ee_auth.is_authenticated():
            self.set_status("Sign in to Earth Engine first (Tools > Sign in to Earth Engine…).", error=True)
            self.action_add_probe.setChecked(False)
            return
        if checked:
            self._armed_pin_mode = "probe"
            self.action_draw_polygon.setChecked(False)
            self.action_add_pin.setChecked(False)
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
        # Dropping a pin *is* the save action for a pin (unlike a drawn
        # polygon, which stays exploratory until a sample/response is
        # explicitly saved) — see docs/ARCHITECTURE.md, "Guiding
        # philosophy". The toggled handlers already refused to arm
        # whichever tool is active without an open project (and, for a
        # probe, without EE sign-in), so self.context.project is set here.
        if self._armed_pin_mode == "probe":
            self.action_add_probe.setChecked(False)
            self._save_probe_pin(lon, lat)
        else:
            self.action_add_pin.setChecked(False)
            self._save_observation_pin(lon, lat)

    def _save_observation_pin(self, lon: float, lat: float) -> None:
        project_key = self.context.project.project_key
        next_number = repo.count_all_pins(self.context.conn, project_key, "observation") + 1
        pin = Pin(
            pin_id=f"{project_key}-OBS-{next_number:03d}",
            pin_type="observation", project_key=project_key, lon=lon, lat=lat,
            created_utc=utc_now_iso(), modified_utc=utc_now_iso(),
        )
        repo.insert_pin(self.context.conn, pin)
        self.map_panel.add_marker(pin.pin_id, lon, lat, popup_text=pin.pin_id)
        self.layers_panel.add_pin_marker(pin.pin_id, pin.pin_id)
        self.context.log("info", f"{pin.pin_id} added.", related_object_id=pin.pin_id)

    def _save_probe_pin(self, lon: float, lat: float) -> None:
        """Samples AE64+norm, Dynamic World, and (best-effort) Sentinel-2
        features/indices in a small buffer around the click, matching the
        GEE prototype's multi-dataset probe. Fixed at a 5 m buffer / mean
        reducer / the current reference year for now — the original UI's
        radius/reducer/year selectors are a reasonable follow-up, not
        built tonight."""
        project_key = self.context.project.project_key
        year = self.context.exploration.reference_year
        ee = self.context.ee.ee

        try:
            self.set_status(f"Sampling AE/S2/DW at {lon:.5f}, {lat:.5f}…")
            region = ee.Geometry.Point([lon, lat]).buffer(5)

            raw_vector_list, vector_norm, _ = self.context.ee.build_reference_vector(year, region)
            ae_vector = raw_vector_list.getInfo()
            ae_norm = vector_norm.getInfo()

            dw_values = self.context.ee.sample_dynamic_world(year, region).getInfo()

            start, end = f"{year}-06-01", f"{year}-09-01"
            s2_collection = self.context.ee.get_s2_collection(region, start, end)
            scene_count = s2_collection.size().getInfo()
            s2_values = None
            if scene_count:
                s2_image = self.context.ee.get_s2_feature_image(s2_collection.median())
                s2_values = s2_image.reduceRegion(
                    reducer=ee.Reducer.mean(), geometry=region, scale=10, maxPixels=1e7
                ).getInfo()

            next_number = repo.count_all_pins(self.context.conn, project_key, "probe") + 1
            pin = Pin(
                pin_id=f"{project_key}-PRB-{next_number:03d}",
                pin_type="probe", project_key=project_key, lon=lon, lat=lat,
                probe_year=int(year), probe_radius_m=5.0, probe_neighbourhood="Pixel",
                probe_reducer="mean", ae_vector=ae_vector, ae_vector_norm=ae_norm,
                dw_values=dw_values, s2_values=s2_values, s2_scene_count=scene_count,
                created_utc=utc_now_iso(), modified_utc=utc_now_iso(),
            )
            repo.insert_pin(self.context.conn, pin)
            self.map_panel.add_marker(pin.pin_id, lon, lat, color="#FF00FF", popup_text=pin.pin_id)
            self.layers_panel.add_pin_marker(pin.pin_id, pin.pin_id)
            self.set_status(f"{pin.pin_id} probe saved.")
            self.context.log("info", f"{pin.pin_id} probe saved.", related_object_id=pin.pin_id)
        except Exception as exc:  # noqa: BLE001 — surfaced to the user, not swallowed
            self.set_status(f"Probe sampling failed: {exc}", error=True)
            self.context.log("error", f"Probe sampling failed: {exc}")

    def _on_map_clicked(self, lon: float, lat: float) -> None:
        self.coordinate_label.setText(f"Lon {lon:.6f}  Lat {lat:.6f}")

    # -- Pin groups + tags -------------------------------------------------

    def _prompt_new_pin_group(self) -> None:
        if self.context.project is None:
            self.set_status("Open or create a project before adding a pin group.", error=True)
            return
        name, ok = QInputDialog.getText(self, "New Pin Group", "Group name:")
        if not ok or not name.strip():
            return
        repo.create_pin_group(self.context.conn, self.context.project.project_key, name.strip())
        self.layers_panel.ensure_pin_group(name.strip())
        self.set_status(f"Pin group '{name.strip()}' created.")

    def _on_pin_context_menu(self, pin_id: str, global_pos) -> None:
        menu = QMenu(self)
        move_action = menu.addAction("Move to group…")
        tags_action = menu.addAction("Edit tags…")
        chosen = self._exec_menu(menu, global_pos)
        if chosen is move_action:
            self._prompt_move_pin_to_group(pin_id)
        elif chosen is tags_action:
            self._prompt_edit_pin_tags(pin_id)

    def _exec_menu(self, menu: QMenu, global_pos):
        """A thin, overridable wrapper around QMenu.exec() — PySide6's
        bound C++ method can't be monkeypatched directly at the class
        level the way a plain Python method can, so tests patch this
        instead of QMenu.exec itself."""
        return menu.exec(global_pos)

    def _prompt_move_pin_to_group(self, pin_id: str) -> None:
        groups = repo.list_pin_groups(self.context.conn, self.context.project.project_key)
        no_group_label = "(no group)"
        options = [no_group_label] + [g["name"] for g in groups]
        choice, ok = QInputDialog.getItem(self, "Move to Group", "Group:", options, editable=False)
        if not ok:
            return
        if choice == no_group_label:
            repo.set_pin_group(self.context.conn, pin_id, None)
            self.layers_panel.move_pin_to_group(pin_id, None)
        else:
            group_row = next(g for g in groups if g["name"] == choice)
            repo.set_pin_group(self.context.conn, pin_id, group_row["group_id"])
            self.layers_panel.move_pin_to_group(pin_id, choice)
        self.set_status(f"{pin_id} moved to {choice}.")

    def _prompt_edit_pin_tags(self, pin_id: str) -> None:
        current = ", ".join(repo.get_pin_tags(self.context.conn, pin_id))
        text, ok = QInputDialog.getText(self, "Edit Tags", "Comma-separated tags:", text=current)
        if not ok:
            return
        tags = [t.strip() for t in text.split(",")]
        repo.set_pin_tags(self.context.conn, pin_id, tags)
        self.set_status(f"{pin_id} tags updated.")

    def refresh_pins(self) -> None:
        """Reloads every saved pin (and the groups they belong to) into
        the Layers panel and the map — the real gap this closes: opening
        a project previously left its saved pins invisible until the next
        one was dropped."""
        if self.context.conn is None or self.context.project is None:
            return
        project_key = self.context.project.project_key
        self.layers_panel.clear_pins()
        self.map_panel.clear_markers()

        groups_by_id = {g["group_id"]: g["name"] for g in repo.list_pin_groups(self.context.conn, project_key)}
        for pin in repo.list_pins(self.context.conn, project_key):
            group_name = groups_by_id.get(pin["group_id"])
            self.layers_panel.add_pin_marker(pin["pin_id"], pin["pin_id"], group_name=group_name)
            self.map_panel.add_marker(pin["pin_id"], pin["lon"], pin["lat"], popup_text=pin["pin_id"])

    def _on_layer_visibility_changed(self, layer_id: str, visible: bool, kind: str) -> None:
        if kind == "marker":
            self.map_panel.set_marker_visible(layer_id, visible)
        else:
            self.map_panel.set_layer_visible(layer_id, visible)

    def _on_clean_map_toggled(self, checked: bool) -> None:
        for dock in self.findChildren(QDockWidget):
            dock.setVisible(not checked)
        for toolbar in self.findChildren(QToolBar):
            toolbar.setVisible(not checked and toolbar is self.main_toolbar)
        self.status_bar.setVisible(not checked)

    # -- Run AE (the golden path) ---------------------------------------

    def _exploration_recipe(self) -> dict:
        exploration = self.context.exploration
        return {
            "reference_year": exploration.reference_year,
            "target_year": exploration.target_year,
            "search_extent": exploration.search_extent,
            "threshold_mode": exploration.threshold_mode,
            "threshold": exploration.threshold,
            "mask_display_style": exploration.mask_display_style,
            "mask_color": exploration.mask_color,
            "mask_opacity": exploration.mask_opacity,
        }

    def _compute_similarity_tile_url(self, geojson_text: str, recipe: dict) -> tuple[str, object]:
        """Shared by the interactive Run AE button and the batch queue —
        everything from "reference geometry" to "a tile URL ready to add
        to the map" lives here exactly once. Also returns the raw
        SimilarityResult (reference vector + norm) so a caller can save it
        as a Latent Signature without a second EE round trip."""
        ee = self.context.ee.ee
        reference_geometry = ee.Geometry(json.loads(geojson_text))
        search_geometry = self.context.ee.get_search_geometry(
            recipe["search_extent"], reference_geometry
        )
        result = self.context.ee.run_similarity(
            recipe["reference_year"], recipe["target_year"], reference_geometry, search_geometry,
        )

        if recipe["threshold_mode"] == "percentile":
            threshold_value = self.context.ee.resolve_percentile_threshold(
                result.similarity, search_geometry, recipe["threshold"] * 100
            )
            masked = self.context.ee.apply_percentile_threshold(result.similarity, threshold_value)
            cutoff_for_vis = threshold_value.getInfo()
        else:
            masked = self.context.ee.apply_absolute_threshold(result.similarity, recipe["threshold"])
            cutoff_for_vis = recipe["threshold"]

        vis_params = get_ae_vis(cutoff_for_vis, recipe["mask_display_style"], recipe["mask_color"])
        map_id = ee.Image(masked).getMapId(vis_params)
        return map_id["tile_fetcher"].url_format, result

    def run_ae_similarity(self) -> None:
        geojson_text = self.context.exploration.reference_geometry_geojson
        if not geojson_text:
            self.set_status("Draw a reference polygon first.", error=True)
            return
        if not self.context.ee_auth.is_authenticated():
            self.set_status("Sign in to Earth Engine first (Tools > Sign in to Earth Engine…).", error=True)
            return

        try:
            self.set_status("Calculating AE similarity…")
            recipe = self._exploration_recipe()
            tile_url_template, similarity_result = self._compute_similarity_tile_url(geojson_text, recipe)

            layer_id = f"response-preview-{uuid.uuid4().hex[:8]}"
            if self._current_response_layer_id:
                self.map_panel.remove_layer(self._current_response_layer_id)
                self.layers_panel.remove_layer(self._current_response_layer_id)
            self.map_panel.add_raster_layer(layer_id, tile_url_template, recipe["mask_opacity"])
            self.layers_panel.add_layer("Responses", layer_id, "Current AE response (unsaved)")
            self._current_response_layer_id = layer_id
            self._last_similarity_result = similarity_result
            self._last_reference_geometry_geojson = geojson_text
            self.action_save_latent_signature.setEnabled(True)

            self.set_status("AE response added.")
            self.context.log("info", "AE similarity run completed.")
        except Exception as exc:  # noqa: BLE001 — surfaced to the user, not swallowed
            self.set_status(f"AE run failed: {exc}", error=True)
            self.context.log("error", f"AE run failed: {exc}")

    def _save_as_latent_signature(self) -> None:
        if self._last_similarity_result is None:
            self.set_status("Run AE similarity first.", error=True)
            return
        if self.context.project is None:
            self.set_status("Open or create a project before saving a signature.", error=True)
            return

        label, ok = QInputDialog.getText(self, "Save Latent Signature", "Label:")
        if not ok or not label.strip():
            return

        try:
            # Same "materialize the vector with one EE round trip" pattern
            # as commit_current_sample() in the GEE prototype — the AE
            # vector only exists as an EE computation graph node until
            # something actually calls getInfo() on it.
            raw_vector = self._last_similarity_result.raw_vector_list.getInfo()
            vector_norm = self._last_similarity_result.vector_norm.getInfo()

            project_key = self.context.project.project_key
            next_number = repo.count_all_latent_signatures(self.context.conn, project_key) + 1
            signature = LatentSignature(
                signature_id=f"{project_key}-SIG-{next_number:03d}",
                project_key=project_key, label=label.strip(), source_type="drawn",
                vector=raw_vector, vector_norm=vector_norm,
                origin_geometry_geojson=self._last_reference_geometry_geojson,
                created_utc=utc_now_iso(),
            )
            repo.insert_latent_signature(self.context.conn, signature)
            self.set_status(f"{signature.signature_id} saved.")
            self.context.log("info", f"{signature.signature_id} saved.", related_object_id=signature.signature_id)
        except Exception as exc:  # noqa: BLE001 — surfaced to the user, not swallowed
            self.set_status(f"Saving latent signature failed: {exc}", error=True)
            self.context.log("error", f"Saving latent signature failed: {exc}")

    # -- Batch queue -------------------------------------------------------

    def _add_current_run_to_queue(self) -> None:
        geojson_text = self.context.exploration.reference_geometry_geojson
        if not geojson_text:
            self.set_status("Draw a reference polygon first.", error=True)
            return
        if self.context.project is None:
            self.set_status("Open or create a project before queuing a run.", error=True)
            return

        job_id = f"JOB-{uuid.uuid4().hex[:8]}"
        repo.insert_batch_job(
            self.context.conn, job_id, self.context.project.project_key,
            "ae_response", geojson_text, self._exploration_recipe(),
        )
        self.refresh_batch_queue()
        self.set_status(f"{job_id} added to the batch queue.")
        self.context.log("info", f"{job_id} queued.", related_object_id=job_id)

    def refresh_batch_queue(self) -> None:
        if self.context.conn is None or self.context.project is None:
            return
        rows = repo.list_batch_jobs(self.context.conn, self.context.project.project_key)
        self.batch_queue_panel.load_jobs(rows)

    def run_batch_queue(self, post_action: str) -> None:
        if self.context.project is None:
            self.set_status("No project open — nothing to run.", error=True)
            return
        if not self.context.ee_auth.is_authenticated():
            self.set_status("Sign in to Earth Engine before running the batch queue.", error=True)
            return

        jobs = repo.list_queued_batch_jobs(self.context.conn, self.context.project.project_key)
        if not jobs:
            self.set_status("Batch queue is empty.")
            return

        succeeded, failed = 0, 0
        for job in jobs:
            repo.update_batch_job_status(self.context.conn, job["job_id"], "running")
            self.refresh_batch_queue()
            try:
                recipe = json.loads(job["recipe_json"])
                self._compute_similarity_tile_url(job["geometry_geojson"], recipe)
                repo.update_batch_job_status(self.context.conn, job["job_id"], "done")
                succeeded += 1
            except Exception as exc:  # noqa: BLE001 — recorded per-job, queue continues
                repo.update_batch_job_status(self.context.conn, job["job_id"], "failed", error_message=str(exc))
                failed += 1
            self.refresh_batch_queue()

        self.context.log("info", f"Batch queue finished: {succeeded} succeeded, {failed} failed.")
        self.set_status(f"Batch queue finished: {succeeded} succeeded, {failed} failed.")

        if post_action != "None":
            self._confirm_and_run_power_action(post_action)

    def _confirm_and_run_power_action(self, action: str) -> None:
        reply = QMessageBox.question(
            self, f"{action} after batch",
            f"The batch queue has finished. {action} this PC now?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            self.context.log("info", f"Post-batch power action: {action}.")
            perform_power_action(action)

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

    def _capture_figure(self) -> None:
        """Screenshots the map widget itself — real basemap tiles plus
        whatever overlays are currently shown — rather than rendering an
        EE thumbnail via getThumbURL(), which is exactly the GEE
        prototype's known limitation this sidesteps: getThumbURL() only
        ever rendered EE imagery, never the basemap underneath it."""
        if self.context.project is None:
            self.set_status("Open or create a project before capturing a figure.", error=True)
            return

        dialog = FigureCaptureDialog(self)
        if dialog.exec() != FigureCaptureDialog.Accepted:
            return
        values = dialog.values()
        if values is None:
            return

        try:
            project_key = self.context.project.project_key
            figure_id = f"{project_key}-FIG-{uuid.uuid4().hex[:8]}"
            figures_dir = Path(self.context.db_path).parent / "figures"
            figures_dir.mkdir(parents=True, exist_ok=True)
            image_path = figures_dir / f"{figure_id}.png"

            pixmap = self.map_panel.grab()
            if not pixmap.save(str(image_path), "PNG"):
                raise OSError(f"Qt could not write {image_path}")

            figure = Figure(
                figure_id=figure_id, project_key=project_key, figure_title=values["title"],
                caption=values["caption"], image_path=f"figures/{image_path.name}",
                created_utc=utc_now_iso(),
            )
            repo.insert_figure(self.context.conn, figure)
            self.set_status(f"{figure_id} captured.")
            self.context.log("info", f"{figure_id} captured.", related_object_id=figure_id)
        except Exception as exc:  # noqa: BLE001 — surfaced to the user, not swallowed
            self.set_status(f"Capturing figure failed: {exc}", error=True)
            self.context.log("error", f"Capturing figure failed: {exc}")

    def _compose_session_report(self) -> None:
        if self.context.project is None:
            self.set_status("Open or create a project before composing a report.", error=True)
            return

        path, _ = QFileDialog.getSaveFileName(
            self, "Compose Session Report", f"{self.context.project.project_key}_report.md",
            "Markdown (*.md)",
        )
        if not path:
            return

        try:
            compose_session_report(self.context.conn, self.context.project.project_key, path)
            self.set_status(f"Session report written to {path}.")
            self.context.log("info", f"Session report composed: {path}")
        except Exception as exc:  # noqa: BLE001 — surfaced to the user, not swallowed
            self.set_status(f"Composing session report failed: {exc}", error=True)
            self.context.log("error", f"Composing session report failed: {exc}")

    def _show_about(self) -> None:
        QMessageBox.about(
            self, "About Scout",
            f"AlphaEarth Scout {SCOUT_VERSION}\n\n"
            "A standalone research workbench for AlphaEarth similarity scouting.",
        )
