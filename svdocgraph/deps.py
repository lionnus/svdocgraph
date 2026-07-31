"""External dependency discovery and reporting.

SVDocGraph leans on three things that are not ordinary Python imports:

* ``bender`` - a Rust binary that owns the source set and the package map. Without
  it there is nothing to elaborate, so it is *required*.
* ``dot`` (Graphviz) - lays out every graph. The site still builds without it, but
  every diagram is missing, so it is *strongly recommended* rather than required.
* ``pyslang`` - a Python wheel, but one whose API moved between releases; a wrong
  version elaborates nothing instead of failing loudly.

This module turns "it produced an empty site" into an actionable message, and backs
``svdocgraph doctor``.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from dataclasses import dataclass

#: pyslang releases whose API this version drives. `Driver` moved to
#: `pyslang.driver` in 11.0; older releases silently elaborate nothing.
PYSLANG_MIN = 11
PYSLANG_MAX = 12    # exclusive

BENDER_HINT = (
    "Install bender:  curl https://pulp-platform.github.io/bender/init -sSf | sh\n"
    "             or:  cargo install bender"
)
DOT_HINT = (
    "Install Graphviz:  apt install graphviz  |  brew install graphviz  |  "
    "dnf install graphviz"
)
PYSLANG_HINT = (
    f"Reinstall svdocgraph so it picks up pyslang "
    f">={PYSLANG_MIN},<{PYSLANG_MAX}  (uv tool install --force svdocgraph)"
)


@dataclass
class Dep:
    name: str
    ok: bool
    detail: str          # version string, or why it is not usable
    hint: str = ""
    required: bool = True

    @property
    def status(self) -> str:
        return "ok" if self.ok else ("missing" if self.required else "not found")


def _first_line(text: str) -> str:
    return (text or "").strip().splitlines()[0] if (text or "").strip() else ""


def check_bender() -> Dep:
    path = shutil.which("bender")
    if not path:
        return Dep("bender", False, "not on PATH", BENDER_HINT)
    try:
        out = subprocess.run(["bender", "--version"], capture_output=True, text=True,
                             check=True, timeout=30)
    except (subprocess.SubprocessError, OSError):
        return Dep("bender", False, f"found at {path} but `bender --version` failed",
                   BENDER_HINT)
    return Dep("bender", True, _first_line(out.stdout) or path)


def check_dot() -> Dep:
    path = shutil.which("dot")
    if not path:
        return Dep("dot (Graphviz)", False, "not on PATH - graphs will be omitted",
                   DOT_HINT, required=False)
    try:
        out = subprocess.run(["dot", "-V"], capture_output=True, text=True,
                             check=True, timeout=30)
    except (subprocess.SubprocessError, OSError):
        return Dep("dot (Graphviz)", False, f"found at {path} but `dot -V` failed",
                   DOT_HINT, required=False)
    # `dot -V` reports on stderr.
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
                   f"{version} has no usable Driver "
                   f"(need >={PYSLANG_MIN},<{PYSLANG_MAX})", PYSLANG_HINT)
    return Dep("pyslang", True, version)


def check_all() -> list[Dep]:
    return [check_bender(), check_dot(), check_pyslang(),
            Dep("python", True, sys.version.split()[0])]


def missing_required() -> list[Dep]:
    return [d for d in check_all() if d.required and not d.ok]


def optional_gaps() -> list[Dep]:
    return [d for d in check_all() if not d.required and not d.ok]
