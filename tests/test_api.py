"""The library interface. Another program calls these two functions."""

from __future__ import annotations

import pytest
from conftest import needs_pyslang

import svdocgraph
from svdocgraph import api, project

pytestmark = [needs_pyslang]


def test_the_package_gives_the_public_names():
    assert svdocgraph.build_documentation is api.build_documentation
    assert svdocgraph.extract_design is api.extract_design
    assert svdocgraph.Design().modules == {}
    assert svdocgraph.__version__


def test_extract_design_gives_the_model(project_dir, stub_bender):
    design = api.extract_design(str(project_dir))
    assert {"demo_top", "demo_adder"} <= set(design.modules)
    assert design.root_package == "demo_ip"


def test_extract_design_reports_the_progress(project_dir, stub_bender):
    said: list = []
    api.extract_design(str(project_dir), log=said.append)
    assert any("root package" in m for m in said)
    assert any("slang" in m for m in said)


def test_build_documentation_writes_the_site(project_dir, stub_bender, tmp_path):
    out = tmp_path / "public"
    design = api.build_documentation(str(project_dir), str(out))
    assert (out / "index.html").is_file()
    assert (out / "module-demo_top.html").is_file()
    assert design.modules


def test_build_documentation_uses_the_settings(project_dir, stub_bender):
    (project_dir / "svdocgraph.yml").write_text("name: Fancy\noutput: site\n")
    api.build_documentation(str(project_dir))
    assert "Fancy" in (project_dir / "site" / "index.html").read_text()


def test_build_documentation_finds_the_project_root(project_dir, stub_bender):
    deep = project_dir / "rtl"
    api.build_documentation(str(deep))
    assert (project_dir / project.DEFAULT_OUTPUT / "index.html").is_file()


def test_a_project_that_bender_cannot_read_raises(tmp_path, stub_bender, monkeypatch):
    """The stub bender gives exit code 1 outside a project."""
    monkeypatch.setattr("svdocgraph.bender.collect",
                        lambda root: _failed("no such package"))
    with pytest.raises(api.BenderFailed, match="no such package"):
        api.extract_design(str(tmp_path))


def _failed(message: str):
    from svdocgraph.bender import BenderInfo
    return BenderInfo(failure=message)
