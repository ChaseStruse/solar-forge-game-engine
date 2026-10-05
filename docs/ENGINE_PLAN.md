# Solar Forge Game Engine — product and implementation plan

Status: proposed direction, October 4, 2026. This repository contains planning
documents only. Commands and layouts below are intended implementation contracts,
not existing functionality. Performance numbers are targets to validate.

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
training, and autonomous background agents. Mobile browser controls and native game
packaging can follow validated demand.

## 2. The first complete experience

The reference game is a small top-down coin collector with movement, collisions,
a score, sound effects, and a restart button.

1. Create a project from a starter template, choosing its local folder.
2. Press Play immediately; keyboard controls and the objective already work.
3. Drag a sprite into the scene and edit it in the inspector.
4. Ask: “Make the player faster and add five coins away from walls.”
5. Inspect the proposed changes, apply them, and preview the result.
6. Undo the change as one action or adjust individual objects manually.
7. Save, close, reopen, and export a static web game.

An equivalent manual workflow must work with AI disabled. The export must run from
a static server without contacting the editor or a model provider.

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
| Export | Self-contained static web build and export validation | Desktop game packages, mobile targets |

Use a restrained graphite theme with solar amber accents, readable typography,
clear selection states, and minimal decorative motion. Share Solar Forge Studios
design tokens when available. Support keyboard navigation, visible focus, scalable
text, accessible contrast, reduced motion, and color-independent error indicators.

Place the scene tree left, viewport center, inspector right, and assets/console
below. Make the assistant collapsible. Provide a searchable command palette,
shortcuts, contextual help, empty states, and plain-language errors with a next step.
Remember layout preferences locally. Avoid mandatory onboarding or a login wall.

## 4. Architecture and provisional stack

Recommend a **TypeScript monorepo with a browser-based editor served by a small
local companion service**. This fits Docker and permits a later desktop wrapper.
The browser renders on the user's GPU; it is not a GUI running in Docker. The
companion owns project file access, imports, builds, and model credentials.

| Layer | Proposed choice | Reason / validation requirement |
| --- | --- | --- |
| Editor | React, TypeScript, Vite | Familiar tooling; keep frame-by-frame game state outside React |
| Runtime | Small scene/component runtime; PixiJS candidate | Control over serialization and editing; prove gameplay implementation is affordable |
| Alternative runtime | Phaser candidate | Existing gameplay systems may reduce implementation effort |
| Companion | Node.js LTS, narrow HTTP API | Share schemas/types; restrict file access to open project roots |
| Project format | Versioned JSON, ordinary assets and TypeScript | Inspectable, portable, suitable for version control |
| Validation | Shared runtime schemas; library selected during foundation work | One source of truth for loading, UI, AI tools, and migrations |
| Testing | Vitest for contracts; Playwright for critical flows | Fast checks with limited browser automation |
| Distribution | Docker for development/self-hosting; desktop packaging after v0.1 proof | Keep development infrastructure optional for end users |

PixiJS is a rendering foundation with WebGL and WebGPU support, not the whole
engine. We would still own gameplay systems. Its rendering and extension model
make it worth evaluating. [PixiJS application](https://pixijs.com/8.x/guides/components/application),
[architecture](https://pixijs.com/8.x/guides/concepts/architecture).

Before committing, build the same tiny scene in PixiJS and Phaser: animation,
movement, collisions, live edits, save/reload, and export. Compare engineering cost,
startup, bundle size, memory, and integration friction. Phaser already offers
gameplay systems including input and physics; choose it if it substantially shortens
delivery within the budgets. Do not ship two runtimes.
[Phaser framework](https://www.phaser.io/phaser4).

Do not fork Godot or write a renderer for v0.1. Reconsider a Godot-based approach
only if the spike shows the web architecture cannot meet requirements. Record the
chosen stack and supported versions in an architecture decision record (ADR). Pin
dependencies and use one package manager and lockfile.

Introduce these boundaries only as implementation needs them:

```text
apps/editor/             UI and editor state
apps/companion/          Local project I/O, builds, model gateway
packages/core/           Project schemas, commands, validation, migrations
packages/runtime/        2D execution; no editor or model dependencies
packages/ai/             Provider adapters, context, tool orchestration
templates/               Small playable starter projects
tests/                   Integration fixtures and critical browser flows
docs/                    Decisions, contracts, guides
```

Dependency direction: editor and companion use core; AI submits core commands;
runtime consumes validated game data. Core cannot import the editor or providers.
Avoid microservices, a database, event sourcing, or a custom ECS architecture until
a concrete need appears.

## 5. Project model, runtime, and extension contracts

A project contains `project.json`, `scenes/`, `assets/`, and `scripts/`. Ignore
generated caches and builds. Use stable IDs and relative asset references, with
separate scene files for manageable diffs. Never store keys or machine-specific
absolute paths in projects.

Use a scene graph with typed components such as Transform2D, Sprite, Camera2D,
Collider2D, AudioSource, and Behavior. Separate authoring state from play state;
stopping preview restores the authored scene. Offer a small script API such as
`onStart`, `onUpdate`, and `onCollision`, with documented lifecycle and cleanup.
Use fixed simulation steps with bounded catch-up, independently scheduled rendering,
and explicit pause/focus behavior. Start with simple collision shapes and triggers.

All mutations enter shared commands such as `createEntity`, `setProperty`,
`attachComponent`, `instantiateScene`, and `applyScriptPatch`. Commands have stable
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
TypeScript interfaces alone are not a security boundary.

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

Keep credentials in the companion or OS credential store, never browser storage or
exports. Bind the local service to loopback with origin checks and session
authentication. Protect project APIs against traversal and symlink escapes. Project
text and model tool requests cannot grant themselves permissions.

Run previews on an isolated origin in a restricted iframe or equivalent boundary;
never expose companion tokens, editor DOM, filesystem handles, or model keys. Use
network restrictions by default and explicit capabilities when games need network
access. Validate this boundary during the architecture spike. Handle runaway scripts
with a way to terminate and restart the preview.

Enterprise readiness is incremental: v0.1 provides endpoint flexibility, local-only
policy, exclusions, and bounded audit metadata. Central SSO, organization roles,
centrally enforced policy, and multi-user hosting come later. A single-user Docker
deployment is not automatically enterprise-secure because it accepts an enterprise
endpoint. Provider retention/residency depends on its deployment and contract.

## 7. Docker: separate application and test execution

**Use separate application and test containers.** Share dependency/build stages,
lockfile, and source revision while keeping testing tools out of the application.
Docker documents multi-stage builds for this separation and Compose profiles for
optional services. [Multi-stage builds](https://docs.docker.com/build/building/multi-stage/),
[Compose profiles](https://docs.docker.com/reference/compose-file/profiles/).

| Service | Responsibility | Lifecycle |
| --- | --- | --- |
| `app` | Compiled editor and companion; chosen project volume | Default application profile |
| `dev` | Editor hot reload and companion watch process | Optional development profile |
| `test` | Type checks, lint, focused unit/contract tests | Disposable; no app dependency |
| `test-app` | Production app build with temporary projects and fake provider | Integration/E2E profile only |
| `e2e` | Browser flows against `test-app` | Disposable; wait for readiness |
| `ollama` | Optional inference with separate model storage | Explicit opt-in profile |

Use a multi-stage application Dockerfile with dependency, build, test, and runtime
targets. Give E2E its own browser-capable image matched to its automation version.
Keep routine tests in the smaller image. Pin images, run non-root, use a
`.dockerignore`, cache dependency downloads, and never mount the Docker socket.
Pass credentials at runtime, excluding them from image layers and test fixtures.

Tests must never mount live user projects or production credentials. Use temporary
storage and unique Compose project names in CI. Capture reports before cleanup,
propagate failure to CI, and clean up even when tests fail. Do not use live inference
in the normal suite.

Planned developer interface, to implement and verify during foundation work:

```sh
docker compose up --build app
docker compose --profile dev up --build dev
docker compose run --build --rm test
docker compose --profile e2e up --build --abort-on-container-exit --exit-code-from e2e
```

Configure `app` with its own profile so explicitly targeting it starts it, while an
E2E profile starts only `test-app` and `e2e`. Define readiness/dependencies explicitly.
Verify these commands return the intended exit status using an intentionally failing
fixture. Keep app/dev ports from competing and document teardown and CI isolation
once configuration exists.

Docker standardizes the toolchain; it does not automatically accelerate builds,
graphics, or inference. Containers add image/download/storage costs. Cache builds,
avoid installing a browser for unit tests, and retain native development commands.
GPU inference is optional and host-specific. Where container GPU support is
unsuitable, connect to a host model server. Container `localhost` means that
container: document a supported host connection or use Compose DNS. Do not expose
inference endpoints publicly by default.

For end users, evaluate a desktop wrapper after the browser workflow works. Tauri
is a candidate with capability controls, but companion packaging and per-OS testing
are additional work. [Tauri capabilities](https://v2.tauri.app/security/capabilities/),
[sidecars](https://v2.tauri.app/develop/sidecar/).
Do not require Docker for the eventual desktop editor or exported games. Desktop
packaging may need native OS runners even when core tests use Docker.

## 8. Performance and focused verification

These budgets are hypotheses. Establish a reference laptop, OS, browser, resolution,
and fixture in phase 0. Measure startup separately from image pulls, builds, model
startup, and downloads.

| Metric | Initial target / measurement |
| --- | --- |
| Editor usable | Under 2 seconds warm, under 5 seconds cold, service already ready |
| Enter Play | Under 1 second for the reference game after assets load |
| Editor actions | Under 100 ms at p95 for selection and property changes |
| Rendering | 60 fps target; p95 frame time below 16.7 ms on a defined 1,000-sprite scene |
| Idle editor memory | Under 250 MiB incremental browser memory; report companion separately |
| Initial editor JS | Under 2 MiB compressed, excluding lazy-loaded tools |
| Starter export | Under 1 MiB compressed code, excluding assets; revisit after runtime spike |
| Routine checks | Under 30 seconds with warm dependencies on the reference machine |
| Critical browser suite | Under 2 minutes, excluding initial image download/build |

If a budget fails, measure before adding complexity or revising it. Lazy-load code
editing/optional panels, virtualize large asset lists, cache imports by content hash,
and move heavy processing off the UI thread. Keep AI out of the runtime loop.
Add frame-time, memory, and load measurements before building a profiler UI.

Tests earn their place by catching meaningful failures:

- Unit/contract: command validation, atomic undo, scene round trips, migrations,
  stable references, path restrictions, provider errors and cancellation.
- Runtime integration: movement/collision rules and resource disposal on restart.
- Browser: create/edit/save/reopen; apply AI fixture and undo; export and play without
  editor/provider dependencies. Add flows only for distinct costly risks.
- Boundary checks: reject unauthorized requests; prove preview code cannot access
  editor credentials or host project APIs.
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
| 0 — Prove foundation | Runtime comparison, preview isolation spike, schema sketch, baseline measurements | Select one runtime in an ADR; record risks and budgets |
| 1 — Reliable workspace | Shell, companion, storage, command/undo layer, Docker app/test targets | Create/save/reopen scene; atomic undo; test failures fail CI |
| 2 — Playable 2D slice | Coin collector, input, collisions, audio, HUD, scripts, export | Manually editable game runs independently of editor |
| 3 — Useful assistant | Context, local/hosted adapters, diffs, commands, patch validation | Bounded task succeeds on verified local and hosted deployments; cancel/undo/offline work |
| 4 — v0.1 polish | Assets, recovery, onboarding, accessibility, budgets, docs | First-time user exercise passes; export contains no secrets or AI dependency |
| 5 — Validated expansion | Desktop packaging, tilemaps, templates, SDK, enterprise governance | Each addition justified by feedback and independently scoped |

The v0.1 release includes phases 0–4. Export is an architectural check in phase 2,
not an end-of-project feature. Avoid polishing a broad assistant before manual
editing is useful. Trial UX throughout development.

First implementation tasks, in dependency order:

1. Record baseline hardware, compare runtime candidates, and select one.
2. Scaffold strict TypeScript, package scripts, formatting, pinned dependencies.
3. Define a versioned project/scene schema and three reversible commands.
4. Build local project I/O, viewport, and inspector around those commands.
5. Add Docker app/test targets and one save/load/undo contract fixture.
6. Implement the playable template and independent web export.
7. Connect AI to proven commands through a fake provider, then real adapters.

## 10. Risks, decisions, and release discipline

| Risk | Response |
| --- | --- |
| Infrastructure crowds out usability | One reference game; reuse a framework if the spike supports it |
| AI corrupts work or invents APIs | Typed commands, current API context, validation, revisions, undo |
| Small local models struggle | Capability detection, compact context, narrower operations, manual fallback |
| Editor leaks into exports | Independent runtime entry point; inspect and execute exports in CI |
| Preview hangs or escapes permissions | Isolation spike, restricted bridge/network, restart path, boundary tests |
| Docker slows routine work | Cached stages, small images, native dev option, optional browser/model images |
| Extensions destabilize editor | Built-ins first, versioned contracts, permissions, disable/recovery path |
| Scope grows indefinitely | 2D release gates; defer work outside reference workflows |

Default assumptions: local single-user authoring, web export first, no account,
TypeScript scripting, keyboard/mouse first, Linux as the initial development host.
Desktop OS support, minimum hardware, first enterprise provider, and licensing are
open decisions. Choose the engine license before external release; document
third-party notices and template/asset licenses. Never infer a license for imported
or generated content.

Maintain a changelog, semantic project-format versions, migration fixtures, and short
ADRs. Commit small, coherent working checkpoints. Root [`AGENTS.md`](../AGENTS.md)
defines model coding, testing, and commit rules. Keep progress honest: a proposed
command is not an implemented feature, and a mocked test does not prove real-model
quality.
