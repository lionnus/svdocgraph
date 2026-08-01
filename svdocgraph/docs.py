"""Reads the written documentation of the project.

A repository has two kinds of documentation. The RTL gives the modules, the
ports and the connections. The Markdown files give the text that a person wrote:
the README, and the pages in `doc/` or `docs/`.

This module finds those files and makes a page from each one. `markup` turns the
text into HTML. Three connections join the two kinds:

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

import yaml

from .markup import (
    HAVE_MARKDOWN,
    HAVE_RST,
    add_anchors,
    markdown_parser,
    rst_to_html,
    strip_tags,
)

#: The directories that hold the written documentation, in the sequence of the
#: search. The README of the project root is always included.
DOC_DIRS = ("docs", "doc", "documentation")

#: The files to read. Markdown and reStructuredText.
DOC_SUFFIXES = (".md", ".markdown", ".rst")

#: The settings of a Read the Docs project. They give the directory of the
#: Sphinx or MkDocs configuration, which holds the pages.
RTD_NAMES = (".readthedocs.yaml", ".readthedocs.yml")

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

    for name in list(extra_dirs or []) + read_rtd_dirs(project_root) + list(DOC_DIRS):
        base = os.path.normpath(os.path.join(project_root, name))
        if not os.path.isdir(base):
            continue
        # The root holds the source of the whole repository. Read only the files
        # that are directly in it, not the files of each subdirectory.
        if os.path.normpath(base) == os.path.normpath(project_root):
            walk = [(base, [], sorted(os.listdir(base)))]
        else:
            walk = os.walk(base)
        for dirpath, dirnames, filenames in walk:
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


#: docutils writes each message to this stream. The pages must stay clean.
def read_rtd_dirs(project_root: str) -> list:
    """The directories that a Read the Docs settings file gives."""
    found: list = []
    for name in RTD_NAMES:
        path = os.path.join(project_root, name)
        if not os.path.isfile(path):
            continue
        try:
            with open(path) as fh:
                data = yaml.safe_load(fh) or {}
        except (OSError, yaml.YAMLError):
            return found
        if not isinstance(data, dict):
            return found
        for tool in ("sphinx", "mkdocs"):
            section = data.get(tool)
            if isinstance(section, dict):
                conf = str(section.get("configuration") or "")
                if not conf:
                    continue
                # `configuration: conf.py` means that the pages are in the root.
                folder = os.path.dirname(conf) or "."
                if folder not in found:
                    found.append(folder)
        break
    return found


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


def _title(html: str, rel_path: str) -> str:
    m = re.search(r"<h1[^>]*>(.*?)</h1>", html, re.S)
    if m:
        return strip_tags(m.group(1)).strip()
    return os.path.splitext(os.path.basename(rel_path))[0].replace("_", " ")


def build_pages(project_root: str, rel_paths: list[str]) -> tuple[dict, dict]:
    """Makes a DocPage for each file. Gives (pages by slug, images to copy)."""
    md = markdown_parser() if HAVE_MARKDOWN else None
    media: dict = {}

    raw: list = []
    for rel in rel_paths:
        is_rst = rel.lower().endswith(".rst")
        if (is_rst and not HAVE_RST) or (not is_rst and md is None):
            continue
        try:
            with open(os.path.join(project_root, rel), errors="replace") as fh:
                text = fh.read()
        except OSError:
            continue
        try:
            html = rst_to_html(text) if is_rst else md.render(text)
        except Exception:
            continue      # One bad file must not stop the documentation.
        raw.append((rel, html))

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
        html, headings = add_anchors(html)
        page.title = _title(html, rel)
        page.html = html
        page.headings = headings
        page.text = " ".join(re.sub(r"<[^>]+>", " ", html).split())[:4000]
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
