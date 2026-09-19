"""Earth Engine compute backend.

Ports sections 2 (DATA HELPERS), 15 (GEOMETRY/EXTENT HELPERS), 17 (AE
SIMILARITY) and 22 (HSV QUALIFIER) of the GEE Code Editor prototype
(v1.4.16-STRESS) to the `earthengine-api` Python client.

The `ee` module is taken as a constructor argument (defaulting to the real
`ee` package) specifically so tests can inject a mock and verify the
composition-graph calls this builds, without network access or Earth
Engine credentials. Note the Python client renames the reserved words
`and`/`or`/`not` to `And`/`Or`/`Not` — this trips people up porting from
the JS client, so it's called out here deliberately.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import ee as _real_ee

BANDS = [f"A{i:02d}" for i in range(64)]
YEARS = ["2017", "2018", "2019", "2020", "2021", "2022", "2023", "2024"]

DW_BANDS = [
    "water", "trees", "grass", "flooded_vegetation", "crops",
    "shrub_and_scrub", "built", "bare", "snow_and_ice",
]

S2_FEATURE_BANDS = [
    "B2", "B3", "B4", "B5", "B6", "B7", "B8", "B8A", "B11", "B12",
    "NDVI", "NDWI", "NDMI", "BSI", "NDRE", "NBR", "NBR2",
]

AE_COLLECTION_ID = "GOOGLE/SATELLITE_EMBEDDING/V1/ANNUAL"
DW_COLLECTION_ID = "GOOGLE/DYNAMICWORLD/V1"
S2_COLLECTION_ID = "COPERNICUS/S2_SR_HARMONIZED"

# Experimental processing windows, not administrative boundaries — ported
# verbatim from the JS SEARCH EXTENTS section.
SEARCH_EXTENT_COORDS: dict[str, list[list[float]]] = {
    "Fylde": [
        [-2.683533991359791, 53.63090325883682],
        [-2.724007157576601, 53.95912832557325],
        [-3.097046586728670, 53.94223694057931],
        [-3.061428577938218, 53.61674742197805],
        [-2.683533991359791, 53.63090325883682],
    ],
    "Rugby": [
        [-1.864795513003882, 52.67253863577725],
        [-1.703312591430576, 52.02726296461070],
        [-0.2485795141283309, 52.14281373870874],
        [-0.3706044494593308, 52.79674378378787],
        [-1.864795513003882, 52.67253863577725],
    ],
    "Oxford / Swindon": [
        [-2.465865799537565, 51.85739735787652],
        [-2.257778772290543, 51.16781087249853],
        [-0.6500001818205003, 51.33028000923049],
        [-0.7475645431488664, 52.01248599261166],
        [-2.465865799537565, 51.85739735787652],
    ],
    "Yorkshire": [
        [0.07611011011868118, 54.33264976045204],
        [-2.118404085207731, 54.15077737224681],
        [-1.850955841609052, 53.11437192622134],
        [0.3089228349426421, 53.29549432188813],
        [0.07611011011868118, 54.33264976045204],
    ],
    "SE England": [
        [-2.536722194836610, 50.44737628223830],
        [0.7865667078880301, 50.72642201689092],
        [0.6165472249835657, 51.55558691786075],
        [-2.720115480035588, 51.27413846344198],
        [-2.536722194836610, 50.44737628223830],
    ],
    "Lancashire": [
        [-3.004490018430338, 53.39615251805643],
        [-1.951132733621426, 53.50031602956092],
        [-2.118248137685995, 54.15018405705395],
        [-3.174173991715066, 54.03786063642587],
        [-3.004490018430338, 53.39615251805643],
    ],
    "Southern Scotland": [
        [-5.129002486891850, 56.41603534947932],
        [-4.813096849662736, 55.41773402332240],
        [-2.122508127076788, 55.67227323652411],
        [-2.426391822472853, 56.69039067500250],
        [-5.129002486891850, 56.41603534947932],
    ],
    "Great Britain": [
        [-5.80, 50.00], [-3.00, 49.75], [1.95, 50.60], [1.85, 52.20],
        [0.70, 53.70], [-1.10, 55.85], [-1.75, 58.75], [-5.10, 58.80],
        [-6.30, 56.20], [-5.65, 54.80], [-4.85, 53.00], [-5.80, 50.00],
    ],
}

# Ireland + NI is a rectangle in the original, kept as bounds rather than a ring.
IRELAND_NI_BOUNDS = (-10.8, 51.2, -5.2, 55.6)  # west, south, east, north

LOCAL_BUFFER_M = 10_000


@dataclass(slots=True)
class SimilarityResult:
    """Everything a UI layer needs to display and later save an AE run."""

    similarity: Any             # ee.Image, unmasked cosine-similarity surface
    raw_vector_list: Any        # ee.List, 64 raw mean band values
    vector_norm: Any            # ee.Number
    reference_geometry: Any
    search_geometry: Any


class EarthEngineBackend:
    def __init__(self, ee_module=None):
        self.ee = ee_module if ee_module is not None else _real_ee

    # -- Data helpers (JS section 2) ----------------------------------

    def load_ae_year(self, year, geometry):
        ee = self.ee
        y = ee.Number.parse(str(year))
        return (
            ee.ImageCollection(AE_COLLECTION_ID)
            .filterDate(ee.Date.fromYMD(y, 1, 1), ee.Date.fromYMD(y.add(1), 1, 1))
            .filterBounds(geometry)
            .mosaic()
            .select(BANDS)
        )

    def load_dw_year(self, year, geometry):
        ee = self.ee
        y = ee.Number.parse(str(year))
        return (
            ee.ImageCollection(DW_COLLECTION_ID)
            .filterDate(ee.Date.fromYMD(y, 1, 1), ee.Date.fromYMD(y.add(1), 1, 1))
            .filterBounds(geometry)
            .select(DW_BANDS)
            .mean()
        )

    def mask_s2(self, image):
        ee = self.ee
        scl = image.select("SCL")
        mask = (
            scl.neq(3).And(scl.neq(8)).And(scl.neq(9)).And(scl.neq(10)).And(scl.neq(11))
        )
        return (
            image.updateMask(mask)
            .divide(10000)
            .copyProperties(image, ["system:time_start", "CLOUDY_PIXEL_PERCENTAGE"])
        )

    def get_s2_collection(self, geometry, start, end):
        ee = self.ee
        return (
            ee.ImageCollection(S2_COLLECTION_ID)
            .filterBounds(geometry)
            .filterDate(start, end)
            .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", 60))
            .map(self.mask_s2)
        )

    def get_s2_composite(self, geometry, start, end):
        return self.get_s2_collection(geometry, start, end).median()

    def get_s2_product(self, composite, product: str) -> dict:
        """Returns {"image": ee.Image, "vis": dict} for the named product,
        matching JS `getS2Product()`. Raises ValueError for an unknown name
        instead of silently returning {} as the JS version effectively did."""
        if product == "RGB":
            return {"image": composite.select(["B4", "B3", "B2"]),
                    "vis": {"min": 0.02, "max": 0.30}}
        if product == "False colour":
            return {"image": composite.select(["B8", "B4", "B3"]),
                    "vis": {"min": 0.02, "max": 0.40}}
        if product == "SWIR":
            return {"image": composite.select(["B12", "B8A", "B4"]),
                    "vis": {"min": 0.02, "max": 0.40}}
        if product == "NDVI":
            return {"image": composite.normalizedDifference(["B8", "B4"]).rename("NDVI"),
                    "vis": {"min": -0.2, "max": 0.8,
                            "palette": ["8c510a", "dfc27d", "f6e8c3", "c7eae5", "5ab4ac", "01665e"]}}
        if product == "NDWI":
            return {"image": composite.normalizedDifference(["B3", "B8"]).rename("NDWI"),
                    "vis": {"min": -0.6, "max": 0.6,
                            "palette": ["8c510a", "f6e8c3", "c7eae5", "2166ac"]}}
        if product == "NDMI":
            return {"image": composite.normalizedDifference(["B8", "B11"]).rename("NDMI"),
                    "vis": {"min": -0.6, "max": 0.6,
                            "palette": ["8c510a", "f6e8c3", "c7eae5", "2166ac"]}}
        if product == "BSI":
            image = composite.expression(
                "((SWIR + RED) - (NIR + BLUE)) / ((SWIR + RED) + (NIR + BLUE))",
                {
                    "SWIR": composite.select("B11"),
                    "RED": composite.select("B4"),
                    "NIR": composite.select("B8"),
                    "BLUE": composite.select("B2"),
                },
            ).rename("BSI")
            return {"image": image, "vis": {"min": -0.5, "max": 0.5, "palette": ["2166ac", "f7f7f7", "b2182b"]}}
        if product == "NDRE":
            return {"image": composite.normalizedDifference(["B8A", "B5"]).rename("NDRE"),
                    "vis": {"min": -0.2, "max": 0.7,
                            "palette": ["8c510a", "f6e8c3", "c7eae5", "01665e"]}}
        if product == "NBR":
            return {"image": composite.normalizedDifference(["B8", "B12"]).rename("NBR"),
                    "vis": {"min": -0.6, "max": 0.8, "palette": ["a50026", "ffffbf", "006837"]}}
        if product == "NBR2":
            return {"image": composite.normalizedDifference(["B11", "B12"]).rename("NBR2"),
                    "vis": {"min": -0.5, "max": 0.5, "palette": ["8c510a", "f7f7f7", "2166ac"]}}
        if product == "B11":
            return {"image": composite.select("B11"), "vis": {"min": 0.02, "max": 0.40}}
        if product == "B12":
            return {"image": composite.select("B12"), "vis": {"min": 0.02, "max": 0.40}}
        raise ValueError(f"Unknown Sentinel-2 product: {product!r}")

    def get_s2_feature_image(self, composite):
        """All bands + all derived indices in one image, matches JS
        `getS2FeatureImage()` — used by probes."""
        selected = composite.select(["B2", "B3", "B4", "B5", "B6", "B7", "B8", "B8A", "B11", "B12"])
        ndvi = composite.normalizedDifference(["B8", "B4"]).rename("NDVI")
        ndwi = composite.normalizedDifference(["B3", "B8"]).rename("NDWI")
        ndmi = composite.normalizedDifference(["B8", "B11"]).rename("NDMI")
        bsi = composite.expression(
            "((SWIR + RED) - (NIR + BLUE)) / ((SWIR + RED) + (NIR + BLUE))",
            {
                "SWIR": composite.select("B11"),
                "RED": composite.select("B4"),
                "NIR": composite.select("B8"),
                "BLUE": composite.select("B2"),
            },
        ).rename("BSI")
        ndre = composite.normalizedDifference(["B8A", "B5"]).rename("NDRE")
        nbr = composite.normalizedDifference(["B8", "B12"]).rename("NBR")
        nbr2 = composite.normalizedDifference(["B11", "B12"]).rename("NBR2")
        return (
            selected.addBands(ndvi).addBands(ndwi).addBands(ndmi)
            .addBands(bsi).addBands(ndre).addBands(nbr).addBands(nbr2)
        )

    def build_hsv_mask(self, composite, h_min, h_max, s_min, s_max, v_min, v_max):
        """Matches JS `buildHSVMask()`. Note the hue wraparound case
        (h_min > h_max, e.g. selecting reds that straddle 0/1) uses Or
        instead of And — this is the one branch worth testing explicitly."""
        ee = self.ee
        rgb = composite.select(["B4", "B3", "B2"]).clamp(0, 1)
        hsv = rgb.rgbToHsv()
        h = hsv.select("hue")
        s = hsv.select("saturation")
        v = hsv.select("value")

        if h_min <= h_max:
            h_mask = h.gte(h_min).And(h.lte(h_max))
        else:
            h_mask = h.gte(h_min).Or(h.lte(h_max))

        return (
            h_mask.And(s.gte(s_min)).And(s.lte(s_max))
            .And(v.gte(v_min)).And(v.lte(v_max))
            .rename("HSV_mask")
        )

    # -- Geometry / extent helpers (JS section 15) --------------------

    def geometry_for_extent(self, name: str):
        ee = self.ee
        if name in SEARCH_EXTENT_COORDS:
            return ee.Geometry.Polygon([SEARCH_EXTENT_COORDS[name]])
        if name == "Ireland + NI":
            return ee.Geometry.Rectangle(list(IRELAND_NI_BOUNDS))
        raise ValueError(f"Unknown search extent: {name!r}")

    def get_search_geometry(self, extent_name: str, reference_geometry):
        if extent_name == "Local":
            return reference_geometry.buffer(LOCAL_BUFFER_M).bounds()
        return self.geometry_for_extent(extent_name)

    # -- AE similarity (JS section 17) --------------------------------

    def build_reference_vector(self, reference_year, reference_geometry, scale=10, max_pixels=1e7):
        """Returns (raw_vector_list, vector_norm, normalized_list) as EE
        objects — matches the reference-vector portion of JS
        `runAESimilarity()`."""
        ee = self.ee
        reference_image = self.load_ae_year(reference_year, reference_geometry)
        mean_dict = reference_image.reduceRegion(
            reducer=ee.Reducer.mean(), geometry=reference_geometry,
            scale=scale, maxPixels=max_pixels,
        )
        raw_vector_list = ee.List([mean_dict.get(b) for b in BANDS])
        raw_vector_array = ee.Array(raw_vector_list)
        vector_norm = raw_vector_array.pow(2).reduce(ee.Reducer.sum(), [0]).sqrt().get([0])
        normalized_list = ee.Array(raw_vector_array.divide(vector_norm)).toList()
        return raw_vector_list, vector_norm, normalized_list

    def run_similarity(
        self, reference_year, target_year, reference_geometry, search_geometry,
        scale=10, max_pixels=1e7,
    ) -> SimilarityResult:
        ee = self.ee
        raw_vector_list, vector_norm, normalized_list = self.build_reference_vector(
            reference_year, reference_geometry, scale, max_pixels
        )
        query_image = ee.Image.constant(normalized_list).rename(BANDS)
        target_image = self.load_ae_year(target_year, search_geometry).clip(search_geometry)
        similarity = (
            target_image.multiply(query_image)
            .reduce(ee.Reducer.sum())
            .rename("similarity")
            .clip(search_geometry)
            .toFloat()
        )
        return SimilarityResult(
            similarity=similarity, raw_vector_list=raw_vector_list, vector_norm=vector_norm,
            reference_geometry=reference_geometry, search_geometry=search_geometry,
        )

    def apply_absolute_threshold(self, similarity_image, threshold: float):
        return similarity_image.updateMask(similarity_image.gte(threshold))

    def resolve_percentile_threshold(self, similarity_image, search_geometry, percentile: float,
                                      scale=250, max_pixels=1e8):
        """percentile is 0-100 (already ×100 from the UI's 0-1 slider),
        matching JS `reduceRegion({reducer: ee.Reducer.percentile([percentile])})`."""
        ee = self.ee
        threshold_dict = similarity_image.reduceRegion(
            reducer=ee.Reducer.percentile([percentile]), geometry=search_geometry,
            scale=scale, maxPixels=max_pixels, bestEffort=False,
        )
        return ee.Number(threshold_dict.values().get(0))

    def apply_percentile_threshold(self, similarity_image, threshold_value):
        return similarity_image.updateMask(similarity_image.gte(threshold_value))

    # -- Point sampling (probes) --------------------------------------

    def sample_dynamic_world(self, year, region, scale=10, max_pixels=1e7):
        """Mean Dynamic World class probabilities over a small region —
        used for probe pins, matching the JS multi-dataset probe's DW
        sampling. Returns an ee.Dictionary; call .getInfo() to
        materialize, same convention as build_reference_vector()."""
        ee = self.ee
        dw_image = self.load_dw_year(year, region)
        return dw_image.reduceRegion(
            reducer=ee.Reducer.mean(), geometry=region, scale=scale, maxPixels=max_pixels,
        )
