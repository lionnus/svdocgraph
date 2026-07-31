"""Checks for the programs that the tool needs.

`bender` gives the source set. Without it the tool cannot start. Graphviz
calculates the graph layouts. Without it the tool writes the pages but not the
graphs. `pyslang` elaborates the design. An old version finds no modules. Pygments
gives the colours of the code.

These checks give a clear message in each of these conditions. The `doctor`
command shows the results.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from dataclasses import dataclass

#: The pyslang versions that this tool can drive. The `Driver` class moved to
#: `pyslang.driver` in version 11. An older version finds no modules.
PYSLANG_MIN = 11
PYSLANG_MAX = 12    # exclusive

BENDER_HINT = (
    "Install bender:  curl https://pulp-platform.github.io/bender/init -sSf | sh\n"
    "  As an option:  cargo install bender"
)
DOT_HINT = (
    "Install Graphviz:  apt install graphviz, brew install graphviz, or "
    "dnf install graphviz"
)
PYSLANG_HINT = (
    f"Install svdocgraph again to get pyslang >={PYSLANG_MIN},<{PYSLANG_MAX}:  "
    "uv tool install --force svdocgraph"
)
PYGMENTS_HINT = "Install svdocgraph again:  uv tool install --force svdocgraph"


@dataclass
class Dep:
    name: str
    ok: bool
    detail: str          # The version, or the cause of the failure
    hint: str = ""
    required: bool = True


def _first_line(text: str) -> str:
    return (text or "").strip().splitlines()[0] if (text or "").strip() else ""


def check_bender() -> Dep:
    path = shutil.which("bender")
    if not path:
        return Dep("bender", False, "not on the PATH", BENDER_HINT)
    try:
        out = subprocess.run(["bender", "--version"], capture_output=True, text=True,
                             check=True, timeout=30)
    except (subprocess.SubprocessError, OSError):
        return Dep("bender", False, f"at {path}, but `bender --version` failed",
                   BENDER_HINT)
    return Dep("bender", True, _first_line(out.stdout) or path)


def check_dot() -> Dep:
    path = shutil.which("dot")
    if not path:
        return Dep("dot (Graphviz)", False, "not on the PATH. The pages show no graphs",
                   DOT_HINT, required=False)
    try:
        out = subprocess.run(["dot", "-V"], capture_output=True, text=True,
                             check=True, timeout=30)
    except (subprocess.SubprocessError, OSError):
        return Dep("dot (Graphviz)", False, f"at {path}, but `dot -V` failed",
                   DOT_HINT, required=False)
    # `dot -V` writes to stderr.
    return Dep("dot (Graphviz)", True, _first_line(out.stderr) or _first_line(out.stdout))


def check_pyslang() -> Dep:
    try:
        import pyslang
    except ImportError:
        return Dep("pyslang", False, "not installed", PYSLANG_HINT)
    version = getattr(pyslang, "__version__", "unknown")
    from .extract import HAVE_PYSLANG
    if not HAVE_PYSLANG:
        return Dep("pyslang", False,
                   f"version {version} has no Driver that this tool can use. "
                   f"It needs >={PYSLANG_MIN},<{PYSLANG_MAX}", PYSLANG_HINT)
    return Dep("pyslang", True, version)


def check_pygments() -> Dep:
    """Pygments gives the colours of the code. The pages operate without it."""
    try:
        import pygments
    except ImportError:
        return Dep("Pygments", False, "not installed. The code has no colours",
                   PYGMENTS_HINT, required=False)
    return Dep("Pygments", True, getattr(pygments, "__version__", "unknown"))


def check_all() -> list[Dep]:
    """Every item the tool needs. Each check runs one time."""
    return [check_bender(), check_dot(), check_pyslang(), check_pygments(),
            Dep("python", True, sys.version.split()[0])]
