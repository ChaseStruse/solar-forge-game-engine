import hashlib
import json
import os
import subprocess
import tarfile

import pytest
from test_exports import game, scripted_game

from solar_forge_engine.project import bundling


@pytest.fixture(scope="module")
def bundle(tmp_path_factory):
    folder = tmp_path_factory.mktemp("native-bundle")
    archive = folder / "Game.tar.gz"
    bundling.export_bundle(archive, scripted_game())
    with tarfile.open(archive) as handle:
        handle.extractall(folder, filter="data")
    relocated = folder / "Moved game with spaces"
    (folder / "Game").rename(relocated)
    return archive, relocated


def test_relocated_bundle_runs_without_system_python_or_project_imports(bundle, tmp_path):
    archive, root = bundle
    marker = tmp_path / "must-not-exist"
    (tmp_path / "sitecustomize.py").write_text(f"open({str(marker)!r}, 'w').close()")
    (tmp_path / "PySide6.py").write_text("raise RuntimeError('project import')")
    environment = dict(
        os.environ,
        PATH="/usr/bin:/bin",
        PYTHONHOME="/missing-python",
        PYTHONPATH=str(tmp_path),
        QT_PLUGIN_PATH="/missing-qt",
        QT_QPA_PLATFORM_PLUGIN_PATH="/missing-plugins",
        QT_QPA_PLATFORM="offscreen",
    )
    result = subprocess.run(
        [str(root / "play"), "--smoke-check"],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report["runtime_from_archive"] and not report["editor_loaded"]
    assert report["script_ready"] and not report["script_failed"]
    assert report["script_message"] == "Input and behaviors verified"
    assert report["scene_unchanged"] and report["collected"] == 1 and report["ticks"] > 0
    assert not marker.exists()
    manifest = json.loads((root / "bundle.json").read_text())
    assert manifest["external_qt_libraries"]
    for relative, entry in manifest["files"].items():
        path = root / relative
        with path.open("rb") as handle:
            assert hashlib.file_digest(handle, "sha256").hexdigest() == entry["sha256"]
        assert path.stat().st_size == entry["bytes"]
    names = list(manifest["files"])
    assert "notices/Python-LICENSE.txt" in names
    assert "notices/PySide6-Essentials-METADATA.txt" in names
    assert not any(
        excluded in name
        for name in names
        for excluded in ("pytest", "/editor/", "/ai/", "sitecustomize", "__pycache__", "QtQml")
    )
    with tarfile.open(archive) as handle:
        assert all(item.isfile() or item.isdir() for item in handle)


def test_bundle_failures_and_late_target_creation_preserve_existing_files(tmp_path, monkeypatch):
    target = tmp_path / "Game.tar.gz"
    target.write_bytes(b"existing")
    with pytest.raises(FileExistsError):
        bundling.export_bundle(target, game())
    assert target.read_bytes() == b"existing"
    link = tmp_path / "Link.tar.gz"
    link.symlink_to(target)
    with pytest.raises(FileExistsError):
        bundling.export_bundle(link, game())
    assert link.is_symlink() and target.read_bytes() == b"existing"
    with pytest.raises(ValueError, match="extension"):
        bundling.export_bundle(tmp_path / "Invalid.zip", game())

    def failed_copy(root):
        (root / "partial").write_bytes(b"partial copy")
        raise OSError("No space left")

    monkeypatch.setattr(bundling, "_copy_runtime", failed_copy)
    failed = tmp_path / "Failed.tar.gz"
    with pytest.raises(OSError, match="No space"):
        bundling.export_bundle(failed, game())
    assert not failed.exists() and not list(tmp_path.glob(".forge-bundle-*"))

    def race_copy(root):
        failed.write_bytes(b"another exporter won")
        return []

    monkeypatch.setattr(bundling, "_copy_runtime", race_copy)
    monkeypatch.setattr(bundling, "_validate_interpreter", lambda root: None)
    with pytest.raises(FileExistsError):
        bundling.export_bundle(failed, game())
    assert failed.read_bytes() == b"another exporter won"
    assert not list(tmp_path.glob(".forge-bundle-*"))
