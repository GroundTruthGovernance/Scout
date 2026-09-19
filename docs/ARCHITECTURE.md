# Scout desktop architecture

This document captures the design decisions made while planning the move
from the AlphaEarth Scout GEE Code Editor prototype (`v1.4.16-STRESS`) to a
standalone desktop application. It exists so decisions don't have to be
re-derived or re-litigated across sessions.

## Guiding philosophy (carried over unchanged)

> Exploration is easy; provenance is automatic; formal saving is
> disciplined; accidental loss should be difficult.

Concretely: drawing a polygon and running an AE query, or dropping a pin,
requires no project identity and touches no database row. Only an explicit
"save" (sample, response, HSV mask, pin, figure, signature) commits
anything to the project database. This must hold throughout the rewrite —
it's the single most load-bearing UX decision in the original tool.

## Compute model: hybrid, not fully offline

AlphaEarth (`GOOGLE/SATELLITE_EMBEDDING/V1/ANNUAL`), Dynamic World and
Sentinel-2 only exist as Earth Engine collections. There is no practical
local mirror. So:

- **Local**: project database (SQLite), UI, map rendering, samples,
  responses, probes, pins, figures, exports, workspace/layout state.
- **Cloud (Earth Engine)**: `reduceRegion`, cosine similarity, percentile
  thresholding, HSV compositing — called through the `earthengine-api`
  Python client instead of the Code Editor's implicit server context.
- Computed results are cached locally once produced (raster arrays, vector
  values) so re-viewing/recolouring a saved response doesn't necessarily
  re-hit EE.

### Authentication

**Per-user OAuth**, not a bundled service account. Each installation signs
in with the researcher's own Google/EE account
(`ee.Authenticate()` → `ee.Initialize(project=...)`) on first run. This was
chosen over a shared service-account key because:

- It's the only sane model for unattended overnight batch runs — usage
  counts against the user's own quota, not a shared secret's.
- No key to protect or rotate in a distributed `.exe`.
- Matches "standalone application" expectations — the app is a client of
  the user's own EE access, not a wrapper around ours.

Token storage: OS-appropriate location via `google-auth-oauthlib`'s default
flow (Windows: `%APPDATA%/scout/`). Login state surfaces in the status bar;
re-auth is a `Tools ▸ Sign in to Earth Engine` menu action.

## Tech stack

| Concern | Choice | Why |
|---|---|---|
| Shell | PySide6 (Qt) | Dockable panels, native menus/shortcuts, mature PyInstaller support. Reuses the team's existing Python/JS scripting fluency rather than requiring C++/Qt from scratch. |
| Map | QWebEngineView hosting **one** page with **N** MapLibre GL JS instances | Native Qt canvas rebuild of pan/zoom/draw/tiles would be high-cost; a single Chromium process with multiple WebGL contexts is far cheaper than N separate QWebEngineView widgets (N browser processes) when tiled/compare views are open. |
| Bridge | QWebChannel | Python ⇄ JS geometry/coordinate/command passing. |
| Project storage | SQLite, plain `sqlite3` + a hand-written DAO layer (no ORM) | Predictable PyInstaller packaging, easy to inspect/debug, dataset sizes here don't need ORM machinery. |
| EE client | `earthengine-api` (Python) | Direct port of the existing `reduceRegion`/cosine-similarity/percentile logic. |
| Packaging | PyInstaller, built on `windows-latest` via GitHub Actions | This dev environment is Linux and cannot produce a Windows binary; CI does it instead. |

## Why not fully replicate COLMAP's C++/Qt stack

COLMAP's native performance matters because it's doing dense reconstruction
on the CPU/GPU locally. Scout's heavy lifting happens on Earth Engine's
servers regardless of local language choice — the desktop app's job is
orchestration, state, and rendering, where Python + Qt is materially faster
to build and iterate on without a meaningful runtime cost.

## UI structure

- **Menu bar**: File, Edit, View, Layer, Sample, Run, Batch, Tools, Window,
  Help.
- **Main toolbar**: draw polygon, add sample, add pin, run AE, save.
- **Specialist toolbars** (HSV, Latent inspection, Batch, Compare):
  independently dockable/hideable via `View ▸ Toolbars`.
- **Dock panels**: Layers (grouped tree — Responses / HSV Masks / Historic
  AOIs / Sentinel-Latent / Pins / Search Extent), Activity Log (auto-logger
  + run history), Attribute Table (bulk delete/archive across
  samples/probes/responses/pins), Batch Queue, Probe Inspector(s), Python
  Console.
- Every dock panel is listed (never destroyed) under `View ▸ Panels`;
  closing hides, it does not lose position/state.
- **Workspaces**: named, saveable window state — panel positions, toolbar
  visibility, map pane layout (single / Run Compare 2-pane / Tiled Product
  View up to 3×2), reopenable in one action. This directly targets a
  specific pain point in comparable tools (e.g. SNAP) where tiled layouts
  don't persist across sessions.

### Two distinct multi-map comparison tools

- **Run Compare**: 2 synced panes, same product, two recipes (Response A vs
  B, or reference year vs target year).
- **Tiled Product View**: up to 3×2 synced panes, same AOI/date, different
  derived products (RGB / false-colour / NDVI / AE mask / DW / etc.) —
  modelled on SNAP's tiled product windows.

Both are implemented as multiple MapLibre instances inside the single
QWebEngineView page, synced by JS broadcasting center/zoom/bearing, not by
Qt shuttling events between separate browser processes.

## Tools

- **Eyedropper (analytical)**: click the map, read the real pixel
  value(s) — RGB or false-colour, whichever raster layer is currently
  active in the Layers panel — via the same point-reduction mechanism
  probes use, then seed the HSV qualifier range from it with an adjustable
  tolerance.
- **Colour picker (cosmetic)**: separate tool, just for choosing a mask's
  display colour. Unrelated to the analytical eyedropper.

## Data model additions beyond the GEE prototype

- **Latent Signature**: a first-class derived/imported A00–A63 vector,
  usable directly as an AE reference. `origin_geometry` is nullable — an
  imported or Python-derived signature (e.g. "mean of S01–S04") may have no
  map location at all, in which case it appears in signature lists/tables
  but not on the map. Carries a `caption` field specifically so it can
  appear correctly labelled in composed reports.
- **Pins** (observations + probes) support **both** nested folders
  (`pin_groups`, self-referential for subgroups) **and** free tags — the
  same distinction the project/experiment/field hierarchy already uses
  structure for, plus cross-cutting search.
- **Session Report composer**: assembles a sequence of saved figures (each
  already carrying its own recipe + note/QA caption) into one document,
  appending an auto-rendered overview map (toggleable labels) and an
  auto-generated coordinates table, output as Markdown feeding the existing
  Obsidian bridge and/or PDF/DOCX. This exists specifically to stop
  duplicate typing between what Scout already knows about a sample/response
  and what gets retyped into a field notebook by hand.
- **Comparison tooling operates on ad-hoc selections**, not just Sample
  Sets — multi-select in the Attribute Table, with an explicit "save
  selection as Sample Set" action once a grouping proves worth keeping.
  Sample Sets remain the disciplined, reproducible unit for batch
  extraction and (later) consensus AE response.
- **64-D comparison**: line chart (existing), a barcode/heatstrip (each
  vector as 64 coloured cells, stackable across samples, with a delta-strip
  mode for A−B) for comparing many samples at a glance, and a pairwise
  cosine-similarity matrix across a selection — reusing the exact math
  Scout already does for AE queries, just sample-vs-sample instead of
  sample-vs-scene. Spider/radar charts are used only for low-dimension data
  (Dynamic World's 9 classes, the 7 spectral indices) — not the raw 64-D
  vector, which is unreadable as a radar plot.
- Heavier statistics (clustering, PCA, regression, significance testing)
  are explicitly **out of scope** for Scout — it exports clean CSV/Parquet
  for Excel/Python/R, per the existing "Scout → Python/R/Colab → Scout"
  loop already used for calibration work.

## Explicitly deferred

- **Manifestation** (the Fylde-specific longitudinal "phenomenon followed
  through time" object) is out of scope for v1. The schema should not make
  this painful to add later — a generic `relationships` table already
  covers most of the linking need, matching the pattern the GEE prototype
  used for its relationship records.
- **Scout Batch Runner** is *not* a separate tool — it's the in-app Batch
  Queue panel (draw → "Run now" or "Add to queue" from the same action). A
  headless CLI entry point into the same core engine remains a future
  option for scripted/unattended use beyond the interactive queue.

## Batch queue + power actions

Queue is a table of pending jobs (geometry + recipe), run sequentially
against EE from the desktop process (not EE's async `Export` task queue —
those are for genuinely large exports, not this interactive loop), with
progress and retry/backoff on transient failures. On queue completion, an
explicit **post-queue action** (None / Sleep / Shutdown) fires only after a
cancellable countdown — never silently.

## Export formats (per data type)

| Data | Format |
|---|---|
| Samples / AOIs / Pins / Sample Sets | GeoPackage (primary) + KML/KMZ for Google Earth interchange |
| AE vectors, DW, probes, measurements | CSV + Parquet |
| Response rasters | Cloud-Optimized GeoTIFF |
| Figures | PNG now; SVG/PDF once a print-composer-style layout exists |
| Full project | the SQLite file + assets folder, zippable for backup/sharing |

## Non-goals for v1

- True offline compute (would require bulk-downloading AE/S2/DW tiles —
  large effort, not pursued unless a specific need arises).
- A general statistics/analysis suite — stays in Excel/Python.
- Manifestation register (see Explicitly deferred).
