"""The command that a CI job runs to examine a generated directory."""

from __future__ import annotations

import json

import pytest
from conftest import needs_pyslang

from rtldoc import check, project

pytestmark = [needs_pyslang]


@pytest.fixture
def site(run_cli, project_dir, stub_bender):
    assert run_cli("gen", cwd=project_dir) == 0
    return project_dir / project.DEFAULT_OUTPUT


def test_a_complete_site_gives_no_problem(site):
    assert check.check(str(site), min_modules=3, min_docs=1, min_sources=3,
                       want_module="demo_top", want_interface="demo_bus_if",
                       max_diagnostics=0) == []


def test_the_summary_counts_each_kind_of_page(site):
    text = check.summary(str(site))
    assert "units" in text and "source pages" in text


def test_a_missing_file_is_a_problem(site):
    (site / "hierarchy.html").unlink()
    assert any("hierarchy.html" in p for p in check.check(str(site)))


def test_the_limits_report_what_is_too_small(site):
    problems = check.check(str(site), min_modules=99, min_interfaces=99,
                           min_docs=99, min_sources=99)
    assert len(problems) == 4
    assert all("expected >=" in p for p in problems)


def test_a_unit_that_must_be_there(site):
    problems = check.check(str(site), want_module="no_such_module",
                           want_interface="demo_top")
    assert "module no_such_module not extracted" in problems
    assert any("demo_top classified as module" in p for p in problems)


def test_a_diagnostic_above_the_limit_is_a_problem(site):
    model = json.loads((site / "model.json").read_text())
    model["diagnostics"] = ["something went wrong"]
    (site / "model.json").write_text(json.dumps(model))
    assert any("1 diagnostics" in p for p in check.check(str(site),
                                                         max_diagnostics=0))


def test_a_module_without_a_page_is_a_problem(site):
    (site / "module-demo_top.html").unlink()
    assert "no page for module demo_top" in check.check(str(site))


def test_a_broken_search_index_is_a_problem(site):
    (site / "assets" / "search.js").write_text("window.RTLDOC_DATA={oops};\n")
    assert any("not valid JSON" in p for p in check.check(str(site)))


def test_an_index_that_does_not_match_the_model_is_a_problem(site):
    model = json.loads((site / "model.json").read_text())
    model["modules"].pop(next(iter(model["modules"])))
    (site / "model.json").write_text(json.dumps(model))
    assert any("does not match" in p for p in check.check(str(site)))


def test_an_index_without_the_search_data_is_a_problem(site):
    (site / "assets" / "search.js").write_text("// nothing here\n")
    assert "assets/search.js has no search index" in check.check(str(site))


def test_the_graphs_are_a_condition(site):
    (site / "hierarchy.html").write_text("<html>no graph</html>")
    (site / "files.html").write_text("<html>no graph</html>")
    problems = check.check(str(site), require_graphs=True, require_file_graph=True)
    assert any("hierarchy.html has no inline SVG" in p for p in problems)
    assert any("files.html has no inline SVG" in p for p in problems)


def test_a_site_without_the_file_graph_is_a_problem(site):
    (site / "files.html").unlink()
    assert "no files.html" in check.check(str(site), require_file_graph=True)


def test_a_page_without_code_is_a_problem(site):
    page = next(iter(sorted(site.glob("src-*.html"))))
    page.write_text("<html>no code</html>")
    assert any("shows no code" in p for p in check.check(str(site), min_sources=1))


def test_a_module_without_ports_or_a_line_is_a_problem(site):
    model = json.loads((site / "model.json").read_text())
    for mod in model["modules"].values():
        mod["ports"] = []
        mod["line"] = 0
    (site / "model.json").write_text(json.dumps(model))
    problems = check.check(str(site), min_sources=1)
    assert any("units have ports" in p for p in problems)
    assert "no module has a line number" in problems


def test_an_empty_directory_gives_problems(tmp_path):
    problems = check.check(str(tmp_path))
    assert len(problems) == len(check.REQUIRED)


def test_a_directory_that_is_not_there_gives_problems(tmp_path):
    problems = check.check(str(tmp_path / "gone"), min_docs=1, min_sources=1)
    assert len(problems) == len(check.REQUIRED) + 2
    assert check.summary(str(tmp_path / "gone")).startswith("0 units")


def test_the_command_gives_the_exit_code(run_cli, site, capsys):
    assert run_cli("check", str(site), "--min-modules", "3") == 0
    assert run_cli("check", str(site), "--min-modules", "99") == 1
    assert "expected >= 99" in capsys.readouterr().err
