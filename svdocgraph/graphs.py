"""Makes the graphs.

Each function gives Graphviz DOT for one view of the design: the contents of one
module, the design hierarchy, the source files and the Bender packages. A node
contains a link, thus the reader can move through the design. `dot` holds the
colours, the DOT syntax and the Graphviz process.
"""

from __future__ import annotations

import html
import os
import re

from .dot import (
    C_CLUSTER,
    C_CLUSTER_LINE,
    C_DEP,
    C_DEP_TXT,
    C_IFACE,
    C_IN,
    C_IO,
    C_NET,
    C_NET_TXT,
    C_OUT,
    C_OWNED,
    C_TOP,
    FONT,
    FONT_MONO,
    NET_BOX,
    PIN_CDS,
    PIN_HEX,
    edge,
    header,
)
from .model import Design
from .naming import is_clock, is_reset


def _mod_node(design: Design, name: str, *, focus: bool = False) -> str:
    mod = design.modules.get(name)
    owned = mod is not None and mod.package == design.root_package
    is_top = name in design.tops
    label = html.escape(name)
    a = [f'label="{label}"', f'href="module-{name}.html"', 'target="_top"',
         f'tooltip="{label}"']
    if mod is None:
        a += [f'fillcolor="{C_DEP}"', f'fontcolor="{C_DEP_TXT}"', 'style="filled,dashed"',
              'penwidth=1', 'color="#cbd5e1"']
    elif is_top or focus:
        a += [f'fillcolor="{C_TOP if is_top else C_OWNED}"', 'fontcolor="white"']
    elif owned:
        a += [f'fillcolor="{C_OWNED}"', 'fontcolor="white"']
    else:
        a += [f'fillcolor="{C_DEP}"', f'fontcolor="{C_DEP_TXT}"']
    return "[" + ", ".join(a) + "]"


def _link(design: Design, unit: str) -> str:
    """The DOT attributes that make a node open the page of *unit*."""
    if not unit or unit not in design.modules:
        return ""
    return f'href="module-{unit}.html", target="_top", tooltip="{html.escape(unit)}", '


# --- internal netlist -------------------------------------------------------

_IDENT = re.compile(r"[A-Za-z_]\w*")


def _net_base(expr: str) -> str:
    """Reduce a connection expression to a groupable net name, or '' to skip."""
    e = (expr or "").strip().lstrip("(").strip()
    if not e or e[0] in "'\"{0123456789":   # constants / concats / literals
        return ""
    m = _IDENT.match(e)
    return m.group(0) if m else ""


_DRIVER_MODPORTS = {"source", "initiator", "master", "mst", "out", "producer", "manager"}
_LOAD_MODPORTS = {"sink", "subordinate", "slave", "slv", "in", "consumer", "target"}


def _role(child, port: str) -> str:
    """driver / load / both for a child instance's port (by its declared dir)."""
    if child is None:
        return "both"
    for p in child.ports:
        if p.name == port:
            return {"in": "load", "out": "driver"}.get(p.direction, "both")
    return "both"


def _iface_role(modport: str) -> str:
    """driver / load / both for an interface connection (by its modport name)."""
    m = (modport or "").lower()
    if m in _DRIVER_MODPORTS:
        return "driver"
    if m in _LOAD_MODPORTS:
        return "load"
    return "both"


def _conn_role(conn, child) -> str:
    return _iface_role(conn.modport) if conn.is_interface else _role(child, conn.port)


def internal_dot(design: Design, name: str, max_nodes: int = 240) -> str:
    """Schematic of *name*: child instances + the signals wiring them together."""
    mod = design.modules[name]
    insts = mod.module_instances
    if not insts:
        return ""

    # net -> list of (node_id, role)
    nets: dict[str, list[tuple[str, str]]] = {}

    def add(net: str, node: str, role: str) -> None:
        if is_clock(net) or is_reset(net):
            return
        nets.setdefault(net, []).append((node, role))

    inst_ids: dict[str, str] = {}
    for inst in insts:
        nid = f"i__{inst.name}"
        inst_ids[inst.name] = nid
        child = design.modules.get(inst.module)
        for c in inst.conns:
            base = _net_base(c.net)
            if base:
                add(base, nid, _conn_role(c, child))

    # The interfaces that the module declares. The signal that carries an
    # interface links to the declaration of that interface.
    iface_of = {i.name: i.module for i in mod.interface_instances}

    # A boundary port joins the net that has its name. `Port.graph_dir` gives
    # `in`, `out` or `` for a port with no direction.
    boundary: dict[str, dict] = {}
    for p in mod.ports:
        if p.name in nets and not (is_clock(p.name) or is_reset(p.name)):
            d = p.graph_dir
            role = "driver" if d == "in" else ("load" if d == "out" else "both")
            boundary[p.name] = {
                "dir": d,
                "iface": p.interface if p.is_interface else "",
                "is_iface": p.is_interface,
            }
            nets[p.name].append((f"p__{p.name}", role))

    # keep only multi-endpoint nets (actual connections)
    nets = {n: eps for n, eps in nets.items() if len({e[0] for e in eps}) >= 2}

    kept_nets = sorted(nets)[:max_nodes]

    lines = [header("LR")]
    # Boundary ports sit outside the module block, like external pins. A boundary
    # port doubles as the hub for its net, so no separate signal node is drawn.
    for net in kept_nets:
        if net in boundary:
            info = boundary[net]
            rank = "min" if info["dir"] == "in" else "max"
            if info["dir"] == "in":
                shape = f"{PIN_CDS}, "
            elif info["dir"] == "out":
                shape = f"{PIN_CDS}, orientation=180, "
            else:
                # A hexagon has a point at each end: the signals go both ways.
                shape = f"{PIN_HEX}, "
            fill = (C_IFACE if info["is_iface"]
                    else {"in": C_IN, "out": C_OUT}.get(info["dir"], C_IO))
            lines.append(
                f'  {{ rank={rank}; "p__{net}" [{shape}{_link(design, info["iface"])}'
                f'label="{html.escape(net)}", fillcolor="{fill}", fontcolor="white", '
                "fontsize=10]; }"
            )
    # The module itself is the enclosing block; submodules and signals nest inside.
    lines.append(f'  subgraph "cluster_{name}" {{')
    lines.append(
        f'    label="{html.escape(name)}"; labeljust=l; fontname="{FONT}"; '
        f'fontsize=11; fontcolor="{C_NET_TXT}"; style=filled; '
        f'fillcolor="{C_CLUSTER}"; color="{C_CLUSTER_LINE}"; margin=14;'
    )
    for inst in insts[:max_nodes]:
        lbl = html.escape(inst.name)
        sub = html.escape(inst.module) + (f" x{inst.count}" if inst.count > 1 else "")
        href = "" if inst.unknown else f'href="module-{inst.module}.html", target="_top", '
        owned = (m := design.modules.get(inst.module)) is not None and m.package == design.root_package
        fill = C_OWNED if owned else C_DEP
        txt = "white" if owned else C_DEP_TXT
        lines.append(
            f'    "{inst_ids[inst.name]}" [{href}'
            f'label=<<b>{lbl}</b><br/><font point-size="8">{sub}</font>>, '
            f'fillcolor="{fill}", fontcolor="{txt}"];'
        )
    for net in kept_nets:
        if net not in boundary:
            iface = iface_of.get(net, "")
            fill = C_IFACE if iface else C_NET
            txt = "white" if iface else C_NET_TXT
            lines.append(
                f'    "n__{net}" [{NET_BOX}, {_link(design, iface)}'
                f'label="{html.escape(net)}", fillcolor="{fill}", fontcolor="{txt}", '
                f'fontname="{FONT_MONO}", fontsize=9];'
            )
    lines.append("  }")
    # Wiring: drivers point into the signal (or boundary pin), signals point out
    # to their loads.
    for net in kept_nets:
        hub = f"p__{net}" if net in boundary else f"n__{net}"
        for node, role in {(n, r) for n, r in nets[net] if not n.startswith("p__")}:
            if role == "driver":
                lines.append(edge(node, hub))
            elif role == "load":
                lines.append(edge(hub, node))
            else:
                lines.append(edge(hub, node, directed=False))
    lines.append("}")
    return "\n".join(lines)


# --- global hierarchy & packages -------------------------------------------

def hierarchy_dot(design: Design, max_nodes: int = 140) -> str:
    roots = design.tops or [
        n for n, m in design.modules.items() if m.package == design.root_package
    ]
    lines = [header("LR")]
    seen: set[str] = set()
    edges: set[tuple[str, str]] = set()
    queue = list(roots)
    while queue and len(seen) < max_nodes:
        name = queue.pop(0)
        if name in seen:
            continue
        seen.add(name)
        mod = design.modules.get(name)
        if mod is None:
            continue
        for inst in mod.module_instances:
            edges.add((name, inst.module))
            if inst.module not in seen:
                queue.append(inst.module)
    for name in sorted(seen):
        lines.append(f'  "{name}" {_mod_node(design, name)};')
    for a, b in sorted(edges):
        lines.append(edge(a, b))
    lines.append("}")
    return "\n".join(lines)


def package_dot(design: Design) -> str:
    lines = [header("LR")]
    for name, pkg in sorted(design.packages.items()):
        fill = C_OWNED if pkg.root else C_DEP
        txt = "white" if pkg.root else C_DEP_TXT
        lines.append(
            f'  "{name}" [label="{html.escape(name)}", href="package-{name}.html", '
            f'target="_top", fillcolor="{fill}", fontcolor="{txt}"];'
        )
    for name, pkg in sorted(design.packages.items()):
        for dep in pkg.deps:
            if dep in design.packages:
                lines.append(edge(name, dep))
    lines.append("}")
    return "\n".join(lines)


def file_dot(design: Design, max_nodes: int = 120) -> str:
    """A graph of the source files of the root package and their connections.

    An edge goes from a file to each file that it needs: the file of a module
    that it instantiates, and the file of a package that it imports. This gives
    the compile sequence and the structure of the repository.
    """
    file_of: dict[str, str] = {}
    for name, mod in design.modules.items():
        if mod.rel_file:
            file_of[name] = mod.rel_file

    owned = {
        mod.rel_file for mod in design.modules.values()
        if mod.rel_file and mod.package == design.root_package
    }
    if not owned:
        return ""

    edges: set = set()
    labels: dict = {}
    for mod in design.modules.values():
        src = mod.rel_file
        if src not in owned:
            continue
        for inst in mod.module_instances:
            dst = file_of.get(inst.module)
            if dst and dst != src:
                edges.add((src, dst))
        for inst in mod.interface_instances:
            dst = file_of.get(inst.module)
            if dst and dst != src:
                edges.add((src, dst))
    for f in owned:
        labels[f] = os.path.basename(f)
    for _, dst in edges:
        labels.setdefault(dst, os.path.basename(dst))

    keep = sorted(labels)[:max_nodes]
    kept = set(keep)

    # The node of a file opens the code of that file.
    urls = {s.rel_path: s.url for s in design.sources.values()}

    lines = [header("LR")]
    for f in keep:
        is_owned = f in owned
        fill = C_OWNED if is_owned else C_DEP
        txt = "white" if is_owned else C_DEP_TXT
        href = f'href="{urls[f]}", target="_top", ' if f in urls else ""
        lines.append(
            f'  "{f}" [{href}label="{html.escape(labels[f])}", '
            f'tooltip="{html.escape(f)}", shape=box, '
            f'fillcolor="{fill}", fontcolor="{txt}", fontname="{FONT_MONO}", fontsize=10];'
        )
    for a, b in sorted(edges):
        if a in kept and b in kept:
            lines.append(edge(a, b))
    lines.append("}")
    return "\n".join(lines)
