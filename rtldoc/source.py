"""Makes a page for each source file of the project.

A person who reads the documentation of a module frequently wants the code. Thus
this tool gives a link to it, as Sphinx, Doxygen and rustdoc do. The code is on
its own page, and not on the page of the module, because a file can have
thousands of lines.

The tool shows only the files of this repository. It does not copy the source of
a dependency, because that source has another licence and another repository.

[Pygments](https://pygments.org/) gives the colours and the line numbers.
"""

from __future__ import annotations

import html
import os
import re

from .model import SourceFile

try:
    from pygments import highlight as _highlight
    from pygments.formatters import HtmlFormatter
    from pygments.lexers import get_lexer_by_name
    from pygments.util import ClassNotFound
    HAVE_PYGMENTS = True
except ImportError:  # pragma: no cover - depends on the installed packages
    HAVE_PYGMENTS = False

#: A file with more lines than this keeps its page, but without the colours. The
#: lexer is slow on a large file, and the HTML becomes large.
MAX_HIGHLIGHT_LINES = 6000

#: A larger file is not source code. It gets no page.
MAX_BYTES = 4_000_000

#: The lexer for each suffix.
LEXERS = {
    ".sv": "systemverilog", ".svh": "systemverilog",
    ".v": "verilog", ".vh": "verilog", ".vs": "verilog",
}

#: The style of the colours, for the light theme and for the dark theme.
LIGHT_STYLE = "default"
DARK_STYLE = "github-dark"

_UNSAFE = re.compile(r"[^A-Za-z0-9_]+")


def slug_for(rel_path: str) -> str:
    """The name of the HTML file for a source file."""
    slug = _UNSAFE.sub("-", rel_path.replace("\\", "/")).strip("-").lower()
    return f"src-{slug or 'file'}"


def _lexer_name(rel_path: str) -> str:
    return LEXERS.get(os.path.splitext(rel_path)[1].lower(), "systemverilog")


def _formatter():
    return HtmlFormatter(linenos="table", lineanchors="L", anchorlinenos=True,
                         cssclass="hl")


def _plain(text: str) -> str:
    """The same table as Pygments makes, but without the colours."""
    lines = text.splitlines() or [""]
    nums = "\n".join(f'<span class="normal"><a href="#L-{i}">{i}</a></span>'
                     for i in range(1, len(lines) + 1))
    code = "\n".join(f'<a id="L-{i}" name="L-{i}"></a>{html.escape(line)}'
                     for i, line in enumerate(lines, 1))
    return ('<div class="hl"><table class="hltable"><tr>'
            f'<td class="linenos"><div class="linenodiv"><pre>{nums}</pre></div></td>'
            f'<td class="code"><div><pre>{code}</pre></div></td></tr></table></div>')


def render_code(text: str, rel_path: str) -> tuple[str, bool]:
    """The code as HTML. The flag is False if the colours are not available."""
    if not HAVE_PYGMENTS or text.count("\n") > MAX_HIGHLIGHT_LINES:
        return _plain(text), False
    try:
        lexer = get_lexer_by_name(_lexer_name(rel_path))
    except ClassNotFound:  # pragma: no cover - the suffixes above are known
        return _plain(text), False
    return _highlight(text, lexer, _formatter()), True


def _prefix(css: str, selector: str) -> str:
    """Puts the selector in front of each rule that does not have it.

    Pygments gives the rules for the line numbers without the selector. Without
    this function the dark colours apply to the light theme.
    """
    out = []
    for line in css.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith(selector) or stripped.startswith("/*"):
            out.append(line)
        else:
            out.append(f"{selector} {stripped}")
    return "\n".join(out)


def style_css() -> str:
    """The colours of the code, for both themes."""
    if not HAVE_PYGMENTS:
        return "/* Pygments is not available. The code has no colours. */\n"
    light = HtmlFormatter(style=LIGHT_STYLE).get_style_defs(".hl")
    dark = HtmlFormatter(style=DARK_STYLE).get_style_defs('[data-theme="dark"] .hl')
    return (_prefix(light, ".hl") + "\n"
            + _prefix(dark, '[data-theme="dark"] .hl') + "\n")


def collect(project_root: str, files, modules: dict) -> dict[str, SourceFile]:
    """Reads each source file in the project and makes the HTML of its code.

    *files* gives more paths than the modules do, because a file can declare a
    package only. A file outside the project root is a dependency, thus the tool
    does not read it.
    """
    root = os.path.realpath(project_root)
    by_rel: dict[str, str] = {}
    for path in files:
        real = os.path.realpath(path)
        if not real.startswith(root + os.sep) or not os.path.isfile(real):
            continue
        by_rel.setdefault(os.path.relpath(real, root), real)

    units: dict[str, list] = {}
    for mod in modules.values():
        if mod.file:
            units.setdefault(os.path.realpath(mod.file), []).append(mod)

    out: dict[str, SourceFile] = {}
    used: set[str] = set()
    for rel in sorted(by_rel):
        real = by_rel[rel]
        try:
            if os.path.getsize(real) > MAX_BYTES:
                continue
            with open(real, encoding="utf-8", errors="replace") as fh:
                text = fh.read()
        except OSError:
            continue
        slug, n = slug_for(rel), 2
        while slug in used:
            slug, n = f"{slug_for(rel)}-{n}", n + 1
        used.add(slug)
        mods = sorted(units.get(real, []), key=lambda m: m.line or 0)
        code, coloured = render_code(text, rel)
        out[slug] = SourceFile(
            slug=slug,
            rel_path=rel,
            package=mods[0].package if mods else "",
            lines=len(text.splitlines()),
            bytes=len(text.encode("utf-8", "replace")),
            units=[(m.name, m.line) for m in mods],
            html=code,
            highlighted=coloured,
        )
    return out
