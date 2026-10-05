# Solar Forge Game Engine

A proposed native Arch Linux desktop engine for making fun, lightweight 2D games.
Python and PySide6 Qt Widgets, aligned with Solar Forge Life Helper and part of the
Solar Forge Studios suite. Local-first and LLM-first, with native Linux exports.

No JavaScript, TypeScript, browser UI, embedded webview, or web export.

Solar Forge combines a clear visual editor, editable game code, and an assistant
that works through inspectable, undoable actions. Manual development and exported
games should work without an AI service.

**Status: editor and built-in native playback.** Create rectangles, select them in the viewport
or scene tree, edit their name/position/size/color, undo/redo, and save/reopen scene
documents. New/Open/Close protect unsaved changes. Play opens a separate native
window with keyboard movement, wall collisions, and coin collection. PNG sprites
and basic project folders are supported; AI, sandboxed Python scripts, and exports
follow in later small features.

## Run on Linux

Use Python 3.14 and uv:

```sh
uv sync --frozen
uv run --frozen solar-forge-engine
```

Choose **Add rectangle**, edit the **Inspector**, and press **Apply changes**.
Select an object and choose **Duplicate object** (Ctrl+D) to create a selected copy
24 units to the right and down. Copies preserve size, color and gameplay role,
use a new ID, and support undo/redo. Duplication uses applied properties.

Choose **Import PNG** (Ctrl+Shift+I) to add a sprite. PNGs must be at most
256×256 pixels and 2 MiB. Transparent pixels are preserved; width and height in the
Inspector control its displayed size. Imported pixels are copied into game data,
so moving/deleting the original image does not affect playback. **Remove sprite**
restores geometric rendering and can be undone. Sprite color is not tinted;
role and rectangular collision bounds still determine gameplay.

Save to a `.forge.json` file. Version-three files contain the entire scene,
roles, and optional sprite pixels. Versions one
and two still load. Before upgrading an older file, its exact bytes are retained
in `<filename>.v1.bak` or `<filename>.v2.bak`. Existing backups are never overwritten;
use Save As if that backup name is occupied. Scene files remain limited to 4 MiB;
embedded sprites count toward that limit. Files never execute scripts.

Use **File → Create project from scene…** (Ctrl+Alt+N) and enter a **new folder name**
to save the current applied scene as a project. Existing folders are never replaced.
The project contains `project.json`, `scenes/main.forge.json`, and an `assets/`
directory. **File → Open project…** (Ctrl+Alt+O) selects a project folder. Ordinary
Save updates its scene; Save As writes a standalone scene and leaves project mode.
Opening an existing standalone scene and creating a project copies it without
rewriting the original. The manifest uses a relative scene path; traversal and
symbolic links in that path are rejected on open and rechecked on save.

Project saves write version-four scene files with relative sprite references to
`assets/<content-hash>.rgba`. Identical sprites share one bounded RGBA pixel file;
files are validated by size, dimensions, and content hash when opened. Move the
entire folder to keep the project portable. Standalone Save As still embeds pixels
in version-three scenes, and Play receives resolved data without reading asset paths.
Older embedded project scenes load unchanged; saving upgrades them after keeping
an exact `.v1.bak`, `.v2.bak`, or `.v3.bak`. Save publishes assets before atomically
replacing the scene. A failed save may leave unused asset files, while the previous
scene stays usable. Assets are not automatically deleted, including after undo or
sprite removal. Disk-wide asset browsing, cleanup, and multiple scenes are future work.

The **Assets** panel previews unique sprites from the loaded scene and imports in
this session. Double-click or choose **Add to scene** to create a new object;
**Apply to selected object** preserves its geometry and gameplay role. Both actions
support undo/redo. Sprites remain in the palette after undo/removal until another
scene is opened or created. The palette is capped at 128 sprites and 4 MiB of pixel
data; it does not scan unused files in `assets/`.

Choose **Coin starter** (Ctrl+Shift+N), then **Play** (F5). Move the teal player
around the gray walls and collect all five gold coins. The HUD tracks the score
and announces completion; **Restart** resets the player and coins. Each object has
an editable **Role** in the Inspector: Decoration, Player, Wall, or Coin. Names and
colors do not determine gameplay behavior. Coins use circular visuals and rectangular
collision bounds. This prototype supports static, axis-aligned walls, not a full
physics system; place the player outside walls when editing its start position.

Press **Play** (F5). **WASD/arrows** move the controlled object within
the 1024×576 play area at 240 units/second; diagonals keep the same speed. If the
scene has a Player role, the first Player is controlled; otherwise the selected object or
first object is used. Use **Pause**, **Restart**, **Esc**,
or the editor's **Stop** (Shift+F5). Playback uses the last applied scene snapshot;
unsaved scene edits are included, but unapplied Inspector fields are not.
Playback changes never modify the authored scene. Opening/New/closing the editor
stops its preview process. This data-only preview runs built-in behavior and does
not execute project scripts or claim to sandbox arbitrary Python.

## Development checks

```sh
uv sync --frozen --extra test
uv run --frozen --extra test ruff check src tests scripts
uv run --frozen --extra test ruff format --check src tests scripts
uv run --frozen --extra test mypy
QT_QPA_PLATFORM=offscreen uv run --frozen --extra test pytest -q
```

Offscreen tests do not establish real Wayland/GPU compatibility. Qt Widgets uses
the smaller PySide6 Essentials distribution; optional add-on modules are deferred.

For a repeatable software rendering fixture:

```sh
QT_QPA_PLATFORM=offscreen QT_QPA_PLATFORMTHEME= uv run --frozen python scripts/benchmark_rendering.py --sprites
```

It measures 1,000 moving sprites sharing one transparent 16×16 RGBA texture,
rendered into a 1024×576 image, reporting median/p95 update-and-render time after
warmup. Omit `--sprites` for rectangles. It does not measure many unique textures,
compositor presentation, input latency, or GPU performance.

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
