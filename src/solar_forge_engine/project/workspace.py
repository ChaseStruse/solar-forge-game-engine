"""Small native project-folder contract; opening projects never executes code."""

import json
import os
import re
import shutil
from dataclasses import dataclass, replace
from pathlib import Path, PurePosixPath

from solar_forge_engine.core.scene import Scene, text
from solar_forge_engine.project.assets import load_project_scene, save_project_scene

MANIFEST = "project.json"
MAX_MANIFEST_BYTES = 16 * 1024


@dataclass(frozen=True)
class Project:
    root: Path
    name: str
    scene: str

    def scene_path(self) -> Path:
        """Reject traversal and symbolic links, including links inside the root."""
        if self.root.is_symlink():
            raise ValueError("Project folders must not be replaced by symbolic links.")
        relative = PurePosixPath(self.scene)
        if (
            relative.is_absolute()
            or len(relative.parts) < 2
            or relative.parts[0] != "scenes"
            or any(part in ("", ".", "..") for part in self.scene.split("/"))
            or "\\" in self.scene
            or not self.scene.endswith(".forge.json")
        ):
            raise ValueError("The project scene must be a relative file inside scenes/.")
        path = self.root
        for part in relative.parts:
            path = path / part
            if path.is_symlink():
                raise ValueError("Project scene paths must not use symbolic links.")
        if not path.resolve().is_relative_to(self.root.resolve()):
            raise ValueError("The scene path must stay inside the project folder.")
        return path


def open_project(root: Path) -> tuple[Project, Scene]:
    root = root.resolve(strict=True)
    manifest = root / MANIFEST
    if manifest.is_symlink() or not manifest.is_file():
        raise ValueError("Choose a project folder containing a regular project.json file.")
    with manifest.open("rb") as handle:
        raw = handle.read(MAX_MANIFEST_BYTES + 1)
    if len(raw) > MAX_MANIFEST_BYTES:
        raise ValueError("Project manifests must be no larger than 16 KiB.")
    try:
        data = json.loads(raw)
    except (ValueError, UnicodeDecodeError, RecursionError) as error:
        raise ValueError("The project manifest is not valid UTF-8 JSON.") from error
    if not isinstance(data, dict) or set(data) != {"format_version", "name", "scene"}:
        raise ValueError("Invalid project manifest fields.")
    if type(data["format_version"]) is not int or data["format_version"] != 1:
        raise ValueError("Unsupported project format version; this editor supports version 1.")
    project = Project(
        root, text(data["name"], "Project name"), text(data["scene"], "Scene path", 240)
    )
    path = project.scene_path()
    if not path.is_file():
        raise ValueError("The project's scene file is missing or is not a regular file.")
    return project, load_project_scene(project.root, path)


def create_project(root: Path, scene: Scene) -> Project:
    """Create a new folder from a scene; never adopt or overwrite an existing folder."""
    root = root.absolute()
    project = Project(root, text(root.name, "Project name"), "scenes/main.forge.json")
    root.mkdir()
    try:
        (root / "scenes").mkdir()
        (root / "assets").mkdir()
        save_project_scene(project.root, project.scene_path(), scene)
        manifest = {
            "format_version": 1,
            "name": project.name,
            "scene": project.scene,
        }
        (root / MANIFEST).write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    except OSError, ValueError:
        shutil.rmtree(root)
        raise
    return project


MAX_PROJECT_SCENES = 128


def list_scenes(project: Project) -> list[str]:
    project.scene_path()
    # The first browser covers the top-level scenes directory and the active scene.
    folder = project.root / "scenes"
    if folder.is_symlink() or not folder.is_dir():
        raise ValueError("Project scenes must use a regular scenes directory.")
    references = {project.scene}
    with os.scandir(folder) as entries:
        for entry in entries:
            if not entry.name.endswith(".forge.json"):
                continue
            reference = f"scenes/{entry.name}"
            replace(project, scene=reference).scene_path()
            if not entry.is_file(follow_symlinks=False):
                continue
            references.add(reference)
            if len(references) > MAX_PROJECT_SCENES:
                raise ValueError("The scene browser supports at most 128 scenes.")
    return sorted(references)


def new_scene_target(project: Project, name: str) -> Project:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9 _-]{0,63}", name):
        raise ValueError("Scene names need 1–64 letters, digits, spaces, underscores or hyphens.")
    if len(list_scenes(project)) >= MAX_PROJECT_SCENES:
        raise ValueError("The scene browser supports at most 128 scenes.")
    target = replace(project, scene=f"scenes/{name}.forge.json")
    if target.scene_path().exists():
        raise FileExistsError("A scene with this filename already exists.")
    return target


def create_scene(project: Project, name: str) -> tuple[Project, Scene]:
    target = new_scene_target(project, name)
    scene = Scene(name=name)
    save_project_scene(target.root, target.scene_path(), scene, exclusive=True)
    return target, scene


def open_scene(project: Project, reference: str) -> tuple[Project, Scene]:
    target = replace(project, scene=reference)
    path = target.scene_path()
    if not path.is_file():
        raise ValueError("The selected scene is missing or is not a regular file.")
    return target, load_project_scene(target.root, path)
