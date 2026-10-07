import base64
import hashlib
import json
from dataclasses import asdict, replace

import pytest

from solar_forge_engine.core.audio import SoundClip
from solar_forge_engine.core.commands import Document, SetCoinSound
from solar_forge_engine.core.scene import Scene
from solar_forge_engine.project.assets import save_project_scene
from solar_forge_engine.project.recovery import read_recovery, recovery_path
from solar_forge_engine.project.storage import load_scene, save_scene
from solar_forge_engine.project.workspace import create_project, open_project


def clip():
    return SoundClip(8000, 1, 2, base64.b64encode(b"\0" * 1600).decode("ascii"))


def test_sound_command_is_atomic_undoable_and_portable(tmp_path):
    document = Document()
    document.execute(SetCoinSound(asdict(clip())), expected_revision=0)
    assert document.scene.coin_sound == clip()
    with pytest.raises(ValueError):
        document.execute(SetCoinSound({"samples": "bad"}), expected_revision=1)
    assert document.revision == 1
    document.undo()
    assert document.scene.coin_sound is None
    document.redo()
    project = create_project(tmp_path / "Project", document.scene)
    assert open_project(project.root)[1] == document.scene
    standalone = tmp_path / "portable.forge.json"
    save_scene(standalone, document.scene)
    assert load_scene(standalone) == document.scene
    assert clip().duration == 0.1


@pytest.mark.parametrize(
    "changes",
    [
        {"samples": "!"},
        {"samples": ""},
        {"channels": True},
        {"width": 3},
        {"rate": 96000},
        {"samples": base64.b64encode(b"abc").decode()},
        {"samples": base64.b64encode(b"\0" * (8000 * 2 * 30 + 2)).decode()},
    ],
)
def test_invalid_sound_data_does_not_change_document(changes):
    document = Document()
    with pytest.raises(ValueError):
        document.execute(SetCoinSound(asdict(clip()) | changes), expected_revision=0)
    assert not document.can_undo and document.scene.coin_sound is None


@pytest.mark.parametrize("version", [7, 8])
def test_previous_scenes_upgrade_with_exact_backup(tmp_path, version):
    project = create_project(tmp_path / "Game", Scene())
    old = Scene().to_data()
    del old["coin_sound"]
    del old["script"]
    old["format_version"] = version
    original = json.dumps(old).encode()
    project.scene_path().write_bytes(original)
    assert open_project(project.root)[1] == Scene()
    save_project_scene(project.root, project.scene_path(), Scene(coin_sound=clip()))
    backup = project.scene_path().with_name(project.scene_path().name + f".v{version}.bak")
    assert backup.read_bytes() == original
    assert open_project(project.root)[1].coin_sound == clip()


def test_previous_recovery_is_preserved_through_sound_upgrade(tmp_path):
    baseline = Scene()
    project = create_project(tmp_path / "Game", baseline)
    old = baseline.to_data()
    del old["coin_sound"]
    del old["script"]
    old["format_version"] = 7
    snapshot = dict(old, name="Recovered")
    recovery_path(project).write_text(
        json.dumps(
            {
                "format_version": 1,
                "base_hash": hashlib.sha256(json.dumps(old, sort_keys=True).encode()).hexdigest(),
                "scene": snapshot,
            }
        )
    )
    assert read_recovery(project, baseline) == replace(baseline, name="Recovered")
    with pytest.raises(ValueError, match="older saved scene"):
        read_recovery(project, replace(baseline, coin_sound=clip()))
