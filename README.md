# Solar Forge Game Engine

A proposed native Arch Linux desktop engine for making fun, lightweight 2D games.
Python and PySide6 Qt Widgets, aligned with Solar Forge Life Helper and part of the
Solar Forge Studios suite. Local-first and LLM-first, with native Linux exports.

No JavaScript, TypeScript, browser UI, embedded webview, or web export.

Solar Forge combines a clear visual editor, editable game code, and an assistant
that works through inspectable, undoable actions. Manual development and exported
games should work without an AI service.

**Status: native editor, playback and scene scripting.** Create rectangles, select them in the viewport
or scene tree, edit their name/position/size/color, undo/redo, and save/reopen scene
documents. New/Open/Close protect unsaved changes. Play opens a separate native
window with keyboard movement, wall collisions, and coin collection. PNG sprites
and basic project folders are supported. An offline assistant demo supports reviewed
scene edits, and opt-in Ollama supports local models. Single-scene runtime-only exports
and experimental Python/Qt folder bundles include restricted scene-level Python scripts.

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

Save to a `.forge.json` file. Version-eleven files contain the entire scene,
roles, movement/animation settings, sprite pixels, optional collection sound and Python source.
Versions one, two, three, five, seven and nine still load. Before upgrading an older
file, its exact bytes are retained in `<filename>.v<old-version>.bak`. Existing backups are never overwritten;
use Save As if that backup name is occupied. Scene files remain limited to 4 MiB;
embedded sprites count toward that limit. Opening and saving files never execute scripts.

Use **File → Create project from scene…** (Ctrl+Alt+N) and enter a **new folder name**
to save the current applied scene as a project. Existing folders are never replaced.
The project contains `project.json`, `scenes/main.forge.json`, and an `assets/`
directory. **File → Open project…** (Ctrl+Alt+O) selects a project folder. Ordinary
Save updates its scene; Save As writes a standalone scene and leaves project mode.
Opening an existing standalone scene and creating a project copies it without
rewriting the original. The manifest uses a relative scene path; traversal and
symbolic links in that path are rejected on open and rechecked on save.

**Scene → Rename scene title…** changes the active title through an undoable edit.
Save persists it without changing the filename, startup scene, or recovery path.

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

Project saves write version-twelve scene files with relative sprite references to
`assets/<content-hash>.rgba`. Identical sprites share one bounded RGBA pixel file;
files are validated by size, dimensions, and content hash when opened. Move the
entire folder to keep the project portable. Standalone Save As still embeds pixels
in version-eleven scenes, and Play receives resolved data without reading asset paths.
Older embedded scenes and version-four/six/eight/ten project scenes load with defaults
for missing fields; saving preserves an exact version-specific `.bak`. Save publishes assets before atomically
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
Successful Save or Undo back to the saved scene queues background cleanup of a
valid matching snapshot. Explicit Discard requests removal of that scene's snapshot.
Invalid, stale, oversized or unsafe snapshots are retained during autosave and
normal cleanup, with Activity messages. Autosave checks the saved baseline and
rechecks existing snapshot bytes before replacing them; detected external changes
stop the operation. Cleanup shares the recovery worker queue and finishes before
closing. Manual Save remains available after recovery failures. Repair or move a
retained conflicting snapshot before expecting autosave to resume for that scene.
This protects against application crashes; power-loss
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
an animated courier, bobbing energy cores, orbiting reactor sparks and pickup speed
bursts. Press Space while moving for a short dash with a cooldown. A timed finish
awards a title and a spark celebration. WASD/arrows move;
Pause and Restart control playback. All 193 objects are editable, including walls
and 25 animated sprites. Open **Scene → Edit scene script** to explore the commented
effects and tweak their constants.
Create a project from this scene to save your changes.

The [editable example project](examples/ember-run/README.md) also includes **Courier
Bay**, an orbital-collection script playground sharing the same assets. Copy its folder before editing and
use **File → Open project**. The original artwork and scenes total less than 256 KB;
no downloads or model connection are needed. [View the scripted showcase](docs/screenshots/ember-run-scripted.png).

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
stops its preview process. Applied scene scripts run in a separate restricted worker.

## Script your scene

Choose **Scene → Edit scene script…** (Ctrl+Shift+E), then **Insert example** or write
Python. **Apply script** creates one undoable scene edit; press **Play** to run it
and **Save** to keep it. Clearing the source removes the script. The native editor
includes syntax colors, indentation, line navigation, API help and insertion of the
selected object's ID. Opening, editing and saving source never execute it.

```python
def on_start(game):
    game.set_speed(300)
    game.data["elapsed"] = 0
    game.say("Collect all the coins!")


def on_update(game, dt):
    game.data["elapsed"] += dt
    if game.total_coins and game.collected == game.total_coins:
        game.say("All collected!")
```

`on_start(game)` runs once per Play/Restart. `on_update(game, dt)` runs before each
fixed simulation step (`dt = 1/60`). Read `game.player` (ID, position, speed),
`game.objects[id]` (ID, name, position, size, role), `game.input["x"]` / `["y"]`
(movement axes −1, 0, 1), `game.time`, `game.collected` and `game.total_coins`.
`game.set_position(id, x, y)` moves existing objects, `game.set_speed(value)` changes
player speed, and `game.say(text)` shows up to 200 plain-text characters. Player
positions stay inside the arena; teleporting does not resolve wall overlaps.
Changing state dictionaries alone has no gameplay effect. `game.data` and globals
persist until Restart; `math` and `random` are available. `print()` appears in Activity.

`game.actions["dash"]` exposes three booleans for Space: `held` is its current state,
`pressed` and `released` report transitions since the previous update request. Edges
are consumed once when a callback is dispatched, including input received while the
worker is busy. A quick tap can report both edges with `held=False`; multiple taps
between requests coalesce. Native key repeats are ignored. The startup callback
receives neutral input. These snapshots grant no device access and do not change
gameplay by themselves: your script defines what a dash does. For example:

```python
def on_update(game, dt):
    if game.actions["dash"]["pressed"]:
        game.say("Space pressed!")
```

The first action is fixed to Space, independently of WASD/arrows movement presets.
Custom action names and rebinding are not implemented. Pause, focus loss, script
failure, Restart and closing clear held keys and pending edges without synthesizing
release events. Press again after resuming; a held key's repeats do not reactivate it.

Select an object and choose **Scene → Edit selected object behavior** (Ctrl+Shift+B), or
use its Inspector **Object behavior…** button. Attach a name such as `drift` and numeric
parameters such as `speed = 20`. Define its callbacks in the scene script:

```python
def drift_start(game, instance):
    instance.data["x"] = game.objects[instance.id]["x"]


def drift_update(game, instance, dt):
    instance.data["x"] += instance.parameters["speed"] * dt
    obj = game.objects[instance.id]
    game.set_position(instance.id, instance.data["x"], obj["y"])
```

Each attached object gets its own `instance.data` and copied `instance.parameters`;
`instance.id` identifies that object. Duplicate an object to reuse the rule with
fresh runtime state, then tune its parameters independently. Restart clears instance
state. Globals and `game.data` remain shared across the scene.

Scene callbacks run first, followed by object callbacks in saved draw order. Each
step shares one snapshot and command budget; commands apply together after all
callbacks succeed. The last command for a property wins. Any callback error stops
scripted Play and identifies the behavior, object ID and source line.

Attachments support one name and up to sixteen finite numeric parameters per object,
with at most 32 attached objects per scene. Parameter names must be identifiers;
values range from −100,000 to 100,000. At least one named callback must be callable
when Play starts. Apply supports undo/redo and rejects stale revisions. Detach all
behaviors before clearing scene source. Standalone format 13 and project format 14
preserve attachments without executing source; older scenes load detached with exact
upgrade backups. Courier Bay demonstrates two independently tuned `bob` instances.
See the [behavior contract](docs/architecture/0003-object-behaviors.md).

Errors stop scripted Play. Activity shows the failing scene and source line when
available; **Edit failed script…** opens that line directly. Apply the fix, Stop the
old preview and press Play again. Navigation disables if the scene or applied source
changed; run Play again for a current error. Exported games report errors without
editor navigation.

**Close · keep draft** retains unapplied text, cursor and text undo history when you
reopen the same scene's script editor, including through error navigation. A draft's
lines may have shifted from the applied source that failed. Drafts are temporary:
applying, opening another document's script editor or closing the editor releases
them. Save persists only applied source. If the scene revision changed, Apply keeps
the draft and refuses to overwrite it. Copy any text you want to keep before choosing
**Reload applied source**, which explicitly replaces the draft with current source.

Pause/focus loss suspend simulation and discard commands from an update that was
in flight when suspension occurred, even if you resume before it finishes. That
callback can still change its worker-local `game.data` and globals.
Restart resets script and game state. Stop/closing terminate the worker. Runtime
changes never alter authored objects. Both export formats include the script and
run without the editor or an AI service.

The first version supports one embedded scene script, up to 32 KiB UTF-8 source,
256 objects, 32 commands and 4 KiB log output per lifecycle step (scene plus object
callbacks). It requires Linux x86_64 and `libseccomp` (`sudo pacman -S libseccomp` on Arch; included in Docker images).
A default-deny kernel policy blocks files, sockets, subprocesses and threads before
source is sent. Missing isolation stops scripting; there is no unrestricted fallback.
Workers receive no editor credentials or project paths and cannot load new packages
from disk. Limits are 256 MiB address space, 60 CPU seconds per Play session, 3 seconds
to initialize isolation, 1 second for startup code and 250 ms per update. These are
termination limits, not frame-time guarantees. External Python modules, runtime
attachment changes, breakpoints and runtime scene transitions remain future work.
See the [isolation decision](docs/architecture/0002-script-sandbox.md) for boundary tests
and limitations.

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
warmup, plus initial canvas construction time. Add `--unique-textures 1000` to
exercise 1,000 distinct textures; counts are bounded to 1–1,000. Omit `--sprites`
for rectangles. These are software measurements, not compositor presentation,
input latency, or GPU performance.

Measure warm startup on your Wayland desktop with isolated temporary preferences:

```sh
QT_QPA_PLATFORM=wayland QT_QPA_PLATFORMTHEME= uv run --frozen python scripts/benchmark_startup.py --samples 5
QT_QPA_PLATFORM=wayland QT_QPA_PLATFORMTHEME= uv run --frozen python scripts/benchmark_startup.py --samples 5 --showcase
```

Each sample starts a fresh process and reports launch-to-first-Qt-paint time and
RSS after startup workers settle. No models are loaded. Samples are bounded to
1–10; use `QT_QPA_PLATFORM=offscreen` for headless/Docker checks. This does not
measure a cold filesystem cache or first compositor-presented frame. See the
[recorded reference measurements](docs/performance/2026-10-05.json).

Measure the native viewport's paint cadence and synthetic mouse response:

```sh
QT_QPA_PLATFORM=wayland QT_QPA_PLATFORMTHEME= uv run --frozen python scripts/benchmark_native.py --unique-textures 1000
```

Keep the temporary benchmark window visible until it closes (normally a few
seconds; 15-second limit). It uses the same 1,000-sprite fixture, 10 warmup/120
measured paints and 5 warmup/50 measured clicks. Reports separate update CPU,
paint CPU, queued paint delay, completion intervals and Qt-posted click response,
along with actual viewport dimensions, scaling and screen refresh rate.
`--unique-textures 1` compares shared sprites; offscreen mode checks tooling only.
Synthetic clicks exclude hardware input, compositor delivery and Inspector refresh.
Qt paint completion does not establish when pixels reach the screen. The
[native reference report](docs/performance/2026-10-05-native.json) retains those limits.

For profiling, vary `--moving-items` from 1 to 1,000 and compare
`--viewport-update minimal`, `bounding`, `smart`, or `full`. `--scene-index bsp`
or `none` compares scene indexing. Updates now use Qt's automatic dirty regions;
`--force-repaint` reproduces the earlier full-viewport request on every update.
Reports include these settings so results remain comparable. The
[repaint-policy comparison](docs/performance/2026-10-05-repaint-policies.json)
shows why engine defaults still use minimal updates: full repainting helps heavy
motion but increases work for ordinary one-object updates. These switches affect
only the benchmark, not your projects or editor preferences.

Benchmark the real Play window's animation workload:

```sh
QT_QPA_PLATFORM=wayland QT_QPA_PLATFORMTHEME= uv run --frozen python scripts/benchmark_play.py --animated-items 1000
```

Keep this temporary window visible and focused. It uses actual fixed-step movement,
sprite-sheet playback and one controlled player; the fixture has 1,000 sprites.
`--animated-items` accepts 0–1,000; `--viewport-update minimal` or `full` compares
forced policies against the default `auto`. Play automatically uses full redraw
after 1,000 frame changes accumulate before a paint, preserving minimal updates
for sparse animation. The editor's redraw policy is unchanged. Reports verify
changing animation frames and unchanged authored data; the
[Play animation comparison](docs/performance/2026-10-05-play-animation.json)
records observed improvements and the remaining cadence/presentation limits.

Manual Save now publishes through a worker while Qt continues processing events.
Editing is disabled until the write finishes, and closing waits for that operation.
A saved document changed or removed externally is preserved; Save fails with your
edits retained, and Save As can keep them in a separate file. A second byte revision
check precedes atomic replacement. New targets publish exclusively. Regular-file
reads reject symbolic links/FIFOs and stay bounded. File and directory flushes improve
publication durability. A nonblocking folder lock coordinates engine scene writers
through publication without creating lock sidecars; competing saves keep your edits
and report that you can retry. Locks release when the writer exits. This targets
local Linux filesystems; arbitrary tools can ignore advisory locks, and network
filesystem, manifest, asset-directory and full power-loss guarantees remain open.
New sprite files and their directory entries flush before the scene is published;
sprite reads reject links and FIFOs without waiting on them.
Reused sprite entries and migration-backup entries also flush before scene replacement;
a failed migration-backup flush preserves the original scene.
Recovery publication and cleanup use the same folder guard; new snapshots publish
exclusively, existing snapshots carry a final byte-revision check, and deletion
flushes its directory. Multi-session ownership of recovery snapshots remains open.
Project manifests use the same safe reader. Startup updates coordinate publication
and check byte revisions; new project metadata flushes its root and parent before
creation succeeds.
Manual Save retries brief publication contention in its worker while keeping the
original byte revision, so recovery cleanup can finish without dropping external-edit
protection. Other write errors still preserve your edits and report the failure.
Activity and error dialogs display project text literally, preserving HTML-like
names without treating them as formatting or image references.

## Native game export

Choose **File → Export active scene as game…**. Select **Lightweight game** for a
new `.pyz`, or **Linux bundle with Python and Qt** for a `.tar.gz`. Export
uses the currently applied scene, including built-in gameplay, sprites, animation
and collection sound. It runs in a worker, retains your unsaved edits, and keeps
the captured snapshot even if you edit afterward. Existing output files are never
overwritten; choose a new filename for a new build.

The archive contains only engine core/runtime code and bounded scene data. It runs
without the editor, assistant, project folder or Docker. It needs **Python 3.14**,
**PySide6-Essentials 6.11.2** and the native Linux Qt libraries; PipeWire is optional
for sound. The lightweight archive leaves these dependencies installed separately; the
folder bundle below carries Python and the Qt Widgets subset. Qt's native extension modules stay outside the zip archive, as described in
[Python's zipapp documentation](https://docs.python.org/3.14/library/zipapp.html).

```sh
# Use an interpreter with the supported Qt package installed
python3.14 -I Game.pyz

# Brief native compatibility check: exercise movement, print a report, then close
python3.14 -I Game.pyz --smoke-check
```

The executable archive also supports `./Game.pyz` when `python3` resolves to the
supported environment. Its launcher uses Python isolated mode, ignoring project
imports and Python environment overrides. Export includes one scene and the built-in
behaviors plus its Python scene script. Runtime scene transitions remain unimplemented.

The **Linux bundle with Python and Qt** option builds a compressed `Game` folder.
Extract the complete folder, then run `./play`. It works after moving or renaming
the folder, including paths containing spaces. No system Python, pip, uv, editor,
or model service is required. It retains system graphics/font dependencies; its
README lists Arch prerequisites, and optional sound still uses system PipeWire.
`./play --smoke-check` exercises movement, presses/releases Space for scripted games
and exits automatically.

Bundle construction stays in the export worker and uses the applied scene captured
at export start. Existing targets are never overwritten, and handled build failures
remove their temporary files. The archive contains file hashes, runtime versions,
external Qt library names, the engine MIT license, installed Python license text
and Qt package metadata. It excludes development packages, user site packages and
editor/assistant code. The launcher disables Python environment overrides, site
customizations and bytecode writes; this is import isolation, not a script sandbox.

Bundles are currently experimental/private: the complete third-party notice and
corresponding-source audit remains open. Interpreter builds can contain additional
embedded libraries; copying their installed license file alone does not complete
that audit. Native Wayland and clean Arch offscreen playback passed on x86_64.
Other architectures, X11 and other Linux distributions are not verified.

Repeat the clean Arch acceptance check with Docker installed (build steps need
network access; execution is offline). Choose a new temporary output directory:

```sh
docker build -f Dockerfile.export-check -t solar-forge-arch-export-check:dev .
export_check_dir=$(mktemp -d /tmp/solar-forge-export.XXXXXX)
.venv/bin/python scripts/validate_bundle.py build-fixture "$export_check_dir"
.venv/bin/python scripts/validate_bundle.py check "$export_check_dir"
# Optional native presentation check; forwards only the current Wayland socket
.venv/bin/python scripts/validate_bundle.py check "$export_check_dir" --qpa wayland
```

The fixture deliberately moves the extracted game into a path containing spaces.
The check mounts only that game read-only, verifies no system Python/Qt is installed,
disables networking and plays a short scripted collection route.
The [scripted acceptance report](docs/performance/2026-10-06-script-runtime.json) records
successful offscreen and Wayland runs. Temporary output is retained
for inspection. The [reference report](docs/performance/2026-10-06-native-bundle.json)
records the image identity, sizes and successful native/Docker-produced exports.
Image builds use a pinned Arch base and resolve Arch packages at build time.

The [CI workflow](.github/workflows/checks.yml) runs on pushes and pull requests:
Ruff, formatting, mypy and pytest in the independent frozen test image, followed by
bundle creation in that same image and clean Arch offscreen playback. Checkout uses
shell/git without Node-based actions, with a read-only token scoped to fetching the
exact tested revision. Container checks run without host display or credentials.
GitHub-hosted execution remains unverified until the branch is pushed.

For the dependency-packaging spike, run the offline developer probe:

```sh
.venv/bin/python scripts/probe_runtime_package.py
.venv/bin/python scripts/probe_runtime_package.py --qpa wayland
```

It copies a Widgets-only Qt subset into a temporary Python environment and exercises
an exported game without an installed engine. It prints sizes, external libraries
and gameplay results, then removes the environment. It needs the frozen dependencies
and installed Wayland libraries even for its offscreen check. This is a measurement
tool, not a distributable bundle; see the [packaging decision](docs/architecture/0001-runtime-packaging.md).

## Project sounds

Open a project, then choose **Scene → Project sounds…**. Import WAV clips, select
one to preview, and use Stop to interrupt playback. Selection changes and closing
also stop playback. Import and validation run in workers. Importing clips leaves scenes and undo history
unchanged; **Use for coin collection** assigns a clip through a validated undoable edit. Clips are copied into `audio/` with readable names and content hashes,
deduplicated and kept portable when the project moves. Source metadata is stripped.

Supported clips: uncompressed PCM WAV, mono/stereo, 8/16 bit, 8–48 kHz, up to
30 seconds and 4 MiB per file. The library allows 128 clips / 32 MiB. Unsafe paths,
malformed files and changed fingerprints are rejected without overwriting files.
Import is a library operation, not an undoable scene edit; library renaming/deletion
are not implemented yet. Audio files are outside sprite cleanup.
Concurrent external editing of the audio directory is not supported.

Each scene can use one collection sound. The dialog shows its duration and lets you
replace/remove it; **Scene → Remove collection sound** also works for standalone scenes.
Assignment/removal supports undo/redo and rejects expired scene revisions. The assigned
PCM is embedded in standalone format 13 and project format 14 within the existing
4 MiB scene limit; source/library paths are not needed by Play or standalone copies.
Earlier scenes load silently and upgrades preserve exact versioned backups.

Play uses one optional voice at 25% volume. Collecting coins triggers that sound once
per collection batch; overlapping events share the active voice. Pause, focus loss,
Restart and closing stop it; Restart makes coins collectable again. Missing PipeWire
is shown in the game status without preventing play. No inference or project code
runs during audio playback.

Native preview uses `/usr/bin/pw-play` from Arch's `pipewire-audio` package and an
active user PipeWire session. Validated PCM samples go over stdin at 25% volume;
source paths are never passed to the player. No Qt multimedia add-ons are needed.
Import remains available when playback is unavailable, with errors shown in the dialog.

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

Audio forwarding is optional. With PipeWire running, use the specific socket override:

```sh
docker compose -f compose.yaml -f compose.audio.yaml up --build desktop
```

The override mounts only `$XDG_RUNTIME_DIR/pipewire-0`; match the image UID/GID to
the host. Images include the PipeWire client; the default desktop configuration
has no audio socket and reports preview unavailable. Neither configuration adds
network access. The headless test image needs no audio session or socket.

Run lint, formatting, type checks and tests in the independent headless image:

```sh
docker compose -f compose.test.yaml run --build --rm test
```

The test service has no display mount, user project volume, or network access.
Its configuration works without a Wayland session. Native Wayland and script isolation
checks also pass; broad compositor/GPU compatibility remains open.

- [Product and implementation plan](docs/ENGINE_PLAN.md)
- [Instructions for coding agents](AGENTS.md)

The native Python desktop direction is fixed. Runtime rendering performance,
packaging, and sandboxing still need their planned validation milestones.
The [script isolation decision](docs/architecture/0002-script-sandbox.md) records the
implemented kernel policy, native/Docker checks and remaining security limitations.

## License

Engine and runtime code are available under the [MIT license](LICENSE).
Python, Qt/PySide6 and other dependencies retain their own licenses. Exporting
a game does not assign a license to imported content or game assets.
