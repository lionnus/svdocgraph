"""Examines a documentation directory that the tool made.

A job in a CI pipeline runs `svdocgraph check`. The command makes sure that the
run gave the expected result, and not an empty site: a design that no longer
elaborates gives a site with no module, and the pipeline must stop.
"""

from __future__ import annotations

import json
import os
import re

INLINE_INDEX = re.compile(
    r'<script id="svdg-data" type="application/json">(.*?)</script>', re.S
)

#: The files that each site must have.
REQUIRED = ("index.html", "hierarchy.html", "packages.html", "design.json",
            "model.json", "assets/style.css", "assets/app.js")


def _names(value) -> list:
    """One name or a list of names."""
    if not value:
        return []
    return [value] if isinstance(value, str) else list(value)


class Limits:
    """The values that the site must reach. Each one is optional."""

    def __init__(self, **kw):
        self.min_modules = kw.get("min_modules", 1)
        self.min_interfaces = kw.get("min_interfaces", 0)
        self.min_docs = kw.get("min_docs", 0)
        self.min_sources = kw.get("min_sources", 0)
        self.max_diagnostics = kw.get("max_diagnostics")
        self.want_module = _names(kw.get("want_module"))
        self.want_interface = _names(kw.get("want_interface"))
        self.require_graphs = bool(kw.get("require_graphs"))
        self.require_file_graph = bool(kw.get("require_file_graph"))


def _glob(site: str, prefix: str) -> list:
    if not os.path.isdir(site):
        return []
    return sorted(f for f in os.listdir(site)
                  if f.startswith(prefix) and f.endswith(".html"))


def _read(site: str, name: str) -> str:
    with open(os.path.join(site, name)) as fh:
        return fh.read()


def _check_model(model: dict, lim: Limits, site: str, problems: list) -> dict:
    modules = model["modules"]
    n_iface = sum(1 for m in modules.values() if m.get("kind") == "interface")

    if len(modules) < lim.min_modules:
        problems.append(f"only {len(modules)} modules, expected >= {lim.min_modules}")
    if n_iface < lim.min_interfaces:
        problems.append(f"only {n_iface} interfaces, expected >= {lim.min_interfaces}")
    for want in lim.want_module:
        if want not in modules:
            problems.append(f"module {want} not extracted")
    for want in lim.want_interface:
        kind = modules.get(want, {}).get("kind")
        if kind != "interface":
            problems.append(f"{want} classified as {kind or 'absent'}, expected interface")

    diags = model.get("diagnostics", [])
    if lim.max_diagnostics is not None and len(diags) > lim.max_diagnostics:
        problems.append(f"{len(diags)} diagnostics (max {lim.max_diagnostics}): "
                        + "; ".join(diags[:5]))

    for name in modules:
        if not os.path.isfile(os.path.join(site, f"module-{name}.html")):
            problems.append(f"no page for module {name}")
            break

    with_ports = sum(1 for m in modules.values() if m.get("ports"))
    if modules and with_ports < len(modules) // 2:
        problems.append(f"only {with_ports}/{len(modules)} units have ports")
    return modules


def check(site: str, **kw) -> list:
    """Examines the site. Gives the list of the problems. Empty means good."""
    lim = Limits(**kw)
    problems: list = []
    modules: dict = {}

    for name in REQUIRED:
        if not os.path.isfile(os.path.join(site, name)):
            problems.append(f"missing {name}")

    if os.path.isfile(os.path.join(site, "model.json")):
        model = json.loads(_read(site, "model.json"))
        modules = _check_model(model, lim, site, problems)

    if os.path.isfile(os.path.join(site, "index.html")):
        m = INLINE_INDEX.search(_read(site, "index.html"))
        if not m:
            problems.append("index.html has no inlined search index")
        else:
            try:
                data = json.loads(m.group(1))
            except json.JSONDecodeError as exc:
                problems.append(f"inlined search index is not valid JSON: {exc}")
            else:
                if len(data.get("modules", [])) != len(modules):
                    problems.append("inlined search index does not match model.json")

    if lim.require_graphs and os.path.isfile(os.path.join(site, "hierarchy.html")):
        if "<svg" not in _read(site, "hierarchy.html"):
            problems.append("hierarchy.html has no inline SVG. Is Graphviz installed?")

    doc_pages = _glob(site, "doc-")
    if len(doc_pages) < lim.min_docs:
        problems.append(f"only {len(doc_pages)} written pages, "
                        f"expected >= {lim.min_docs}")

    if lim.require_file_graph:
        if not os.path.isfile(os.path.join(site, "files.html")):
            problems.append("no files.html")
        elif "<svg" not in _read(site, "files.html"):
            problems.append("files.html has no inline SVG")

    src_pages = _glob(site, "src-")
    if len(src_pages) < lim.min_sources:
        problems.append(f"only {len(src_pages)} source pages, "
                        f"expected >= {lim.min_sources}")
    elif lim.min_sources:
        if "hltable" not in _read(site, src_pages[0]):
            problems.append(f"{src_pages[0]} shows no code")
        if not any(m.get("line") for m in modules.values()):
            problems.append("no module has a line number")

    return problems


def summary(site: str) -> str:
    """One line that gives what the site holds."""
    modules: dict = {}
    path = os.path.join(site, "model.json")
    if os.path.isfile(path):
        modules = json.loads(_read(site, "model.json"))["modules"]
    n_iface = sum(1 for m in modules.values() if m.get("kind") == "interface")
    return (f"{len(modules)} units, {n_iface} interfaces, "
            f"{len(_glob(site, 'module-'))} module pages, "
            f"{len(_glob(site, 'doc-'))} written pages, "
            f"{len(_glob(site, 'src-'))} source pages")
