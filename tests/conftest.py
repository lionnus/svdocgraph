"""The fixtures that the tests use.

The tests operate without an installation of bender. The `stub_bender` fixture
puts a small script on the PATH. The script answers the three commands that the
tool sends to bender. The integration workflow uses the true bender.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"

STUB_BENDER = """\
#!/usr/bin/env python3
import json, os, sys

def sources():
    # The tool always calls bender in the project root.
    rtl = os.path.join(os.getcwd(), "rtl")
    files = [os.path.join(rtl, f) for f in sorted(os.listdir(rtl)) if f.endswith(".sv")]
    # The package and the interface must come before the modules that use them.
    order = ["demo_pkg.sv", "demo_bus_if.sv", "demo_adder.sv", "demo_top.sv",
             "demo_gen.sv"]
    files.sort(key=lambda p: order.index(os.path.basename(p))
               if os.path.basename(p) in order else 99)
    return files

argv = sys.argv[1:]
if argv[:1] == ["--version"]:
    print("bender 0.28.1 (stub)")   # This must operate in each directory
elif argv[:2] == ["script", "flist-plus"]:
    files = sources()
    print("\\n".join(files))
elif argv[:2] == ["sources", "-f"]:
    # RTLDOC_STUB_DEP_FILES gives the files of a second package. bender puts the
    # group of a dependency in the group of the root package.
    dep = [f for f in os.environ.get("RTLDOC_STUB_DEP_FILES", "").split(",") if f]
    root = [f for f in sources() if os.path.basename(f) not in dep]
    group = {"package": "demo_ip", "files": list(root)}
    if dep:
        group["files"].append({
            "package": "demo_dep",
            "files": [f for f in sources() if os.path.basename(f) in dep],
        })
    print(json.dumps(group))
else:
    sys.exit(1)
"""


@pytest.fixture
def project_dir(tmp_path: Path) -> Path:
    """A copy of the example project, in a new git repository."""
    dst = tmp_path / "demo"
    shutil.copytree(FIXTURES / "demo", dst)
    subprocess.run(["git", "init", "-q"], cwd=dst, check=False)
    return dst


@pytest.fixture
def stub_bender(tmp_path: Path, monkeypatch) -> Path:
    """Puts a substitute for `bender` on the PATH."""
    bindir = tmp_path / "bin"
    bindir.mkdir(exist_ok=True)
    exe = bindir / "bender"
    exe.write_text(STUB_BENDER)
    exe.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bindir}{os.pathsep}{os.environ['PATH']}")
    return exe


@pytest.fixture
def run_cli(monkeypatch):
    """Runs the command-line interface in a directory. Gives the exit code."""
    from rtldoc import cli

    def _run(*argv: str, cwd: Path | None = None) -> int:
        if cwd is not None:
            monkeypatch.chdir(cwd)
        return cli.main(list(argv))

    return _run


def have_dot() -> bool:
    return shutil.which("dot") is not None


needs_dot = pytest.mark.skipif(not have_dot(), reason="Graphviz `dot` not installed")
needs_pyslang = pytest.mark.skipif(
    not __import__("rtldoc.extract", fromlist=["x"]).HAVE_PYSLANG,
    reason="usable pyslang (>=11) not installed",
)

__all__ = ["json", "sys", "needs_dot", "needs_pyslang"]


@pytest.fixture
def stub_bender_with_dependency(stub_bender, monkeypatch):
    """The same bender, but `demo_adder` belongs to a second package."""
    monkeypatch.setenv("RTLDOC_STUB_DEP_FILES", "demo_adder.sv")
    return stub_bender
