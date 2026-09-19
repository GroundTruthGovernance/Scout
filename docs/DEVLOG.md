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

<!-- New entries go above this line, most recent first is fine as long as
     each entry is dated and self-contained. -->
