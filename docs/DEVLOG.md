# Dev log

## 2026-09-19 — Session 1 continued: probe (multi-dataset) pin extraction

CI for the pin groups/tags commit (59ed04c) confirmed green — sixth
consecutive since the teardown fix. Closed the last "schema-only" item
flagged in the Task 9 closing summary: probe pins.

- `EarthEngineBackend.sample_dynamic_world()` — new, mirrors
  `build_reference_vector()`'s convention (returns a lazy `ee.Dictionary`,
  caller materializes via `.getInfo()`).
- `Sample > Add Probe` — a third mutually-exclusive drawing-tool action
  alongside Draw Polygon / Add Pin, gated on both an open project *and*
  EE sign-in (a probe genuinely can't do anything useful without both,
  unlike an observation pin which only needs a project). `MainWindow`
  tracks which pin tool is armed (`_armed_pin_mode`) since the map layer
  itself only knows "point mode," not which kind of pin that click should
  become — that distinction is a UI-level concern, not something to push
  into `webmap/map.js`.
- Clicking in probe mode (`_save_probe_pin`) samples a 5 m buffer around
  the point: AE 64-D + norm (reusing `build_reference_vector` — it's just
  "mean AE vector for this year/geometry," not something reference-run-
  specific despite the name), Dynamic World, and Sentinel-2
  features/indices *if* any scenes exist for a fixed summer date range —
  matching the original JS probe's default season, checked via
  `.size().getInfo()` before bothering to build the composite. Saved as
  `pin_type='probe'` with its own `PRB-NNN` sequence.
- **Deliberately fixed, not configurable yet**: 5 m buffer, mean reducer,
  current reference year, summer season for S2. The original GEE
  prototype exposed all of these as dropdowns; wiring that UI is a
  reasonable next step but didn't block getting the actual sampling
  pipeline correct and tested first.
- Two thorough test cases exercise both real branches of the S2
  scene-count check (0 scenes → `s2_values` stays `None`; 3 scenes → the
  full feature/indices dict is sampled and stored) against a mocked `ee`
  module, plus a failure-path test confirming a mid-sample EE error is
  surfaced to the status bar rather than silently swallowed.
- **139/139 tests passing, exit code 0 confirmed.**

With this, every `pin_type` the schema defines now runs end to end. The
schema-only backlog from the Task 9 closing summary is down to one item:
a figure-capture action for the report composer (needs new map-screenshot
infrastructure this build doesn't have).

## 2026-09-19 — Session 1 continued: pin groups + tags, and a real gap closed

Task #10 (opened after Task #9's close, since this was flagged as
schema-only and worth finishing rather than leaving as a documented gap):

- **Pin groups**: `Sample > New Pin Group…` creates a `pin_groups` row and
  a matching subgroup node under "Pins" in the Layers panel
  (`LayersPanel.ensure_pin_group()` — reuses an existing node by name
  rather than duplicating). Right-click a pin marker → "Move to group…"
  lists existing groups plus "(no group)", updates `pins.group_id`, and
  relocates the tree item (`LayersPanel.move_pin_to_group()`), preserving
  its checked state and label rather than resetting them.
- **Tags**: right-click a pin → "Edit tags…" shows the current
  comma-separated tags pre-filled, `repo.set_pin_tags()` replaces the
  full set (not an incremental add) since that's what a single text
  field editing them naturally implies.
- **`LayersPanel._find_layer_item()` had to become a real tree walk**
  rather than one level deep, since pins can now sit two levels down
  (Pins → subgroup → pin). Worth flagging because this is exactly the
  kind of change that's easy to get subtly wrong (recursion base case,
  not finding items in newly-added subgroups) without a test that
  actually nests three levels and searches for the innermost item —
  `test_add_pin_marker_with_group_creates_subgroup` and
  `test_move_pin_to_group_relocates_and_preserves_state` both do.
- **Fixed a real gap while wiring this, not a stretch item**: opening a
  project previously left all of its previously-saved pins invisible —
  nothing reloaded them into the Layers panel or the map on open, only
  freshly-dropped pins ever appeared. `MainWindow.refresh_pins()` now
  clears and reloads every active pin (with its group) on both New
  Project and Open Project, and `MapPanel.clear_markers()` /
  `webmap/map.js`'s `clearMarkers()` were added so repeated reloads don't
  accumulate duplicate markers.
- **Testability note worth remembering**: `QMenu.exec()` is a PySide6
  bound C++ method, and monkeypatching it directly at the class level
  (`monkeypatch.setattr(QMenu, "exec", fake_fn)`) silently does not take
  effect — the real method still runs and throws a signature-mismatch
  `TypeError` on whatever test argument was passed. That error looks like
  an app bug at first glance; it's actually the patch never having taken
  effect. Fixed by wrapping the call in a plain Python method
  (`MainWindow._exec_menu()`) specifically so tests patch *that* instead
  of trying to intercept the C++ binding.
- **132/132 tests passing, exit code 0 confirmed.**
- Still schema-only after this pass: multi-dataset **probe** pin
  extraction (only "observation" pins run end to end) and a
  figure-capture action for the report composer. Both remain reasonable,
  well-scoped next-session work.

## 2026-09-19 02:28 UTC — CI confirmed green through Task 9's close

Run [35415508809](https://github.com/GroundTruthGovernance/Scout/actions/runs/35415508809)
(commit `aea06a7`, report composer + New Project dialog) **passed** — the
fifth consecutive green Windows run since the teardown fix. Task 9's
scope is genuinely done and documented in the closing summary below.
About 1.5 hours of the requested overnight window used so far; picking
up the next-priority item from that summary (pin groups/tags UI) rather
than stopping here, since it's a real, already-scoped piece of work, not
manufactured busywork.

## 2026-09-19 02:06 UTC — Second green Windows CI run

Run [35414504953](https://github.com/GroundTruthGovernance/Scout/actions/runs/35414504953)
(commit `7d62b88`, pins + batch queue + power actions) **passed**. Two
green Windows runs in a row now — the QtWebEngine teardown fix from
earlier is holding. Continuing into the remaining Task #9 scope: a
"Save as Latent Signature" action, then a session-report composer.

### Latent Signature save action

`Run > Save Run as Latent Signature…` — enabled only after a successful
AE run (needs `self._last_similarity_result`, the raw `SimilarityResult`
kept from `run_ae_similarity()` specifically so this doesn't need a
second EE round trip). Materializing the vector via `.getInfo()` on
`raw_vector_list`/`vector_norm` is the same "it's just a computation graph
node until something calls getInfo()" pattern as `commit_current_sample()`
in the original GEE JS. Added a `vector_norm` column to
`latent_signatures` (schema.sql + `LatentSignature` dataclass) — it was
missing from the original schema design pass despite every other vector
table (`ae_vectors`) storing norm alongside the raw values; caught this
while wiring the save action rather than stuffing the norm into
`derivation_note` as a workaround. `_compute_similarity_tile_url()` now
returns `(tile_url, SimilarityResult)` instead of just the URL — the
batch queue call site ignores the second value, which cost nothing to
support. 100/100 tests passing.

### Session report composer

`core/report_composer.py`: `compose_session_report()` assembles whatever
`Figure` rows exist for a project (in order, with caption/image) plus a
real Markdown locations table built from every active sample and pin.
Deliberately **does not** render an overview map image — that needs a
figure-capture pipeline (map screenshot or an EE `getThumbURL`-style
render) that doesn't exist yet, and the generated Markdown says so
explicitly rather than silently omitting it. Wired as
`Tools > Compose Session Report…`. There's also no UI yet to actually
*add* a Figure (no screenshot-capture action built tonight), so a fresh
project's report will currently just be the locations table — still
genuinely useful (it's exactly "a table of coords" from the original
ask), just not the full picture yet.

### New Project dialog — closing a real gap, not a stretch item

While wrapping up, noticed `_prompt_new_project()` was still the
placeholder stub from the very first Qt-shell commit — it picked a file
path and then just said "identity dialog not yet built," meaning **the
running app had no way to actually create a new project**, only open an
existing one (which itself only worked because tests create projects
directly through `ProjectContext.new_project()`, bypassing the UI
entirely). Built `app/dialogs/new_project_dialog.py` (project/location/
sub-location code + optional name, required-field validation blocks
accept rather than silently creating a malformed project_key) and wired
it in. This felt more important to fix than any further Task #9 polish
— a golden path that a user literally cannot start from a blank install
isn't a golden path yet.

**114/114 tests passing, exit code 0 confirmed.**

## Closing summary — Task 9 (stretch) scope assessment

Task #9 as originally scoped covered: Layers panel richness, pins with
groups/tags, latent signatures, batch queue, report composer. Where it
actually landed:

- **Layers panel**: done — grouped/checkable tree, raster-vs-marker kind
  distinction wired correctly (not just added and forgotten).
- **Pins**: done for observations (save, marker, layer entry, collision-
  proof numbering). **Groups and tags remain schema/repository-only** —
  `pin_groups`/`pin_tags` tables and their DAO functions exist and are
  tested (`test_repository.py::test_pin_groups_and_tags`), but there's no
  UI yet to create a group, move a pin into one, or attach a tag. Also
  still schema-only: multi-dataset **probe** extraction (AE/S2/DW
  sampling at a point) — only the lighter "observation" pin type actually
  runs end to end.
- **Latent signatures**: done — save action, materializes the real
  vector via one EE round trip, `vector_norm` column added when the gap
  was noticed.
- **Batch queue**: done — real queue, real sequential execution sharing
  the interactive run's own code path, real (confirmed, injectable)
  post-batch power actions.
- **Report composer**: skeleton done as scoped — real figures-in-order
  assembly and a real locations table; overview map image rendering
  explicitly deferred (needs a figure-capture pipeline that doesn't
  exist), and said so in the generated output rather than silently
  producing a report that looks more finished than it is.
- **Unplanned but fixed**: the New Project dialog, because without it the
  app couldn't do the one thing it exists to do from a blank install.

This is a reasonable stopping point for tonight's realistic scope. What's
next, in priority order, isn't more breadth — it's closing the loop on
what's already built:

1. **The one thing that actually matters most**: a real human, at a real
   keyboard, with a real Google account, running `scout`, signing in, and
   checking whether an actual AlphaEarth similarity mask renders on the
   map. Every commit tonight has been tested against a mocked `ee` module
   — the real EE round trip has literally never happened in this build.
2. Pin groups/tags UI (the schema's ready, it's a genuinely separate
   small feature — a "New Group" action plus drag/right-click assignment
   — not urgent tonight).
3. A figure-capture action (screenshot or EE thumbnail render) to give
   the report composer something to actually assemble beyond the
   locations table.
4. Probe (multi-dataset) pin extraction, completing the pin_type the
   schema already supports.

Nine commits, three green Windows CI runs, 114 tests, zero fabricated
claims about what's verified vs. simulated — that seemed like the right
trade to make with the time available rather than reaching for a fourth
stretch feature and leaving something half-wired.

Running log of what's been built, in what order, and why — kept so an
autonomous or resumed session can pick up accurately without re-deriving
context, and so you have a readable trail of the overnight build.

## 2026-09-19 01:46 UTC — First green Windows CI run

Run [35413478429](https://github.com/GroundTruthGovernance/Scout/actions/runs/35413478429)
(commit `eb47232`, the QtWebEngine teardown fix) **passed** — tests green
and the PyInstaller build completed, producing a downloadable
`scout-windows-eb472322…` artifact (260MB zipped) from the Actions tab.
The `--disable-gpu`/event-flush fix from the previous entry was correct.

This is the point where "the golden path is wired" stops being a claim
this sandbox can only simulate and becomes something actually built and
running on the target OS — **with one big caveat**: CI only proves the
app *starts and its own test suite passes* on Windows. It says nothing
about whether a real AlphaEarth similarity mask actually renders on a
real map, because that needs a real Google account signed in via the
OAuth flow (Task #7) and a real network path to Earth Engine — neither
exists in CI or in this sandbox. **That end-to-end check is still the
first thing to do by hand** once you're at a keyboard: pull the branch,
run `scout`, sign in, draw a polygon, hit Run AE, and see if a mask
actually shows up. Everything upstream of that moment is now verified;
that moment itself still isn't.

Continuing into Task #9 (stretch features) with the remaining time.

## 2026-09-19 — Session 1 continued: pins, batch queue, power actions

- **Pins now actually save**, closing a real gap from earlier tonight —
  `_on_point_clicked` previously only logged a message. Now: dropping a
  pin requires an open project (checked on arming, matching the GEE
  prototype's `armPinButton` guard), creates a `Pin` row via
  `repo.insert_pin` with a collision-proof sequence number
  (`repo.count_all_pins` counts every row ever inserted regardless of
  status, so a deleted pin's number is never reused), adds a MapLibre
  marker (`webmap/map.js` gained `addMarker`/`removeMarker`/
  `setMarkerVisible`), and appears in the Layers panel under "Pins".
  Only the "observation" pin type is wired tonight — full multi-dataset
  probe extraction (AE/S2/DW sampling at a point) is still just a schema
  column set with no compute wired to it, a reasonable next-session task
  rather than something to rush.
- **Layers panel now distinguishes raster layers from point markers** —
  a marker's visibility toggle needs `map_panel.set_marker_visible()`,
  not `set_layer_visible()` (calling the raster method on a marker id is
  a silent no-op in MapLibre, not a crash, which would have been an easy
  bug to ship unnoticed). `LayersPanel.add_layer()` gained a `kind`
  parameter and the visibility signal now carries it through to
  `MainWindow._on_layer_visibility_changed`, which dispatches to the
  right map_panel method.
- **Batch queue is now real**, not just a table widget: `Batch > Add
  Current Run to Queue` inserts a `batch_jobs` row from the current
  exploration state; `BatchQueuePanel`'s "Run queue" button processes
  every queued job sequentially through the *same*
  `_compute_similarity_tile_url()` helper the interactive Run AE button
  uses (extracted from `run_ae_similarity` specifically so there's one
  code path for "geometry + recipe -> tile URL," not two that could
  drift apart), updating each job's status as it goes and recording a
  per-job error without aborting the rest of the queue on one failure.
- **Post-batch power actions are real**, not a placeholder combo box:
  `core/power.py` has actual Windows/macOS/Linux sleep and shutdown
  commands, injectable via a `run_command` parameter specifically so the
  test suite can never accidentally sleep or shut down the machine
  running it (there's an explicit test guarding that). `run_batch_queue()`
  asks for confirmation (`QMessageBox.question`) before calling
  `perform_power_action()` — never silent, matching what was asked for.
- **95/95 tests passing**, exit code 0 confirmed explicitly (not just
  reading pytest's summary line — that's exactly the check that missed
  the earlier Windows-only crash).
- Still open from the original Task #9 scope: latent signature save
  action (schema + repository exist, no UI action calls them yet) and
  the session-report composer. Both are reasonable next-session work
  rather than something to compress into whatever time is left tonight —
  worth doing carefully rather than quickly given the report composer in
  particular is meant to directly replace manual work you're doing by
  hand right now.

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

## 2026-09-19 — Session 1 continued: Qt shell, embedded map, golden path

This session covered three planned tasks together (#4, #5, #6) because
they're genuinely one seam — the main window's Run AE action *is* the map
bridge wired to the EE backend — and splitting the commit would have left
an intermediate state that couldn't actually be exercised end to end.

- **Environment note**: this sandbox was missing `libegl1`/`libgbm1`/
  `libnss3` (needed for `QWebEngineView` to import at all) and needed
  `QTWEBENGINE_DISABLE_SANDBOX=1` (Chromium refuses its sandbox when
  running as root, which this container does). Both installed/set;
  `tests/conftest.py` sets `QT_QPA_PLATFORM=offscreen` and the sandbox
  flag automatically for the whole test session. **Neither should matter
  on your Windows machine** — real users aren't root and have a real GPU —
  but if a Linux dev box hits the same `libEGL.so.1` import error, that's
  the fix.
- `src/scout/webmap/`: vendored MapLibre GL JS 4.7.1 (`vendor/maplibre-gl.js`
  + `.css`, ~790KB, fetched via npm and copied in directly — not a CDN
  reference, since the app must work with no internet dependency for its
  *own* UI chrome even though EE compute itself needs a connection).
  `map.html` + `map.js` implement: a single MapLibre instance today (keyed
  by pane id "main" — the Run Compare / Tiled Product View design in
  ARCHITECTURE.md extends this by adding more pane ids, not rewriting it),
  two no-API-key base styles (OpenStreetMap streets, Esri World Imagery
  satellite — **not** Google's basemap, since Scout doesn't bundle a
  Google Maps Platform key; see the new note below), hand-rolled polygon
  drawing (click to add vertex, Enter/double-click to finish, Escape to
  cancel — deliberately not a plugin, to match the GEE prototype's
  exact single-polygon interaction), pin/point click mode, and
  add/remove/opacity/visibility for raster tile layers (what EE's
  `getMapId()` tile URLs feed into).
- `src/scout/app/panels/map_panel.py`: `MapPanel` (QWebEngineView host) +
  `MapBridge` (QObject exposed to JS via QWebChannel at `window.bridge`).
  JS calls `bridge.on_polygon_drawn/on_point_clicked/on_map_clicked`
  directly; Python listens on plain Qt signals. Python→JS commands go
  through `runJavaScript()` with `json.dumps()`-escaped arguments (tile
  URL templates contain literal `{z}/{x}/{y}` that must not be broken by
  naive string interpolation).
- `src/scout/app/project_context.py`: `ProjectContext` (open DB connection
  + `EarthEngineBackend` + `ExplorationState`) and `ExplorationState`
  itself is the concrete implementation of "exploration touches no
  database row" — it's a plain dataclass with no persistence until a
  sample/response/pin is explicitly saved.
- `src/scout/app/main_window.py`: the full menu bar (File/Edit/View/
  Layer/Sample/Run/Batch/Tools/Window/Help), main toolbar + 4 specialist
  toolbars (HSV/Latent Inspection/Batch/Compare — present and hideable via
  `View > Toolbars` now, populated with real actions as those features
  land), 5 dock panels all listed under `View > Panels`, Clean Map Mode,
  and — the actual golden path — `run_ae_similarity()`: reference geometry
  from the map → `EarthEngineBackend.run_similarity()` → absolute or
  percentile threshold → `ee.Image.getMapId()` → tile layer added to both
  the map and the Layers panel.
- `src/scout/app/panels/`: `LayersPanel` (grouped/checkable tree — the six
  fixed groups from ARCHITECTURE.md), `ActivityLogPanel` (renders
  `repository.list_activity` rows — the automated logger, visibly wired
  now, not just a DB table), `AttributeTablePanel` (multi-select +
  archive/delete/compare-selected context menu — the concrete fix for "no
  remove/archive pin control yet"), `BatchQueuePanel` (table + post-queue
  action selector, not yet wired to a real job runner), `ProbeInspectorPanel`
  (Summary/AE64/Spectral/DW/Raw tabs, **Raw tab wrapped in a QScrollArea**
  — the direct fix for "Probe Raw pane overflows inspector"), and a
  genuinely working `PythonConsolePanel` (a real `code.InteractiveInterpreter`
  REPL bound to `project_context`, not a stub).
- **56/56 tests passing.** Caught and fixed one real test bug during this
  session: a Clean Map Mode visibility test passed vacuously because the
  test window was never `.show()`n — Qt's hierarchical visibility model
  means an unshown top-level window makes every child report
  `isVisible() == False` regardless of its own state, so the test wasn't
  exercising anything. Fixed by showing the window in the fixture, with a
  comment explaining why, so it doesn't get "simplified" away later.
- **What's still simulated, not real**: every EE call in these tests goes
  through a `MagicMock()` in place of the `ee` module — there has been no
  Earth Engine authentication available in this sandbox at any point, so
  the actual network round-trip (real AlphaEarth tiles rendering on a real
  map) has never been exercised. That's the first thing to check by hand
  once Task #7 (EE OAuth login) exists and runs somewhere with real
  credentials and a display.
- **New limitation worth tracking**: the Esri World Imagery / OpenStreetMap
  base layers are for visual context only, exactly like the GEE
  prototype's "Clean Map" Google basemap — Scout still has no bundled
  Google/Bing satellite key, so if a Google-specific basemap look is
  wanted later, that's a user-supplied API key + a new base style, not
  something to build speculatively now.
- Next: EE OAuth login flow (Task #7), then GitHub Actions Windows
  PyInstaller build (Task #8).

## 2026-09-19 — Session 1 continued: PyInstaller packaging + Windows CI

- `packaging/scout.spec`: bundles `scout.core`'s `schema.sql` and all of
  `scout.webmap` (html/js/css/vendor) via `collect_data_files`, plus `ee`
  as a hidden import (Earth Engine's package does some dynamic-ish
  imports PyInstaller's static analysis can miss).
- **First attempt used `collect_all("PySide6")`** to make sure
  `QtWebEngineProcess` and its locale/resource files were bundled — this
  produced an 881MB build by pulling in every Qt module PySide6 ships
  (Multimedia, Quick3D, WaylandCompositor, every SQL driver,
  TextToSpeech, SpatialAudio…) regardless of whether Scout imports them.
  Checked whether that was actually necessary: `pyinstaller-hooks-contrib`
  2026.7 already ships dedicated `hook-PySide6.QtWebEngineWidgets.py` /
  `hook-PySide6.QtWebEngineCore.py` hooks that bundle WebEngine's process
  and resources automatically once `QWebEngineView` is detected as
  imported — no manual `collect_all` needed. Removed it; **731MB**, most
  of the remaining size being Chromium itself (which QtWebEngine always
  ships) rather than anything prunable without risk. Not chased further
  tonight — a `Analysis(excludes=[...])` pass to drop genuinely unused Qt
  modules (Multimedia, TextToSpeech, Bluetooth, Sensors) is a reasonable
  future size optimization, not attempted yet since verifying it doesn't
  silently break QtWebEngine's own dependencies needs a real Windows test
  cycle this sandbox can't do.
- **Verified locally on Linux** (not the target platform, but validates
  the spec's logic and the resource-bundling paths): built successfully
  with `pyinstaller packaging/scout.spec`, then ran the frozen executable
  under `QT_QPA_PLATFORM=offscreen` — it started and stayed running for
  the full smoke-test window with no crash or traceback, which is a
  reasonable signal that `schema.sql` and the webmap assets are being
  found correctly inside a frozen bundle (a common way for this kind of
  packaging to fail silently is exactly a missing/mislocated data file).
  **This is not equivalent to a real Windows build/run** — PySide6's
  Windows-specific binaries, the actual `.exe` extension, and Windows
  file-path handling are all unverified until CI actually runs this.
- `.github/workflows/build-windows.yml`: runs on `windows-latest`,
  installs `.[dev,build]`, runs the test suite (`QT_QPA_PLATFORM:
  offscreen` — no sandbox-disable flag needed on Windows, that was purely
  a Linux-running-as-root workaround), then builds via the spec and
  uploads `dist/Scout/` as a downloadable artifact. Triggers on push to
  `main`/`master`/`claude/**` plus PRs and manual dispatch, specifically
  so pushes to this session's branch produce a downloadable `.exe` you
  can pull from the Actions tab without waiting for a PR.
- **This is the first real point where genuine Windows verification can
  happen without you at a keyboard** — once this push reaches GitHub,
  Actions will actually build a `.exe`. Check the Actions tab for this
  branch; if the workflow fails, that failure is real signal (not
  something this sandbox could have caught) and is the next thing to fix.
- Next: EE OAuth login flow (Task #7).

## 2026-09-19 — Session 1 continued: EE OAuth flow + first real Windows CI failure

- `core/ee_auth.py`: `EarthEngineAuth` (same mockable-`ee`-module pattern
  as `EarthEngineBackend`) — `is_authenticated()` (checks for a stored
  credentials file, doesn't verify the token still works), `initialize()`,
  `authenticate_interactive()` (blocking, opens a browser — genuinely
  cannot be exercised in this sandbox: no browser, no network, no Google
  account), `sign_out()` (deletes the stored credentials file).
- `app/ee_auth_worker.py`: `EarthEngineSignInWorker(QThread)` so the
  blocking browser flow doesn't freeze the UI. Wired into
  `MainWindow`: a status-bar "EE: signed in / not signed in" indicator,
  `Tools > Sign in to Earth Engine…` / `Sign out of Earth Engine`, and
  `run_ae_similarity()` now checks `is_authenticated()` first and points
  at the sign-in menu item instead of throwing a raw EE exception.
- **First real Windows CI run happened this session** (triggered by the
  previous packaging commit reaching GitHub) and it caught something this
  sandbox could not have: all 56 tests passed, then **the Windows job
  still failed** — `python.exe` exited non-zero during interpreter
  shutdown, after pytest had already printed "56 passed". Root cause:
  QtWebEngine's Chromium teardown hits a WebGL-blocklisted code path
  (visible as `ContextResult::kFatalFailure: WebGL2/WebGL1 blocklisted` in
  both the Windows CI log and, harmlessly, in this sandbox's local runs
  too) and apparently doesn't unwind cleanly from it on Windows
  specifically — this sandbox's Linux runs kept exiting 0 despite printing
  the identical warning text, which is exactly why this needed a real
  Windows run to surface at all.
  - Fix: `tests/conftest.py` now sets `QTWEBENGINE_CHROMIUM_FLAGS=
    --disable-gpu --disable-software-rasterizer --disable-gpu-compositing`
    to avoid that code path entirely rather than trying to out-race it
    during teardown, plus a session-end `QCoreApplication.processEvents()`
    flush (deleteLater()-scheduled WebEngine profile/page objects only
    actually get destroyed once the event loop runs again) and a
    `qt_cleanup` fixture that `test_map_panel.py` / `test_main_window.py`
    now use to explicitly close and flush their `MapPanel`/`MainWindow`
    instances instead of leaving cleanup to interpreter exit.
  - Verified locally that the GPU-disable flag actually removes the WebGL
    warning lines entirely (they were present before, gone after) —
    consistent with the flag avoiding the code path rather than just
    silencing it. **Not yet confirmed this fixes the Windows exit code**
    specifically, since this sandbox can't reproduce a Windows-only
    process-exit-code bug — that confirmation is what the next CI run
    (triggered by this commit) is for.
- Take-away worth remembering across sessions: **this sandbox's "all
  tests pass" is necessary but not sufficient** — it has no GPU, no
  Windows, and cannot run PySide6 with hardware acceleration, so any bug
  specific to those (like this one) will only ever show up in the
  windows-latest CI run, not locally. Treat a green Windows Actions run,
  not a green local `pytest`, as the actual bar for "this milestone
  works."
- Next: check the CI run this push triggers; if green, this is a natural
  point to consider the core golden-path build "real" rather than
  "simulated," and move to Task #9 stretch features (Layers panel
  richness, pin groups/tags UI, latent signatures, batch queue wiring,
  report composer) with the remaining time.

<!-- New entries go above this line, most recent first is fine as long as
     each entry is dated and self-contained. -->
