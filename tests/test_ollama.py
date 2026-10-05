import json
import time
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Event, Thread

import pytest

from solar_forge_engine.ai.demo import Context
from solar_forge_engine.ai.ollama import MAX_CONTEXT_BYTES, OllamaProvider, scene_context
from solar_forge_engine.ai.proposals import decode_proposal
from solar_forge_engine.core.commands import Document
from solar_forge_engine.core.scene import Entity, Scene
from solar_forge_engine.core.showcase import ember_run
from solar_forge_engine.editor.window import EditorWindow


@contextmanager
def server(reply, status=200, wait=None):
    requests = []
    started = Event()

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            requests.append(
                (self.path, json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
            )
            self.respond()

        def do_GET(self):
            requests.append((self.path, None))
            self.respond()

        def respond(self):
            started.set()
            if wait is not None:
                wait.wait(3)
            self.send_response(status)
            self.send_header("Content-Length", str(len(reply)))
            self.end_headers()
            try:
                self.wfile.write(reply)
            except OSError:
                pass  # Canceled client deliberately closes its socket.

        def log_message(self, *args):
            pass

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=httpd.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{httpd.server_port}", requests, started
    finally:
        if wait is not None:
            wait.set()
        httpd.shutdown()
        httpd.server_close()
        thread.join()


def envelope(revision=0):
    content = json.dumps(
        {
            "format_version": 1,
            "revision": revision,
            "summary": "Move hero",
            "commands": [{"tool": "set_entity", "id": "hero", "changes": {"x": 120}}],
        }
    )
    return json.dumps({"done": True, "message": {"content": content}}).encode()


@pytest.mark.parametrize(
    "endpoint",
    [
        "https://127.0.0.1:11434",
        "http://example.com",
        "http://192.168.1.1",
        "http://user:secret@localhost",
        "http://localhost/api/chat",
        "http://localhost?secret=value",
        "http://localhost:0",
        "http://[::1]:99999",
    ],
)
def test_only_explicit_loopback_addresses_are_accepted(endpoint):
    with pytest.raises(ValueError, match="loopback"):
        OllamaProvider(endpoint, "test-model")


def test_local_addresses_and_cloud_models():
    assert OllamaProvider("http://localhost", "test-model").address() == ("127.0.0.1", 11434)
    assert OllamaProvider("http://[::1]:11434", "test-model").address() == ("::1", 11434)
    with pytest.raises(ValueError, match="cloud"):
        OllamaProvider("http://localhost", "test-cloud")


def test_metadata_context_is_bounded_and_keeps_selected_object_without_pixels():
    scene = ember_run()
    raw = scene_context(Context(scene, 3, "courier"))
    data = json.loads(raw)
    assert len(raw.encode()) <= MAX_CONTEXT_BYTES
    assert data["objects"][0]["id"] == "courier"
    assert data["objects"][0]["animated"]
    assert data["omitted_objects"] > 0
    assert "pixels" not in raw and "base64" not in raw and ".rgba" not in raw


def test_real_http_request_schema_response_validation_and_atomic_undo(monkeypatch):
    monkeypatch.setenv("HTTP_PROXY", "http://127.0.0.1:1")
    document = Document(Scene(entities=(Entity("hero"),)))
    context = Context(document.scene, 0, "hero")
    with server(envelope()) as (endpoint, requests, _):
        raw = OllamaProvider(endpoint, "test-model").propose("Move hero", context)
    path, request = requests[0]
    assert path == "/api/chat"
    assert request["stream"] is False
    assert request["format"]["properties"]["revision"]["const"] == 0
    assert request["model"] == "test-model"
    proposal = decode_proposal(raw, context.scene, 0)
    original = document.scene
    document.execute(*proposal.commands, expected_revision=0)
    assert document.scene.entity("hero").x == 120
    document.undo()
    assert document.scene == original


@pytest.mark.parametrize(
    ("reply", "status", "error"),
    [
        (b"invalid", 200, "invalid JSON"),
        (b"{}", 200, "incomplete"),
        (b"x" * 65537, 200, "64 KiB"),
        (json.dumps({"done": True, "message": {"content": "x" * 16385}}).encode(), 200, "16 KiB"),
        (b"", 302, "HTTP 302"),
        (b"", 404, "HTTP 404"),
    ],
    ids=["invalid-json", "incomplete", "large-envelope", "large-proposal", "redirect", "missing"],
)
def test_malformed_large_and_redirect_responses_fail_closed(reply, status, error):
    with server(reply, status) as (endpoint, _, _):
        with pytest.raises(ValueError, match=error):
            OllamaProvider(endpoint, "test-model").propose("Move hero", Context(Scene(), 0, None))


@pytest.mark.parametrize("cancel", [False, True])
def test_cancel_and_absolute_deadline_interrupt_waiting_for_headers(cancel):
    release, canceled = Event(), Event()
    with server(envelope(), wait=release) as (endpoint, _, started):
        errors = []

        def request():
            try:
                OllamaProvider(endpoint, "test-model", 1).propose(
                    "Move hero", Context(Scene(), 0, None, canceled.is_set)
                )
            except ValueError as error:
                errors.append(str(error))

        worker = Thread(target=request)
        before = time.monotonic()
        worker.start()
        assert started.wait(1)
        if cancel:
            canceled.set()
        worker.join(2)
        assert not worker.is_alive()
        assert time.monotonic() - before < 2
        assert ("canceled" if cancel else "timed out") in errors[0]


def test_assistant_local_provider_review_apply_and_return_to_offline(qtbot):
    editor = EditorWindow()
    qtbot.addWidget(editor)
    editor._confirm_discard = lambda: True
    editor.document = Document(Scene(entities=(Entity("hero"),)))
    editor.selected_id = "hero"
    editor.refresh()
    panel = editor.assistant
    original = editor.document.scene
    with server(envelope()) as (endpoint, _, _):
        panel.provider_choice.setCurrentIndex(1)
        panel.endpoint.setText(endpoint)
        panel.model.setText("test-model")
        panel.prompt.setText("Move hero to 120")
        panel.generate()
        assert not panel.provider_choice.isEnabled()
        qtbot.waitUntil(lambda: not panel.busy)
        assert panel.apply_button.isEnabled()
        assert editor.document.scene == original
        panel.apply()
        assert editor.document.scene.entity("hero").x == 120
        editor.undo()
        assert editor.document.scene == original
    panel.provider_choice.setCurrentIndex(0)
    panel.prompt.setText("add coin")
    panel.generate()
    qtbot.waitUntil(lambda: not panel.busy)
    assert panel.apply_button.isEnabled()
