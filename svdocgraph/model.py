"""Design data model for SVDocGraph.

These dataclasses are the single source of truth that the extractor fills in and
the renderer reads from. They are deliberately plain (JSON-serialisable) so the
intermediate model can be dumped, diffed, and consumed by other tools.
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
    """Effective port direction (in/out/inout) for an interface modport."""
    m = (modport or "").lower()
    if m in _OUT_MODPORTS:
        return "out"
    if m in _IN_MODPORTS:
        return "in"
    return "inout"


def reset_polarity(name: str) -> str:
    """Best-effort active-low/high guess from a reset port name."""
    n = name.lower()
    if re.search(r"(rst|reset)_?n", n) or n.endswith("n") or n.endswith("ni") or "_nb" in n:
        return "active-low"
    if re.search(r"(rst|reset)_?b", n) or n.endswith("b"):
        return "active-low"
    return "active-high"


@dataclass
class Param:
    """A module parameter or localparam."""

    name: str
    type: str = ""
    default: str = ""          # as-written default expression, if any
    value: str = ""            # elaborated/resolved value, if available
    is_localparam: bool = False
    desc: str = ""             # doc comment, if any


@dataclass
class Port:
    """A module port."""

    name: str
    direction: str             # in | out | inout | ref | interface
    type: str = ""             # resolved type string, e.g. "logic[2047:0]"
    width: int | None = None   # resolved bit width, if known
    is_interface: bool = False
    interface: str = ""        # interface name, for interface ports
    modport: str = ""          # modport name, for interface ports
    desc: str = ""             # doc comment, if any

    @property
    def eff_dir(self) -> str:
        """Direction used for grouping: interfaces map via their modport."""
        return interface_dir(self.modport) if self.is_interface else self.direction


@dataclass
class PortConn:
    """A single ``.port(net)`` connection on an instance."""

    port: str                  # formal port name on the instantiated module
    net: str = ""              # actual net/expression connected (as written)
    is_interface: bool = False
    modport: str = ""          # modport for interface connections (e.g. source/sink)


@dataclass
class Instance:
    """A child instance inside a module body."""

    name: str                  # instance name, e.g. "i_obuf"
    module: str                # instantiated definition name
    count: int = 1             # >1 for instance arrays / generate-loop copies
    array: bool = False
    params: dict[str, str] = field(default_factory=dict)   # override -> value
    conns: list[PortConn] = field(default_factory=list)
    unknown: bool = False      # module definition was not found (black box)
    is_interface: bool = False  # an SV interface instance (a "stream"/bus), not a submodule


@dataclass
class Module:
    """A SystemVerilog module (or interface) definition."""

    name: str
    kind: str = "module"       # module | interface | package | program
    params: list[Param] = field(default_factory=list)
    ports: list[Port] = field(default_factory=list)
    instances: list[Instance] = field(default_factory=list)
    imports: list[str] = field(default_factory=list)        # imported packages
    # Provenance
    file: str = ""             # absolute source path
    rel_file: str = ""         # path relative to project root, if local
    package: str = ""          # owning bender package
    line: int = 0
    desc: str = ""             # header doc comment
    elaborated: bool = False   # True if ports/types are resolved by slang
    # Derived (filled by graph stage)
    instantiated_by: list[str] = field(default_factory=list)

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
        """Child *module* instances (the design hierarchy)."""
        return [i for i in self.instances if not i.is_interface]

    @property
    def interface_instances(self) -> list[Instance]:
        """Child SV *interface* instances (streams / buses declared in the body)."""
        return [i for i in self.instances if i.is_interface]


@dataclass
class BenderPackage:
    """A dependency from Bender.yml / Bender.lock."""

    name: str
    version: str = ""
    source: str = ""           # git url / path
    rev: str = ""              # locked revision
    root: bool = False         # the top-level package being documented
    deps: list[str] = field(default_factory=list)


@dataclass
class Design:
    """The whole extracted design."""

    root_package: str = ""
    project_root: str = ""
    modules: dict[str, Module] = field(default_factory=dict)
    packages: dict[str, BenderPackage] = field(default_factory=dict)
    tops: list[str] = field(default_factory=list)          # detected design tops
    generated_at: str = ""
    tool_version: str = ""
    diagnostics: list[str] = field(default_factory=list)   # extraction warnings

    def to_json(self) -> dict[str, Any]:
        return dataclasses.asdict(self)
