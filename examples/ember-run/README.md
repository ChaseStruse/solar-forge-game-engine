# Ember Run — Solar Sanctuary

Recover twelve energy cores in a living solarpunk station. Pilot the animated
courier with WASD or arrows, weave between greenhouse beds and solar arrays, and
collect every gold diamond. The HUD announces completion; Restart resets the run.
Garden tenders hover beside the reactor, pollen drifts through the corridors, and
a turning mint-and-gold aureole surrounds the living forge.

Copy this folder somewhere writable, then choose **File → Open project** in Solar
Forge Game Engine. Select the copied folder and press **Play** (F5). The startup
scene is Ember Run. The Project Scenes panel also offers **Courier Bay**, a small
sprite playground using shared assets.

The main scene has 231 editable objects, 25 animated sprites, three Python
behaviors, and an original collection chime. Try changing the courier's movement
speed, moving walls, duplicating energy cores, or adjusting animation frame rate
in the Inspector. Select a **Garden tender** or **Reactor aureole** and open
**Scene → Python behavior** to customize its motion. Apply changes before playing;
save to retain edits. Playback leaves authored scenes unchanged.

All pixel art and audio are original, authored in the engine's Python showcase
module. Project-relative RGBA assets are shared between scenes; Python source and
PCM audio live inside the project. The complete example is about 260 KiB and
requires no image downloads, model accounts, or network access.

Behaviors use the engine's restricted Python worker and require its supported
Linux sandbox environment; unavailable restrictions produce a clear error rather
than executing source without protection. The collection chime uses `pw-play`
when available; the game remains playable without audio output.

**File → Export game** creates a native Linux `.pyz` with its own scene, art,
source and audio. Running that lightweight export requires the supported Python,
PySide6 and scripting restrictions; no editor, model provider or Docker is needed.

For a fresh built-in copy, click **Forge showcase** (Ctrl+Shift+F). Create a project
from that scene to save it into your own folder.
