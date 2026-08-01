"""The design data.

The extractor fills these classes. The renderer reads them. Each class is plain
data, thus the tool can write the full model as JSON for other tools. The rules
that read a name are in `naming`.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field
from typing import Any

from .naming import interface_dir, is_clock, is_reset, name_direction


@dataclass
class Param:
    """A parameter or a localparam of a module."""

    name: str
    type: str = ""
    default: str = ""          # The default expression from the source
    value: str = ""            # The value after the elaboration
    is_localparam: bool = False
    desc: str = ""             # The comment above the declaration


@dataclass
class Port:
    """A port of a module."""

    name: str
    direction: str             # in | out | inout | ref | interface
    type: str = ""             # The type after the elaboration
    width: int | None = None   # The width in bits, if it is known
    is_interface: bool = False
    interface: str = ""        # The interface name, for an interface port
    modport: str = ""          # The modport name, for an interface port
    desc: str = ""             # The comment above the declaration

    @property
    def eff_dir(self) -> str:
        """The direction to group by. An interface port uses its modport."""
        return interface_dir(self.modport) if self.is_interface else self.direction

    @property
    def graph_dir(self) -> str:
        """The direction to draw: `in`, `out`, or `` for a port with no direction.

        The language gives the direction of a logic port. An interface port has
        no direction: the name gives it, and then the modport. An interface port
        with no other data goes in two directions.
        """
        if not self.is_interface:
            if self.direction in ("in", "out"):
                return self.direction
            return name_direction(self.name)
        named = name_direction(self.name)
        if named:
            return named
        modport = interface_dir(self.modport)
        return modport if modport in ("in", "out") else ""


@dataclass
class PortConn:
    """One `.port(net)` connection on an instance."""

    port: str                  # The port name on the child module
    net: str = ""              # The connected net, as written in the source
    is_interface: bool = False
    modport: str = ""          # The modport, for an interface connection


@dataclass
class Instance:
    """A child instance in a module."""

    name: str                  # The instance name
    module: str                # The name of the module it instantiates
    count: int = 1             # More than 1 for an array or a generate loop
    array: bool = False
    params: dict[str, str] = field(default_factory=dict)   # override -> value
    conns: list[PortConn] = field(default_factory=list)
    unknown: bool = False      # The module was not found. It is a black box
    is_interface: bool = False  # An interface instance, not a child module


@dataclass
class Module:
    """A SystemVerilog module or interface."""

    name: str
    kind: str = "module"       # module | interface | package | program
    params: list[Param] = field(default_factory=list)
    ports: list[Port] = field(default_factory=list)
    instances: list[Instance] = field(default_factory=list)
    imports: list[str] = field(default_factory=list)        # Imported packages
    # Where the module comes from
    file: str = ""             # The absolute path of the source file
    rel_file: str = ""         # The path from the project root
    package: str = ""          # The Bender package that owns the file
    line: int = 0
    desc: str = ""             # The first sentence of the comment
    doc_comment: str = ""      # The full comment above the declaration
    elaborated: bool = False   # True if slang resolved the ports and the types
    # Filled after the extraction
    instantiated_by: list[str] = field(default_factory=list)
    doc_page: str = ""         # The written page that documents this module

    @property
    def n_inputs(self) -> int:
        return sum(1 for p in self.ports if p.eff_dir == "in")

    @property
    def n_outputs(self) -> int:
        return sum(1 for p in self.ports if p.eff_dir == "out")

    @property
    def clocks(self) -> list[Port]:
        return [p for p in self.ports if is_clock(p.name)]

    @property
    def resets(self) -> list[Port]:
        return [p for p in self.ports if is_reset(p.name)]

    @property
    def module_instances(self) -> list[Instance]:
        """The child modules. These make the design hierarchy."""
        return [i for i in self.instances if not i.is_interface]

    @property
    def interface_instances(self) -> list[Instance]:
        """The interface instances that the module declares."""
        return [i for i in self.instances if i.is_interface]


@dataclass
class DocPage:
    """One page of written documentation from the repository."""

    slug: str
    title: str
    rel_path: str              # The path from the project root
    html: str = ""
    module: str = ""           # The module that this page documents
    headings: list = field(default_factory=list)
    text: str = ""


@dataclass
class SourceFile:
    """One source file of the project, with its code as HTML."""

    slug: str
    rel_path: str              # The path from the project root
    package: str = ""
    lines: int = 0
    bytes: int = 0
    units: list = field(default_factory=list)   # (name, line) of each unit
    html: str = ""             # The code, with the colours and the line numbers
    highlighted: bool = False  # False if the colours are not available

    @property
    def url(self) -> str:
        return f"{self.slug}.html"


@dataclass
class BenderPackage:
    """A package from Bender.yml and Bender.lock."""

    name: str
    version: str = ""
    source: str = ""           # The git URL or the path
    rev: str = ""              # The revision from Bender.lock
    root: bool = False         # True for the package that the tool documents
    deps: list[str] = field(default_factory=list)


@dataclass
class Design:
    """The full design."""

    root_package: str = ""
    project_root: str = ""
    modules: dict[str, Module] = field(default_factory=dict)
    packages: dict[str, BenderPackage] = field(default_factory=dict)
    tops: list[str] = field(default_factory=list)          # The design tops
    #: Each source file of the root package. A file that declares a package only
    #: has no module, thus the modules do not give the full list.
    source_files: list[str] = field(default_factory=list)
    doc_pages: dict[str, DocPage] = field(default_factory=dict)
    sources: dict[str, SourceFile] = field(default_factory=dict)
    generated_at: str = ""
    tool_version: str = ""
    diagnostics: list[str] = field(default_factory=list)   # Warnings

    def to_json(self) -> dict[str, Any]:
        """The model as JSON. The code of each file is not in it, because the
        HTML of the code is large and the file itself is available."""
        data = dataclasses.asdict(self)
        for src in data.get("sources", {}).values():
            src.pop("html", None)
        return data
