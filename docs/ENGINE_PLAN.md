# Solar Forge Game Engine — product and implementation plan

Status: playable native prototype, updated October 5, 2026. Implemented features
include native scene editing and playback, Docker workflows, duplication, PNG
sprites, project-relative assets and sprite reuse, autosave/recovery, multiple scenes,
startup-scene selection, asset quarantine/restoration, movement/input settings,
viewport drag/snap/zoom/pan, sprite-sheet animation, an offline assistant demo and
an opt-in loopback Ollama adapter with reviewed scene edits.
The Scene panel also supports case-insensitive name/ID search and combined role
filtering, with matching counts and Ctrl+L focus. Filters affect only the object
list: authoring, viewport visibility and selection remain intact. Selected objects
outside the filter retain their Inspector and receive an explicit hint. Filters
refresh after command edits and undo/redo and persist within the editor session.
Verification: 184 tests pass locally (11.76 seconds) and in Docker (13.95 seconds),
with Ruff, formatting and strict mypy passing. Native Wayland search, role filters,
selection preservation and Ctrl+L focus were verified.
Viewport locks now prevent accidental object dragging while keeping
selection, Inspector edits and reviewed assistant commands available. Inspector
and Ctrl+Shift+L controls synchronize with Scene-list lock markers. Bulk decoration
locking and unlock-all live in the Scene menu. Lock changes cancel drag previews,
guard against late commits, and preserve unapplied Inspector fields. Locks are not
game data or undo steps; they survive undo/redo. Per-scene locks automatically
persist in user-local preferences, keyed by the absolute scene path, and restore
when reopening or switching scenes. First save and Save As carry current locks;
external project moves do not carry these personal settings. Serialized background
I/O merges edits made during loading and flushes pending settings before closing.
Bounded regular-file validation preserves corrupt metadata and detected external
changes, reporting failures in Activity rather than overwriting them. Docker uses
the existing preferences volume; runtime scene files and exports remain unchanged.
Lock verification: 192 tests pass locally (14.81 seconds) and in Docker (17.23 seconds).
Ruff, formatting and strict mypy pass. Native Wayland persistence, reopening,
unlocking and unchanged scene bytes were verified, alongside previous drag checks.
The Ember Run showcase adds original pixel art, 187 editable objects, 19 animated
sprites and a twelve-core collection route. Its portable example includes a second
scene sharing assets; the built-in template is accessible in native and Docker builds.
Quarantine now supports reviewed permanent deletion of one selected file. A bounded
worker rescan precedes default-No confirmation with path, size and fingerprint;
a second content check precedes unlink. Cancellation, changed files and failures
leave other assets and scene data untouched. Empty batch folders remain, and
concurrent external editing and power-loss guarantees are still unsupported.
Purge verification: 200 tests pass locally (15.20 seconds) and in Docker (17.79 seconds).
Ruff, formatting and strict mypy pass. Native Wayland confirmation, default No,
cancellation and deletion of an isolated temporary file were verified.
The architecture and release milestones below remain planned work; unmeasured
performance budgets remain targets.

Explicit draw-order controls now move selected objects forward/backward or directly
to the front/back through validated, revision-checked commands. Scene tuple order
remains the persisted back-to-front order; no format bump or migration is needed.
Editor and Play assign matching draw indices, including overlapping hit testing.
Scene-menu shortcuts and Inspector position hints follow selection and boundary
availability. Ordering preserves entity data, supports undo/redo and project/
standalone saves, and acts on the full scene even when search filters hide objects.
Native Wayland shortcuts, selection, overlapping picking and undo/redo were verified.
Draw-order verification: 206 tests pass locally (15.43 seconds) and in Docker
(18.11 seconds), with Ruff, formatting and strict mypy passing.

Recovery now preserves invalid, stale, oversized and unsafe snapshots during
autosave and normal cleanup. Autosave validates the saved baseline, and snapshot
replacement/cleanup rechecks observed bytes before mutation. Regular-file reads
use nonblocking, no-follow descriptors. Cleanup is serialized with snapshot writes
in workers, remains tied to its original project/scene across switching, and drains
within the existing bounded close wait. Activity reports conflicts; manual Save
remains available. Explicit Discard still removes the scene's snapshot. These are
observed-change checks, not cross-process locking or power-loss guarantees.
Recovery verification: 214 tests pass locally (15.76 seconds) and in Docker
(18.46 seconds); Ruff, formatting and strict mypy pass. Native Wayland corrupt-file
preservation, manual saving and worker shutdown were verified.

Repeatable benchmark tooling now measures 1–1,000 distinct sprite textures and
initial canvas construction, plus warm-process launch to first Qt paint using
isolated preferences. Five native Wayland samples measured median 712.168 ms for
the welcome screen and 747.704 ms for Ember Run; startup RSS was 136.352 and
137.734 MiB respectively. The 1,000-texture software fixture measured median
3.958 ms / p95 4.321 ms, with 35.126 ms canvas construction; shared-texture p95
was 3.871 ms. The raw [reference report](performance/2026-10-05.json) records
versions, fixture sizes, sample times, CPU and limitations. Native presentation,
cold-cache startup, input latency and GPU budgets remain open; these measurements
do not justify renderer complexity or prove the complete 60 fps presentation gate.
Benchmarks and resource bounds were exercised locally and in the offline Docker
test image. Ruff, formatting and strict mypy pass; no runtime code changed here.

Native viewport instrumentation now separates update CPU, paint CPU, queued paint
delay and completion cadence using the shared moving-sprite fixture. Synthetic
Qt-posted clicks measure selection and subsequent paint separately, excluding
hardware, compositor delivery and Inspector refresh. The benchmark records actual
viewport dimensions, DPR and screen refresh, limits runtime to 15 seconds, and
reports 120 measured paints and 50 measured clicks after warmup.
On native Wayland at DPR 1.25 / reported 165 Hz, the 1,000-texture run measured
paint CPU p95 5.888 ms, update CPU p95 2.328 ms, latest-update-to-paint-start p95
7.961 ms, click-to-selection p95 0.521 ms and click-to-paint p95 6.820 ms.
Paint completion cadence was median 16.154 ms / p95 20.535 ms, exceeding the
16.7 ms cadence target; the renderer gate remains open. Profiling deferred scene
updates and scheduling is next; compositor presentation still needs independent
evidence. The [raw native report](performance/2026-10-05-native.json) records
shared/unique results and scope. Both benchmark paths passed native/offscreen and
Docker execution checks, plus Ruff, formatting and strict mypy. Runtime code is unchanged.

Repaint profiling now compares 1, 32 and 1,000 moving objects with minimal,
bounding-rectangle, smart and full update modes, and optionally BSP/no indexing.
The default benchmark uses natural Qt dirty-region updates; `--force-repaint`
reproduces the earlier forced whole-viewport request. Every report records workload
and policy settings. Single-run native comparisons measured one-object paint p95
0.230 ms with minimal updates versus 5.321 ms with full updates. For 1,000 moving
objects, full updates reduced queued-paint p95 from 6.932 to 1.288 ms and cadence
p95 from 24.460 to 17.057 ms. Bounding/smart modes did not provide a clear global
replacement, and disabling indexing did not resolve the earlier queue delay.
Engine defaults remain unchanged: these findings warrant animation-heavy Play
measurements before choosing a selective policy. The complete 16.7 ms cadence
and compositor gates remain open. The
[policy comparison report](performance/2026-10-05-repaint-policies.json) retains
natural and exploratory forced-update results, without introducing timing tests.
Native Wayland comparisons, offline Docker mode checks, invalid workload bounds,
Ruff, formatting and strict mypy were verified.

Actual Play animation profiling now uses PlayerWindow's timer, fixed-step movement
and SpriteAnimator, with 1,000 sprites, one controlled player and bounded two-frame
60 fps sheets. It checks changed frames and unchanged authored data, records
120 measured paints after warmup, and compares sparse/dense animation workloads.
A conservative Play-only policy accumulates actual changed frame pixmaps until
painting completes: 1,000 pending changes switch to full viewport redraw; sparse
updates keep minimal redraw. Unchanged/hidden frames do not count, and queued
dense mode survives a later unchanged sync until painting finishes. The editor
policy stays unchanged; there are no new UI controls or dependencies.
Native Wayland 1,000-animation cadence p95 improved from 45.603 ms with minimal
redraw to 17.276 ms with auto, with queued-paint p95 1.332 ms. Sparse auto runs
retained paint p95 0.187 ms (no animations) and 0.548 ms (32 animations).
These are reference observations, not a cross-machine guarantee; the 16.7 ms
cadence target and compositor/hardware-input gates remain open. The
[raw Play comparison](performance/2026-10-05-play-animation.json) records policy
and workload results. Regression checks cover changed/hidden frames and coalesced
dense painting: 215 tests pass locally (15.79 seconds) and in Docker (18.49 seconds),
with Ruff, formatting and strict mypy passing.

The actual dense Play benchmark also completed in Docker offscreen mode with
changing frames and unchanged authored data. Its cadence p95 was 31.233 ms,
reinforcing that host timing gains are not a container/compositor guarantee.

Project sounds now support worker-based WAV import, bounded library scanning and
native PipeWire preview through Scene → Project sounds. Canonical PCM clips retain
readable, content-addressed filenames in a portable `audio/` folder; imports deduplicate
without changing scenes, undo history or project formats. Limits are mono/stereo,
8/16 bit, 8–48 kHz, 30 seconds / 4 MiB per clip and 128 clips / 32 MiB per library.
No-follow regular-file reads, format/hash validation and exclusive publication reject
unsafe inputs and preserve conflicting files. Source metadata is stripped. Preview
passes validated raw PCM over stdin to the fixed system PipeWire client at 25% volume;
selection changes and closing stop playback, including a bounded kill fallback.
PipeWire is optional for native import; no Qt multimedia add-on or Python dependency
was added. Both Docker images include its client, while `compose.audio.yaml` optionally
forwards only the user PipeWire socket. Default networking/display isolation is preserved.
Library renaming/deletion and concurrent-directory editing remain open. Sprite cleanup does not touch audio. Native Wayland import and real
PipeWire preview completed with exit zero and unchanged scene bytes. The same flow
passed in the Wayland desktop container with its optional audio socket; the default
container imported clips and reported unavailable playback without a socket. Asynchronous
capability probing accommodates Arch and Debian PipeWire stdin differences. A shared
runtime playback component now owns process discovery, one-voice playback and bounded
shutdown; the editor imports/scans in workers and reuses this component. The refactor
passed 13 focused audio tests, lint/type checks and real native Wayland playback.
Audio verification: 228 tests pass locally (16.62 seconds) and in Docker (19.48 seconds),
with Ruff, formatting and strict mypy passing. Tests cover malformed/unsafe/bounded
input, conflicts, deduplication, moved projects, both stdin modes, unavailable playback
and termination of an unresponsive player. These checks establish successful playback
processes, not subjective audio quality or broad device/compositor compatibility.

The coin-sound data foundation now adds one optional bounded PCM clip per scene.
Standalone format 9 and project format 10 embed that clip so saved scenes, recovery
and data-only Play snapshots do not depend on source paths or the sound library.
Project sprite references remain unchanged. Earlier formats load with no sound;
upgrades preserve exact versioned backups, and prior v5/v7 recovery hashes remain
compatible when the baseline has no sound. `SetCoinSound` provides validated,
revision-checked undo/redo. Assigned PCM remains within the existing 4 MiB scene
limit; relative audio references and larger music clips are deferred. The schema
checkpoint passed 93 focused integrity/audio tests, Ruff and strict mypy.

Scene sound assignment/removal now runs through `SetCoinSound` with revision checks,
size validation and undo/redo. The native Sounds dialog assigns a selected imported
clip; a Scene-menu removal action also works for standalone documents. Play reads
only the snapshot, decodes PCM once before ticking and uses one optional voice.
Collection batches trigger once; overlapping events share that voice. Pause, focus
loss, restart and closing terminate playback, with a bounded kill fallback. Runtime
SIGTERM requests a graceful window close so normal editor Stop also disposes audio.
Native Wayland assignment, save/reopen, undo/redo, real coin playback and restart
completed with zero playback exit codes and unchanged authored data, both directly
and in the native Wayland desktop container with optional audio forwarding. Full integration:
242 tests pass locally (17.12 seconds) and in Docker (20.50 seconds), plus Ruff,
formatting and strict mypy. Arbitrary script execution, multi-voice mixing, music and
abrupt process-kill cleanup guarantees remain deferred.

Manual scene saves now move serialization, validation and disk I/O into a worker.
A nested Qt event loop preserves the existing synchronous Save-before-switch contract
while processing paints/timers; authoring controls stay disabled until completion.
Close and reentrant Save are guarded. Known saved documents are compared with their
saved baseline, and observed byte revisions are checked again before publication.
External edits/removal, malformed files, links and FIFOs leave external data and
current edits intact; Save As remains available. New targets publish exclusively.
File and containing-directory flushes improve metadata durability. These checks
now include a nonblocking Linux directory `flock` covering scene validation,
migration backup and atomic publication. Locking the containing directory survives
scene replacement without persistent sidecars. Competing engine saves return a
retry message and preserve edits; process exit releases the lock. Separate-process
checks exercise contention after the final revision check, stale retries and writer
termination. Advisory locks do not restrict arbitrary tools; network filesystem,
asset-directory, manifest and full power-loss guarantees remain open. See
[Linux flock semantics](https://man7.org/linux/man-pages/man2/flock.2.html).
Native Wayland save/conflict/Save As and clean close were verified.
Save verification: 250 tests pass locally (18.04 seconds) and in Docker (21.60 seconds),
with Ruff, formatting and strict mypy passing. Regression checks cover observed
external edits/removal, unsafe targets, late changes, event-loop responsiveness,
close guarding and file/directory flushes.
With process contention and termination regressions added, 261 tests pass locally
(20.91 seconds) and in Docker (24.85 seconds), with Ruff, formatting and mypy passing.

Scene → Rename scene title now edits the active title through `SetSceneName`, with
validation, revision protection and undo/redo. Saving retains the project's file,
startup manifest, recovery and lock paths. Cancellation and invalid/expired edits
preserve the current scene. The small scene-organization checkpoint passed 22
focused scene/document/project tests, Ruff and strict mypy; no format change is needed.

The first independent native export now publishes an exclusive executable `.pyz`
through a worker from the applied scene snapshot. An explicit source allowlist packs
only core/runtime code and embedded sprite/animation/PCM data, excluding editor,
project, AI, scripts and preferences. Shared runtime startup handles normal Play and
exported games; shared control selection prefers the first Player. The launcher uses
isolated Python mode, rejects unsupported Python versions and reports missing Qt.
A CLI smoke check exercises the native window/timer/input and reports the imported
runtime origin, gameplay state and absence of editor packages. Existing output files
are preserved, and editing after export starts does not alter the captured snapshot
or mark the document saved.

Native Wayland export launched in a temporary Python/Qt-only environment with no
engine installed: the 15,751-byte two-object fixture moved and collected its coin,
kept authored data intact, and imported runtime code from the archive. Dependencies
were reused via local Qt links, both natively and in the Wayland desktop container;
this is not a clean-machine distribution test.
Python 3.14, PySide6-Essentials 6.11.2 and Linux Qt libraries remain prerequisites;
PipeWire is optional. Bundling native dependencies, clean Arch acceptance and full
project/scene-transition export remain open. The
[Python zipapp contract](https://docs.python.org/3.14/library/zipapp.html) explains
why native extension dependencies stay outside this first archive.
Export verification: 258 tests pass locally (20.38 seconds) and in Docker (24.54 seconds),
plus Ruff, formatting and strict mypy. Tests cover actual archive movement/collection,
portable sprites/audio, isolated imports/environment overrides, invalid snapshots,
exclusive output publication and immutable background export snapshots.

Game metadata and audio diagnostics now render as literal Qt text, and the startup
scene label also avoids interpreting filename markup. A regression fixture confirmed
that AutoText loaded an `<img>` path from an object name while PlainText did not.
This prevents game/project text from implicitly loading image resources through
those labels. Ten focused runtime/export checks, Ruff and strict mypy passed.

UI direction: the native editor now uses near-black surfaces with solarpunk leaf
green, mint and solar-gold accents, a vector sun-and-leaves emblem, a scene header,
and an actionable welcome card. Empty scenes
offer showcase, create-object and open-project paths; populated scenes retain
viewport editing. Project Scenes shares the Scene dock's tabs, giving the Inspector
more vertical room; Play and Apply receive primary accents. All docks remain
movable and floatable. No animation timers or new dependencies were added.
One compact toolbar replaces two rows. New/Open/showcase, Add rectangle,
duplicate/delete and zoom commands remain in menus with their shortcuts;
Save, undo/redo, PNG import, Fit, snapping and Play remain directly accessible.
Grid spacing appears only when snapping is enabled. The palette is centralized
in `editor/theme.py`; a user-facing theme editor remains future work.
Native Wayland create/undo, welcome transitions and showcase opening were checked;
142 regression tests pass in Docker, with Ruff, formatting and strict mypy passing.
The Inspector now groups Object, Transform, Appearance and Movement properties
in native solarpunk panels. Forms wrap long rows in narrow docks, and Apply remains
outside the scroll area and disables when no object is selected. Existing command
validation, selection and undo/redo workflows remain shared across all groups.
Keyboard navigation follows the visual group order. Native Wayland grouped editing,
Apply, undo/redo, scrolling and keyboard order were verified. The integration suite
passes all 192 tests locally (14.96 seconds) and in Docker (17.21 seconds); Ruff,
formatting and strict mypy pass.
The Assets panel now offers bounded case-insensitive name/dimension search,
thumbnail entries with separate name/size lines, matching counts and an explicit
no-results hint. Ctrl+Alt+L reveals and focuses sprite search. Filtering changes
only the list and clears hidden palette selections, guarding Add/Apply actions
while preserving scene selection and revision. Imports, undo and background project
scans reapply the active filter; existing palette limits remain unchanged.
Native Wayland entries, filtering, shortcut focus and scene integrity were verified.
Asset-search verification: 193 tests pass locally (15.08 seconds) and in Docker
(17.66 seconds), with Ruff, formatting and strict mypy passing.
Previews: `docs/screenshots/editor-welcome.png` and `editor-workshop.png`.

Showcase verification: the complete twelve-core route avoids walls, distributed
scenes match their built-in templates, and Play leaves authoring unchanged.
All 142 tests passed locally (2.41 seconds) and in Docker (3.07 seconds), with
Ruff, formatting and strict mypy passing. Native Wayland opening, animation,
pause/restart and second-scene switching were verified. Opening instructions are
in `examples/ember-run/README.md`; a preview is in `docs/screenshots/ember-run.png`.

### Implemented foundation checkpoints

- Python 3.14, PySide6 Essentials 6.11.2, uv lockfile, Ruff, mypy and focused pytest.
- Native Qt shell, Graphics View rectangles, scene tree, property inspector, and
  create/update/delete commands with transactional undo/redo and revision checks.
- Duplicate Object (Ctrl+D) copies applied properties and gameplay roles with a
  fresh ID and a 24-unit offset, selects the copy, and uses the shared create command.
  Names and positions remain within schema limits. Undo/redo and save/reopen are verified.
- Version-seven `.forge.json` scene documents with version-one/two/three/five loading support,
  bounded/validated reads, atomic writes, and unsaved-change protection on New/Open/Close.
- Core integrity tests and one native edit/save/reopen workflow; offscreen visual QA.
- Separate non-root Docker desktop/test images and independent headless test Compose;
  the native app forwards its window through Wayland and keeps networking disabled.
- Native Play process receiving a bounded, validated JSON snapshot over stdin;
  shared rectangle renderer, fixed-step keyboard movement, pause, restart and Stop.
  Authored scenes remain unchanged. Isolated Python startup ignores working-directory
  packages and Python path environment overrides; no project Python code executes.
- Editable coin-collector starter: Player/Wall/Coin/Decoration roles, static
  axis-aligned wall collisions, coin triggers, score/completion HUD, and restart.
  Version-seven scenes persist roles, sprites, movement and animation settings; legacy scenes load without changing
  disk data. Save creates a non-overwriting `.v1.bak` or `.v2.bak` before upgrading.
- PNG sprite import (Ctrl+Shift+I), embedded bounded RGBA data, transparency,
  inspector sizing/removal, and cached native pixmaps shared by editor and player.
  Imports are capped at 256×256 pixels and 2 MiB; scenes remain capped at 4 MiB.
  Source paths are not persisted or accessed by playback. Standalone scenes embed
  pixels; project saves deduplicate them into validated, relative asset files.
- Create project from the current applied scene and open project folders through
  the native File menu. Version-one `project.json` identifies a relative scene in
  `scenes/`; `assets/` stores content-addressed RGBA sprite files. Existing folders are never adopted/overwritten.
  Scene paths reject traversal and symlinks on open/save; failed creation removes
  the newly created folder. Standalone scenes and embedded sprites remain supported.
- Version-four project scenes use relative `assets/<hash>.rgba` sprite references;
  opening verifies dimensions, bounded bytes and content hashes, then resolves them
  into portable version-seven scene data. Identical sprites share a file. Play does
  not read project paths. Assets publish before atomic scene replacement; failed
  saves can leave unused assets, while previous scenes and their references survive.
  Embedded project upgrades preserve exact `.v1.bak`, `.v2.bak` or `.v3.bak` bytes.
- Native Assets panel with preview icons, unique sprite reuse, Add to scene,
  and Apply to selected object through validated commands. Apply preserves geometry
  and gameplay roles. Imported/loaded sprites remain reusable for the current scene
  session after undo/removal; a new/opened scene resets the palette. It is bounded
  to 128 sprites / 4 MiB pixel data and does not index unused asset files on disk.
- Project-only recovery snapshots after a two-second edit debounce, serialized and
  written in a worker thread with at most one job active. A single self-contained
  snapshot per scene is capped at 4 MiB and atomically replaced; manual scene and
  asset files are untouched. Opening offers Recover/Discard/Open saved, restoration
  uses an undoable `RestoreScene` command, and Save/Discard/Undo-to-saved clears the
  snapshot. Baseline fingerprints normalize scene numbers and reject stale snapshots.
  Failed/invalid recovery is reported without blocking manual save or saved-project
  opening. In-flight writes are cleared after Save/Discard; close waits briefly for
  the worker rather than destroying an active thread.
- Project Scenes panel: create named empty scenes, list up to 128 top-level scene
  files, refresh external changes, and switch via double-click or Open selected.
  Validation rejects unsafe paths/duplicate names before any discard prompt, and
  new scene publication is exclusive and atomic. Save/Discard/Cancel protects dirty
  edits; activation stops Play, resets undo/palette, and offers per-scene recovery.
  Ordinary switching leaves the manifest default unchanged; explicit startup selection
  is now available. Runtime transitions are not implemented.
- Project-wide sprite catalog from saved scenes, automatically indexed in a worker
  on project open/scene activation and manually via Refresh project assets. Existing
  scene, path and hash validators are reused; malformed scenes yield warnings.
  Work is limited to the scene browser's 128 scenes, 16 MiB of scene-file bytes, and
  128 sprites / 4 MiB unique pixel data. UI icons are created only after completion
  on the UI thread; old-project results are ignored and the new project is rescanned.
  Cross-scene Add/Apply use existing undoable commands and reuse asset files on Save.
  Unreferenced files, backups and recovery snapshots are not catalog sources yet.
- Repeatable 1,000-moving-rectangle software benchmark at 1024×576: 10 warmup frames,
  120 measured frames. Initial Arch host run: median 4.805 ms, p95 4.953 ms, Python
  3.14.7 / Qt 6.11.2 / offscreen QImage rendering. This does not establish sprite,
  compositor or GPU budgets; the complete backend selection gate remains open.

Verification: the foundation had 12 focused tests; playback adds movement,
keyboard/pause/restart, and subprocess lifecycle checks. The collector adds collision,
score/reset, starter persistence, migration backup, invalid roles, and a complete
starter route around the walls. Object duplication adds property preservation,
undo/redo and save/reopen checks. Sprite checks cover transparency, source removal,
Play, invalid input, bounded dimensions and both legacy upgrades: 30 tests passed
locally in 1.26 seconds and in Docker in 1.57 seconds before project-folder work.
Project checks add save/reopen, copy preservation, failure cleanup and path boundaries
for 39 tests at that checkpoint (local 0.45 seconds; Docker 0.61 seconds). Asset
checks add moved-project/Play portability, deduplication, standalone saves, hash
validation, path rejection, failed-save preservation and embedded upgrades: 46 tests
passed locally in 0.65 seconds and in Docker in 0.85 seconds. Native Wayland
asset import/save/reopen/Play was also verified. Sprite palette checks add reuse,
apply/undo, retained previews, save/reopen deduplication, reset and size rejection:
48 tests passed locally in 0.68 seconds and in Docker in 0.90 seconds. Palette
layout was visually inspected; native Wayland reuse was smoke-tested. Save As/New
transitions are covered. Recovery adds atomic failure preservation, automatic timer
write, undo/redo restore, keep/discard choices, stale/corrupt rejection, in-flight
save races and error handling: 56 tests passed locally in 0.80 seconds and in Docker
in 1.07 seconds. Native Wayland autosave/recover/manual-save was verified. Ruff,
formatting, and strict mypy pass. Multiple-scene checks add create/save/switch,
cancellation, per-scene recovery, invalid/duplicate names, exclusive-write failure
and symlink rejection: 63 tests passed locally in 0.88 seconds and in Docker in
1.21 seconds. The panel was visually inspected; native Wayland scene creation,
save, switch and Play were verified. Project catalog checks cover cross-scene reuse,
save deduplication, invalid-scene warnings, cancellation/budgets, and old-project
result rejection: 66 tests passed locally in 0.96 seconds and in Docker in
1.31 seconds. Native Wayland scan/reuse/save across scenes was verified. Cleanup
checks cover protected references, incomplete scans, changed review state, cancellation,
and rollback after partial moves: 74 tests passed locally in 1.10 seconds and in Docker
in 1.46 seconds. Ruff, formatting, and strict mypy passed; native Wayland reviewed
cleanup and quarantine were verified. Movement checks cover invalid commands,
legacy embedded/project upgrades with exact backups, undo/redo, duplication, persistence,
preset filtering, normalized speed and restart: 84 tests passed locally in 1.13 seconds
and in Docker in 1.50 seconds. Quality checks and native Wayland authoring/playback passed. Viewport checks add
rectangle/sprite previews, single-step undo/redo and save/reopen, snapping versus clicks,
cancellation and revision conflicts: 92 tests passed locally in 1.39 seconds and
in Docker in 1.83 seconds; Ruff, formatting and strict mypy passed.
Native Wayland dragging/snapping/undo passed; the final toolbar and scrollable
Inspector layout were visually inspected. Navigation checks cover pointer anchoring,
zoom limits, middle-button pan, wheel modifiers, snapped dragging across scales,
cancellation and fitting distant objects: 97 tests passed locally in 1.53 seconds and in Docker in 1.98 seconds;
Ruff, formatting and strict mypy passed.
Native Wayland zoom/pan/drag/undo/Fit passed and the toolbar was visually inspected.
Quarantine restoration checks cover exact bytes, unchanged scenes, existing targets,
symlinks, changed files, incomplete scans, failed source removal and worker lifecycle:
108 tests passed locally in 1.67 seconds and in Docker in 2.17 seconds. Ruff, formatting
and strict mypy passed. Native Wayland browsing/restoration passed; the dialog was
visually inspected.
Startup-scene checks cover persisted selection, invalid/missing/symlinked targets,
external settings changes, failed atomic writes and preservation of active unsaved
edits/history: 115 tests passed locally in 1.74 seconds and in Docker in 2.28 seconds. Native Wayland selection
and reopen passed; the project panel was inspected. Ruff, formatting and strict
mypy passed.
Animation checks cover bounded metadata, grid validation, edit/undo/duplication,
portable sprites, legacy backups and recovery, frame timing, pause and restart:
125 tests passed locally in 1.82 seconds and in Docker in 2.39 seconds;
Ruff, formatting and strict mypy passed. Native Wayland animation/pause/restart
passed and rendering was visually inspected. Older scenes remain static; saves
upgrade standalone scenes to version seven and project scenes to version eight.
Version-five recovery fingerprints remain compatible when baseline animation is absent.
Assistant checks cover deterministic proposals, response limits, unsafe/invalid tools,
atomic review/apply/undo/save, stale documents, cancellation, provider failures and
close-while-running: 139 tests passed locally in 2.18 seconds and in Docker in
2.82 seconds. Ruff, formatting and strict mypy passed. Native Wayland proposal,
review, Apply and Undo were verified. No real-model response is claimed.
Project create/open/Play also
passed a native Wayland smoke check. PNG editor and Play startup/shutdown were checked
on Wayland; authored scene data stayed unchanged. Previous native/container collector
startup/shutdown checks also passed on the Arch host.
An intentionally failing test previously returned exit status 1 in the independent
test container. This does not validate an arbitrary-code sandbox or establish full
compositor/GPU compatibility.

This is a small authoring slice, not a completed phase 0 or phase 1. Project asset
libraries and sound import/collection playback now exist, alongside a runtime-only
native export and opt-in local Ollama adapter. Sandboxed scripts, dependency-bundled
exports and enterprise adapters remain unimplemented. The assistant starts with
an offline demo fixture. Project folders support multiple authored scenes with
relative sprite references, per-scene recovery and a project-wide sprite palette.
Reviewed unused-asset scanning, reversible quarantine and native browsing/restoration
are implemented, including reviewed single-file purge. Runtime scene transitions remain planned.
The Qt backend remains provisional pending representative sprite workloads and
native presentation benchmarks.
See the [README](../README.md) for runnable commands. Later sections distinguish
implemented contracts from the intended project and release architecture.

### Completed implementation checkpoints

| Commit | Delivered checkpoint |
| --- | --- |
| `302d629` | Python package and native editor; rectangle editing; validated commands; transactional undo/redo; atomic scene persistence |
| `1db6335` | Separate non-root Wayland desktop and offscreen test containers; verified test failure exit handling |
| `be32b68` | Native Play subprocess; shared renderer; normalized fixed-step movement; pause/restart/Stop; software rendering fixture; dependency-layer caching |
| `515d995` | Editable coin starter; explicit gameplay roles; static wall collisions; collectible triggers; score/completion HUD; version-one backup before upgrade |

**Fixed platform decision:** native Arch Linux desktop, Python application and game
scripting, and PySide6 Qt Widgets. No JavaScript, TypeScript, browser UI, embedded
webview, or web export. This supersedes the original web-based proposal.

## 1. Product promise

**Turn a small game idea into something playable quickly, then give its creator
clear control over every part of it.**

Solar Forge is a 2D engine in the Solar Forge Studios suite. Take inspiration from
Godot's approachable scene editing while keeping the initial feature set much
smaller. AI should understand scenes, assets, behaviors, errors, and editor actions;
it should help throughout development rather than exist only as a chat panel.

Primary users are solo developers, small studios, hobbyists, and people learning
game development. Start with arcade games, puzzle games, and simple top-down games.
Add platformers after collisions and character movement are reliable.

- **Usability:** a template becomes playable before the user learns the engine.
- **Creator control:** visual editing, ordinary code, and AI assistance work together.
- **Local ownership:** projects are readable files; no account is required to edit.
- **Fast feedback:** loading, selection, editing, play, and undo stay responsive.
- **Small runtime:** exports contain no editor, model client, or cloud dependency.
- **Extensibility:** documented component and command contracts without a plugin
  marketplace or generalized framework in the first release.

Out of scope for v0.1: 3D, multiplayer networking, consoles, native mobile exports,
real-time collaboration, a full visual scripting language, an asset store, model
training, web exports, and autonomous background agents. Other native operating
systems can follow validated demand; Arch Linux desktop is the initial target.

## 2. The first complete experience

The reference game is a small top-down coin collector with movement, collisions,
a score, sound effects, and a restart button.

1. Create a project from a starter template, choosing its local folder.
2. Press Play immediately; keyboard controls and the objective already work.
3. Drag a sprite into the scene and edit it in the inspector.
4. Ask: “Make the player faster and add five coins away from walls.”
5. Inspect the proposed changes, apply them, and preview the result.
6. Undo the change as one action or adjust individual objects manually.
7. Save, close, reopen, and export a native Linux game.

An equivalent manual workflow must work with AI disabled. The exported Linux game
must launch without the editor, Docker, or a model provider. Validate it on a clean
Arch installation without the development environment.

Success criterion: at least four of five first-time testers can customize and
export the template within ten minutes without developer intervention. Test whether
labels, defaults, and recovery paths are understandable, not just functional.

**Current usable subset:** choose Coin starter, edit object properties and roles,
press Play, navigate around walls, collect all five coins, restart, and save/reopen
the scene. A focused route test verifies the starter can be completed without crossing
walls. PNG sprites can be imported, sized, duplicated, saved and played. Scenes
can be copied into a new project folder and reopened through its manifest.
Sprite dragging, collection sound effects, reviewed local-model edits and runtime-only
native export are implemented; dependency bundling remains pending. The five-person usability exercise has not run.

## 3. Scope and editor design

| Area | v0.1 requirement | Later, if justified |
| --- | --- | --- |
| Workspace | Project browser, scene tree, viewport, inspector, assets, console | Saved custom layouts, multiple windows |
| Scene editing | Move/rotate/scale, snapping, parenting, layers, duplicate, undo/redo | Advanced constraints and level tooling |
| Rendering | Sprites, atlases, text, camera, pixel-perfect option | Shader editor, advanced lighting |
| Gameplay | Input actions, reusable behaviors, triggers, basic collisions, timers | Complex rigid-body physics |
| Content | Asset import, sprite animation, audio, reusable scene instances | Tilemap authoring, richer animation tools |
| UI | Labels, buttons, anchors, basic scaling | Full UI layout designer |
| Development | Play/stop, error links, small script editor, external-editor workflow | Breakpoint debugger, profiler UI |
| AI | Contextual questions, structured scene edits, bounded script changes | Asset generation integrations |
| Export | Native Linux game bundle and clean-machine validation | Other native platforms if requested |

Implemented scope is intentionally narrower than the v0.1 requirements above:

- Workspace: native scene tree, viewport, property inspector, menus/toolbar, activity
  log, shortcuts, empty-scene guidance, and create/open project-folder actions.
  Assets panel previews and reuses loaded/imported sprites; Project Scenes supports
  create/switch/refresh. Saved-scene sprite indexing and reviewed unused-asset scans
  run in workers; approved unused sprites move into reversible quarantine.
- Scene editing: create/delete, name, X/Y, width/height, hex color, role, and undo/redo.
  Inspector changes require Apply. Viewport dragging commits one validated position
  edit on release; Escape, focus loss, refresh or changed revision cancels the preview.
  Optional 1–256-unit grid snapping applies to drags; its settings are session-only.
  Ctrl+wheel zooms at the pointer; toolbar/keyboard zoom and middle-button pan
  leave scene data unchanged. Fit scene includes the arena and distant authored objects.
  Navigation settings are session-only. No resize/rotation gizmos, hierarchy or layer controls yet. Selected-object duplication is implemented with Ctrl+D.
- Rendering: native rectangles and circular coin visuals, selection, tooltips, and
  fit-to-view, and imported PNG sprites with cached native pixmaps and transparency.
  Equal-cell sprite sheets loop in row order at 1–60 fps, up to 256 frames; the
  editor shows frame zero. Play caches shared frame pixmaps, freezes on pause/focus
  loss, and restarts at frame zero. Sprite geometry/collision bounds remain unchanged.
  No named clips, partial sequences, game camera tooling, or game UI editor.
- Gameplay: 1024×576 arena, per-object movement speed (0–2,000 units/second)
  and WASD/arrows presets; defaults remain 240 units/second with both key sets,
  normalized diagonals, static axis-aligned walls, rectangular coin trigger bounds,
  score/completion display, pause, restart, and focus-loss handling. Initial wall
  overlap is not resolved. General input actions and reusable behavior components
  are still planned.
- Development: separate native Play process, Stop, startup/error log, and snapshot
  playback that leaves authored state unchanged. No project script execution,
  script editor, debugger, or dependency-bundled game export yet; local model connection
  and runtime-only native export are implemented.
  The Assistant tab has a deterministic offline demo with review/apply/discard,
  atomic undo, bounded scene tools, cancellation and stale-document protection.

Use a restrained graphite theme with solar amber accents, readable typography,
clear selection states, and minimal decorative motion. Share Solar Forge Studios
design tokens when available. Support keyboard navigation, visible focus, scalable
text, accessible contrast, reduced motion, and color-independent error indicators.

Place the scene tree left, viewport center, inspector right, and assets/console
below. Make the assistant collapsible. Provide a searchable command palette,
shortcuts, contextual help, empty states, and plain-language errors with a next step.
Remember layout preferences locally. Avoid mandatory onboarding or a login wall.

## 4. Native Python architecture and suite alignment

Use **Python with PySide6 Qt Widgets**, targeting Arch Linux on Wayland first.
Build actual native windows, menus, dialogs, docking panels, and a native viewport.
No browser engine, HTML UI, Electron, Tauri, QtWebEngine, QML/JavaScript layer,
Node tooling, or JavaScript/TypeScript application, game, plugin, or test code.
HTTP access to model APIs is permitted; that does not make the editor web-based.

The sibling `../solar-forge-life-helper` was inspected for this revision. Its
`pyproject.toml`, README, Dockerfiles, Compose configuration, and widget code use
Python 3.14, PySide6, Hatchling, `uv.lock`, pytest/pytest-qt, Ruff, Wayland forwarding,
and separate run/test images. Follow those conventions where appropriate. Reuse
visual conventions after reviewing their fit; do not copy its account system,
database, application domain, or dependencies unrelated to game development.

| Layer | Direction | Validation requirement |
| --- | --- | --- |
| Language/tooling | Python, `pyproject.toml`, Hatchling, uv and one lockfile | Start by checking the Life Helper Python/PySide6 versions against engine dependencies |
| Editor | PySide6 Qt Widgets, dock panels, native text editor | Responsive input, keyboard access, scaling, Wayland focus |
| 2D rendering | Prototype Qt Graphics View with cached native pixmaps and shared rendering adapter | Measure animation, transforms, many sprites, camera motion, and export size |
| Runtime | Python scene/component simulation with native Qt rendering/audio bindings | Separate process and package entry point; no editor or AI imports |
| Project I/O | Python services inside the editor, worker jobs for expensive operations | Atomic saves and project-root restrictions; no local HTTP server required |
| Model integration | Python provider adapters with streaming and cancellation | Worker I/O; marshal results back to the UI thread |
| Tests | pytest, pytest-qt, Ruff, one Python type checker | Small deterministic tests and a few native UI workflows |
| Distribution | Native Arch package/launcher plus Docker desktop run image | Both launch native windows; exports work without Docker |

Implemented choices are Python 3.14, PySide6 Essentials 6.11.2, Hatchling, uv with
one lockfile, Ruff, mypy, pytest, and pytest-qt. Qt Graphics View is shared by editor
and player. The renderer draws geometry and native sprite pixmaps, decoding each
unique resolved sprite once per scene rebuild; the frame loop only moves items.
The built-in simulation is Qt-independent. Recovery writes run in a Qt worker
thread. Audio bindings, broader asset pipelines and provider adapters remain planned.

Qt's Graphics View provides 2D scene items and views through Python bindings.
Use it as the first rendering spike so authoring and standalone playback can share
one visual implementation. Keep simulation data independent of Qt items and isolate
editor gizmos from runtime rendering. [Qt Graphics View documentation](https://doc.qt.io/qtforpython-6/overviews/qtwidgets-graphicsview.html).

This is a candidate rendering backend, not a claim that Qt supplies a complete game
engine or meets our budgets. Measure the coin collector and a 1,000-sprite fixture.
If inadequate, evaluate a Python-accessible native rendering backend such as
pygame-ce/SDL before choosing one implementation. Do not ship competing backends or
build a renderer abstraction framework prematurely. A separate native Play window
is acceptable for v0.1; do not depend on embedding foreign windows under Wayland.
[pygame-ce documentation](https://pyga.me/docs/ref/pygame.html).

Python is the preferred implementation language, not a performance guarantee. Use
native library operations for drawing, cache assets, minimize per-frame Python
allocations, and measure collision/update costs. Keep UI operations on the Qt main
thread. Use workers for blocking I/O and processes for CPU-heavy Python tasks when
measurements justify them. Introduce compiled extensions only for proven bottlenecks
with an explicit architecture decision; do not replace the Python-first direction.

Current repository structure:

```text
pyproject.toml
uv.lock
src/solar_forge_engine/
    editor/             Native window, scene tree, viewport and inspector
    core/               Scene/role/sprite schemas, commands, built-in starter data
    runtime/            Simulation, shared renderer and native player entry point
    project/            Scene I/O, upgrade backup, PNG normalization, folders, assets, recovery
    __main__.py         Native editor entry point
scripts/                Software rendering and isolated warm-startup benchmarks
tests/                  Scene, editor, player, collector, sprite and project checks
docs/                   This plan
Dockerfile.run
Dockerfile.test
compose.yaml
compose.test.yaml
```

The `ai/` package contains the offline provider and bounded proposal decoder.
Add export modules, `resources/`, external `templates/`,
and `packaging/` when their features are implemented. The current starter is data in
[`core/templates.py`](../src/solar_forge_engine/core/templates.py); it contains no
project scripts. A source-run console launcher and Docker image exist; Arch package
recipes, desktop entries, icons, and distributable game packaging do not yet exist.

Editor, project, and AI layers use core; runtime consumes validated game data.
Core cannot import the editor or providers. The standalone player must not import
editor/AI modules. Avoid microservices, databases, event sourcing, or a custom ECS
until a concrete need appears. Pin supported versions and record backend selection
in a short architecture decision record (ADR).

Provide an Arch `PKGBUILD`, application icon, `.desktop` entry, and a console
launcher. Follow XDG paths for preferences/cache; let users select project folders.
Validate Wayland, fractional scaling, clipboard, file dialogs, fonts, audio, and
GPU behavior on the actual Arch desktop. X11 support is secondary, explicitly tested
before advertised. Container tests alone cannot establish desktop compatibility.

Package native games with their player, assets, Python runtime and required native
libraries, or offer an Arch package with declared dependencies. Evaluate a directory
bundle first to avoid single-file extraction startup overhead. Verify licensing,
Qt plugin inclusion, and the clean-machine dependency boundary. Distribution beyond
Arch needs its own ABI/build baseline. [Qt deployment guidance](https://doc.qt.io/qtforpython-6.8/deployment/index.html).

## 5. Project model, runtime, and extension contracts

**Current persistence:** a version-one `project.json` manifest identifies one
relative scene inside `scenes/`; `assets/` contains immutable content-addressed
RGBA sprite pixels referenced by version-eight project scenes.
Manifest reads are limited to 16 KiB, strictly validated, and never execute code.
Opening and saving revalidate paths against traversal and symlinks. Creation requires
a new folder, copies the current scene, preserves the source file, and cleans up
on handled failure. Save As leaves project mode and writes a standalone scene.
This is path validation, not protection against concurrent hostile filesystem changes
or an OS sandbox.

Project sprite references are constrained to `assets/<64 lowercase hex digits>.rgba`.
The hash covers dimensions and raw RGBA pixels; opening rejects missing, damaged,
oversized and symlinked assets. Copies reuse one file, and moving the whole folder
preserves references. Open resolves assets into immutable in-memory Sprite data;
Play and standalone Save As use that snapshot without external path access.
Assets publish through a flushed temporary file and exclusive hard link before the
scene's atomic replacement. Handled failures preserve prior scene data; unused
assets may remain. Reviewed cleanup protects scenes, backups, recovery, undo/redo and
palette references, then revalidates the complete scan before quarantine. Unknown or
incomplete scans abort; handled move failures roll back. Its 512-entry / 32 MiB
budget keeps scans bounded. Quarantine is reversible and does not reclaim space.
The native quarantine browser restores one selected file through an exclusive hard
link followed by source removal; existing targets are never overwritten. Changed
files require a fresh scan. Failed source removal retains both copies. Browsing
uses workers with 512-entry / 32 MiB limits; unknown entries, symlinks and invalid
RGBA byte lengths abort. Restoration preserves bytes without inferring dimensions;
scene loading retains dimension/hash validation. Permanent deletion is not implemented.
Recovery uses a single bounded embedded snapshot per scene, not an append-only journal.
This is not a whole-folder atomic transaction or concurrent filesystem sandbox.

Each standalone version-seven `.forge.json` file contains scene name,
stable entity IDs, geometry, color, explicit Role values and optional embedded
sprites (dimensions plus base64 RGBA pixels), movement speed and keyboard preset, plus optional sprite-sheet animation settings.
Legacy scenes default to 240 units/second and WASD/arrows. Version-four project
scenes remain supported; project saves now write version eight; version-six project scenes remain supported. Version-one scenes
load in memory with Decoration roles. Loading does not rewrite the original; saving
over a legacy scene first creates a version-specific `.v<old-version>.bak`
as appropriate to the target format.
An occupied backup name requires Save As. Both on-disk scenes and resolved snapshots
are limited to 4 MiB, preserving the standalone/Play boundary; scenes support 10,000
entities. Undo/redo uses bounded in-memory scene history with monotonic revisions.
Preview state lives in a separate simulation and is not persisted into the scene.

**Implemented recovery:** `<scene>.recovery.json` is a version-one envelope with
baseline fingerprint and embedded scene data (maximum 4 MiB total). A two-second
edit debounce starts one worker-thread write; cleanup requests coalesce per scene
and share that worker queue. There is no frame-loop I/O.
Baseline hashes canonicalize int/float geometry to match save/load normalization.
Invalid or stale snapshots never replace saved scenes automatically. Users choose
Recover/Discard/Open saved; recovery is undoable and dirty until manually saved.
Save and Undo-to-saved queue validated cleanup, preserving conflicting snapshots;
explicit Discard removes the snapshot, including late worker completion.
No standalone/untitled recovery, unapplied-field capture, snapshot
history, power-loss durability guarantee, or concurrent multi-instance coordination
is implemented yet.

Implemented commands are `CreateEntity`, `SetEntity`, `DeleteEntity`, `MoveEntity`, and `RestoreScene` in
[`core/commands.py`](../src/solar_forge_engine/core/commands.py). Batched edits apply
atomically with an expected revision; invalid or stale changes leave the document
and history intact. The UI uses this command layer. The assistant exposes a bounded create/set/delete dispatcher. No generic
component registration exists yet. Typed roles are the current built-in gameplay
contract, preceding the richer component design below.

Project scene browsing covers up to 128 top-level scene files plus the active
manifest scene when nested. New scenes use exclusive atomic file publication and
validated names; existing files are never overwritten. Scene activation clears
current undo/palette state and handles that scene’s recovery snapshot. Project
reopen selects the manifest startup scene, which ordinary switching does not modify.
Set selected as startup scene validates saved data/assets in a worker, checks for
externally changed settings, and atomically updates the manifest. The active scene,
unsaved edits, history and Play remain unchanged; this project setting is outside
scene undo/redo. Nested scene
tree UI, scene renaming/deletion, and runtime transitions remain planned.

Saved-scene asset indexing runs in a worker with interruption on close; results
from a different project root are ignored. It loads validated scenes and deduplicates
sprites into the existing bounded palette. An explicit Refresh action handles
external changes. Corrupt scenes are skipped with warnings. This is an ephemeral
catalog of saved-scene references, not a persisted index of all asset files.

**Planned project extensions:** scene organization,
and sandboxed Python `scripts/`. The basic `project.json`, `scenes/`, and `assets/`
layout and relative sprite references are implemented; standalone scenes still
embed pixels. Ignore generated caches and builds. Use stable IDs and relative asset references, with
separate scene files for manageable diffs. Never store keys or machine-specific
absolute paths in projects.

Use a scene graph with typed components such as Transform2D, Sprite, Camera2D,
Collider2D, AudioSource, and Behavior. Separate authoring state from play state;
stopping preview restores the authored scene. Offer a small script API such as
`on_start`, `on_update`, and `on_collision`, with documented lifecycle and cleanup.
Use fixed simulation steps with bounded catch-up, independently scheduled rendering,
and explicit pause/focus behavior. Start with simple collision shapes and triggers.

All mutations enter shared commands such as `create_entity`, `set_property`,
`attach_component`, `instantiate_scene`, and `apply_script_patch`. Commands have stable
targets, schema-validated arguments, a project revision, and a reversible result.
Batch related changes into atomic transactions. Reject stale edits and generate a
fresh preview against the current revision instead of overwriting intervening work.

Write saves atomically, retain a bounded recovery journal, and offer crash recovery.
Back up before migration; never silently rewrite newer unsupported formats. Asset
imports track source, content hash, and licensing notes where known. Do not execute
project scripts simply by opening or indexing a project.

Ship built-in components using a registration contract. Later expose versioned
extension points for components, importers, exporters, inspector controls, and model
adapters. Extensions declare compatibility and capabilities. Keep runtime and editor
extensions distinct. Untrusted plugins need actual process or sandbox isolation;
Python protocols and type hints alone are not a security boundary.

## 6. LLM-first, with local and enterprise support

**Status: reviewed proposals and initial Ollama adapter implemented.** The native Assistant tab
defaults to a deterministic fake provider with exact demo requests, not a language model.
It proposes create/set/delete scene commands, validates the entire batch in a
throwaway Document, and displays an explicit diff before Apply. Responses are
limited to 16 KiB / 16 commands; requests to 2,000 characters. No scripts, file
patches, sprite changes or arbitrary execution tools are exposed. Apply revalidates
and checks document identity/revision, then creates one atomic undoable edit.
Generation runs in a Qt worker. Discard cancels results, stale responses cannot
apply, and provider errors leave authoring untouched. Closing waits for an active
request to finish. The Ollama adapter accepts explicit HTTP loopback settings and
installed model names, uses schema-constrained non-streaming chat, and closes its
client socket on cancellation or the absolute 1–120-second deadline. Connect waits
are capped at two seconds. It sends up to 128 objects / 32 KiB of metadata, with no
pixels or project paths; selected/gameplay objects take priority. HTTP envelopes
are capped at 64 KiB. Proxies, redirects and cloud-named models are rejected;
offline inference also requires the operator to disable cloud on the Ollama server.
Default app/test Compose networking remains disabled; `compose.ollama.yaml` is an
explicit Linux host-network override for the desktop. No services are managed and
no models are downloaded. Installed-model discovery uses a bounded, cancellable
GET `/api/tags` request and an editable picker; up to 128 entries are accepted,
deduplicated and filtered to exclude cloud-named models and advertised remote aliases. Discovery sends no scene
context and does not load models. An explicit Save local connection action stores
validated version-one endpoint/model/deadline preferences atomically under the
user's XDG config directory, outside projects. Loading stays offline, preserves
settings typed while loading, and reports malformed files without rewriting them.
Preference I/O runs in workers with 4 KiB reads and regular-file checks. The Docker
runtime has a separate writable `preferences` volume for non-root persistence.
Check model capabilities performs a bounded `/api/show` metadata request without
scene context or inference. It reports completion capabilities and advertised
context length when available. Every generation preflights again and rejects
missing/invalid capability metadata, models without completion, and advertised
remote aliases before sending scene data. Preflight and chat share one absolute
deadline. Capability metadata does not prove JSON quality, active context budget,
or server isolation; reviewed proposal validation and offline server configuration
remain required.
Verification: 181 tests pass locally (11.66 seconds) and in Docker (13.30 seconds).
Ruff, formatting and strict mypy pass. Real loopback HTTP fixtures cover transport,
schema requests, bad/oversized responses, redirect refusal, cancellation/deadlines,
review, Apply and Undo, discovery bounds/cancellation, and preference persistence
and malformed-file preservation. Native Wayland discovery/save/offline reopen and
runtime non-root volume writes were checked. Live inference on an existing
`granite4.1:3b` model, with temporary cloud-disabled Ollama 0.33.3 on port 11439,
produced valid reviewed position edits and native Wayland Apply/Undo (6.12 seconds).
An Ember Run speed edit also passed preflight, validation, Apply and Undo
(6.19 seconds; 28,417-byte context, 180-byte response). These are individual
observations, not performance budgets or a general model-quality claim. The
temporary server was stopped; no models were downloaded or services reconfigured.
Capability/remote rejection and a shared metadata/chat deadline are covered by
offline HTTP fixtures. Enterprise adapters, credentials and broader
tool orchestration remain planned. Manual workflows
remain independent of the assistant. The broader behavior below is the target design.

The assistant answers questions about selected objects, explains errors, constructs
scenes, adds behaviors, and makes small code changes. Supply a compact, versioned
engine reference and examples matching the installed engine rather than relying on
model memory of APIs.

```text
Intent + selected context
  -> provider adapter
  -> proposed typed commands / bounded file patches
  -> schema, permission, revision, and resource-limit checks
  -> readable diff and optional disposable preview
  -> apply one transaction
  -> play/check result, keep or undo
```

Default to reviewing changes as a batch. Let users opt into automatic application
of reversible scene edits within a bounded scope. Destructive file actions, new
external connections, and dependency installation require explicit permission.
Read-only questions need no confirmation dialogs. Cancellation, partial responses,
malformed output, timeouts, and retries must leave the project intact.

| Target | Initial support contract |
| --- | --- |
| Local inference | One verified Ollama configuration; configurable compatible endpoint |
| Hosted models | At least one verified hosted provider, selectable by the user |
| Enterprise endpoint | Configurable base URL, deployment/model ID, auth strategy, timeouts, proxy and CA settings |
| Offline mode | Manual editing, exports, docs, local model access; no cloud fallback |

Adapters normalize streaming, cancellation, context limits, tool/schema support,
usage reporting, and errors. Use native adapters where compatibility endpoints omit
needed behavior. Ollama documents partial API compatibility; verify individual
features rather than assuming endpoint interchangeability.
[Ollama compatibility](https://github.com/ollama/ollama/blob/main/docs/api/openai-compatibility.mdx).

Create provider contract fixtures without real inference. Before claiming support,
run a manual acceptance exercise against one local model and one hosted/enterprise
deployment. Models without reliable structured output can support explanation and
suggestions; visibly disable unsupported write tools.

Start context assembly with the selection, relevant scene/components, API reference,
and recent errors. Add file search as needed; defer embeddings/vector databases
until retrieval quality demands them. Show what leaves the machine, support content
exclusions, and redact secrets before constructing prompts. Label token/cost estimates
as estimates, show actual usage when available, and allow per-task limits. Never
retry indefinitely or silently switch to a paid model.

Keep credentials in an OS credential store or a dedicated provider worker, never
projects, game bundles, or inherited preview environment variables. Restrict file
operations to project roots and prevent traversal/symlink escapes. Project text and
model requests cannot grant themselves permissions. Use private, bounded IPC for
worker commands/results; deserialize data, never arbitrary Python objects from an
untrusted worker.

Run Python game previews in a separate process so crashes and runaway loops can be
terminated without losing editor state. **A subprocess is not a sandbox.** Before
running untrusted/generated code, implement and verify a Linux sandbox policy, such
as bubblewrap with a read-only project snapshot, isolated writable save directory,
restricted filesystem/process access, no credentials, and network disabled by
default. Expose only necessary display/audio resources. Use explicit permissions for
networked games. Validate the sandbox both for native launch and container launch;
nested namespace restrictions can differ. If isolation is unavailable, do not
silently execute untrusted code; provide a clear trusted-project execution choice.
Bubblewrap supplies mechanisms; the caller must define the actual policy.
[Bubblewrap security model](https://github.com/containers/bubblewrap).

Enterprise readiness is incremental: v0.1 is intended to provide endpoint flexibility, local-only
policy, exclusions, and bounded audit metadata. Central SSO, organization roles,
centrally enforced policy, and multi-user hosting come later. A single-user Docker
deployment is not automatically enterprise-secure because it accepts an enterprise
endpoint. Provider retention/residency depends on its deployment and contract.

## 7. Docker: native desktop app and separate test container

**Retain containerization using separate native desktop run and test images**, as
Life Helper does. Docker launches the Python/Qt application and forwards its window
to the host Wayland compositor. It does not host a webpage or remote desktop UI.
Keep a direct native launcher available as well.

| Image/service | Responsibility | Isolation |
| --- | --- | --- |
| `Dockerfile.run` / `desktop` | Native editor and standalone preview support | Selected project/config volumes, current Wayland socket, required audio/GPU access only |
| `Dockerfile.test` / `test` | Ruff, Python type checking, focused pytest/pytest-qt | Offscreen Qt, temporary projects, no host display or credentials |
| Optional model service | Local inference, separate model storage | Explicit enablement; not part of normal tests |

The desktop and test services are implemented. The app currently mounts the current
Wayland socket, persistent `/projects` and user-preferences volumes. Audio forwarding
is opt-in through `compose.audio.yaml`; explicit GPU mapping and model services remain
unimplemented. Both runtime
services have networking disabled. Dependency installation precedes source copying
so code-only rebuilds reuse the dependency layer. Test-only packages stay in the
test image. The default test command runs Ruff, formatting, mypy, and pytest.

Share the Python version, lockfile, source revision, and needed native libraries.
Use a common dependency stage or otherwise keep the two Dockerfiles synchronized;
install test extras only in the test image. Pin images and cache dependency downloads.
Docker supports separating build/runtime dependencies with multi-stage builds.
[Docker multi-stage builds](https://docs.docker.com/build/building/multi-stage/).

Use a non-root user matching the host UID/GID. Forward only the current Wayland
socket, not the entire runtime directory. Add specific render devices and audio
sockets only if the selected backend requires them. No privileged mode, Docker
socket mount, broad home-directory mount, or blanket display access changes.
Keep the local-only configuration network-disabled; model access is a deliberate
configuration with explicit endpoints. Unlike Life Helper's entirely offline
container, the model-enabled configuration must support the chosen local/enterprise
endpoint. Do not silently enable network access in previews or tests.

Use `compose.yaml` for the native app and a standalone `compose.test.yaml` for tests.
This avoids requiring Wayland environment variables or evaluating host display
mounts on a headless runner. These foundation commands are implemented.
Native and container Wayland startup/shutdown smoke checks have passed. Broader
compositor/GPU compatibility and performance checks are still pending:

```sh
# Native desktop window through Wayland
docker compose up --build desktop

# Independent headless test container; propagate its exit status
docker compose -f compose.test.yaml run --build --rm test

# Direct native development workflow
uv sync --frozen
uv run --frozen solar-forge-engine

# Same focused tests without Docker
QT_QPA_PLATFORM=offscreen uv run --frozen --extra test pytest -q
```

Test configuration uses `QT_QPA_PLATFORM=offscreen`, no inference, and temporary
data/cache/config directories. The demo provider fixtures run offline today. Never mount a live project
or production secrets. Capture reports before cleanup; verify an intentionally
failing fixture fails CI. Document volume persistence and cleanup without encouraging
deletion of user projects. Separate ephemeral test storage from persistent app data.

Offscreen tests cover widget behavior, not real compositor, GPU, audio, or input
compatibility. Run a small native Wayland smoke check on Arch for releases. If a
backend needs a display for integration tests, add an isolated virtual display only
to that test job; do not expose the user's desktop. Confirm native and container
launches have consistent project behavior and acceptable performance.

Container GPU inference is optional and host-specific. Support a host model server
when necessary. Container `localhost` means the container; document host routing or
Compose DNS and endpoint binding. Never expose inference endpoints publicly by
default. The engine's own interface remains entirely native.

Use the Life Helper image strategy as a starting point, then validate required Qt,
audio and rendering libraries. A Debian-based Python container can run on Arch;
it does not replace testing Arch packaging and host drivers. Native editor packages
and exported games must not require Docker.

## 8. Performance and focused verification

These budgets are hypotheses. Establish a reference Arch laptop, compositor, driver, resolution,
and fixture in phase 0. Measure startup separately from image pulls, builds, model
startup, and downloads.

| Metric | Initial target / measurement |
| --- | --- |
| Editor usable | Under 2 seconds warm, under 5 seconds cold from native process launch |
| Enter Play | Under 1 second for the reference game after assets load |
| Editor actions | Under 100 ms at p95 for selection and property changes |
| Rendering | 60 fps target; p95 frame time below 16.7 ms on a defined 1,000-sprite scene |
| Idle editor memory | Under 250 MiB editor RSS; report preview/workers/model separately |
| Editor distribution | Record installed and download sizes with Python/Qt included; set a budget after the packaging spike |
| Starter export | Record full native bundle size including Python/Qt; set a measured budget in phase 0 |
| Routine checks | Under 30 seconds with warm dependencies on the reference machine |
| Critical native UI suite | Under 2 minutes, excluding initial image download/build |

Recorded evidence so far: the initial software rectangle fixture reported median
4.805 ms and p95 4.953 ms. The October 5 sprite fixture (1,000 moving items sharing
one 16×16 transparent RGBA texture, 10 warmup/120 measured frames, 1024×576 QImage,
Python 3.14.7 / Qt 6.11.2 on Arch) reported median 3.622 ms and p95 3.910 ms.
The rectangle comparison reported median 5.361 ms and p95 5.645 ms. These are
software rendering measurements, not native presentation. Updated distinct-texture
and native first-paint results are recorded near the top and in the linked reference
report; the complete renderer gate remains open.
The 30-test suite passed locally in 1.26 seconds and in Docker in 1.57 seconds;
pytest timings exclude lint, type checks, image builds and downloads. Warm startup
to first Qt paint and RSS after startup workers settle are now measured. Cold-cache
startup, editor-action latency, steady-state idle memory, distribution and export
budgets remain unmeasured.
Do not treat the software fixture as proof of the native 60 fps presentation target.

If a budget fails, measure before adding complexity or revising it. Lazy-load code
editing/optional panels, virtualize large asset lists, cache imports by content hash,
and move heavy processing off the UI thread. Keep AI out of the runtime loop.
Add frame-time, memory, and load measurements before building a profiler UI.

Tests earn their place by catching meaningful failures:

- Unit/contract: command validation, atomic undo, scene round trips, migrations,
  stable references, path restrictions, provider errors and cancellation.
- Runtime integration: movement/collision rules and resource disposal on restart.
- Native UI: create/edit/save/reopen; apply AI fixture and undo; export and play without
  editor/provider dependencies. Add flows only for distinct costly risks.
- Boundary checks: reject unauthorized requests; prove preview code cannot access
  editor credentials or unrelated user files. Allow only the project snapshot,
  isolated saves, and explicitly required runtime libraries/devices.
- Performance: fixed-fixture milestone reports; avoid noisy per-commit timing gates
  until repeatability is established.

Use deterministic provider fixtures in CI. Real-model acceptance is separate, with
an explicit budget and consent. Document manual UX/graphics checks. No arbitrary
coverage percentage, screenshot suite for every control, or tests copying the
implementation. Data-integrity and permission tests are worth their cost.

## 9. Delivery phases and exit criteria

Build one usable vertical slice before expanding. Estimates depend on staffing and
experience; these milestones are gates, not promised delivery dates.

| Phase | Current status | Remaining exit work |
| --- | --- | --- |
| 0 — Prove foundation | Partial: dependencies, native viewport/player, Wayland launch, software fixture verified | Representative sprite and presentation budgets, isolation policy, packaging spike, reference hardware record and backend ADR |
| 1 — Reliable workspace | Partial: multiple authored scenes, project folders, relative assets, path/hash validation, recovery, save/reopen, upgrades, undo and Docker tests | Scene organization, expanded recovery guarantees and complete project integrity checks; CI automation still absent |
| 2 — Playable 2D slice | Partial: editable collector, PNG sprites, configurable movement/key presets, walls, coin triggers, HUD and restart | Expanded asset libraries/animation clips, audio, arbitrary key bindings/behaviors, sandboxed Python lifecycle and independent Linux export tested on clean Arch |
| 3 — Useful assistant | Partial: offline demo proposals, readable diffs, validated atomic edits, undo/revision protection and cancellation | Verified local/hosted models, compact model context, request timeouts, privacy and credential handling |
| 4 — v0.1 polish | Not started as a release milestone; basic theme, shortcuts and help already exist | Arch distribution, recovery/onboarding/accessibility checks, measured budgets, first-time-user exercise and release documentation |
| 5 — Validated expansion | Deferred | Feedback justifying tilemaps, SDK, additional native platforms and enterprise governance |

The v0.1 release includes phases 0–4. Export is an architectural check in phase 2,
not an end-of-project feature. Avoid polishing a broad assistant before manual
editing is useful. Trial UX throughout development.

Completed task checklist:

- [x] Scaffold the Python package, pinned dependencies, uv lockfile, Ruff, mypy and launcher.
- [x] Implement a versioned scene schema and create/update/delete commands.
- [x] Connect native viewport, inspector, scene tree and local scene persistence.
- [x] Verify atomic undo/redo, stale revisions, validation and save-failure preservation.
- [x] Implement separate Docker desktop/test images and verify failure propagation.
- [x] Implement data-only native Play with state separation, pause/restart and Stop.
- [x] Measure a repeatable software rendering fixture.
- [x] Implement the editable collector and verify a complete route around its walls.
- [x] Persist gameplay roles and protect version-one originals during save upgrades.
- [x] Add selected-object duplication with Ctrl+D through validated, undoable commands.
- [x] Import bounded PNG sprites with portable pixels and shared cached native rendering.
- [x] Benchmark a transparent shared-texture sprite fixture.
- [x] Benchmark distinct sprite textures, canvas construction and isolated native warm startup.
- [x] Instrument native viewport paint cadence, update/paint CPU and synthetic selection latency.
- [x] Profile repaint/index policies across light/heavy motion with natural dirty-region updates.
- [x] Benchmark actual Play animation and selectively redraw dense frame changes without slowing sparse updates.
- [ ] Close the complete renderer/sandbox/packaging foundation gates.
- [x] Add validated project-folder creation/opening around existing scenes.
- [x] Add relative, content-addressed sprite assets with validated loading and upgrade backups.
- [x] Add a bounded native sprite palette with previews and undoable reuse/application.
- [x] Add bounded project autosave, user-controlled crash recovery, and in-flight save protection.
- [x] Preserve recovery conflicts and invalid snapshots with worker-based validated cleanup.
- [x] Add bounded multiple-scene creation/browsing and safe switching with per-scene recovery.
- [x] Add asynchronous saved-scene project sprite indexing and cross-scene reuse.
- [x] Add undoable per-object movement speed and WASD/arrows presets with compatible scene upgrades.
- [x] Add single-object viewport dragging, cancellation, and optional grid snapping.
- [x] Add pointer-centered wheel zoom, toolbar/keyboard zoom, middle-button pan and Fit scene for distant objects.
- [x] Add view-only object name/ID search, combined role filters, counts and keyboard focus.
- [x] Add session-only viewport drag locks, bulk decoration locking, markers and safe cancellation.
- [x] Persist per-scene drag locks in local editor preferences with background I/O and close flushing.
- [x] Group Inspector properties with adaptive forms and an always-visible Apply action.
- [x] Add sprite palette search, clearer thumbnail entries and safe filtered reuse.
- [x] Add validated object draw ordering, boundary-aware actions and consistent editor/Play stacking.
- [x] Add undoable scene-title editing without changing project file/startup paths.
- [x] Add bounded unused-file review, reference protection, revalidation and reversible quarantine.
- [x] Add native bounded quarantine browsing and exclusive, revalidated restoration.
- [x] Add explicit startup-scene selection with validation and atomic manifest updates.
- [x] Add bounded looping sprite-sheet animation, first-frame editor rendering, and deterministic Play timing/restart.
- [x] Ship Ember Run: an animated, playable forge showcase and compact editable two-scene example.
- [x] Add worker-based single-file quarantine purge with fresh review, default-No confirmation and revalidation.
- [x] Add background manual saving, observed external-edit checks and directory flushing.
- [x] Coordinate concurrent engine scene saves with nonblocking publication locks and process-exit recovery.
- [ ] Add stronger concurrent-edit and power-loss recovery guarantees.
- [x] Add bounded project WAV import, portable deduplication and optional native/Docker PipeWire preview.
- [x] Add undoable portable collection sounds and one-voice, restart-safe native Play audio.
- [x] Add runtime-only native active-scene export and verified editor-free playback.
- [ ] Bundle runtime dependencies and verify exported games on clean Arch.
- [x] Measure a copied Widgets-only Qt subset and verify editor-free exports on host and Docker Wayland.
- [ ] Add sandboxed Python game scripting.
- [x] Connect an offline fake provider through bounded scene tools and reviewed atomic edits.
- [x] Add an opt-in Ollama loopback adapter with bounded metadata, deadlines and cancellation.
- [x] Add bounded installed-model discovery and worker-based saved local preferences, preserving offline startup.
- [x] Add model capability preflight and verify live local proposals, native review, Apply and Undo.
- [ ] Add verified local and enterprise model adapters, timeouts and credential handling.

Next small features, in recommended order:

1. Continue scene organization and project integrity work; stronger concurrent-edit
   and power-loss recovery guarantees remain open.
2. Package native runtime dependencies and verify the independent game export
   on clean Arch. Measure bundle size and startup, preserving the lightweight option.
   The [packaging spike](architecture/0001-runtime-packaging.md) proves an 80 MiB
   Qt subset with actual copies; interpreter bundling, notices and clean-machine
   dependency verification remain open.
3. Prove a native and container-compatible sandbox before enabling imported/generated
   Python behaviors. Add the minimal script lifecycle and terminate/recovery checks.
4. Connect local and enterprise provider adapters after the initial fake-provider
   workflow and scene-edit review are verified. Script-edit tools depend on the
   sandboxed execution path.

Continue committing coherent small features. Do not repeat finished scaffolding or
replace the working native approach while closing the remaining milestone gates.

## 10. Risks, decisions, and release discipline

| Risk | Response |
| --- | --- |
| Infrastructure crowds out usability | One reference game; reuse a framework if the spike supports it |
| AI corrupts work or invents APIs | Typed commands, current API context, validation, revisions, undo |
| Small local models struggle | Capability detection, compact context, narrower operations, manual fallback |
| Editor leaks into exports | Independent runtime entry point; inspect and execute exports in CI |
| Preview hangs or escapes permissions | Isolation spike, restricted IPC/filesystem/network, restart path, boundary tests |
| Docker slows routine work | Cached stages, small images, native dev option, offscreen tests and optional model images |
| Extensions destabilize editor | Built-ins first, versioned contracts, permissions, disable/recovery path |
| Scope grows indefinitely | 2D release gates; defer work outside reference workflows |

Fixed direction: native Arch Linux desktop, Python/PySide6, Python game scripting,
native Linux exports, and no JavaScript/TypeScript or web UI. Default assumptions:
local single-user authoring, no account, keyboard/mouse first, and Wayland first.
Other native OS support, minimum hardware, first enterprise provider, and licensing
remain open decisions. Choose the engine license before external release; document
third-party notices and template/asset licenses. Never infer a license for imported
or generated content.

Maintain a changelog, semantic project-format versions, migration fixtures, and short
ADRs. Commit small, coherent working checkpoints. Root [`AGENTS.md`](../AGENTS.md)
defines model coding, testing, and commit rules. Keep progress honest: a proposed
command is not an implemented feature, and a mocked test does not prove real-model
quality.
