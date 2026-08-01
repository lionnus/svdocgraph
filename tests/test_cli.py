"""The commands, from end to end, with the example project."""

from __future__ import annotations

import json
import os
import re

import pytest
from conftest import needs_dot, needs_pyslang

from rtldoc import deps, project

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
    assert "/.rtldoc/" in (project_dir / ".gitignore").read_text()


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
    (project_dir / "rtldoc.yml").write_text("output: build/docs\nname: Fancy Name\n")
    assert _gen(run_cli, project_dir) == 0
    index = project_dir / "build" / "docs" / "index.html"
    assert index.is_file()
    assert "Fancy Name" in index.read_text()
    assert not (project_dir / project.DEFAULT_OUTPUT).exists()


def test_the_search_index_is_one_script_that_each_page_loads(run_cli, project_dir,
                                                             stub_bender):
    """A `file://` page cannot read a file with fetch, but it can load a script."""
    from rtldoc.check import SEARCH_INDEX
    out = project_dir / project.DEFAULT_OUTPUT
    assert _gen(run_cli, project_dir) == 0
    m = SEARCH_INDEX.search((out / "assets" / "search.js").read_text())
    assert m, "no search index"
    data = json.loads(m.group(1))
    assert {mod["name"] for mod in data["modules"]} >= {"demo_top", "demo_adder"}
    assert "</script>" not in m.group(1)
    for page in ("index.html", "module-demo_top.html"):
        html = (out / page).read_text()
        assert '<script src="assets/search.js">' in html
        assert "demo_adder" not in html.split("<footer")[-1], "no copy in the page"


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
    monkeypatch.setattr("rtldoc.cli._build_design",
                        lambda ctx: pytest.fail("open must not re-elaborate"))
    assert run_cli("open", cwd=project_dir) == 0
    assert (project_dir / project.DEFAULT_OUTPUT / "index.html").stat().st_mtime_ns == stamp


def test_init_writes_config_and_gitignore(run_cli, project_dir):
    assert run_cli("init", cwd=project_dir) == 0
    assert (project_dir / "rtldoc.yml").is_file()
    assert "/.rtldoc/" in (project_dir / ".gitignore").read_text()


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
    """A dependency that bender cannot resolve is the most usual failure. bender
    gives a clear message, thus the user must see that message."""
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


def test_extra_tops_are_passed_to_the_extractor(run_cli, project_dir, stub_bender):
    (project_dir / "rtldoc.yml").write_text("tops: [demo_bus_if]\n")
    seen = {}

    def spy(ctx):
        seen["tops"] = ctx.tops
        raise SystemExit(0)

    import rtldoc.cli as cli
    real = cli._build_design
    cli._build_design = spy
    try:
        with pytest.raises(SystemExit):
            run_cli("gen", "--top", "demo_top", cwd=project_dir)
    finally:
        cli._build_design = real
    assert seen["tops"] == ["demo_bus_if", "demo_top"], "config tops come first, then -top"


def test_a_directory_without_bender_yml_warns(run_cli, tmp_path, stub_bender, capsys):
    assert run_cli("gen", cwd=tmp_path) != 0
    assert "No Bender.yml" in capsys.readouterr().err


def test_open_explains_a_browser_that_will_not_start(run_cli, project_dir, stub_bender,
                                                     monkeypatch, capsys):
    monkeypatch.setattr("webbrowser.open", lambda url: False)
    assert run_cli("open", cwd=project_dir) == 0
    assert "Open this URL manually" in capsys.readouterr().err


class _FakeServer:
    """A substitute for socketserver.TCPServer. It stops after one request."""

    served = False

    def __init__(self, addr, handler):
        self.addr = addr

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def serve_forever(self):
        _FakeServer.served = True
        raise KeyboardInterrupt


def test_serve_builds_then_serves(run_cli, project_dir, stub_bender, monkeypatch):
    import socketserver
    _FakeServer.served = False
    monkeypatch.setattr(socketserver, "TCPServer", _FakeServer)
    assert run_cli("serve", "-p", "8123", cwd=project_dir) == 0
    assert _FakeServer.served
    assert (project_dir / project.DEFAULT_OUTPUT / "index.html").is_file()


def test_serve_can_skip_the_build(run_cli, project_dir, stub_bender, monkeypatch):
    import socketserver
    assert _gen(run_cli, project_dir) == 0
    monkeypatch.setattr(socketserver, "TCPServer", _FakeServer)
    monkeypatch.setattr("rtldoc.cli._build_design",
                        lambda ctx: pytest.fail("--no-build must not re-elaborate"))
    assert run_cli("serve", "--no-build", cwd=project_dir) == 0


def test_serve_reports_a_busy_port(run_cli, project_dir, stub_bender, monkeypatch, capsys):
    import socketserver

    def busy(addr, handler):
        raise OSError("Address already in use")

    monkeypatch.setattr(socketserver, "TCPServer", busy)
    assert run_cli("serve", cwd=project_dir) == 1
    assert "Cannot listen on port" in capsys.readouterr().err


def test_dump_also_stops_when_bender_fails(run_cli, project_dir, tmp_path, monkeypatch):
    bindir = tmp_path / "bin2"
    bindir.mkdir()
    exe = bindir / "bender"
    exe.write_text(
        "#!/bin/sh\n"
        '[ "$1" = "--version" ] && { echo "bender 0.28.1"; exit 0; }\n'
        "echo 'error: no such target' >&2\nexit 1\n"
    )
    exe.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bindir}:{os.environ['PATH']}")
    out = tmp_path / "design.json"
    assert run_cli("dump", "-o", str(out), cwd=project_dir) == 4
    assert not out.exists()


def test_doctor_lists_graphviz_as_optional(run_cli, stub_bender, monkeypatch, capsys):
    """Graphviz is not necessary. Its absence gives a warning, not an error."""
    import shutil as _shutil
    real = _shutil.which
    monkeypatch.setattr(deps.shutil, "which",
                        lambda name: None if name == "dot" else real(name))
    assert run_cli("doctor") == 0
    assert "The pages show no graphs" in capsys.readouterr().out


def test_gen_warns_but_continues_without_graphviz(run_cli, project_dir, stub_bender,
                                                  monkeypatch, capsys):
    import shutil as _shutil
    real = _shutil.which
    monkeypatch.setattr(deps.shutil, "which",
                        lambda name: None if name == "dot" else real(name))
    monkeypatch.setattr("rtldoc.dot.have_dot", lambda: False)
    assert _gen(run_cli, project_dir) == 0
    assert "The pages show no graphs" in capsys.readouterr().err
    assert (project_dir / project.DEFAULT_OUTPUT / "index.html").is_file()


def test_generate_loops_collapse_into_one_instance(run_cli, project_dir, stub_bender):
    """A generate loop makes N copies of one instance. The page shows one row."""
    assert _gen(run_cli, project_dir) == 0
    model = json.loads((project_dir / project.DEFAULT_OUTPUT / "model.json").read_text())
    stages = [i for i in model["modules"]["demo_gen"]["instances"] if i["name"] == "i_stage"]
    assert len(stages) == 1
    assert stages[0]["count"] == 4
    assert stages[0]["array"] is True


def test_init_keeps_an_existing_config(run_cli, project_dir, capsys):
    (project_dir / "rtldoc.yml").write_text("name: Mine\n")
    assert run_cli("init", cwd=project_dir) == 0
    assert (project_dir / "rtldoc.yml").read_text() == "name: Mine\n"
    assert "already exists" in capsys.readouterr().err


def test_an_empty_design_is_not_rendered(run_cli, project_dir, tmp_path, monkeypatch):
    """bender answers, but gives no source file. The tool writes no pages."""
    bindir = tmp_path / "emptybin"
    bindir.mkdir()
    exe = bindir / "bender"
    exe.write_text(
        "#!/bin/sh\n"
        '[ "$1" = "--version" ] && { echo "bender 0.28.1"; exit 0; }\n'
        '[ "$1 $2" = "script flist-plus" ] && exit 0\n'
        '[ "$1 $2" = "sources -f" ] && { echo "{}"; exit 0; }\n'
        "exit 1\n"
    )
    exe.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bindir}:{os.environ['PATH']}")
    assert run_cli("gen", cwd=project_dir) == 1
    assert not (project_dir / project.DEFAULT_OUTPUT).exists()


def test_a_manifest_without_a_package_name_warns(run_cli, project_dir, stub_bender, capsys):
    """Without a package name, no package owns the files. slang can still find
    the tops, thus the run continues with a warning."""
    (project_dir / "Bender.yml").write_text("sources:\n  - rtl/demo_adder.sv\n")
    assert run_cli("gen", cwd=project_dir) == 0
    assert "No bender root package" in capsys.readouterr().err


def test_init_outside_a_bender_project_warns(run_cli, tmp_path, capsys):
    assert run_cli("init", cwd=tmp_path) == 0
    assert "No Bender.yml" in capsys.readouterr().err


def test_interface_instances_are_not_child_modules(run_cli, project_dir, stub_bender):
    """`demo_bus_if i_bus (...)` is an interface instance, not a submodule."""
    assert _gen(run_cli, project_dir) == 0
    model = json.loads((project_dir / project.DEFAULT_OUTPUT / "model.json").read_text())
    by_name = {i["name"]: i for i in model["modules"]["demo_top"]["instances"]}
    assert by_name["i_bus"]["is_interface"] is True
    assert by_name["i_bus"]["module"] == "demo_bus_if"
    assert by_name["i_adder_a"]["is_interface"] is False


def test_every_module_has_a_page(run_cli, project_dir, stub_bender_with_dependency):
    """A module of a dependency also needs a page, not only a module of the root."""
    assert _gen(run_cli, project_dir) == 0
    out = project_dir / project.DEFAULT_OUTPUT
    model = json.loads((out / "model.json").read_text())
    packages = {m["package"] for m in model["modules"].values()}
    assert "demo_dep" in packages, "the fixture must give two packages"
    for name in model["modules"]:
        assert (out / f"module-{name}.html").is_file(), f"no page for {name}"


def test_search_index_carries_the_ports_and_the_owner(run_cli, project_dir,
                                                      stub_bender_with_dependency):
    """The search palette finds a module by a port name, and marks the owner."""
    assert _gen(run_cli, project_dir) == 0
    index = json.loads((project_dir / project.DEFAULT_OUTPUT / "design.json").read_text())
    by_name = {m["name"]: m for m in index["modules"]}
    assert "sum_o" in by_name["demo_adder"]["ports"]
    assert by_name["demo_top"]["owned"] is True
    assert by_name["demo_adder"]["owned"] is False, "demo_adder is in demo_dep"
    assert by_name["demo_bus_if"]["kind"] == "interface"


def test_the_root_package_is_first_in_the_side_bar(run_cli, project_dir,
                                                   stub_bender_with_dependency):
    assert _gen(run_cli, project_dir) == 0
    html = (project_dir / project.DEFAULT_OUTPUT / "index.html").read_text()
    order = [g for g in re.findall(r'nav-group[^>]*data-pkg="([^"]+)"', html)
             if g != "(documentation)"]
    assert order[0] == "demo_ip", f"the root package must come first, found {order}"
    assert "demo_dep" in order


# -- the written documentation in the site ---------------------------------


def test_the_written_pages_are_in_the_site(run_cli, project_dir, stub_bender):
    assert _gen(run_cli, project_dir) == 0
    out = project_dir / project.DEFAULT_OUTPUT
    assert (out / "doc-readme.html").is_file()
    assert (out / "doc-demo_adder.html").is_file()
    assert (out / "assets" / "docmedia" / "doc" / "adder.png").is_file()


def test_a_module_page_links_to_its_written_page(run_cli, project_dir, stub_bender):
    """`doc/demo_adder.md` documents `demo_adder`, so the two pages join."""
    assert _gen(run_cli, project_dir) == 0
    out = project_dir / project.DEFAULT_OUTPUT
    assert 'href="doc-demo_adder.html"' in (out / "module-demo_adder.html").read_text()
    assert 'href="module-demo_adder.html"' in (out / "doc-demo_adder.html").read_text()
    assert "pill-doc" not in (out / "module-demo_top.html").read_text()


def test_the_written_pages_are_in_the_side_bar_and_the_search(run_cli, project_dir,
                                                              stub_bender):
    assert _gen(run_cli, project_dir) == 0
    out = project_dir / project.DEFAULT_OUTPUT
    assert "nav-docs" in (out / "index.html").read_text()
    index = json.loads((out / "design.json").read_text())
    titles = {d["name"] for d in index["docs"]}
    assert {"Demo IP", "The registered adder"} <= titles


def test_the_file_graph_is_in_the_site(run_cli, project_dir, stub_bender):
    assert _gen(run_cli, project_dir) == 0
    out = project_dir / project.DEFAULT_OUTPUT
    page = (out / "files.html").read_text()
    assert "rtl/demo_top.sv" in page
    assert "rtl/demo_adder.sv" in page
    assert 'href="module-demo_adder.html"' in page
    assert 'href="files.html"' in (out / "index.html").read_text()


def test_each_file_gets_a_page_with_its_code(run_cli, project_dir, stub_bender):
    assert _gen(run_cli, project_dir) == 0
    out = project_dir / project.DEFAULT_OUTPUT
    page = out / "src-rtl-demo_adder-sv.html"
    assert page.is_file()
    text = page.read_text()
    assert "endmodule" in text, "the code must be in the page"
    assert 'id="L-1"' in text
    assert 'href="module-demo_adder.html"' in text
    # The files page and the search index give the file.
    assert 'href="src-rtl-demo_adder-sv.html"' in (out / "files.html").read_text()
    index = json.loads((out / "design.json").read_text())
    assert "rtl/demo_adder.sv" in {f["path"] for f in index["files"]}


def test_the_page_of_a_module_links_to_its_line(run_cli, project_dir, stub_bender):
    assert _gen(run_cli, project_dir) == 0
    out = project_dir / project.DEFAULT_OUTPUT
    model = json.loads((out / "model.json").read_text())
    line = model["modules"]["demo_adder"]["line"]
    assert line > 0
    page = (out / "module-demo_adder.html").read_text()
    assert f'href="src-rtl-demo_adder-sv.html#L-{line}"' in page


def test_the_code_of_a_dependency_stays_out_of_the_site(
        run_cli, project_dir, stub_bender_with_dependency):
    assert _gen(run_cli, project_dir) == 0
    out = project_dir / project.DEFAULT_OUTPUT
    assert (out / "src-rtl-demo_top-sv.html").is_file()
    assert not (out / "src-rtl-demo_adder-sv.html").is_file(), \
        "demo_adder belongs to another package, thus its code has another licence"
    assert (out / "module-demo_adder.html").is_file(), "the module keeps its page"


def test_the_model_gives_the_files_but_not_the_code(run_cli, project_dir, stub_bender):
    assert _gen(run_cli, project_dir) == 0
    out = project_dir / project.DEFAULT_OUTPUT
    model = json.loads((out / "model.json").read_text())
    src = model["sources"]["src-rtl-demo_adder-sv"]
    assert src["rel_path"] == "rtl/demo_adder.sv"
    assert src["lines"] > 0
    assert "html" not in src, "the code would make the model large"


def test_the_settings_can_stop_the_pages_with_the_code(run_cli, project_dir, stub_bender):
    (project_dir / "rtldoc.yml").write_text("sources: false\n")
    assert _gen(run_cli, project_dir) == 0
    out = project_dir / project.DEFAULT_OUTPUT
    assert not list(out.glob("src-*.html"))
    assert (out / "files.html").is_file(), "the file graph stays"
    assert "src-" not in (out / "module-demo_adder.html").read_text()


def test_a_project_without_documentation_still_builds(run_cli, project_dir, stub_bender):
    (project_dir / "README.md").unlink()
    import shutil as _shutil
    _shutil.rmtree(project_dir / "doc")
    assert _gen(run_cli, project_dir) == 0
    out = project_dir / project.DEFAULT_OUTPUT
    assert not list(out.glob("doc-*.html"))
    assert "nav-docs" not in (out / "index.html").read_text()


def test_the_settings_can_stop_the_written_pages(run_cli, project_dir, stub_bender):
    (project_dir / "rtldoc.yml").write_text("docs: false\n")
    assert _gen(run_cli, project_dir) == 0
    out = project_dir / project.DEFAULT_OUTPUT
    assert not list(out.glob("doc-*.html"))
    assert (out / "index.html").is_file()


def test_a_directory_from_the_settings_gives_pages(run_cli, project_dir, stub_bender):
    manual = project_dir / "manual"
    manual.mkdir()
    (manual / "bring_up.md").write_text("# Bring up\n\nHow to start `demo_top`.\n")
    (project_dir / "rtldoc.yml").write_text("docs: [manual]\n")
    assert _gen(run_cli, project_dir) == 0
    page = project_dir / project.DEFAULT_OUTPUT / "doc-manual-bring_up.html"
    assert page.is_file()
    assert 'href="module-demo_top.html"' in page.read_text()


def test_the_comment_above_a_module_becomes_a_page_section(run_cli, project_dir,
                                                           stub_bender):
    """The RTL carries its own documentation. hwpe-stream writes it in
    reStructuredText in a `/** */` block above the module."""
    assert _gen(run_cli, project_dir) == 0
    out = project_dir / project.DEFAULT_OUTPUT
    page = (out / "module-demo_top.html").read_text()
    assert "module-doc" in page
    assert "wires two adders in series" in page
    assert 'href="module-demo_bus_if.html"' in page, "a bold name becomes a link"
    assert "Solderpad" not in page, "the licence block is not the documentation"

    model = json.loads((out / "model.json").read_text())
    assert model["modules"]["demo_top"]["desc"].startswith("The demo_top module wires")
