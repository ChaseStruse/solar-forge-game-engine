# Ember Run — scriptable forge playground

Recover twelve energy cores in a glowing industrial forge. Pilot the courier with
WASD or arrows, navigate around machinery, and collect the gold diamonds. Cores
bob in a travelling wave; six sparks orbit the reactor. Each pickup gives you a
short **Overdrive** speed burst. Press **Space while moving** for a 0.25-second dash
at speed 480; it recharges 1.2 seconds after the press. Holding Space does not
repeat the dash. Walls still stop you, and an active pickup boost resumes after
the dash. The HUD tracks power, progress, dash readiness and simulation time.
Finish to earn **Solar Ace** (under 45 seconds), **Forge Runner** (under 75 seconds),
or **Core Keeper**; the sparks gather around your courier to celebrate. Pause freezes
the run, and Restart resets everything. The sparks are decoration, not collectibles.

Copy this folder somewhere writable, then choose **File → Open project** in Solar
Forge Game Engine. Select the copied folder and press **Play** (F5). The startup
scene is Ember Run. For a fresh built-in main scene, choose **Forge showcase**
(Ctrl+Shift+F), then create a project from it to save your changes.

## Open the code and make it yours

Choose **Scene → Edit scene script…** (Ctrl+Shift+E). Each scene includes its own
commented Python example. **Apply script**, stop the current preview, then press
**Play** again to use your edits; **Save** keeps them. Apply supports Undo/Redo,
and playback leaves authored objects unchanged. Constants are at the top:

| Try this | What changes |
| --- | --- |
| `BOOST_SPEED = 400` | A faster pickup burst |
| `BOOST_SECONDS = 2.5` | More time to chain pickups together |
| `DASH_SPEED = 550` | A faster Space dash |
| `DASH_SECONDS = 0.35` | A longer dash |
| `DASH_COOLDOWN = 2` | More time between dashes |
| `CORE_BOB_HEIGHT = 0` | Stationary cores while other effects keep running |
| `SPARK_RADIUS = 100` | A wider reactor orbit |
| Change the medal thresholds in `on_update` | Your own time-trial challenge |

The main script demonstrates saving initial positions in `on_start`, sine-wave
motion, phased orbits, reading `game.actions["dash"]["pressed"]`, reacting once to a
changed collection count, timed effects and persistent victory state. HUD commands
are sent only when their text changes;
`print()` sends pickup milestones to the editor's Activity panel. Script speed
constants override the Inspector's player speed during Play.

## Courier Bay — Orbit Lab

Select **Courier Bay** in the Project Scenes panel, then Play. Chase four satellites
around a gently floating flame. They travel slowly enough to catch with normal
movement; collect all four to record your time. This smaller script demonstrates
scene-level orbital motion alongside reusable object behaviors.

Open its script and try `ORBIT_SPEED = 0` to freeze the targets, a negative value to
reverse their direction, or `ORBIT_RADIUS = 140` for a tighter chase. `BOB_HEIGHT`
controls the flame's vertical motion. Keep the radius below 240 to stay comfortably
inside the arena. Restart to try another run.

Two lower beacons share the `bob` behavior. Select either beacon, open **Scene →
Edit selected object behavior** (Ctrl+Shift+B), and change `amplitude` or `rate`, then Apply
and Play. Their initial values are 8/2 and 16/3. Each has its own elapsed time and
origin in `instance.data`; `bob_start` and `bob_update` define the shared rule in
the scene script. Undo/redo, duplication, save/reopen and exports preserve the
attachment. Restart resets motion without changing authored positions.

## What is included

Ember Run has 193 editable objects and 25 animated sprites, including collision
walls, courier, cores, beacons and sparks. Both scenes share original pixel art;
no downloads, model connection or external Python packages are needed. Scripts are
embedded in the scene files and ship with both native export formats. Execution
requires Linux x86_64 and libseccomp, also supplied by the engine's Docker images.

The source templates live in
[`showcase_scripts.py`](../../src/solar_forge_engine/core/showcase_scripts.py).
They are copied into each scene so your edits belong to your project. These demos
use the current movement/action/position/speed/message API; there are no enemies or
scene transitions.
