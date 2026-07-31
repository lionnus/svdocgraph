"""Elaborates the design with slang and makes the design model.

The tool drives slang in the same process through pyslang. Thus it reads the
elaborated tree directly.

The sequence is:

1. Read the source set and the files of the root package from bender.
2. Find the module names in those files with a regular expression. Give these
   names to slang as tops. Thus each module elaborates, also a module that no
   other module instantiates.
3. Elaborate one time. Then walk the instance tree of each top and make one
   Module for each definition.
4. If slang cannot elaborate a module of the root package, make a page from the
   source text only.

A module that fails gives a diagnostic. It does not stop the run.
"""

from __future__ import annotations

import os
import re

from .bender import BenderInfo
from .model import Design, Instance, Module, Param, Port, PortConn

# The `Driver` class is in `pyslang.driver` from pyslang 11. An older version has
# a different class that this tool cannot drive. `deps.check_pyslang` gives the
# message for that condition.
try:
    from pyslang.driver import Driver
    HAVE_PYSLANG = True
except ImportError:  # pragma: no cover - depends on the installed pyslang
    Driver = None
    HAVE_PYSLANG = False


# --- Functions that read the source text ------------------------------------

_DECL_RE = re.compile(
    r"^\s*(?P<kind>module|interface|package|program)\s+(?:automatic\s+|static\s+)?"
    r"(?P<name>\w+)",
    re.MULTILINE,
)


def declared_units(files: list[str]) -> dict[str, tuple[str, str]]:
    """Finds the modules in the files. Gives {name: (kind, file)}."""
    out: dict[str, tuple[str, str]] = {}
    for f in files:
        try:
            with open(f, errors="replace") as fh:
                text = fh.read()
        except OSError:
            continue
        for m in _DECL_RE.finditer(text):
            out.setdefault(m.group("name"), (m.group("kind"), f))
    return out


def _header_doc(file: str, name: str) -> str:
    """Reads the `//` comment lines immediately above the module declaration."""
    try:
        with open(file, errors="replace") as fh:
            lines = fh.readlines()
    except OSError:
        return ""
    decl = re.compile(r"^\s*(?:module|interface)\s+" + re.escape(name) + r"\b")
    idx = next((i for i, ln in enumerate(lines) if decl.match(ln)), None)
    if idx is None:
        return ""
    doc: list[str] = []
    j = idx - 1
    while j >= 0:
        s = lines[j].strip()
        if s.startswith("//"):
            body = s[2:].strip()
            # Do not use the licence lines.
            if body and not re.match(r"(copyright|spdx|licen|http|---)", body, re.I):
                doc.append(body)
            j -= 1
        elif s == "":
            break
        else:
            break
    return " ".join(reversed(doc))[:300]


# --- Functions that read the elaborated tree --------------------------------

def _dir_str(direction) -> str:
    s = str(direction).split(".")[-1].lower()
    return {"in": "in", "out": "out", "inout": "inout", "ref": "ref"}.get(s, s)


def _kind(sym) -> str:
    return type(sym).__name__


def _direct_instances(body) -> list:
    """The child instances of a module. Includes the generate blocks."""
    found: list = []

    def walk(scope):
        for m in scope:
            k = _kind(m)
            if k == "InstanceSymbol":
                found.append(m)
            elif k in (
                "GenerateBlockSymbol",
                "GenerateBlockArraySymbol",
                "StatementBlockSymbol",
            ):
                walk(m)

    walk(body)
    return found


def _port_from_symbol(p) -> Port | None:
    k = _kind(p)
    if k == "InterfacePortSymbol":
        iface = ""
        for attr in ("interfaceDef", "interface"):
            obj = getattr(p, attr, None)
            if obj is not None:
                iface = getattr(obj, "name", "") or str(obj)
                break
        mp = getattr(p, "modport", "")
        modport = getattr(mp, "name", "") if mp and not isinstance(mp, str) else (mp or "")
        return Port(
            name=p.name, direction="interface", type=iface or "interface",
            is_interface=True, interface=iface, modport=modport,
        )
    if k != "PortSymbol":
        return None
    t = getattr(p, "type", None)
    width = getattr(t, "bitWidth", None) if t is not None else None
    return Port(
        name=p.name,
        direction=_dir_str(getattr(p, "direction", "")),
        type=str(t) if t is not None else "",
        width=width if width else None,
    )


def _conn_info(pc, sm) -> tuple[str, str, bool]:
    """Gives (net, modport, is_interface) for one port connection.

    For an interface port, slang gives the connected instance and the modport in
    `ifaceConn`. For a usual port, the tool reads the connected expression.
    """
    port = getattr(pc, "port", None)
    expr = getattr(pc, "expression", None)
    if port is not None and _kind(port) == "InterfacePortSymbol":
        modport = ""
        fallback = ""
        ic = getattr(pc, "ifaceConn", None)
        if isinstance(ic, (tuple, list)) and ic:
            if len(ic) > 1 and ic[1] is not None:
                modport = getattr(ic[1], "name", "") or ""
            if ic[0] is not None:
                fallback = getattr(ic[0], "name", "") or ""
        # Use the source text first. It has the true net name. `ifaceConn` gives
        # the name of the interface type for a boundary port. That name would
        # make one net from two different streams.
        return _net_text(expr, sm) or fallback, modport, True
    return _net_text(expr, sm), "", False


def _net_text(expr, sm) -> str:
    """The connected net, as written in the source.

    slang puts the connection of an output port in an assignment. The external
    net is on one side of it. For the other ports the tool reads the source range
    of the expression. Thus a bit-select keeps its index.
    """
    if expr is None:
        return ""
    if _kind(expr) == "AssignmentExpression":
        for side in (getattr(expr, "left", None), getattr(expr, "right", None)):
            if side is not None and _kind(side) != "EmptyArgumentExpression":
                text = _net_text(side, sm)
                if text:
                    return text
        return ""
    syn = getattr(expr, "syntax", None)
    if syn is not None:
        return str(syn).strip()
    sr = getattr(expr, "sourceRange", None)
    if sr is not None and sm is not None:
        try:
            return sm.getSourceText(sr.start.buffer)[sr.start.offset:sr.end.offset].strip()
        except Exception:
            pass
    return ""


def _instance_from_symbol(inst, sm) -> Instance:
    body = inst.body
    defn = getattr(body, "definition", None)
    module = defn.name if defn is not None else getattr(body, "name", "?")
    is_iface = "interface" in str(getattr(defn, "definitionKind", "")).lower()
    params: dict[str, str] = {}
    for p in body.parameters:
        if not getattr(p, "isLocal", False):
            params[p.name] = str(getattr(p, "value", ""))
    conns: list[PortConn] = []
    for pc in (inst.portConnections or []):
        port = getattr(pc, "port", None)
        pname = getattr(port, "name", "") if port is not None else ""
        net, modport, is_if = _conn_info(pc, sm)
        conns.append(PortConn(port=pname, net=net, is_interface=is_if, modport=modport))
    return Instance(
        name=inst.name, module=module, params=params, conns=conns,
        is_interface=is_iface,
    )


def _collapse_instances(raw: list[Instance]) -> list[Instance]:
    """Makes one instance from the copies that a generate loop or an array makes."""
    out: dict[tuple[str, str], Instance] = {}
    order: list[tuple[str, str]] = []
    for inst in raw:
        key = (inst.name, inst.module)
        if key in out:
            out[key].count += 1
            out[key].array = True
        else:
            out[key] = inst
            order.append(key)
    return [out[k] for k in order]


def _definition_kind(defn) -> str:
    """The kind of an elaborated definition: module, interface or program.

    Without this, the tool shows each interface as a module.
    """
    raw = getattr(defn, "definitionKind", None)
    name = getattr(raw, "name", "") or str(raw).rsplit(".", 1)[-1]
    kind = name.split(":")[0].strip().lower()
    return kind if kind in ("module", "interface", "program", "package") else "module"


def _module_from_body(body, sm) -> Module:
    defn = getattr(body, "definition", None)
    name = defn.name if defn is not None else body.name
    mod = Module(name=name, kind=_definition_kind(defn), elaborated=True)
    # The file and the line
    loc = getattr(defn, "location", None)
    if loc is not None and sm is not None:
        try:
            mod.file = os.path.realpath(sm.getFileName(loc))
            mod.line = sm.getLineNumber(loc)
        except Exception:
            pass
    for p in body.portList:
        port = _port_from_symbol(p)
        if port is not None:
            mod.ports.append(port)
    for p in body.parameters:
        mod.params.append(
            Param(
                name=p.name,
                value=str(getattr(p, "value", "")),
                is_localparam=bool(getattr(p, "isLocal", False)),
            )
        )
    for m in body:
        if _kind(m) == "WildcardImportSymbol":
            pkg = getattr(m, "package", None)
            pname = getattr(pkg, "name", "") if pkg is not None else ""
            if pname and pname not in mod.imports:
                mod.imports.append(pname)
    raw = [_instance_from_symbol(i, sm) for i in _direct_instances(body)]
    mod.instances = _collapse_instances(raw)
    return mod


# --- The main function ------------------------------------------------------

def extract_design(
    project_root: str,
    bender: BenderInfo,
    cmd_file: str,
    extra_tops: list[str] | None = None,
) -> Design:
    design = Design(root_package=bender.root_package, project_root=project_root)
    design.diagnostics.extend(bender.diagnostics)

    if not HAVE_PYSLANG:
        design.diagnostics.append(
            "pyslang is not available, or its version is too old. The tool needs "
            "version 11. Run `svdocgraph doctor`."
        )
        return design
    if not cmd_file or not os.path.exists(cmd_file):
        design.diagnostics.append("No slang command file. bender gave no file list.")
        return design

    owned = declared_units(bender.root_files)
    owned_modules = [n for n, (k, _) in owned.items() if k in ("module", "interface")]
    tops = sorted(set(owned_modules) | set(extra_tops or []))

    driver = Driver()
    driver.addStandardArgs()
    top_args = " ".join(f"--top {t}" for t in tops)
    cmd = (
        f'slang -f "{cmd_file}" {top_args} '
        "--ignore-unknown-modules --allow-toplevel-iface-ports "
        "--error-limit=0 --max-instance-array 4096"
    )
    if not driver.parseCommandLine(cmd):
        design.diagnostics.append("slang did not accept the command line.")
        return design
    if not driver.processOptions():
        design.diagnostics.append("slang did not accept the options or the file list.")
        return design
    driver.parseAllSources()
    comp = driver.createCompilation()
    sm = comp.sourceManager

    # Walk the instance tree of each top. Keep one module for each definition.
    seen: set[str] = set()

    def visit(sym):
        if _kind(sym) == "InstanceSymbol":
            body = sym.body
            defn = getattr(body, "definition", None)
            dname = defn.name if defn is not None else getattr(body, "name", "")
            if dname and dname not in seen:
                seen.add(dname)
                try:
                    design.modules[dname] = _module_from_body(body, sm)
                except Exception as exc:  # One bad module must not stop the run
                    design.diagnostics.append(f"extract {dname}: {exc}")

    root = comp.getRoot()
    for top in root.topInstances:
        try:
            top.visit(visit)
        except Exception as exc:
            design.diagnostics.append(f"visit {top.name}: {exc}")

    # A module of the root package that slang did not elaborate keeps a page.
    for name in owned_modules:
        if name not in design.modules:
            kind, file = owned[name]
            design.modules[name] = Module(
                name=name, kind=kind, file=os.path.realpath(file), elaborated=False,
                desc="(not elaborated - from the source text only)",
            )

    _annotate(design, bender, owned)
    return design


def _annotate(design: Design, bender: BenderInfo, owned: dict) -> None:
    """Adds the origin, the package, the comments and the parent modules."""
    design.packages = bender.packages
    for name, mod in design.modules.items():
        # The origin of the module
        if mod.file:
            mod.package = bender.file_to_package.get(mod.file, "")
            if mod.file.startswith(design.project_root):
                mod.rel_file = os.path.relpath(mod.file, design.project_root)
        if not mod.package and name in owned:
            mod.package = bender.root_package
        # The comment above the declaration
        if mod.file and not mod.desc.startswith("("):
            doc = _header_doc(mod.file, name)
            if doc:
                mod.desc = doc
    # reverse edges + unknown flagging (module hierarchy only, skip interfaces)
    known = set(design.modules)
    for name, mod in design.modules.items():
        for inst in mod.instances:
            if inst.module not in known:
                inst.unknown = True
            elif not inst.is_interface:
                design.modules[inst.module].instantiated_by.append(name)
    for mod in design.modules.values():
        mod.instantiated_by = sorted(set(mod.instantiated_by))
    # design tops = owned modules nobody instantiates
    design.tops = sorted(
        n for n, m in design.modules.items()
        if m.package == bender.root_package and not m.instantiated_by
    )
