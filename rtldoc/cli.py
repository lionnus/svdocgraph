"""The command-line interface.

The user installs the tool one time and then runs it in a Bender project. The tool
finds the project data without options.

Exit codes: 1 no modules, 2 the output directory has other files, 3 a necessary
program is not available, 4 bender failed.
"""

from __future__ import annotations

import argparse
import os
import sys
import webbrowser

from . import __version__, api, check, deps, project
from .api import BenderFailed
from .render import render_site

QUIET = False


def _log(msg: str) -> None:
    if not QUIET:
        print(f"\033[36m›\033[0m {msg}", file=sys.stderr)


def _ok(msg: str) -> None:
    if not QUIET:
        print(f"\033[32m✓\033[0m {msg}", file=sys.stderr)


def _warn(msg: str) -> None:
    print(f"\033[33m!\033[0m {msg}", file=sys.stderr)


def _err(msg: str) -> None:
    print(f"\033[31m✗\033[0m {msg}", file=sys.stderr)


# -- shared resolution -----------------------------------------------------


class Ctx:
    """The project root, the settings and the output directory for one command."""

    def __init__(self, args, use_output: bool = True):
        self.root, found = project.find_project_root(args.path)
        if not found:
            _warn(f"No Bender.yml in {os.path.abspath(args.path)} or in its parents. "
                  "The tool uses that directory as the project root.")
        self.config = project.load_config(self.root)
        # The `-o` option of `dump` gives a file, not a directory.
        out = (getattr(args, "output", None) if use_output else None) or self.config.output
        self.outdir = out if os.path.isabs(out) else os.path.join(self.root, out)
        self.outdir = os.path.abspath(self.outdir)
        self.is_default_output = not use_output or getattr(args, "output", None) is None
        self.tops = list(dict.fromkeys(self.config.tops + (getattr(args, "top", None) or [])))

    @property
    def rel_out(self) -> str:
        rel = os.path.relpath(self.outdir, os.getcwd())
        return rel if not rel.startswith("..") else self.outdir


def _build_design(ctx: Ctx):
    _log(f"Project: {ctx.root}")
    if ctx.config.found:
        _log(f"Settings: {os.path.relpath(ctx.config.path, ctx.root)}")
    design = api.extract_design(ctx.root, tops=ctx.tops, log=_log)
    if not design.root_package:
        _warn("No bender root package. Make sure that Bender.yml gives a name.")
    _ok(f"{len(design.modules)} modules "
        f"({sum(1 for m in design.modules.values() if m.package == design.root_package)} "
        f"in the root package), {len(design.tops)} tops")
    for d in design.diagnostics[:8]:
        _warn(d)
    return design


def _bender_failed(exc: Exception) -> None:
    """Shows the message from bender."""
    _err("bender could not describe this project:")
    for line in str(exc).splitlines():
        print(f"    {line}", file=sys.stderr)
    _err("Correct the bender setup first. `bender checkout` shows the same "
         "problem. The tool wrote no files.")


def _preflight() -> int:
    """Stops before the elaboration if a necessary program is not available."""
    missing = [d for d in deps.check_all() if not d.ok]
    for dep in missing:
        report = _err if dep.required else _warn
        report(f"{dep.name}: {dep.detail}")
        for line in dep.hint.splitlines():
            report(f"  {line}")
    return 3 if any(d.required for d in missing) else 0


def _generate(ctx: Ctx, force: bool) -> int:
    """Elaborates the design and writes the pages. Gives the exit code."""
    rc = _preflight()
    if rc:
        return rc
    if not force and not project.is_ours(ctx.outdir):
        _err(f"{ctx.rel_out} contains files that this tool did not write.")
        _err("Use --force to replace them, or use -o to select a different directory.")
        return 2

    try:
        design = _build_design(ctx)
    except BenderFailed as exc:
        _bender_failed(exc)
        return 4
    if not design.modules:
        _err("The tool found no modules. It wrote no pages.")
        return 1

    _log(f"Pages → {ctx.rel_out}")
    render_site(design, ctx.outdir, title=ctx.config.name,
                doc_dirs=ctx.config.doc_dirs if ctx.config.docs_enabled else None,
                with_docs=ctx.config.docs_enabled,
                with_sources=ctx.config.sources_enabled)

    if ctx.is_default_output:
        touched = project.ensure_gitignored(ctx.outdir)
        if touched:
            _log(f"Added {os.path.basename(ctx.outdir)}/ to the "
                 f"{os.path.relpath(touched, os.getcwd())}")

    _ok(f"The documentation is ready in \033[1m{ctx.rel_out}\033[0m")
    _log(f"To open it: rtldoc open   ({project.index_url(ctx.outdir)})")
    return 0


def _open_browser(url: str) -> None:
    if not webbrowser.open(url):
        _warn(f"The tool cannot start a browser. Open this URL manually:\n  {url}")


# -- commands --------------------------------------------------------------


def cmd_gen(args) -> int:
    ctx = Ctx(args)
    rc = _generate(ctx, args.force)
    if rc == 0 and args.open:
        _open_browser(project.index_url(ctx.outdir))
    return rc


def cmd_open(args) -> int:
    ctx = Ctx(args)
    index = os.path.join(ctx.outdir, "index.html")
    if not os.path.isfile(index):
        _log("There is no documentation. The tool makes it first.")
        rc = _generate(ctx, args.force)
        if rc != 0:
            return rc
    else:
        info = project.read_build_info(ctx.outdir) or {}
        when = info.get("generated_at")
        _log(f"Open {ctx.rel_out}" + (f" (made {when})" if when else ""))
    _open_browser(project.index_url(ctx.outdir))
    return 0


def cmd_serve(args) -> int:
    import functools
    import http.server
    import socketserver

    ctx = Ctx(args)
    if not args.no_build or not os.path.isfile(os.path.join(ctx.outdir, "index.html")):
        rc = _generate(ctx, args.force)
        if rc != 0:
            return rc

    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=ctx.outdir)
    socketserver.TCPServer.allow_reuse_address = True
    try:
        httpd = socketserver.TCPServer(("", args.port), handler)
    except OSError as exc:
        _err(f"Cannot listen on port {args.port}: {exc}")
        return 1
    with httpd:
        url = f"http://localhost:{args.port}/"
        _ok(f"Server at \033[1m{url}\033[0m . Push Ctrl-C to stop.")
        if args.open:
            _open_browser(url)
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print(file=sys.stderr)
    return 0


def cmd_init(args) -> int:
    root, found = project.find_project_root(args.path)
    if not found:
        _warn(f"No Bender.yml in {os.path.abspath(args.path)} or in its parents. "
              "Run this command in a Bender project.")
    cfg = project.write_config(root)
    if cfg:
        _ok(f"Wrote {os.path.relpath(cfg, os.getcwd())}")
    else:
        _log("The settings file already exists. The tool did not change it.")
    touched = project.ensure_gitignored(os.path.join(root, project.DEFAULT_OUTPUT))
    if touched:
        _ok(f"Added {project.DEFAULT_OUTPUT}/ to {os.path.relpath(touched, os.getcwd())}")
    print(
        "\nNext:\n"
        "  rtldoc gen --open      make the documentation and open it\n"
        "\nTo call the tool from a Makefile:\n"
        "  .PHONY: docs\n"
        "  docs:\n"
        "  \trtldoc gen\n",
        file=sys.stderr,
    )
    return 0


def cmd_doctor(args) -> int:
    """Shows the status of each necessary program."""
    checks = deps.check_all()
    width = max(len(d.name) for d in checks)
    bad = False
    for d in checks:
        mark = "\033[32m✓\033[0m" if d.ok else (
            "\033[31m✗\033[0m" if d.required else "\033[33m!\033[0m")
        print(f"{mark} {d.name.ljust(width)}  {d.detail}")
        if not d.ok:
            bad = bad or d.required
            for line in d.hint.splitlines():
                print(f"  {line}")
    if bad:
        print("\nInstall the items with ✗ before you run the tool.")
        return 3
    print("\nAll the necessary programs are available. Run `rtldoc gen`.")
    return 0


def cmd_check(args) -> int:
    """Examines a directory that `gen` made. For a job in a CI pipeline."""
    problems = check.check(
        args.site,
        min_modules=args.min_modules, min_interfaces=args.min_interfaces,
        min_docs=args.min_docs, min_sources=args.min_sources,
        max_diagnostics=args.max_diagnostics,
        want_module=args.want_module, want_interface=args.want_interface,
        require_graphs=args.require_graphs, require_file_graph=args.require_file_graph,
    )
    if problems:
        _err(f"{args.site} is not complete:")
        for p in problems:
            print(f"    {p}", file=sys.stderr)
        return 1
    _ok(f"{args.site}: {check.summary(args.site)}")
    return 0


def cmd_dump(args) -> int:
    import json
    rc = _preflight()
    if rc:
        return rc
    ctx = Ctx(args, use_output=False)
    try:
        design = _build_design(ctx)
    except BenderFailed as exc:
        _bender_failed(exc)
        return 4
    with open(args.output, "w") as fh:
        json.dump(design.to_json(), fh, indent=2)
    _ok(f"Wrote {args.output}")
    return 0


# -- argument parsing ------------------------------------------------------


def main(argv=None) -> int:
    p = argparse.ArgumentParser(
        prog="rtldoc",
        description="Bender-aware SystemVerilog design map & documentation generator. "
                    "Run it from the root of a bender project.",
    )
    p.add_argument("--version", action="version", version=f"rtldoc {__version__}")
    p.add_argument("-q", "--quiet", action="store_true", help="only print warnings and errors")
    sub = p.add_subparsers(dest="cmd", required=True)

    def common(sp, output: bool = True):
        # The user can put --quiet before or after the command name. SUPPRESS
        # keeps the value from the first position.
        sp.add_argument("-q", "--quiet", action="store_true", default=argparse.SUPPRESS,
                        help="only print warnings and errors")
        sp.add_argument("path", nargs="?", default=".",
                        help="project root (default: nearest Bender.yml from here)")
        sp.add_argument("--top", action="append", metavar="NAME",
                        help="extra top module(s) to elaborate (repeatable)")
        if output:
            sp.add_argument("-o", "--output", metavar="DIR",
                            help=f"output directory (default: {project.DEFAULT_OUTPUT}/)")
            sp.add_argument("--force", action="store_true",
                            help="overwrite an output directory not generated by rtldoc")

    g = sub.add_parser("gen", aliases=["build"], help="generate the documentation")
    common(g)
    g.add_argument("--open", action="store_true", help="open the result in a browser")
    g.set_defaults(func=cmd_gen)

    o = sub.add_parser("open", help="open the generated documentation (builds it if missing)")
    common(o)
    o.set_defaults(func=cmd_open)

    s = sub.add_parser("serve", help="generate, then serve over http")
    common(s)
    s.add_argument("-p", "--port", type=int, default=8080, help="port (default: 8080)")
    s.add_argument("--open", action="store_true", help="open the browser")
    s.add_argument("--no-build", action="store_true", help="serve an existing build as-is")
    s.set_defaults(func=cmd_serve)

    i = sub.add_parser("init", help="write rtldoc.yml and a .gitignore rule")
    i.add_argument("-q", "--quiet", action="store_true", default=argparse.SUPPRESS,
                   help="only print warnings and errors")
    i.add_argument("path", nargs="?", default=".", help="project root (default: .)")
    i.set_defaults(func=cmd_init)

    doc = sub.add_parser("doctor", help="show the status of the necessary programs")
    doc.set_defaults(func=cmd_doctor)

    c = sub.add_parser("check", help="examine a generated directory (for CI)")
    c.add_argument("site", help="the directory that `gen` wrote")
    c.add_argument("--min-modules", type=int, default=1)
    c.add_argument("--min-interfaces", type=int, default=0)
    c.add_argument("--min-docs", type=int, default=0, help="written pages")
    c.add_argument("--min-sources", type=int, default=0, help="pages with code")
    c.add_argument("--max-diagnostics", type=int, default=None)
    c.add_argument("--want-module", action="append", default=[], metavar="NAME",
                   help="a module that must be in the result (repeatable)")
    c.add_argument("--want-interface", action="append", default=[], metavar="NAME",
                   help="a unit that must be an interface (repeatable)")
    c.add_argument("--require-graphs", action="store_true")
    c.add_argument("--require-file-graph", action="store_true")
    c.set_defaults(func=cmd_check, quiet=False)

    d = sub.add_parser("dump", help="emit the extracted design model as JSON")
    common(d, output=False)
    d.add_argument("-o", "--output", default="rtldoc.json", help="output JSON file")
    d.set_defaults(func=cmd_dump)

    args = p.parse_args(argv)
    global QUIET
    QUIET = args.quiet
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
