# Python behaviors

Select an object, then open **Scene → Python behavior…** (`Ctrl+Alt+P`). Choose a
keyboard, patrol, or spin template, import a UTF-8 `.py` file, or write code in the
native editor. The panel provides highlighting, line numbers, automatic indentation
and ordinary text undo. **Apply behavior** attaches your code in one scene undo
step; **Detach** removes the attachment. Each object has at most one behavior.
Duplicating an object copies its behavior; deleting it removes its attachment.
Scene Undo restores both the object and its behavior.

Drafts survive object selection changes. **Save**, **Play**, project creation and
**Export** apply all valid drafts together; invalid or stale drafts stop that action
without partially applying code. Save/Discard/Cancel also protects drafts when
switching scenes or closing. Project recovery captures valid unapplied drafts without
executing them. **Revert all drafts** returns to applied source. A source changed
through Undo or another command while you are editing requires Undo of that change
or reverting your draft; it is never silently overwritten.

Behavior names use 1–48 ASCII letters, digits, underscores or hyphens, starting with
a letter or digit. Sources are limited to 64 KiB each, sixteen behaviors and 512 KiB
aggregate per scene. The existing 4 MiB scene limit also applies. Syntax errors can
be saved; loading and importing code never execute it.

## Callbacks

Define any of the following functions at module level. Omitted callbacks are skipped.
Modules load once for each fresh Play session; globals and `ctx.state` persist for
that session. At least one callback is required. `dt` is seconds, capped at 0.1;
`ctx.elapsed` is elapsed simulation time. Callbacks run in attachment order in a
single asynchronous worker, outside the Qt UI and renderer.

```python
def start(ctx):
    ctx.state["speed"] = 240


def update(ctx, dt):
    ctx.move(ctx.input.horizontal * ctx.state["speed"] * dt,
             ctx.input.vertical * ctx.state["speed"] * dt)


def on_collect(ctx, other_id):
    ctx.add_score(10)


def on_collision(ctx, other_id):
    print("Hit", other_id)


def on_key(ctx, key, pressed):
    if key == "space" and pressed:
        ctx.set_color("#f3cb77")


def stop(ctx):
    print("Session ended")
```

`on_collision` reports swept movement blocked by a Wall. `on_collect` runs for the
controlled object and each collected Coin, with the other object's ID. Events are
queued for the next worker request, deduplicated and limited to 128 pending events.
Repeated attempts to move into a wall can produce repeated collision callbacks.
A script on the controlled object replaces its built-in keyboard movement; other
objects keep their normal native behavior.

`on_key` receives key edges. Input supports letters, digits, arrow names (`left`,
`right`, `up`, `down`), `space`, `enter`, `shift` and `ctrl`; names are lowercase.
Escape is reserved for closing Play. `ctx.input.down("space")` checks held keys;
`ctx.input.x/y` are integer WASD/arrow axes; `horizontal/vertical` normalize diagonal
movement. Focus loss and Pause clear keys and stop future updates. An already-running
callback can finish, but its motion is discarded while paused or unfocused.

## Context API

| API | Behavior |
| --- | --- |
| `ctx.id`, `ctx.x`, `ctx.y` | Owning object ID and most recently observed runtime position |
| `ctx.world_width`, `ctx.world_height` | Arena size: 1024 × 576 |
| `ctx.elapsed` | Simulation time in seconds |
| `ctx.state` | Private persistent dictionary for this attachment; reset on Restart |
| `ctx.input` | Held keys and movement axes described above |
| `ctx.get(id)` | Read-only view of an object's observed `id`, `name`, `x`, `y`, `width`, `height`, `color`, `role` |
| `ctx.move(dx, dy)` | Relative movement with swept wall collisions and arena clamping |
| `ctx.set_position(x, y)` | Absolute teleport, clamped to the arena; bypasses wall sweeping |
| `ctx.set_rotation(degrees)` | Visual rotation around the object's center |
| `ctx.set_color("#rrggbb")` | Shape fill color; sprites are not tinted |
| `ctx.set_visible(bool)` | Visual visibility; collision and coin rules remain active |
| `ctx.add_score(points)` | Add an integer within ±1,000; total score clamped to ±1,000,000 |
| `print(...)` | Captured in editor Activity, with bounded output |

Actions affect only the owning object's runtime body and the game score. Authored
scene data, history and saved files remain unchanged. `move` updates the worker's
local position optimistically; the next request supplies the collision-resolved
position. Coordinates must be finite and within ±100,000. A worker request permits
at most 64 actions across all attachments. Rotation does not rotate collision boxes.
`ctx.get` positions are refreshed for scripted objects and the controlled object;
other properties describe their authored snapshot.

This initial API does not spawn/delete runtime objects, switch scenes, load arbitrary
project modules, hot reload code or provide a general filesystem/plugin interface.
Use native scene tools for authoring and Restart Play after applying source changes.

## Debugging and lifecycle

Python errors appear in **Activity** and the Python panel's error list. Double-click
an error to select its object and source line. Errors from an older source snapshot
are not mapped onto changed drafts. A failure pauses the game; **Restart** starts a
fresh worker with fresh globals/state. Changed editor code requires stopping and
starting Play again, since Play holds an immutable scene snapshot.

Startup has a five-second deadline; update and stop requests have 250 ms deadlines.
A loop, crash, malformed response, excessive output or unavailable restriction backend
stops the worker and displays an error. Runtime output has a 64 KiB packet limit and
256 KiB total limit per request; captured logs allow sixteen 512-character messages
per request, with at most 32 shown per second. Stop is best effort: an idle worker
gets its `stop` callbacks; a busy or hung worker is killed within its deadline.
Closing or restarting retires the old process before creating a fresh one.

## Files and exports

Project scenes reference immutable source snapshots under
`scripts/<name>--<sha256>.py`. Standalone scenes and recovery data embed source.
Save publishes Python snapshots before publishing the scene that references them.
The original imported file is never modified. For an external-editor workflow,
edit your own `.py` working copy and import it again; importing copies source into
an unapplied draft. Direct edits to content-addressed project snapshots fail integrity
checks instead of silently replacing source. Old snapshots remain available for Undo
and other scenes; sprite cleanup does not delete them.

**Export active scene as game…** includes applied Python source and the same isolated
worker in the native `.pyz`. The editor, model server, project folder and Docker are
not required. Current exports still require Python 3.14, PySide6-Essentials 6.11.2 and
native Linux libraries; fully bundled dependencies remain the next packaging task.

## Assistant proposals

The offline demo supports `script selected keyboard`, `script selected patrol`,
`script selected spin` and `detach script selected`. These are deterministic templates,
not an LLM. Opt-in Ollama can propose `set_script` and `detach_script` commands with
Python source. Review shows the entire proposed source before Apply, and the combined
scene/code edit is undoable. Proposing or applying code never executes it.

Existing Python source and paths are excluded from automatic model context; only
an attachment-present flag is sent with ordinary scene metadata. Source replacement
therefore needs an explicit request describing the desired behavior. Manual source
drafts block assistant Apply until you apply or revert them. Unsupported tools,
invalid bindings, stale revisions and serialized scene-size overflows are rejected.
Provider limits still bound an entire proposal to 16 KiB and sixteen commands.

## Execution restrictions

Script execution currently requires x86_64 Linux, Landlock ABI 6+ (Linux 6.12+) and
`libseccomp.so.2`. Both Docker images include libseccomp. Missing capabilities fail
closed; there is no unrestricted fallback. Standard-library helpers such as `math`
and `random` work. Installed packages, Qt, editor/model modules, project imports,
files, credentials, display/audio sockets, networking and child processes are not
available to behaviors. The worker receives no editor environment and closes inherited
file descriptors above stdin/stdout/stderr before executing source.

Landlock limits filesystem access and seccomp limits syscalls; memory, CPU, descriptor
and file-size limits provide additional bounds. Landlock does not hide all filesystem
metadata. These restrictions are implemented and tested boundaries, not a claim of
complete protection against unknown kernel/interpreter vulnerabilities. See the
[sandbox architecture record](architecture/0002-script-sandbox.md) for details.
