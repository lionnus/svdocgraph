"""Shared fixtures.

The tests must run without a real `bender` installation (it is a Rust binary, and
CI for a Python package should not need one to test the Python). `stub_bender`
puts a tiny script on the PATH that answers the three commands SVDocGraph asks of
bender, using the fixture project in `tests/fixtures/demo`. The real thing is
covered by the integration workflow, which runs against actual PULP repositories.
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
    # Real bender is always invoked with cwd=<project root>.
    rtl = os.path.join(os.getcwd(), "rtl")
    files = [os.path.join(rtl, f) for f in sorted(os.listdir(rtl)) if f.endswith(".sv")]
    # demo_pkg and the interface must be compiled before their users.
    order = ["demo_pkg.sv", "demo_bus_if.sv", "demo_adder.sv", "demo_top.sv"]
    files.sort(key=lambda p: order.index(os.path.basename(p))
               if os.path.basename(p) in order else 99)
    return files

argv = sys.argv[1:]
if argv[:1] == ["--version"]:
    print("bender 0.28.1 (stub)")   # must work from any cwd
elif argv[:2] == ["script", "flist-plus"]:
    files = sources()
    print("\\n".join(files))
elif argv[:2] == ["sources", "-f"]:
    print(json.dumps({"package": "demo_ip", "files": sources()}))
else:
    sys.exit(1)
"""


@pytest.fixture
def project_dir(tmp_path: Path) -> Path:
    """A throwaway copy of the demo bender project, inside a git repo."""
    dst = tmp_path / "demo"
    shutil.copytree(FIXTURES / "demo", dst)
    subprocess.run(["git", "init", "-q"], cwd=dst, check=False)
    return dst


@pytest.fixture
def stub_bender(tmp_path: Path, monkeypatch) -> Path:
    """Put a fake `bender` on the PATH."""
    bindir = tmp_path / "bin"
    bindir.mkdir(exist_ok=True)
    exe = bindir / "bender"
    exe.write_text(STUB_BENDER)
    exe.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bindir}{os.pathsep}{os.environ['PATH']}")
    return exe


@pytest.fixture
def run_cli(monkeypatch):
    """Run the CLI in-process from a given directory, returning its exit code."""
    from svdocgraph import cli

    def _run(*argv: str, cwd: Path | None = None) -> int:
        if cwd is not None:
            monkeypatch.chdir(cwd)
        return cli.main(list(argv))

    return _run


def have_dot() -> bool:
    return shutil.which("dot") is not None


needs_dot = pytest.mark.skipif(not have_dot(), reason="Graphviz `dot` not installed")
needs_pyslang = pytest.mark.skipif(
    not __import__("svdocgraph.extract", fromlist=["x"]).HAVE_PYSLANG,
    reason="usable pyslang (>=11) not installed",
)

__all__ = ["json", "sys", "needs_dot", "needs_pyslang"]
