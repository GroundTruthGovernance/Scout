# Dev log

Running log of what's been built, in what order, and why — kept so an
autonomous or resumed session can pick up accurately without re-deriving
context, and so you have a readable trail of the overnight build.

## 2026-09-19 — Session 1: scaffold

- Repository was empty; this is the first commit.
- Created Python project scaffold (`pyproject.toml`, `src/scout/` package
  layout: `core/`, `app/`, `webmap/`), dev/build extras, pytest config.
- Wrote `docs/ARCHITECTURE.md` consolidating every design decision made in
  the planning conversation (compute model, auth model, tech stack, UI
  structure, comparison tooling, data model additions, deferred items,
  export formats) so nothing discussed only in chat gets lost.
- Next: SQLite schema + DAO layer (Task #2), then port the EE algorithmic
  core from the GEE JS (Task #3).

## 2026-09-19 — Session 1 continued: project database

- `src/scout/core/schema.sql`: full SQLite schema — projects/experiments/
  sessions/vocabulary, samples, ae_vectors, dynamic_world, responses,
  hsv_masks, sample_sets(+members), pins(+pin_groups,+pin_tags),
  latent_signatures, figures, session_reports, events/measurements/
  relationships/references, workspaces, bookmarks, batch_jobs,
  activity_log. Deliberately flat/denormalized in the same spirit as the
  GEE prototype's FeatureCollection property bags — see
  docs/ARCHITECTURE.md for the reasoning.
- `src/scout/core/util.py`: pure-Python port of the JS helper layer
  (safe_code/safe_text/safe_number, make_uid, simple_hash, colour/palette
  helpers) — no EE or Qt dependency, fully unit tested
  (`tests/test_util.py`).
- `src/scout/core/db.py` + `models.py` + `repository.py`: connection/schema
  management, typed dataclasses, and DAO functions for projects, samples
  (with duplicate-id protection), AE vectors + Dynamic World (upsert,
  64-value validation), responses (recipe-fingerprint duplicate lookup),
  pins with **both** folders (`pin_groups`, self-referential) and tags,
  latent signatures (nullable origin geometry, 64-value validation), and
  the activity log. `record_status` is `active | archived | deleted`
  throughout — `archived` hides from default listings without being
  destructive, `deleted` is excluded everywhere. This is the concrete fix
  for "no remove/archive pin control yet" in the GEE prototype's bug list.
- Set up a venv, installed the package (PySide6 6.11, earthengine-api
  1.7.43, numpy 2.4.6 all installed cleanly), wrote
  `tests/test_repository.py` covering all of the above — **19/19 tests
  pass**.
- Next: port the EE algorithmic core (cosine similarity, thresholding,
  HSV mask, S2 products) to `core/ee_backend.py` (Task #3).

## 2026-09-19 — Session 1 continued: Earth Engine compute backend

- `src/scout/core/ee_backend.py`: `EarthEngineBackend` class porting
  sections 2/15/17/22 of the GEE prototype — `load_ae_year`/`load_dw_year`,
  Sentinel-2 collection/composite/product functions (RGB, false colour,
  SWIR, NDVI/NDWI/NDMI/BSI/NDRE/NBR/NBR2, individual bands),
  `get_s2_feature_image` (all bands+indices, for probes), `build_hsv_mask`
  (including the hue-wraparound And/Or branch), search extents (all named
  AOI polygons ported verbatim as coordinate lists), `run_similarity` +
  `build_reference_vector` (the actual cosine-similarity core), and both
  absolute and percentile thresholding.
- Takes the `ee` module as a constructor argument (defaults to the real
  package) specifically so tests can inject a `MagicMock` and verify the
  *shape* of the computation graph — which collection, which reducer,
  which bands, and for HSV, which boolean branch — without network access.
  This sandbox has no Earth Engine credentials at any point in this build,
  so **live verification against real AlphaEarth/Sentinel-2 data has not
  happened and needs to happen on your machine** once the auth flow
  (Task #7) exists. Confirmed `import ee` itself works with zero
  credentials (only `ee.Initialize()`/actual server calls need auth), so
  the app can at least start and show a "sign in" prompt cleanly.
  `build_response_fingerprint` and `get_ae_vis` (vis-params dict for
  `getMapId`) added to `core/util.py` alongside the existing helpers, since
  both are pure Python with no EE dependency.
- **37/37 tests passing.** Notably the HSV hue-wraparound test would
  actually fail if the And/Or branch were wired backwards — verified by
  briefly swapping the condition and confirming the test catches it.
- Next: Qt shell (Task #4) — main window, menu bar, dock panel stubs.

<!-- New entries go above this line, most recent first is fine as long as
     each entry is dated and self-contained. -->
