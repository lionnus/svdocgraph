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


# -- the documentation comment above a module ------------------------------


def _tree(text: str):
    from pyslang import syntax
    t = syntax.SyntaxTree.fromText(text)
    return t[0] if isinstance(t, tuple) else t


def test_a_block_comment_above_a_module_is_the_documentation():
    trees = [_tree("/**\n * The **adder** adds.\n * It needs one clock.\n */\n"
                   "module m ();\nendmodule\n")]
    assert extract.doc_comments(trees)["m"] == "The **adder** adds.\nIt needs one clock."


def test_a_line_comment_above_a_module_is_the_documentation():
    trees = [_tree("// The adder adds.\n// It needs one clock.\nmodule m ();\nendmodule\n")]
    assert extract.doc_comments(trees)["m"] == "The adder adds.\nIt needs one clock."


def test_the_licence_block_is_not_the_documentation():
    """A PULP file starts with the licence, then the documentation."""
    trees = [_tree(
        "/*\n * m.sv\n * Copyright (C) 2018 ETH Zurich\n"
        " * Licensed under the Solderpad Hardware License\n */\n\n"
        "/**\n * The real description.\n */\n"
        "module m ();\nendmodule\n"
    )]
    assert extract.doc_comments(trees)["m"] == "The real description."


def test_a_comment_before_an_import_still_belongs_to_the_module():
    """slang attaches a comment to the token after it. In hwpe-stream an import
    is between the comment and the module."""
    trees = [_tree(
        "/**\n * The description.\n */\n"
        "import my_pkg::*;\n"
        "module m ();\nendmodule\n"
    )]
    assert extract.doc_comments(trees)["m"] == "The description."


def test_each_module_of_a_file_keeps_its_own_comment():
    trees = [_tree(
        "/** First module. */\nmodule a ();\nendmodule\n"
        "/** Second module. */\nmodule b ();\nendmodule\n"
    )]
    got = extract.doc_comments(trees)
    assert got["a"] == "First module."
    assert got["b"] == "Second module."


def test_a_comment_before_an_include_still_belongs_to_the_module(tmp_path):
    """The HCI modules put `include "hci_helpers.svh"` after the description."""
    from pyslang import syntax
    (tmp_path / "defs.svh").write_text("`define X 1\n")
    (tmp_path / "m.sv").write_text(
        '/**\n * The real description.\n */\n`include "defs.svh"\n'
        "module m ();\nendmodule\n"
    )
    tree = syntax.SyntaxTree.fromFile(str(tmp_path / "m.sv"))
    trees = [tree[0] if isinstance(tree, tuple) else tree]
    assert extract.doc_comments(trees) == {"m": "The real description."}


def test_the_authors_are_not_the_documentation():
    trees = [_tree(
        "/*\n * Authors:  Anna Example <anna@example.com>\n"
        " *           Bo Example <bo@example.com>\n */\n"
        "module m ();\nendmodule\n"
    )]
    assert extract.doc_comments(trees) == {}


def test_a_comment_keeps_the_description_that_follows_the_author():
    trees = [_tree(
        "/*\n * Author: Anna Example\n * Description: A counter that counts.\n */\n"
        "module m ();\nendmodule\n"
    )]
    assert extract.doc_comments(trees)["m"] == "Description: A counter that counts."


def test_a_comment_from_an_include_file_is_not_the_documentation(tmp_path):
    """The HCI and common_cells headers end with `endif /* `ifndef ... */`.

    slang puts the text of the header before the module. Without the file of
    each comment, that comment becomes the description of the module.
    """
    from pyslang import syntax
    (tmp_path / "defs.svh").write_text(
        "`ifndef X\n`define X 1\n`endif /* `ifndef X */\n"
    )
    (tmp_path / "m.sv").write_text(
        '/**\n * The real description.\n */\n`include "defs.svh"\n'
        "module m ();\nendmodule\n"
    )
    tree = syntax.SyntaxTree.fromFile(str(tmp_path / "m.sv"))
    trees = [tree[0] if isinstance(tree, tuple) else tree]
    assert extract.doc_comments(trees) == {"m": "The real description."}


def test_an_unknown_file_does_not_stop_the_comments():
    """slang gives no location for some trivia. The comment stays."""
    class Location:
        pass

    class Manager:
        def getFileName(self, loc):
            raise RuntimeError("no such buffer")

    class Trivia:
        kind = "TriviaKind.Directive"

        def getExplicitLocation(self):
            return Location()

        def syntax(self):
            raise RuntimeError("no syntax")

    assert extract._file_of(Manager(), Location()) is None
    assert extract._trivia_files([Trivia()], Manager()) == [None]
    assert extract._directive_trivia(Trivia(), Manager()) == ([], [])


def test_a_module_without_a_comment_gets_none():
    assert extract.doc_comments([_tree("module m ();\nendmodule\n")]) == {}


def test_the_summary_is_the_first_sentence():
    text = "The source streamer performs loads. It also does other things.\nMore text."
    assert extract._summary(text) == "The source streamer performs loads."


def test_the_summary_leaves_out_a_directive():
    text = ".. figure:: img/a.png\n\nThe module moves the data. Then it stops."
    assert extract._summary(text).startswith("The module moves the data.")
