"""Documentation for SystemVerilog projects that use Bender.

The command line is `svdocgraph`. This package is also a library:

    from svdocgraph import build_documentation
    build_documentation("path/to/project", "public")

The modules are in layers. A module imports from a lower layer only, thus there
is no cycle. `tests/test_architecture.py` holds the rule.

1. `model` gives the data, `naming` gives the rules that read a name.
2. `bender` reads the project, `deps` finds the necessary programs, `project`
   holds the conventions, `markup` turns text into HTML.
3. `comments` reads the comment above a unit, `extract` elaborates with slang,
   `docs` reads the written pages, `source` makes the code pages, `dot` drives
   Graphviz.
4. `graphs` makes each graph, `render` writes the site, `check` examines it.
5. `cli` gives the commands.
"""

from __future__ import annotations

__version__ = "0.1.0"

__all__ = [
    "Design",
    "Module",
    "Port",
    "__version__",
    "build_documentation",
    "check_site",
    "extract_design",
]


def __getattr__(name: str):
    """Imports on demand. Thus `svdocgraph --version` does not load pyslang."""
    if name in ("Design", "Module", "Port"):
        from . import model
        return getattr(model, name)
    if name in ("build_documentation", "extract_design"):
        from . import api
        return getattr(api, name)
    if name == "check_site":
        from .check import check
        return check
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
