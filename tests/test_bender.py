"""The bender layer: the data that it reads, and the messages on a failure."""

from __future__ import annotations

import json

from svdocgraph import bender


def test_root_package_name_is_read(project_dir):
    assert bender._read_root_name(str(project_dir)) == "demo_ip"


def test_root_package_name_survives_a_broken_manifest(tmp_path):
    (tmp_path / "Bender.yml").write_text("package: [not, a, mapping\n")
    assert bender._read_root_name(str(tmp_path)) == ""


def test_missing_manifest_gives_an_empty_name(tmp_path):
    assert bender._read_root_name(str(tmp_path)) == ""


def test_lockfile_supplies_versions_and_provenance(tmp_path):
    (tmp_path / "Bender.lock").write_text(json.dumps({
        "packages": {
            "common_cells": {
                "revision": "abc123",
                "version": "1.40.0",
                "source": {"Git": "https://github.com/pulp-platform/common_cells.git"},
                "dependencies": ["tech_cells_generic"],
            },
        },
    }))
    packages = {}
    bender._parse_lock(str(tmp_path), packages)
    pkg = packages["common_cells"]
    assert pkg.version == "1.40.0"
    assert pkg.rev == "abc123"
    assert pkg.source.endswith("common_cells.git")
    assert pkg.deps == ["tech_cells_generic"]


def test_missing_lockfile_is_not_an_error(tmp_path):
    packages = {}
    bender._parse_lock(str(tmp_path), packages)
    assert packages == {}


def test_nested_source_groups_are_flattened(tmp_path):
    """`bender sources` puts the groups in each other. Each file needs a package."""
    a = tmp_path / "a.sv"
    b = tmp_path / "b.sv"
    a.touch()
    b.touch()
    info = bender.BenderInfo(root_package="root")
    bender._flatten_sources(
        {"package": "root", "files": [
            str(a),
            {"package": "dep", "files": [str(b)]},
        ]},
        "root", info,
    )
    assert info.file_to_package[str(a.resolve())] == "root"
    assert info.file_to_package[str(b.resolve())] == "dep"
    assert info.root_files == [str(a)], "only root files feed the top list"


def test_error_text_keeps_the_diagnosis_and_drops_the_noise():
    raw = (
        "\x1b[32;1m     Cloning\x1b[m common_cells (https://github.com/x/y.git)\n"
        "\x1b[32;1m    Checkout\x1b[m fpnew (https://github.com/x/z.git)\n"
        "\x1b[31;1merror:\x1b[m Requirement `^0.2.11` conflicts.\n"
        "- package `riscv` requires `^0.1.1`\n"
    )
    out = bender._clean_error(raw)
    assert out.startswith("error: Requirement")
    assert "Cloning" not in out
    assert "\x1b" not in out


def test_error_text_falls_back_to_the_last_lines():
    out = bender._clean_error("something went wrong\nno error prefix here\n")
    assert "no error prefix here" in out


def test_collect_reports_a_failing_bender(project_dir, tmp_path, monkeypatch):
    bindir = tmp_path / "bin"
    bindir.mkdir()
    exe = bindir / "bender"
    exe.write_text("#!/bin/sh\necho 'error: broken' >&2\nexit 1\n")
    exe.chmod(0o755)
    monkeypatch.setenv("PATH", str(bindir))
    info = bender.collect(str(project_dir))
    assert "error: broken" in info.failure
    assert info.flist_plus == ""


def test_collect_without_bender_is_not_fatal(project_dir, monkeypatch):
    monkeypatch.setenv("PATH", "")
    info = bender.collect(str(project_dir))
    assert not info.failure, "a missing bender is caught earlier, by the preflight"
    assert info.diagnostics


def test_collect_reads_the_source_set(project_dir, stub_bender):
    info = bender.collect(str(project_dir))
    assert info.root_package == "demo_ip"
    assert info.flist_plus.count(".sv") == 5
    assert len(info.root_files) == 5
    assert info.packages["demo_ip"].root is True


def test_command_file_is_written_for_slang(project_dir, stub_bender, tmp_path):
    info = bender.collect(str(project_dir))
    path = bender.write_command_file(info, str(tmp_path / "sources.f"))
    assert path
    written = open(path).read()
    assert written.count(".sv") == 5
    assert all(ln.startswith('"') for ln in written.splitlines())


def test_no_command_file_without_a_source_list(tmp_path):
    assert bender.write_command_file(bender.BenderInfo(), str(tmp_path / "x.f")) is None


def _fake_bender(tmp_path, monkeypatch, sources_body: str):
    """A bender that gives a file list, and that behaves as given for `sources`."""
    bindir = tmp_path / "bin"
    bindir.mkdir(exist_ok=True)
    exe = bindir / "bender"
    exe.write_text(
        "#!/bin/sh\n"
        '[ "$1 $2" = "script flist-plus" ] && { echo "/tmp/x.sv"; exit 0; }\n'
        f'[ "$1 $2" = "sources -f" ] && {{ {sources_body} }}\n'
        "exit 1\n"
    )
    exe.chmod(0o755)
    monkeypatch.setenv("PATH", str(bindir))


def test_a_failing_sources_command_only_removes_the_package_data(project_dir, tmp_path,
                                                                 monkeypatch):
    _fake_bender(tmp_path, monkeypatch, "echo 'error: no target' >&2; exit 1;")
    info = bender.collect(str(project_dir))
    assert not info.failure, "the file list is available, so the run continues"
    assert any("no package data" in d for d in info.diagnostics)


def test_unreadable_sources_json_is_reported(project_dir, tmp_path, monkeypatch):
    _fake_bender(tmp_path, monkeypatch, "echo 'not json'; exit 0;")
    info = bender.collect(str(project_dir))
    assert not info.failure
    assert any("JSON" in d for d in info.diagnostics)


def test_command_file_entries_have_quotation_marks(tmp_path):
    """slang divides a command file at each space. Thus a path with a space in it
    needs quotation marks."""
    info = bender.BenderInfo(flist_plus=(
        "+incdir+/my design/include\n"
        "\n"
        "/my design/rtl/a.sv\n"
    ))
    path = bender.write_command_file(info, str(tmp_path / "sources.f"))
    assert open(path).read().splitlines() == [
        '"+incdir+/my design/include"',
        '"/my design/rtl/a.sv"',
    ]
