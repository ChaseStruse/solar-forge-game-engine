import json
from threading import Event

import pytest

from solar_forge_engine.ai.demo import Context, DemoProvider
from solar_forge_engine.ai.proposals import decode_proposal
from solar_forge_engine.core.commands import Document
from solar_forge_engine.core.scene import Entity, Scene
from solar_forge_engine.editor.window import EditorWindow
from solar_forge_engine.project.storage import load_scene


def proposal(commands, revision=0):
    return json.dumps(
        {"format_version": 1, "revision": revision, "summary": "Review edits", "commands": commands}
    )


@pytest.mark.parametrize(
    "commands",
    [
        [{"tool": "run_python", "code": "print('bad')"}],
        [{"tool": "set_entity", "id": "player", "changes": {"script": "bad"}}],
        [{"tool": "set_entity", "id": "player", "changes": {"id": "changed"}}],
        [
            {"tool": "set_entity", "id": "player", "changes": {"x": 200}},
            {"tool": "set_entity", "id": "player", "changes": {"width": -1}},
        ],
        [{"tool": "delete_entity", "id": "missing"}],
        [{"tool": "create_entity", "entity": {"id": "player"}}],
    ],
)
def test_untrusted_proposals_reject_tools_and_partial_invalid_edits(commands):
    scene = Scene(entities=(Entity("player"),))
    with pytest.raises(ValueError):
        decode_proposal(proposal(commands), scene, 0)
    assert scene.entity("player").x == 0


def test_response_revision_and_resource_bounds():
    scene = Scene(entities=(Entity("player"),))
    command = {"tool": "delete_entity", "id": "player"}
    for raw in ("x" * 17000, proposal([command] * 17), proposal([command], revision=1), "invalid"):
        with pytest.raises(ValueError):
            decode_proposal(raw, scene, 0)


def test_demo_response_is_deterministic_and_applies_atomically():
    document = Document(Scene(entities=(Entity("player"),)))
    context = Context(document.scene, 0, "player")
    provider = DemoProvider()
    prompt = "move selected to 200 150; rename selected Hero; add coin"
    response = provider.propose(prompt, context)
    assert response == provider.propose(prompt, context)
    result = decode_proposal(response, context.scene, context.revision)
    assert "x: 0 → 200.0" in result.review
    original = document.scene
    document.execute(*result.commands, expected_revision=result.revision)
    assert document.scene.entity("player").name == "Hero"
    assert len(document.scene.entities) == 2
    document.undo()
    assert document.scene == original
    document.redo()
    assert document.scene.entity("player").x == 200


def editor_with_object(qtbot):
    editor = EditorWindow()
    qtbot.addWidget(editor)
    editor._confirm_discard = lambda: True
    editor.add_rectangle()
    editor.saved_scene = editor.document.scene
    return editor


def generate(qtbot, editor, prompt):
    editor.assistant.prompt.setText(prompt)
    editor.assistant.generate()
    qtbot.waitUntil(lambda: not editor.assistant.busy)


def test_review_discard_apply_undo_and_save(qtbot, tmp_path):
    editor = editor_with_object(qtbot)
    original = editor.document.scene
    revision = editor.document.revision
    generate(qtbot, editor, "move selected to 200 150; rename selected Hero")
    assert editor.document.scene == original
    assert not editor.dirty
    assert editor.assistant.apply_button.isEnabled()
    assert "Hero" in editor.assistant.review.toPlainText()
    editor.assistant.discard()
    editor.assistant.apply()
    assert editor.document.scene == original
    generate(qtbot, editor, "move selected to 200 150; rename selected Hero")
    editor.assistant.apply()
    edited = editor.document.scene
    assert edited.entities[0].name == "Hero"
    assert editor.document.revision == revision + 1
    editor.undo()
    assert editor.document.scene == original
    editor.redo()
    assert editor.document.scene == edited
    editor.path = tmp_path / "assistant.forge.json"
    assert editor.save()
    assert load_scene(editor.path) == edited


def test_stale_revision_and_replaced_document_never_apply(qtbot):
    editor = editor_with_object(qtbot)
    generate(qtbot, editor, "delete selected")
    editor.add_rectangle()
    changed = editor.document.scene
    assert not editor.assistant.apply_button.isEnabled()
    editor.assistant.apply()
    assert editor.document.scene == changed
    generate(qtbot, editor, "add coin")
    editor.document = Document()
    editor.assistant.apply()
    assert editor.document.scene == Scene()
    assert "fresh proposal" in editor.assistant.status.text()


@pytest.mark.parametrize("action", ["cancel", "edit", "close", "error"])
def test_inflight_results_cannot_apply_after_cancellation_or_changes(qtbot, action):
    editor = editor_with_object(qtbot)
    started, proceed = Event(), Event()

    class DelayedProvider:
        def propose(self, prompt, context):
            started.set()
            assert proceed.wait(3)
            if action == "error":
                raise RuntimeError("provider unavailable")
            return DemoProvider().propose(prompt, context)

    editor.assistant.provider = DelayedProvider()
    editor.assistant.prompt.setText("delete selected")
    original = editor.document.scene
    editor.assistant.generate()
    qtbot.waitUntil(started.is_set)
    try:
        if action == "cancel":
            editor.assistant.discard()
        elif action == "edit":
            editor.add_rectangle()
        elif action == "close":
            editor.show()
            editor.close()
            assert editor.isVisible()
    finally:
        proceed.set()
    qtbot.waitUntil(lambda: not editor.assistant.busy)
    assert not editor.assistant.apply_button.isEnabled()
    editor.assistant.apply()
    if action != "edit":
        assert editor.document.scene == original
    else:
        assert len(editor.document.scene.entities) == 2
    if action == "error":
        assert "provider unavailable" in editor.assistant.status.text()
