"""Bender integration.

SVDocGraph is *Bender-aware*: instead of asking the user to list source files and
include directories, it drives `bender` directly to learn the full source set, the
include dirs, the macro defines, and - crucially - which dependency package every
file belongs to. That package map is what powers the provenance / ownership views.

Everything here degrades gracefully: if `bender` is missing or a command fails we
return empty structures and record a diagnostic rather than crashing.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import dataclass, field

import yaml

from .model import BenderPackage


@dataclass
class BenderInfo:
    """Everything we learn from bender for one project."""

    root_package: str = ""
    flist_plus: str = ""                       # text of `bender script flist-plus`
    file_to_package: dict[str, str] = field(default_factory=dict)
    packages: dict[str, BenderPackage] = field(default_factory=dict)
    root_files: list[str] = field(default_factory=list)   # files owned by root pkg
    diagnostics: list[str] = field(default_factory=list)


def have_bender() -> bool:
    return shutil.which("bender") is not None


def _run(args: list[str], cwd: str) -> str | None:
    try:
        out = subprocess.run(args, cwd=cwd, capture_output=True, text=True, check=True)
        return out.stdout
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None


def _read_root_name(project_root: str) -> str:
    path = os.path.join(project_root, "Bender.yml")
    try:
        with open(path) as fh:
            data = yaml.safe_load(fh)
        return (data.get("package") or {}).get("name", "") or ""
    except (OSError, yaml.YAMLError):
        return ""


def _parse_lock(project_root: str, packages: dict[str, BenderPackage]) -> None:
    """Enrich packages with locked revision / source from Bender.lock."""
    path = os.path.join(project_root, "Bender.lock")
    try:
        with open(path) as fh:
            lock = yaml.safe_load(fh)
    except (OSError, yaml.YAMLError):
        return
    for name, entry in (lock.get("packages") or {}).items():
        pkg = packages.setdefault(name, BenderPackage(name=name))
        src = entry.get("source") or {}
        if isinstance(src, dict):
            # source is e.g. {"Git": "https://..."} or {"Path": "..."}
            for loc in src.values():
                pkg.source = str(loc)
        pkg.rev = entry.get("revision") or ""
        pkg.version = entry.get("version") or ""
        pkg.deps = list(entry.get("dependencies") or [])


def _flatten_sources(group: dict, root_pkg: str, info: BenderInfo) -> None:
    """Walk the nested `bender sources` JSON, recording file -> package."""
    pkg = group.get("package")
    for f in group.get("files", []):
        if isinstance(f, str):
            if pkg:
                info.file_to_package[os.path.realpath(f)] = pkg
                if pkg == root_pkg:
                    info.root_files.append(f)
        elif isinstance(f, dict):
            _flatten_sources(f, root_pkg, info)


def collect(project_root: str) -> BenderInfo:
    """Gather all bender-derived information for *project_root*."""
    info = BenderInfo()
    if not have_bender():
        info.diagnostics.append("`bender` not found on PATH; provenance disabled.")
        return info

    info.root_package = _read_root_name(project_root)

    flist = _run(["bender", "script", "flist-plus"], project_root)
    if flist is None:
        info.diagnostics.append("`bender script flist-plus` failed.")
    else:
        info.flist_plus = flist

    sources = _run(["bender", "sources", "-f"], project_root)
    if sources:
        try:
            data = json.loads(sources)
            # `-f` (flat) yields a list of groups; plain `sources` yields one nest.
            groups = data if isinstance(data, list) else [data]
            for g in groups:
                _flatten_sources(g, info.root_package, info)
        except json.JSONDecodeError:
            info.diagnostics.append("Could not parse `bender sources -f` JSON.")

    # Seed packages from the file map, then enrich from the lockfile.
    for name in set(info.file_to_package.values()):
        info.packages.setdefault(name, BenderPackage(name=name))
    if info.root_package:
        root = info.packages.setdefault(
            info.root_package, BenderPackage(name=info.root_package)
        )
        root.root = True
    _parse_lock(project_root, info.packages)

    return info


def write_command_file(info: BenderInfo, path: str) -> str | None:
    """Materialise the bender flist-plus as a slang command file. Returns path."""
    if not info.flist_plus:
        return None
    with open(path, "w") as fh:
        fh.write(info.flist_plus)
    return path
