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

import io
import os
import re
import shutil
import warnings
from dataclasses import dataclass, field

import yaml

try:
    from markdown_it import MarkdownIt
    HAVE_MARKDOWN = True
except ImportError:  # pragma: no cover - depends on the installed packages
    MarkdownIt = None
    HAVE_MARKDOWN = False

try:
    from docutils.core import publish_parts
    HAVE_RST = True
except ImportError:  # pragma: no cover - depends on the installed packages
    publish_parts = None
    HAVE_RST = False

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
_RST_SETTINGS = {
    "report_level": 5,          # Report nothing. A Sphinx directive is unknown here.
    "halt_level": 5,            # Never stop on an error.
    "raw_enabled": 0,           # The same rule as for Markdown: no raw HTML.
    "file_insertion_enabled": 0,  # `.. include::` must not read another file.
    "embed_stylesheet": False,
    "output_encoding": "unicode",
    "doctitle_xform": True,
    "sectsubtitle_xform": False,
}


def _render_rst(text: str) -> str:
    """HTML from reStructuredText.

    docutils reads the standard directives. A directive from a Sphinx extension,
    for example `wavedrom`, is unknown; docutils gives no output for it and this
    function does not report it.
    """
    with warnings.catch_warnings():
        # docutils 0.23 reports that `writer_name` goes away in 2.0. The pin in
        # pyproject.toml keeps this version range, and the user cannot act on it.
        warnings.simplefilter("ignore", PendingDeprecationWarning)
        parts = publish_parts(
            text, writer_name="html5",
            settings_overrides={**_RST_SETTINGS, "warning_stream": io.StringIO()},
        )
    return parts["html_body"]


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
        # docutils gives the section an identifier. A second element with the same
        # identifier would make the anchor ambiguous.
        if f'id="{anchor}"' in html:
            headings.append((level, _TAG.sub("", inner).strip(), anchor))
            return m.group(0)
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


#: Where a name of a unit appears. Markdown gives `code`. docutils gives
#: `span class="docutils literal"` for a double backtick and `cite` for a single
#: one. The comments in the PULP repositories put the name in bold.
_CODE = re.compile(
    r'<code>([^<>]+)</code>'
    r'|<span class="docutils literal">([^<>]+)</span>'
    r'|<cite>([^<>]+)</cite>'
    r'|<strong>([^<>]+)</strong>'
)


def link_names(html: str, targets: dict) -> str:
    """Makes a link from each name of a unit in the text."""
    def repl(m):
        name = m.group(1) or m.group(2) or m.group(3) or m.group(4)
        url = targets.get(name)
        if url is None:
            return m.group(0)
        return f'<a class="xref" href="{url}"><code>{name}</code></a>'

    return _CODE.sub(repl, html)


#: A comment that has a directive or a role is reStructuredText. The comments in
#: the PULP repositories use `.. figure::` and `:numref:`.
_RST_MARKS = re.compile(r"^\s*\.\.\s+[a-z_-]+::|:[a-z]+:`", re.M)


#: The Doxygen commands. A command starts with `@` or with a backslash.
_DOXY_MARKS = re.compile(r"[@\\](brief|details|param|return[s]?|retval|note|warning|see)\b")
_DOXY_PARAM = re.compile(r"^\s*[@\\]param\s*(?:\[[^\]]*\])?\s+(\w+)\s*", re.M)
_DOXY_LABEL = re.compile(r"^\s*[@\\](return[s]?|retval|note|warning|see|details)\s*", re.M)
_DOXY_INLINE = re.compile(r"[@\\]([cpba])\s+(\S+)")
_DOXY_LABELS = {"return": "Returns", "returns": "Returns", "retval": "Returns",
                "note": "Note", "warning": "Warning", "see": "See", "details": ""}


def doxygen_to_markdown(text: str) -> str:
    """Markdown from a comment that uses the Doxygen commands.

    Doxygen has no parser for SystemVerilog, but many repositories use its
    commands in the comments. Doxygen reads Markdown, thus the commands become
    Markdown and the usual renderer makes the HTML.
    """
    text = re.sub(r"^\s*[@\\]brief\s*", "", text, flags=re.M)
    text = _DOXY_PARAM.sub(r"- `\1` — ", text)
    # The empty line stops Markdown from adding the text to the list above.
    text = _DOXY_LABEL.sub(lambda m: f"\n**{_DOXY_LABELS[m.group(1).lower()]}:** "
                           if _DOXY_LABELS[m.group(1).lower()] else "\n", text)
    return _DOXY_INLINE.sub(
        lambda m: (f"**{m.group(2)}**" if m.group(1) == "b"
                   else f"*{m.group(2)}*" if m.group(1) == "a"
                   else f"`{m.group(2)}`"),
        text,
    )


def render_comment(text: str) -> str:
    """HTML from the documentation comment of a module.

    The comment is Markdown, reStructuredText or Doxygen. A directive or a role
    shows reStructuredText. A command that starts with `@` shows Doxygen.
    """
    if not text.strip():
        return ""
    try:
        if _RST_MARKS.search(text) and HAVE_RST:
            return _render_rst(text)
        if _DOXY_MARKS.search(text):
            text = doxygen_to_markdown(text)
        if HAVE_MARKDOWN:
            return _parser().render(text)
    except Exception:
        pass
    return ""


def _title(html: str, rel_path: str) -> str:
    m = re.search(r"<h1[^>]*>(.*?)</h1>", html, re.S)
    if m:
        return _TAG.sub("", m.group(1)).strip()
    return os.path.splitext(os.path.basename(rel_path))[0].replace("_", " ")


def build_pages(project_root: str, rel_paths: list[str]) -> tuple[dict, dict]:
    """Makes a DocPage for each file. Gives (pages by slug, images to copy)."""
    md = _parser() if HAVE_MARKDOWN else None
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
            html = _render_rst(text) if is_rst else md.render(text)
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
