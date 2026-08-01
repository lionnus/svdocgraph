"""The Graphviz interface: the colours, the DOT syntax and the process.

`graphs` says which graphs the tool draws. This module says how a graph becomes
DOT and then SVG. Graphviz is an external program, thus `render_dot` gives None
if it is not installed, and each page operates without the graphs.
"""

from __future__ import annotations

import html
import shutil
import subprocess

# The colours. Each fill is solid. There are no borders and no round corners.
C_OWNED = "#2563eb"     # Modules of the root package
C_TOP = "#7c3aed"       # Design tops
C_DEP = "#e2e8f0"       # Modules of a dependency, and black boxes
C_DEP_TXT = "#334155"
C_IFACE = "#0d9488"     # Interfaces
C_NET = "#ffffff"       # Signal nodes
C_NET_TXT = "#475569"
# The pins of the module. The colour gives the kind, the shape gives the
# direction. These are the colours of the port table, thus the two agree.
C_IN = "#2563eb"        # An input
C_OUT = "#c81d77"       # An output
C_IO = "#b45309"        # No direction: the signals go both ways

# `cds` draws about two thirds of the height of its node, and `hexagon` draws the
# full height. These values give each pin and each signal the same height.
PIN_CDS = 'shape=cds, height=0.37, margin="0.16,0.0"'
PIN_HEX = 'shape=hexagon, height=0.25, margin="0.16,0.0"'
NET_BOX = 'shape=box, height=0.25, margin="0.10,0.0"'
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


def header(rankdir: str = "TB") -> str:
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


def edge(a: str, b: str, label: str = "", directed: bool = True) -> str:
    extra = []
    if label:
        extra.append(f'label="{html.escape(label)}"')
    if not directed:
        extra.append("dir=none")
    if extra:
        return f'  "{a}" -> "{b}" [{", ".join(extra)}];'
    return f'  "{a}" -> "{b}";'
