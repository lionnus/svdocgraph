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

from . import __version__, docs, graphs, markup, project, source
from .dot import render_dot
from .model import Design, Module
from .naming import reset_polarity

_HERE = os.path.dirname(os.path.abspath(__file__))
_TEMPLATES = os.path.join(_HERE, "templates")
_ASSETS = os.path.join(_HERE, "assets")

_SVG_WH = re.compile(r'(<svg\b[^>]*?)\s+width="[^"]*"\s+height="[^"]*"', re.S)


def _responsive(svg: str | None) -> str | None:
    """Removes the fixed size of an SVG. Thus the style sheet can scale it."""
    if not svg:
        return None
    svg = _SVG_WH.sub(r"\1", svg, count=1)
    return re.sub(r"<svg\b", '<svg class="rtld-graph"', svg, count=1)


def _json_for_script(payload) -> str:
    """JSON that is safe in an inline `<script>` element."""
    return (json.dumps(payload, separators=(",", ":"))
            .replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026"))


class Renderer:
    def __init__(self, design: Design, outdir: str, title: str = "",
                 doc_dirs: list | None = None, with_docs: bool = True,
                 with_sources: bool = True):
        self.design = design
        self.outdir = outdir
        self.doc_dirs = list(doc_dirs or [])
        self.with_docs = with_docs
        self.with_sources = with_sources
        self._doc_media: dict = {}
        self._file_dot = ""
        self._has_file_graph = False
        self._src_urls: dict[str, str] = {}   # rel path -> the page of the code
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
        self.env.filters["reset_polarity"] = reset_polarity

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
            "doc_nav": docs.order_pages(self.design.doc_pages),
            "has_files": self._has_file_graph or bool(self.design.sources),
            "design": self.design,
            "src_urls": self._src_urls,
        }
        base.update(kw)
        return base

    def build(self) -> None:
        """Writes the full site."""
        os.makedirs(self.outdir, exist_ok=True)
        self._clean()
        self._copy_assets()
        # The written pages and the file graph must exist before any page, because
        # each page shows them in the side bar.
        self._load_docs()
        self._load_sources()
        self._file_dot = graphs.file_dot(self.design)
        self._has_file_graph = bool(self._file_dot)
        self._write_search_index()
        self._render_index()
        self._render_hierarchy()
        self._render_packages()
        for name in self.design.modules:
            self._render_module(name)
        for name in self.design.packages:
            self._render_package(name)
        if self._has_file_graph or self.design.sources:
            self._render_files()
        for slug in self.design.sources:
            self._render_source(slug)
        for slug in self.design.doc_pages:
            self._render_doc(slug)
        docs.copy_media(self._doc_media, self.outdir)
        self._write_build_info()

    @property
    def _xref_targets(self) -> dict:
        """The address of each unit, for a link in the text."""
        targets = {n: f"module-{n}.html" for n in self.design.modules}
        targets.update({n: f"package-{n}.html" for n in self.design.packages})
        return targets

    def _load_docs(self) -> None:
        """Reads the Markdown files of the repository and makes HTML from them."""
        if not self.with_docs or not markup.HAVE_MARKDOWN or not self.design.project_root:
            return
        rel_paths = docs.find_files(self.design.project_root, self.doc_dirs)
        pages, media = docs.build_pages(self.design.project_root, rel_paths)
        docs.attach_to_modules(pages, self.design.modules)
        # A link to a unit makes the text navigable.
        targets = self._xref_targets
        for page in pages.values():
            page.html = markup.link_names(page.html, targets)
            if page.module:
                self.design.modules[page.module].doc_page = page.slug
        self.design.doc_pages = pages
        self._doc_media = media

    def _load_sources(self) -> None:
        """Reads the source files of the root package and makes HTML of the code.

        A dependency keeps its code out of the site. `bender checkout` puts the
        dependencies in the project, thus the package decides, not the path.
        """
        if not self.with_sources or not self.design.project_root:
            return
        files = list(self.design.source_files) + [
            m.file for m in self.design.modules.values()
            if m.file and m.package == self.design.root_package
        ]
        self.design.sources = source.collect(
            self.design.project_root, files, self.design.modules
        )
        self._src_urls = {s.rel_path: s.url for s in self.design.sources.values()}

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
                or fn in ("files.html",)
                or (fn.startswith(("module-", "package-", "doc-", "src-"))
                    and fn.endswith(".html"))
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
        # Pygments makes the colours of the code. Each style is a file, thus the
        # tool writes the style that it uses.
        with open(os.path.join(dst, "code.css"), "w") as fh:
            fh.write(source.style_css())

    def _write_search_index(self) -> None:
        """Writes the search index one time, as a script that each page loads.

        A `file://` page cannot read a file with `fetch`, but it can load a
        script. Thus the index is a script, and not JSON that the pages fetch or
        hold. A design of 150 modules gives an index of 150 kB. In each of the
        400 pages that is 60 MB. In one script it is 150 kB.
        """
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
            "docs": [
                {"name": d.title, "url": f"{d.slug}.html", "path": d.rel_path,
                 "text": d.text[:600]}
                for d in self.design.doc_pages.values()
            ],
            "files": [
                {"name": os.path.basename(s.rel_path), "url": s.url,
                 "path": s.rel_path, "lines": s.lines}
                for s in self.design.sources.values()
            ],
        }
        with open(os.path.join(self.outdir, "assets", "search.js"), "w") as fh:
            fh.write(f"window.RTLDOC_DATA={_json_for_script(payload)};\n")
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
        svg = _responsive(render_dot(graphs.hierarchy_dot(d, max_nodes=60)))
        html = self.env.get_template("index.html").render(
            **self._ctx(stats=stats, hierarchy_svg=svg, active="index")
        )
        self._write("index.html", html)

    def _render_hierarchy(self) -> None:
        svg = _responsive(render_dot(graphs.hierarchy_dot(self.design)))
        html = self.env.get_template("hierarchy.html").render(
            **self._ctx(hierarchy_svg=svg, active="hierarchy")
        )
        self._write("hierarchy.html", html)

    def _render_packages(self) -> None:
        svg = _responsive(render_dot(graphs.package_dot(self.design)))
        html = self.env.get_template("packages.html").render(
            **self._ctx(package_svg=svg, active="packages")
        )
        self._write("packages.html", html)

    def _render_module(self, name: str) -> None:
        mod = self.design.modules[name]
        # The comment above the declaration is Markdown or reStructuredText.
        comment_html = markup.link_names(markup.render_comment(mod.doc_comment),
                                       self._xref_targets) if mod.doc_comment else ""
        dot = graphs.internal_dot(self.design, name)
        svg = _responsive(render_dot(dot)) if dot else None
        ports = {"in": [], "out": [], "inout": []}
        for p in mod.ports:
            ports.get(p.eff_dir, ports["inout"]).append(p)
        html = self.env.get_template("module.html").render(
            **self._ctx(mod=mod, ports=ports, internal_svg=svg,
                        comment_html=comment_html, active="module")
        )
        self._write(f"module-{name}.html", html)

    def _render_files(self) -> None:
        """The graph of the source files and their connections."""
        rows = [
            {"path": s.rel_path, "units": [u[0] for u in s.units],
             "package": s.package, "url": s.url, "lines": s.lines}
            for s in sorted(self.design.sources.values(), key=lambda s: s.rel_path)
        ]
        if not rows:
            # No code on the site. The modules still give the list of the files.
            rels = sorted({m.rel_file for m in self.design.modules.values() if m.rel_file})
            for rel in rels:
                mods = [m for m in self.design.modules.values() if m.rel_file == rel]
                rows.append({"path": rel, "units": sorted(m.name for m in mods),
                             "package": mods[0].package, "url": "", "lines": 0})
        html = self.env.get_template("files.html").render(
            **self._ctx(file_svg=_responsive(render_dot(self._file_dot)),
                        rows=rows, active="files")
        )
        self._write("files.html", html)

    def _render_source(self, slug: str) -> None:
        src = self.design.sources[slug]
        html = self.env.get_template("source.html").render(
            **self._ctx(src=src, active="files")
        )
        self._write(f"{slug}.html", html)

    def _render_doc(self, slug: str) -> None:
        page = self.design.doc_pages[slug]
        html = self.env.get_template("doc.html").render(
            **self._ctx(page=page, active="doc")
        )
        self._write(f"{slug}.html", html)

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


def render_site(design: Design, outdir: str, title: str = "",
                doc_dirs: list | None = None, with_docs: bool = True,
                with_sources: bool = True) -> None:
    design.generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    design.tool_version = __version__
    Renderer(design, outdir, title=title, doc_dirs=doc_dirs, with_docs=with_docs,
             with_sources=with_sources).build()
