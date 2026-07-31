"""The design data.

The extractor fills these classes. The renderer reads them. Each class is plain
data, thus the tool can write the full model as JSON for other tools.
"""

from __future__ import annotations

import dataclasses
import re
from dataclasses import dataclass, field
from typing import Any


def _is_clock(name: str) -> bool:
    n = name.lower()
    return "clk" in n or "clock" in n


def _is_reset(name: str) -> bool:
    n = name.lower()
    return "rst" in n or "reset" in n


_OUT_MODPORTS = {"source", "initiator", "master", "mst", "out", "producer", "manager"}
_IN_MODPORTS = {"sink", "subordinate", "slave", "slv", "in", "consumer", "target"}


def interface_dir(modport: str) -> str:
    """The direction of an interface port, from the name of its modport."""
    m = (modport or "").lower()
    if m in _OUT_MODPORTS:
        return "out"
    if m in _IN_MODPORTS:
        return "in"
    return "inout"


def reset_polarity(name: str) -> str:
    """The polarity of a reset port, from its name."""
    n = name.lower()
    if re.search(r"(rst|reset)_?n", n) or n.endswith("n") or n.endswith("ni") or "_nb" in n:
        return "active-low"
    if re.search(r"(rst|reset)_?b", n) or n.endswith("b"):
        return "active-low"
    return "active-high"


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
    desc: str = ""             # The comment above the declaration
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
        return [p for p in self.ports if _is_clock(p.name)]

    @property
    def resets(self) -> list[Port]:
        return [p for p in self.ports if _is_reset(p.name)]

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
    doc_pages: dict[str, DocPage] = field(default_factory=dict)
    generated_at: str = ""
    tool_version: str = ""
    diagnostics: list[str] = field(default_factory=list)   # Warnings

    def to_json(self) -> dict[str, Any]:
        return dataclasses.asdict(self)
