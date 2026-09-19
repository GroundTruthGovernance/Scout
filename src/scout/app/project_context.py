"""Holds everything specific to the currently open Scout project: the
database connection, the Earth Engine backend, and the in-memory
exploration state (current drawn geometry, current run parameters) that
deliberately never touches the database until something is explicitly
saved — see docs/ARCHITECTURE.md, "Guiding philosophy".
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

from PySide6.QtCore import QObject, Signal

from scout.core import db, repository as repo
from scout.core.ee_auth import EarthEngineAuth
from scout.core.ee_backend import EarthEngineBackend
from scout.core.models import Project, project_key as make_project_key
from scout.core.util import utc_now_iso


@dataclass(slots=True)
class ExplorationState:
    """Transient state for the current draw/run — never persisted unless
    the user explicitly saves a sample, response, or pin from it."""

    reference_geometry_geojson: str | None = None
    reference_year: str = "2023"
    target_year: str = "2023"
    search_extent: str = "Fylde"
    threshold_mode: str = "absolute"       # 'absolute' | 'percentile'
    threshold: float = 0.90
    mask_display_style: str = "Similarity ramp"
    mask_color: str = "FF7F00"
    mask_opacity: float = 0.75


class ProjectContext(QObject):
    """One instance lives for the lifetime of an open project. Qt signals
    let dock panels (Activity Log, Layers, Attribute Table) react to
    changes without polling."""

    project_opened = Signal(str)     # project_key
    project_closed = Signal()
    activity_logged = Signal(str, str)   # level, message

    def __init__(
        self, ee_backend: EarthEngineBackend | None = None,
        ee_auth: EarthEngineAuth | None = None, parent=None,
    ):
        super().__init__(parent)
        self.conn: sqlite3.Connection | None = None
        self.db_path: Path | None = None
        self.project: Project | None = None
        self.ee = ee_backend or EarthEngineBackend()
        self.ee_auth = ee_auth or EarthEngineAuth()
        self.exploration = ExplorationState()

    # -- Lifecycle ------------------------------------------------------

    @property
    def is_open(self) -> bool:
        return self.conn is not None and self.project is not None

    def new_project(
        self, db_path: str | Path, project_code: str, location_code: str,
        sublocation_code: str, project_name: str = "",
    ) -> Project:
        proj_key = make_project_key(project_code, location_code, sublocation_code)
        if proj_key is None:
            raise ValueError("Project code, location code and sub-location code are all required.")

        self.close()
        self.conn = db.connect(db_path)
        self.db_path = Path(db_path)

        project = Project(
            project_key=proj_key, project_code=project_code, location_code=location_code,
            sublocation_code=sublocation_code, project_name=project_name,
            created_utc=utc_now_iso(), modified_utc=utc_now_iso(),
        )
        repo.upsert_project(self.conn, project)
        self.project = project
        self.log("info", f"Project {proj_key} created.")
        self.project_opened.emit(proj_key)
        return project

    def open_project(self, db_path: str | Path) -> Project:
        self.close()
        self.conn = db.connect(db_path)
        self.db_path = Path(db_path)

        rows = self.conn.execute("SELECT * FROM projects ORDER BY modified_utc DESC LIMIT 1").fetchall()
        if not rows:
            self.conn.close()
            self.conn = None
            raise ValueError(f"{db_path} has no project record — is this a Scout project file?")

        row = rows[0]
        self.project = Project(
            project_key=row["project_key"], project_code=row["project_code"],
            location_code=row["location_code"], sublocation_code=row["sublocation_code"],
            project_name=row["project_name"] or "", created_utc=row["created_utc"],
            modified_utc=row["modified_utc"],
        )
        self.log("info", f"Project {self.project.project_key} opened.")
        self.project_opened.emit(self.project.project_key)
        return self.project

    def close(self) -> None:
        if self.conn is not None:
            self.conn.close()
        self.conn = None
        self.db_path = None
        self.project = None
        self.exploration = ExplorationState()
        self.project_closed.emit()

    # -- Activity log -----------------------------------------------------

    def log(self, level: str, message: str, related_object_id: str | None = None) -> None:
        if self.conn is not None:
            repo.log_activity(
                self.conn, message, level=level, related_object_id=related_object_id,
                project_key=self.project.project_key if self.project else None,
            )
        self.activity_logged.emit(level, message)
