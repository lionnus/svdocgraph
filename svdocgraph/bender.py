"""Reads the project data from bender.

The user does not list the source files. The tool asks bender for them, and also
for the include directories, the macro definitions, and the package that owns each
file. The package data gives each module its origin in the documentation.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from dataclasses import dataclass, field

import yaml

from .model import BenderPackage


@dataclass
class BenderInfo:
    """The data that bender gives for one project."""

    root_package: str = ""
    flist_plus: str = ""                       # Output of `bender script flist-plus`
    file_to_package: dict[str, str] = field(default_factory=dict)
    packages: dict[str, BenderPackage] = field(default_factory=dict)
    root_files: list[str] = field(default_factory=list)   # Files of the root package
    diagnostics: list[str] = field(default_factory=list)
    #: The message from bender if it cannot describe the project. Usually a
    #: dependency that bender cannot resolve.
    failure: str = ""


def have_bender() -> bool:
    return shutil.which("bender") is not None


def _run(args: list[str], cwd: str) -> tuple[str | None, str]:
    """Runs a bender command. Gives (output, error). The output is None on a failure.

    bender writes a clear message on a failure. Thus the tool keeps that message.
    """
    try:
        out = subprocess.run(args, cwd=cwd, capture_output=True, text=True, check=True)
    except subprocess.CalledProcessError as exc:
        return None, _clean_error(exc.stderr or exc.stdout or "")
    return out.stdout, ""


_ANSI = re.compile(r"\x1b\[[0-9;]*m")


def _clean_error(text: str) -> str:
    """Keeps only the part of the bender output that gives the cause.

    bender puts colours and progress messages in the same output. Thus this
    function removes the colours and starts at the first `error:` line.
    """
    lines = [_ANSI.sub("", ln).rstrip() for ln in text.strip().splitlines()]
    lines = [ln for ln in lines if ln.strip()]
    for i, ln in enumerate(lines):
        if ln.lstrip().lower().startswith("error"):
            return "\n".join(lines[i:i + 6])
    return "\n".join(lines[-6:])


def _read_root_name(project_root: str) -> str:
    path = os.path.join(project_root, "Bender.yml")
    try:
        with open(path) as fh:
            data = yaml.safe_load(fh)
        return (data.get("package") or {}).get("name", "") or ""
    except (OSError, yaml.YAMLError):
        return ""


def _parse_lock(project_root: str, packages: dict[str, BenderPackage]) -> None:
    """Adds the revision and the source of each package from Bender.lock."""
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
            # The source is {"Git": "https://..."} or {"Path": "..."}
            for loc in src.values():
                pkg.source = str(loc)
        pkg.rev = entry.get("revision") or ""
        pkg.version = entry.get("version") or ""
        pkg.deps = list(entry.get("dependencies") or [])


def _flatten_sources(group: dict, root_pkg: str, info: BenderInfo) -> None:
    """Reads the JSON from `bender sources`. It gives the package of each file."""
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
    """Collects all the bender data for the project."""
    info = BenderInfo()
    if not have_bender():
        info.diagnostics.append("`bender` is not on the PATH. The pages show no package data.")
        return info

    info.root_package = _read_root_name(project_root)

    flist, err = _run(["bender", "script", "flist-plus"], project_root)
    if flist is None:
        # Without the file list the tool cannot continue.
        info.failure = err or "`bender script flist-plus` failed."
        return info
    info.flist_plus = flist

    sources, err = _run(["bender", "sources", "-f"], project_root)
    if sources is None and err:
        info.diagnostics.append(f"`bender sources -f` failed. The pages show no package data:\n{err}")
    if sources:
        try:
            data = json.loads(sources)
            # The `-f` option gives a list of groups.
            groups = data if isinstance(data, list) else [data]
            for g in groups:
                _flatten_sources(g, info.root_package, info)
        except json.JSONDecodeError:
            info.diagnostics.append("The tool cannot read the JSON from `bender sources -f`.")

    # Make one package for each name, then add the data from the lockfile.
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
    """Write the bender file list as a slang command file. Returns the path.

    slang divides a command file at each space. Thus each entry has quotation
    marks. If not, a project in a directory with a space in its name fails.
    """
    if not info.flist_plus:
        return None
    lines = []
    for raw in info.flist_plus.splitlines():
        entry = raw.strip()
        if not entry:
            continue
        lines.append(entry if entry.startswith('"') else f'"{entry}"')
    with open(path, "w") as fh:
        fh.write("\n".join(lines) + "\n")
    return path
