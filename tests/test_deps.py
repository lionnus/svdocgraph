"""The checks for the necessary programs, and the `doctor` command."""

from __future__ import annotations

from conftest import needs_dot, needs_pyslang

from rtldoc import deps


def test_bender_detected(stub_bender):
    dep = deps.check_bender()
    assert dep.ok
    assert "bender" in dep.detail


def test_bender_missing_is_required_with_a_hint(monkeypatch):
    monkeypatch.setenv("PATH", "")
    dep = deps.check_bender()
    assert not dep.ok and dep.required
    assert "pulp-platform" in dep.hint


def test_broken_bender_is_reported(tmp_path, monkeypatch):
    """A `bender` that is available but does not run is not usable."""
    bad = tmp_path / "bin"
    bad.mkdir()
    exe = bad / "bender"
    exe.write_text("#!/bin/sh\nexit 1\n")
    exe.chmod(0o755)
    monkeypatch.setenv("PATH", str(bad))
    dep = deps.check_bender()
    assert not dep.ok
    assert "failed" in dep.detail


@needs_dot
def test_graphviz_detected():
    dep = deps.check_dot()
    assert dep.ok and "graphviz" in dep.detail.lower()


def test_graphviz_is_optional(monkeypatch):
    monkeypatch.setenv("PATH", "")
    dep = deps.check_dot()
    assert not dep.ok
    assert not dep.required, "the site still builds without graphs"


@needs_pyslang
def test_pyslang_version_is_supported():
    dep = deps.check_pyslang()
    assert dep.ok
    major = int(dep.detail.split(".")[0])
    assert deps.PYSLANG_MIN <= major < deps.PYSLANG_MAX


@needs_dot
@needs_pyslang
def test_doctor_passes_when_everything_is_present(run_cli, stub_bender, capsys):
    assert run_cli("doctor") == 0
    assert "All the necessary programs are available" in capsys.readouterr().out


def test_doctor_fails_and_explains(run_cli, monkeypatch, capsys):
    monkeypatch.setenv("PATH", "")
    assert run_cli("doctor") == 3
    out = capsys.readouterr().out
    assert "bender" in out and "cargo install bender" in out


def test_broken_graphviz_is_reported(tmp_path, monkeypatch):
    bad = tmp_path / "bin"
    bad.mkdir()
    exe = bad / "dot"
    exe.write_text("#!/bin/sh\nexit 1\n")
    exe.chmod(0o755)
    monkeypatch.setenv("PATH", str(bad))
    dep = deps.check_dot()
    assert not dep.ok
    assert "failed" in dep.detail


def test_check_all_covers_every_requirement():
    names = {d.name for d in deps.check_all()}
    assert {"bender", "pyslang", "python"} <= names


def test_an_unusable_pyslang_is_reported(monkeypatch):
    """pyslang is installed, but its version has no driver that the tool can use."""
    monkeypatch.setattr("rtldoc.deps.HAVE_PYSLANG", False)
    dep = deps.check_pyslang()
    assert not dep.ok and dep.required
    assert "Driver" in dep.detail
