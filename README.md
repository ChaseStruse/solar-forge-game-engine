# Solar Forge Game Engine

A proposed native Arch Linux desktop engine for making fun, lightweight 2D games.
Python and PySide6 Qt Widgets, aligned with Solar Forge Life Helper and part of the
Solar Forge Studios suite. Local-first and LLM-first, with native Linux exports.

No JavaScript, TypeScript, browser UI, embedded webview, or web export.

Solar Forge combines a clear visual editor, editable game code, and an assistant
that works through inspectable, undoable actions. Manual development and exported
games should work without an AI service.

**Status: first editor foundation.** Create rectangles, select them in the viewport
or scene tree, edit their name/position/size/color, undo/redo, and save/reopen scene
documents. New/Open/Close protect unsaved changes. This is not yet a playable game
engine: gameplay, assets, project folders, AI, sandboxed previews, and exports follow
in later small features.

## Run on Linux

Use Python 3.14 and uv:

```sh
uv sync --frozen
uv run --frozen solar-forge-engine
```

Choose **Add rectangle**, edit the **Inspector**, and press **Apply changes**.
Save to a `.forge.json` file. These version-one files contain the entire scene;
the project-folder format in the plan is future work. Files never execute scripts.

## Development checks

```sh
uv sync --frozen --extra test
uv run --frozen --extra test ruff check src tests
uv run --frozen --extra test ruff format --check src tests
uv run --frozen --extra test mypy
QT_QPA_PLATFORM=offscreen uv run --frozen --extra test pytest -q
```

Offscreen tests do not establish real Wayland/GPU compatibility. Qt Widgets uses
the smaller PySide6 Essentials distribution; optional add-on modules are deferred.

## Docker

Run the native window from a Linux Wayland session:

```sh
docker compose up --build desktop
```

Scene files saved under `/projects` persist in the Compose `projects` volume.
`docker compose down` retains it; `docker compose down -v` deletes it. To use a host
project folder, bind it to `/projects` in a local `compose.override.yaml`. On hosts
whose numeric UID/GID are not 1000, set `SOLAR_FORGE_UID` and `SOLAR_FORGE_GID` to
the values from `id -u` and `id -g` before building. The app runs without networking.

Run lint, formatting, type checks and tests in the independent headless image:

```sh
docker compose -f compose.test.yaml run --build --rm test
```

The test service has no display mount, user project volume, or network access.
Its configuration works without a Wayland session. Native compositor/GPU testing
and gameplay preview isolation remain later validation work.

- [Product and implementation plan](docs/ENGINE_PLAN.md)
- [Instructions for coding agents](AGENTS.md)

The native Python desktop direction is fixed. Runtime rendering performance,
packaging, and sandboxing still need their planned validation milestones.
