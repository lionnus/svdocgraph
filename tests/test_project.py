"""The project rules: the root, the settings, the .gitignore and the output."""

from __future__ import annotations

import subprocess

from svdocgraph import project


def test_find_root_from_subdirectory(project_dir):
    sub = project_dir / "rtl"
    root, found = project.find_project_root(str(sub))
    assert found
    assert root == str(project_dir.resolve())


def test_find_root_without_bender_yml(tmp_path):
    root, found = project.find_project_root(str(tmp_path))
    assert not found
    assert root == str(tmp_path)


def test_config_absent_gives_defaults(project_dir):
    cfg = project.load_config(str(project_dir))
    assert not cfg.found
    assert cfg.output == project.DEFAULT_OUTPUT
    assert cfg.tops == []


def test_config_is_read(project_dir):
    (project_dir / "svdocgraph.yml").write_text(
        "output: docs/design\ntops: [demo_top]\nname: Demo\n"
    )
    cfg = project.load_config(str(project_dir))
    assert cfg.found
    assert cfg.output == "docs/design"
    assert cfg.tops == ["demo_top"]
    assert cfg.name == "Demo"


def test_config_accepts_scalar_top(project_dir):
    (project_dir / "svdocgraph.yml").write_text("top: demo_top\n")
    assert project.load_config(str(project_dir)).tops == ["demo_top"]


def test_config_survives_broken_yaml(project_dir):
    (project_dir / "svdocgraph.yml").write_text("output: [unclosed\n")
    cfg = project.load_config(str(project_dir))
    assert cfg.output == project.DEFAULT_OUTPUT


def test_write_config_does_not_clobber(project_dir):
    first = project.write_config(str(project_dir))
    assert first is not None
    (project_dir / "svdocgraph.yml").write_text("name: mine\n")
    assert project.write_config(str(project_dir)) is None
    assert (project_dir / "svdocgraph.yml").read_text() == "name: mine\n"


def test_gitignore_added_once(project_dir):
    outdir = project_dir / project.DEFAULT_OUTPUT
    outdir.mkdir()
    assert project.ensure_gitignored(str(outdir))
    text = (project_dir / ".gitignore").read_text()
    assert "/.svdocgraph/" in text
    # Already ignored: a second call must not append a duplicate rule.
    assert project.ensure_gitignored(str(outdir)) is None
    assert (project_dir / ".gitignore").read_text() == text


def test_gitignore_appends_cleanly_to_existing_file(project_dir):
    (project_dir / ".gitignore").write_text("*.log")   # no trailing newline
    outdir = project_dir / project.DEFAULT_OUTPUT
    outdir.mkdir()
    project.ensure_gitignored(str(outdir))
    lines = (project_dir / ".gitignore").read_text().splitlines()
    assert lines[0] == "*.log"
    assert "/.svdocgraph/" in lines


def test_gitignore_skipped_outside_a_repo(tmp_path):
    outdir = tmp_path / "nowhere" / ".svdocgraph"
    outdir.mkdir(parents=True)
    assert project.ensure_gitignored(str(outdir)) is None


def test_gitignore_respects_an_existing_rule(project_dir):
    (project_dir / ".gitignore").write_text("/.svdocgraph/\n")
    subprocess.run(["git", "add", "-A"], cwd=project_dir, check=False,
                   capture_output=True)
    outdir = project_dir / project.DEFAULT_OUTPUT
    outdir.mkdir()
    assert project.ensure_gitignored(str(outdir)) is None


def test_ownership_of_output_directory(tmp_path):
    missing = tmp_path / "gone"
    assert project.is_ours(str(missing))          # nothing there yet

    empty = tmp_path / "empty"
    empty.mkdir()
    assert project.is_ours(str(empty))            # empty is fair game

    foreign = tmp_path / "docs"
    foreign.mkdir()
    (foreign / "README.md").write_text("hand written")
    assert not project.is_ours(str(foreign))      # someone else's files

    project.write_build_info(str(foreign), version="0.1.0")
    assert project.is_ours(str(foreign))          # marked as a previous build
    assert project.read_build_info(str(foreign))["tool"] == "svdocgraph"


def test_read_build_info_tolerates_garbage(tmp_path):
    tmp_path.joinpath(project.BUILD_INFO).write_text("not json")
    assert project.read_build_info(str(tmp_path)) is None


def test_config_that_is_not_a_mapping_is_ignored(project_dir):
    (project_dir / "svdocgraph.yml").write_text("- just\n- a list\n")
    assert project.load_config(str(project_dir)).output == project.DEFAULT_OUTPUT


def test_gitignore_is_skipped_for_output_outside_the_repository(project_dir, tmp_path):
    outside = tmp_path / "elsewhere" / "site"
    outside.mkdir(parents=True)
    assert project.ensure_gitignored(str(outside)) is None


def test_gitignore_handles_a_missing_git_binary(project_dir, monkeypatch):
    monkeypatch.setenv("PATH", "")
    outdir = project_dir / project.DEFAULT_OUTPUT
    outdir.mkdir()
    assert project.ensure_gitignored(str(outdir)) is None, "no git means nothing to do"


def test_index_url_points_at_the_entry_page(tmp_path):
    url = project.index_url(str(tmp_path))
    assert url.startswith("file://")
    assert url.endswith("index.html")


def test_the_settings_give_more_documentation_directories(project_dir):
    (project_dir / "svdocgraph.yml").write_text("docs: [manual, spec]\n")
    cfg = project.load_config(str(project_dir))
    assert cfg.doc_dirs == ["manual", "spec"]
    assert cfg.docs_enabled


def test_the_settings_can_stop_the_documentation(project_dir):
    (project_dir / "svdocgraph.yml").write_text("docs: false\n")
    cfg = project.load_config(str(project_dir))
    assert not cfg.docs_enabled
    assert cfg.doc_dirs == []


def test_the_settings_can_stop_the_code(project_dir):
    (project_dir / "svdocgraph.yml").write_text("sources: false\n")
    cfg = project.load_config(str(project_dir))
    assert not cfg.sources_enabled
    assert cfg.docs_enabled, "the two settings are separate"
