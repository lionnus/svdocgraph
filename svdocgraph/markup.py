"""Turns the markup that a person wrote into HTML.

The tool reads three kinds of markup: Markdown, reStructuredText and the Doxygen
commands. The written pages of a repository and the comment above a module both
come through here, thus the two look the same in the site.

Each parser is an external package: markdown-it-py and docutils. The HTML in the
source is escaped, and a `raw` directive gives no output. Thus a dependency
cannot put a script element in the site.
"""

from __future__ import annotations

import io
import re
import warnings

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


def rst_to_html(text: str) -> str:
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


def markdown_parser():
    # `html: False` escapes the HTML in the source. Thus a dependency cannot put
    # a script element in the site.
    return MarkdownIt("commonmark", {"html": False}).enable(["table", "strikethrough"])


_TAG = re.compile(r"<[^>]+>")
_HEADING = re.compile(r"<h([1-3])>(.*?)</h\1>", re.S)


def _anchor(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", _TAG.sub("", text).lower()).strip("-") or "section"


def add_anchors(html: str) -> tuple[str, list]:
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
            return rst_to_html(text)
        if _DOXY_MARKS.search(text):
            text = doxygen_to_markdown(text)
        if HAVE_MARKDOWN:
            return markdown_parser().render(text)
    except Exception:
        pass
    return ""




def strip_tags(html: str) -> str:
    """The text of an HTML fragment, without the elements."""
    return _TAG.sub("", html)
