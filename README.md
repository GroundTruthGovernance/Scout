# Scout

Scout is a standalone desktop research workbench for AlphaEarth similarity
scouting — draw a reference polygon, ask where/when sufficiently similar
states occur, and keep full provenance of every sample, probe, response and
figure along the way.

This repository is the desktop rebuild of the original AlphaEarth Scout
Google Earth Engine (GEE) Code Editor script. The GEE prototype
(`v1.4.16-STRESS`) proved out the workflow and data model under real field
use (project "SOL"); this app keeps that logic but replaces the Code Editor
sandbox with a real windowed application, a real project database, and real
files.

See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for the design decisions
and [`docs/DEVLOG.md`](docs/DEVLOG.md) for a running log of what has been
built and why.

## Why a desktop app, and why it still needs the internet

AlphaEarth embeddings and Dynamic World only exist as Earth Engine
collections — there's no local copy to compute against offline. So Scout is
a **hybrid**: the project database, UI, map rendering, samples, probes,
figures and exports are entirely local; the actual similarity/threshold
compute is a call out to Earth Engine via the `earthengine-api` Python
client, authenticated per-user (not a bundled service account).

What moving off the Code Editor buys you regardless of that: real dockable
windows, a real project database instead of EE-Asset checkpoint slots, real
file export, proper deletion/archiving, no more raw-pane overflow, and a
batch queue that can run overnight and put the machine to sleep when it's
done.

## Status

Early scaffold — see the task list in `docs/DEVLOG.md` for what's actually
implemented vs. planned. Not yet functional end-to-end; core data layer and
EE compute logic are being ported from the GEE JS first, then the Qt shell
and map are wired on top.

## Setup (development)

Requires Python 3.11+.

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
```

Run the test suite (does not require Earth Engine credentials — EE calls
are mocked):

```bash
pytest
```

## Running the app

```bash
scout
```

On first run you'll be asked to sign in to Earth Engine with your own
Google account (`ee.Authenticate()`); this only needs to happen once per
machine. See `docs/ARCHITECTURE.md#authentication` for details.

## Building the Windows executable

The `.exe` is built by GitHub Actions on `windows-latest` (this development
environment is Linux and cannot produce a Windows binary directly) — see
`.github/workflows/build-windows.yml`. To build locally on Windows:

```powershell
pip install -e ".[build]"
pyinstaller packaging/scout.spec
```

## Project layout

```
src/scout/
  core/        # data model, SQLite project database, Earth Engine backend
  app/         # PySide6 desktop shell (windows, docks, menus)
  webmap/      # embedded MapLibre GL map (HTML/JS/CSS + vendored library)
tests/         # pytest suite (EE calls mocked)
docs/          # architecture + running dev log
packaging/     # PyInstaller spec + Windows CI build
```
