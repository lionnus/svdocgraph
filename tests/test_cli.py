"""End-to-end CLI behaviour, driven against the fixture project via a stub bender."""

from __future__ import annotations

import json
import os
import re

import pytest
from conftest import needs_dot, needs_pyslang

from svdocgraph import project

pytestmark = [needs_pyslang]


def _gen(run_cli, project_dir, *extra):
    return run_cli("gen", *extra, cwd=project_dir)


def test_gen_writes_the_default_directory(run_cli, project_dir, stub_bender):
    assert _gen(run_cli, project_dir) == 0
    out = project_dir / project.DEFAULT_OUTPUT
    assert (out / "index.html").is_file()
    assert (out / "module-demo_top.html").is_file()
    assert (out / "module-demo_adder.html").is_file()
    assert (out / "assets" / "style.css").is_file()
    assert (out / project.BUILD_INFO).is_file()


def test_gen_extracts_the_expected_design(run_cli, project_dir, stub_bender):
    assert _gen(run_cli, project_dir) == 0
    model = json.loads((project_dir / project.DEFAULT_OUTPUT / "model.json").read_text())
    modules = model["modules"]
    assert {"demo_top", "demo_adder", "demo_bus_if"} <= set(modules)

    # Every owned module is elaborated as its own top, so widths come from the
    # module's default parameters.
    adder = modules["demo_adder"]
    widths = {p["name"]: p.get("width") for p in adder["ports"]}
    assert widths["sum_o"] == 8, "default parameter W=8 must resolve"
    assert {p["name"] for p in adder["ports"] if p["direction"] == "in"} == {
        "clk_i", "rst_ni", "a_i", "b_i"
    }
    # demo_top defaults W to demo_pkg::DataWidth, so the package import resolves.
    assert {p["name"]: p["width"] for p in modules["demo_top"]["ports"]}["y_o"] == 32

    top = modules["demo_top"]
    assert {i["module"] for i in top["instances"]} >= {"demo_adder"}
    assert {c["net"] for i in top["instances"] for c in i["conns"]} >= {"mid"}
    assert modules["demo_bus_if"]["kind"] == "interface"


def test_gen_is_idempotent(run_cli, project_dir, stub_bender):
    assert _gen(run_cli, project_dir) == 0
    before = (project_dir / ".gitignore").read_text()
    assert _gen(run_cli, project_dir) == 0
    assert (project_dir / ".gitignore").read_text() == before


def test_gen_adds_a_gitignore_rule(run_cli, project_dir, stub_bender):
    assert _gen(run_cli, project_dir) == 0
    assert "/.svdocgraph/" in (project_dir / ".gitignore").read_text()


def test_gen_refuses_a_foreign_output_directory(run_cli, project_dir, stub_bender):
    docs = project_dir / "docs"
    docs.mkdir()
    (docs / "index.html").write_text("<h1>hand written</h1>")
    (docs / "notes.md").write_text("keep me")

    assert _gen(run_cli, project_dir, "-o", "docs") == 2
    assert (docs / "index.html").read_text() == "<h1>hand written</h1>"

    assert _gen(run_cli, project_dir, "-o", "docs", "--force") == 0
    assert "hand written" not in (docs / "index.html").read_text()
    assert (docs / "notes.md").read_text() == "keep me", "unrelated files survive"


def test_gen_runs_from_a_subdirectory(run_cli, project_dir, stub_bender):
    assert run_cli("gen", cwd=project_dir / "rtl") == 0
    assert (project_dir / project.DEFAULT_OUTPUT / "index.html").is_file()


def test_config_drives_output_and_title(run_cli, project_dir, stub_bender):
    (project_dir / "svdocgraph.yml").write_text("output: build/docs\nname: Fancy Name\n")
    assert _gen(run_cli, project_dir) == 0
    index = project_dir / "build" / "docs" / "index.html"
    assert index.is_file()
    assert "Fancy Name" in index.read_text()
    assert not (project_dir / project.DEFAULT_OUTPUT).exists()


def test_search_index_is_inlined_and_valid(run_cli, project_dir, stub_bender):
    """A file:// page cannot fetch design.json, so the index must be embedded."""
    assert _gen(run_cli, project_dir) == 0
    html = (project_dir / project.DEFAULT_OUTPUT / "module-demo_top.html").read_text()
    m = re.search(r'<script id="svdg-data" type="application/json">(.*?)</script>',
                  html, re.S)
    assert m, "no inline search index"
    data = json.loads(m.group(1))
    assert {mod["name"] for mod in data["modules"]} >= {"demo_top", "demo_adder"}
    assert "</script>" not in m.group(1)


@needs_dot
def test_graphs_are_inlined_as_svg(run_cli, project_dir, stub_bender):
    assert _gen(run_cli, project_dir) == 0
    out = project_dir / project.DEFAULT_OUTPUT
    assert "<svg" in (out / "hierarchy.html").read_text()
    top = (out / "module-demo_top.html").read_text()
    assert "<svg" in top and "demo_adder" in top


def test_open_builds_when_missing(run_cli, project_dir, stub_bender, monkeypatch):
    opened = []
    monkeypatch.setattr("webbrowser.open", lambda url: opened.append(url) or True)
    assert run_cli("open", cwd=project_dir) == 0
    assert (project_dir / project.DEFAULT_OUTPUT / "index.html").is_file()
    assert opened and opened[0].startswith("file://")


def test_open_does_not_rebuild(run_cli, project_dir, stub_bender, monkeypatch):
    assert _gen(run_cli, project_dir) == 0
    stamp = (project_dir / project.DEFAULT_OUTPUT / "index.html").stat().st_mtime_ns
    monkeypatch.setattr("webbrowser.open", lambda url: True)
    monkeypatch.setattr("svdocgraph.cli._build_design",
                        lambda ctx: pytest.fail("open must not re-elaborate"))
    assert run_cli("open", cwd=project_dir) == 0
    assert (project_dir / project.DEFAULT_OUTPUT / "index.html").stat().st_mtime_ns == stamp


def test_init_writes_config_and_gitignore(run_cli, project_dir):
    assert run_cli("init", cwd=project_dir) == 0
    assert (project_dir / "svdocgraph.yml").is_file()
    assert "/.svdocgraph/" in (project_dir / ".gitignore").read_text()


def test_dump_writes_the_model(run_cli, project_dir, stub_bender, tmp_path):
    out = tmp_path / "design.json"
    assert run_cli("dump", "-o", str(out), cwd=project_dir) == 0
    data = json.loads(out.read_text())
    assert data["root_package"] == "demo_ip"
    assert "demo_top" in data["modules"]


def test_quiet_accepted_on_both_sides(run_cli, project_dir, stub_bender):
    assert run_cli("-q", "gen", cwd=project_dir) == 0
    assert run_cli("gen", "-q", cwd=project_dir) == 0


def test_missing_bender_fails_with_a_hint(run_cli, project_dir, monkeypatch, capsys):
    monkeypatch.setenv("PATH", "")           # nothing on the PATH at all
    assert run_cli("gen", cwd=project_dir) == 3
    err = capsys.readouterr().err
    assert "bender" in err and "pulp-platform" in err
    assert not (project_dir / project.DEFAULT_OUTPUT).exists()


def test_failing_bender_is_reported_in_its_own_words(run_cli, project_dir, tmp_path,
                                                     monkeypatch, capsys):
    """An unresolvable dependency is the most common real failure; bender explains
    it well, so that explanation must reach the user rather than 'no modules'."""
    bindir = tmp_path / "badbin"
    bindir.mkdir()
    exe = bindir / "bender"
    exe.write_text(
        "#!/bin/sh\n"
        'case "$1 $2" in\n'
        '  "--version ") echo "bender 0.28.1"; exit 0 ;;\n'
        "esac\n"
        'echo "     Cloning common_cells (https://github.com/pulp-platform/x.git)" >&2\n'
        "printf '\\033[31;1merror:\\033[m Requirement `^0.2.11` conflicts with other "
        "requirements on dependency `tech_cells_generic`.\\n' >&2\n"
        "exit 1\n"
    )
    exe.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bindir}:{os.environ['PATH']}")

    assert run_cli("gen", cwd=project_dir) == 4
    err = capsys.readouterr().err
    assert "conflicts with other requirements" in err
    assert "\x1b[31;1merror" not in err, "bender's colour codes must be stripped"
    assert "Cloning" not in err, "progress noise must not bury the error"
    assert not (project_dir / project.DEFAULT_OUTPUT).exists()


def test_build_is_an_alias_for_gen(run_cli, project_dir, stub_bender):
    assert run_cli("build", cwd=project_dir) == 0
    assert (project_dir / project.DEFAULT_OUTPUT / "index.html").is_file()
