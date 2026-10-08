# Scene-local reusable object behaviors

Status: selected for implementation; verification will be recorded after integration.

An object may attach one behavior name and up to sixteen numeric parameters.
The name identifies `<name>_start(game, instance)` and
`<name>_update(game, instance, dt)` functions in the scene's existing embedded Python
source. At least one callback must exist and be callable when Play starts. Source
editing, attachment edits, save/load and exports do not evaluate Python. Clearing
source requires detaching behaviors first. External modules and runtime attachment
changes are outside this slice.

Each worker-owned instance exposes its object `id`, a copied `parameters` dictionary
and a separate initially empty `data` dictionary. Globals and `game.data` remain
scene-wide; authors use `instance.data` for independent instance state. Restart
creates a fresh worker and resets all state. Parameters are finite numbers within
±100,000, with identifier names and no duplicate keys. Attachments and parameters
are immutable authoring data, distinct from runtime dictionaries. Duplication copies
the attachment and parameters, then creates a fresh instance under the new object ID.

One worker owns scene and object lifecycles. After evaluating source, call scene
`on_start`, then attachment start callbacks in persisted object order. Each update
calls scene `on_update`, then object update callbacks in the same order. All observe
one input/simulation snapshot and emit through the existing position/speed/message
API. Commands apply together only after the full response validates; the last command
for a property wins. An error in any callback stops scripted Play without applying
partial commands. Error text includes the behavior name and object ID, while source
line navigation uses the existing scene editor.

Support at most 32 attachments per scene, within the existing 256 scripted-object,
32-command, 4 KiB output and 32 KiB source limits. These are shared per-step budgets,
not separate budgets per attachment. Pause/focus loss discard pending commands;
callback-local state can still advance as in the current scene-script contract.
The worker receives validated attachment metadata with startup state. It loads only
trusted engine validation code before installing the existing kernel policy;
project source still arrives after restrictions. No syscall permission is added.

Standalone format 13 and project format 14 add optional attachment data to objects.
Prior formats load detached and keep exact upgrade backups. Recovery must accept
older baseline hashes only when the baseline contains no attachments. Native object
attachment/parameter controls use revision-checked `SetEntity`, and existing scene
source editing defines reusable code. Demonstrate two differently tuned instances
and verify independent state, undo/redo, duplication, migration, recovery, restart,
failure atomicity and both exported formats before marking this slice complete.
