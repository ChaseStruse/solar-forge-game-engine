# Solar Forge Game Engine — product and implementation plan

Status: implementation started, October 4, 2026. The native scene editor foundation
is implemented. The architecture and later milestones below describe intended work;
performance numbers remain targets, not measured guarantees.

### Implemented foundation checkpoints

- Python 3.14, PySide6 Essentials 6.11.2, uv lockfile, Ruff, mypy and focused pytest.
- Native Qt shell, Graphics View rectangles, scene tree, property inspector, and
  create/update/delete commands with transactional undo/redo and revision checks.
- Version-one `.forge.json` scene documents, bounded/validated loading, atomic writes,
  and unsaved-change handling on New/Open/Close.
- Core integrity tests and one native edit/save/reopen workflow; offscreen visual QA.
- Separate non-root Docker desktop/test images and independent headless test Compose;
  the native app forwards its window through Wayland and keeps networking disabled.
- Native Play process receiving a bounded, validated JSON snapshot over stdin;
  shared rectangle renderer, fixed-step keyboard movement, pause, restart and Stop.
  Authored scenes remain unchanged. Isolated Python startup ignores working-directory
  packages and Python path environment overrides; no project Python code executes.
- Editable coin-collector starter: Player/Wall/Coin/Decoration roles, static
  axis-aligned wall collisions, coin triggers, score/completion HUD, and restart.
  Version-two scenes persist roles; version-one loads without changing disk data,
  and Save creates a non-overwriting `.v1.bak` before writing the upgraded format.
- Repeatable 1,000-moving-rectangle software benchmark at 1024×576: 10 warmup frames,
  120 measured frames. Initial Arch host run: median 4.805 ms, p95 4.953 ms, Python
  3.14.7 / Qt 6.11.2 / offscreen QImage rendering. This does not establish sprite,
  compositor or GPU budgets; the complete backend selection gate remains open.

Verification: the foundation had 12 focused tests; playback adds movement,
keyboard/pause/restart, and subprocess lifecycle checks. The collector adds collision,
score/reset, starter persistence, migration backup, invalid roles, and a complete
starter route around the walls for 21 tests total. Ruff,
formatting, and strict mypy pass. Native and container Play startup/shutdown were
verified on the Arch host's Wayland session, with authored scene data unchanged.
An intentionally failing test previously returned exit status 1 in the independent
test container. This does not validate an arbitrary-code sandbox or establish full
compositor/GPU compatibility.

This is a small authoring slice, not a completed phase 0 or phase 1. Project folders,
assets, audio, sandboxed script execution, AI, and native game exports are not
implemented. A single scene file deliberately precedes multi-file project persistence.
The Qt backend remains provisional pending sprite and native presentation benchmarks. See the README
for commands that are actually runnable; later commands below are design targets.

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

Suggested structure, introduced as needed:

```text
pyproject.toml
uv.lock
src/solar_forge_engine/
    editor/             Qt Widgets, inspector, native viewport and panels
    core/               Data schemas, reversible commands, migrations
    runtime/            Simulation, rendering/audio adapter, standalone player
    ai/                 Provider adapters, context, tool orchestration
    project/            File I/O, assets, recovery and native export
    __main__.py         Native editor entry point
resources/              Icons, themes and desktop integration assets
templates/              Python game scripts and sample assets
tests/                  Focused contracts and native UI checks
packaging/              Arch package recipe and game bundle configuration
Dockerfile.run
Dockerfile.test
compose.yaml
compose.test.yaml
```

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

A project contains `project.json`, `scenes/`, `assets/`, and Python `scripts/`. Ignore
generated caches and builds. Use stable IDs and relative asset references, with
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

Enterprise readiness is incremental: v0.1 provides endpoint flexibility, local-only
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
mounts on a headless runner. These foundation commands are implemented; container
compositor/GPU compatibility still requires a native host smoke check:

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

Test configuration uses `QT_QPA_PLATFORM=offscreen`, deterministic provider fixtures,
no inference, and temporary data/cache/config directories. Never mount a live project
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

| Phase | Deliverable | Exit criterion |
| --- | --- | --- |
| 0 — Prove foundation | Python/Qt viewport, native player, Wayland/sandbox and packaging spikes | Validate native backend, isolation, dependency versions and measured budgets on Arch |
| 1 — Reliable workspace | Qt shell, project storage, command/undo layer, Docker run/test images | Create/save/reopen scene; atomic undo; test failures fail CI |
| 2 — Playable 2D slice | Coin collector, input, collisions, audio, HUD, Python scripts, Linux export | Native exported game runs on clean Arch without editor or Docker |
| 3 — Useful assistant | Context, local/hosted adapters, diffs, commands, patch validation | Bounded task succeeds on verified local and hosted deployments; cancel/undo/offline work |
| 4 — v0.1 polish | Arch packaging, assets, recovery, onboarding, accessibility, budgets, docs | First-time user exercise passes; export contains no secrets or AI dependency |
| 5 — Validated expansion | Tilemaps, templates, SDK, enterprise governance, other native platforms | Each addition justified by feedback and independently scoped |

The v0.1 release includes phases 0–4. Export is an architectural check in phase 2,
not an end-of-project feature. Avoid polishing a broad assistant before manual
editing is useful. Trial UX throughout development.

First implementation tasks, in dependency order:

1. Validate Python/PySide6 compatibility, native rendering, Wayland and packaging.
2. Scaffold the Python package, uv lockfile, Ruff, type checks and native launcher.
3. Define a versioned project/scene schema and three reversible commands.
4. Build local project I/O, native Qt viewport, and inspector around those commands.
5. Add separate Docker desktop/test images and one save/load/undo contract fixture.
6. Implement the playable template and independent native Linux export.
7. Connect AI to proven commands through a fake provider, then real adapters.

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
