"""Writes the HTML pages.

The renderer makes a static site from the design model. The site operates offline:
each graph is inline SVG and the search index is in each page.
"""

from __future__ import annotations

import json
import os
import re
import shutil
from datetime import datetime, timezone

from jinja2 import Environment, FileSystemLoader, select_autoescape

from . import __version__, graphs, project
from .model import Design, Module
from .model import reset_polarity as model_reset_polarity

_HERE = os.path.dirname(os.path.abspath(__file__))
_TEMPLATES = os.path.join(_HERE, "templates")
_ASSETS = os.path.join(_HERE, "assets")

_SVG_WH = re.compile(r'(<svg\b[^>]*?)\s+width="[^"]*"\s+height="[^"]*"', re.S)


def _responsive(svg: str | None) -> str | None:
    """Removes the fixed size of an SVG. Thus the style sheet can scale it."""
    if not svg:
        return None
    svg = _SVG_WH.sub(r"\1", svg, count=1)
    return re.sub(r"<svg\b", '<svg class="svdg-graph"', svg, count=1)


def _json_for_script(payload) -> str:
    """JSON that is safe in an inline `<script>` element."""
    return (json.dumps(payload, separators=(",", ":"))
            .replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026"))


class Renderer:
    def __init__(self, design: Design, outdir: str, title: str = ""):
        self.design = design
        self.outdir = outdir
        self._search_json = "{}"   # replaced in _write_search_index, before any page
        self.env = Environment(
            loader=FileSystemLoader(_TEMPLATES),
            autoescape=select_autoescape(["html"]),
            trim_blocks=True,
            lstrip_blocks=True,
        )
        self.env.globals.update(
            tool_version=__version__,
            root_package=design.root_package,
            project_name=(title
                          or os.path.basename(design.project_root.rstrip("/"))
                          or "design"),
        )
        self.env.filters["dirbadge"] = _dirbadge
        self.env.filters["reset_polarity"] = model_reset_polarity

    def _nav(self) -> list[dict]:
        """The side bar. The modules are in groups by package."""
        groups: dict[str, list[Module]] = {}
        for m in self.design.modules.values():
            groups.setdefault(m.package or "(unknown)", []).append(m)
        ordered = sorted(
            groups.items(),
            key=lambda kv: (kv[0] != self.design.root_package, kv[0].lower()),
        )
        return [
            {
                "package": pkg,
                "is_root": pkg == self.design.root_package,
                "modules": sorted(mods, key=lambda m: m.name),
            }
            for pkg, mods in ordered
        ]

    def _ctx(self, **kw):
        base = {
            "nav": self._nav(),
            "design": self.design,
            # The index is in each page. Thus the search operates when the user
            # opens the page from the disk. A `file://` page cannot read a file.
            "search_json": self._search_json,
        }
        base.update(kw)
        return base

    def build(self) -> None:
        """Writes the full site."""
        os.makedirs(self.outdir, exist_ok=True)
        self._clean()
        self._copy_assets()
        self._write_search_index()
        self._render_index()
        self._render_hierarchy()
        self._render_packages()
        for name in self.design.modules:
            self._render_module(name)
        for name in self.design.packages:
            self._render_package(name)
        self._write_build_info()

    def _clean(self) -> None:
        """Removes the pages of the last run. Thus no old page stays.

        The function removes only the files that have the names that the tool
        writes. It does not remove the directory or any other file.
        """
        keep = {"index.html", "hierarchy.html", "packages.html"}
        for fn in os.listdir(self.outdir):
            ours = (
                fn in keep
                or fn == project.BUILD_INFO
                or fn in ("design.json", "model.json")
                or (fn.startswith(("module-", "package-")) and fn.endswith(".html"))
            )
            if ours:
                os.remove(os.path.join(self.outdir, fn))
        assets = os.path.join(self.outdir, "assets")
        if os.path.isdir(assets):
            shutil.rmtree(assets)

    def _write_build_info(self) -> None:
        project.write_build_info(
            self.outdir,
            version=__version__,
            project_root=self.design.project_root,
            root_package=self.design.root_package,
            generated_at=self.design.generated_at,
            modules=len(self.design.modules),
            packages=len(self.design.packages),
        )

    def _copy_assets(self) -> None:
        dst = os.path.join(self.outdir, "assets")
        shutil.copytree(_ASSETS, dst, dirs_exist_ok=True)

    def _write_search_index(self) -> None:
        """Writes the search index, and keeps a copy for the pages."""
        idx = []
        for m in self.design.modules.values():
            idx.append({
                "name": m.name,
                "kind": m.kind,
                "package": m.package,
                "ports": [p.name for p in m.ports],
                "url": f"module-{m.name}.html",
                "ni": m.n_inputs,
                "no": m.n_outputs,
                "owned": m.package == self.design.root_package,
            })
        payload = {
            "modules": idx,
            "packages": [
                {"name": p.name, "url": f"package-{p.name}.html", "root": p.root}
                for p in self.design.packages.values()
            ],
        }
        self._search_json = _json_for_script(payload)
        with open(os.path.join(self.outdir, "design.json"), "w") as fh:
            json.dump(payload, fh)
        # The full model, for other tools
        with open(os.path.join(self.outdir, "model.json"), "w") as fh:
            json.dump(self.design.to_json(), fh, indent=2)

    def _write(self, path: str, html: str) -> None:
        with open(os.path.join(self.outdir, path), "w") as fh:
            fh.write(html)

    def _render_index(self) -> None:
        d = self.design
        stats = {
            "modules": len(d.modules),
            "owned": sum(1 for m in d.modules.values() if m.package == d.root_package),
            "tops": len(d.tops),
            "packages": len(d.packages),
        }
        svg = _responsive(graphs.render_dot(graphs.hierarchy_dot(d, max_nodes=60)))
        html = self.env.get_template("index.html").render(
            **self._ctx(stats=stats, hierarchy_svg=svg, active="index")
        )
        self._write("index.html", html)

    def _render_hierarchy(self) -> None:
        svg = _responsive(graphs.render_dot(graphs.hierarchy_dot(self.design)))
        html = self.env.get_template("hierarchy.html").render(
            **self._ctx(hierarchy_svg=svg, active="hierarchy")
        )
        self._write("hierarchy.html", html)

    def _render_packages(self) -> None:
        svg = _responsive(graphs.render_dot(graphs.package_dot(self.design)))
        html = self.env.get_template("packages.html").render(
            **self._ctx(package_svg=svg, active="packages")
        )
        self._write("packages.html", html)

    def _render_module(self, name: str) -> None:
        mod = self.design.modules[name]
        dot = graphs.internal_dot(self.design, name)
        svg = _responsive(graphs.render_dot(dot)) if dot else None
        ports = {"in": [], "out": [], "inout": []}
        for p in mod.ports:
            ports.get(p.eff_dir, ports["inout"]).append(p)
        html = self.env.get_template("module.html").render(
            **self._ctx(mod=mod, ports=ports, internal_svg=svg, active="module")
        )
        self._write(f"module-{name}.html", html)

    def _render_package(self, name: str) -> None:
        pkg = self.design.packages[name]
        mods = sorted(
            (m for m in self.design.modules.values() if m.package == name),
            key=lambda m: m.name,
        )
        html = self.env.get_template("package.html").render(
            **self._ctx(pkg=pkg, modules=mods, active="package")
        )
        self._write(f"package-{name}.html", html)


def _dirbadge(direction: str) -> str:
    return {
        "in": "in", "out": "out", "inout": "io", "ref": "ref", "interface": "if",
    }.get(direction, direction)


def render_site(design: Design, outdir: str, title: str = "") -> None:
    design.generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    design.tool_version = __version__
    Renderer(design, outdir, title=title).build()
