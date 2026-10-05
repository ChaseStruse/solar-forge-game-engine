import json
import time

import pytest
from test_ollama import envelope, server
from test_preferences import editor

from solar_forge_engine.ai.demo import Context
from solar_forge_engine.ai.ollama import OllamaProvider
from solar_forge_engine.core.scene import Entity, Scene


def metadata(capabilities=None, **extra):
    return json.dumps({"capabilities": capabilities or ["completion"], **extra}).encode()


def test_capabilities_report_metadata_without_inference_or_scene_context():
    raw = metadata(
        ["tools", "completion"],
        model_info={
            "general.architecture": "test",
            "test.context_length": 8192,
        },
    )
    with server(lambda _: raw) as (endpoint, requests, _):
        result = OllamaProvider(endpoint, "test-model").capabilities(lambda: False)
    assert result.names == ("completion", "tools")
    assert result.context_length == 8192
    assert requests == [("/api/show", {"model": "test-model", "verbose": False})]
    assert "review" in result.description


@pytest.mark.parametrize(
    "raw",
    [
        b"{}",
        b'{"capabilities": []}',
        metadata(["embedding"]),
        metadata(["completion"], remote_host="https://example.com"),
        metadata(["completion"], remote_model="upstream"),
        metadata(["completion"] * 17),
        metadata([None]),
    ],
)
def test_incompatible_or_remote_models_are_rejected_before_chat(raw):
    with server(lambda _: raw) as (endpoint, requests, _):
        context = Context(Scene(entities=(Entity("hero"),)), 0, "hero")
        with pytest.raises(ValueError):
            OllamaProvider(endpoint, "test-model").propose("Move hero", context)
        assert [path for path, _ in requests] == ["/api/show"]


def test_preflight_and_chat_share_one_absolute_deadline():
    def delayed(path):
        time.sleep(0.6)
        return metadata() if path == "/api/show" else envelope()

    with server(delayed) as (endpoint, requests, _):
        before = time.monotonic()
        with pytest.raises(ValueError, match="timed out"):
            OllamaProvider(endpoint, "test-model", 1).propose(
                "Move hero", Context(Scene(entities=(Entity("hero"),)), 0, "hero")
            )
        assert time.monotonic() - before < 1.7
        assert [path for path, _ in requests] == ["/api/show", "/api/chat"]


def test_native_check_is_read_only_and_missing_model_does_not_fall_back(qtbot):
    window = editor(qtbot)
    panel = window.assistant
    scene = window.document.scene
    with server(lambda _: metadata(["completion"])) as (endpoint, requests, _):
        panel.provider_choice.setCurrentIndex(1)
        panel.endpoint.setText(endpoint)
        panel.model.setText("test-model")
        panel.check_model()
        qtbot.waitUntil(lambda: not panel.busy)
        assert "Completion available" in panel.status.text()
        assert requests == [("/api/show", {"model": "test-model", "verbose": False})]
        assert window.document.scene == scene
        assert not panel.apply_button.isEnabled()
    with server(b"", status=404) as (endpoint, requests, _):
        panel.endpoint.setText(endpoint)
        panel.check_model()
        qtbot.waitUntil(lambda: not panel.busy)
        assert "HTTP 404" in panel.status.text()
        assert requests == [("/api/show", {"model": "test-model", "verbose": False})]
        assert panel.provider_choice.currentIndex() == 1
        assert window.document.scene == scene
