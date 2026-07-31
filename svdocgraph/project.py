"""Project conventions: where the docs go, how they are found, and how to open them.

SVDocGraph is meant to be installed once and run inside any Bender repository with
no arguments, the way ``cargo doc`` or ``mkdocs build`` are. That convenience lives
here:

* :func:`find_project_root` - run the tool from any subdirectory; the project root
  is the nearest ancestor with a ``Bender.yml``.
* :data:`DEFAULT_OUTPUT` - generated docs land in a single tool-owned directory,
  ``.svdocgraph/``, so a project only ever needs one ``.gitignore`` line and the
  output can never collide with a hand-written ``docs/``.
* :func:`load_config` - optional ``svdocgraph.yml`` so ``make docs`` needs no flags.
* :func:`ensure_gitignored` - keep the generated directory out of commits.
* :func:`read_build_info` / :func:`write_build_info` - a marker file inside the
  output directory. It records what produced the build (so ``svdocgraph open`` can
  report its age) and marks the directory as ours, so a build never deletes files
  from a directory SVDocGraph did not generate.
"""

from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass, field

import yaml

#: Generated documentation directory, relative to the project root.
DEFAULT_OUTPUT = ".svdocgraph"

#: Marker written inside the output directory; also identifies it as ours.
BUILD_INFO = ".svdocgraph-build.json"

#: Config file names looked for in the project root, in order.
CONFIG_NAMES = ("svdocgraph.yml", "svdocgraph.yaml", ".svdocgraph.yml")


def find_project_root(start: str = ".") -> tuple[str, bool]:
    """Nearest ancestor of *start* containing a ``Bender.yml``.

    Returns ``(root, found)``. When no ``Bender.yml`` is found anywhere up the
    tree, ``start`` itself is returned with ``found=False`` - the caller decides
    whether that is fatal.
    """
    cur = os.path.abspath(start)
    while True:
        if os.path.isfile(os.path.join(cur, "Bender.yml")):
            return cur, True
        parent = os.path.dirname(cur)
        if parent == cur:
            return os.path.abspath(start), False
        cur = parent


# -- config ----------------------------------------------------------------


@dataclass
class Config:
    """Optional per-project settings from ``svdocgraph.yml``."""

    output: str = DEFAULT_OUTPUT
    tops: list[str] = field(default_factory=list)
    name: str = ""          # display name; defaults to the project directory name
    path: str = ""          # config file this came from ("" if none)

    @property
    def found(self) -> bool:
        return bool(self.path)


def load_config(project_root: str) -> Config:
    """Read ``svdocgraph.yml`` from *project_root*, if present.

    Unknown keys are ignored so a config written for a newer version still loads.
    """
    for name in CONFIG_NAMES:
        path = os.path.join(project_root, name)
        if not os.path.isfile(path):
            continue
        try:
            with open(path) as fh:
                data = yaml.safe_load(fh) or {}
        except (OSError, yaml.YAMLError):
            return Config()
        if not isinstance(data, dict):
            return Config()
        tops = data.get("tops") or data.get("top") or []
        if isinstance(tops, str):
            tops = [tops]
        return Config(
            output=str(data.get("output") or DEFAULT_OUTPUT),
            tops=[str(t) for t in tops],
            name=str(data.get("name") or ""),
            path=path,
        )
    return Config()


CONFIG_TEMPLATE = """\
# SVDocGraph project configuration - https://github.com/lkesting/svdocgraph
# Every key is optional; delete what you do not need.

# Where `svdocgraph gen` writes the site (relative to this file).
output: {output}

# Extra top modules to elaborate, for tops only reachable from a testbench.
# tops:
#   - my_top
#   - my_other_top

# Display name in the site header (defaults to the project directory name).
# name: My Design
"""


def write_config(project_root: str, output: str = DEFAULT_OUTPUT) -> str | None:
    """Create ``svdocgraph.yml`` in *project_root*. Returns the path, or None if
    a config already exists."""
    existing = load_config(project_root)
    if existing.found:
        return None
    path = os.path.join(project_root, CONFIG_NAMES[0])
    with open(path, "w") as fh:
        fh.write(CONFIG_TEMPLATE.format(output=output))
    return path


# -- git -------------------------------------------------------------------


def git_root(path: str) -> str | None:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=path, capture_output=True, text=True, check=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None
    return out.stdout.strip() or None


def _is_ignored(repo: str, target: str) -> bool:
    """True if git already ignores *target* (honours nested and global excludes)."""
    try:
        rc = subprocess.run(
            ["git", "check-ignore", "-q", target],
            cwd=repo, capture_output=True, text=True,
        ).returncode
    except FileNotFoundError:
        return False
    return rc == 0


def ensure_gitignored(outdir: str) -> str | None:
    """Make sure the generated directory is not committed.

    Appends a rule to the repository's top-level ``.gitignore`` (creating it if
    needed) when *outdir* is inside a git work tree and not already ignored.
    Returns the ``.gitignore`` path if it was modified, else ``None``.
    """
    outdir = os.path.abspath(outdir)
    repo = git_root(os.path.dirname(outdir))
    if not repo:
        return None
    rel = os.path.relpath(outdir, repo)
    if rel.startswith(".."):        # output lives outside the repo; nothing to do
        return None
    probe = os.path.join(outdir, "index.html")
    if _is_ignored(repo, probe):
        return None

    path = os.path.join(repo, ".gitignore")
    rule = "/" + rel.replace(os.sep, "/").rstrip("/") + "/"
    existing = ""
    if os.path.isfile(path):
        with open(path) as fh:
            existing = fh.read()
    block = "" if not existing or existing.endswith("\n") else "\n"
    block += f"\n# SVDocGraph generated documentation\n{rule}\n"
    with open(path, "a") as fh:
        fh.write(block)
    return path


# -- build marker ----------------------------------------------------------


def read_build_info(outdir: str) -> dict | None:
    try:
        with open(os.path.join(outdir, BUILD_INFO)) as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def write_build_info(outdir: str, **fields) -> None:
    with open(os.path.join(outdir, BUILD_INFO), "w") as fh:
        json.dump({"tool": "svdocgraph", **fields}, fh, indent=2)


def is_ours(outdir: str) -> bool:
    """True if *outdir* is empty, missing, or a previous SVDocGraph build."""
    if not os.path.isdir(outdir):
        return True
    if not os.listdir(outdir):
        return True
    return os.path.isfile(os.path.join(outdir, BUILD_INFO))


def index_url(outdir: str) -> str:
    """``file://`` URL of the generated entry page."""
    index = os.path.abspath(os.path.join(outdir, "index.html"))
    return "file://" + index
