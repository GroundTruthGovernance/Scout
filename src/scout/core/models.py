"""Typed dataclasses for the core Scout entities.

These are plain data containers used by scout.core.repository; they are
not an ORM layer (see docs/ARCHITECTURE.md for why plain sqlite3 was
chosen over one).
"""

from __future__ import annotations

from dataclasses import dataclass, field


def project_key(project_code: str, location_code: str, sublocation_code: str) -> str | None:
    """Matches JS `getProjectKey()`: all three parts required, else None."""
    if not (project_code and location_code and sublocation_code):
        return None
    return f"{project_code}-{location_code}-{sublocation_code}"


def sample_id(proj_key: str, field_code: str, sample_code: str) -> str | None:
    """Matches JS `getSampleId()`."""
    if not (proj_key and field_code and sample_code):
        return None
    return f"{proj_key}-{field_code}-{sample_code}"


@dataclass(slots=True)
class Project:
    project_key: str
    project_code: str
    location_code: str
    sublocation_code: str
    project_name: str = ""
    created_utc: str = ""
    modified_utc: str = ""


@dataclass(slots=True)
class Sample:
    sample_id: str
    sample_uid: str
    project_key: str
    field_code: str
    sample_code: str
    geometry_geojson: str
    sample_name: str = ""
    experiment_id: str = ""
    session_id: str = ""
    centroid_lon: float | None = None
    centroid_lat: float | None = None
    area_m2: float | None = None
    perimeter_m: float | None = None
    sample_role: str = "TARGET"
    sample_type: str = "UNKNOWN"
    selection_origin: str = "HUMAN"
    reason: str = "EXPLORATORY"
    classification_confidence: str = "NOT_SET"
    tags: str = ""
    qa_note: str = ""
    record_status: str = "active"
    created_utc: str = ""
    modified_utc: str = ""


@dataclass(slots=True)
class AEVector:
    sample_id: str
    year: int
    vector: list[float]   # 64 floats, A00..A63
    vector_norm: float
    created_utc: str = ""


@dataclass(slots=True)
class DynamicWorldRecord:
    sample_id: str
    year: int
    water: float = 0.0
    trees: float = 0.0
    grass: float = 0.0
    flooded_vegetation: float = 0.0
    crops: float = 0.0
    shrub_and_scrub: float = 0.0
    built: float = 0.0
    bare: float = 0.0
    snow_and_ice: float = 0.0
    created_utc: str = ""


DW_FIELDS = (
    "water", "trees", "grass", "flooded_vegetation", "crops",
    "shrub_and_scrub", "built", "bare", "snow_and_ice",
)


@dataclass(slots=True)
class Response:
    response_id: str
    project_key: str
    reference_year: int
    target_year: int
    threshold_mode: str          # 'absolute' | 'percentile'
    threshold: float
    sample_id: str | None = None
    sample_uid: str | None = None
    experiment_id: str = ""
    requested_percentile: float | None = None
    resolved_similarity_cutoff: float | None = None
    search_extent: str = ""
    search_extent_geojson: str = ""
    reference_geometry_geojson: str = ""
    reference_mean_vector_norm: float | None = None
    prediction: str = ""
    result_class: str = "NOT_SET"
    result_confidence: str = "NOT_SET"
    recipe_fingerprint: str = ""
    duplicate_of: str = ""
    mask_display_style: str = "Similarity ramp"
    mask_color: str = "FF7F00"
    mask_opacity: float = 0.75
    cached_raster_path: str | None = None
    tags: str = ""
    qa_note: str = ""
    record_status: str = "active"
    created_utc: str = ""
    modified_utc: str = ""


@dataclass(slots=True)
class Pin:
    pin_id: str
    pin_type: str   # 'observation' | 'probe'
    project_key: str
    lon: float
    lat: float
    note: str = ""
    sample_id: str | None = None
    response_id: str | None = None
    group_id: int | None = None
    tags: list[str] = field(default_factory=list)
    probe_year: int | None = None
    probe_radius_m: float | None = None
    probe_neighbourhood: str | None = None
    probe_reducer: str | None = None
    ae_vector: list[float] | None = None
    ae_vector_norm: float | None = None
    dw_values: dict | None = None
    s2_values: dict | None = None
    s2_scene_count: int | None = None
    record_status: str = "active"
    created_utc: str = ""
    modified_utc: str = ""


@dataclass(slots=True)
class LatentSignature:
    signature_id: str
    project_key: str
    label: str
    source_type: str   # 'drawn' | 'imported' | 'derived'
    vector: list[float]
    vector_norm: float | None = None
    origin_sample_id: str | None = None
    origin_geometry_geojson: str | None = None
    caption: str = ""
    tags: str = ""
    derivation_note: str = ""
    record_status: str = "active"
    created_utc: str = ""
