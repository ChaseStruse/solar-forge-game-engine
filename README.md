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
and basic project folders are supported. An offline assistant demo supports reviewed
scene edits; real model adapters, sandboxed Python scripts, and exports follow later.

## Run on Linux

Use Python 3.14 and uv:

```sh
uv sync --frozen
uv run --frozen solar-forge-engine
```

Choose **Add rectangle**, edit the **Inspector**, and press **Apply changes**.
Drag an object in the viewport to move it. The preview leaves scene data unchanged
until release, which creates one undo step and updates the Inspector. **Esc** cancels;
changing focus or refreshing the scene also cancels an unfinished drag. Clicks alone
do not move objects. Dragging supports rectangles, coins and sprites, one object at a time.

Use **Snap to grid** (Ctrl+Shift+G) and **Grid spacing** in the viewport toolbar
for nearest-grid positioning. Spacing is 1–256 scene units (default 16); snapping
starts disabled. The visible grid applies only to dragging, leaving typed Inspector
positions unchanged. Grid preferences are session-only. **Ctrl+wheel** zooms around the pointer;
**Zoom in/out** (Ctrl+= / Ctrl+-) zoom around the viewport center, and **100%**
(Ctrl+0) restores actual size. Manual zoom ranges from 0.1% to 800%. Drag with the
middle mouse button to pan; the plain wheel scrolls. **Fit scene** (F) frames the
play area and authored objects, including those outside the arena. Navigation
cancels unfinished object drags and never changes scene data or undo history.
Zoom and pan are session-only. The Inspector groups controls into **Object**,
**Transform**, **Appearance**, and **Movement**. Scroll its properties in smaller
windows; **Apply changes** stays visible below them. Fields wrap in narrow docks.

Use **Scene → Draw order** to **Bring forward**, **Send backward**, **Bring to
front**, or **Send to back**. Ctrl+PageUp/PageDown moves one step; add Shift to
move directly to the front/back. The Scene list runs from back to front, and the
Inspector shows the selected object's position. Objects at the front draw over
earlier objects and receive overlapping clicks first. Order changes support undo,
redo and save/reopen; Play uses the same order. Search filters do not limit ordering
to matching objects, and viewport drag locks still allow deliberate order changes.

Select an object and choose **Duplicate object** (Ctrl+D) to create a selected copy
24 units to the right and down. Copies preserve size, color and gameplay role,
use a new ID, and support undo/redo. Duplication uses applied properties.

Choose **Import PNG** (Ctrl+Shift+I) to add a sprite. PNGs must be at most
256×256 pixels and 2 MiB. Transparent pixels are preserved; width and height in the
Inspector control its displayed size. Imported pixels are copied into game data,
so moving/deleting the original image does not affect playback. **Remove sprite**
restores geometric rendering and can be undone. Sprite color is not tinted;
role and rectangular collision bounds still determine gameplay.

The **Assets** panel shows thumbnail entries with names and pixel dimensions.
Use its search field to filter by name or size (case-insensitive), or press
**Ctrl+Alt+L** to focus it. A matching count and clear button help navigate the
palette. Filtering changes only the list; hidden selections cannot be added or
applied accidentally. The filter stays active during imports, undo and project
asset scans; clear it to see the complete palette.

To animate an imported PNG sheet, select its object, enable **Loop sprite sheet in
Play**, and set **Frame columns**, **Frame rows**, and **Frames/second**, then apply.
Frames must be equal-sized cells that divide the full image evenly. Sheets remain
limited to 256×256 pixels; animations allow at most 256 frames and 1–60 frames/second.
All cells loop from left to right, then top to bottom. The editor displays the first
frame; Play animates every visible configured sprite. Pause and focus loss freeze
animation; Restart returns it to the first frame. Authored size and rectangular
collision bounds stay unchanged, so adjust Width/Height for the desired frame size.
Animation settings support undo, duplication and portable project/standalone saves.
Removing or replacing a sprite clears its animation settings in the same undoable
edit. Named clips, partial-sheet sequences and one-shot animations remain future work.

Save to a `.forge.json` file. Version-seven files contain the entire scene,
roles, movement/animation settings, and optional sprite pixels. Versions one, two,
three and five still load. Before upgrading an older file, its exact bytes are retained
in `<filename>.v<old-version>.bak`. Existing backups are never overwritten;
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

The **Project scenes** panel lists up to 128 top-level scene files. **New project
scene** creates an empty named scene without overwriting an existing file. Names
use 1–64 letters, digits, spaces, underscores or hyphens, starting with a letter or
digit. Double-click a scene or choose **Open selected scene** to switch; unsaved
changes offer Save/Discard/Cancel. Invalid targets leave the current scene intact.
Save and recovery apply to the active scene; switching stops Play and resets the
current undo history and sprite palette. **Refresh scenes** picks up files added
outside the editor. Select a saved scene and choose **Set selected as startup scene**
to make it open when the project is reopened. The panel displays the current startup
scene; scroll the panel to reach its controls in smaller windows. This validates
saved scene data and sprite references in a worker, then atomically updates
`project.json`. It keeps the active scene, unsaved edits, undo history and Play
snapshot unchanged. It uses the selected scene's saved bytes, rather than unapplied
or unsaved edits. **Refresh scenes** reloads externally changed settings; stale,
invalid or failed updates leave the manifest intact. Startup selection is a project
setting outside scene undo/redo. Ordinary scene switching still leaves that setting
unchanged and does not introduce runtime scene transitions.

Project saves write version-eight scene files with relative sprite references to
`assets/<content-hash>.rgba`. Identical sprites share one bounded RGBA pixel file;
files are validated by size, dimensions, and content hash when opened. Move the
entire folder to keep the project portable. Standalone Save As still embeds pixels
in version-seven scenes, and Play receives resolved data without reading asset paths.
Older embedded scenes and version-four/six project scenes load with default movement
settings; saving upgrades them after keeping an exact version-specific `.bak`. Save publishes assets before atomically
replacing the scene. A failed save may leave unused asset files, while the previous
scene stays usable. Assets are not automatically deleted, including after undo or
sprite removal. Reviewed cleanup is available below.

The **Assets** panel previews unique sprites from the loaded scene, session imports,
and other saved project scenes. Project open/switch starts a background scan;
**Refresh project assets** rescans after external changes. Double-click or choose **Add to scene** to create a new object;
**Apply to selected object** preserves its geometry and gameplay role. Both actions
support undo/redo. Sprites remain in the palette after undo/removal until another
scene is opened or created. The palette is capped at 128 sprites and 4 MiB of pixel
data. Indexing reads up to 16 MiB of saved scene files using the existing bounded
scene/asset validators; malformed scenes are skipped with Activity messages.
Unused files, backups, and recovery snapshots are not catalog sources. Scan results
from a previously opened project cannot populate the current project palette.

Choose **Review unused assets** after saving to scan for unused project sprite files
in a worker. The review shows the count and size; **Show Details** lists filenames.
Confirmation moves them into `.asset-quarantine/<id>/`; cancellation leaves them alone.
Saved scenes, upgrade backups, recovery snapshots, and current undo/redo and palette
sprites are protected. The scan checks at most 512 files/directories and 32 MiB;
invalid, unknown, symlinked, or unreadable entries stop cleanup. The worker rechecks
file contents and references before moving anything and rolls back handled move failures.
Choose **Browse quarantined assets** in the scrollable Assets panel, select a file,
and choose **Restore selected asset** to return its exact bytes to `assets/`.
The browser shows batch paths and byte sizes; **Refresh quarantine** picks up external
changes. Scanning and restoration run in workers with the same 512-entry / 32 MiB
scan limits. Unknown entries, symbolic links and invalid/oversized RGBA files stop
scans. A changed file requires a fresh review, and any existing target blocks restore,
even if its bytes match. Scene data and undo history remain unchanged. Restored unused
files do not automatically appear in the sprite palette, which indexes saved scenes.

To reclaim space, select one file and choose **Review permanent deletion…**. A
worker rescans quarantine within its existing limits. The confirmation shows its
path and byte size, offers its SHA-256 in Details, and defaults to **No**. Confirming
permanently removes only that quarantine file after another content check; there
is no undo. Changed files require refreshing and reviewing again. Empty batch
folders remain. Concurrent external editing during deletion is not supported.

If removing the quarantined copy fails after restoration, both copies remain.
Raw files carry no image dimensions; restoration preserves their bytes, while project loading still
validates sprite dimensions and content hashes. Concurrent-edit and power-loss
guarantees remain future work.

Project edits automatically produce a recovery snapshot after two seconds without
another applied edit. Serialization and writing run in a worker; the normal scene
and asset files are untouched. Only one snapshot is retained per scene, capped at
4 MiB with embedded pixels, so recovery does not depend on newly imported assets
having been saved. Unapplied Inspector fields and standalone scenes are not autosaved.

On reopening a project, choose **Recover edits**, **Discard snapshot**, or **Open
saved scene**. Recover creates an undoable edit and remains unsaved until **Save**.
Successful Save, explicit Discard, or Undo back to the saved scene clears recovery.
Invalid or stale snapshots are retained and reported in Activity instead of
replacing saved work. This protects against application crashes; power-loss
persistence and concurrent editing from multiple engine instances are not guaranteed.

The native editor's solarpunk welcome screen pairs black surfaces with leaf green,
mint and solar gold. It offers direct actions to explore
the demo, create an object, or open a project. Scene and Project Scenes share tabs;
the Inspector and Assistant remain beside the viewport. Panels can be moved or
floated. One compact toolbar keeps frequent actions visible; creation, duplication,
deletion and zoom commands remain in menus with keyboard shortcuts. Grid spacing
appears when snapping is enabled. [Preview the workspace](docs/screenshots/editor-workshop.png).

Use the **Scene** panel's search to find objects by name or ID, with an optional
**Role** filter. Search ignores letter case and combines with the role choice.
**Ctrl+L** opens the Scene panel and focuses search. The count shows matching and
total objects. Filtering affects only the list; it leaves viewport objects,
selection, Inspector edits and the game unchanged. A selected object outside the
filter is identified below the list. Clear search and choose **All roles** to see
everything again. Filters stay active across scene changes during this session.

Select an object and enable **Lock viewport dragging** in the Inspector, or press
**Ctrl+Shift+L**. The Scene list marks it **Locked**. Locked objects remain
selectable; deliberate Inspector and assistant edits still work. From the Scene
menu, **Lock decorations against dragging** protects backgrounds in one step and
**Unlock all viewport dragging** clears every lock. Changing locks cancels an
in-progress drag without moving the object and preserves unapplied Inspector fields.
Locks create no undo step and do not change scene files or Play. They survive
undo/redo and automatically save in the background for each saved scene. Reopening
or switching scenes restores its locks; an unsaved scene carries its locks into
its first save, and Save As carries them to the new scene.

Settings live under `$XDG_CONFIG_HOME/solar-forge-engine/scene-locks` (normally
`~/.config/solar-forge-engine/scene-locks`), keyed by the absolute scene path.
Docker uses its existing preferences volume. These are personal settings: moving
or copying a project outside Save As does not carry its locks. Invalid settings
and detected external changes are preserved, with a warning in Activity; locks
remain usable in memory. Repair the settings and reopen the scene to resume saving.

Try **Forge showcase** (Ctrl+Shift+F), then **Play** (F5), to explore **Ember Run**:
an animated courier, flickering reactor, industrial pixel art, and twelve energy
cores to recover. WASD/arrows move; Pause and Restart control playback. All 187
objects are editable, including collision walls and 19 animated sprites.
Create a project from this scene to save your changes.

The [editable example project](examples/ember-run/README.md) also includes **Courier
Bay**, a second scene sharing the same assets. Copy its folder before editing and
use **File → Open project**. The original artwork and scenes total less than 256 KB;
no downloads or model connection are needed. [View the showcase](docs/screenshots/ember-run.png).

Choose **File → Coin starter** (Ctrl+Shift+N), then **Play** (F5). Move the teal player
around the gray walls and collect all five gold coins. The HUD tracks the score
and announces completion; **Restart** resets the player and coins. Each object has
an editable **Role** in the Inspector: Decoration, Player, Wall, or Coin. Names and
colors do not determine gameplay behavior. Coins use circular visuals and rectangular
collision bounds. This prototype supports static, axis-aligned walls, not a full
physics system; place the player outside walls when editing its start position.

Set **Movement speed** (0–2,000 units/second) and **Movement keys** (WASD, arrows,
or both) in the Inspector, then **Apply changes**. These settings are undoable,
copied by duplication, and saved with the object. Zero speed disables movement;
existing scenes default to 240 units/second with both key sets. Settings affect the
controlled object in Play; they do not make every object move automatically.

Press **Play** (F5). The selected movement keys move the controlled object within
the 1024×576 play area; diagonals keep the same speed. If the
scene has a Player role, the first Player is controlled; otherwise the selected object or
first object is used. Use **Pause**, **Restart**, **Esc**,
or the editor's **Stop** (Shift+F5). Playback uses the last applied scene snapshot;
unsaved scene edits are included, but unapplied Inspector fields are not.
Playback changes never modify the authored scene. Opening/New/closing the editor
stops its preview process. This data-only preview runs built-in behavior and does
not execute project scripts or claim to sandbox arbitrary Python.

## Assistant and local models

Open the **Assistant** tab beside the Inspector; scroll, resize or undock the panel
to see its review controls. By default it uses a deterministic offline fixture, **not an LLM**.
No model, credentials or networking are required. Enter a supported request and
choose **Propose edits**:

- `add rectangle` or `add coin`
- `move selected to 200 150`
- `rename selected Hero`
- `color selected #33aa88`
- `speed selected 120`
- `delete selected`

Separate requests with semicolons for a batch. Selected-object requests use the
object selected when generation starts. Review the explicit property changes and
IDs, then **Apply reviewed edits** or **Discard / cancel proposal**. Generation
never edits the scene. Apply creates one atomic undo step; Save persists the result.
Any scene edit, Undo/Redo, or replaced document invalidates the proposal. Selection
changes alone do not retarget it. Unsupported requests show an error without edits.

Requests are capped at 2,000 characters; responses at 16 KiB and 16 commands.
Only creation, deletion and the listed scene properties are exposed. Script,
filesystem, sprite/animation and arbitrary-code tools are unavailable. Proposals
run in a worker. The demo discards canceled results; the Ollama adapter also closes
the waiting request socket. Model output never runs code or directly modifies files.

For natural-language proposals, choose **Ollama · loopback** in the Assistant tab,
enter your installed model name and local server address, and choose a deadline
(1–120 seconds; default 60). Nothing connects until you press **Propose edits**.
Use **Refresh installed models** to populate the editable model picker. Discovery
contacts only the configured server and sends no scene context; cloud-named entries
and advertised remote aliases are excluded. It neither downloads nor loads models.
You can also type a model name. **Check model capabilities** queries
[Ollama model metadata](https://github.com/ollama/ollama/blob/main/docs/api.md#show-model-information)
without generating a proposal or sending scene data. It reports available
capabilities and the model's advertised context length when present; that length
does not establish the server's active context budget or guarantee a correct proposal.
Every generation repeats the check: missing/invalid metadata, remote aliases and
models without text completion are rejected before scene data is sent. Preflight
and inference share the configured deadline. Embedding-only models cannot edit scenes.

Choose **Save local connection** to remember the endpoint, model and deadline in
`$XDG_CONFIG_HOME/solar-forge-engine/assistant.json` (normally under `~/.config`).
Preferences load in the background; startup remains **Offline demo**, without an
automatic connection. Invalid preferences show an error and preserve default
settings and the original file. Saving preferences does not save or change a game
project. Discovery and preference reads/writes run off the UI thread.
Start your own Ollama server with cloud disabled:

```sh
OLLAMA_NO_CLOUD=1 ollama serve
```

Use a model already installed locally; the engine does not download models or
manage Ollama services. If Ollama is managed as a service, configure that service
instead of starting a second server. Ollama documents cloud disabling in its
[FAQ](https://docs.ollama.com/faq#how-do-i-disable-ollama-cloud-features).
The engine accepts HTTP loopback addresses only, bypasses environment proxies,
rejects redirects and model names containing `cloud`, and does not fall back to
another provider. Your Ollama server must be configured for offline inference;
the editor cannot control a server's upstream connections or custom model aliases.

Requests use Ollama's [structured chat API](https://docs.ollama.com/api/chat).
Only object metadata is supplied: no pixels, project paths or file contents.
Context includes up to 128 objects within 32 KiB, prioritizing the selected object
and gameplay roles; omitted objects are reported to the model. Responses have a
64 KiB HTTP envelope cap and the existing 16 KiB proposal cap. Invalid, incomplete,
late or stale proposals leave the scene unchanged. Cancellation closes the client
connection; it does not guarantee immediate release of server-side inference resources.

Native launching can reach host Ollama directly. Default Docker networking remains
disabled. On Linux, opt into the host network namespace to reach host loopback:

```sh
docker compose -f compose.yaml -f compose.ollama.yaml up --build desktop
```

The test container stays isolated and uses temporary loopback HTTP fixtures, with
no model downloads. Live inference was verified with the installed `granite4.1:3b`
model on a temporary cloud-disabled Ollama 0.33.3 server: reviewed edits and Undo
worked for a small scene and the Ember Run showcase. The temporary server was
stopped afterward; normal launching still requires your own Ollama server.
Docker stores saved settings in its
`preferences` volume, separately from the `projects` volume. Enterprise adapters
remain future work.

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
