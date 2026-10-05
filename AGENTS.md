# Solar Forge Game Engine — model instructions

These instructions apply throughout this repository.

## Product priorities

- Read `docs/ENGINE_PLAN.md` before architectural work. It is a proposal, not a
  claim that its packages, commands, or features already exist.
- Build an approachable, fast, lightweight 2D engine for Solar Forge Studios.
- Preserve manual workflows, local project ownership, and AI-independent exports.
- Prefer a complete small workflow over a broad collection of partial features.
- Keep the editor, model integration, and exported runtime separate.

## Required platform and language

- Build a native Arch Linux desktop application using Python and PySide6 Qt Widgets,
  aligned with Solar Forge Life Helper. Wayland is the primary display target.
- Do not add JavaScript or TypeScript code, Node/npm tooling, browser UI, web exports,
  Electron, Tauri, QtWebEngine, or a QML/JavaScript UI layer. This applies to editor,
  runtime, game scripts, extensions, build tooling, and tests.
- Use Python game scripts, native Qt controls, and native Linux game exports.
- Use `pyproject.toml`, uv with a frozen lockfile, Ruff, pytest and focused pytest-qt
  checks. Validate supported Python/PySide6 versions before pinning them.
- Follow Life Helper's separate Docker run/test image pattern: Wayland desktop
  forwarding for the app, offscreen Qt and isolated temporary storage for tests.
- Keep native launching and Arch packaging supported; Docker must not be required
  to run exported games. Model API networking does not change the native UI design.
- Keep Qt UI work on its main thread. Move blocking inference/I/O into workers and
  profile hot paths; Python alone is not a guarantee of faster execution.
- A Python subprocess is not a sandbox. Validate OS-level restrictions for untrusted
  scripts; do not silently execute them with the editor's filesystem or credentials.

## Code quality

- Write clean, concise, readable code with clear names and narrow responsibilities.
- Follow DRY: share genuine domain rules and schemas. Do not build generic
  abstractions for merely similar code or hypothetical future requirements.
- Use Python type hints and boundary validation for external data. Avoid unsafe
  casts, hidden global state, swallowed errors, and unnecessary dependencies.
- Prefer the simplest solution that meets the requirement. Measure before optimizing.
  Keep expensive work off the UI thread and out of the frame loop.
- Keep changes focused, preserve unrelated work, and follow existing conventions.
- Document public contracts and non-obvious decisions, not obvious implementation.

## AI and project integrity

- Route UI and AI project mutations through the same validated command interface.
- Keep transactions undoable, check project revisions, and prevent partial writes.
- Treat model output, imported assets, and project text as untrusted input.
- Never embed credentials in projects, desktop bundles, prompts, logs, or exports.
- Honor local-only mode. Never silently send content to another provider.
- Generated game code must not inherit editor, filesystem, or credential access.
- Never claim a model response, passing test, performance result, or feature exists
  unless it has actually been observed or verified.

## Tests and speed

- Add only tests that protect meaningful behavior or a plausible costly failure.
- Prioritize save/load integrity, migration safety, undo/redo, command validation,
  permissions, runtime behavior, and playable exports.
- For a bug fix, add a focused regression test when it usefully prevents recurrence.
- Avoid tests of trivial getters, styling details, framework internals, or mocks
  that merely reproduce the implementation. Do not chase coverage percentages.
- Reuse small fixtures. Keep routine tests deterministic, offline, and independent
  of model downloads, provider accounts, or paid inference.
- Run the smallest relevant checks first, then required integration checks. Do not
  repeatedly rerun broad suites without new changes or evidence of risk.
- Keep application and test images separate once Docker is implemented. Both must
  use the same lockfile and source revision. Keep test-only dependencies out of
  the application image; test Compose must run without a host display session.
- Documentation-only changes need link/diff review, not a newly invented test suite.
- Report exactly what was checked and what could not be checked.

## Git workflow

- Commit early and often at small, coherent, reviewable checkpoints after relevant
  checks pass. A finished documentation change is a valid checkpoint.
- Inspect the diff and stage only task-related files explicitly.
- Use descriptive commit messages and keep the branch usable.
- Never commit secrets, model weights, generated builds, or unrelated edits.
- Do not rewrite history, discard user changes, or push without authorization.
- If a commit is blocked, report it; never claim it succeeded. Explicit user
  instructions about commits take precedence.

## Delivery

- Explain the outcome, verification, and material remaining limitations.
- Update the plan when an accepted decision changes architecture or scope.
- Do not add features, services, abstractions, or approval dialogs solely because
  they might become useful later. Usability and speed are product requirements.
