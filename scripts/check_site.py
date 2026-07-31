#!/usr/bin/env python3
"""Examines a documentation directory that the tool made.

The integration workflow uses this script. It makes sure that a run against a real
design gave the expected result, and not an empty site. You can also use it
manually:

    python scripts/check_site.py .svdocgraph --min-modules 50 --want-interface AXI_BUS
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

INLINE_INDEX = re.compile(
    r'<script id="svdg-data" type="application/json">(.*?)</script>', re.S
)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("site", type=Path, help="the documentation directory")
    ap.add_argument("--min-modules", type=int, default=1)
    ap.add_argument("--min-interfaces", type=int, default=0)
    ap.add_argument("--want-module", action="append", default=[],
                    help="a module that must be in the result (repeatable)")
    ap.add_argument("--want-interface", action="append", default=[],
                    help="a unit that must be an interface (repeatable)")
    ap.add_argument("--max-diagnostics", type=int, default=None,
                    help="the maximum number of diagnostics")
    ap.add_argument("--require-graphs", action="store_true",
                    help="the hierarchy page must contain an SVG")
    ap.add_argument("--min-docs", type=int, default=0,
                    help="the least number of written documentation pages")
    ap.add_argument("--require-file-graph", action="store_true",
                    help="the site must contain the graph of the source files")
    args = ap.parse_args(argv)

    site: Path = args.site
    problems: list[str] = []

    def need(path: str) -> Path | None:
        p = site / path
        if not p.is_file():
            problems.append(f"missing {path}")
            return None
        return p

    for name in ("index.html", "hierarchy.html", "packages.html", "design.json",
                 "model.json", "assets/style.css", "assets/app.js"):
        need(name)

    model_path = site / "model.json"
    modules: dict = {}
    if model_path.is_file():
        model = json.loads(model_path.read_text())
        modules = model["modules"]
        kinds = [m.get("kind") for m in modules.values()]
        n_iface = kinds.count("interface")

        if len(modules) < args.min_modules:
            problems.append(f"only {len(modules)} modules, expected >= {args.min_modules}")
        if n_iface < args.min_interfaces:
            problems.append(f"only {n_iface} interfaces, expected >= {args.min_interfaces}")
        for want in args.want_module:
            if want not in modules:
                problems.append(f"module {want} not extracted")
        for want in args.want_interface:
            kind = modules.get(want, {}).get("kind")
            if kind != "interface":
                problems.append(f"{want} classified as {kind or 'absent'}, expected interface")

        diags = model.get("diagnostics", [])
        if args.max_diagnostics is not None and len(diags) > args.max_diagnostics:
            problems.append(f"{len(diags)} diagnostics (max {args.max_diagnostics}): "
                            + "; ".join(diags[:5]))

        # Each unit must have a page.
        for name in modules:
            if not (site / f"module-{name}.html").is_file():
                problems.append(f"no page for module {name}")
                break

        # The ports must be resolved, and not empty.
        with_ports = sum(1 for m in modules.values() if m.get("ports"))
        if modules and with_ports < len(modules) // 2:
            problems.append(f"only {with_ports}/{len(modules)} units have ports")

    index = site / "index.html"
    if index.is_file():
        html = index.read_text()
        m = INLINE_INDEX.search(html)
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

    if args.require_graphs:
        hier = site / "hierarchy.html"
        if hier.is_file() and "<svg" not in hier.read_text():
            problems.append("hierarchy.html contains no inline SVG (is Graphviz installed?)")

    doc_pages = sorted(site.glob("doc-*.html"))
    if len(doc_pages) < args.min_docs:
        problems.append(f"only {len(doc_pages)} written pages, expected >= {args.min_docs}")

    if args.require_file_graph:
        files_page = site / "files.html"
        if not files_page.is_file():
            problems.append("no files.html")
        elif "<svg" not in files_page.read_text():
            problems.append("files.html contains no inline SVG")

    if problems:
        print(f"FAIL {site}", file=sys.stderr)
        for p in problems:
            print(f"  - {p}", file=sys.stderr)
        return 1

    print(f"OK {site}: {len(modules)} units, "
          f"{sum(1 for m in modules.values() if m.get('kind') == 'interface')} interfaces, "
          f"{len(list(site.glob('module-*.html')))} pages, "
          f"{len(doc_pages)} written pages")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
