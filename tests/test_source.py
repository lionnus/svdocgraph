"""The pages that show the code of a source file."""

from __future__ import annotations

import pytest

from svdocgraph import source
from svdocgraph.model import Module

CODE = "module a;\n  // hello\nendmodule\n"


def test_the_slug_is_a_safe_file_name():
    assert source.slug_for("rtl/ctrl/demo_top.sv") == "src-rtl-ctrl-demo_top-sv"
    assert source.slug_for("a b/c+d.sv") == "src-a-b-c-d-sv"
    assert source.slug_for("") == "src-file"


def test_the_code_gets_colours_and_a_line_number_for_each_line():
    html, coloured = source.render_code(CODE, "rtl/a.sv")
    assert coloured
    assert 'id="L-1"' in html and 'id="L-3"' in html
    assert 'href="#L-2"' in html, "each line number must be a link"
    assert "hltable" in html
    assert 'class="k"' in html, "`module` must be a keyword"


def test_a_large_file_keeps_its_page_but_loses_the_colours(monkeypatch):
    monkeypatch.setattr(source, "MAX_HIGHLIGHT_LINES", 3)
    html, coloured = source.render_code("a\n" * 10, "rtl/a.sv")
    assert not coloured
    assert 'id="L-10"' in html and "hltable" in html


def test_the_code_without_colours_cannot_inject_html(monkeypatch):
    monkeypatch.setattr(source, "MAX_HIGHLIGHT_LINES", 0)
    html, coloured = source.render_code("<script>x</script>\n", "rtl/a.sv")
    assert not coloured
    assert "<script>" not in html
    assert "&lt;script&gt;" in html


def test_a_file_that_is_not_verilog_still_gets_a_page():
    html, coloured = source.render_code("x = 1\n", "scripts/a.py")
    assert coloured and 'id="L-1"' in html


def test_each_style_rule_names_its_theme():
    css = source.style_css()
    for line in css.splitlines():
        if line.strip() and not line.strip().startswith("/*"):
            assert line.startswith(('.hl', '[data-theme="dark"] .hl')), line
    assert '[data-theme="dark"] .hl pre' in css, "the dark theme needs its own rules"


def _write(tmp_path, rel, text):
    path = tmp_path / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return str(path)


@pytest.fixture
def project(tmp_path):
    top = _write(tmp_path, "rtl/top.sv", CODE)
    pkg = _write(tmp_path, "rtl/pkg.sv", "package p;\nendpackage\n")
    return tmp_path, top, pkg


def test_collect_reads_each_file_and_names_its_units(project):
    root, top, pkg = project
    mods = {"a": Module(name="a", file=top, package="demo", line=1)}
    out = source.collect(str(root), [top, pkg], mods)
    by_path = {s.rel_path: s for s in out.values()}
    assert set(by_path) == {"rtl/top.sv", "rtl/pkg.sv"}
    assert by_path["rtl/top.sv"].units == [("a", 1)]
    assert by_path["rtl/top.sv"].package == "demo"
    assert by_path["rtl/top.sv"].lines == 3
    # A file that declares a package only has no unit, but it keeps its page.
    assert by_path["rtl/pkg.sv"].units == []


def test_collect_names_the_units_in_the_sequence_of_the_lines(project):
    root, top, _ = project
    mods = {
        "b": Module(name="b", file=top, line=9),
        "a": Module(name="a", file=top, line=2),
    }
    out = source.collect(str(root), [top], mods)
    assert next(iter(out.values())).units == [("a", 2), ("b", 9)]


def test_collect_skips_a_file_outside_the_project(project, tmp_path):
    root, top, _ = project
    other = _write(tmp_path.parent, "elsewhere/dep.sv", CODE)
    out = source.collect(str(root), [top, other], {})
    assert [s.rel_path for s in out.values()] == ["rtl/top.sv"]


def test_collect_skips_a_file_that_is_too_large(project, monkeypatch):
    root, top, pkg = project
    monkeypatch.setattr(source, "MAX_BYTES", 10)
    out = source.collect(str(root), [top, pkg], {})
    assert out == {}


def test_collect_skips_a_file_that_is_not_available(project):
    root, top, _ = project
    out = source.collect(str(root), [top, str(root / "rtl" / "gone.sv")], {})
    assert [s.rel_path for s in out.values()] == ["rtl/top.sv"]


def test_collect_skips_a_file_that_it_cannot_read(project, monkeypatch):
    root, top, _ = project

    def refuse(path):
        raise OSError("no permission")

    monkeypatch.setattr(source.os.path, "getsize", refuse)
    assert source.collect(str(root), [top], {}) == {}


def test_collect_accepts_a_module_without_a_file(project):
    """A module that slang did not elaborate has no file."""
    root, top, _ = project
    out = source.collect(str(root), [top], {"x": Module(name="x")})
    assert next(iter(out.values())).units == []


def test_the_pages_operate_without_pygments(monkeypatch):
    monkeypatch.setattr(source, "HAVE_PYGMENTS", False)
    assert "Pygments" in source.style_css()
    html, coloured = source.render_code(CODE, "rtl/a.sv")
    assert not coloured and "endmodule" in html


def test_two_files_cannot_take_the_same_page(project):
    root, top, _ = project
    other = _write(root, "rtl-top.sv", CODE)   # the same slug as rtl/top.sv
    out = source.collect(str(root), [top, other], {})
    assert len(out) == 2, "each file needs its own page"
    assert len(set(out)) == 2
