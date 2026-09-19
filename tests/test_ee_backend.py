"""Tests for the EE compute backend using a mocked `ee` module.

These verify the *shape* of the computation graph Scout builds (which
collections/reducers/bands are used, and — for the HSV hue wraparound —
which boolean branch is composed) without any network access or Earth
Engine credentials. Live verification against real AlphaEarth/Sentinel-2
data has to happen on a machine with EE auth, which this sandbox has not
had at any point in this build.
"""

from unittest.mock import MagicMock

import pytest

from scout.core.ee_backend import (
    AE_COLLECTION_ID,
    BANDS,
    DW_BANDS,
    DW_COLLECTION_ID,
    EarthEngineBackend,
    S2_COLLECTION_ID,
    SEARCH_EXTENT_COORDS,
)


@pytest.fixture
def mock_ee():
    return MagicMock(name="ee")


@pytest.fixture
def backend(mock_ee):
    return EarthEngineBackend(ee_module=mock_ee)


def test_load_ae_year_uses_correct_collection_and_bands(backend, mock_ee):
    geometry = MagicMock(name="geometry")
    backend.load_ae_year("2023", geometry)

    mock_ee.ImageCollection.assert_called_once_with(AE_COLLECTION_ID)
    # .filterDate(...).filterBounds(geometry).mosaic().select(BANDS)
    filter_date_chain = mock_ee.ImageCollection.return_value.filterDate.return_value
    filter_date_chain.filterBounds.assert_called_once_with(geometry)
    filter_date_chain.filterBounds.return_value.mosaic.assert_called_once_with()
    filter_date_chain.filterBounds.return_value.mosaic.return_value.select.assert_called_once_with(BANDS)


def test_load_dw_year_uses_correct_collection_and_bands(backend, mock_ee):
    geometry = MagicMock(name="geometry")
    backend.load_dw_year("2023", geometry)

    mock_ee.ImageCollection.assert_called_once_with(DW_COLLECTION_ID)
    filter_date_chain = mock_ee.ImageCollection.return_value.filterDate.return_value
    filter_date_chain.filterBounds.return_value.select.assert_called_once_with(DW_BANDS)
    filter_date_chain.filterBounds.return_value.select.return_value.mean.assert_called_once_with()


def test_get_s2_collection_filters_cloud_percentage(backend, mock_ee):
    geometry = MagicMock(name="geometry")
    backend.get_s2_collection(geometry, "2023-06-01", "2023-09-01")

    mock_ee.ImageCollection.assert_called_once_with(S2_COLLECTION_ID)
    mock_ee.Filter.lt.assert_called_once_with("CLOUDY_PIXEL_PERCENTAGE", 60)


def test_get_s2_product_unknown_raises(backend):
    composite = MagicMock(name="composite")
    with pytest.raises(ValueError):
        backend.get_s2_product(composite, "not-a-real-product")


def test_get_s2_product_rgb_vis_params(backend):
    composite = MagicMock(name="composite")
    result = backend.get_s2_product(composite, "RGB")
    composite.select.assert_called_once_with(["B4", "B3", "B2"])
    assert result["vis"] == {"min": 0.02, "max": 0.30}


def test_get_s2_product_ndvi_uses_normalized_difference(backend):
    composite = MagicMock(name="composite")
    backend.get_s2_product(composite, "NDVI")
    composite.normalizedDifference.assert_called_once_with(["B8", "B4"])


def test_hsv_mask_normal_range_uses_and(backend):
    composite = MagicMock(name="composite")
    backend.build_hsv_mask(composite, h_min=0.2, h_max=0.4, s_min=0, s_max=1, v_min=0, v_max=1)

    hsv = composite.select.return_value.clamp.return_value.rgbToHsv.return_value
    h = hsv.select.return_value
    # h.select("hue") is called first, so hsv.select.return_value is shared for hue only if
    # select() always returns the same mock regardless of args (true for MagicMock) —
    # what matters is which branch fired on that hue mock.
    assert h.gte.return_value.And.called
    assert not h.gte.return_value.Or.called


def test_hsv_mask_wraparound_range_uses_or(backend):
    composite = MagicMock(name="composite")
    backend.build_hsv_mask(composite, h_min=0.9, h_max=0.1, s_min=0, s_max=1, v_min=0, v_max=1)

    hsv = composite.select.return_value.clamp.return_value.rgbToHsv.return_value
    h = hsv.select.return_value
    assert h.gte.return_value.Or.called
    assert not h.gte.return_value.And.called


def test_geometry_for_extent_known_names(backend, mock_ee):
    backend.geometry_for_extent("Fylde")
    mock_ee.Geometry.Polygon.assert_called_once_with([SEARCH_EXTENT_COORDS["Fylde"]])


def test_geometry_for_extent_ireland_uses_rectangle(backend, mock_ee):
    backend.geometry_for_extent("Ireland + NI")
    mock_ee.Geometry.Rectangle.assert_called_once()


def test_geometry_for_extent_unknown_raises(backend):
    with pytest.raises(ValueError):
        backend.geometry_for_extent("Atlantis")


def test_get_search_geometry_local_buffers_reference(backend):
    reference_geometry = MagicMock(name="reference_geometry")
    backend.get_search_geometry("Local", reference_geometry)
    reference_geometry.buffer.assert_called_once_with(10_000)
    reference_geometry.buffer.return_value.bounds.assert_called_once_with()


def test_get_search_geometry_named_extent_ignores_reference(backend, mock_ee):
    reference_geometry = MagicMock(name="reference_geometry")
    backend.get_search_geometry("Fylde", reference_geometry)
    reference_geometry.buffer.assert_not_called()
    mock_ee.Geometry.Polygon.assert_called_once()


def test_run_similarity_builds_normalized_query_and_multiplies_target(backend, mock_ee):
    reference_geometry = MagicMock(name="reference_geometry")
    search_geometry = MagicMock(name="search_geometry")

    result = backend.run_similarity("2023", "2024", reference_geometry, search_geometry)

    # reference vector: reduceRegion on the reference-year AE image
    mock_ee.Reducer.mean.assert_called()
    # normalized query image is built from an ee.Array, not the raw list
    mock_ee.Image.constant.assert_called_once()
    mock_ee.Image.constant.return_value.rename.assert_called_once_with(BANDS)

    assert result.similarity is not None
    assert result.reference_geometry is reference_geometry
    assert result.search_geometry is search_geometry


def test_apply_absolute_threshold_masks_by_gte(backend):
    similarity = MagicMock(name="similarity")
    backend.apply_absolute_threshold(similarity, 0.9)
    similarity.gte.assert_called_once_with(0.9)
    similarity.updateMask.assert_called_once_with(similarity.gte.return_value)


def test_sample_dynamic_world_uses_mean_reducer_and_dw_collection(backend, mock_ee):
    region = MagicMock(name="region")
    backend.sample_dynamic_world("2023", region)

    mock_ee.ImageCollection.assert_called_once_with(DW_COLLECTION_ID)
    mock_ee.Reducer.mean.assert_called()
    filter_date_chain = mock_ee.ImageCollection.return_value.filterDate.return_value
    dw_image = filter_date_chain.filterBounds.return_value.select.return_value.mean.return_value
    dw_image.reduceRegion.assert_called_once_with(
        reducer=mock_ee.Reducer.mean.return_value, geometry=region, scale=10, maxPixels=1e7
    )


def test_resolve_percentile_threshold_uses_percentile_reducer(backend, mock_ee):
    similarity = MagicMock(name="similarity")
    search_geometry = MagicMock(name="search_geometry")
    backend.resolve_percentile_threshold(similarity, search_geometry, 90.0)
    mock_ee.Reducer.percentile.assert_called_once_with([90.0])
