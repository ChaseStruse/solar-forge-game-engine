"""Bounded quarantine browsing and exclusive, byte-preserving asset restoration."""

import hashlib
import os
import re
import stat
from dataclasses import dataclass
from pathlib import Path

from solar_forge_engine.core.sprite import MAX_PIXEL_BYTES
from solar_forge_engine.project.cleanup import MAX_SCAN_BYTES, MAX_SCAN_FILES
from solar_forge_engine.project.workspace import Project


@dataclass(frozen=True)
class QuarantinedAsset:
    reference: str
    size: int
    fingerprint: str


def quarantine_folder(project: Project) -> Path:
    project.scene_path()
    folder = project.root / ".asset-quarantine"
    if folder.is_symlink():
        raise ValueError("Quarantine folders must not use symbolic links.")
    return folder


def inspect_asset(project: Project, reference: str) -> QuarantinedAsset:
    if not re.fullmatch(r"[0-9a-f]{32}/[0-9a-f]{64}\.rgba", reference):
        raise ValueError("Invalid quarantine asset path.")
    folder = quarantine_folder(project)
    path = folder / reference
    if path.parent.is_symlink() or path.is_symlink() or not path.is_file():
        raise ValueError("Quarantined assets must be regular files without symbolic links.")
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(descriptor, "rb") as handle:
        if not stat.S_ISREG(os.fstat(handle.fileno()).st_mode):
            raise ValueError("Quarantined assets must be regular files.")
        raw = handle.read(MAX_PIXEL_BYTES + 1)
    if not raw or len(raw) > MAX_PIXEL_BYTES or len(raw) % 4:
        raise ValueError("Quarantined asset has invalid or oversized RGBA bytes.")
    return QuarantinedAsset(reference, len(raw), hashlib.sha256(raw).hexdigest())


def list_quarantined(project: Project) -> tuple[QuarantinedAsset, ...]:
    folder = quarantine_folder(project)
    if not folder.exists():
        return ()
    entries: list[QuarantinedAsset] = []
    count = total = 0
    with os.scandir(folder) as batches:
        for batch in batches:
            count += 1
            if (
                count > MAX_SCAN_FILES
                or not re.fullmatch(r"[0-9a-f]{32}", batch.name)
                or not batch.is_dir(follow_symlinks=False)
            ):
                raise ValueError("Quarantine scan is incomplete or contains unknown entries.")
            with os.scandir(batch.path) as files:
                for file in files:
                    count += 1
                    if count > MAX_SCAN_FILES:
                        raise ValueError("Quarantine scan exceeds its 512-entry limit.")
                    asset = inspect_asset(project, f"{batch.name}/{file.name}")
                    total += asset.size
                    if total > MAX_SCAN_BYTES:
                        raise ValueError("Quarantine scan exceeds its 32 MiB limit.")
                    entries.append(asset)
    return tuple(sorted(entries, key=lambda asset: asset.reference))


def restore_asset(project: Project, asset: QuarantinedAsset) -> None:
    if inspect_asset(project, asset.reference) != asset:
        raise ValueError("Quarantined asset changed after review. Refresh before restoring.")
    assets = project.root / "assets"
    if assets.is_symlink() or not assets.is_dir():
        raise ValueError("Restoration requires a regular assets folder.")
    source = quarantine_folder(project) / asset.reference
    target = assets / source.name
    # Exclusive publication also refuses existing files, directories and dangling symlinks.
    os.link(source, target, follow_symlinks=False)
    # If unlink fails, both copies remain available; never roll back by deleting a target
    # that another process might have replaced. Concurrent editing is not supported.
    source.unlink()


def purge_asset(project: Project, asset: QuarantinedAsset) -> None:
    """Remove only a reviewed quarantine file; leave assets and scene data intact.

    Concurrent external modification during this operation is not supported.
    """
    if inspect_asset(project, asset.reference) != asset:
        raise ValueError("Quarantined asset changed after review. Refresh before purging.")
    (quarantine_folder(project) / asset.reference).unlink()
