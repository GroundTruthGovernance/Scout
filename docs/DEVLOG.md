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

<!-- New entries go above this line, most recent first is fine as long as
     each entry is dated and self-contained. -->
