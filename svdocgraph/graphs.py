"""Makes the graphs.

Each function writes Graphviz DOT. Graphviz then calculates the layout and gives
SVG. The nodes contain links, thus the reader can move through the design.

There are three graphs: the contents of one module, the design hierarchy, and the
Bender packages.
"""

from __future__ import annotations

import html
import os
import re
import shutil
import subprocess

from .model import Design, _is_clock, _is_reset

# The colours. Each fill is solid. There are no borders and no round corners.
C_OWNED = "#2563eb"     # Modules of the root package
C_TOP = "#7c3aed"       # Design tops
C_DEP = "#e2e8f0"       # Modules of a dependency, and black boxes
C_DEP_TXT = "#334155"
C_IFACE = "#0d9488"     # Interfaces
C_NET = "#ffffff"       # Signal nodes
C_NET_TXT = "#475569"
C_PORT = "#0f172a"      # Ports of the module
C_CLUSTER = "#f1f5f9"   # Fill of the module boundary
C_CLUSTER_LINE = "#cbd5e1"
EDGE = "#94a3b8"
FONT = "IBM Plex Sans"
FONT_MONO = "IBM Plex Mono"


def have_dot() -> bool:
    return shutil.which("dot") is not None


def render_dot(dot: str) -> str | None:
    if not have_dot():
        return None
    try:
        out = subprocess.run(
            ["dot", "-Tsvg"], input=dot, capture_output=True, text=True, check=True
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None
    svg = out.stdout
    i = svg.find("<svg")
    return svg[i:] if i >= 0 else svg


def _header(rankdir: str = "TB") -> str:
    return (
        "digraph G {\n"
        f"  rankdir={rankdir};\n"
        '  bgcolor="transparent";\n'
        f'  graph [fontname="{FONT}"];\n'
        f'  node [shape=box, style=filled, penwidth=0, fontname="{FONT}", '
        'fontsize=11, margin="0.16,0.07"];\n'
        f'  edge [color="{EDGE}", penwidth=1.0, arrowsize=0.6, fontname="{FONT}", '
        f'fontsize=9, fontcolor="{C_NET_TXT}"];\n'
        "  nodesep=0.30; ranksep=0.55;\n"
    )


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


def _edge(a: str, b: str, label: str = "", directed: bool = True) -> str:
    extra = []
    if label:
        extra.append(f'label="{html.escape(label)}"')
    if not directed:
        extra.append("dir=none")
    if extra:
        return f'  "{a}" -> "{b}" [{", ".join(extra)}];'
    return f'  "{a}" -> "{b}";'


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
        if _is_clock(net) or _is_reset(net):
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

    # boundary ports join nets that share their name; interface ports use their
    # modport to decide whether they are an input (left) or output (right) pin.
    boundary: dict[str, tuple[str, str]] = {}
    for p in mod.ports:
        if p.name in nets and not (_is_clock(p.name) or _is_reset(p.name)):
            d = p.eff_dir
            role = "driver" if d == "in" else ("load" if d == "out" else "both")
            side = "in" if d == "in" else "out"
            boundary[p.name] = (f"p__{p.name}", side)
            nets[p.name].append((f"p__{p.name}", role))

    # keep only multi-endpoint nets (actual connections)
    nets = {n: eps for n, eps in nets.items() if len({e[0] for e in eps}) >= 2}

    kept_nets = sorted(nets)[:max_nodes]

    lines = [_header("LR")]
    # Boundary ports sit outside the module block, like external pins. A boundary
    # port doubles as the hub for its net, so no separate signal node is drawn.
    for net in kept_nets:
        if net in boundary:
            _, side = boundary[net]
            rank = "min" if side == "in" else "max"
            ori = "" if side == "in" else "orientation=180, "
            lines.append(
                f'  {{ rank={rank}; "p__{net}" [shape=cds, {ori}'
                f'label="{html.escape(net)}", fillcolor="{C_PORT}", fontcolor="white", '
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
            lines.append(
                f'    "n__{net}" [label="{html.escape(net)}", '
                f'fillcolor="{C_NET}", fontcolor="{C_NET_TXT}", fontname="{FONT_MONO}", '
                'fontsize=9, margin="0.08,0.03"];'
            )
    lines.append("  }")
    # Wiring: drivers point into the signal (or boundary pin), signals point out
    # to their loads.
    for net in kept_nets:
        hub = f"p__{net}" if net in boundary else f"n__{net}"
        for node, role in {(n, r) for n, r in nets[net] if not n.startswith("p__")}:
            if role == "driver":
                lines.append(_edge(node, hub))
            elif role == "load":
                lines.append(_edge(hub, node))
            else:
                lines.append(_edge(hub, node, directed=False))
    lines.append("}")
    return "\n".join(lines)


# --- global hierarchy & packages -------------------------------------------

def hierarchy_dot(design: Design, max_nodes: int = 140) -> str:
    roots = design.tops or [
        n for n, m in design.modules.items() if m.package == design.root_package
    ]
    lines = [_header("LR")]
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
        lines.append(_edge(a, b))
    lines.append("}")
    return "\n".join(lines)


def package_dot(design: Design) -> str:
    lines = [_header("LR")]
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
                lines.append(_edge(name, dep))
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

    lines = [_header("LR")]
    for f in keep:
        is_owned = f in owned
        fill = C_OWNED if is_owned else C_DEP
        txt = "white" if is_owned else C_DEP_TXT
        lines.append(
            f'  "{f}" [label="{html.escape(labels[f])}", '
            f'tooltip="{html.escape(f)}", shape=box, '
            f'fillcolor="{fill}", fontcolor="{txt}", fontname="{FONT_MONO}", fontsize=10];'
        )
    for a, b in sorted(edges):
        if a in kept and b in kept:
            lines.append(_edge(a, b))
    lines.append("}")
    return "\n".join(lines)
