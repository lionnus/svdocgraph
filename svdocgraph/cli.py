"""SVDocGraph command-line interface.

Designed to feel like ``mkdocs`` / ``cargo doc`` for Bender-based SystemVerilog:
run it inside any bender project and it discovers everything itself.

  svdocgraph build [PATH]     generate the static site
  svdocgraph serve [PATH]     build, then serve locally with live preview
  svdocgraph dump  [PATH]     emit the extracted design model as JSON
"""

from __future__ import annotations

import argparse
import os
import sys
import tempfile
import webbrowser

from . import __version__, bender, extract
from .render import render_site


def _log(msg: str) -> None:
    print(f"\033[36m›\033[0m {msg}", file=sys.stderr)


def _ok(msg: str) -> None:
    print(f"\033[32m✓\033[0m {msg}", file=sys.stderr)


def _warn(msg: str) -> None:
    print(f"\033[33m!\033[0m {msg}", file=sys.stderr)


def _build_design(project_root: str, tops: list[str]):
    project_root = os.path.abspath(project_root)
    _log(f"Project: {project_root}")
    info = bender.collect(project_root)
    if info.root_package:
        _log(f"Bender root package: \033[1m{info.root_package}\033[0m "
             f"({len(info.root_files)} source files, {len(info.packages)} deps)")
    else:
        _warn("No bender root package detected (is there a Bender.yml?).")

    with tempfile.TemporaryDirectory() as td:
        cmd_file = bender.write_command_file(info, os.path.join(td, "sources.f")) or ""
        _log("Elaborating with slang …")
        design = extract.extract_design(project_root, info, cmd_file, extra_tops=tops)

    _ok(f"Extracted {len(design.modules)} modules "
        f"({sum(1 for m in design.modules.values() if m.package == design.root_package)} owned), "
        f"{len(design.tops)} tops")
    for d in design.diagnostics[:8]:
        _warn(d)
    return design


def cmd_build(args) -> int:
    design = _build_design(args.path, args.top or [])
    if not design.modules:
        _warn("No modules extracted - nothing to render.")
        return 1
    out = os.path.abspath(args.output)
    _log(f"Rendering site → {out}")
    render_site(design, out)
    _ok(f"Done. Open {os.path.join(out, 'index.html')}")
    if args.open:
        webbrowser.open("file://" + os.path.join(out, "index.html"))
    return 0


def cmd_dump(args) -> int:
    import json
    design = _build_design(args.path, args.top or [])
    out = args.output
    with open(out, "w") as fh:
        json.dump(design.to_json(), fh, indent=2)
    _ok(f"Wrote {out}")
    return 0


def cmd_serve(args) -> int:
    import functools
    import http.server
    import socketserver

    rc = cmd_build(args)
    if rc != 0:
        return rc
    out = os.path.abspath(args.output)
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=out)
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("", args.port), handler) as httpd:
        url = f"http://localhost:{args.port}/"
        _ok(f"Serving at \033[1m{url}\033[0m  (Ctrl-C to stop)")
        if args.open:
            webbrowser.open(url)
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print(file=sys.stderr)
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(
        prog="svdocgraph",
        description="Bender-aware SystemVerilog design map & documentation generator.",
    )
    p.add_argument("--version", action="version", version=f"svdocgraph {__version__}")
    sub = p.add_subparsers(dest="cmd", required=True)

    def common(sp):
        sp.add_argument("path", nargs="?", default=".", help="project root (default: .)")
        sp.add_argument("--top", action="append", help="extra top module(s) to elaborate")

    b = sub.add_parser("build", help="generate the static documentation site")
    common(b)
    b.add_argument("-o", "--output", default="svdocgraph_site", help="output directory")
    b.add_argument("--open", action="store_true", help="open the result in a browser")
    b.set_defaults(func=cmd_build)

    s = sub.add_parser("serve", help="build then serve locally")
    common(s)
    s.add_argument("-o", "--output", default="svdocgraph_site", help="output directory")
    s.add_argument("-p", "--port", type=int, default=8080, help="port (default: 8080)")
    s.add_argument("--open", action="store_true", help="open the browser")
    s.set_defaults(func=cmd_serve)

    d = sub.add_parser("dump", help="emit the extracted design model as JSON")
    common(d)
    d.add_argument("-o", "--output", default="svdocgraph.json", help="output JSON file")
    d.set_defaults(func=cmd_dump)

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
