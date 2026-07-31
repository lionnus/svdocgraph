#!/usr/bin/env python3
"""Smoke-check a generated SVDocGraph site.

Used by the integration workflow to assert that a run against a real design
produced something meaningful, rather than an empty-but-successful site. Also
handy by hand:

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
    ap.add_argument("site", type=Path, help="generated site directory")
    ap.add_argument("--min-modules", type=int, default=1)
    ap.add_argument("--min-interfaces", type=int, default=0)
    ap.add_argument("--want-module", action="append", default=[],
                    help="module that must be present (repeatable)")
    ap.add_argument("--want-interface", action="append", default=[],
                    help="unit that must be classified as an interface (repeatable)")
    ap.add_argument("--max-diagnostics", type=int, default=None,
                    help="fail if the design carries more diagnostics than this")
    ap.add_argument("--require-graphs", action="store_true",
                    help="fail unless the hierarchy page contains an inline SVG")
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

        # Every extracted unit must have a page.
        for name in modules:
            if not (site / f"module-{name}.html").is_file():
                problems.append(f"no page for module {name}")
                break

        # Ports and parameters should actually be resolved, not empty shells.
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

    if problems:
        print(f"FAIL {site}", file=sys.stderr)
        for p in problems:
            print(f"  - {p}", file=sys.stderr)
        return 1

    print(f"OK {site}: {len(modules)} units, "
          f"{sum(1 for m in modules.values() if m.get('kind') == 'interface')} interfaces, "
          f"{len(list(site.glob('module-*.html')))} pages")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
