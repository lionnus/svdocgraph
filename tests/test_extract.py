"""The extractor functions that operate without an elaboration."""

from __future__ import annotations

from svdocgraph import extract
from svdocgraph.bender import BenderInfo

RTL = "tests/fixtures/demo/rtl"


def _fixture(name: str) -> str:
    from pathlib import Path
    return str(Path(__file__).parent / "fixtures" / "demo" / "rtl" / name)


def test_declared_units_reports_names_and_kinds():
    units = extract.declared_units([
        _fixture("demo_pkg.sv"), _fixture("demo_bus_if.sv"),
        _fixture("demo_adder.sv"), _fixture("demo_top.sv"),
    ])
    assert units["demo_adder"][0] == "module"
    assert units["demo_bus_if"][0] == "interface"
    assert units["demo_pkg"][0] == "package"
    assert units["demo_top"][1].endswith("demo_top.sv")


def test_declared_units_ignores_unreadable_files():
    assert extract.declared_units(["/nonexistent/nope.sv"]) == {}


def test_header_doc_is_taken_from_the_comment_above_the_declaration():
    doc = extract._header_doc(_fixture("demo_adder.sv"), "demo_adder")
    assert "Registered adder" in doc


def test_header_doc_skips_licence_boilerplate(tmp_path):
    f = tmp_path / "m.sv"
    f.write_text(
        "// Copyright 2026 ETH Zurich\n"
        "// SPDX-License-Identifier: Apache-2.0\n"
        "// A useful description.\n"
        "module m ();\nendmodule\n"
    )
    doc = extract._header_doc(str(f), "m")
    assert doc == "A useful description."


def test_header_doc_is_empty_when_absent(tmp_path):
    f = tmp_path / "m.sv"
    f.write_text("module m ();\nendmodule\n")
    assert extract._header_doc(str(f), "m") == ""
    assert extract._header_doc(str(f), "other") == ""


class _Defn:
    def __init__(self, kind):
        self.definitionKind = kind


class _Kind:
    """Stands in for pyslang's DefinitionKind enum."""

    def __init__(self, name):
        self.name = name

    def __str__(self):
        return f"DefinitionKind.{self.name}"


def test_definition_kind_distinguishes_interfaces():
    assert extract._definition_kind(_Defn(_Kind("Interface"))) == "interface"
    assert extract._definition_kind(_Defn(_Kind("Module"))) == "module"
    assert extract._definition_kind(_Defn(_Kind("Program"))) == "program"


def test_definition_kind_falls_back_to_module():
    assert extract._definition_kind(_Defn(None)) == "module"
    assert extract._definition_kind(None) == "module"
    assert extract._definition_kind(_Defn(_Kind("SomethingNew"))) == "module"


def test_direction_strings_are_normalised():
    assert extract._dir_str("ArgumentDirection.In") == "in"
    assert extract._dir_str("ArgumentDirection.InOut") == "inout"
    assert extract._dir_str("ArgumentDirection.Ref") == "ref"


def test_header_doc_stops_at_a_blank_line(tmp_path):
    f = tmp_path / "m.sv"
    f.write_text("// Not part of the header.\n\n// The description.\nmodule m ();\nendmodule\n")
    assert extract._header_doc(str(f), "m") == "The description."


def test_header_doc_ignores_an_unreadable_file():
    assert extract._header_doc("/nonexistent/m.sv", "m") == ""


def test_extraction_needs_pyslang(monkeypatch):
    monkeypatch.setattr(extract, "HAVE_PYSLANG", False)
    design = extract.extract_design("/tmp", BenderInfo(), "sources.f")
    assert design.modules == {}
    assert "pyslang" in design.diagnostics[0]


def test_extraction_needs_a_command_file():
    design = extract.extract_design("/tmp", BenderInfo(), "")
    assert design.modules == {}
    assert "command file" in design.diagnostics[0]


def test_extraction_reports_a_command_file_slang_refuses(tmp_path):
    """slang stops if the file list gives a file that is not available."""
    cmd = tmp_path / "sources.f"
    cmd.write_text(f"{tmp_path}/does_not_exist.sv\n")
    design = extract.extract_design(str(tmp_path), BenderInfo(), str(cmd))
    assert design.modules == {}
    assert any("slang" in d for d in design.diagnostics)


def test_header_doc_stops_at_a_line_of_code(tmp_path):
    f = tmp_path / "m.sv"
    f.write_text("`define X 1\n// The description.\nmodule m ();\nendmodule\n")
    assert extract._header_doc(str(f), "m") == "The description."


def test_a_long_doc_comment_is_shortened(tmp_path):
    f = tmp_path / "m.sv"
    f.write_text("// " + "word " * 200 + "\nmodule m ();\nendmodule\n")
    assert len(extract._header_doc(str(f), "m")) <= 300
