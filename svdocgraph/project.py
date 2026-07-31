"""The rules of a project: the root, the output directory and the settings.

The user runs the tool in a Bender project without options. These functions make
that possible. They find the project root, read the optional settings file, keep
the output directory out of the commits, and mark the output directory. The mark
makes sure that the tool removes only its own files.
"""

from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass, field

import yaml

#: The output directory, relative to the project root.
DEFAULT_OUTPUT = ".svdocgraph"

#: The mark in the output directory. It shows that the tool made the directory.
BUILD_INFO = ".svdocgraph-build.json"

#: The names of the settings file, in the sequence of the search.
CONFIG_NAMES = ("svdocgraph.yml", "svdocgraph.yaml", ".svdocgraph.yml")


def find_project_root(start: str = ".") -> tuple[str, bool]:
    """Finds the nearest parent directory that contains a `Bender.yml` file.

    Gives (root, found). If there is no such directory, gives *start* and False.
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
    """The settings from `svdocgraph.yml`. Each one is optional."""

    output: str = DEFAULT_OUTPUT
    tops: list[str] = field(default_factory=list)
    name: str = ""          # The title. The default is the directory name
    doc_dirs: list = field(default_factory=list)   # More directories with Markdown
    docs_enabled: bool = True                      # `docs: false` stops the search
    path: str = ""          # The settings file. Empty if there is none

    @property
    def found(self) -> bool:
        return bool(self.path)


def load_config(project_root: str) -> Config:
    """Reads `svdocgraph.yml`, if it is available.

    The function ignores an unknown key. Thus a file from a newer version loads.
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
        # `docs` gives more directories with Markdown, or `false` to use none.
        raw_docs = data.get("docs", None)
        enabled = raw_docs is not False
        if isinstance(raw_docs, str):
            raw_docs = [raw_docs]
        doc_dirs = [str(d) for d in raw_docs] if isinstance(raw_docs, list) else []
        return Config(
            output=str(data.get("output") or DEFAULT_OUTPUT),
            tops=[str(t) for t in tops],
            name=str(data.get("name") or ""),
            doc_dirs=doc_dirs,
            docs_enabled=enabled,
            path=path,
        )
    return Config()


CONFIG_TEMPLATE = """\
# SVDocGraph project configuration - https://github.com/lionnus/svdocgraph
# Each key is optional. Remove the keys that you do not need.

# The output directory, relative to this file.
output: {output}

# Additional top modules. Use this for a top that only a testbench instantiates.
# tops:
#   - my_top
#   - my_other_top

# The title in the page header. The default is the name of the directory.
# name: My Design
"""


def write_config(project_root: str, output: str = DEFAULT_OUTPUT) -> str | None:
    """Writes `svdocgraph.yml`. Gives the path, or None if the file exists."""
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
    """True if git ignores the target."""
    return subprocess.run(
        ["git", "check-ignore", "-q", target],
        cwd=repo, capture_output=True, text=True,
    ).returncode == 0


def ensure_gitignored(outdir: str) -> str | None:
    """Keeps the output directory out of the commits.

    Adds a rule to the `.gitignore` file of the repository. Does nothing if the
    directory is not in a repository, or if git ignores it. Gives the path of the
    changed file, or None.
    """
    outdir = os.path.abspath(outdir)
    repo = git_root(os.path.dirname(outdir))
    if not repo:
        return None
    rel = os.path.relpath(outdir, repo)
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
    """True if the directory is empty, or if the tool made it."""
    if not os.path.isdir(outdir):
        return True
    if not os.listdir(outdir):
        return True
    return os.path.isfile(os.path.join(outdir, BUILD_INFO))


def index_url(outdir: str) -> str:
    """The `file://` URL of the first page."""
    index = os.path.abspath(os.path.join(outdir, "index.html"))
    return "file://" + index
