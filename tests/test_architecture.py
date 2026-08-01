"""The rules of the package layout.

Each module has one subject. A module imports from a lower layer only.

Without a test, that rule goes away with the next change. An import is one line,
and a cycle gives no error until the package is large.
"""

from __future__ import annotations

import ast
import pathlib

import pytest

PACKAGE = pathlib.Path(__file__).parent.parent / "svdocgraph"

#: The layers, from the bottom. A module imports from its own layer or lower.
LAYERS = [
    ["naming"],
    ["model"],
    ["bender", "deps", "project", "markup"],
    ["comments", "docs", "dot", "extract", "source"],
    ["graphs", "render", "check"],
    ["api"],
    ["cli"],
]

LAYER_OF = {name: i for i, layer in enumerate(LAYERS) for name in layer}

#: A module of the same layer that another module of that layer may import.
SAME_LAYER = {
    ("extract", "comments"),
    ("docs", "markup"),
    ("graphs", "dot"),
    ("render", "graphs"),
    ("render", "docs"),
    ("render", "source"),
    ("render", "markup"),
    ("render", "project"),
}


def module_names() -> list:
    return sorted(p.stem for p in PACKAGE.glob("*.py") if p.stem != "__init__")


def imports_of(name: str) -> list:
    """The modules of this package that *name* imports."""
    tree = ast.parse((PACKAGE / f"{name}.py").read_text())
    found: list = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.level == 1:
            if node.module:
                found.append(node.module)
            else:      # `from . import a, b`
                found += [a.name for a in node.names]
    return [m for m in found if m != "__version__"]


def test_each_module_is_in_a_layer():
    assert set(module_names()) == set(LAYER_OF), (
        "a new module needs a layer in this test"
    )


@pytest.mark.parametrize("name", module_names())
def test_a_module_imports_from_a_lower_layer(name):
    here = LAYER_OF[name]
    for other in imports_of(name):
        assert other in LAYER_OF, f"{name} imports the unknown module {other}"
        there = LAYER_OF[other]
        if there == here:
            assert (name, other) in SAME_LAYER, (
                f"{name} imports {other} of the same layer. Add it to SAME_LAYER "
                "if the two are not a cycle."
            )
        else:
            assert there < here, f"{name} (layer {here}) imports {other} (layer {there})"


def test_the_lowest_layer_needs_nothing():
    for name in LAYERS[0]:
        assert [m for m in imports_of(name) if m not in LAYERS[0]] == []


def test_no_module_imports_the_package_itself():
    """`from svdocgraph import x` inside the package makes a cycle."""
    for name in module_names():
        text = (PACKAGE / f"{name}.py").read_text()
        assert "from svdocgraph" not in text, name
        assert "import svdocgraph" not in text, name


def test_each_module_says_what_it_is_for():
    for name in module_names():
        tree = ast.parse((PACKAGE / f"{name}.py").read_text())
        doc = ast.get_docstring(tree)
        assert doc, f"{name} needs a docstring that says what it is for"


def test_the_public_api_is_available():
    import svdocgraph

    for name in svdocgraph.__all__:
        assert getattr(svdocgraph, name) is not None
    with pytest.raises(AttributeError):
        _ = svdocgraph.not_a_real_name
