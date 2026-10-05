import json
import os
from threading import Event

import pytest
from test_ollama import server

from solar_forge_engine.ai.ollama import OllamaProvider
from solar_forge_engine.ai.preferences import read_profile, save_profile
from solar_forge_engine.editor.window import EditorWindow


def models(*names):
    return json.dumps({"models": [{"name": name} for name in names]}).encode()


def test_discovery_get_filters_cloud_models_and_deduplicates():
    with server(models("local-b:latest", "local-a", "local-a", "other-cloud")) as (
        endpoint,
        requests,
        _,
    ):
        found = OllamaProvider(endpoint, "discovery").models(lambda: False)
    assert found == ("local-a", "local-b:latest")
    assert requests == [("/api/tags", None)]


@pytest.mark.parametrize(
    "response", [b"{}", b'{"models": [null]}', models("bad model"), models(*["x"] * 129)]
)
def test_discovery_rejects_unbounded_or_invalid_lists(response):
    with server(response) as (endpoint, _, _):
        with pytest.raises(ValueError):
            OllamaProvider(endpoint, "discovery").models(lambda: False)


def test_profile_roundtrip_and_invalid_file_preservation(tmp_path):
    path = tmp_path / "preferences" / "assistant.json"
    provider = OllamaProvider("http://127.0.0.1:11434", "local-model", 30)
    assert read_profile(path) is None
    save_profile(path, provider)
    assert read_profile(path) == provider
    assert set(json.loads(path.read_bytes())) == {"format_version", "endpoint", "model", "timeout"}
    for raw in (
        b"x" * 4097,
        b'{"format_version":2}',
        b"invalid",
        json.dumps(
            {
                "format_version": 1,
                "endpoint": "http://example.com",
                "model": "local-model",
                "timeout": 30,
            }
        ).encode(),
    ):
        path.write_bytes(raw)
        with pytest.raises(ValueError):
            read_profile(path)
        assert path.read_bytes() == raw
    link = tmp_path / "link"
    link.symlink_to(path)
    with pytest.raises(OSError):
        read_profile(link)
    with pytest.raises(ValueError):
        save_profile(link, provider)
    fifo = tmp_path / "fifo"
    os.mkfifo(fifo)
    with pytest.raises(ValueError, match="regular file"):
        read_profile(fifo)


def editor(qtbot):
    window = EditorWindow()
    qtbot.addWidget(window)
    window._confirm_discard = lambda: True
    qtbot.waitUntil(lambda: not window.assistant.busy)
    return window


def test_discovery_save_and_reopen_without_auto_connect(qtbot):
    window = editor(qtbot)
    panel = window.assistant
    original = window.document.scene
    with server(models("local-a", "local-b")) as (endpoint, requests, _):
        panel.provider_choice.setCurrentIndex(1)
        panel.endpoint.setText(endpoint)
        panel.discover_models()
        qtbot.waitUntil(lambda: not panel.busy)
        assert panel.model.text() == "local-a"
        assert panel.model_picker.count() == 2
        assert window.document.scene == original
        panel.model.setText("local-b")
        panel.timeout.setValue(25)
        panel.save_connection()
        qtbot.waitUntil(lambda: not panel.busy)
        assert "saved" in panel.status.text()
        reopened = editor(qtbot).assistant
        assert reopened.provider_choice.currentIndex() == 0
        assert reopened.endpoint.text() == endpoint
        assert reopened.model.text() == "local-b"
        assert reopened.timeout.value() == 25
        assert requests == [("/api/tags", None)]
        assert window.document.scene == original


def test_canceled_discovery_preserves_picker_and_scene(qtbot):
    window = editor(qtbot)
    panel = window.assistant
    original = window.document.scene
    release = Event()
    with server(models("replacement"), wait=release) as (endpoint, _, started):
        panel.endpoint.setText(endpoint)
        panel.model.setText("existing")
        panel.discover_models()
        qtbot.waitUntil(started.is_set)
        panel.discard()
        qtbot.waitUntil(lambda: not panel.busy)
        assert "canceled" in panel.status.text()
        assert panel.model.text() == "existing"
        assert window.document.scene == original


def test_corrupt_preferences_warn_and_leave_offline_defaults(qtbot, monkeypatch, tmp_path):
    path = tmp_path / "assistant.json"
    path.write_text("{bad")
    monkeypatch.setattr("solar_forge_engine.editor.assistant.profile_path", lambda: path)
    panel = editor(qtbot).assistant
    assert panel.provider_choice.currentIndex() == 0
    assert panel.model.text() == ""
    assert "ignored" in panel.status.text()
    assert path.read_text() == "{bad"
