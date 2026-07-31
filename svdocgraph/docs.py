"""Reads the written documentation of the project.

A repository has two kinds of documentation. The RTL gives the modules, the
ports and the connections. The Markdown files give the text that a person wrote:
the README, and the pages in `doc/` or `docs/`.

This module finds those files and makes HTML from them. Thus one site contains
both kinds. Three connections join them:

* A page with the name of a module attaches to the page of that module. For
  example, `doc/axi_xbar.md` attaches to the module `axi_xbar`.
* A `code` element with the name of a module becomes a link to that module.
* The pages are in the search index.
"""

from __future__ import annotations

import os
import re
import shutil
from dataclasses import dataclass, field

try:
    from markdown_it import MarkdownIt
    HAVE_MARKDOWN = True
except ImportError:  # pragma: no cover - depends on the installed packages
    MarkdownIt = None
    HAVE_MARKDOWN = False

#: The directories that hold the written documentation, in the sequence of the
#: search. The README of the project root is always included.
DOC_DIRS = ("docs", "doc", "documentation")

#: The files to read. Sphinx uses .rst, which this version does not read.
DOC_SUFFIXES = (".md", ".markdown")

#: The image types to copy into the site.
MEDIA_SUFFIXES = (".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp")

#: The directory in the site that holds the images of the documentation.
MEDIA_DIR = "docmedia"

_MAX_BYTES = 2_000_000     # A larger file is not documentation.


@dataclass
class DocPage:
    """One page of written documentation."""

    slug: str                  # The name of the HTML file, without the suffix
    title: str
    rel_path: str              # The path from the project root
    html: str = ""             # The body of the page
    module: str = ""           # The module that this page documents
    headings: list = field(default_factory=list)   # (level, text, anchor)
    text: str = ""             # The text without markup, for the search

    @property
    def url(self) -> str:
        return f"{self.slug}.html"


# --- Discovery --------------------------------------------------------------


def _slug(rel_path: str) -> str:
    """The name of the HTML file for a documentation file.

    The name of the documentation directory is not in the slug. Thus
    `doc/axi_xbar.md` becomes `doc-axi_xbar`, which keeps the name of the module.
    """
    stem = os.path.splitext(rel_path)[0]
    parts = stem.replace("\\", "/").split("/")
    if len(parts) > 1 and parts[0].lower() in DOC_DIRS:
        parts = parts[1:]
    slug = re.sub(r"[^A-Za-z0-9_]+", "-", "-".join(parts)).strip("-").lower()
    return f"doc-{slug or 'page'}"


def find_files(project_root: str, extra_dirs: list[str] | None = None) -> list[str]:
    """The Markdown files of the project, as paths from the project root."""
    found: list[str] = []
    readme = _first_readme(project_root)
    if readme:
        found.append(readme)

    for name in list(extra_dirs or []) + list(DOC_DIRS):
        base = os.path.join(project_root, name)
        if not os.path.isdir(base):
            continue
        for dirpath, dirnames, filenames in os.walk(base):
            dirnames[:] = sorted(d for d in dirnames if not d.startswith("."))
            for fn in sorted(filenames):
                if not fn.lower().endswith(DOC_SUFFIXES):
                    continue
                path = os.path.join(dirpath, fn)
                if os.path.getsize(path) > _MAX_BYTES:
                    continue
                rel = os.path.relpath(path, project_root)
                if rel not in found:
                    found.append(rel)
    return found


def _first_readme(project_root: str) -> str:
    for name in os.listdir(project_root):
        if name.lower() in ("readme.md", "readme.markdown"):
            return name
    return ""


# --- Rendering --------------------------------------------------------------


def _parser():
    # `html: False` escapes the HTML in the source. Thus a dependency cannot put
    # a script element in the site.
    return MarkdownIt("commonmark", {"html": False}).enable(["table", "strikethrough"])


_TAG = re.compile(r"<[^>]+>")
_HEADING = re.compile(r"<h([1-3])>(.*?)</h\1>", re.S)


def _anchor(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", _TAG.sub("", text).lower()).strip("-") or "section"


def _add_anchors(html: str) -> tuple[str, list]:
    """Gives each heading an identifier, and collects the headings."""
    headings: list = []
    used: set = set()

    def repl(m):
        level, inner = int(m.group(1)), m.group(2)
        anchor = _anchor(inner)
        n = 2
        while anchor in used:
            anchor, n = f"{_anchor(inner)}-{n}", n + 1
        used.add(anchor)
        headings.append((level, _TAG.sub("", inner).strip(), anchor))
        return f'<h{level} id="{anchor}">{inner}</h{level}>'

    return _HEADING.sub(repl, html), headings


_HREF = re.compile(r'(<a\b[^>]*\bhref=")([^"]+)(")')
_SRC = re.compile(r'(<img\b[^>]*\bsrc=")([^"]+)(")')
_EXTERNAL = re.compile(r"^(?:[a-z][a-z0-9+.-]*:|//|#)")


def _rewrite_links(html: str, rel_path: str, by_rel: dict) -> str:
    """Makes the links between the documentation pages work in the site."""
    base = os.path.dirname(rel_path)

    def repl(m):
        head, target, tail = m.groups()
        if _EXTERNAL.match(target):
            return m.group(0)
        path, _, anchor = target.partition("#")
        if not path:
            return m.group(0)
        rel = os.path.normpath(os.path.join(base, path))
        page = by_rel.get(rel)
        if page is None:
            return m.group(0)
        return f"{head}{page.url}{'#' + anchor if anchor else ''}{tail}"

    return _HREF.sub(repl, html)


def _rewrite_media(html: str, rel_path: str, project_root: str, media: dict) -> str:
    """Points each image at the copy in the site, and records the copy."""
    base = os.path.dirname(rel_path)

    def repl(m):
        head, target, tail = m.groups()
        if _EXTERNAL.match(target):
            return m.group(0)
        rel = os.path.normpath(os.path.join(base, target.partition("#")[0]))
        source = os.path.join(project_root, rel)
        if rel.startswith("..") or not os.path.isfile(source):
            return m.group(0)
        if not rel.lower().endswith(MEDIA_SUFFIXES):
            return m.group(0)
        media[rel] = source
        return f"{head}assets/{MEDIA_DIR}/{rel}{tail}"

    return _SRC.sub(repl, html)


_CODE = re.compile(r"<code>([^<>]+)</code>")


def link_names(html: str, targets: dict) -> str:
    """Makes a link from each `code` element that gives the name of a unit."""
    def repl(m):
        name = m.group(1)
        url = targets.get(name)
        if url is None:
            return m.group(0)
        return f'<a class="xref" href="{url}"><code>{name}</code></a>'

    return _CODE.sub(repl, html)


def _title(html: str, rel_path: str) -> str:
    m = re.search(r"<h1[^>]*>(.*?)</h1>", html, re.S)
    if m:
        return _TAG.sub("", m.group(1)).strip()
    return os.path.splitext(os.path.basename(rel_path))[0].replace("_", " ")


def build_pages(project_root: str, rel_paths: list[str]) -> tuple[dict, dict]:
    """Makes a DocPage for each file. Gives (pages by slug, images to copy)."""
    if not HAVE_MARKDOWN:
        return {}, {}
    md = _parser()
    media: dict = {}

    raw: list = []
    for rel in rel_paths:
        try:
            with open(os.path.join(project_root, rel), errors="replace") as fh:
                text = fh.read()
        except OSError:
            continue
        raw.append((rel, md.render(text)))

    # Two files can give the same slug, for example `README.md` and
    # `doc/README.md`. Each page needs its own name.
    by_rel: dict = {}
    used: set = set()
    for rel, _ in raw:
        slug = _slug(rel)
        if slug in used:
            stem = _slug(rel)
            n = 2
            while slug in used:
                slug, n = f"{stem}-{n}", n + 1
        used.add(slug)
        by_rel[rel] = DocPage(slug=slug, title="", rel_path=rel)
    pages: dict = {}
    for rel, html in raw:
        page = by_rel[rel]
        html = _rewrite_links(html, rel, by_rel)
        html = _rewrite_media(html, rel, project_root, media)
        html, headings = _add_anchors(html)
        page.title = _title(html, rel)
        page.html = html
        page.headings = headings
        page.text = " ".join(_TAG.sub(" ", html).split())[:4000]
        pages[page.slug] = page
    return pages, media


def copy_media(media: dict, outdir: str) -> None:
    """Copies the images of the documentation into the site."""
    for rel, source in media.items():
        dst = os.path.join(outdir, "assets", MEDIA_DIR, rel)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copyfile(source, dst)


def attach_to_modules(pages: dict, module_names) -> None:
    """Attaches a page to the module that has the same name."""
    names = set(module_names)
    for page in pages.values():
        stem = os.path.splitext(os.path.basename(page.rel_path))[0]
        if stem in names:
            page.module = stem


def order_pages(pages: dict) -> list:
    """The sequence in the side bar: the README first, then the other pages."""
    def key(page):
        base = os.path.basename(page.rel_path).lower()
        depth = page.rel_path.count(os.sep)
        first = 0 if depth == 0 and base.startswith("readme") else 1
        index = 0 if base.startswith(("readme", "index")) else 1
        return (first, depth, page.rel_path.rsplit(os.sep, 1)[0], index, page.title.lower())

    return sorted(pages.values(), key=key)
