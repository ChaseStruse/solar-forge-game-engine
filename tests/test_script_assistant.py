import json

import pytest
from test_assistant import editor_with_object, generate, proposal
from test_ollama import envelope, server

from solar_forge_engine.ai.demo import Context
from solar_forge_engine.ai.ollama import OllamaProvider, scene_context
from solar_forge_engine.ai.proposals import decode_proposal
from solar_forge_engine.core.commands import Document
from solar_forge_engine.core.scene import Entity, Scene
from solar_forge_engine.core.script import ScriptBinding


def test_source_is_reviewed_and_attached_undoably_without_execution(tmp_path):
    marker = tmp_path / "must-not-exist"
    source = f"open({str(marker)!r}, 'w').write('bad')\ndef start(ctx):\n    pass\n"
    scene = Scene(entities=(Entity("player"),))
    document = Document(scene)
    result = decode_proposal(
        proposal(
            [
                {"tool": "set_entity", "id": "player", "changes": {"x": 200}},
                {"tool": "set_script", "id": "player", "name": "motion", "source": source},
            ]
        ),
        scene,
        0,
    )
    assert source in result.review and "Attach Python motion" in result.review
    document.execute(*result.commands, expected_revision=result.revision)
    assert document.scene.scripts[0].source == source
    assert not marker.exists()
    document.undo()
    assert document.scene == scene
    document.redo()
    detach = decode_proposal(
        proposal(
            [
                {"tool": "detach_script", "id": "player"},
            ],
            document.revision,
        ),
        document.scene,
        document.revision,
    )
    assert "Detach Python behavior" in detach.review
    document.execute(*detach.commands, expected_revision=detach.revision)
    assert not document.scene.scripts
    document.undo()
    assert document.scene.scripts[0].source == source
    assert not marker.exists()


@pytest.mark.parametrize(
    "command",
    [
        {"tool": "set_script", "id": "player", "name": "../outside", "source": "pass"},
        {"tool": "set_script", "id": "missing", "name": "motion", "source": "pass"},
        {
            "tool": "set_script",
            "id": "player",
            "name": "motion",
            "source": "pass",
            "path": "/tmp/p.py",
        },
        {"tool": "set_script", "id": "player", "name": "motion", "source": "\x00"},
    ],
)
def test_invalid_script_proposals_cannot_partially_apply(command):
    scene = Scene(entities=(Entity("player"),))
    with pytest.raises(ValueError):
        decode_proposal(
            proposal(
                [
                    {"tool": "set_entity", "id": "player", "changes": {"x": 200}},
                    command,
                ]
            ),
            scene,
            0,
        )
    assert scene.entity("player").x == 0 and not scene.scripts


def test_generated_source_respects_serialized_scene_limit(monkeypatch):
    from solar_forge_engine.ai import proposals

    scene = Scene(entities=(Entity("player"),))
    monkeypatch.setattr(proposals, "MAX_FILE_BYTES", 1024)
    with pytest.raises(ValueError, match="scene limit"):
        decode_proposal(
            proposal(
                [
                    {"tool": "set_script", "id": "player", "name": "motion", "source": "#" * 1000},
                ]
            ),
            scene,
            0,
        )
    assert not scene.scripts


def test_loopback_schema_accepts_source_but_context_never_sends_existing_code():
    binding = ScriptBinding.from_source(
        "hero", "private", "# private source\ndef start(ctx):\n    pass\n"
    )
    scene = Scene(entities=(Entity("hero"),), scripts=(binding,))
    context = Context(scene, 0, "hero")
    raw_context = scene_context(context)
    assert json.loads(raw_context)["objects"][0]["has_python"]
    assert binding.source not in raw_context and binding.path not in raw_context
    response = json.loads(envelope())
    data = json.loads(response["message"]["content"])
    data["commands"] = [
        {
            "tool": "set_script",
            "id": "hero",
            "name": "movement",
            "source": "def update(ctx, dt):\n    ctx.move(120 * dt, 0)\n",
        }
    ]
    response["message"]["content"] = json.dumps(data)
    with server(json.dumps(response).encode()) as (endpoint, requests, _):
        raw = OllamaProvider(endpoint, "test-model").propose("Add Python movement", context)
    request = requests[-1][1]
    schema = request["format"]["properties"]["commands"]["items"]["oneOf"]
    assert {entry["properties"]["tool"]["const"] for entry in schema} >= {
        "set_script",
        "detach_script",
    }
    assert "private source" not in json.dumps(request)
    result = decode_proposal(raw, scene, 0)
    assert "Replace Python movement" in result.review
    document = Document(scene)
    document.execute(*result.commands, expected_revision=0)
    document.undo()
    assert document.scene == scene


def test_offline_behavior_review_does_not_overwrite_pending_manual_drafts(qtbot):
    editor = editor_with_object(qtbot)
    generate(qtbot, editor, "script selected keyboard")
    assert not editor.document.scene.scripts
    assert "def update(ctx, dt)" in editor.assistant.review.toPlainText()
    editor.scripts.templates.setCurrentText("Patrol")
    editor.scripts.use_template()
    source = editor.scripts.code.toPlainText()
    editor.assistant.apply()
    assert "drafts" in editor.assistant.status.text()
    assert editor.scripts.code.toPlainText() == source
    assert not editor.document.scene.scripts
    editor.scripts.revert()
    editor.assistant.apply()
    assert editor.document.scene.scripts[0].name == "keyboard"
    editor.document.undo()
    editor.refresh()
    assert not editor.document.scene.scripts
    editor.close()
